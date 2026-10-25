// Actual production display code, rendered by real LVGL on a memory display.
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "Display.cpp"

DeviceSettings g_Settings;
SessionInfo g_SessionInfo;
SessionData g_Sessions[4];
ModeStates g_ModeStates;
MeterData g_MeterData;
PcStatsData g_PcStats;
bool g_PcStatsValid = false;
MediaInfoData g_MediaInfo;
bool g_MediaInfoValid = false;
uint32_t g_Now = 0, g_HeartbeatTimeout = 0;
bool g_DisplayAsleep = false, g_ClockMode = false, g_PcAsleep = false;

namespace Input {
bool g_RawKeyStates[6] = {};
bool g_KeyStatesChanged = false;
bool TouchAvailable() { return true; }
TouchEvent LastTouchEvent() { return TouchEvent::None; }
uint8_t LastTouchRawGesture() { return 0; }
uint8_t LastTouchFingers() { return 0; }
uint16_t LastTouchX() { return 0; }
uint16_t LastTouchY() { return 0; }
bool TouchIntActive() { return false; }
uint32_t TouchSampleCounter() { return 0; }
}

namespace {
constexpr int WIDTH = 320, HEIGHT = 240, BUFFER_LINES = 24;
static lv_color_t buffer_a[WIDTH * BUFFER_LINES], buffer_b[WIDTH * BUFFER_LINES];
static std::array<uint16_t, WIDTH * HEIGHT> framebuffer;
static lv_disp_t *display = nullptr;
static uint32_t clock_tick = 0;
static unsigned high_writes = 0, low_writes = 0;
static unsigned max_used_bytes = 0, frames_rendered = 0;
static bool backlight = false;
struct DrawText {
    std::string text;
    lv_area_t area;
    unsigned line_height;
    bool marquee;
};
static std::vector<DrawText> text_trace;

void require(bool value, const char *message) {
    if (!value) { std::fprintf(stderr, "Native theme assertion: %s\n", message); std::abort(); }
}

void flush(lv_disp_drv_t *driver, const lv_area_t *area, lv_color_t *pixels) {
    require(area->x1 >= 0 && area->y1 >= 0 && area->x2 < WIDTH && area->y2 < HEIGHT,
            "LVGL flush escaped 320x240 bounds");
    for (int y = area->y1; y <= area->y2; ++y)
        for (int x = area->x1; x <= area->x2; ++x)
            framebuffer[y * WIDTH + x] = (pixels++)->full;
    lv_disp_flush_ready(driver);
}

void refresh() {
    text_trace.clear();
    lv_obj_update_layout(lv_scr_act());
    Display::Update();
    lv_obj_invalidate(lv_scr_act());
    lv_refr_now(display);
    lv_mem_monitor_t memory;
    lv_mem_monitor(&memory);
    max_used_bytes = std::max(max_used_bytes, unsigned(memory.total_size - memory.free_size));
    require(lv_mem_test() == LV_RES_OK, "LVGL heap integrity failed");
    ++frames_rendered;
}

void write_frame(const std::string &path) {
    FILE *file = std::fopen(path.c_str(), "wb");
    require(file != nullptr, "Cannot create native framebuffer output");
    for (uint16_t pixel : framebuffer) {
        const uint8_t bytes[] = {uint8_t(pixel), uint8_t(pixel >> 8)};
        require(std::fwrite(bytes, 1, 2, file) == 2, "Framebuffer write failed");
    }
    std::fclose(file);
    file = std::fopen((path.substr(0, path.size() - 7) + ".draw.json").c_str(), "wb");
    require(file != nullptr, "Cannot create native draw trace");
    std::fputs("[", file);
    for (size_t i = 0; i < text_trace.size(); ++i) {
        const auto &entry = text_trace[i];
        if (i) std::fputc(',', file);
        std::fputs("{\"text\":\"", file);
        for (unsigned char ch : entry.text) {
            if (ch == '"' || ch == '\\') std::fputc('\\', file);
            if (ch < 32) std::fprintf(file, "\\u%04x", unsigned(ch));
            else std::fputc(ch, file);
        }
        std::fprintf(file, "\",\"rect\":[%d,%d,%d,%d],\"font_line_height\":%u,\"marquee\":%s}",
                     entry.area.x1, entry.area.y1, lv_area_get_width(&entry.area),
                     lv_area_get_height(&entry.area), entry.line_height, entry.marquee ? "true" : "false");
    }
    std::fputs("]\n", file);
    std::fclose(file);
}

unsigned objects(lv_obj_t *parent) {
    unsigned total = 1;
    for (uint32_t index = 0; index < lv_obj_get_child_cnt(parent); ++index)
        total += objects(lv_obj_get_child(parent, index));
    return total;
}

void set_clock(uint8_t style) {
    g_Settings.clockStyle = style & 7;
    g_Settings.clockStyleHigh = style >> 3;
}

void initialize() {
    require(LV_COLOR_DEPTH == 16 && LV_COLOR_16_SWAP == 0 && sizeof(lv_color_t) == 2,
            "The test must use native RGB565 without byte swapping");
    lv_init();
    static lv_disp_draw_buf_t buffers;
    lv_disp_draw_buf_init(&buffers, buffer_a, buffer_b, WIDTH * BUFFER_LINES);
    static lv_disp_drv_t driver;
    lv_disp_drv_init(&driver);
    driver.hor_res = WIDTH; driver.ver_res = HEIGHT;
    driver.draw_buf = &buffers; driver.flush_cb = flush;
    display = lv_disp_drv_register(&driver);
    Display::Wake();
}

void clocks(const std::string &directory) {
    const uint8_t moments[][3] = {{0, 0, 0}, {10, 8, 36}, {12, 34, 1}, {23, 59, 59}};
    unsigned verified_changes = 0, verified_sleep = 0;
    for (uint8_t style = 0; style < 16; ++style) {
        set_clock(style);
        for (unsigned moment = 0; moment < 4; ++moment) {
            const auto &time = moments[moment];
            Display::ClockScreen(time[0], time[1], time[2]);
            refresh();
            const auto before = framebuffer;
            char filename[48];
            std::snprintf(filename, sizeof(filename), "/clock-%02u-%u.rgb565", style, moment);
            write_frame(directory + filename);
#if VUNMIX_HAS_DEVICE_THEMES
            const unsigned retained_objects = objects(lv_scr_act());
            for (uint8_t theme = 0; theme < 8; ++theme) {
                const DeviceSettings settings_before = g_Settings;
                Display::SetDeviceTheme(theme);
                require(Display::DeviceTheme() == theme, "Selected theme ID was not retained");
                require(std::memcmp(&settings_before, &g_Settings, sizeof(g_Settings)) == 0,
                        "Theme selection modified clock or other device settings");
                refresh();
                require(framebuffer == before, "Selecting a theme modified visible clock pixels");
                Display::ClockScreen(time[0], time[1], time[2]);
                refresh();
                require(framebuffer == before, "Clock redraw after theme selection changed pixels");
                require(objects(lv_scr_act()) == retained_objects,
                        "Theme selection allocated extra clock objects");
                require(Display::ActiveDeviceTheme() == 255,
                        "Clock incorrectly reported an active device theme");
                ++verified_changes;

                Display::Sleep();
                const unsigned wakes_before = high_writes;
                require(!backlight, "Display::Sleep failed to turn off backlight");
                Display::SetDeviceTheme((theme + 1) % 8);
                refresh();
                require(!backlight && high_writes == wakes_before,
                        "Theme selection woke a sleeping display");
                require(framebuffer == before, "Deferred sleeping theme selection changed clock");
                Display::Wake();
                Display::ClockScreen(time[0], time[1], time[2]);
                refresh();
                require(framebuffer == before, "Wake changed the original clock pixels");
                ++verified_sleep;
            }
#endif
        }
    }
    std::printf("{\"clock_frames\":64,\"theme_changes_while_clock\":%u,"
                "\"theme_changes_while_sleeping\":%u,\"max_host_lvgl_heap_bytes\":%u,"
                "\"rendered_frames\":%u}\n", verified_changes, verified_sleep,
                max_used_bytes, frames_rendered);
}

#if VUNMIX_HAS_DEVICE_THEMES
void health(bool valid, bool full = false) {
    g_PcStatsValid = valid;
    g_PcStats.cpuUsage = 56; g_PcStats.cpuTemp = 62;
    g_PcStats.gpuUsage = 42; g_PcStats.gpuTemp = 58;
    g_PcStats.ramUsage = 68; g_PcStats.ramUsedMB = 11161; g_PcStats.ramTotalMB = 16384;
    g_PcStats.netDownKBps = 2458; g_PcStats.netUpKBps = 307;
    if (full) {
        g_PcStats.cpuUsage = g_PcStats.gpuUsage = g_PcStats.ramUsage = 100;
        g_PcStats.cpuTemp = g_PcStats.gpuTemp = 100;
    }
    Display::HealthScreen(valid, 3600, valid ? 25 : 5000, 100000, 80000, 64000,
                         120, 90, 0, 0, Command::OK, Command::NONE,
                         MODE_HEALTH, 0, 3, 1, 2, true, 12);
    refresh();
}

lv_obj_t *legacy_scrolling_label(lv_obj_t *parent) {
    if (lv_obj_get_class(parent) == &lv_label_class &&
            lv_label_get_long_mode(parent) == LV_LABEL_LONG_SCROLL_CIRCULAR &&
            std::strstr(lv_label_get_text(parent), "WM") != nullptr) return parent;
    for (uint32_t i = 0; i < lv_obj_get_child_cnt(parent); ++i) {
        if (auto *found = legacy_scrolling_label(lv_obj_get_child(parent, i))) return found;
    }
    return nullptr;
}

lv_area_t marquee_region(uint8_t theme) {
    lv_area_t area{};
    bool found = false;
    if (theme == 0) {
        if (auto *label = legacy_scrolling_label(lv_scr_act())) {
            lv_obj_get_coords(label, &area); found = true;
        }
    } else {
        for (const auto &entry : text_trace) {
            if (entry.marquee && entry.area.x1 >= 0 && entry.area.x1 < WIDTH &&
                    std::strstr(entry.text.c_str(), "WM") != nullptr) {
                area = entry.area; found = true; break;
            }
        }
    }
    require(found, "Long default/media text did not enter its marquee path");
    // Compare only the text viewport; independently changing meters cannot
    // create a false-positive movement result elsewhere in the framebuffer.
    area.x2 = std::min<lv_coord_t>(area.x1 + 119, WIDTH - 1);
    area.y2 = std::min<lv_coord_t>(area.y2, HEIGHT - 1);
    return area;
}

bool same_region(const std::array<uint16_t, WIDTH * HEIGHT> &before, const lv_area_t &area) {
    for (int y = area.y1; y <= area.y2; ++y)
        for (int x = area.x1; x <= area.x2; ++x)
            if (before[y * WIDTH + x] != framebuffer[y * WIDTH + x]) return false;
    return true;
}

unsigned check_marquees(uint8_t theme) {
    SessionData long_name;
    std::strcpy(long_name.name, "WMWMMWWMWWWMWMWMMWMWWMMWWMWMW");
    require(std::strlen(long_name.name) == 29, "Marquee fixture must occupy 29 wire bytes");
    long_name.data.id = 1; long_name.data.volume = 68; long_name.data.isDefault = true;
    Display::DeviceEditScreen(&long_name, "Out", MODE_OUTPUT); refresh();
    const auto name_region = marquee_region(theme);
    auto before = framebuffer;
    for (unsigned tick = 1; tick <= 20; ++tick) {
        clock_tick += 100; g_Now = clock_tick; g_HeartbeatTimeout = g_Now + 5000;
        Display::SetMeterLevels((tick * 7) % 101, 0);
        Display::DeviceEditScreen(&long_name, "Out", MODE_OUTPUT); refresh();
    }
    require(!same_region(before, name_region), "Default name marquee restarted on live meter updates");
    long_name.data.isDefault = false;
    Display::DeviceEditScreen(&long_name, "Out", MODE_OUTPUT); refresh();
    before = framebuffer;
    for (unsigned tick = 1; tick <= 20; ++tick) {
        clock_tick += 100; g_Now = clock_tick; g_HeartbeatTimeout = g_Now + 5000;
        Display::SetMeterLevels((tick * 7) % 101, 0);
        Display::DeviceEditScreen(&long_name, "Out", MODE_OUTPUT); refresh();
    }
    require(same_region(before, name_region), "Nondefault endpoint name started scrolling");
    if (theme == 0) return 2; // New renderers preserve media scrolling; Classic is unchanged.

    const auto saved_media = g_MediaInfo;
    const bool saved_valid = g_MediaInfoValid;
    std::strcpy(g_MediaInfo.title, "WMWMMWWMWWWMWMWMMWMWWMMWWMWMW");
    std::strcpy(g_MediaInfo.artist, "WMWMMWWMWWWMWMWMMWM");
    g_MediaInfoValid = true;
    SessionData app;
    std::strcpy(app.name, "Spotify"); app.data.id = 3; app.data.volume = 44;
    Display::ApplicationEditScreen(&app, MODE_APPLICATION); refresh();
    const auto media_region = marquee_region(theme);
    before = framebuffer;
    for (unsigned tick = 1; tick <= 20; ++tick) {
        clock_tick += 100; g_Now = clock_tick; g_HeartbeatTimeout = g_Now + 5000;
        Display::SetMeterLevels((tick * 7) % 101, 0);
        Display::ApplicationEditScreen(&app, MODE_APPLICATION); refresh();
    }
    require(!same_region(before, media_region), "PC media marquee restarted on live meter updates");
    g_MediaInfo = saved_media; g_MediaInfoValid = saved_valid;
    return 3;
}

void check_classic_game_labels() {
    lv_obj_t *bars[] = {Display::s_faderA, Display::s_faderB};
    lv_obj_t *names[] = {Display::s_faderNameA, Display::s_faderNameB};
    for (unsigned i = 0; i < 2; ++i) {
        auto *value = static_cast<lv_obj_t *>(lv_obj_get_user_data(bars[i]));
        lv_area_t name_area, value_area, overlap;
        lv_obj_get_coords(names[i], &name_area); lv_obj_get_coords(value, &value_area);
        require(!_lv_area_intersect(&overlap, &name_area, &value_area),
                "Classic Game volume and session name labels overlap");
    }
}

void lifecycle(const std::string &directory) {
    constexpr unsigned CYCLES = 24;
    unsigned dynamic_checks = 0;
    unsigned marquee_checks = 0;
    size_t stable_free = 0, stable_largest = 0;
    unsigned stable_objects = 0, stable_used_count = 0;
    SessionData output, input, app, alternate;
    std::strcpy(output.name, "Realtek USB Audio");
    output.data.id = 1; output.data.isDefault = true; output.data.volume = 68;
    std::strcpy(input.name, "Microphone USB");
    input.data.id = 2; input.data.isDefault = true; input.data.isMuted = true; input.data.volume = 72;
    std::strcpy(app.name, "Spotify"); app.data.id = 3; app.data.volume = 44;
    std::strcpy(alternate.name, "Counter-Strike"); alternate.data.id = 4; alternate.data.volume = 80;
    g_SessionInfo.sessions[0] = 3; g_SessionInfo.sessions[1] = 1; g_SessionInfo.sessions[2] = 2;
    g_HeartbeatTimeout = 5000;
    std::strcpy(g_MediaInfo.title, "A Moment Apart");
    std::strcpy(g_MediaInfo.artist, "ODESZA");
    g_MediaInfo.isPlaying = 1; g_MediaInfoValid = true;
    auto snapshot = [&](unsigned cycle, uint8_t theme, const char *scene) {
        if (cycle != 0) return;
        char filename[80];
        std::snprintf(filename, sizeof(filename), "/theme-%u-%s.rgb565", theme, scene);
        write_frame(directory + filename);
    };

    for (unsigned cycle = 0; cycle < CYCLES; ++cycle) {
        for (uint8_t theme = 0; theme < 8; ++theme) {
            const auto settings_before = g_Settings;
            const auto mode_before = g_ModeStates;
            const auto session_before = g_SessionInfo;
            Display::SetDeviceTheme(theme);
            require(std::memcmp(&settings_before, &g_Settings, sizeof(g_Settings)) == 0 &&
                    std::memcmp(&mode_before, &g_ModeStates, sizeof(g_ModeStates)) == 0 &&
                    std::memcmp(&session_before, &g_SessionInfo, sizeof(g_SessionInfo)) == 0,
                    "Theme change mutated device/model state");
            Display::SetMeterLevels(36, 0);
            Display::DeviceEditScreen(&output, "Out", MODE_OUTPUT);
            refresh();
            require(Display::ActiveDeviceTheme() == theme, "Non-clock theme was not applied");
            snapshot(cycle, theme, "output");
            output.data.volume = 0;
            Display::DeviceEditScreen(&output, "Out", MODE_OUTPUT); refresh();
            snapshot(cycle, theme, "output-zero");
            auto previous = framebuffer;
            output.data.volume = 100;
            Display::DeviceEditScreen(&output, "Out", MODE_OUTPUT); refresh();
            snapshot(cycle, theme, "output-full");
            require(framebuffer != previous, "Volume 0 and 100 rendered identically"); ++dynamic_checks;
            output.data.volume = 68;

            Display::DeviceEditScreen(&input, "In", MODE_INPUT); refresh();
            snapshot(cycle, theme, "input-muted");
            previous = framebuffer;
            input.data.isMuted = false;
            Display::DeviceEditScreen(&input, "In", MODE_INPUT); refresh();
            require(framebuffer != previous && input.data.volume == 72,
                    "Mute rendering lost stored volume or failed to update"); ++dynamic_checks;
            input.data.isMuted = true;

            SessionData focused;
            std::strcpy(focused.name, "Headphones");
            focused.data.id = 6; focused.data.volume = 30;
            g_Sessions[INDEX_CURRENT] = focused;
            g_Sessions[INDEX_PREVIOUS] = output;
            std::strcpy(g_Sessions[INDEX_NEXT].name, "HDMI Display");
            g_Sessions[INDEX_NEXT].data.volume = 40;
            g_SessionInfo.current = 2;
            Display::DeviceSelectScreen(&focused, true, false, MODE_OUTPUT); refresh();
            snapshot(cycle, theme, "select");
            previous = framebuffer;
            focused.data.volume = 100;
            Display::DeviceSelectScreen(&focused, true, false, MODE_OUTPUT); refresh();
            snapshot(cycle, theme, "select-full");
            Display::DeviceEditScreen(&output, "Out", MODE_OUTPUT); refresh();
            require(framebuffer != previous, "Browse/default/edit state did not repaint"); ++dynamic_checks;

            Display::ApplicationEditScreen(&app, MODE_APPLICATION); refresh();
            snapshot(cycle, theme, "apps");
            previous = framebuffer;
            SessionData empty;
            g_SessionInfo.sessions[2] = 0;
            g_MediaInfoValid = false;
            Display::ApplicationSelectScreen(&empty, false, false, MODE_APPLICATION); refresh();
            snapshot(cycle, theme, "no-apps");
            require(framebuffer != previous, "Empty application selection reused old pixels"); ++dynamic_checks;
            g_SessionInfo.sessions[2] = 2;
            g_MediaInfoValid = true;

            SessionData voice;
            std::strcpy(voice.name, "Discord"); voice.data.id = 5; voice.data.volume = 55;
            Display::GameSelectScreen(&alternate, 'A', false, true, MODE_GAME); refresh();
            snapshot(cycle, theme, "game-select-a");
            Display::GameSelectScreen(&voice, 'B', true, false, MODE_GAME); refresh();
            snapshot(cycle, theme, "game-select-b");
            Display::GameEditScreen(&alternate, &voice, MODE_GAME); refresh();
            if (theme == 0) check_classic_game_labels();
            snapshot(cycle, theme, "game");
            previous = framebuffer;
            voice.data.volume = alternate.data.volume = 100;
            Display::GameEditScreen(&alternate, &voice, MODE_GAME); refresh();
            if (theme == 0) check_classic_game_labels();
            snapshot(cycle, theme, "game-full");
            voice.data.volume = 80; alternate.data.volume = 55;
            Display::GameEditScreen(&alternate, &voice, MODE_GAME); refresh();
            require(framebuffer != previous, "Game A/B live values failed to repaint"); ++dynamic_checks;
            alternate.data.volume = 80;

            SessionData unicode_name = output;
            std::strcpy(unicode_name.name, u8"Âm thanh Việt Nam 12345");
            require(std::strlen(unicode_name.name) <= 29, "UTF-8 fixture exceeds protocol name field");
            Display::DeviceEditScreen(&unicode_name, "Out", MODE_OUTPUT); refresh();
            snapshot(cycle, theme, "long-name");
            Display::SetMeterLevels(0, 0);
            Display::DeviceEditScreen(&output, "Out", MODE_OUTPUT); refresh();
            previous = framebuffer;
            Display::SetMeterLevels(100, 50);
            Display::DeviceEditScreen(&output, "Out", MODE_OUTPUT); refresh();
            require(framebuffer != previous, "Live meter data failed to repaint"); ++dynamic_checks;

            if (cycle == 0) marquee_checks += check_marquees(theme);

            health(true); snapshot(cycle, theme, "health"); previous = framebuffer;
            health(true, true); snapshot(cycle, theme, "health-full");
            health(false);
            snapshot(cycle, theme, "health-wait");
            require(framebuffer != previous, "Health waiting/offline state reused telemetry pixels"); ++dynamic_checks;
            g_HeartbeatTimeout = 0;
            Display::SplashScreen(); refresh();
            snapshot(cycle, theme, "offline");
            Display::InfoScreen(true); refresh();
            snapshot(cycle, theme, "info");
            Input::g_RawKeyStates[0] = true;
            Display::KeyTestScreen(); refresh();
            snapshot(cycle, theme, "key-test");
            Input::g_RawKeyStates[0] = false;
            Display::KeyTestScreen(); refresh();
            clock_tick += 16;
            g_Now = clock_tick;
            g_HeartbeatTimeout = g_Now + 5000;
        }
        // Return to exactly the same small original screen for leak accounting.
        set_clock(0);
        Display::ClockScreen(10, 8, 36); refresh();
        lv_mem_monitor_t memory;
        lv_mem_monitor(&memory);
        if (cycle == 1) {
            stable_free = memory.free_size; stable_largest = memory.free_biggest_size;
            stable_used_count = memory.used_cnt; stable_objects = objects(lv_scr_act());
        } else if (cycle > 1) {
            require(memory.free_size == stable_free && memory.used_cnt == stable_used_count,
                    "Retained LVGL allocation grew across identical theme/mode cycles");
            require(memory.free_biggest_size == stable_largest,
                    "Largest free LVGL block degraded across identical cycles");
            require(objects(lv_scr_act()) == stable_objects,
                    "Retained widget count grew across theme/mode cycles");
        }
    }
    std::printf("{\"cycles\":%u,\"theme_mode_rounds\":%u,\"dynamic_pixel_checks\":%u,"
                "\"marquee_pixel_checks\":%u,"
                "\"stable_free_bytes\":%u,\"stable_largest_free_block\":%u,"
                "\"stable_objects\":%u,\"max_host_lvgl_heap_bytes\":%u,\"rendered_frames\":%u}\n",
                CYCLES, CYCLES * 8, dynamic_checks, marquee_checks, unsigned(stable_free),
                unsigned(stable_largest), stable_objects, max_used_bytes, frames_rendered);
}
#endif
} // namespace

// Only ThemeRenderer.cpp redirects calls here. This observes real immediate
// drawing, then invokes the original LVGL rasterizer unchanged. It cannot see
// the shared legacy diagnostics, whose layout is outside the theme change.
extern "C" void native_draw_label(lv_draw_ctx_t *context, const lv_draw_label_dsc_t *descriptor,
                                   const lv_area_t *area, const char *text,
                                   lv_draw_label_hint_t *hint) {
    const bool marquee = (descriptor->flag & LV_TEXT_FLAG_EXPAND) != 0;
    if (area->y1 < 0 || area->y2 >= HEIGHT || (!marquee && (area->x1 < 0 || area->x2 >= WIDTH))) {
        std::fprintf(stderr, "Immediate text out of bounds: '%s' at %d,%d..%d,%d\n",
                     text, area->x1, area->y1, area->x2, area->y2);
        std::abort();
    }
    lv_point_t measured{};
    lv_txt_get_size(&measured, text, descriptor->font, descriptor->letter_space,
                    descriptor->line_space, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
    if (!marquee && (measured.x > lv_area_get_width(area) || measured.y > lv_area_get_height(area))) {
        std::fprintf(stderr, "Immediate text clips its drawing area: '%s'\n", text);
        std::abort();
    }
    if (std::strcmp(text, "...") == 0 ||
            (text[0] >= '0' && text[0] <= '9' && std::strstr(text, "...") != nullptr)) {
        std::fprintf(stderr, "A scalar field was truncated instead of showing its value: '%s'\n", text);
        std::abort();
    }
    bool duplicate = false;
    for (const auto &entry : text_trace)
        if (entry.text == text && std::memcmp(&entry.area, area, sizeof(*area)) == 0) duplicate = true;
    if (!duplicate) text_trace.push_back({text, *area, descriptor->font->line_height, marquee});
    lv_draw_label(context, descriptor, area, text, hint);
}

extern "C" uint32_t millis(void) { return clock_tick; }
void native_gpio_write(int pin, int value) {
    require(pin == PIN_TFT_BL, "Unexpected hardware pin accessed by display renderer");
    backlight = value == HIGH;
    if (backlight) ++high_writes; else ++low_writes;
}

int main(int argc, char **argv) {
    if (argc != 3) { std::fprintf(stderr, "Usage: native-theme clocks|lifecycle output_directory\n"); return 2; }
    initialize();
    if (std::strcmp(argv[1], "clocks") == 0) clocks(argv[2]);
#if VUNMIX_HAS_DEVICE_THEMES
    else if (std::strcmp(argv[1], "lifecycle") == 0) lifecycle(argv[2]);
#endif
    else return 3;
    return 0;
}
