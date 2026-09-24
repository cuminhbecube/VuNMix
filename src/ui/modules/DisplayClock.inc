
    // =========================================================
    // CLOCK STANDBY SCREEN
    // Styles: Neon Digital / Minimal / Flip Cards / Analog
    // =========================================================

    void ClockScreen(uint8_t hour, uint8_t minute, uint8_t second) {
        uint8_t clockStyle = g_Settings.clockStyle <= 3 ? g_Settings.clockStyle : 0;

        // Rebuild the clock when entering standby or when Desktop changes the
        // selected style while the clock is already visible.
        if (s_currentScreen != ScreenType::CLOCK || s_clockStyleBuilt != clockStyle) {
            FullReset();
            s_currentScreen = ScreenType::CLOCK;
            s_clockStyleBuilt = clockStyle;
            s_lastClockSec = 255;
        }

        if (!s_clockPanel) {
            uint32_t bgColor = clockStyle == 0 ? 0x000000
                              : clockStyle == 2 ? 0x0B0B0D
                              : clockStyle == 3 ? 0x090B10
                                                : COL_BG;
            lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(bgColor), LV_PART_MAIN);
            lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, LV_PART_MAIN);

            s_clockPanel = lv_obj_create(lv_scr_act());
            lv_obj_set_size(s_clockPanel, SW, SH);
            lv_obj_set_pos(s_clockPanel, 0, 0);
            lv_obj_set_style_bg_opa(s_clockPanel, LV_OPA_TRANSP, LV_PART_MAIN);
            lv_obj_set_style_border_width(s_clockPanel, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(s_clockPanel, 0, LV_PART_MAIN);
            lv_obj_set_style_radius(s_clockPanel, 0, LV_PART_MAIN);
            lv_obj_clear_flag(s_clockPanel, LV_OBJ_FLAG_SCROLLABLE);

            if (clockStyle == 0) {
                // Original VuNMix neon DSEG clock.
                s_clockHM = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockHM, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockHM, lv_color_hex(COL_CYAN), LV_PART_MAIN);
                lv_obj_align(s_clockHM, LV_ALIGN_CENTER, -85, -2);

                s_clockColon = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockColon, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockColon, lv_color_hex(COL_CYAN), LV_PART_MAIN);
                lv_label_set_text(s_clockColon, ":");
                lv_obj_align(s_clockColon, LV_ALIGN_CENTER, 0, -7);

                s_clockSec = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockSec, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockSec, lv_color_hex(COL_CYAN), LV_PART_MAIN);
                lv_obj_align(s_clockSec, LV_ALIGN_CENTER, 85, -2);

                s_clockBrand = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockBrand, &lv_font_montserrat_12, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockBrand, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
                lv_label_set_text(s_clockBrand, "VuNMix Studio");
                lv_obj_align(s_clockBrand, LV_ALIGN_BOTTOM_MID, 0, -8);
            } else if (clockStyle == 1) {
                // Minimal desk-clock layout: one quiet time line + seconds.
                s_clockHM = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockHM, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockHM, lv_color_hex(0xF5F7FA), LV_PART_MAIN);
                lv_obj_set_style_text_letter_space(s_clockHM, 2, LV_PART_MAIN);
                lv_obj_align(s_clockHM, LV_ALIGN_CENTER, 0, -16);

                s_clockSecond = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockSecond, &lv_font_montserrat_16, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockSecond, lv_color_hex(0x8C939D), LV_PART_MAIN);
                lv_obj_align(s_clockSecond, LV_ALIGN_CENTER, 0, 58);

                s_clockBrand = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockBrand, &lv_font_montserrat_10, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockBrand, lv_color_hex(COL_CYAN), LV_PART_MAIN);
                lv_obj_set_style_text_letter_space(s_clockBrand, 2, LV_PART_MAIN);
                lv_label_set_text(s_clockBrand, "VUNMIX  /  CLOCK");
                lv_obj_align(s_clockBrand, LV_ALIGN_TOP_MID, 0, 16);
            } else if (clockStyle == 2) {
                // Split-flap inspired layout, adapted to a small 320x240 TFT.
                lv_obj_t* hourCard = lv_obj_create(s_clockPanel);
                lv_obj_set_size(hourCard, 118, 126);
                lv_obj_align(hourCard, LV_ALIGN_CENTER, -66, -4);
                lv_obj_set_style_bg_color(hourCard, lv_color_hex(0x1B1B1E), LV_PART_MAIN);
                lv_obj_set_style_bg_opa(hourCard, LV_OPA_COVER, LV_PART_MAIN);
                lv_obj_set_style_border_width(hourCard, 1, LV_PART_MAIN);
                lv_obj_set_style_border_color(hourCard, lv_color_hex(0x303035), LV_PART_MAIN);
                lv_obj_set_style_radius(hourCard, 12, LV_PART_MAIN);
                lv_obj_set_style_pad_all(hourCard, 0, LV_PART_MAIN);
                lv_obj_clear_flag(hourCard, LV_OBJ_FLAG_SCROLLABLE);

                lv_obj_t* minuteCard = lv_obj_create(s_clockPanel);
                lv_obj_set_size(minuteCard, 118, 126);
                lv_obj_align(minuteCard, LV_ALIGN_CENTER, 66, -4);
                lv_obj_set_style_bg_color(minuteCard, lv_color_hex(0x1B1B1E), LV_PART_MAIN);
                lv_obj_set_style_bg_opa(minuteCard, LV_OPA_COVER, LV_PART_MAIN);
                lv_obj_set_style_border_width(minuteCard, 1, LV_PART_MAIN);
                lv_obj_set_style_border_color(minuteCard, lv_color_hex(0x303035), LV_PART_MAIN);
                lv_obj_set_style_radius(minuteCard, 12, LV_PART_MAIN);
                lv_obj_set_style_pad_all(minuteCard, 0, LV_PART_MAIN);
                lv_obj_clear_flag(minuteCard, LV_OBJ_FLAG_SCROLLABLE);

                s_clockHM = lv_label_create(hourCard);
                lv_obj_set_style_text_font(s_clockHM, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockHM, lv_color_hex(0xF4F4F4), LV_PART_MAIN);
                lv_obj_center(s_clockHM);

                s_clockSec = lv_label_create(minuteCard);
                lv_obj_set_style_text_font(s_clockSec, &lv_font_dseg_90_bpp1, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockSec, lv_color_hex(0xF4F4F4), LV_PART_MAIN);
                lv_obj_center(s_clockSec);

                lv_obj_t* flipCards[2] = {hourCard, minuteCard};
                for (uint8_t i = 0; i < 2; ++i) {
                    lv_obj_t* split = lv_obj_create(flipCards[i]);
                    lv_obj_set_size(split, 112, 2);
                    lv_obj_center(split);
                    lv_obj_set_style_bg_color(split, lv_color_hex(0x08080A), LV_PART_MAIN);
                    lv_obj_set_style_bg_opa(split, LV_OPA_COVER, LV_PART_MAIN);
                    lv_obj_set_style_border_width(split, 0, LV_PART_MAIN);
                    lv_obj_set_style_radius(split, 0, LV_PART_MAIN);
                    lv_obj_set_style_pad_all(split, 0, LV_PART_MAIN);
                }

                s_clockColon = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockColon, &lv_font_montserrat_36, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockColon, lv_color_hex(0x73737A), LV_PART_MAIN);
                lv_label_set_text(s_clockColon, ":");
                lv_obj_align(s_clockColon, LV_ALIGN_CENTER, 0, -5);

                s_clockSecond = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockSecond, &lv_font_montserrat_12, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockSecond, lv_color_hex(0x8B8B92), LV_PART_MAIN);
                lv_obj_align(s_clockSecond, LV_ALIGN_BOTTOM_MID, 0, -12);

                s_clockBrand = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockBrand, &lv_font_montserrat_10, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockBrand, lv_color_hex(0x696970), LV_PART_MAIN);
                lv_obj_set_style_text_letter_space(s_clockBrand, 2, LV_PART_MAIN);
                lv_label_set_text(s_clockBrand, "FLIP CLOCK");
                lv_obj_align(s_clockBrand, LV_ALIGN_TOP_MID, 0, 12);
            } else {
                // Analog face uses LVGL meter ticks/needles, so no bitmap assets
                // or extra font memory is required.
                s_clockMeter = lv_meter_create(s_clockPanel);
                lv_obj_set_size(s_clockMeter, 184, 184);
                lv_obj_align(s_clockMeter, LV_ALIGN_CENTER, 0, -4);
                lv_obj_set_style_bg_color(s_clockMeter, lv_color_hex(0x11141A), LV_PART_MAIN);
                lv_obj_set_style_bg_opa(s_clockMeter, LV_OPA_COVER, LV_PART_MAIN);
                lv_obj_set_style_border_color(s_clockMeter, lv_color_hex(0x2D333B), LV_PART_MAIN);
                lv_obj_set_style_border_width(s_clockMeter, 1, LV_PART_MAIN);
                lv_obj_set_style_radius(s_clockMeter, LV_RADIUS_CIRCLE, LV_PART_MAIN);
                lv_obj_set_style_pad_all(s_clockMeter, 16, LV_PART_MAIN);

                lv_meter_scale_t* scale = lv_meter_add_scale(s_clockMeter);
                lv_meter_set_scale_ticks(
                    s_clockMeter, scale, 60, 2, 7, lv_color_hex(0x59616C)
                );
                lv_meter_set_scale_major_ticks(
                    s_clockMeter, scale, 5, 3, 11, lv_color_hex(0xD8DEE9), 8
                );
                lv_meter_set_scale_range(s_clockMeter, scale, 0, 60, 360, 270);

                s_clockHourHand = lv_meter_add_needle_line(
                    s_clockMeter, scale, 6, lv_color_hex(0xF5F7FA), -42
                );
                s_clockMinuteHand = lv_meter_add_needle_line(
                    s_clockMeter, scale, 4, lv_color_hex(COL_CYAN), -28
                );
                s_clockSecondHand = lv_meter_add_needle_line(
                    s_clockMeter, scale, 2, lv_color_hex(0xFF5B67), -20
                );

                s_clockBrand = lv_label_create(s_clockPanel);
                lv_obj_set_style_text_font(s_clockBrand, &lv_font_montserrat_10, LV_PART_MAIN);
                lv_obj_set_style_text_color(s_clockBrand, lv_color_hex(0x7D8590), LV_PART_MAIN);
                lv_obj_set_style_text_letter_space(s_clockBrand, 2, LV_PART_MAIN);
                lv_label_set_text(s_clockBrand, "VUNMIX  ANALOG");
                lv_obj_align(s_clockBrand, LV_ALIGN_BOTTOM_MID, 0, -7);
            }
        }

        if (second != s_lastClockSec) {
            s_lastClockSec = second;

            char bufH[4];
            char bufM[4];
            char bufHM[8];
            char bufSecond[16];
            snprintf(bufH, sizeof(bufH), "%02u", hour);
            snprintf(bufM, sizeof(bufM), "%02u", minute);
            snprintf(bufHM, sizeof(bufHM), "%02u:%02u", hour, minute);

            if (clockStyle == 0) {
                lv_label_set_text(s_clockHM, bufH);
                lv_label_set_text(s_clockSec, bufM);
                if ((second & 1U) == 0) {
                    lv_obj_clear_flag(s_clockColon, LV_OBJ_FLAG_HIDDEN);
                } else {
                    lv_obj_add_flag(s_clockColon, LV_OBJ_FLAG_HIDDEN);
                }
            } else if (clockStyle == 1) {
                lv_label_set_text(s_clockHM, bufHM);
                snprintf(bufSecond, sizeof(bufSecond), "SECONDS  %02u", second);
                lv_label_set_text(s_clockSecond, bufSecond);
            } else if (clockStyle == 2) {
                lv_label_set_text(s_clockHM, bufH);
                lv_label_set_text(s_clockSec, bufM);
                snprintf(bufSecond, sizeof(bufSecond), "SECONDS  %02u", second);
                lv_label_set_text(s_clockSecond, bufSecond);
            } else if (s_clockMeter && s_clockHourHand && s_clockMinuteHand && s_clockSecondHand) {
                uint8_t hourValue = (uint8_t)(((hour % 12U) * 5U) + (minute / 12U));
                lv_meter_set_indicator_value(s_clockMeter, s_clockHourHand, hourValue);
                lv_meter_set_indicator_value(s_clockMeter, s_clockMinuteHand, minute);
                lv_meter_set_indicator_value(s_clockMeter, s_clockSecondHand, second);
            }
        }
    }
