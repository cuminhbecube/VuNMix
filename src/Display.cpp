#include "Display.h"
#include "Input.h"
#include <TFT_eSPI.h>
#include <lvgl.h>

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
        Serial.println("  -> Backlight ON (GPIO 8)...");
        Serial.flush();
        pinMode(PIN_TFT_BL, OUTPUT);
        digitalWrite(PIN_TFT_BL, HIGH);
        delay(100);

        Serial.println("  -> tft.init()...");
        Serial.flush();
        tft.init();
        Serial.println("  -> tft.init() DONE.");
        Serial.flush();
        delay(100);

        Serial.println("  -> tft.setRotation(1)...");
        Serial.flush();
        tft.setRotation(1);

        Serial.println("  -> tft.fillScreen(BLACK)...");
        Serial.flush();
        tft.fillScreen(TFT_BLACK);

        Serial.println("  -> lv_init()...");
        Serial.flush();
        lv_init();

        lv_disp_draw_buf_init(&s_dispBuf, s_buf1, s_buf2, (uint32_t)SW * BUF_LINES);

        lv_disp_drv_init(&s_dispDrv);
        s_dispDrv.hor_res  = SW;
        s_dispDrv.ver_res  = SH;
        s_dispDrv.flush_cb = flushCB;
        s_dispDrv.draw_buf = &s_dispBuf;
        lv_disp_drv_register(&s_dispDrv);

        Serial.println("  -> Display Init COMPLETE.");
        Serial.flush();
    }

    void Update() {
        lv_task_handler();
    }

    // =========================================================
    // Screen Tracking
    // =========================================================
    enum class ScreenType {
        NONE, SPLASH, KEY_TEST, INFO, DEVICE_SELECT, DEVICE_EDIT, GAME_SELECT, GAME_EDIT
    };

    static ScreenType s_currentScreen = ScreenType::NONE;

    // --- Persistent UI Shell objects ---
    static lv_obj_t* s_header     = nullptr;
    static lv_obj_t* s_headerIcon = nullptr;
    static lv_obj_t* s_headerTitle= nullptr;
    static lv_obj_t* s_navbar     = nullptr;
    static lv_obj_t* s_navBtns[4] = {nullptr};
    static lv_obj_t* s_glowStrip  = nullptr;
    static lv_obj_t* s_contentArea= nullptr;

    // --- Content widgets (reused per screen) ---
    static lv_obj_t* s_titleLabel  = nullptr;
    static lv_obj_t* s_volArc      = nullptr;
    static lv_obj_t* s_volLabel    = nullptr;
    static lv_obj_t* s_volArcB     = nullptr;
    static lv_obj_t* s_volLabelB   = nullptr;
    static lv_obj_t* s_subLabel    = nullptr;
    static lv_obj_t* s_subLabelB   = nullptr;

    // Splash specific
    static lv_obj_t* s_splashDots  = nullptr;
    static lv_anim_t s_dotAnim;
    static uint8_t   s_dotState = 0;

    // Track which mode the shell was built for
    static DisplayMode s_shellMode = MODE_SPLASH;
    static bool s_shellBuilt = false;

    // Splash Keypad Test
    static lv_obj_t* s_keyGrid = nullptr;
    static lv_obj_t* s_keyBoxes[6] = {nullptr};

    // =========================================================
    // Helpers
    // =========================================================
    static const char* GetModeString(DisplayMode mode) {
        switch(mode) {
            case MODE_OUTPUT:      return "OUTPUT";
            case MODE_INPUT:       return "INPUT";
            case MODE_APPLICATION: return "APP";
            case MODE_GAME:        return "GAME MIXER";
            default:               return "";
        }
    }

    static const char* GetModeIcon(DisplayMode mode) {
        switch(mode) {
            case MODE_OUTPUT:      return LV_SYMBOL_VOLUME_MAX;
            case MODE_INPUT:       return LV_SYMBOL_AUDIO;
            case MODE_APPLICATION: return LV_SYMBOL_LIST;
            case MODE_GAME:        return LV_SYMBOL_SHUFFLE;
            default:               return "";
        }
    }

    static lv_color_t GetModeColor(DisplayMode mode) {
        switch(mode) {
            case MODE_OUTPUT:      return lv_color_hex(COL_CYAN);
            case MODE_INPUT:       return lv_color_hex(COL_PURPLE);
            case MODE_APPLICATION: return lv_color_hex(COL_GREEN);
            case MODE_GAME:        return lv_color_hex(COL_ORANGE);
            default:               return lv_color_hex(0xFFFFFF);
        }
    }

    // Nav bar icon symbols (simple text for 4 modes)
    static const char* s_navIcons[4] = {
        LV_SYMBOL_VOLUME_MAX, // Output
        LV_SYMBOL_AUDIO,      // Input
        LV_SYMBOL_LIST,        // Apps
        LV_SYMBOL_SHUFFLE      // Game
    };

    static const DisplayMode s_navModes[4] = {
        MODE_OUTPUT, MODE_INPUT, MODE_APPLICATION, MODE_GAME
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
            for (int i = 0; i < 4; i++) {
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
        lv_obj_set_style_text_color(s_headerTitle, accent, LV_PART_MAIN);
        lv_label_set_text(s_headerTitle, GetModeString(mode));

        // Glow strip
        lv_obj_set_style_bg_color(s_glowStrip, accent, LV_PART_MAIN);
        lv_obj_set_style_bg_opa(s_glowStrip, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_shadow_color(s_glowStrip, accent, LV_PART_MAIN);

        // Nav buttons — highlight active
        for (int i = 0; i < 4; i++) {
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
        }
    }

    // Full screen reset (for splash or first boot)
    static void FullReset() {
        lv_obj_clean(lv_scr_act());
        lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(COL_BG), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, LV_PART_MAIN);
        s_currentScreen = ScreenType::NONE;
        s_shellBuilt = false;
        s_header = nullptr;
        s_headerIcon = nullptr;
        s_headerTitle = nullptr;
        s_navbar = nullptr;
        for (int i = 0; i < 4; i++) s_navBtns[i] = nullptr;
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
            
            int btnW = 80;
            int btnH = 80;
            int gapX = 15;
            int gapY = 15;
            int startX = (SW - (3*btnW + 2*gapX)) / 2;
            int startY = (SH - (2*btnH + gapY)) / 2;

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
    }

    // =========================================================
    // INFO SCREEN (Version)
    // =========================================================
    void InfoScreen() {
        if (s_currentScreen != ScreenType::INFO) {
            FullReset();
            s_currentScreen = ScreenType::INFO;
        }
        if (!s_titleLabel) {
            s_titleLabel = lv_label_create(lv_scr_act());
            lv_obj_set_style_text_font(s_titleLabel, &lv_font_montserrat_36, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_titleLabel, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_label_set_text(s_titleLabel, VERSION);
            lv_obj_center(s_titleLabel);
        }
    }

    // =========================================================
    // DEVICE SELECT SCREEN (Output/Input Navigate)
    // =========================================================
    void DeviceSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode) {
        // Ensure shell is built
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO) {
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

            lv_obj_t* devIcon = lv_label_create(iconBg);
            lv_obj_set_style_text_font(devIcon, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(devIcon, accent, LV_PART_MAIN);
            lv_label_set_text(devIcon, GetModeIcon(mode));
            lv_obj_center(devIcon);

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
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO) {
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
        if (name.length() > 26) name = name.substring(0, 24) + "..";
        if (name.length() == 0) name = "---";
        lv_label_set_text(s_titleLabel, name.c_str());

        // Default badge
        if (session->data.isDefault) {
            lv_obj_set_style_text_color(s_subLabel, accent, LV_PART_MAIN);
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
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO) {
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
    static lv_obj_t* s_faderA     = nullptr;
    static lv_obj_t* s_faderB     = nullptr;
    static lv_obj_t* s_faderLblA  = nullptr;
    static lv_obj_t* s_faderLblB  = nullptr;
    static lv_obj_t* s_faderNameA = nullptr;
    static lv_obj_t* s_faderNameB = nullptr;

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
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH || s_currentScreen == ScreenType::INFO) {
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
