    // Six miniature dials per digit, each represented by two orthogonal hands.
    // Directions: 0=up, 1=right, 2=down, 3=left; 4=inactive diagonal.
    static const uint8_t kClockHandDigits[10][6] = {
        {7,17,2,2,1,3}, {24,2,24,2,24,2}, {6,17,11,3,1,18},
        {6,17,6,17,6,3}, {2,2,1,17,24,2}, {7,18,1,17,6,3},
        {7,18,7,17,1,3}, {6,17,24,2,24,2}, {7,17,1,3,1,3},
        {7,17,1,17,6,3}
    };
    static void ClockHand(lv_draw_ctx_t* ctx, const lv_area_t& base, int x, int y, int direction) {
        const int dx[5] = {0, 10, 0, -10, -7};
        const int dy[5] = {-10, 0, 10, 0, 7};
        ClockLine(ctx, base, x, y, x+dx[direction], y+dy[direction], direction==4 ? 0x35414C : 0xE3EAF2, 3);
    }
    static void DrawClockClock(lv_draw_ctx_t* ctx, const lv_area_t& base) {
        const uint8_t digits[4] = {uint8_t(s_artHour/10), uint8_t(s_artHour%10),
                                  uint8_t(s_artMinute/10), uint8_t(s_artMinute%10)};
        for (int i=0; i<4; ++i) for (int dial=0; dial<6; ++dial) {
            int x = 35+i*62+(dial%2)*28, y = 33+(dial/2)*42;
            ClockRect(ctx, base, x-13, y-13, 26, 26, 0x24313B, 13);
            ClockRect(ctx, base, x-11, y-11, 22, 22, 0x101820, 11);
            int pose = kClockHandDigits[digits[i]][dial];
            ClockHand(ctx, base, x, y, pose/5); ClockHand(ctx, base, x, y, pose%5);
        }
    }
    static void DrawPolygon(lv_draw_ctx_t* ctx, const lv_area_t& base) {
        const int x[12] = {144,178,204,214,204,178,144,110,84,74,84,110};
        const int y[12] = {12,20,44,78,112,136,144,136,112,78,44,20};
        const int dx[6] = {-7,0,7,7,0,-7}, dy[6] = {-4,-8,-4,4,8,4};
        for (int i=0; i<12; ++i) for (int side=0; side<6; ++side) {
            int next=(side+1)%6;
            ClockLine(ctx, base, x[i]+dx[side], y[i]+dy[side], x[i]+dx[next], y[i]+dy[next],
                      i==s_artHour%12 ? 0x71E8DC : 0x344656, i==s_artHour%12 ? 3 : 1);
        }
        char text[4]; snprintf(text, sizeof(text), "%02u", s_artMinute);
        ClockText(ctx, base, 105, 59, 78, text, &lv_font_montserrat_36, 0xDFECFA);
        // Six triangle markers indicate the current ten-minute sector.
        for (int i=0; i<6; ++i) {
            int px=113+i*12;
            uint32_t color = i==s_artMinute/10 ? 0xB59EFF : 0x344656;
            ClockLine(ctx, base, px, 110, px+4, 102, color);
            ClockLine(ctx, base, px+4, 102, px+8, 110, color);
            ClockLine(ctx, base, px+8, 110, px, 110, color);
        }
    }
