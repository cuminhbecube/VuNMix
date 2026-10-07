    // Immediate drawing keeps complex clocks to one retained LVGL object.
    // Coordinates are local to a 288x156 viewport; LVGL clips to that object.
    static void ClockRect(lv_draw_ctx_t* ctx, const lv_area_t& base, int x, int y,
                          int w, int h, uint32_t color, int radius = 0) {
        lv_area_t area = {lv_coord_t(base.x1+x), lv_coord_t(base.y1+y),
                          lv_coord_t(base.x1+x+w-1), lv_coord_t(base.y1+y+h-1)};
        lv_draw_rect_dsc_t dsc; lv_draw_rect_dsc_init(&dsc);
        dsc.bg_color = lv_color_hex(color); dsc.bg_opa = LV_OPA_COVER;
        dsc.radius = radius;
        lv_draw_rect(ctx, &dsc, &area);
    }
    static void ClockText(lv_draw_ctx_t* ctx, const lv_area_t& base, int x, int y,
                          int width, const char* text, const lv_font_t* font, uint32_t color) {
        lv_area_t area = {lv_coord_t(base.x1+x), lv_coord_t(base.y1+y),
                          lv_coord_t(base.x1+x+width-1), lv_coord_t(base.y1+y+font->line_height-1)};
        lv_draw_label_dsc_t dsc; lv_draw_label_dsc_init(&dsc);
        dsc.font = font; dsc.color = lv_color_hex(color); dsc.align = LV_TEXT_ALIGN_CENTER;
        lv_draw_label(ctx, &dsc, &area, text, nullptr);
    }
    static void ClockLine(lv_draw_ctx_t* ctx, const lv_area_t& base, int x1, int y1,
                          int x2, int y2, uint32_t color, int width = 2) {
        lv_point_t a = {lv_coord_t(base.x1+x1), lv_coord_t(base.y1+y1)};
        lv_point_t b = {lv_coord_t(base.x1+x2), lv_coord_t(base.y1+y2)};
        lv_draw_line_dsc_t dsc; lv_draw_line_dsc_init(&dsc);
        dsc.color = lv_color_hex(color); dsc.width = width;
        lv_draw_line(ctx, &dsc, &a, &b);
    }
    static const uint8_t kClockDigits[10][7] = {
        {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14}, {14,17,1,2,4,8,31},
        {30,1,1,14,1,1,30}, {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
        {14,16,16,30,17,17,14}, {31,1,2,4,8,8,8}, {14,17,17,14,17,17,14},
        {14,17,17,15,1,1,14}
    };
    static void DrawMatrixTime(lv_draw_ctx_t* ctx, const lv_area_t& base, bool round) {
        const uint8_t digits[4] = {uint8_t(s_artHour/10), uint8_t(s_artHour%10),
                                  uint8_t(s_artMinute/10), uint8_t(s_artMinute%10)};
        for (int digit=0; digit<4; ++digit) {
            int left = 14 + digit*60 + (digit>=2 ? 20 : 0);
            for (int row=0; row<7; ++row) for (int col=0; col<5; ++col) {
                bool lit = kClockDigits[digits[digit]][row] & (1U<<(4-col));
                ClockRect(ctx, base, left+col*10, 32+row*10, 8, 8,
                          lit ? (round ? 0xFFAF47 : 0x81D4FF) : 0x182029, round ? 4 : 0);
            }
        }
        ClockRect(ctx, base, 139, 52, 8, 8, 0xE9B670, round ? 4 : 0);
        ClockRect(ctx, base, 139, 82, 8, 8, 0xE9B670, round ? 4 : 0);
        if (!round) {
            // A static 8-bit skyline; no background images or animation buffers.
            for (int i=0; i<18; ++i) {
                int height = 10 + (i*7)%22;
                ClockRect(ctx, base, i*16, 156-height, 14, height, i%2 ? 0x223B68 : 0x172A4F);
                ClockRect(ctx, base, i*16+5, 156-height+4, 3, 3, 0xF3D68C);
            }
        }
    }
