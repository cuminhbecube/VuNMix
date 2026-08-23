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