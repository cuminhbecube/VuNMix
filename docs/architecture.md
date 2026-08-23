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

`src/Display.cpp` is now a tiny display composition root. The current LVGL
implementation lives under `src/ui/DisplayScreens.inc` and is textually included
into the same translation unit.

The include-based split is deliberate for v0.7: the legacy display code has a
large amount of file-local LVGL widget/cache state. Moving that state across C++
translation units in the same release would change initialization/lifetime
semantics and create unnecessary UI regression risk. Keeping one translation
unit preserves behavior while moving the screen implementation out of the
public display entry point.

The implementation is organized conceptually into these screen families:

- shell/theme — colors, nav shell, shared glass-panel helpers;
- standalone — splash, input-test, info and clock screens;
- mixer — output/input/application/game selection and editing;
- health — PC/device telemetry dashboard;
- media/app visuals — app-icon cache and media metadata presentation hooks.

A later UI-only change can split those regions into independent translation
units behind an explicit `DisplayContext`; protocol and desktop code do not need
to change for that work.

## Protocol compatibility boundary

Protocol v1 remains the compatibility boundary for v0.7:

- magic: `A5 5A`;
- maximum payload: 64 bytes;
- CRC-16/CCITT-FALSE;
- command IDs remain 1–22 exactly as defined before the refactor;
- packed payload sizes are unchanged.

`desktop/tests/test_architecture_boundaries.py` locks the controller/display
size boundaries and the protocol-v1 command map so future refactors cannot
silently collapse the architecture back into monolithic files or renumber the
wire protocol.
