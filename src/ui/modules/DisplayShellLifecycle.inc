        }

        // --- Update shell for current mode ---
        // Header
        lv_obj_set_style_text_color(s_headerIcon, accent, LV_PART_MAIN);
        lv_label_set_text(s_headerIcon, GetModeIcon(mode));
        lv_obj_clear_flag(s_headerIcon, LV_OBJ_FLAG_HIDDEN);
        if (s_appIconImg) lv_obj_add_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_text_color(s_headerTitle, accent, LV_PART_MAIN);
        lv_label_set_text(s_headerTitle, GetModeString(mode));

        if (mode == MODE_GAME) {
            lv_obj_clear_flag(s_meterAlternate, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_meterCurrent, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_size(s_meterCurrent, 76, 3);
            lv_obj_set_size(s_meterAlternate, 76, 3);
            lv_obj_align(s_meterAlternate, LV_ALIGN_RIGHT_MID, -24, -4);
            lv_obj_align(s_meterCurrent, LV_ALIGN_RIGHT_MID, -24, 4);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_ORANGE), LV_PART_INDICATOR);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_PRIMARY), LV_PART_INDICATOR);
        } else if (mode == MODE_HEALTH) {
            lv_obj_add_flag(s_meterAlternate, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s_meterCurrent, LV_OBJ_FLAG_HIDDEN);
        } else {
            // Stereo L / R Dual Meter
            lv_obj_clear_flag(s_meterCurrent, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_meterAlternate, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_size(s_meterCurrent, 76, 3);
            lv_obj_set_size(s_meterAlternate, 76, 3);
            lv_obj_align(s_meterAlternate, LV_ALIGN_RIGHT_MID, -24, -4);
            lv_obj_align(s_meterCurrent, LV_ALIGN_RIGHT_MID, -24, 4);
            lv_obj_set_style_bg_color(s_meterAlternate, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterCurrent, lv_color_hex(COL_SURFACE_HIGH), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_meterAlternate, accent, LV_PART_INDICATOR);
            lv_obj_set_style_bg_color(s_meterCurrent, accent, LV_PART_INDICATOR);
        }
        lv_bar_set_value(s_meterCurrent, s_meterCurrentValue, LV_ANIM_OFF);
        lv_bar_set_value(s_meterAlternate, s_meterAlternateValue, LV_ANIM_OFF);

        // Glow strip
        lv_obj_set_style_bg_color(s_glowStrip, accent, LV_PART_MAIN);
        lv_obj_set_style_bg_opa(s_glowStrip, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_shadow_color(s_glowStrip, accent, LV_PART_MAIN);

        // Nav buttons — highlight active
        for (int i = 0; i < NAV_MODE_COUNT; i++) {
            if (s_navModes[i] == mode) {
                lv_obj_set_style_text_color(s_navBtns[i], accent, LV_PART_MAIN);
                lv_obj_set_style_text_opa(s_navBtns[i], LV_OPA_COVER, LV_PART_MAIN);
                lv_obj_set_style_text_font(s_navBtns[i], &lv_font_montserrat_24, LV_PART_MAIN);
            } else {
                lv_obj_set_style_text_color(s_navBtns[i], lv_color_hex(COL_ON_SURFACE_V), LV_PART_MAIN);
                lv_obj_set_style_text_opa(s_navBtns[i], LV_OPA_50, LV_PART_MAIN);
                lv_obj_set_style_text_font(s_navBtns[i], &lv_font_montserrat_20, LV_PART_MAIN);
            }
        }

        s_shellMode = mode;
    }

    static void ShowShell(bool visible) {
        if (s_header)    lv_obj_set_style_opa(s_header,    visible ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
        if (s_navbar)    lv_obj_set_style_opa(s_navbar,    visible ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
        if (s_glowStrip) lv_obj_set_style_opa(s_glowStrip, visible ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_MAIN);
    }

    // =========================================================
    // Clear Content Area (preserves shell)
    // =========================================================
    static void ClearContent(ScreenType type) {
        digitalWrite(PIN_TFT_BL, HIGH);
        if (s_currentScreen != type) {
            if (s_contentArea) {
                lv_obj_clean(s_contentArea);
            }
            s_currentScreen = type;
            s_titleLabel = nullptr;
            s_volArc = nullptr;
            s_volArcB = nullptr;
            s_volLabel = nullptr;
            s_volLabelB = nullptr;
            s_subLabel = nullptr;
            s_subLabelB = nullptr;
            s_splashDots = nullptr;
            s_faderA = nullptr;
            s_faderB = nullptr;
            s_faderNameA = nullptr;
            s_faderNameB = nullptr;
            for (int i = 0; i < 8; ++i) s_healthRows[i] = nullptr;
            s_cpuArc = nullptr;
            s_cpuVal = nullptr;
            s_cpuSub = nullptr;
            s_gpuArc = nullptr;
            s_gpuVal = nullptr;
            s_gpuSub = nullptr;
            s_ramArc = nullptr;
            s_ramVal = nullptr;
            s_ramSub = nullptr;
            s_netDownLbl = nullptr;
            s_netUpLbl = nullptr;
            s_sysLinkLbl = nullptr;
            s_sysHeapLbl = nullptr;
        }
    }

    // Full screen reset (for splash or first boot)
    static void FullReset() {
        if (s_splashDots) {
            lv_anim_del(s_splashDots, nullptr);
        }
        lv_obj_clean(lv_scr_act());
        lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(COL_BG), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, LV_PART_MAIN);
        s_currentScreen = ScreenType::NONE;
        s_shellBuilt = false;
        s_header = nullptr;
        s_headerIcon = nullptr;
        s_headerTitle = nullptr;
        s_meterCurrent = nullptr;
        s_meterAlternate = nullptr;
        s_appIconImg = nullptr;
        s_navbar = nullptr;
        for (int i = 0; i < NAV_MODE_COUNT; i++) s_navBtns[i] = nullptr;
        s_glowStrip = nullptr;
        s_contentArea = nullptr;
        s_titleLabel = nullptr;
        s_volArc = nullptr;
        s_volArcB = nullptr;
        s_volLabel = nullptr;
        s_volLabelB = nullptr;
        s_subLabel = nullptr;
        s_subLabelB = nullptr;
        s_splashDots = nullptr;
        s_keyGrid = nullptr;
        for (int i=0; i<6; i++) s_keyBoxes[i] = nullptr;
        s_touchStatusLabel = nullptr;
        s_touchEventLabel = nullptr;
        s_touchRawLabel = nullptr;
        for (int i = 0; i < 8; ++i) s_healthRows[i] = nullptr;
        s_cpuArc = nullptr;
        s_cpuVal = nullptr;
        s_cpuSub = nullptr;
        s_gpuArc = nullptr;
        s_gpuVal = nullptr;
        s_gpuSub = nullptr;
        s_ramArc = nullptr;
        s_ramVal = nullptr;
        s_ramSub = nullptr;
        s_netDownLbl = nullptr;
        s_netUpLbl = nullptr;
        s_sysLinkLbl = nullptr;
        s_sysHeapLbl = nullptr;
        s_clockHM = nullptr;
        s_clockColon = nullptr;
        s_clockSec = nullptr;
        s_clockBrand = nullptr;
        s_clockPanel = nullptr;
        s_faderA = nullptr;
        s_faderB = nullptr;
        s_faderNameA = nullptr;
        s_faderNameB = nullptr;
    }

    void SetMeterLevels(uint8_t current, uint8_t alternate) {
        s_meterCurrentValue = min((uint8_t)100, current);
        s_meterAlternateValue = min((uint8_t)100, alternate);
        if (s_meterCurrent)
            lv_bar_set_value(s_meterCurrent, s_meterCurrentValue, LV_ANIM_OFF);
        if (s_meterAlternate)
            lv_bar_set_value(s_meterAlternate, s_meterAlternateValue, LV_ANIM_OFF);
    }

    void ReceiveAppIconMeta(const AppIconMeta* meta) {
        if (!meta || meta->id == 0 || meta->width != APP_ICON_SIZE ||
            meta->height != APP_ICON_SIZE || meta->dataLength != APP_ICON_BYTES) {
            return;
        }

        AppIconCacheEntry* icon = FindAppIcon(meta->id);
        if (!icon) {
            icon = &s_appIcons[s_appIconWriteSlot];
            s_appIconWriteSlot = (s_appIconWriteSlot + 1) % APP_ICON_CACHE_SIZE;
        }
        icon->id = meta->id;
        icon->received = 0;
        memset(icon->data, 0, sizeof(icon->data));
    }

    void ReceiveAppIconChunk(const AppIconChunk* chunk) {
        if (!chunk || chunk->id == 0 || chunk->length == 0 || chunk->length > 60)
            return;

        AppIconCacheEntry* icon = FindAppIcon(chunk->id);
        if (!icon) {
            if (chunk->index == 0) {
                icon = &s_appIcons[s_appIconWriteSlot];
                s_appIconWriteSlot = (s_appIconWriteSlot + 1) % APP_ICON_CACHE_SIZE;
                icon->id = chunk->id;
                icon->received = 0;
                memset(icon->data, 0, sizeof(icon->data));
            } else {
                return;
            }
        }

        uint16_t offset = (uint16_t)chunk->index * 60U;
        if (offset >= APP_ICON_BYTES)
            return;

        uint16_t writable = min((uint16_t)chunk->length, (uint16_t)(APP_ICON_BYTES - offset));
        memcpy(icon->data + offset, chunk->data, writable);
        uint16_t end = offset + writable;
        if (end > icon->received)
            icon->received = end;
    }

    // =========================================================
    // SPLASH SCREEN