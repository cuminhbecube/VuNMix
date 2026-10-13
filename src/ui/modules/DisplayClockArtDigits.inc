    static void DrawNixie(lv_draw_ctx_t* ctx, const lv_area_t& base) {
        const uint8_t digits[4] = {uint8_t(s_artHour/10), uint8_t(s_artHour%10),
                                  uint8_t(s_artMinute/10), uint8_t(s_artMinute%10)};
        for (int i=0; i<4; ++i) {
            int x=i*72+3;
            ClockRect(ctx, base, x, 8, 66, 122, 0x503321, 24);
            ClockRect(ctx, base, x+2, 10, 62, 118, 0x1E1712, 22);
            ClockRect(ctx, base, x+8, 22, 3, 80, 0x4C3527, 1);
            ClockText(ctx, base, x+5, 44, 56, "8", &lv_font_montserrat_36, 0x42241A);
            char text[2] = {char('0'+digits[i]), 0};
            ClockText(ctx, base, x+5, 44, 56, text, &lv_font_montserrat_36, 0xFF973B);
            ClockRect(ctx, base, x+2, 127, 62, 12, 0x72604B, 3);
        }
    }
    static void DrawBarcode(lv_draw_ctx_t* ctx, const lv_area_t& base) {
        const uint8_t digits[6] = {uint8_t(s_artHour/10), uint8_t(s_artHour%10),
            uint8_t(s_artMinute/10), uint8_t(s_artMinute%10), uint8_t(s_artSecond/10), uint8_t(s_artSecond%10)};
        // Decorative bit bars, with conventional time shown beneath.
        for (int i=0; i<24; ++i) {
            int bit = (digits[i/4] >> (3-i%4)) & 1;
            ClockRect(ctx, base, 12+i*11, 8, bit ? 7 : 3, 99, 0xDCECF3);
        }
        char time[12]; snprintf(time, sizeof(time), "%02u:%02u:%02u", s_artHour, s_artMinute, s_artSecond);
        ClockText(ctx, base, 0, 119, 288, time, &lv_font_montserrat_20, 0x79CBD6);
    }
    static void DrawMathClock(lv_draw_ctx_t* ctx, const lv_area_t& base) {
        const uint8_t values[2] = {s_artHour, s_artMinute};
        const char* titles[2] = {"HOURS", "MINUTES"};
        for (int i=0; i<2; ++i) {
            ClockText(ctx, base, 0, i*78, 288, titles[i], &lv_font_montserrat_12, 0x7E85A6);
            char formula[24];
            if (values[i]%2 == 0) snprintf(formula, sizeof(formula), "%u x 2", values[i]/2);
            else snprintf(formula, sizeof(formula), "%u - 7", values[i]+7);
            ClockText(ctx, base, 0, 21+i*78, 288, formula, &lv_font_montserrat_36, i ? 0xEFC589 : 0xB3B9FF);
        }
    }
