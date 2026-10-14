# ST7789 320x240 LVGL SPI DMA — ESP32-S3 implementation and hardware QA

Baseline: VuNMix v0.4.26, ESP32-S3 N16R8, TFT_eSPI pinned at
`16e37595040eac69cd628e4bffb56fc30cad6299`, LVGL 8.3.11,
PlatformIO Arduino ESP32 `espressif32@6.9.0`.

## Audit of the released code
- Main LVGL renderer: `src/ui/modules/DisplayCoreState.inc` ->
  `flushCB` used `tft.pushColors(..., true)` (CPU-driven SPI), then marked
  LVGL flush ready. **No DMA allocation or init in the released code.**
- Two LVGL draw buffers each contain 320 x 24 RGB565 pixels (15,360 bytes).
- SPI clock fixed at 27 MHz; ST7789 240x320 rotated landscape to 320x240.
- The boot AVI uses `VideoPlayer.cpp` and a separate TFT_eSPI object
  sequentially *before* LVGL initializes. AVI decoding remains unchanged.

## Changed rendering path
1. Use HSPI/SPI3 with SCLK GPIO16, MOSI GPIO17, DC GPIO15, reset
   GPIO18, CS=-1, MISO=-1; SPI clock stays 27 MHz.
2. `-D VUNMIX_TFT_DMA=1` enables DMA by default. Set to `0` if
   hardware needs immediate rollback to the prior blocking SPI flush.
3. Allocate **15 KiB internal DMA-capable staging** with
   `heap_caps_malloc(MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA)`.
   Never DMA directly from PSRAM and never overwrite LVGL's draw buffers.
4. Swap RGB565 byte order into the staging buffer, preserving the
   `pushColors(..., true)` visual convention without modifying LVGL pixels.
5. Queue `tft.pushPixelsDMA` only for a tile fitting staging capacity.
   `finishDmaFlush` waits for the transaction, releases SPI and **then**
   calls `lv_disp_flush_ready`.
6. LVGL 8 `wait_cb` completes pending DMA when rendering requires the
   next buffer. End-of-update completion covers the final tile as well.
7. If DMA-capable internal RAM allocation fails, keep the previous
   synchronous `pushColors` path. Driver init also has its own false-
   result fallback. The driver may assert on lower-level SPI bus errors;
   **an initDMA internal assert cannot be recovered in firmware**.
8. Boot logs include `[DISPLAY] ST7789 SPI ...; LVGL DMA: enabled|SPI fallback`.

## Safety, caveats and real-world validation
- DMA reduces CPU copying overhead and permits overlap with LVGL draw work,
  but 27MHz is unchanged: bandwidth and effective FPS are *not guaranteed*
  to improve until measured.
- TFT_eSPI on ESP32-S3 has community reports of DMA freezes/one-frame
  failures, especially on various SPI hosts/versions. See Bodmer
  TFT_eSPI discussion #2233, issues #3414 and #3759.
- There are **no hardware logs or oscilloscope observations in CI**:
  do not claim a device has DMA working merely because code compiles.
- Do not raise SPI frequency until hardware signal-integrity tests PASS.
- Physically validate both firmware and user input before publishing a
  hardware-certified release:

| ID | Procedure | Acceptance |
| --- | --- | --- |
| D01 | Cold boot 20 times | Intro video, subsequent LVGL refresh every time |
| D02 | Serial log at boot | DMA enabled, no SPI bus init assertion |
| D03 | Cycle all 16 clock styles | No freezes, missing tiles, RGB/BGR inversion |
| D04 | Switch Output/Input/App/Game/Health | Text and meters respond, stable color |
| D05 | Move volume slider fast, touch/keys together | No stale frame, no input lag |
| D06 | Wake/sleep 100 cycles | Screen refreshes, LED state and no deadlocks |
| D07 | 24h runtime, rapidly changing VU | No increasing heap use, crash, DMA hang |
| D08 | FPS before/after at same 27 MHz | Compare measured frame duration and CPU |
| D09 | Build with `VUNMIX_TFT_DMA=0` | Sync fallback still fully functional |

## Source and tests
- Config: `platformio.ini`.
- DMA pipeline: `src/ui/modules/DisplayCoreState.inc`.
- Static QA: `desktop/tests/test_display_dma_firmware.py`.
- CI: full ESP32-S3 compile + 16-clock contracts, desktop tests, five
  isolated connection/crash suites; physical matrix remains to be run.
