"""Black-screen hotfix regression gate for ST7789 after boot intro.

v0.4.27 enabled TFT_eSPI::initDMA() on an SPIClass-owned bus. The library
uses ESP_ERROR_CHECK on spi_bus_initialize which can abort when the bus is
already initialized. This guard keeps the *known-good* v0.4.26 rendering
path until a hardware-validated replacement has been implemented.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "ui" / "modules" / "DisplayCoreState.inc"
PIO = ROOT / "platformio.ini"
VIDEO = ROOT / "src" / "VideoPlayer.cpp"
BOOT = ROOT / "src" / "main.cpp"


class DisplayBootRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CORE.read_text(encoding="utf-8")
        cls.pio = PIO.read_text(encoding="utf-8")
        cls.video = VIDEO.read_text(encoding="utf-8")
        cls.boot = BOOT.read_text(encoding="utf-8")

    def test_original_spi_bus_and_screen_wiring_restored(self):
        for flag in (
            "-D ST7789_DRIVER=1",
            "-D TFT_MOSI=17",
            "-D TFT_SCLK=16",
            "-D TFT_DC=15",
            "-D TFT_RST=18",
            "-D TFT_CS=-1",
            "-D SPI_FREQUENCY=27000000",
        ):
            self.assertIn(flag, self.pio)
        self.assertNotIn("-D USE_HSPI_PORT=1", self.pio)
        self.assertNotIn("-D VUNMIX_TFT_DMA=1", self.pio)
        self.assertNotIn("-D TFT_MISO=-1", self.pio)

    def test_lvgl_flush_stays_blocking_until_explicit_dma_validation(self):
        self.assertIn("tft.pushColors((uint16_t *)color_p, w * h, true)", self.core)
        self.assertIn("tft.startWrite();", self.core)
        self.assertIn("tft.endWrite();", self.core)
        self.assertIn("lv_disp_flush_ready(drv);", self.core)
        self.assertLess(self.core.index("tft.endWrite();"),
                        self.core.index("lv_disp_flush_ready(drv);"))
        for unsupported in ("tft.initDMA(", "pushPixelsDMA(", "dmaWait(",
                            "DisplayDma.inc", "waitFlushCB", "s_dmaInFlight"):
            self.assertNotIn(unsupported, self.core)
        self.assertFalse((ROOT / "src" / "ui" / "modules" / "DisplayDma.inc").exists())

    def test_known_good_lvgl_buffers_and_driver(self):
        self.assertIn("static lv_color_t s_buf1[", self.core)
        self.assertIn("static lv_color_t s_buf2[", self.core)
        self.assertIn("lv_disp_draw_buf_init(&s_dispBuf, s_buf1, s_buf2", self.core)
        self.assertIn("s_dispDrv.flush_cb = flushCB;", self.core)
        self.assertIn("lv_disp_drv_register(&s_dispDrv)", self.core)
        self.assertLessEqual(len(self.core.splitlines()), 240)

    def test_intro_and_lvgl_still_run_sequentially(self):
        self.assertLess(self.boot.index('VideoPlayer::Play("/intro.avi")'),
                        self.boot.index("Display::Initialize();"))
        self.assertLess(self.boot.index("Display::Initialize();"),
                        self.boot.index("Display::SplashScreen();"))
        self.assertIn("s_tft.init();", self.video)


if __name__ == "__main__":
    unittest.main()
