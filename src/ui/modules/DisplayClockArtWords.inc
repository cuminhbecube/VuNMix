    static const char* kClockWords[27] = {
        "IT IS", "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
        "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN",
        "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN", "TWENTY",
        "THIRTY", "FORTY", "FIFTY", "HOURS", "MINUTES"
    };
    static bool ClockWordActive(int index, int value) {
        if (value<20) return index==value+1;
        return index==19+value/10 || (value%10 && index==value%10+1);
    }
    static void DrawWordClock(lv_draw_ctx_t* ctx, const lv_area_t& base) {
        for (int i=0; i<27; ++i) {
            bool hours = ClockWordActive(i, s_artHour), minutes = ClockWordActive(i, s_artMinute);
            uint32_t color = i==0 ? 0xEAF0F6 : i==25 ? 0x78CAFF : i==26 ? 0xF2BB71
                : hours && minutes ? 0xFFFFFF : hours ? 0x78CAFF : minutes ? 0xF2BB71 : 0x293744;
            ClockText(ctx, base, (i%3)*96, (i/3)*17, 96, kClockWords[i], &lv_font_montserrat_12, color);
        }
    }
