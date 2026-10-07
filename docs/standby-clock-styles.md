# Standby clock styles

The desktop app's Settings → Clock Style menu now offers eight styles. Choose a style and press Save; it is sent with the normal device settings. Set Clock Standby (min) above zero to enable idle clock display.

| ID | Style | Appearance |
| --- | --- | --- |
| 0 | Neon Digital | Original cyan DSEG clock |
| 1 | Minimal | White time with a separate seconds line |
| 2 | Flip Cards | Two large hour/minute cards |
| 3 | Analog | Round face with three hands |
| 4 | Orbit | Blue seconds ring surrounding digital time |
| 5 | Binary | Three columns for hour/minute/second, with bit weights and decimal values |
| 6 | Terminal | Green command-line layout with blinking cursor |
| 7 | Retro LCD | Pale green LCD face inside a dark case |

New styles require both the updated PC app and firmware; older firmware supports IDs 0–3 and falls back to Neon for higher IDs. Existing saved styles retain their IDs. Settings remain 19 bytes and the protocol version is unchanged. The existing three clock-style bits fit all eight choices without affecting the five LED-mode bits.

All new graphics use existing LVGL primitives and fonts. Widget creation occurs on entry/style change, and per-second updates reuse those widgets. FullReset clears their pointers after deleting the screen. No extra bitmap assets, fonts, worker threads or animations are introduced. Clock updates also track the full time, so a time synchronization that changes the hour/minute while keeping the same seconds updates immediately.

Validation covers every style/LED combination and config persistence. A host C++ test runs the actual clock renderer against an LVGL ownership double through 20 cycles of all eight styles, with 3,600 ticks per style. It checks fixed-shape bounds, binary values, same-second time corrections and object reuse/reset. This double does not validate LVGL rasterization or physical TFT output; firmware CI compiles against real LVGL, and a device check remains useful for appearance.
