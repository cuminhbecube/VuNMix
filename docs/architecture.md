# VuNMix architecture

This document describes the v0.7 refactor boundaries. The refactor is behavior
preserving: protocol v1 command IDs, frame format and public controller entry
points remain unchanged.

## Desktop controller layers

`AppController` is the composition root. It owns services, protocol state,
worker lifetime and firmware-update serialization, but no longer contains the
implementation of every desktop responsibility.

- `controller_device.py` — power transitions, serial verification, protocol
  version gate and initial handshake.
- `controller_state.py` — hardware message decoding, Windows volume mutation,
  session selection and state push to the ESP32.
- `controller_workers.py` — periodic heartbeat/time/telemetry sync and live
  audio meter worker.
- `controller_power.py` — hidden Win32 power-notification window.
- `diagnostic_controller.py` — diagnostics + production firmware updater.
- `profile_controller.py` — persistent profiles/context switching.
- `media_controller.py` — optional media artwork transport.
- `audio_automation_controller.py` — per-app routing and ducking.

Feature controllers extend the base through narrow layers instead of adding
more responsibilities back to `app_controller.py`.

## Firmware display layers

`src/Display.cpp` is a tiny display composition root. It includes
`src/ui/DisplayScreens.inc`, which is itself only an ordered assembler for
focused UI modules under `src/ui/modules`:

- `DisplayCoreState.inc` — TFT/LVGL initialization, design tokens and shared
  widget/cache state;
- `DisplayThemeShell.inc` — theme helpers, mode icons/colors, glass-panel helper
  and persistent navigation shell construction;
- `DisplayShellLifecycle.inc` — shell updates/reset, meter update and app-icon
  receive/cache lifecycle;
- `DisplayStandalone.inc` — splash, input-test and version/info screens;
- `DisplayHealth.inc` — PC/device telemetry dashboard;
- `DisplayClockSelect.inc` — standby clock and output/input/app selection screen;
- `DisplayMixerMedia.inc` — volume edit, application media metadata and game
  selection/mixer construction;
- `DisplayGameLifecycle.inc` — game fader completion plus display timer/sleep
  lifecycle.

The modules are textually included in a fixed order into **one C++ translation
unit**. This is deliberate for v0.7: the legacy display implementation has a
large amount of file-local LVGL widget/cache state. Crossing translation-unit
boundaries at the same time as the structural split would change static
initialization/lifetime semantics and increase UI regression risk. The ordered
module split gives each screen family a clear maintenance boundary while
preserving the exact runtime ownership model.

If a later UI-only change introduces an explicit `DisplayContext`, these modules
can become independent `.cpp` files without requiring protocol or desktop
changes.

## Protocol compatibility boundary

Protocol v1 remains the compatibility boundary for v0.7:

- magic: `A5 5A`;
- maximum payload: 64 bytes;
- CRC-16/CCITT-FALSE;
- command IDs remain 1–22 exactly as defined before the refactor;
- packed payload sizes are unchanged.

`desktop/tests/test_architecture_boundaries.py` locks the controller/display
size boundaries, requires the ordered firmware UI module list, prevents any one
module from regrowing into a new 1,600-line monolith, and locks the protocol-v1
command map.
