#include "Display.h"
#include "Input.h"
#include <TFT_eSPI.h>
#include <lvgl.h>

LV_FONT_DECLARE(lv_font_dseg_90_bpp1);

extern DeviceSettings g_Settings;

namespace Display {
    TFT_eSPI tft = TFT_eSPI();

    static constexpr int16_t SW = 320;
    static constexpr int16_t SH = 240;

    static const uint32_t BUF_LINES = (uint32_t)SH / 10u;
    static lv_color_t s_buf1[(uint32_t)SW * ((uint32_t)SH / 10u)];
    static lv_color_t s_buf2[(uint32_t)SW * ((uint32_t)SH / 10u)];

    static lv_disp_drv_t      s_dispDrv;
    static lv_disp_draw_buf_t s_dispBuf;

    // =========================================================
    // Cyber-Tactile Design Tokens
    // =========================================================
    static const uint32_t COL_BG             = 0x141218;
    static const uint32_t COL_SURFACE        = 0x141218;
    static const uint32_t COL_SURFACE_LOW    = 0x0F0D13;
    static const uint32_t COL_SURFACE_HIGH   = 0x36343A;
    static const uint32_t COL_SURFACE_CONT   = 0x211F24;
    static const uint32_t COL_ON_SURFACE     = 0xE6E0E9;
    static const uint32_t COL_ON_SURFACE_V   = 0xCBC4D2;
    static const uint32_t COL_PRIMARY        = 0xCFBCFF;
    static const uint32_t COL_OUTLINE_V      = 0x494551;
    static const uint32_t COL_GLASS_BORDER   = 0x2A2A2F; // ~10% white on dark

    // Mode accent colors
    static const uint32_t COL_CYAN   = 0x06B6D4; // Output
    static const uint32_t COL_PURPLE = 0xCFBCFF; // Input
    static const uint32_t COL_GREEN  = 0x00FF88; // Application
    static const uint32_t COL_ORANGE = 0xFF7A00; // Game
    static const uint32_t COL_BLUE   = 0x60A5FA; // Health / debug

    // Layout constants
    static const int16_t HEADER_H  = 32;
    static const int16_t NAVBAR_H  = 32;
    static const int16_t STRIP_H   = 2;
    static const int16_t CONTENT_Y = HEADER_H;
    static const int16_t CONTENT_H = SH - HEADER_H - STRIP_H - NAVBAR_H;
    static const int16_t PAD       = 6;

    // =========================================================
    // TFT Flush Callback
    // =========================================================
    static void flushCB(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_p)
    {
        uint32_t w = (uint32_t)(area->x2 - area->x1 + 1);
        uint32_t h = (uint32_t)(area->y2 - area->y1 + 1);
        tft.startWrite();
        tft.setAddrWindow(area->x1, area->y1, w, h);
        tft.pushColors((uint16_t *)color_p, w * h, true);
        tft.endWrite();
        lv_disp_flush_ready(drv);
    }

    // =========================================================
    // Init
    // =========================================================
    void Initialize() {
        pinMode(PIN_TFT_BL, OUTPUT);
        digitalWrite(PIN_TFT_BL, HIGH);
        delay(100);

        tft.init();
        delay(100);

        tft.setRotation(1);

        tft.fillScreen(TFT_BLACK);

        lv_init();

        lv_disp_draw_buf_init(&s_dispBuf, s_buf1, s_buf2, (uint32_t)SW * BUF_LINES);

        lv_disp_drv_init(&s_dispDrv);
        s_dispDrv.hor_res  = SW;
        s_dispDrv.ver_res  = SH;
        s_dispDrv.flush_cb = flushCB;
        s_dispDrv.draw_buf = &s_dispBuf;
        lv_disp_drv_register(&s_dispDrv);

    }

    void Update() {
        lv_task_handler();
    }

    // =========================================================
    // Screen Tracking
    // =========================================================
    enum class ScreenType {
        NONE, SPLASH, KEY_TEST, INFO, CLOCK, DEVICE_SELECT, DEVICE_EDIT, GAME_SELECT, GAME_EDIT, HEALTH
    };

    static ScreenType s_currentScreen = ScreenType::NONE;

    // --- Persistent UI Shell objects ---
    static lv_obj_t* s_header     = nullptr;
    static lv_obj_t* s_headerIcon = nullptr;
    static lv_obj_t* s_headerTitle= nullptr;
    static lv_obj_t* s_navbar     = nullptr;
    static constexpr uint8_t NAV_MODE_COUNT = 5;
    static lv_obj_t* s_navBtns[NAV_MODE_COUNT] = {nullptr};
    static lv_obj_t* s_glowStrip  = nullptr;
    static lv_obj_t* s_contentArea= nullptr;
    static lv_obj_t* s_meterCurrent = nullptr;
    static lv_obj_t* s_meterAlternate = nullptr;
    static lv_obj_t* s_appIconImg = nullptr;
    static uint8_t s_meterCurrentValue = 0;
    static uint8_t s_meterAlternateValue = 0;
    static lv_color_t s_appIconCanvasBuf[16 * 16];
    static lv_img_dsc_t s_appIconDsc;

    // --- Content widgets (reused per screen) ---
    static lv_obj_t* s_titleLabel  = nullptr;
    static lv_obj_t* s_volArc      = nullptr;
    static lv_obj_t* s_volLabel    = nullptr;
    static lv_obj_t* s_volArcB     = nullptr;
    static lv_obj_t* s_volLabelB   = nullptr;
    static lv_obj_t* s_subLabel    = nullptr;
    static lv_obj_t* s_subLabelB   = nullptr;

    // Game mixer widgets. These objects are children of s_contentArea and
    // therefore become invalid whenever ClearContent/FullReset cleans LVGL.
    static lv_obj_t* s_faderA      = nullptr;
    static lv_obj_t* s_faderB      = nullptr;
    static lv_obj_t* s_faderNameA  = nullptr;
    static lv_obj_t* s_faderNameB  = nullptr;

    // PC Stats / Dashboard widgets
    static lv_obj_t* s_cpuArc      = nullptr;
    static lv_obj_t* s_cpuVal      = nullptr;
    static lv_obj_t* s_cpuSub      = nullptr;
    static lv_obj_t* s_gpuArc      = nullptr;
    static lv_obj_t* s_gpuVal      = nullptr;
    static lv_obj_t* s_gpuSub      = nullptr;
    static lv_obj_t* s_ramArc      = nullptr;
    static lv_obj_t* s_ramVal      = nullptr;
    static lv_obj_t* s_ramSub      = nullptr;
    static lv_obj_t* s_netDownLbl  = nullptr;
    static lv_obj_t* s_netUpLbl    = nullptr;
    static lv_obj_t* s_sysLinkLbl  = nullptr;
    static lv_obj_t* s_sysHeapLbl  = nullptr;

    // Splash specific
    static lv_obj_t* s_splashDots  = nullptr;
    static lv_anim_t s_dotAnim;
    static uint8_t   s_dotState = 0;

    static constexpr uint8_t APP_ICON_SIZE = 16;
    static constexpr uint16_t APP_ICON_BYTES = APP_ICON_SIZE * APP_ICON_SIZE * 2;
    static constexpr uint8_t APP_ICON_CACHE_SIZE = 8;
    struct AppIconCacheEntry {
        uint8_t id = 0;
        uint16_t received = 0;
        uint8_t data[APP_ICON_BYTES] = {0};
    };
    static AppIconCacheEntry s_appIcons[APP_ICON_CACHE_SIZE];
    static uint8_t s_appIconWriteSlot = 0;

    // Track which mode the shell was built for
    static DisplayMode s_shellMode = MODE_SPLASH;
    static bool s_shellBuilt = false;

    static AppIconCacheEntry* FindAppIcon(uint8_t id) {
        if (id == 0) return nullptr;
        for (uint8_t i = 0; i < APP_ICON_CACHE_SIZE; ++i) {
            if (s_appIcons[i].id == id)
                return &s_appIcons[i];
        }
        return nullptr;
    }

    static void UpdateAppIcon(uint8_t id, DisplayMode mode) {
        if (!s_appIconImg || !s_headerIcon || mode != MODE_APPLICATION)
            return;

        AppIconCacheEntry* icon = FindAppIcon(id);
        if (!icon || icon->received < APP_ICON_BYTES) {
            lv_obj_add_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_headerIcon, LV_OBJ_FLAG_HIDDEN);
            return;
        }

        lv_obj_add_flag(s_headerIcon, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_appIconImg, LV_OBJ_FLAG_HIDDEN);

        for (uint16_t i = 0; i < APP_ICON_SIZE * APP_ICON_SIZE; ++i) {
            uint16_t rgb565 = (uint16_t)icon->data[i * 2] | ((uint16_t)icon->data[i * 2 + 1] << 8);
            uint8_t r = (uint8_t)(((rgb565 >> 11) & 0x1F) * 255 / 31);
            uint8_t g = (uint8_t)(((rgb565 >> 5) & 0x3F) * 255 / 63);
            uint8_t b = (uint8_t)((rgb565 & 0x1F) * 255 / 31);
            s_appIconCanvasBuf[i] = lv_color_make(r, g, b);
        }
        s_appIconDsc.header.always_zero = 0;
        s_appIconDsc.header.w = APP_ICON_SIZE;
        s_appIconDsc.header.h = APP_ICON_SIZE;
        s_appIconDsc.header.cf = LV_IMG_CF_TRUE_COLOR;
        s_appIconDsc.data_size = sizeof(s_appIconCanvasBuf);
        s_appIconDsc.data = (const uint8_t*)s_appIconCanvasBuf;
        lv_img_set_src(s_appIconImg, &s_appIconDsc);
        lv_obj_invalidate(s_appIconImg);
    }

    // Splash Keypad Test
    static lv_obj_t* s_keyGrid = nullptr;
    static lv_obj_t* s_keyBoxes[6] = {nullptr};
    static lv_obj_t* s_touchStatusLabel = nullptr;
    static lv_obj_t* s_touchEventLabel = nullptr;
    static lv_obj_t* s_touchRawLabel = nullptr;