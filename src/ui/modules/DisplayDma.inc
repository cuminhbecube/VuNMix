// LVGL ST7789 SPI DMA backend for ESP32-S3.
// Included once inside namespace Display from DisplayCoreState.inc;
// shares the active TFT_eSPI instance and LVGL driver state.

    // The ST7789 SPI bus is write-only. DMA transfers use a dedicated,
    // internal DMA-capable staging buffer; LVGL's drawing buffers must not be
    // swapped in-place or reused while DMA is reading from them.
    static constexpr uint32_t DMA_PIXELS = (uint32_t)SW * BUF_LINES;
    static_assert(LV_COLOR_DEPTH == 16, "VuNMix ST7789 requires RGB565 LVGL");
    static uint16_t* s_dmaPixels = nullptr;
    static bool s_dmaEnabled = false;
    static bool s_dmaInFlight = false;
    static lv_disp_drv_t* s_dmaPendingDrv = nullptr;

    // =========================================================
    // TFT DMA / LVGL Flush
    // =========================================================
    // A flush is complete only after the SPI DMA transaction finishes.
    // 'wait_cb' is also used to unblock LVGL when it renders multiple tiles
    // in one lv_timer_handler call. All callbacks run on the LVGL loop task.
    static void finishDmaFlush()
    {
        if (!s_dmaInFlight)
            return;

        tft.dmaWait();
        tft.endWrite();
        s_dmaInFlight = false;
        lv_disp_drv_t* completed = s_dmaPendingDrv;
        s_dmaPendingDrv = nullptr;
        if (completed)
            lv_disp_flush_ready(completed);
    }

    static void waitFlushCB(lv_disp_drv_t* drv)
    {
        (void)drv;
        finishDmaFlush();
    }

    static void flushCB(lv_disp_drv_t* drv, const lv_area_t* area, lv_color_t* color_p)
    {
        const uint32_t w = (uint32_t)(area->x2 - area->x1 + 1);
        const uint32_t h = (uint32_t)(area->y2 - area->y1 + 1);
        const uint32_t count = w * h;

        // The single staging buffer is reused only after the prior DMA has
        // fully completed. Every flush still has its own LVGL ready callback.
        finishDmaFlush();

#if VUNMIX_TFT_DMA
        if (s_dmaEnabled && count <= DMA_PIXELS) {
            // The old pushColors(..., true) path transmitted swapped RGB565.
            // TFT_eSPI::pushPixelsDMA does NOT do that unless setSwapBytes is
            // enabled (which would modify our staging buffer in-place).
            // Produce wire-order bytes in a separate DMA-capable allocation.
            const uint16_t* source = reinterpret_cast<const uint16_t*>(color_p);
            for (uint32_t i = 0; i < count; ++i) {
                const uint16_t pixel = source[i];
                s_dmaPixels[i] = (uint16_t)((pixel << 8) | (pixel >> 8));
            }

            tft.startWrite();
            tft.setAddrWindow(area->x1, area->y1, w, h);
            tft.pushPixelsDMA(s_dmaPixels, count);
            s_dmaPendingDrv = drv;
            s_dmaInFlight = true;
            return;
        }
#endif

        // Fallback works even without DMA-capable free heap. Keep the former
        // synchronous path unchanged, including RGB565 byte ordering.
        tft.startWrite();
        tft.setAddrWindow(area->x1, area->y1, w, h);
        tft.pushColors((uint16_t*)color_p, count, true);
        tft.endWrite();
        lv_disp_flush_ready(drv);
    }

    static void initializeDma()
    {
#if VUNMIX_TFT_DMA
    // Keep the 15 KiB LVGL tile (320*24*2) in internal, DMA-visible RAM.
    // PSRAM-only buffers cannot be passed directly to TFT_eSPI SPI DMA.
    s_dmaPixels = static_cast<uint16_t*>(heap_caps_malloc(
        DMA_PIXELS * sizeof(uint16_t),
        MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA
    ));
    if (s_dmaPixels) {
        // With no CS pin, TFT_eSPI must not control chip select.
        s_dmaEnabled = tft.initDMA(false);
        if (!s_dmaEnabled) {
            heap_caps_free(s_dmaPixels);
            s_dmaPixels = nullptr;
        }
    }
    Serial.printf(
        "[DISPLAY] ST7789 SPI %lu Hz; LVGL DMA: %s; tile: %lu pixels\n",
        (unsigned long)SPI_FREQUENCY,
        s_dmaEnabled ? "enabled" : "SPI fallback",
        (unsigned long)DMA_PIXELS
    );
#else
    Serial.println("[DISPLAY] ST7789 DMA disabled at build time");
#endif

    }
