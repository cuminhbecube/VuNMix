
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