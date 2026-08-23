    // DEVICE HEALTH / DEBUG SCREEN & PC TELEMETRY GAUGE DASHBOARD
    // =========================================================
    static lv_obj_t* CreateCyberGauge(lv_obj_t* parent, int16_t x, int16_t y, int16_t w, int16_t h,
                                      const char* title, uint32_t colorHex,
                                      lv_obj_t*& outArc, lv_obj_t*& outValLabel, lv_obj_t*& outSubLabel)
    {
        lv_obj_t* card = CreateGlassPanel(parent, w, h);
        lv_obj_set_pos(card, x, y);
        lv_obj_set_style_border_color(card, lv_color_hex(colorHex), LV_PART_MAIN);
        lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
        lv_obj_set_style_border_opa(card, LV_OPA_50, LV_PART_MAIN);

        // Title at top
        lv_obj_t* tLbl = lv_label_create(card);
        lv_obj_set_style_text_font(tLbl, &lv_font_montserrat_12, LV_PART_MAIN);
        lv_obj_set_style_text_color(tLbl, lv_color_hex(colorHex), LV_PART_MAIN);
        lv_label_set_text(tLbl, title);
        lv_obj_align(tLbl, LV_ALIGN_TOP_MID, 0, 4);

        // Radial Arc Gauge
        outArc = lv_arc_create(card);
        lv_obj_set_size(outArc, 60, 60);
        lv_obj_align(outArc, LV_ALIGN_CENTER, 0, 4);
        lv_arc_set_bg_angles(outArc, 135, 45);
        lv_arc_set_range(outArc, 0, 100);

        lv_obj_set_style_arc_color(outArc, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
        lv_obj_set_style_arc_width(outArc, 6, LV_PART_MAIN);
        lv_obj_set_style_arc_rounded(outArc, true, LV_PART_MAIN);

        lv_obj_set_style_arc_color(outArc, lv_color_hex(colorHex), LV_PART_INDICATOR);
        lv_obj_set_style_arc_width(outArc, 6, LV_PART_INDICATOR);
        lv_obj_set_style_arc_rounded(outArc, true, LV_PART_INDICATOR);
        lv_obj_set_style_shadow_color(outArc, lv_color_hex(colorHex), LV_PART_INDICATOR);
        lv_obj_set_style_shadow_width(outArc, 12, LV_PART_INDICATOR);
        lv_obj_set_style_shadow_opa(outArc, LV_OPA_50, LV_PART_INDICATOR);

        lv_obj_set_style_bg_opa(outArc, LV_OPA_TRANSP, LV_PART_KNOB);
        lv_obj_clear_flag(outArc, LV_OBJ_FLAG_CLICKABLE);

        // Value inside Arc
        outValLabel = lv_label_create(outArc);
        lv_obj_set_style_text_font(outValLabel, &lv_font_montserrat_14, LV_PART_MAIN);
        lv_obj_set_style_text_color(outValLabel, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
        lv_label_set_text(outValLabel, "0%");
        lv_obj_align(outValLabel, LV_ALIGN_CENTER, 0, 0);

        // Subtitle below Arc
        outSubLabel = lv_label_create(card);
        lv_obj_set_style_text_font(outSubLabel, &lv_font_montserrat_10, LV_PART_MAIN);
        lv_obj_set_style_text_color(outSubLabel, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
        lv_label_set_text(outSubLabel, "");
        lv_obj_align(outSubLabel, LV_ALIGN_BOTTOM_MID, 0, -4);

        return card;
    }

    void HealthScreen(
        bool pcConnected,
        uint32_t uptimeSeconds,
        uint32_t serialAgeMs,
        uint32_t freeHeap,
        uint32_t minFreeHeap,
        uint32_t maxAllocHeap,
        uint32_t rxFrames,
        uint32_t txFrames,
        uint32_t crcErrors,
        uint32_t protocolErrors,
        Command lastCommand,
        Command lastErrorCommand,
        uint8_t currentMode,
        uint8_t currentIndex,
        uint8_t outputCount,
        uint8_t inputCount,
        uint8_t appCount,
        bool touchReady,
        uint32_t touchSamples
    ) {
        if (!s_shellBuilt || s_currentScreen == ScreenType::SPLASH ||
            s_currentScreen == ScreenType::KEY_TEST || s_currentScreen == ScreenType::INFO ||
            s_currentScreen == ScreenType::CLOCK) {
            FullReset();
            s_shellBuilt = false;
        }
        BuildShell(MODE_HEALTH);
        ClearContent(ScreenType::HEALTH);
        ShowShell(true);

        // Build graphical 3-Gauge HUD + Dual Bottom Cards if not created
        if (!s_cpuArc) {
            // 1. CPU Gauge Card (Left: X=0, W=100)
            CreateCyberGauge(s_contentArea, 0, 6, 100, 98,
                             "CPU", COL_CYAN,
                             s_cpuArc, s_cpuVal, s_cpuSub);

            // 2. GPU Gauge Card (Center: X=103, W=100)
            CreateCyberGauge(s_contentArea, 103, 6, 100, 98,
                             "GPU", COL_ORANGE,
                             s_gpuArc, s_gpuVal, s_gpuSub);

            // 3. RAM Gauge Card (Right: X=207, W=100)
            CreateCyberGauge(s_contentArea, 207, 6, 100, 98,
                             "RAM", COL_PURPLE,
                             s_ramArc, s_ramVal, s_ramSub);

            // 4. Bottom Left: Network Card (X=0, W=152, H=58)
            lv_obj_t* netCard = CreateGlassPanel(s_contentArea, 152, 58);
            lv_obj_set_pos(netCard, 0, 108);
            lv_obj_set_style_border_color(netCard, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_obj_set_style_border_width(netCard, 1, LV_PART_MAIN);
            lv_obj_set_style_border_opa(netCard, LV_OPA_30, LV_PART_MAIN);

            s_netDownLbl = lv_label_create(netCard);
            lv_obj_set_style_text_font(s_netDownLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_netDownLbl, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_obj_align(s_netDownLbl, LV_ALIGN_TOP_LEFT, 8, 6);

            s_netUpLbl = lv_label_create(netCard);
            lv_obj_set_style_text_font(s_netUpLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_netUpLbl, lv_color_hex(COL_CYAN), LV_PART_MAIN);
            lv_obj_align(s_netUpLbl, LV_ALIGN_BOTTOM_LEFT, 8, -6);

            // 5. Bottom Right: System Card (X=155, W=152, H=58)
            lv_obj_t* sysCard = CreateGlassPanel(s_contentArea, 152, 58);
            lv_obj_set_pos(sysCard, 155, 108);
            lv_obj_set_style_border_color(sysCard, lv_color_hex(COL_BLUE), LV_PART_MAIN);
            lv_obj_set_style_border_width(sysCard, 1, LV_PART_MAIN);
            lv_obj_set_style_border_opa(sysCard, LV_OPA_30, LV_PART_MAIN);

            s_sysLinkLbl = lv_label_create(sysCard);
            lv_obj_set_style_text_font(s_sysLinkLbl, &lv_font_montserrat_12, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_sysLinkLbl, lv_color_hex(COL_GREEN), LV_PART_MAIN);
            lv_obj_align(s_sysLinkLbl, LV_ALIGN_TOP_LEFT, 8, 6);

            s_sysHeapLbl = lv_label_create(sysCard);
            lv_obj_set_style_text_font(s_sysHeapLbl, &lv_font_montserrat_10, LV_PART_MAIN);
            lv_obj_set_style_text_color(s_sysHeapLbl, lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
            lv_obj_align(s_sysHeapLbl, LV_ALIGN_BOTTOM_LEFT, 8, -6);
        }

        char buf[64];
        if (g_PcStatsValid) {
            // Update CPU gauge
            lv_arc_set_value(s_cpuArc, g_PcStats.cpuUsage);
            snprintf(buf, sizeof(buf), "%u%%", g_PcStats.cpuUsage);
            lv_label_set_text(s_cpuVal, buf);
            lv_label_set_text(s_cpuSub, "LOAD");

            // Update GPU gauge
            lv_arc_set_value(s_gpuArc, g_PcStats.gpuUsage);
            snprintf(buf, sizeof(buf), "%u%%", g_PcStats.gpuUsage);
            lv_label_set_text(s_gpuVal, buf);
            if (g_PcStats.gpuTemp > 0)
                snprintf(buf, sizeof(buf), "%u°C", g_PcStats.gpuTemp);
            else
                snprintf(buf, sizeof(buf), "GPU LOAD");
            lv_label_set_text(s_gpuSub, buf);

            // Update RAM gauge
            lv_arc_set_value(s_ramArc, g_PcStats.ramUsage);
            snprintf(buf, sizeof(buf), "%u%%", g_PcStats.ramUsage);
            lv_label_set_text(s_ramVal, buf);
            snprintf(buf, sizeof(buf), "%u/%uG",
                     (g_PcStats.ramUsedMB + 512) / 1024,
                     (g_PcStats.ramTotalMB + 512) / 1024);
            lv_label_set_text(s_ramSub, buf);

            // Update Network Download
            if (g_PcStats.netDownKBps >= 1024)
                snprintf(buf, sizeof(buf), LV_SYMBOL_DOWN " %.1f MB/s", g_PcStats.netDownKBps / 1024.0);
            else
                snprintf(buf, sizeof(buf), LV_SYMBOL_DOWN " %u KB/s", g_PcStats.netDownKBps);
            lv_label_set_text(s_netDownLbl, buf);

            // Update Network Upload
            if (g_PcStats.netUpKBps >= 1024)
                snprintf(buf, sizeof(buf), LV_SYMBOL_UP " %.1f MB/s", g_PcStats.netUpKBps / 1024.0);
            else
                snprintf(buf, sizeof(buf), LV_SYMBOL_UP " %u KB/s", g_PcStats.netUpKBps);
            lv_label_set_text(s_netUpLbl, buf);

            // Update PC Link status
            snprintf(buf, sizeof(buf), "%s LINK %lums",
                     pcConnected ? LV_SYMBOL_OK : LV_SYMBOL_WARNING,
                     (unsigned long)serialAgeMs);
            lv_obj_set_style_text_color(s_sysLinkLbl, pcConnected ? lv_color_hex(COL_GREEN) : lv_color_hex(0xFF3333), LV_PART_MAIN);
            lv_label_set_text(s_sysLinkLbl, buf);

            // Update ESP Heap & Frame count
            snprintf(buf, sizeof(buf), "Heap:%luK | %lu",
                     (unsigned long)(freeHeap / 1024UL),
                     (unsigned long)rxFrames);
            lv_label_set_text(s_sysHeapLbl, buf);
        } else {
            // Standby when PC stats not yet received
            lv_arc_set_value(s_cpuArc, 0);
            lv_label_set_text(s_cpuVal, "--");
            lv_label_set_text(s_cpuSub, "WAIT");

            lv_arc_set_value(s_gpuArc, 0);
            lv_label_set_text(s_gpuVal, "--");
            lv_label_set_text(s_gpuSub, "WAIT");

            lv_arc_set_value(s_ramArc, 0);
            lv_label_set_text(s_ramVal, "--");
            lv_label_set_text(s_ramSub, "WAIT");

            lv_label_set_text(s_netDownLbl, LV_SYMBOL_DOWN " -- KB/s");
            lv_label_set_text(s_netUpLbl, LV_SYMBOL_UP " -- KB/s");

            snprintf(buf, sizeof(buf), "%s PC WAIT", pcConnected ? LV_SYMBOL_OK : LV_SYMBOL_WARNING);
            lv_obj_set_style_text_color(s_sysLinkLbl, pcConnected ? lv_color_hex(COL_ORANGE) : lv_color_hex(0xFF3333), LV_PART_MAIN);
            lv_label_set_text(s_sysLinkLbl, buf);

            snprintf(buf, sizeof(buf), "Heap:%luK | %lu",
                     (unsigned long)(freeHeap / 1024UL),
                     (unsigned long)rxFrames);
            lv_label_set_text(s_sysHeapLbl, buf);
        }
    }