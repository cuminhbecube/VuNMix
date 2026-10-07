# Standby clock styles

Settings → Clock Style offers sixteen styles. Choose one and press Save. Set Clock Standby (min) above zero to enable the idle clock display. Install both the v0.4.21 desktop app and firmware to use IDs 8–15.

| ID | Style | Appearance |
| --- | --- | --- |
| 0 | Neon Digital | Cyan DSEG clock |
| 1 | Minimal | White time with a separate seconds line |
| 2 | Flip Cards | Large hour/minute cards |
| 3 | Analog | Round face with three hands |
| 4 | Orbit | Blue seconds ring around digital time |
| 5 | Binary | Hour/minute/second bit columns with decimal values |
| 6 | Terminal | Green command-line clock with blinking cursor |
| 7 | Retro LCD | Pale green LCD face inside a dark case |
| 8 | Nixie | Orange numerals in rounded glass tube outlines |
| 9 | Word Clock | English word grid highlighting exact 24-hour hour/minute values |
| 10 | Pixel Art | Blue pixel digits above a small city skyline |
| 11 | Dot Matrix | Orange illuminated dots forming hour/minute digits |
| 12 | ClockClock | 24 miniature dials forming four digits; hands change at minute boundaries |
| 13 | Barcode | Decorative binary bars encoding six decimal digits, with readable time |
| 14 | Polygon | Twelve hour hexagons, six ten-minute triangle sectors and exact minute numeral |
| 15 | Math Clock | Arithmetic expressions for the hour and minute |

All eight additions include an exact HH:MM:SS / 24H footer. Barcode is decorative, not a standard scannable barcode. ClockClock has discrete hand positions without animated transitions.

## Compatibility

Settings remain 19 bytes, protocol version 1 and saved style IDs 0–7 retain their meanings. The low three style bits remain in byte 4 alongside the five LED-mode bits. Byte 3 bit 0 retains sleepEnabled; previously unused bit 1 extends the clock ID to four bits. Bits 2–7 remain zero. Old stored byte values 0/1 decode unchanged.

The desktop app checks firmware semantic versions during the connection handshake. Only firmware v0.4.21 and later receives the extension bit. For older or unrecognized development firmware, selecting IDs 8–15 sends Neon while preserving the user's selected style in PC configuration, sleep setting and LED mode. IDs 0–7 use the original packet representation. Updating firmware enables the saved new selection on reconnect. Custom builds should use a semantic version at least v0.4.21 to enable these designs.

## Resources and validation

Graphics use existing LVGL primitives and fonts. New art styles use a single custom draw object, a title and a footer; no retained dot grids, framebuffer assets or canvas are allocated. Widget creation occurs on entry/style change. Updates reuse the objects and redraw bounded shapes. FullReset clears pointers after deleting the screen. No fonts, bitmap assets, worker threads or continuous animations are added. Time synchronization also updates when the hour/minute changes but seconds remain equal.

Tests cover all sixteen style/LED combinations, configuration persistence, legacy fallback and native C++ packet bytes versus Python bytes. A host C++ test runs the actual renderer against an LVGL ownership double through 20 cycles of all sixteen styles with 3,600 ticks per style (1,152,000 ticks). It checks drawing bounds, word values, binary values, same-second corrections and object reuse/reset. Firmware CI compiles against real LVGL; the host double does not validate rasterization or physical TFT appearance.
