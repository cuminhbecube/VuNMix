    // Extra styles allocate widgets only when entering/changing the screen.
    // Tick updates reuse those objects; FullReset owns all child destruction.
    static uint32_t ExtraClockBackground(uint8_t style) {
        if (style >= 8) {
            const uint32_t colors[8] = {0x100C08,0x10171D,0x090E29,0x060806,0x111820,0x090F14,0x080F19,0x101018};
            return colors[style-8];
        }
        return style == 4 ? 0x080D19 : style == 5 ? 0x0A1015
             : style == 6 ? 0x030A05 : 0x17211C;
    }

    static lv_obj_t* ClockLabel(lv_obj_t* parent, const char* text,
                               const lv_font_t* font, uint32_t color,
                               lv_align_t align, int16_t x, int16_t y) {
        lv_obj_t* label = lv_label_create(parent);
        lv_label_set_text(label, text);
        lv_obj_set_style_text_font(label, font, LV_PART_MAIN);
        lv_obj_set_style_text_color(label, lv_color_hex(color), LV_PART_MAIN);
        lv_obj_align(label, align, x, y);
        return label;
    }

    static void BuildExtraClock(uint8_t style) {
        if (style == 4) {
            // Orbit: an outer seconds ring around a quiet digital dial.
            s_clockProgress = lv_arc_create(s_clockPanel);
            lv_obj_set_size(s_clockProgress, 188, 188);
            lv_obj_align(s_clockProgress, LV_ALIGN_CENTER, 0, 0);
            lv_obj_set_style_bg_opa(s_clockProgress, LV_OPA_TRANSP, LV_PART_MAIN);
            lv_obj_set_style_border_width(s_clockProgress, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(s_clockProgress, 0, LV_PART_MAIN);
            lv_arc_set_bg_angles(s_clockProgress, 0, 360);
            lv_arc_set_rotation(s_clockProgress, 270);
            lv_arc_set_range(s_clockProgress, 0, 60);
            lv_obj_set_style_arc_width(s_clockProgress, 7, LV_PART_MAIN);
            lv_obj_set_style_arc_color(s_clockProgress, lv_color_hex(0x202B43), LV_PART_MAIN);
            lv_obj_set_style_arc_width(s_clockProgress, 7, LV_PART_INDICATOR);
            lv_obj_set_style_arc_color(s_clockProgress, lv_color_hex(0x78B9FF), LV_PART_INDICATOR);
            lv_obj_remove_style(s_clockProgress, nullptr, LV_PART_KNOB);
            lv_obj_clear_flag(s_clockProgress, LV_OBJ_FLAG_CLICKABLE);
            s_clockHM = ClockLabel(s_clockPanel, "00:00", &lv_font_montserrat_36,
                                  0xEEF5FF, LV_ALIGN_CENTER, 0, -8);
            s_clockSecond = ClockLabel(s_clockPanel, "00", &lv_font_montserrat_16,
                                      0x78B9FF, LV_ALIGN_CENTER, 0, 32);
            ClockLabel(s_clockPanel, "ORBIT", &lv_font_montserrat_10,
                       0x6C819D, LV_ALIGN_TOP_MID, 0, 7);
            ClockLabel(s_clockPanel, "VUNMIX / 24H", &lv_font_montserrat_10,
                       0x6C819D, LV_ALIGN_BOTTOM_MID, 0, -7);
        } else if (style == 5) {
            // Binary values: each column reads top-to-bottom as 32,16,8,4,2,1.
            const char* headings[3] = {"HOUR", "MIN", "SEC"};
            const uint32_t colors[3] = {0x70D6FF, 0xBD9AFF, 0x7DE6B5};
            for (uint8_t col = 0; col < 3; ++col) {
                const int16_t x = 82 + col * 78;
                ClockLabel(s_clockPanel, headings[col], &lv_font_montserrat_12,
                           colors[col], LV_ALIGN_TOP_MID, x - SW / 2, 27);
                for (uint8_t row = 0; row < 6; ++row) {
                    lv_obj_t* dot = s_clockBinary[col][row] = lv_obj_create(s_clockPanel);
                    lv_obj_set_size(dot, 16, 16);
                    lv_obj_set_pos(dot, x - 8, 57 + row * 22);
                    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, LV_PART_MAIN);
                    lv_obj_set_style_border_width(dot, 1, LV_PART_MAIN);
                    lv_obj_set_style_border_color(dot, lv_color_hex(colors[col]), LV_PART_MAIN);
                    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, LV_PART_MAIN);
                    lv_obj_set_style_bg_color(dot, lv_color_hex(0x18232D), LV_PART_MAIN);
                    lv_obj_set_style_pad_all(dot, 0, LV_PART_MAIN);
                    lv_obj_clear_flag(dot, LV_OBJ_FLAG_SCROLLABLE);
                    lv_obj_clear_flag(dot, LV_OBJ_FLAG_CLICKABLE);
                }
            }
            for (uint8_t row = 0; row < 6; ++row) {
                char weight[4];
                snprintf(weight, sizeof(weight), "%u", 1U << (5U - row));
                ClockLabel(s_clockPanel, weight, &lv_font_montserrat_10,
                           0x536673, LV_ALIGN_TOP_LEFT, 20, 60 + row * 22);
            }
            s_clockHM = ClockLabel(s_clockPanel, "00", &lv_font_montserrat_20,
                                  colors[0], LV_ALIGN_TOP_MID, -78, 190);
            s_clockSec = ClockLabel(s_clockPanel, "00", &lv_font_montserrat_20,
                                   colors[1], LV_ALIGN_TOP_MID, 0, 190);
            s_clockSecond = ClockLabel(s_clockPanel, "00", &lv_font_montserrat_20,
                                      colors[2], LV_ALIGN_TOP_MID, 78, 190);
            ClockLabel(s_clockPanel, "BINARY / VUNMIX", &lv_font_montserrat_10,
                       0x536673, LV_ALIGN_BOTTOM_MID, 0, -6);
        } else if (style == 6) {
            // Terminal: green text, restrained command-line framing and cursor.
            ClockLabel(s_clockPanel, "VUNMIX / TERMINAL", &lv_font_montserrat_12,
                       0x4A9964, LV_ALIGN_TOP_LEFT, 18, 20);
            ClockLabel(s_clockPanel, "> clock --24h", &lv_font_montserrat_16,
                       0x88B696, LV_ALIGN_TOP_LEFT, 18, 60);
            s_clockHM = ClockLabel(s_clockPanel, "00:00:00", &lv_font_montserrat_36,
                                  0x83FFA5, LV_ALIGN_LEFT_MID, 18, -2);
            s_clockSecond = ClockLabel(s_clockPanel, "> standby _", &lv_font_montserrat_14,
                                      0x4A9964, LV_ALIGN_TOP_LEFT, 18, 159);
            ClockLabel(s_clockPanel, "LOCAL TIME / 24H", &lv_font_montserrat_10,
                       0x357048, LV_ALIGN_BOTTOM_LEFT, 18, -17);
        } else {
            // Retro LCD: a fixed light-green display inside a dark instrument case.
            ClockLabel(s_clockPanel, "VUNMIX / RETRO LCD", &lv_font_montserrat_12,
                       0xB7C4AC, LV_ALIGN_TOP_MID, 0, 18);
            lv_obj_t* lcd = lv_obj_create(s_clockPanel);
            lv_obj_set_size(lcd, 288, 132);
            lv_obj_center(lcd);
            lv_obj_set_style_bg_color(lcd, lv_color_hex(0xB4C99A), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(lcd, LV_OPA_COVER, LV_PART_MAIN);
            lv_obj_set_style_border_width(lcd, 3, LV_PART_MAIN);
            lv_obj_set_style_border_color(lcd, lv_color_hex(0x64775A), LV_PART_MAIN);
            lv_obj_set_style_radius(lcd, 8, LV_PART_MAIN);
            lv_obj_set_style_pad_all(lcd, 0, LV_PART_MAIN);
            lv_obj_clear_flag(lcd, LV_OBJ_FLAG_SCROLLABLE);
            lv_obj_clear_flag(lcd, LV_OBJ_FLAG_CLICKABLE);
            ClockLabel(lcd, "24H", &lv_font_montserrat_10, 0x536246,
                       LV_ALIGN_TOP_RIGHT, -12, 9);
            s_clockHM = ClockLabel(lcd, "00:00", &lv_font_montserrat_36,
                                  0x263A25, LV_ALIGN_CENTER, 0, -6);
            lv_obj_set_style_text_letter_space(s_clockHM, 4, LV_PART_MAIN);
            s_clockSecond = ClockLabel(lcd, "SEC 00", &lv_font_montserrat_14,
                                      0x536246, LV_ALIGN_BOTTOM_MID, 0, -15);
            ClockLabel(s_clockPanel, "QUARTZ / DIGITAL", &lv_font_montserrat_10,
                       0x879B81, LV_ALIGN_BOTTOM_MID, 0, -18);
        }
    }

    static void UpdateExtraClock(uint8_t style, uint8_t hour, uint8_t minute,
                                 uint8_t second, const char* timeHM) {
        char text[20];
        if (style == 4) {
            lv_label_set_text(s_clockHM, timeHM);
            snprintf(text, sizeof(text), "%02u", second);
            lv_label_set_text(s_clockSecond, text);
            lv_arc_set_value(s_clockProgress, second);
        } else if (style == 5) {
            const uint8_t values[3] = {hour, minute, second};
            const uint32_t colors[3] = {0x70D6FF, 0xBD9AFF, 0x7DE6B5};
            lv_obj_t* labels[3] = {s_clockHM, s_clockSec, s_clockSecond};
            for (uint8_t col = 0; col < 3; ++col) {
                snprintf(text, sizeof(text), "%02u", values[col]);
                lv_label_set_text(labels[col], text);
                for (uint8_t row = 0; row < 6; ++row)
                    lv_obj_set_style_bg_color(s_clockBinary[col][row],
                        lv_color_hex(values[col] & (1U << (5U - row)) ? colors[col] : 0x18232D), LV_PART_MAIN);
            }
        } else if (style == 6) {
            snprintf(text, sizeof(text), "%02u:%02u:%02u", hour, minute, second);
            lv_label_set_text(s_clockHM, text);
            lv_label_set_text(s_clockSecond, (second & 1U) ? "> standby  " : "> standby _");
        } else {
            lv_label_set_text(s_clockHM, timeHM);
            snprintf(text, sizeof(text), "SEC %02u", second);
            lv_label_set_text(s_clockSecond, text);
        }
    }


