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