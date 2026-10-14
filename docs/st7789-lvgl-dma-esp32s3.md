# VuNMix ST7789 DMA incident — v0.4.27 black screen hotfix

**Status: DMA ROLLED BACK.** The v0.4.27 display-DMA experiment caused
a **user-confirmed regression:** the AVI intro plays, then the ST7789 screen
is black when control passes to LVGL. Until hardware validation can be
performed, no new release may enable the experimental SPI DMA backend.

## Findings from source inspection

The v0.4.27 firmware:
- Switched TFT_eSPI from the previous default SPI bus to ESP32-S3 HSPI/SPI3.
- Called `tft.init()` (which initializes SPIClass's bus), then called
  `tft.initDMA(false)` in DisplayDma.inc.
- The pinned TFT_eSPI ESP32-S3 DMA implementation calls
  `spi_bus_initialize(spi_host, ...)` **again on the same host**, and then
  `ESP_ERROR_CHECK(ret)`. If the bus is already initialized, this can cause
  a fatal assertion/reset instead of the intended fallback.
- The video player initializes and draws before the LVGL startup, so this
  is consistent with an intro that plays but no following display. The
  exact hardware reset reason is **not proven without the USB Serial log**.

Other potential causes still require hardware tests, including SPI host
pin routing, CS-less bus behavior, or RGB565 transfer ordering.

## Hotfix: return to last known working implementation

- Revert `platformio.ini` exactly to the released **v0.4.26** file.
  This restores its original SPI host and 27 MHz ST7789 configuration.
- Revert `src/ui/modules/DisplayCoreState.inc` **byte-for-byte** to
  v0.4.26, including the synchronous LVGL `pushColors(...,true)` flush.
- Remove the unsafe experimental `DisplayDma.inc`.
- Add source-level regression gates in
  `desktop/tests/test_display_dma_firmware.py`; these forbid accidental
  reintroduction of DMA and verify intro-before-LVGL startup.
- Leave the existing AVI, 16 clocks, USB protocol, PC application,
  OTA behavior and persistent DeviceSettings unchanged.

This is an intentional safety rollback of **only** the unvalidated DMA
experiment, not a performance improvement. No claims of increased FPS.

## Physical verification after flashing

1. Keep `v0.4.26` firmware available as a recovery image:
   https://github.com/cuminhbecube/VuNMix/releases/tag/v0.4.26
2. Flash the hotfix firmware and power cycle. Check that the intro video
   **and** following 'Waiting for connection' splash are visible.
3. Connect the Windows desktop app and cycle Output, Input, Application,
   Game, Health and all 16 clock styles.
4. Check touch and buttons, LED/backlight wake and sleep, and colors.
5. If the screen stays black, collect USB serial logs at **115200 baud**
   from power-up. Look for `ESP_ERROR_CHECK failed`, backtrace, panic and
   brownout/reset reason. Do not assert a root cause until logs confirm it.
6. Run 24-hour stability validation before calling the device hardware
   validated.

## Future DMA research branch — separate from the recovery firmware

A safe future architecture must avoid initializing a second ESP-IDF SPI
device on an SPIClass-owned host without bus coordination. Consider a
single owner for the SPI bus with esp_lcd DMA, or a proven display library
integration. Hardware-test bus ownership, buffered RGB565 bytes, LVGL
flush lifetime, video-to-LVGL handoff and 16 clock transitions. Only
enable DMA again after physical panel testing, with a retained rollback.

CI validates firmware compilation, regression contracts, desktop tests
and crash-reconnect stress. **CI does not validate TFT electrical output.**
