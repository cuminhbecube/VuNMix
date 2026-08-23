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