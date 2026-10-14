"""Regression contracts for the ESP32-S3 LVGL/TFT SPI DMA backend.

These structural assertions catch lost DMA flags, early LVGL flush completion,
unsafe PSRAM buffers, or an accidentally disabled synchronous fallback.
Hardware-level throughput and panel integrity still require a real board.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "ui" / "modules" / "DisplayCoreState.inc"
PIO = ROOT / "platformio.ini"


class St7789DmaContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CORE.read_text(encoding="utf-8")
        cls.pio = PIO.read_text(encoding="utf-8")

    def test_dma_is_enabled_for_spi3_and_write_only_st7789(self):
        for setting in (
            "-D ST7789_DRIVER=1",
            "-D USE_HSPI_PORT=1",
            "-D TFT_MISO=-1",
            "-D SPI_FREQUENCY=27000000",
            "-D VUNMIX_TFT_DMA=1",
        ):
            self.assertIn(setting, self.pio)

    def test_internal_dma_staging_preserves_lvgl_buffers_and_colors(self):
        self.assertIn("MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA", self.core)
        self.assertIn("DMA_PIXELS * sizeof(uint16_t)", self.core)
        self.assertIn("static_assert(LV_COLOR_DEPTH == 16", self.core)
        self.assertIn("s_dmaPixels[i] = (uint16_t)((pixel << 8) | (pixel >> 8))", self.core)
        self.assertNotIn("tft.pushPixelsDMA((uint16_t*)color_p", self.core)

    def test_flush_not_ready_before_dma_finishes(self):
        finish = self.core.split("static void finishDmaFlush()", 1)[1].split(
            "static void waitFlushCB(", 1)[0]
        self.assertLess(finish.index("tft.dmaWait()"), finish.index("lv_disp_flush_ready("))
        self.assertLess(finish.index("tft.endWrite()"), finish.index("lv_disp_flush_ready("))
        self.assertIn("s_dispDrv.wait_cb = waitFlushCB;", self.core)
        self.assertIn("finishDmaFlush();", self.core)
        self.assertIn("tft.pushPixelsDMA(s_dmaPixels, count)", self.core)

    def test_fallback_when_dma_unavailable_and_old_spi_colors_retained(self):
        self.assertIn("#if VUNMIX_TFT_DMA", self.core)
        self.assertIn("s_dmaEnabled = tft.initDMA(false);", self.core)
        self.assertIn("if (s_dmaEnabled && count <= DMA_PIXELS)", self.core)
        self.assertIn("tft.pushColors((uint16_t*)color_p, count, true)", self.core)
        self.assertIn("lv_disp_flush_ready(drv);", self.core)
        self.assertIn('s_dmaEnabled ? "enabled" : "SPI fallback"', self.core)

    def test_only_one_dma_transfer_owns_lvgl_buffer_at_a_time(self):
        flush = self.core.split("static void flushCB(", 1)[1].split(
            "// =========================================================\n    // Init", 1
        )[0]
        self.assertLess(flush.index("finishDmaFlush();"),
                        flush.index("tft.pushPixelsDMA("))
        self.assertLess(flush.index("s_dmaPendingDrv = drv"),
                        flush.index("s_dmaInFlight = true"))
        self.assertGreaterEqual(self.core.count("finishDmaFlush();"), 3)


if __name__ == "__main__":
    unittest.main()
