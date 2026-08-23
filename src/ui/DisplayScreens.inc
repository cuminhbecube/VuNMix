#include "Display.h"
#include "Input.h"
#include <TFT_eSPI.h>
#include <lvgl.h>

LV_FONT_DECLARE(lv_font_dseg_90_bpp1);

extern DeviceSettings g_Settings;

namespace Display {
    TFT_eSPI tft = TFT_eSPI();

    static constexpr int16_t SW = 320;
    static constexpr int16_t SH = 240;

    static const uint32_t BUF_LINES = (uint32_t)SH / 10u;
    static lv_color_t s_buf1[(uint32_t)SW * ((uint32_t)SH / 10u)];
    static lv_color_t s_buf2[(uint32_t)SW * ((uint32_t)SH / 10u)];

    static lv_disp_drv_t      s_dispDrv;
    static lv_disp_draw_buf_t s_dispBuf;

    // =========================================================
    // Cyber-Tactile Design Tokens
    // =========================================================
    static const uint32_t COL_BG             = 0x141218;
    static const uint32_t COL_SURFACE        = 0x141218;
    static const uint32_t COL_SURFACE_LOW    = 0x0F0D13;
    static const uint32_t COL_SURFACE_HIGH   = 0x36343A;
    static const uint32_t COL_SURFACE_CONT   = 0x211F24;
    static const uint32_t COL_ON_SURFACE     = 0xE6E0E9;
    static const uint32_t COL_ON_SURFACE_V   = 0xCBC4D2;
    static const uint32_t COL_PRIMARY        = 0xCFBCFF;
    static const uint32_t COL_OUTLINE_V      = 0x494551;
    static const uint32_t COL_GLASS_BORDER   = 0x2A2A2F; // ~10% white on dark

    // Mode accent colors
    static const uint32_t COL_CYAN   = 0x06B6D4; // Output
    static const uint32_t COL_PURPLE = 0xCFBCFF; // Input
    static const uint32_t COL_GREEN  = 0x00FF88; // Application
    static const uint32_t COL_ORANGE = 0xFF7A00; // Game
    static const uint32_t COL_BLUE   = 0x60A5FA; // Health / debug

    // Layout constants
    static const int16_t HEADER_H  = 32;
    static const int16_t NAVBAR_H  = 32;
    static const int16_t STRIP_H   = 2;
    static const int16_t CONTENT_Y = HEADER_H;
    static const int16_t CONTENT_H = SH - HEADER_H - STRIP_H - NAVBAR_H;
    static const int16_t PAD       = 6;

    // =========================================================
    // TFT Flush Callback
    // =========================================================
    static void flushCB(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_p)
    {
        uint32_t w = (uint32_t)(area->x2 - area->x1 + 1);
        uint32_t h = (uint32_t)(area->y2 - area->y1 + 1);
        tft.startWrite();
        tft.setAddrWindow(area->x1, area->y1, w, h);
        tft.pushColors((uint16_t *)color_p, w * h, true);
        tft.endWrite();
        lv_disp_flush_ready(drv);
    }

    // =========================================================
    // Init
    // =========================================================
    void Initialize() {
        pinMode(PIN_TFT_BL, OUTPUT);
        digitalWrite(PIN_TFT_BL, HIGH);
        delay(100);

        tft.init();
        delay(100);

        tft.setRotation(1);

        tft.fillScreen(TFT_BLACK);

        lv_init();

        lv_disp_draw_buf_init(&s_dispBuf, s_buf1, s_buf2, (uint32_t)SW * BUF_LINES);

        lv_disp_drv_init(&s_dispDrv);
        s_dispDrv.hor_res  = SW;
        s_dispDrv.ver_res  = SH;
        s_dispDrv.flush_cb = flushCB;
        s_dispDrv.draw_buf = &s_dispBuf;
        lv_disp_drv_register(&s_dispDrv);

    }

    void Update() {
        lv_task_handler();
    }

    // =========================================================
    // Screen Tracking
    // =========================================================
    enum class ScreenType {
        NONE, SPLASH, KEY_TEST, INFO, CLOCK, DEVICE_SELECT, DEVICE_EDIT, GAME_SELECT, GAME_EDIT, HEALTH
    };

    static ScreenType s_currentScreen = ScreenType::NONE;

    // --- Persistent UI Shell objects ---
    static lv_obj_t* s_header     = nullptr;
    static lv_obj_t* s_headerIcon = nullptr;
    static lv_obj_t* s_headerTitle= nullptr;
    static lv_obj_t* s_navbar     = nullptr;
    static constexpr uint8_t NAV_MODE_COUNT = 5;
    static lv_obj_t* s_navBtns[NAV_MODE_COUNT] = {nullptr};
    static lv_obj_t* s_glowStrip  = nullptr;
    static lv_obj_t* s_contentArea= nullptr;
    static lv_obj_t* s_meterCurrent = nullptr;
    static lv_obj_t* s_meterAlternate = nullptr;
    static lv_obj_t* s_appIconImg = nullptr;
    static uint8_t s_meterCurrentValue = 0;
    static uint8_t s_meterAlternateValue = 0;
    static lv_color_t s_appIconCanvasBuf[16 * 16];
    static lv_img_dsc_t s_appIconDsc;

    // --- Content widgets (reused per screen) ---
    static lv_obj_t* s_titleLabel  = nullptr;
    static lv_obj_t* s_volArc      = nullptr;
    static lv_obj_t* s_volLabel    = nullptr;
    static lv_obj_t* s_volArcB     = nullptr;
    static lv_obj_t* s_volLabelB   = nullptr;
    static lv_obj_t* s_subLabel    = nullptr;
    static lv_obj_t* s_subLabelB   = nullptr;

    // Game mixer widgets. These objects are children of s_contentArea and
    // therefore become invalid whenever ClearContent/FullReset cleans LVGL.
    static lv_obj_t* s_faderA      = nullptr;
    static lv_obj_t* s_faderB      = nullptr;
    static lv_obj_t* s_faderNameA  = nullptr;
    static lv_obj_t* s_faderNameB  = nullptr;

    // PC Stats / Dashboard widgets
    static lv_obj_t* s_cpuArc      = nullptr;
    static lv_obj_t* s_cpuVal      = nullptr;
    static lv_obj_t* s_cpuSub      = nullptr;
    static lv_obj_t* s_gpuArc      = nullptr;
    static lv_obj_t* s_gpuVal      = nullptr;
    static lv_obj_t* s_gpuSub      = nullptr;
    static lv_obj_t* s_ramArc      = nullptr;
    static lv_obj_t* s_ramVal      = nullptr;
    static lv_obj_t* s_ramSub      = nullptr;
    static lv_obj_t* s_netDownLbl  = nullptr;
    static lv_obj_t* s_netUpLbl    = nullptr;
    static lv_obj_t* s_sysLinkLbl  = nullptr;
    static lv_obj_t* s_sysHeapLbl  = nullptr;

    // Splash specific
    static lv_obj_t* s_splashDots  = nullptr;
    static lv_anim_t s_dotAnim;
    static uint8_t   s_dotState = 0;

    static constexpr uint8_t APP_ICON_SIZE = 16;
    static constexpr uint16_t APP_ICON_BYTES = APP_ICON_SIZE * APP_ICON_SIZE * 2;
    static constexpr uint8_t APP_ICON_CACHE_SIZE = 8;
    struct AppIconCacheEntry {
        uint8_t id = 0;
        uint16_t received = 0;
        uint8_t data[APP_ICON_BYTES] = {0};
    };
    static AppIconCacheEntry s_appIcons[APP_ICON_CACHE_SIZE];
    static uint8_t s_appIconWriteSlot = 0;

    // Track which mode the shell was built for
    static DisplayMode s_shellMode = MODE_SPLASH;
    static bool s_shellBuilt = false;

    static AppIconCacheEntry* FindAppIcon(uint8_t id) {
        if (id == 0) return nullptr;
        for (uint8_t i = 0; i < APP_ICON_CACHE_SIZE; ++i) {
            if (s_appIcons[i].id == id)
                return &s_appIcons[i];
        }
        return nullptr;
    }

    static void UpdateAppIcon(uint8_t id, DisplayMode mode) {
        if (!s_appIconImg || !s_headerIcon || mode != MODE_APPLICATION)
            return;

        AppIconCacheEntry* icon = FindAppIcon(id);
        if (!icon || icon->received < APP_ICON_BYTES) {
            lv_obj_add_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_headerIcon, LV_OBJ_FLAG_HIDDEN);
            return;
        }

        lv_obj_add_flag(s_headerIcon, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);

        for (uint16_t i = 0; i < APP_ICON_SIZE * APP_ICON_SIZE; ++i) {
            uint16_t rgb565 = (uint16_t)icon->data[i * 2] | ((uint16_t)icon->data[i * 2 + 1] << 8);
            uint8_t r = (uint8_t)(((rgb565 >> 11) & 0x1F) * 255 / 31);
            uint8_t g = (uint8_t)(((rgb565 >> 5) & 0x3F) * 255 / 63);
            uint8_t b = (uint8_t)((rgb565 & 0x1F) * 255 / 31);
            s_appIconCanvasBuf[i] = lv_color_make(r, g, b);
        }
        s_appIconDsc.header.always_zero = 0;
        s_appIconDsc.header.w = APP_ICON_SIZE;
        s_appIconDsc.header.h = APP_ICON_SIZE;
        s_appIconDsc.header.cf = LV_IMG_CF_TRUE_COLOR;
        s_appIconDsc.data_size = sizeof(s_appIconCanvasBuf);
        s_appIconDsc.data = (const uint8_t*)s_appIconCanvasBuf;
        lv_img_set_src(s_appIconImg, &s_appIconDsc);
        lv_obj_invalidate(s_appIconImg);
    }

    // Splash Keypad Test
    static lv_obj_t* s_keyGrid = nullptr;
    static lv_obj_t* s_keyBoxes[6] = {nullptr};
    static lv_obj_t* s_touchStatusLabel = nullptr;
    static lv_obj_t* s_touchEventLabel = nullptr;
    static lv_obj_t* s_touchRawLabel = nullptr;
    static lv_obj_t* s_healthRows[8] = {nullptr};

    // Clock Standby
    static lv_obj_t* s_clockHM     = nullptr;
    static lv_obj_t* s_clockColon  = nullptr;
    static lv_obj_t* s_clockSec    = nullptr;
    static lv_obj_t* s_clockBrand  = nullptr;
    static lv_obj_t* s_clockPanel  = nullptr;
    static uint8_t   s_lastClockSec = 255;

    // =========================================================
    // Helpers
    // =========================================================
    static const char* GetModeString(DisplayMode mode) {
        switch(mode) {
            case MODE_OUTPUT:      return "OUTPUT";
            case MODE_INPUT:       return "INPUT";
            case MODE_APPLICATION: return "APP";
            case MODE_GAME:        return "GAME MIXER";
            case MODE_HEALTH:      return "HEALTH";
            default:               return "";
        }
    }

    static const char* GetModeIcon(DisplayMode mode) {
        switch(mode) {
            case MODE_OUTPUT:      return LV_SYMBOL_VOLUME_MAX;
            case MODE_INPUT:       return LV_SYMBOL_AUDIO;
            case MODE_APPLICATION: return LV_SYMBOL_LIST;
            case MODE_GAME:        return LV_SYMBOL_SHUFFLE;
            case MODE_HEALTH:      return LV_SYMBOL_SETTINGS;
            default:               return "";
        }
    }

    static lv_color_t GetModeColor(DisplayMode mode) {
        switch(mode) {
            case MODE_OUTPUT:      return lv_color_hex(COL_CYAN);
            case MODE_INPUT:       return lv_color_hex(COL_PURPLE);
            case MODE_APPLICATION: return lv_color_hex(COL_GREEN);
            case MODE_GAME:        return lv_color_hex(COL_ORANGE);
            case MODE_HEALTH:      return lv_color_hex(COL_BLUE);
            default:               return lv_color_hex(0xFFFFFF);
        }
    }

    // Nav bar icon symbols
    static const char* s_navIcons[NAV_MODE_COUNT] = {
        LV_SYMBOL_VOLUME_MAX, // Output
        LV_SYMBOL_AUDIO,      // Input
        LV_SYMBOL_LIST,        // Apps
        LV_SYMBOL_SHUFFLE,     // Game
        LV_SYMBOL_SETTINGS     // Health
    };

    static const DisplayMode s_navModes[NAV_MODE_COUNT] = {
        MODE_OUTPUT, MODE_INPUT, MODE_APPLICATION, MODE_GAME, MODE_HEALTH
    };

    // =========================================================
    // Glass Panel Helper
    // =========================================================
    static lv_obj_t* CreateGlassPanel(lv_obj_t* parent, int16_t w, int16_t h) {
        lv_obj_t* panel = lv_obj_create(parent);
        lv_obj_set_size(panel, w, h);
        lv_obj_set_style_bg_color(panel, lv_color_hex(0x161618), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(panel, LV_OPA_80, LV_PART_MAIN);
        lv_obj_set_style_border_color(panel, lv_color_hex(COL_GLASS_BORDER), LV_PART_MAIN);
        lv_obj_set_style_border_width(panel, 1, LV_PART_MAIN);
        lv_obj_set_style_border_opa(panel, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_radius(panel, 6, LV_PART_MAIN);
        lv_obj_set_style_pad_all(panel, 0, LV_PART_MAIN);
        lv_obj_clear_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
        return panel;
    }

    static const char* CommandName(Command command) {
        switch (command) {
            case Command::TEST: return "TEST";
            case Command::OK: return "OK";
            case Command::SETTINGS: return "SET";
            case Command::SESSION_INFO: return "INFO";
            case Command::CURRENT_SESSION: return "CUR";
            case Command::ALTERNATE_SESSION: return "ALT";
            case Command::PREVIOUS_SESSION: return "PREV";
            case Command::NEXT_SESSION: return "NEXT";
            case Command::VOLUME_CURR_CHANGE: return "VCUR";
            case Command::VOLUME_ALT_CHANGE: return "VALT";
            case Command::MODE_STATES: return "MODE";
            case Command::DEBUG: return "DBG";
            case Command::SLEEP: return "SLEEP";
            case Command::TIME_SYNC: return "TIME";
            case Command::METER_LEVEL: return "VU";
            case Command::APP_ICON_META: return "IMETA";
            case Command::APP_ICON_CHUNK: return "ICHK";
            case Command::ERROR: return "ERR";
            case Command::NONE:
            default: return "---";
        }
    }

    static void SetHealthRow(uint8_t row, const char* label, const char* value, uint32_t color) {
        if (row >= 8 || !s_healthRows[row]) return;
        char text[48];
        snprintf(text, sizeof(text), "%s %s", label, value);
        lv_label_set_text(s_healthRows[row], text);
        lv_obj_set_style_text_color(s_healthRows[row], lv_color_hex(color), LV_PART_MAIN);
    }

    // =========================================================
    // Build / Update Persistent UI Shell
    // =========================================================
    static void BuildShell(DisplayMode mode) {
        lv_color_t accent = GetModeColor(mode);

        if (!s_shellBuilt) {
            // --- Screen background ---
            lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(COL_BG), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, LV_PART_MAIN);

            // === TOP HEADER ===
            s_header = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_header, SW, HEADER_H);
            lv_obj_set_pos(s_header, 0, 0);
            lv_obj_set_style_bg_color(s_header, lv_color_hex(COL_SURFACE), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(s_header, LV_OPA_80, LV_PART_MAIN);
            lv_obj_set_style_border_side(s_header, LV_BORDER_SIDE_BOTTOM, LV_PART_MAIN);
            lv_obj_set_style_border_color(s_header, lv_color_hex(COL_GLASS_BORDER), LV_PART_MAIN);
            lv_obj_set_style_border_width(s_header, 1, LV_PART_MAIN);
            lv_obj_set_style_radius(s_header, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_left(s_header, PAD, LV_PART_MAIN);
            lv_obj_set_style_pad_right(s_header, PAD, LV_PART_MAIN);
            lv_obj_clear_flag(s_header, LV_OBJ_FLAG_SCROLLABLE);

            // Header icon
            s_headerIcon = lv_label_create(s_header);
            lv_obj_set_style_text_font(s_headerIcon, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_align(s_headerIcon, LV_ALIGN_LEFT_MID, 0, 0);

            s_appIconImg = lv_img_create(s_header);
            lv_obj_align(s_appIconImg, LV_ALIGN_LEFT_MID, 0, 0);
            lv_obj_add_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);

            // Header title
            s_headerTitle = lv_label_create(s_header);
            lv_obj_set_style_text_font(s_headerTitle, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_align(s_headerTitle, LV_ALIGN_LEFT_MID, 20, 0);

            // Battery icon on right
            lv_obj_t* battIcon = lv_label_create(s_header);
            lv_obj_set_style_text_font(battIcon, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_set_style_text_color(battIcon, lv_color_hex(COL_PRIMARY), LV_PART_MAIN);
            lv_label_set_text(battIcon, LV_SYMBOL_CHARGE);
            lv_obj_align(battIcon, LV_ALIGN_RIGHT_MID, 0, 0);

            // Live peak meters. Game mode uses two rows; other modes use the
            // current-channel row centered in the header.
            s_meterAlternate = lv_bar_create(s_header);
            lv_obj_set_size(s_meterAlternate, 76, 3);
            lv_bar_set_range(s_meterAlternate, 0, 100);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(s_meterAlternate, LV_OPA_COVER, LV_PART_MAIN);
            lv_obj_set_style_radius(s_meterAlternate, 2, LV_PART_MAIN);
            lv_obj_set_style_radius(s_meterAlternate, 2, LV_PART_INDICATOR);
            lv_obj_align(s_meterAlternate, LV_ALIGN_RIGHT_MID, -24, -4);

            s_meterCurrent = lv_bar_create(s_header);
            lv_obj_set_size(s_meterCurrent, 76, 4);
            lv_bar_set_range(s_meterCurrent, 0, 100);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(s_meterCurrent, LV_OPA_COVER, LV_PART_MAIN);
            lv_obj_set_style_radius(s_meterCurrent, 2, LV_PART_MAIN);
            lv_obj_set_style_radius(s_meterCurrent, 2, LV_PART_INDICATOR);
            lv_obj_align(s_meterCurrent, LV_ALIGN_RIGHT_MID, -24, 0);

            // === CONTENT AREA (container for mode-specific content) ===
            s_contentArea = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_contentArea, SW, CONTENT_H);
            lv_obj_set_pos(s_contentArea, 0, CONTENT_Y);
            lv_obj_set_style_bg_opa(s_contentArea, LV_OPA_TRANSP, LV_PART_MAIN);
            lv_obj_set_style_border_width(s_contentArea, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(s_contentArea, PAD, LV_PART_MAIN);
            lv_obj_set_style_radius(s_contentArea, 0, LV_PART_MAIN);
            lv_obj_clear_flag(s_contentArea, LV_OBJ_FLAG_SCROLLABLE);

            // === RGB GLOW STRIP ===
            s_glowStrip = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_glowStrip, SW, STRIP_H);
            lv_obj_set_pos(s_glowStrip, 0, SH - NAVBAR_H - STRIP_H);
            lv_obj_set_style_border_width(s_glowStrip, 0, LV_PART_MAIN);
            lv_obj_set_style_radius(s_glowStrip, 0, LV_PART_MAIN);
            lv_obj_set_style_shadow_width(s_glowStrip, 8, LV_PART_MAIN);
            lv_obj_set_style_shadow_opa(s_glowStrip, LV_OPA_60, LV_PART_MAIN);
            lv_obj_clear_flag(s_glowStrip, LV_OBJ_FLAG_SCROLLABLE);

            // === BOTTOM NAVIGATION BAR ===
            s_navbar = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_navbar, SW, NAVBAR_H);
            lv_obj_set_pos(s_navbar, 0, SH - NAVBAR_H);
            lv_obj_set_style_bg_color(s_navbar, lv_color_hex(COL_SURFACE_LOW), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(s_navbar, LV_OPA_COVER, LV_PART_MAIN);
            lv_obj_set_style_border_side(s_navbar, LV_BORDER_SIDE_TOP, LV_PART_MAIN);
            lv_obj_set_style_border_color(s_navbar, lv_color_hex(COL_PRIMARY), LV_PART_MAIN);
            lv_obj_set_style_border_opa(s_navbar, LV_OPA_30, LV_PART_MAIN);
            lv_obj_set_style_border_width(s_navbar, 1, LV_PART_MAIN);
            lv_obj_set_style_radius(s_navbar, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(s_navbar, 0, LV_PART_MAIN);
            lv_obj_set_style_layout(s_navbar, LV_LAYOUT_FLEX, LV_PART_MAIN);
            lv_obj_set_flex_flow(s_navbar, LV_FLEX_FLOW_ROW);
            lv_obj_set_flex_align(s_navbar, LV_FLEX_ALIGN_SPACE_AROUND, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
            lv_obj_clear_flag(s_navbar, LV_OBJ_FLAG_SCROLLABLE);

            // Nav buttons
            for (int i = 0; i < NAV_MODE_COUNT; i++) {
                s_navBtns[i] = lv_label_create(s_navbar);
                lv_obj_set_style_text_font(s_navBtns[i], &lv_font_montserrat_20, LV_PART_MAIN);
                lv_label_set_text(s_navBtns[i], s_navIcons[i]);
            }

            s_shellBuilt = true;
        }

        // --- Update shell for current mode ---
        // Header
        lv_obj_set_style_text_color(s_headerIcon, accent, LV_PART_MAIN);
        lv_label_set_text(s_headerIcon, GetModeIcon(mode));
        lv_obj_clear_flag(s_headerIcon, LV_OBJ_FLAG_HIDDEN);
        if (s_appIconImg) lv_obj_add_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_text_color(s_headerTitle, accent, LV_PART_MAIN);
        lv_label_set_text(s_headerTitle, GetModeString(mode));

        if (mode == MODE_GAME) {
            lv_obj_clear_flag(s_meterAlternate, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_meterCurrent, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_size(s_meterCurrent, 76, 3);
            lv_obj_set_size(s_meterAlternate, 76, 3);
            lv_obj_align(s_meterAlternate, LV_ALIGN_RIGHT_MID, -24, -4);
            lv_obj_align(s_meterCurrent, LV_ALIGN_RIGHT_MID, -24, 4);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_ORANGE), LV_PART_INDICATOR);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_PRIMARY), LV_PART_INDICATOR);
        } else if (mode == MODE_HEALTH) {
            lv_obj_add_flag(s_meterAlternate, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s_meterCurrent, LV_OBJ_FLAG_HIDDEN);
        } else {
            // Stereo L / R Dual Meter
            lv_obj_clear_flag(s_meterCurrent, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_meterAlternate, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_size(s_meterCurrent, 76, 3);
            lv_obj_set_size(s_meterAlternate, 76, 3);
            lv_obj_align(s_meterAlternate, LV_ALIGN_RIGHT_MID, -24, -4);
            lv_obj_align(s_meterCurrent, LV_ALIGN_RIGHT_MID, -24, 4);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterAlternate, accent, LV_PART_INDICATOR);
            lv_obj_set_style_bg_color(s_meterCurrent, accent, LV_PART_INDICATOR);
        }
        lv_bar_set_value(s_meterCurrent, s_meterCurrentValue, LV_ANIM_OFF);
        lv_bar_set_value(s_meterAlternate, s_meterAlternateValue, LV_ANIM_OFF);

        // Glow strip
        lv_obj_set_style_bg_color(s_glowStrip, accent, LV_PART_MAIN);
        lv_obj_set_style_bg_opa(s_glowStrip, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_shadow_color(s_glowStrip, accent, LV_PART_MAIN);

        // Nav buttons — highlight active
        for (int i = 0; i < NAV_MODE_COUNT; i++) {
            if (s_navModes[i] == mode) {
                lv_obj_set_style_text_color(s_navBtns[i], accent, LV_PART_MAIN);
                lv_obj_set_style_text_opa(s_navBtns[i], LV_OPA_COVER, LV_PART_MAIN);
                lv_obj_set_style_text_font(s_navBtns[i], &lv_font_montserrat_24, LV_PART_MAIN);
            } else {
                lv_obj_set_style_text_color(s_navBtns[i], lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
                lv_obj_set_style_text_opa(s_navBtns[i], LV_OPA_50, LV_PART_MAIN);
                lv_obj_set_style_text_font(s_navBtns[i], &lv_font_montserrat_20, LV_PART_MAIN);
            }
        }

        s_shellMode = mode;
    }

    static void ShowShell(bool visible) {
        if (s_header)    lv_obj_set_style_opa(s_header,    visible ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
        if (s_navbar)    lv_obj_set_style_opa(s_navbar,    visible ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
        if (s_glowStrip) lv_obj_set_style_opa(s_glowStrip, visible ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
    }

    // =========================================================
    // Clear Content Area (preserves shell)
    // =========================================================
    static void ClearContent(ScreenType type) {
        digitalWrite(PIN_TFT_BL, HIGH);
        if (s_currentScreen != type) {
            if (s_contentArea) {
                lv_obj_clean(s_contentArea);
            }
            s_currentScreen = type;
            s_titleLabel = nullptr;
            s_volArc = nullptr;
            s_volArcB = nullptr;
            s_volLabel = nullptr;
            s_volLabelB = nullptr;
            s_subLabel = nullptr;
            s_subLabelB = nullptr;
            s_splashDots = nullptr;
            s_faderA = nullptr;
            s_faderB = nullptr;
            s_faderNameA = nullptr;
            s_faderNameB = nullptr;
            for (int i = 0; i < 8; ++i) s_healthRows[i] = nullptr;
            s_cpuArc = nullptr;
            s_cpuVal = nullptr;
            s_cpuSub = nullptr;
            s_gpuArc = nullptr;
            s_gpuVal = nullptr;
            s_gpuSub = nullptr;
            s_ramArc = nullptr;
            s_ramVal = nullptr;
            s_ramSub = nullptr;
            s_netDownLbl = nullptr;
            s_netUpLbl = nullptr;
            s_sysLinkLbl = nullptr;
            s_sysHeapLbl = nullptr;
        }
    }

    // Full screen reset (for splash or first boot)
    static void FullReset() {
        if (s_splashDots) {
            lv_anim_del(s_splashDots, nullptr);
        }
        lv_obj_clean(lv_scr_act());
        lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(COL_BG), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, LV_PART_MAIN);
        s_currentScreen = ScreenType::NONE;
        s_shellBuilt = false;
        s_header = nullptr;
        s_headerIcon = nullptr;
        s_headerTitle = nullptr;
        s_meterCurrent = nullptr;
        s_meterAlternate = nullptr;
        s_appIconImg = nullptr;
        s_navbar = nullptr;
        for (int i = 0; i < NAV_MODE_COUNT; i++) s_navBtns[i] = nullptr;
        s_glowStrip = nullptr;
        s_contentArea = nullptr;
        s_titleLabel = nullptr;
        s_volArc = nullptr;
        s_volArcB = nullptr;
        s_volLabel = nullptr;
        s_volLabelB = nullptr;
        s_subLabel = nullptr;
        s_subLabelB = nullptr;
        s_splashDots = nullptr;
        s_keyGrid = nullptr;
        for (int i=0; i<6; i++) s_keyBoxes[i] = nullptr;
        s_touchStatusLabel = nullptr;
        s_touchEventLabel = nullptr;
        s_touchRawLabel = nullptr;
        for (int i = 0; i < 8; ++i) s_healthRows[i] = nullptr;
        s_cpuArc = nullptr;
        s_cpuVal = nullptr;
        s_cpuSub = nullptr;
        s_gpuArc = nullptr;
        s_gpuVal = nullptr;
        s_gpuSub = nullptr;
        s_ramArc = nullptr;
        s_ramVal = nullptr;
        s_ramSub = nullptr;
        s_netDownLbl = nullptr;
        s_netUpLbl = nullptr;
        s_sysLinkLbl = nullptr;
        s_sysHeapLbl = nullptr;
        s_clockHM = nullptr;
        s_clockColon = nullptr;
        s_clockSec = nullptr;
        s_clockBrand = nullptr;
        s_clockPanel = nullptr;
        s_faderA = nullptr;
        s_faderB = nullptr;
        s_faderNameA = nullptr;
        s_faderNameB = nullptr;
    }

    void SetMeterLevels(uint8_t current, uint8_t alternate) {
        s_meterCurrentValue = min((uint8_t)100, current);
        s_meterAlternateValue = min((uint8_t)100, alternate);
        if (s_meterCurrent)
            lv_bar_set_value(s_meterCurrent, s_meterCurrentValue, LV_ANIM_OFF);
        if (s_meterAlternate)
            lv_bar_set_value(s_meterAlternate, s_meterAlternateValue, LV_ANIM_OFF);
    }

    void ReceiveAppIconMeta(const AppIconMeta* meta) {
        if (!meta || meta->id == 0 || meta->width != APP_ICON_SIZE ||
            meta->height != APP_ICON_SIZE || meta->dataLength != APP_ICON_BYTES) {
            return;
        }

        AppIconCacheEntry* icon = FindAppIcon(meta->id);
        if (!icon) {
            icon = &s_appIcons[s_appIconWriteSlot];
            s_appIconWriteSlot = (s_appIconWriteSlot + 1) % APP_ICON_CACHE_SIZE;
        }
        icon->id = meta->id;
        icon->received = 0;
        memset(icon->data, 0, sizeof(icon->data));
    }

    void ReceiveAppIconChunk(const AppIconChunk* chunk) {
        if (!chunk || chunk->id == 0 || chunk->length == 0 || chunk->length > 60)
            return;

        AppIconCacheEntry* icon = FindAppIcon(chunk->id);
        if (!icon) {
            if (chunk->index == 0) {
                icon = &s_appIcons[s_appIconWriteSlot];
                s_appIconWriteSlot = (s_appIconWriteSlot + 1) % APP_ICON_CACHE_SIZE;
                icon->id = chunk->id;
                icon->received = 0;
                memset(icon->data, 0, sizeof(icon->data));
            } else {
                return;
            }
        }

        uint16_t offset = (uint16_t)chunk->index * 60U;
        if (offset >= APP_ICON_BYTES)
            return;

        uint16_t writable = min((uint16_t)chunk->length, (uint16_t)(APP_ICON_BYTES - offset));
        memcpy(icon->data + offset, chunk->data, writable);
        uint16_t end = offset + writable;
        if (end > icon->received)
            icon->received = end;
    }

    // =========================================================
    // SPLASH SCREEN
    // =========================================================
    static void dotAnimCB(void* var, int32_t v) {
        s_dotState = v % 4;
        if (s_splashDots) {
            const char* dots[] = {"", ".", "..", "..."};
            String txt = String("Waiting for connection") + dots[s_dotState];
            lv_label_set_text(s_splashDots, txt.c_str());
        }
    }

    void SplashScreen() {
        // Splash uses full screen (no shell)
        if (s_currentScreen != ScreenType::SPLASH) {
            FullReset();
            s_currentScreen = ScreenType::SPLASH;
        }

        if (!s_titleLabel) {
            // Centered glass panel
            lv_obj_t* panel = lv_obj_create(lv_scr_act());
            lv_obj_set_size(panel, 280, 140);
            lv_obj_align(panel, LV_ALIGN_CENTER, 0, -10);
            lv_obj_set_style_bg_color(panel, lv_color_hex(0x13161F), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, LV_PART_MAIN);
            lv_obj_set_style_border_color(panel, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_set_style_border_width(panel, 2, LV_PART_MAIN);
            lv_obj_set_style_border_opa(panel, LV_OPA_60, LV_PART_MAIN);
            lv_obj_set_style_radius(panel, 20, LV_PART_MAIN);
            lv_obj_set_style_shadow_color(panel, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_set_style_shadow_width(panel, 40, LV_PART_MAIN);
            lv_obj_set_style_shadow_opa(panel, LV_OPA_30, LV_PART_MAIN);
            lv_obj_set_style_shadow_spread(panel, 5, LV_PART_MAIN);
            lv_obj_clear_flag(panel, LV_OBJ_FLAG_SCROLLABLE);

            // "VuNMix" title
            s_titleLabel = lv_label_create(panel);
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_montserrat_36, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_label_set_text(s_titleLabel, "VuNMix");
            lv_obj_align(s_titleLabel, LV_ALIGN_CENTER, 0, -15);

            // Divider line
            lv_obj_t* line = lv_obj_create(panel);
            lv_obj_set_size(line, 120, 2);
            lv_obj_align(line, LV_ALIGN_CENTER, 0, 12);
            lv_obj_set_style_bg_color(line, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(line, LV_OPA_40, LV_PART_MAIN);
            lv_obj_set_style_border_width(line, 0, LV_PART_MAIN);

            // Animated dots text
            s_splashDots = lv_label_create(panel);
            lv_obj_set_style_text_font(s_splashDots, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_splashDots, lv_color_hex(0x8B949E), LV_PART_MAIN);
            lv_label_set_text(s_splashDots, "Waiting for connection");
            lv_obj_align(s_splashDots, LV_ALIGN_CENTER, 0, 35);

            lv_anim_init(&s_dotAnim);
            lv_anim_set_var(&s_dotAnim, s_splashDots);
            lv_anim_set_exec_cb(&s_dotAnim, dotAnimCB);
            lv_anim_set_values(&s_dotAnim, 0, 3);
            lv_anim_set_time(&s_dotAnim, 2000);
            lv_anim_set_repeat_count(&s_dotAnim, LV_ANIM_REPEAT_INFINITE);
            lv_anim_start(&s_dotAnim);
        }
    }

    void KeyTestScreen() {
        if (s_currentScreen != ScreenType::KEY_TEST) {
            FullReset();
            s_currentScreen = ScreenType::KEY_TEST;
            
            // Build the keypad grid
            s_keyGrid = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_keyGrid, SW, SH);
            lv_obj_set_pos(s_keyGrid, 0, 0);
            lv_obj_set_style_bg_color(s_keyGrid, lv_color_hex(COL_BG), LV_PART_MAIN);
            lv_obj_set_style_pad_all(s_keyGrid, 0, LV_PART_MAIN);
            lv_obj_set_style_border_width(s_keyGrid, 0, LV_PART_MAIN);
            lv_obj_clear_flag(s_keyGrid, LV_OBJ_FLAG_SCROLLABLE);
            
            int btnW = 72;
            int btnH = 62;
            int gapX = 15;
            int gapY = 10;
            int startX = (SW - (3*btnW + 2*gapX)) / 2;
            int startY = 44;

            const char* keyNames[6] = {"P", "M", "N", "-", "SPC", "+"};
            for (int i=0; i<6; i++) {
                int row = i / 3;
                int col = i % 3;
                s_keyBoxes[i] = lv_obj_create(s_keyGrid);
                lv_obj_set_size(s_keyBoxes[i], btnW, btnH);
                lv_obj_set_pos(s_keyBoxes[i], startX + col * (btnW + gapX), startY + row * (btnH + gapY));
                
                lv_obj_set_style_bg_color(s_keyBoxes[i], lv_color_hex(0x2A2A2F), LV_PART_MAIN);
                lv_obj_set_style_bg_opa(s_keyBoxes[i], LV_OPA_COVER, LV_PART_MAIN);
                lv_obj_set_style_border_color(s_keyBoxes[i], lv_color_hex(0x404040), LV_PART_MAIN);
                lv_obj_set_style_border_width(s_keyBoxes[i], 2, LV_PART_MAIN);
                lv_obj_set_style_radius(s_keyBoxes[i], 16, LV_PART_MAIN);
                lv_obj_clear_flag(s_keyBoxes[i], LV_OBJ_FLAG_SCROLLABLE);

                lv_obj_t* lbl = lv_label_create(s_keyBoxes[i]);
                lv_label_set_text(lbl, keyNames[i]);
                lv_obj_set_style_text_color(lbl, lv_color_hex(0x8B949E), LV_PART_MAIN);
                lv_obj_set_style_text_font(lbl, &lv_font_montserrat_14, LV_PART_MAIN);
                lv_obj_center(lbl);
            }

            s_titleLabel = lv_label_create(s_keyGrid);
            lv_label_set_text(s_titleLabel, "INPUT TEST");
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_align(s_titleLabel, LV_ALIGN_TOP_MID, 0, 10);

            s_touchStatusLabel = lv_label_create(s_keyGrid);
            lv_obj_set_style_text_font(s_touchStatusLabel, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_align(s_touchStatusLabel, LV_ALIGN_BOTTOM_MID, 0, -28);

            s_touchEventLabel = lv_label_create(s_keyGrid);
            lv_obj_set_style_text_font(s_touchEventLabel, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_touchEventLabel, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_obj_align(s_touchEventLabel, LV_ALIGN_BOTTOM_MID, 0, -13);

            s_touchRawLabel = lv_label_create(s_keyGrid);
            lv_obj_set_style_text_font(s_touchRawLabel, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_touchRawLabel, lv_color_hex(0x8B949E), LV_PART_MAIN);
            lv_obj_align(s_touchRawLabel, LV_ALIGN_BOTTOM_MID, 0, 5);
        }

        // Update key colors based on state
        for (int i=0; i<6; i++) {
            if (s_keyBoxes[i]) {
                if (Input::g_RawKeyStates[i]) {
                    lv_obj_set_style_border_color(s_keyBoxes[i], lv_color_hex(0xFFFFFF), LV_PART_MAIN);
                    lv_obj_set_style_border_width(s_keyBoxes[i], 3, LV_PART_MAIN);
                    lv_obj_t* lbl = lv_obj_get_child(s_keyBoxes[i], 0);
                    if (lbl) lv_obj_set_style_text_color(lbl, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
                } else {
                    lv_obj_set_style_border_color(s_keyBoxes[i], lv_color_hex(0x404040), LV_PART_MAIN);
                    lv_obj_set_style_border_width(s_keyBoxes[i], 2, LV_PART_MAIN);
                    lv_obj_t* lbl = lv_obj_get_child(s_keyBoxes[i], 0);
                    if (lbl) lv_obj_set_style_text_color(lbl, lv_color_hex(0x8B949E), LV_PART_MAIN);
                }
            }
        }

        if (s_touchStatusLabel) {
            bool ready = Input::TouchAvailable();
            lv_obj_set_style_text_color(
                s_touchStatusLabel,
                ready ? lv_color_hex(COL_GREEN) : lv_color_hex(0xFF3333),
                LV_PART_MAIN
            );
            lv_label_set_text(s_touchStatusLabel, ready ? "TOUCH READY" : "TOUCH NOT FOUND");
        }

        if (s_touchEventLabel) {
            const char *eventText = "---";
            switch (Input::LastTouchEvent()) {
                case Input::TouchEvent::Tap:        eventText = "LAST: TAP"; break;
                case Input::TouchEvent::DoubleTap:  eventText = "LAST: DOUBLE TAP"; break;
                case Input::TouchEvent::LongPress:  eventText = "LAST: LONG PRESS"; break;
                case Input::TouchEvent::SwipeLeft:  eventText = "LAST: SWIPE LEFT"; break;
                case Input::TouchEvent::SwipeRight: eventText = "LAST: SWIPE RIGHT"; break;
                case Input::TouchEvent::SwipeUp:    eventText = "LAST: SWIPE UP"; break;
                case Input::TouchEvent::SwipeDown:  eventText = "LAST: SWIPE DOWN"; break;
                default: break;
            }
            lv_label_set_text(s_touchEventLabel, eventText);
        }

        if (s_touchRawLabel) {
            char rawText[64];
            snprintf(
                rawText,
                sizeof(rawText),
                "RAW:%02X F:%u X:%u Y:%u INT:%u",
                Input::LastTouchRawGesture(),
                Input::LastTouchFingers(),
                Input::LastTouchX(),
                Input::LastTouchY(),
                Input::TouchIntActive() ? 1 : 0
            );
            lv_label_set_text(s_touchRawLabel, rawText);
        }
    }

    // =========================================================
    // INFO SCREEN (Version)
    // =========================================================
    void InfoScreen(bool touchAvailable) {
        if (s_currentScreen != ScreenType::INFO) {
            FullReset();
            s_currentScreen = ScreenType::INFO;
        }
        if (!s_titleLabel) {
            s_titleLabel = lv_label_create(lv_scr_act());
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_montserrat_36, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_label_set_text(s_titleLabel, VERSION);
            lv_obj_align(s_titleLabel, LV_ALIGN_CENTER, 0, -16);

            s_subLabel = lv_label_create(lv_scr_act());
            lv_obj_set_style_text_font(s_subLabel, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_align(s_subLabel, LV_ALIGN_CENTER, 0, 22);
        }

        lv_obj_set_style_text_color(
            s_subLabel,
            touchAvailable ? lv_color_hex(COL_GREEN) : lv_color_hex(0xFF3333),
            LV_PART_MAIN
        );
        lv_label_set_text(
            s_subLabel,
            touchAvailable ? "TOUCH READY" : "TOUCH NOT FOUND"
        );
    }

    // =========================================================
    // DEVICE HEALTH / DEBUG SCREEN & PC TELEMETRY GAUGE DASHBOARD
    // =========================================================
    static lv_obj_t* CreateCyberGauge(lv_obj_t* parent, int16_t x, int16_t y, int16_t w, int16_t h,
                                      const char* title, uint32_t colorHex,
                                      lv_obj_t*& outArc, lv_obj_t*& outValLabel, lv_obj_t*& outSubLabel)
    {
        lv_obj_t* card = CreateGlassPanel(parent, w, h);
        lv_obj_set_pos(card, x, y);
        lv_obj_set_style_border_color(card, lv_color_hex(colorHex), LV_PART_MAIN);
        lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
        lv_obj_set_style_border_opa(card, LV_OPA_50, LV_PART_MAIN);

        // Title at top
        lv_obj_t* tLbl = lv_label_create(card);
        lv_obj_set_style_text_font(tLbl, &lv_font_montserrat_12, LV_PART_MAIN);
        lv_obj_set_style_text_color(tLbl, lv_color_hex(colorHex), LV_PART_MAIN);
        lv_label_set_text(tLbl, title);
        lv_obj_align(tLbl, LV_ALIGN_TOP_MID, 0, 4);

        // Radial Arc Gauge
        outArc = lv_arc_create(card);
        lv_obj_set_size(outArc, 60, 60);
        lv_obj_align(outArc, LV_ALIGN_CENTER, 0, 4);
        lv_arc_set_bg_angles(outArc, 135, 45);
        lv_arc_set_range(outArc, 0, 100);

        lv_obj_set_style_arc_color(outArc, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
        lv_obj_set_style_arc_width(outArc, 6, LV_PART_MAIN);
        lv_obj_set_style_arc_rounded(outArc, true, LV_PART_MAIN);

        lv_obj_set_style_arc_color(outArc, lv_color_hex(colorHex), LV_PART_INDICATOR);
        lv_obj_set_style_arc_width(outArc, 6, LV_PART_INDICATOR);
        lv_obj_set_style_arc_rounded(outArc, true, LV_PART_INDICATOR);
        lv_obj_set_style_shadow_color(outArc, lv_color_hex(colorHex), LV_PART_INDICATOR);
        lv_obj_set_style_shadow_width(outArc, 12, LV_PART_INDICATOR);
        lv_obj_set_style_shadow_opa(outArc, LV_OPA_50, LV_PART_INDICATOR);

        lv_obj_set_style_bg_opa(outArc, LV_OPA_TRANSP, LV_PART_KNOB);
        lv_obj_clear_flag(outArc, LV_OBJ_FLAG_CLICKABLE);

        // Value inside Arc
        outValLabel = lv_label_create(outArc);
        lv_obj_set_style_text_font(outValLabel, &lv_font_montserrat_14, LV_PART_MAIN);
        lv_obj_set_style_text_color(outValLabel, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
        lv_label_set_text(outValLabel, "0%");
        lv_obj_align(outValLabel, LV_ALIGN_CENTER, 0, 0);

        // Subtitle below Arc
        outSubLabel = lv_label_create(card);
        lv_obj_set_style_text_font(outSubLabel, &lv_font_montserrat_10, LV_PART_MAIN);
        lv_obj_set_style_text_color(outSubLabel, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
        lv_label_set_text(outSubLabel, "");
        lv_obj_align(outSubLabel, LV_ALIGN_BOTTOM_MID, 0, -4);

        return card;
    }

    void HealthScreen(
        bool pcConnected,
        uint32_t uptimeSeconds,
        uint32_t serialAgeMs,
        uint32_t freeHeap,
        uint32_t minFreeHeap,
        uint32_t maxAllocHeap,
        uint32_t rxFrames,
        uint32_t txFrames,
        uint32_t crcErrors,
        uint32_t protocolErrors,
        Command lastCommand,
        Command lastErrorCommand,
        uint8_t currentMode,
        uint8_t currentIndex,
        uint8_t outputCount,
        uint8_t inputCount,
        uint8_t appCount,
        bool touchReady,
        uint32_t touchSamples
    ) {
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH ||
            s_currentScreen == ScreenType::KEY_TEST || s_currentScreen == ScreenType::INFO ||
            s_currentScreen == ScreenType::CLOCK) {
            FullReset();
            s_shellBuilt = false;
        }
        BuildShell(MODE_HEALTH);
        ClearContent(ScreenType::HEALTH);
        ShowShell(true);

        // Build graphical 3-Gauge HUD + Dual Bottom Cards if not created
        if (!s_cpuArc) {
            // 1. CPU Gauge Card (Left: X=0, W=100)
            CreateCyberGauge(s_contentArea, 0, 6, 100, 98,
                             "CPU", COL_CYAN,
                             s_cpuArc, s_cpuVal, s_cpuSub);

            // 2. GPU Gauge Card (Center: X=103, W=100)
            CreateCyberGauge(s_contentArea, 103, 6, 100, 98,
                             "GPU", COL_ORANGE,
                             s_gpuArc, s_gpuVal, s_gpuSub);

            // 3. RAM Gauge Card (Right: X=207, W=100)
            CreateCyberGauge(s_contentArea, 207, 6, 100, 98,
                             "RAM", COL_PURPLE,
                             s_ramArc, s_ramVal, s_ramSub);

            // 4. Bottom Left: Network Card (X=0, W=152, H=58)
            lv_obj_t* netCard = CreateGlassPanel(s_contentArea, 152, 58);
            lv_obj_set_pos(netCard, 0, 108);
            lv_obj_set_style_border_color(netCard, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_obj_set_style_border_width(netCard, 1, LV_PART_MAIN);
            lv_obj_set_style_border_opa(netCard, LV_OPA_30, LV_PART_MAIN);

            s_netDownLbl = lv_label_create(netCard);
            lv_obj_set_style_text_font(s_netDownLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_netDownLbl, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_obj_align(s_netDownLbl, LV_ALIGN_TOP_LEFT, 8, 6);

            s_netUpLbl = lv_label_create(netCard);
            lv_obj_set_style_text_font(s_netUpLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_netUpLbl, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_align(s_netUpLbl, LV_ALIGN_BOTTOM_LEFT, 8, -6);

            // 5. Bottom Right: System Card (X=155, W=152, H=58)
            lv_obj_t* sysCard = CreateGlassPanel(s_contentArea, 152, 58);
            lv_obj_set_pos(sysCard, 155, 108);
            lv_obj_set_style_border_color(sysCard, lv_color_hex(COL_BLUE), LV_PART_MAIN);
            lv_obj_set_style_border_width(sysCard, 1, LV_PART_MAIN);
            lv_obj_set_style_border_opa(sysCard, LV_OPA_30, LV_PART_MAIN);

            s_sysLinkLbl = lv_label_create(sysCard);
            lv_obj_set_style_text_font(s_sysLinkLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_sysLinkLbl, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_obj_align(s_sysLinkLbl, LV_ALIGN_TOP_LEFT, 8, 6);

            s_sysHeapLbl = lv_label_create(sysCard);
            lv_obj_set_style_text_font(s_sysHeapLbl, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_sysHeapLbl, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_obj_align(s_sysHeapLbl, LV_ALIGN_BOTTOM_LEFT, 8, -6);
        }

        char buf[64];
        if (g_PcStatsValid) {
            // Update CPU gauge
            lv_arc_set_value(s_cpuArc, g_PcStats.cpuUsage);
            snprintf(buf, sizeof(buf), "%u%%", g_PcStats.cpuUsage);
            lv_label_set_text(s_cpuVal, buf);
            lv_label_set_text(s_cpuSub, "LOAD");

            // Update GPU gauge
            lv_arc_set_value(s_gpuArc, g_PcStats.gpuUsage);
            snprintf(buf, sizeof(buf), "%u%%", g_PcStats.gpuUsage);
            lv_label_set_text(s_gpuVal, buf);
            if (g_PcStats.gpuTemp > 0)
                snprintf(buf, sizeof(buf), "%u°C", g_PcStats.gpuTemp);
            else
                snprintf(buf, sizeof(buf), "GPU LOAD");
            lv_label_set_text(s_gpuSub, buf);

            // Update RAM gauge
            lv_arc_set_value(s_ramArc, g_PcStats.ramUsage);
            snprintf(buf, sizeof(buf), "%u%%", g_PcStats.ramUsage);
            lv_label_set_text(s_ramVal, buf);
            snprintf(buf, sizeof(buf), "%u/%uG",
                     (g_PcStats.ramUsedMB + 512) / 1024,
                     (g_PcStats.ramTotalMB + 512) / 1024);
            lv_label_set_text(s_ramSub, buf);

            // Update Network Download
            if (g_PcStats.netDownKBps >= 1024)
                snprintf(buf, sizeof(buf), LV_SYMBOL_DOWN " %.1f MB/s", g_PcStats.netDownKBps / 1024.0);
            else
                snprintf(buf, sizeof(buf), LV_SYMBOL_DOWN " %u KB/s", g_PcStats.netDownKBps);
            lv_label_set_text(s_netDownLbl, buf);

            // Update Network Upload
            if (g_PcStats.netUpKBps >= 1024)
                snprintf(buf, sizeof(buf), LV_SYMBOL_UP " %.1f MB/s", g_PcStats.netUpKBps / 1024.0);
            else
                snprintf(buf, sizeof(buf), LV_SYMBOL_UP " %u KB/s", g_PcStats.netUpKBps);
            lv_label_set_text(s_netUpLbl, buf);

            // Update PC Link status
            snprintf(buf, sizeof(buf), "%s LINK %lums",
                     pcConnected ? LV_SYMBOL_OK : LV_SYMBOL_WARNING,
                     (unsigned long)serialAgeMs);
            lv_obj_set_style_text_color(s_sysLinkLbl, pcConnected ? lv_color_hex(COL_GREEN) : lv_color_hex(0xFF3333), LV_PART_MAIN);
            lv_label_set_text(s_sysLinkLbl, buf);

            // Update ESP Heap & Frame count
            snprintf(buf, sizeof(buf), "Heap:%luK | %lu",
                     (unsigned long)(freeHeap / 1024UL),
                     (unsigned long)rxFrames);
            lv_label_set_text(s_sysHeapLbl, buf);
        } else {
            // Standby when PC stats not yet received
            lv_arc_set_value(s_cpuArc, 0);
            lv_label_set_text(s_cpuVal, "--");
            lv_label_set_text(s_cpuSub, "WAIT");

            lv_arc_set_value(s_gpuArc, 0);
            lv_label_set_text(s_gpuVal, "--");
            lv_label_set_text(s_gpuSub, "WAIT");

            lv_arc_set_value(s_ramArc, 0);
            lv_label_set_text(s_ramVal, "--");
            lv_label_set_text(s_ramSub, "WAIT");

            lv_label_set_text(s_netDownLbl, LV_SYMBOL_DOWN " -- KB/s");
            lv_label_set_text(s_netUpLbl, LV_SYMBOL_UP " -- KB/s");

            snprintf(buf, sizeof(buf), "%s PC WAIT", pcConnected ? LV_SYMBOL_OK : LV_SYMBOL_WARNING);
            lv_obj_set_style_text_color(s_sysLinkLbl, pcConnected ? lv_color_hex(COL_ORANGE) : lv_color_hex(0xFF3333), LV_PART_MAIN);
            lv_label_set_text(s_sysLinkLbl, buf);

            snprintf(buf, sizeof(buf), "Heap:%luK | %lu",
                     (unsigned long)(freeHeap / 1024UL),
                     (unsigned long)rxFrames);
            lv_label_set_text(s_sysHeapLbl, buf);
        }
    }

    // =========================================================
    // CLOCK STANDBY SCREEN (Digital Clock)
    // =========================================================

    void ClockScreen(uint8_t hour, uint8_t minute, uint8_t second) {
        if (s_currentScreen != ScreenType::CLOCK) {
            FullReset();
            s_currentScreen = ScreenType::CLOCK;
            s_clockHM = nullptr;
            s_clockColon = nullptr;
            s_clockSec = nullptr;
            s_clockBrand = nullptr;
            s_clockPanel = nullptr;
            s_lastClockSec = 255;
        }

        if (!s_clockHM) {
            // --- Fullscreen dark background ---
            lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(0x000000), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, LV_PART_MAIN);

            // Container for absolute positioning
            s_clockPanel = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_clockPanel, 320, 100);
            lv_obj_center(s_clockPanel);
            lv_obj_set_style_bg_opa(s_clockPanel, LV_OPA_TRANSP, LV_PART_MAIN);
            lv_obj_set_style_border_width(s_clockPanel, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(s_clockPanel, 0, LV_PART_MAIN);
            lv_obj_clear_flag(s_clockPanel, LV_OBJ_FLAG_SCROLLABLE);

            // --- Hours ---
            s_clockHM = lv_label_create(s_clockPanel);
            lv_obj_set_style_text_font(s_clockHM, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_clockHM, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_align(s_clockHM, LV_ALIGN_CENTER, -85, 0);

            // --- Colon ---
            s_clockColon = lv_label_create(s_clockPanel);
            lv_obj_set_style_text_font(s_clockColon, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_clockColon, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_label_set_text(s_clockColon, ":");
            lv_obj_align(s_clockColon, LV_ALIGN_CENTER, 0, -5);

            // --- Minutes ---
            s_clockSec = lv_label_create(s_clockPanel);
            lv_obj_set_style_text_font(s_clockSec, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_clockSec, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_align(s_clockSec, LV_ALIGN_CENTER, 85, 0);

            // --- Sub-brand / Status label ---
            s_clockBrand = lv_label_create(lv_scr_act());
            lv_obj_set_style_text_font(s_clockBrand, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_clockBrand, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_label_set_text(s_clockBrand, "VuNMix Studio");
            lv_obj_align(s_clockBrand, LV_ALIGN_BOTTOM_MID, 0, -8);
        }

        // --- Update time text ---
        if (second != s_lastClockSec) {
            s_lastClockSec = second;
            
            char bufH[4];
            snprintf(bufH, sizeof(bufH), "%02d", hour);
            lv_label_set_text(s_clockHM, bufH);
            
            char bufM[4];
            snprintf(bufM, sizeof(bufM), "%02d", minute);
            lv_label_set_text(s_clockSec, bufM);
            
            if (second % 2 == 0) {
                lv_obj_clear_flag(s_clockColon, LV_OBJ_FLAG_HIDDEN);
            } else {
                lv_obj_add_flag(s_clockColon, LV_OBJ_FLAG_HIDDEN);
            }
        }
    }

    // =========================================================
    // DEVICE SELECT SCREEN (Output/Input Navigate)
    // =========================================================
    void DeviceSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode) {
        // Ensure shell is built
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO || s_currentScreen == ScreenType::CLOCK) {
            FullReset();
            s_shellBuilt = false;
        }
        BuildShell(mode);
        ShowShell(true);
        ClearContent(ScreenType::DEVICE_SELECT);

        lv_color_t accent = GetModeColor(mode);

        if (!s_titleLabel) {
            // --- Volume Arc (circular gauge) ---
            s_volArc = lv_arc_create(s_contentArea);
            lv_obj_set_size(s_volArc, 100, 100);
            lv_obj_align(s_volArc, LV_ALIGN_TOP_MID, 0, 2);
            lv_arc_set_bg_angles(s_volArc, 135, 45);
            lv_arc_set_range(s_volArc, 0, 100);

            // Background track
            lv_obj_set_style_arc_color(s_volArc, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_arc_width(s_volArc, 6, LV_PART_MAIN);
            lv_obj_set_style_arc_rounded(s_volArc, true, LV_PART_MAIN);

            // Indicator
            lv_obj_set_style_arc_color(s_volArc, accent, LV_PART_INDICATOR);
            lv_obj_set_style_arc_width(s_volArc, 6, LV_PART_INDICATOR);
            lv_obj_set_style_arc_rounded(s_volArc, true, LV_PART_INDICATOR);
            lv_obj_set_style_shadow_color(s_volArc, accent, LV_PART_INDICATOR);
            lv_obj_set_style_shadow_width(s_volArc, 12, LV_PART_INDICATOR);
            lv_obj_set_style_shadow_opa(s_volArc, LV_OPA_50, LV_PART_INDICATOR);

            // Hide knob
            lv_obj_set_style_bg_opa(s_volArc, LV_OPA_TRANSP, LV_PART_KNOB);
            lv_obj_clear_flag(s_volArc, LV_OBJ_FLAG_CLICKABLE);

            // Volume number inside arc
            s_volLabel = lv_label_create(s_volArc);
            lv_obj_set_style_text_font(s_volLabel, &lv_font_montserrat_28, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_volLabel, lv_color_hex(COL_PRIMARY), LV_PART_MAIN);
            lv_obj_align(s_volLabel, LV_ALIGN_CENTER, 0, -4);

            // "PERCENT" sub-label
            s_subLabelB = lv_label_create(s_volArc);
            lv_obj_set_style_text_font(s_subLabelB, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_subLabelB, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_label_set_text(s_subLabelB, "PERCENT");
            lv_obj_align(s_subLabelB, LV_ALIGN_CENTER, 0, 14);

            // --- Section labels ---
            lv_obj_t* secLbl = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(secLbl, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(secLbl, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_label_set_text(secLbl, "ACTIVE DEVICE");
            lv_obj_align(secLbl, LV_ALIGN_TOP_LEFT, PAD, 106);

            lv_obj_t* modeLbl = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(modeLbl, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(modeLbl, accent, LV_PART_MAIN);
            lv_label_set_text(modeLbl, "NAVIGATE");
            lv_obj_align(modeLbl, LV_ALIGN_TOP_RIGHT, -PAD, 106);

            // --- Active Device Card ---
            lv_obj_t* card = CreateGlassPanel(s_contentArea, SW - PAD * 4, 32);
            lv_obj_align(card, LV_ALIGN_TOP_MID, 0, 120);
            // Cyan/accent glow border
            lv_obj_set_style_border_color(card, accent, LV_PART_MAIN);
            lv_obj_set_style_border_width(card, 2, LV_PART_MAIN);
            lv_obj_set_style_shadow_color(card, accent, LV_PART_MAIN);
            lv_obj_set_style_shadow_width(card, 10, LV_PART_MAIN);
            lv_obj_set_style_shadow_opa(card, LV_OPA_40, LV_PART_MAIN);
            lv_obj_set_style_radius(card, 6, LV_PART_MAIN);

            // Device icon circle
            lv_obj_t* iconBg = lv_obj_create(card);
            lv_obj_set_size(iconBg, 22, 22);
            lv_obj_align(iconBg, LV_ALIGN_LEFT_MID, 6, 0);
            lv_obj_set_style_bg_color(iconBg, accent, LV_PART_MAIN);
            lv_obj_set_style_bg_opa(iconBg, LV_OPA_20, LV_PART_MAIN);
            lv_obj_set_style_radius(iconBg, LV_RADIUS_CIRCLE, LV_PART_MAIN);
            lv_obj_set_style_border_width(iconBg, 0, LV_PART_MAIN);
            lv_obj_clear_flag(iconBg, LV_OBJ_FLAG_SCROLLABLE);

            lv_obj_t* cardIconLbl = lv_label_create(iconBg);
            lv_obj_set_style_text_font(cardIconLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(cardIconLbl, accent, LV_PART_MAIN);
            lv_label_set_text(cardIconLbl, GetModeIcon(mode));
            lv_obj_center(cardIconLbl);

            // Device name
            s_titleLabel = lv_label_create(card);
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_vn_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
            lv_obj_set_width(s_titleLabel, SW - 120);
            lv_label_set_long_mode(s_titleLabel, LV_LABEL_LONG_DOT);
            lv_obj_align(s_titleLabel, LV_ALIGN_LEFT_MID, 34, 0);

            // Scroll arrows indicator
            s_subLabel = lv_label_create(card);
            lv_obj_set_style_text_font(s_subLabel, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_subLabel, accent, LV_PART_MAIN);
            lv_obj_align(s_subLabel, LV_ALIGN_RIGHT_MID, -6, 0);
        }

        // Update values
        lv_arc_set_value(s_volArc, session->data.volume);

        if (session->data.isMuted) {
            lv_obj_set_style_text_color(s_volLabel, lv_color_hex(0xFF3333), LV_PART_MAIN);
            lv_label_set_text(s_volLabel, "MUTE");
            lv_obj_set_style_text_font(s_volLabel, &lv_font_montserrat_20, LV_PART_MAIN);
            lv_obj_set_style_arc_color(s_volArc, lv_color_hex(0x444444), LV_PART_INDICATOR);
        } else {
            lv_obj_set_style_text_color(s_volLabel, lv_color_hex(COL_PRIMARY), LV_PART_MAIN);
            lv_obj_set_style_text_font(s_volLabel, &lv_font_montserrat_28, LV_PART_MAIN);
            String volStr = String(session->data.volume);
            lv_label_set_text(s_volLabel, volStr.c_str());
            lv_obj_set_style_arc_color(s_volArc, accent, LV_PART_INDICATOR);
        }

        // Device name
        String name = String(session->name);
        if (name.length() == 0) name = "---";
        lv_label_set_text(s_titleLabel, name.c_str());
        UpdateAppIcon(session->data.id, mode);

        // Scroll arrows
        String arrows = "";
        if (canScrollLeft) arrows += LV_SYMBOL_LEFT " ";
        if (canScrollRight) arrows += LV_SYMBOL_RIGHT;
        lv_label_set_text(s_subLabel, arrows.c_str());
    }

    // =========================================================
    // DEVICE EDIT SCREEN (Output/Input Edit)
    // =========================================================
    void DeviceEditScreen(SessionData* session, const char* typeLabel, DisplayMode mode) {
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO || s_currentScreen == ScreenType::CLOCK) {
            FullReset();
            s_shellBuilt = false;
        }
        BuildShell(mode);
        ShowShell(true);
        ClearContent(ScreenType::DEVICE_EDIT);

        lv_color_t accent = GetModeColor(mode);

        if (!s_volArc) {
            // Large arc gauge
            s_volArc = lv_arc_create(s_contentArea);
            lv_obj_set_size(s_volArc, 130, 130);
            lv_obj_align(s_volArc, LV_ALIGN_TOP_MID, 0, 2);
            lv_arc_set_bg_angles(s_volArc, 135, 45);
            lv_arc_set_range(s_volArc, 0, 100);

            // Background track
            lv_obj_set_style_arc_color(s_volArc, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_arc_width(s_volArc, 10, LV_PART_MAIN);
            lv_obj_set_style_arc_rounded(s_volArc, true, LV_PART_MAIN);

            // Indicator
            lv_obj_set_style_arc_width(s_volArc, 10, LV_PART_INDICATOR);
            lv_obj_set_style_arc_rounded(s_volArc, true, LV_PART_INDICATOR);

            // Glow
            lv_obj_set_style_shadow_width(s_volArc, 20, LV_PART_INDICATOR);
            lv_obj_set_style_shadow_opa(s_volArc, LV_OPA_60, LV_PART_INDICATOR);

            // Hide knob
            lv_obj_set_style_bg_opa(s_volArc, LV_OPA_TRANSP, LV_PART_KNOB);
            lv_obj_clear_flag(s_volArc, LV_OBJ_FLAG_CLICKABLE);

            // Volume label
            s_volLabel = lv_label_create(s_volArc);
            lv_obj_set_style_text_font(s_volLabel, &lv_font_montserrat_36, LV_PART_MAIN);
            lv_obj_align(s_volLabel, LV_ALIGN_CENTER, 0, -4);

            // "PERCENT" sub-label
            s_subLabelB = lv_label_create(s_volArc);
            lv_obj_set_style_text_font(s_subLabelB, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_subLabelB, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_label_set_text(s_subLabelB, "PERCENT");
            lv_obj_align(s_subLabelB, LV_ALIGN_CENTER, 0, 18);

            // Device name below arc
            s_titleLabel = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_vn_14, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(COL_ON_SURFACE), LV_PART_MAIN);
            lv_obj_set_width(s_titleLabel, SW - 40);
            lv_label_set_long_mode(s_titleLabel, LV_LABEL_LONG_DOT);
            lv_obj_set_style_anim_speed(s_titleLabel, 28, LV_PART_MAIN);
            lv_obj_set_style_text_align(s_titleLabel, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
            lv_obj_align(s_titleLabel, LV_ALIGN_BOTTOM_MID, 0, -20);

            // Default badge
            s_subLabel = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(s_subLabel, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_align(s_subLabel, LV_ALIGN_BOTTOM_MID, 0, -6);
        }

        // Update values
        lv_arc_set_value(s_volArc, session->data.volume);

        if (session->data.isMuted) {
            lv_obj_set_style_arc_color(s_volArc, lv_color_hex(0x444444), LV_PART_INDICATOR);
            lv_obj_set_style_shadow_opa(s_volArc, LV_OPA_0, LV_PART_INDICATOR);
            lv_obj_set_style_text_color(s_volLabel, lv_color_hex(0xFF3333), LV_PART_MAIN);
            lv_obj_set_style_text_font(s_volLabel, &lv_font_montserrat_24, LV_PART_MAIN);
            lv_label_set_text(s_volLabel, "MUTE");
        } else {
            lv_obj_set_style_arc_color(s_volArc, accent, LV_PART_INDICATOR);
            lv_obj_set_style_shadow_color(s_volArc, accent, LV_PART_INDICATOR);
            lv_obj_set_style_shadow_opa(s_volArc, LV_OPA_60, LV_PART_INDICATOR);
            lv_obj_set_style_text_color(s_volLabel, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
            lv_obj_set_style_text_font(s_volLabel, &lv_font_montserrat_36, LV_PART_MAIN);
            String volStr = String(session->data.volume);
            lv_label_set_text(s_volLabel, volStr.c_str());
        }

        // Name
        String name = String(session->name);
        if (name.length() == 0) name = "---";

        // Only the selected default Input/Output device gets a marquee. Keep
        // navigation and application screens static so moving between items
        // remains visually stable.
        bool scrollDefaultDevice =
            (mode == MODE_INPUT || mode == MODE_OUTPUT) &&
            session->data.isDefault;
        lv_label_long_mode_t longMode = scrollDefaultDevice
            ? LV_LABEL_LONG_SCROLL_CIRCULAR
            : LV_LABEL_LONG_DOT;

        // METER_LEVEL refreshes this screen at 15 Hz. Avoid resetting the
        // label/animation when neither the mode nor text has changed.
        if (lv_label_get_long_mode(s_titleLabel) != longMode)
            lv_label_set_long_mode(s_titleLabel, longMode);
        if (strcmp(lv_label_get_text(s_titleLabel), name.c_str()) != 0)
            lv_label_set_text(s_titleLabel, name.c_str());

        // Default badge or Media Info
        if (mode == MODE_APPLICATION && g_MediaInfoValid && g_MediaInfo.title[0] != '\0') {
            char mediaTxt[64];
            const char* icon = g_MediaInfo.isPlaying ? LV_SYMBOL_PLAY : LV_SYMBOL_PAUSE;
            if (g_MediaInfo.artist[0] != '\0') {
                snprintf(mediaTxt, sizeof(mediaTxt), "%s %s - %s", icon, g_MediaInfo.artist, g_MediaInfo.title);
            } else {
                snprintf(mediaTxt, sizeof(mediaTxt), "%s %s", icon, g_MediaInfo.title);
            }
            lv_obj_set_style_text_color(s_subLabel, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_label_set_long_mode(s_subLabel, LV_LABEL_LONG_SCROLL_CIRCULAR);
            lv_label_set_text(s_subLabel, mediaTxt);
        } else if (session->data.isDefault) {
            lv_obj_set_style_text_color(s_subLabel, accent, LV_PART_MAIN);
            lv_label_set_long_mode(s_subLabel, LV_LABEL_LONG_DOT);
            lv_label_set_text(s_subLabel, LV_SYMBOL_OK " DEFAULT");
        } else {
            lv_label_set_text(s_subLabel, "");
        }
    }

    // =========================================================
    // APPLICATION SCREENS (reuse device screens)
    // =========================================================
    void ApplicationSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode) {
        DeviceSelectScreen(session, canScrollLeft, canScrollRight, mode);
    }

    void ApplicationEditScreen(SessionData* session, DisplayMode mode) {
        DeviceEditScreen(session, "APP", mode);
    }

    // =========================================================
    // GAME SELECT SCREEN
    // =========================================================
    void GameSelectScreen(SessionData* session, char channel, bool canScrollLeft, bool canScrollRight, DisplayMode mode) {
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO || s_currentScreen == ScreenType::CLOCK) {
            FullReset();
            s_shellBuilt = false;
        }
        BuildShell(mode);
        ShowShell(true);
        ClearContent(ScreenType::GAME_SELECT);

        lv_color_t accent = GetModeColor(mode);

        if (!s_titleLabel) {
            // Channel selection panel
            lv_obj_t* panel = CreateGlassPanel(s_contentArea, SW - PAD * 4, CONTENT_H - 20);
            lv_obj_align(panel, LV_ALIGN_CENTER, 0, 0);
            lv_obj_set_style_border_color(panel, accent, LV_PART_MAIN);
            lv_obj_set_style_border_width(panel, 2, LV_PART_MAIN);
            lv_obj_set_style_shadow_color(panel, accent, LV_PART_MAIN);
            lv_obj_set_style_shadow_width(panel, 15, LV_PART_MAIN);
            lv_obj_set_style_shadow_opa(panel, LV_OPA_30, LV_PART_MAIN);
            lv_obj_set_style_radius(panel, 12, LV_PART_MAIN);

            // Channel label
            s_subLabel = lv_label_create(panel);
            lv_obj_set_style_text_font(s_subLabel, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_subLabel, accent, LV_PART_MAIN);
            lv_obj_align(s_subLabel, LV_ALIGN_TOP_MID, 0, 10);

            // Channel icon
            lv_obj_t* chIcon = lv_label_create(panel);
            lv_obj_set_style_text_font(chIcon, &lv_font_montserrat_36, LV_PART_MAIN);
            lv_obj_set_style_text_color(chIcon, accent, LV_PART_MAIN);
            lv_label_set_text(chIcon, channel == 'A' ? LV_SYMBOL_SHUFFLE : LV_SYMBOL_AUDIO);
            lv_obj_align(chIcon, LV_ALIGN_CENTER, 0, -10);

            // Session name
            s_titleLabel = lv_label_create(panel);
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_vn_20, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
            lv_obj_set_width(s_titleLabel, SW - 60);
            lv_label_set_long_mode(s_titleLabel, LV_LABEL_LONG_DOT);
            lv_obj_set_style_text_align(s_titleLabel, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
            lv_obj_align(s_titleLabel, LV_ALIGN_BOTTOM_MID, 0, -30);

            // Scroll arrows
            s_subLabelB = lv_label_create(panel);
            lv_obj_set_style_text_font(s_subLabelB, &lv_font_montserrat_14, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_subLabelB, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_obj_align(s_subLabelB, LV_ALIGN_BOTTOM_MID, 0, -10);
        }

        // Update
        String chStr = String("SELECT CHANNEL ") + channel;
        lv_label_set_text(s_subLabel, chStr.c_str());

        String name = String(session->name);
        if (name.length() == 0) name = "---";
        lv_label_set_text(s_titleLabel, name.c_str());

        String arrows = "";
        if (canScrollLeft) arrows += LV_SYMBOL_LEFT "  ";
        if (canScrollRight) arrows += LV_SYMBOL_RIGHT;
        lv_label_set_text(s_subLabelB, arrows.c_str());
    }

    // =========================================================
    // GAME EDIT SCREEN (Dual Fader Mixer)
    // =========================================================
    static lv_obj_t* BuildFaderChannel(lv_obj_t* parent, int16_t x, const char* icon,
                                        const char* label, lv_color_t color, bool active) {
        // Channel container
        lv_obj_t* ch = lv_obj_create(parent);
        lv_obj_set_size(ch, 120, CONTENT_H - 10);
        lv_obj_set_pos(ch, x, 0);
        lv_obj_set_style_bg_opa(ch, LV_OPA_TRANSP, LV_PART_MAIN);
        lv_obj_set_style_border_width(ch, 0, LV_PART_MAIN);
        lv_obj_set_style_pad_all(ch, 0, LV_PART_MAIN);
        lv_obj_clear_flag(ch, LV_OBJ_FLAG_SCROLLABLE);
        if (!active) lv_obj_set_style_opa(ch, LV_OPA_60, LV_PART_MAIN);

        // Icon
        lv_obj_t* ic = lv_label_create(ch);
        lv_obj_set_style_text_font(ic, &lv_font_montserrat_24, LV_PART_MAIN);
        lv_obj_set_style_text_color(ic, color, LV_PART_MAIN);
        lv_label_set_text(ic, icon);
        lv_obj_align(ic, LV_ALIGN_TOP_MID, 0, 4);

        // Label
        lv_obj_t* lb = lv_label_create(ch);
        lv_obj_set_style_text_font(lb, &lv_font_montserrat_10, LV_PART_MAIN);
        lv_obj_set_style_text_color(lb, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
        lv_label_set_text(lb, label);
        lv_obj_align(lb, LV_ALIGN_TOP_MID, 0, 30);

        // Fader track (glass panel)
        lv_obj_t* track = CreateGlassPanel(ch, 50, 70);
        lv_obj_align(track, LV_ALIGN_TOP_MID, 0, 44);
        lv_obj_set_style_radius(track, 8, LV_PART_MAIN);
        if (active) {
            lv_obj_set_style_shadow_color(track, color, LV_PART_MAIN);
            lv_obj_set_style_shadow_width(track, 12, LV_PART_MAIN);
            lv_obj_set_style_shadow_opa(track, LV_OPA_30, LV_PART_MAIN);
        }

        // Bar inside track
        lv_obj_t* bar = lv_bar_create(track);
        lv_obj_set_size(bar, 8, 56);
        lv_obj_align(bar, LV_ALIGN_CENTER, 0, 0);
        lv_bar_set_range(bar, 0, 100);
        lv_obj_set_style_bg_color(bar, lv_color_hex(COL_SURFACE_LOW), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_radius(bar, LV_RADIUS_CIRCLE, LV_PART_MAIN);
        lv_obj_set_style_bg_color(bar, color, LV_PART_INDICATOR);
        lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_INDICATOR);
        lv_obj_set_style_radius(bar, LV_RADIUS_CIRCLE, LV_PART_INDICATOR);

        // Volume number below track
        lv_obj_t* val = lv_label_create(ch);
        lv_obj_set_style_text_font(val, &lv_font_montserrat_16, LV_PART_MAIN);
        lv_obj_set_style_text_color(val, color, LV_PART_MAIN);
        lv_label_set_text(val, "0");
        lv_obj_align(val, LV_ALIGN_BOTTOM_MID, 0, -2);

        // Return bar so we can update it
        // But we need to return both bar and value label...
        // Use a trick: store value label as user data of bar
        lv_obj_set_user_data(bar, val);

        return bar;
    }

    void GameEditScreen(SessionData* altSession, SessionData* curSession, DisplayMode mode) {
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO || s_currentScreen == ScreenType::CLOCK) {
            FullReset();
            s_shellBuilt = false;
        }
        BuildShell(mode);
        ShowShell(true);
        ClearContent(ScreenType::GAME_EDIT);

        lv_color_t accent = GetModeColor(mode);
        lv_color_t colorA = lv_color_hex(COL_PRIMARY);
        lv_color_t colorB = lv_color_hex(COL_ON_SURFACE_V);

        bool aActive = altSession->data.volume >= curSession->data.volume;

        if (!s_faderA) {
            // Left channel: Game (altSession)
            s_faderA = BuildFaderChannel(s_contentArea, PAD, LV_SYMBOL_SHUFFLE, "GAME",
                                          colorA, aActive);

            // Center divider / MIX label
            lv_obj_t* mixLbl = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(mixLbl, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(mixLbl, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_label_set_text(mixLbl, "MIX");
            lv_obj_align(mixLbl, LV_ALIGN_CENTER, 0, 0);

            // Center vertical line
            lv_obj_t* divLine = lv_obj_create(s_contentArea);
            lv_obj_set_size(divLine, 1, CONTENT_H - 30);
            lv_obj_align(divLine, LV_ALIGN_TOP_MID, 0, 10);
            lv_obj_set_style_bg_color(divLine, lv_color_hex(COL_OUTLINE_V), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(divLine, LV_OPA_50, LV_PART_MAIN);
            lv_obj_set_style_border_width(divLine, 0, LV_PART_MAIN);

            // Right channel: Voice (curSession)
            s_faderB = BuildFaderChannel(s_contentArea, SW - 120 - PAD - 12, LV_SYMBOL_AUDIO, "VOICE",
                                          colorB, !aActive);

            // Name labels at bottom
            s_faderNameA = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(s_faderNameA, &lv_font_vn_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_faderNameA, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_obj_align(s_faderNameA, LV_ALIGN_BOTTOM_LEFT, PAD + 10, -2);
            lv_obj_set_width(s_faderNameA, 110);
            lv_label_set_long_mode(s_faderNameA, LV_LABEL_LONG_DOT);

            s_faderNameB = lv_label_create(s_contentArea);
            lv_obj_set_style_text_font(s_faderNameB, &lv_font_vn_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_faderNameB, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_obj_align(s_faderNameB, LV_ALIGN_BOTTOM_RIGHT, -PAD - 10, -2);
            lv_obj_set_width(s_faderNameB, 110);
            lv_label_set_long_mode(s_faderNameB, LV_LABEL_LONG_DOT);
            lv_obj_set_style_text_align(s_faderNameB, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
        }

        // Update fader A
        lv_bar_set_value(s_faderA, altSession->data.volume, LV_ANIM_ON);
        lv_obj_t* valA = (lv_obj_t*)lv_obj_get_user_data(s_faderA);
        if (valA) {
            String vA = String(altSession->data.volume);
            lv_label_set_text(valA, vA.c_str());
        }

        // Update fader B
        lv_bar_set_value(s_faderB, curSession->data.volume, LV_ANIM_ON);
        lv_obj_t* valB = (lv_obj_t*)lv_obj_get_user_data(s_faderB);
        if (valB) {
            String vB = String(curSession->data.volume);
            lv_label_set_text(valB, vB.c_str());
        }

        // Names
        String nameA = String(altSession->name);
        if (nameA.length() > 14) nameA = nameA.substring(0, 12) + "..";
        if (nameA.length() == 0) nameA = "---";
        lv_label_set_text(s_faderNameA, nameA.c_str());

        String nameB = String(curSession->name);
        if (nameB.length() > 14) nameB = nameB.substring(0, 12) + "..";
        if (nameB.length() == 0) nameB = "---";
        lv_label_set_text(s_faderNameB, nameB.c_str());
    }

    // =========================================================
    // TIMERS & SLEEP
    // =========================================================
    void UpdateTimers(uint32_t deltaTime) {
        // Handled by lv_task_handler via Update()
    }

    void ResetTimers() {
    }

    void Sleep() {
        digitalWrite(PIN_TFT_BL, LOW);
    }
}
