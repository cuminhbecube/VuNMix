# Native device theme regression gate

Run the mandatory release gate from the repository root:

```sh
python tools/native_theme_regression.py --download --verify
```

This requires Python 3.11+, GCC/G++, `ar`, and the pinned LVGL 8.3.11 source.
It does not require Pillow, a browser, SDL, Windows, a display server, or a board.
`--download` verifies the official archive SHA-256 before extraction and verifies
the exact source tree used by the compiler. A previously verified tree can be
provided with `VUNMIX_LVGL_DIR`; `VUNMIX_LVGL_ARCHIVE` accepts the pinned tarball.
`VUNMIX_NATIVE_CACHE` selects an external build/vendor cache; its default is in
the operating system's temporary directory.

## What is executed

The C++ harness includes the actual production `Display.cpp`, links the actual
theme renderer and original font tables, and renders through real LVGL into
320×240 RGB565 memory flushes with the production 320×24 double draw buffers.
The Arduino/TFT headers only adapt strings and GPIO declarations. GPIO writes
record backlight state; the physical TFT initializer/flush stubs abort if called.

The clock baseline contains 64 framebuffer SHA-256 values: every original clock
ID 0–15 at four fixed times. These were generated from immutable commit
`4ee00c424cf34e56eec26a383689197b2b47b4e1`, never from the modified working tree.
The gate verifies the clock modules and original font sources remain byte
identical, normalizing only checkout CRLF line endings. It then verifies actual
pixels and exercises changing all eight theme selections while clocks are
visible and while the backlight is asleep. Neither action may change clock
pixels, add objects/text, alter clock settings, or wake the display.

One LVGL process also repeatedly switches themes/modes with live volume, mute,
default/browse, application, Game A/B, meter, UTF-8, telemetry and offline data.
It checks actual pixel changes, heap integrity, retained object counts, free
memory and the largest free allocation after repeated identical cycles. The
suite preserves access to the original Info and key/touch diagnostic screens.
It also checks the actual text viewport while meter updates continue: default
endpoint names scroll in all eight themes, nondefault names remain static, and
media text scrolls in each of the seven new renderers. Classic Game value and
session-name label rectangles must not intersect at normal or 100% volume.

The immediate-draw label observer calls the real LVGL rasterizer unchanged. It
checks non-marquee text bounds, actual font measurements, and scalar truncation
for the new renderers, including 0/100% and 100 °C fixtures. Marquee text may
extend horizontally through its explicitly clipped viewport; other text may
not extend outside its declared drawing area or the physical 320×240 frame.

The eight shipped desktop preview PNGs are decoded without Pillow and compared
pixel-for-pixel with the production Output renderer. Their SHA-256 values and
source provenance must match the manifest. Preview creation is a separate,
explicit operation:

```sh
python tools/native_theme_regression.py --download --export-previews /tmp/device-theme-previews
```

Review those images before replacing the packaged assets. `--output /tmp/qa`
retains raw captures and diagnostic results. Normal verification uses a
temporary directory and never changes source, goldens or packaged assets.

## Baseline maintenance

`--generate-baseline` reads only the pinned git tree and requires it to be
available locally. It cannot bless modified current clock rendering. A clock
design change is outside this release's contract and requires a separate
explicitly reviewed policy change.

## Limits

Host heap counts are not ESP32-S3 RAM or timing measurements. This gate does not
exercise USB transport, NVS flash, the actual touchscreen, SPI transfer timing,
LCD brightness/gamma, or Windows audio. Native tests complement the existing
protocol/input tests and required physical-device checks.
