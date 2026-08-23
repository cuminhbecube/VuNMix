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