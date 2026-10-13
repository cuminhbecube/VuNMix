# VuNMix hardware QA matrix and release blockers

Baseline: v0.4.24, ESP32-S3 N16R8, ST7789 320x240, CST816S,
six-key matrix, ten WS2812 LEDs, Windows 10/11.
**Software CI does not prove the checks below pass on a physical device.**
Record firmware/app versions, COM port, test PC OS build, pass/fail and logs.

| ID | Hardware test | Acceptance | Status |
| --- | --- | --- | --- |
| H01 | Connect USB cable, auto discovery and initial handshake | Correct board/version; no repeated disconnect | NOT RUN |
| H02 | Unplug/replug 100 times with active media/VU | Auto reconnect; no duplicate worker or stale COM operations | NOT RUN |
| H03 | Sleep/resume PC 20 cycles (hibernate separately) | App remains running, link recovers, no crash | NOT RUN |
| H04 | Switch Output -> APP -> GAME 50 times | Master volume never changes without explicit user action | NOT RUN |
| H05 | Change output/input default devices while connected | Display/session identity follows correct device | NOT RUN |
| H06 | Change 16 clock styles, sleep/wake 20 cycles | Each style renders, correct no overflow, no reboot, no heap drift | NOT RUN |
| H07 | Flash versioned .bin using packaged desktop app | ESP32-S3 resets, reconnects, verified version matches image | NOT RUN |
| H08 | Firmware flash failure: cable/boot mode, recovery | Helpful actionable error, device remains recoverable | NOT RUN |
| H09 | Run app 24-72h: OBS offline/online, media, ducking | RSS/handles/threads plateau; no crash or audio regression | NOT RUN |
| H10 | Buttons/touch/LED brightness sleep and clock | Inputs responsive; safe awake-only gesture; no IO conflicts | NOT RUN |
| H11 | Flash full firmware on blank spare board | Bootloader/partition/firmware offsets validated | NOT RUN |

## Collect a reproducible evidence bundle

1. Install latest Windows Setup and firmware **from the same release**.
2. Record host, serial port and observed firmware version in Update Center.
3. Save `%LOCALAPPDATA%\VuNMix\logs\vunmix.log` plus the update journal.
4. Capture Windows Task Manager Details: private memory, handles, threads, CPU
   at 0h, 1h, 8h, 24h and 72h. The sync worker also logs
   `VuNMix process memory: rss=... private=... handles=...` every five minutes.
5. For clock tests, capture all 16 screens and the firmware version.
6. For update tests, compare the device-reported semantic version after
   reconnect with the requested firmware version.
7. Attach evidence to the relevant GitHub issue and check the matching row
   only after observation, not because tests pass on GitHub Actions.

## P0 criteria before claiming hardware-certified release

- #1 firmware flash + reconnect on an actual board: H07.
- #30 navigation does not alter Windows master output: H04.
- #2 release gate: a previous published feature baseline is retained
  and released installer/firmware assets match their checksums.
- Any unexpected volume change, a failed flash unrecoverable without ROM
  fallback, repeated crash or monotonic multi-hour resource growth blocks
  a production-certified build.

The application may ship as a software-tested beta pending these hardware
checks, but it must not be represented as hardware-validated.
