    static void DrawArtClock(lv_event_t* event) {
        if (lv_event_get_code(event) != LV_EVENT_DRAW_MAIN) return;
        lv_obj_t* obj = lv_event_get_target(event);
        lv_draw_ctx_t* ctx = lv_event_get_draw_ctx(event);
        lv_area_t base; lv_obj_get_coords(obj, &base);
        switch (s_clockStyleBuilt) {
            case 8: DrawNixie(ctx, base); break;
            case 9: DrawWordClock(ctx, base); break;
            case 10: DrawMatrixTime(ctx, base, false); break;
            case 11: DrawMatrixTime(ctx, base, true); break;
            case 12: DrawClockClock(ctx, base); break;
            case 13: DrawBarcode(ctx, base); break;
            case 14: DrawPolygon(ctx, base); break;
            case 15: DrawMathClock(ctx, base); break;
        }
    }
    static void BuildArtClock(uint8_t style) {
        const char* titles[8] = {"NIXIE", "WORD CLOCK", "PIXEL ART", "DOT MATRIX",
                                 "CLOCKCLOCK", "BARCODE", "POLYGON", "MATH CLOCK"};
        ClockLabel(s_clockPanel, titles[style-8], &lv_font_montserrat_12,
                   0x9AB2CA, LV_ALIGN_TOP_MID, 0, 12);
        s_clockArt = lv_obj_create(s_clockPanel);
        lv_obj_set_size(s_clockArt, 288, 156);
        lv_obj_set_pos(s_clockArt, 16, 42);
        lv_obj_set_style_bg_opa(s_clockArt, LV_OPA_TRANSP, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_clockArt, 0, LV_PART_MAIN);
        lv_obj_set_style_pad_all(s_clockArt, 0, LV_PART_MAIN);
        lv_obj_set_style_radius(s_clockArt, 0, LV_PART_MAIN);
        lv_obj_clear_flag(s_clockArt, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_clear_flag(s_clockArt, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_event_cb(s_clockArt, DrawArtClock, LV_EVENT_DRAW_MAIN, nullptr);
        s_clockSecond = ClockLabel(s_clockPanel, "00:00:00 / 24H", &lv_font_montserrat_14,
                                   0xA0B7C7, LV_ALIGN_BOTTOM_MID, 0, -12);
    }
    static void UpdateArtClock(uint8_t hour, uint8_t minute, uint8_t second) {
        s_artHour = hour; s_artMinute = minute; s_artSecond = second;
        char text[20]; snprintf(text, sizeof(text), "%02u:%02u:%02u / 24H", hour, minute, second);
        lv_label_set_text(s_clockSecond, text);
        lv_obj_invalidate(s_clockArt);
    }
