# VuNMix v0.4.29 source audit (2026-10-18)

Base commit: `64ea4928`. Changes prepared for the next patch version.

## Confirmed and fixed

- Game Mixer desktop polling synchronized only `INDEX_CURRENT`. The periodic worker now updates current and alternate game channels independently, with epoch, ID and name verification before transmitting.
- Unconnected Splash key-test remained latched after a tap or key press. Diagnostic view now returns to Splash after eight seconds of released inputs, and receives a one-second timer tick.
- Desktop entry point lacked an explicit single-instance guard. A per-Windows-session named mutex prevents a second tray process from opening the same COM port.

## Findings from the supplied report already resolved

- Game Mixer double-tap transmits both current and alternate volume commands.
- `ClearContent` and `FullReset` null the surviving game LVGL pointers in `src/ui/modules/DisplayShellLifecycle.inc`.
- `ResetState` no longer resets persisted `g_Settings`, which is loaded from NVS during startup.
- Desktop config and logging are stored under user-writable LOCALAPPDATA and the legacy config is migrated.
- Session names are truncated safely at UTF-8 boundaries by `_truncate_utf8`.
- USB port rediscovery and confirmed device identity, media control over CDC, CST816S touch and stable application IDs already exist.

## Deferred / not safe as a blind hotfix

- Intro video and LVGL use independent TFT_eSPI instances with sequential initialization. This is redundant but not an established leak. A prior DMA/display regression caused black screens; changing display bus ownership requires hardware validation.
- The P/M/N keyboard labels do not match some documented navigation semantics, but changing them without testing users' installed hardware could break existing controls. Record the keymap clarification as a future feature.
- Grouping sessions solely by executable name can incorrectly couple separate audio sessions from the same process; stable session identities are the correct default.
- Bundled third-party DSEG font sources and archives should be cleaned only in a dedicated, licensing-aware repository task.

## Validation still required

Run the complete CI gates (firmware, Python unit tests, connection stress, packaged desktop Windows installer) and validate the video/TFT handoff, COM reconnection, native audio sessions and input gestures on physical hardware before publishing.
