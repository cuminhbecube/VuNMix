# Device themes

## User behavior

The eight stable IDs are Classic (0), Windows Dark (1), Studio (2), Paper (3),
Orbit (4), Pixel (5), Blocks (6), and Terminal (7). Device → Appearance previews
the selected theme; the existing **Save settings** action commits the PC preference
and requests synchronization. Lighting/standby controls remain in the other
Device subview. The PC application's own Windows-dark palette is independent.

The preference is optional when upgrading an old config. Until the user saves
an explicit choice, the selector follows the device's reported configuration;
opening a new PC app must not silently overwrite a choice stored by another PC.
Once saved, the latest desired choice is reapplied after a verified reconnection.

Preview uses sample data and actual 320×240 native firmware frames, not live
telemetry. Previewing alone sends no command. The controller tracks draft UI
selection, desired PC configuration, and the device-confirmed configuration
separately. It reports disconnected, applying, applied, deferred, unsupported,
timeout, and error states without blocking the Tk event loop.

## Immutable clock boundary

All 16 original `ClockStyle` IDs, drawing modules, font tables, PC preview code,
and clock selection behavior are retained. Theme palettes live outside the
original `COL_*` constants and do not alter the LVGL global theme. There is no
theme name, logo, label, border, or other new overlay on clocks.

`Display::SetDeviceTheme` changes only the selected ID. If a clock or sleeping
screen is visible, the main loop persists the choice but requests no redraw or
wake. The ordinary input/sleep state machine eventually returns to a non-clock
page, at which point the selected presentation is used. Theme requests do not
reset session, volume, mute, mode, inactivity, or volume-activity timers.

The original information/key/touch diagnostics remain shared screens. Themed
Output/Input/Application, selection, Game, Health, and offline views receive a
copied live model from the existing firmware state. One owned LVGL presentation
object is reused for themed updates and destroyed on exit; Classic retains the
original widgets. Long active endpoint/media names use bounded text scrolling.

## Optional protocol-v1 extension

The original 19-byte `DeviceSettings`, its clock bits, all prior command IDs,
and `version;P=1` TEST identity are unchanged. Theme storage uses the separate
NVS key `ui_theme` in the existing `vunmix` namespace, defaulting to Classic.
The PC uses a separate nullable `device_theme_id` preference.

`UI_THEME` is command **23**. Payloads are little-endian:

| Direction | Format | Fields |
| --- | --- | --- |
| PC → device | `<BBH>` (4 bytes) | operation, theme ID, request ID |
| Device → PC | `<HBBBB>` (6 bytes) | request ID, status, configured theme ID, support mask, schema |

Operations: QUERY=0, SET=1. Schema=1. The eight supported themes occupy bits
0–7 of the mask. Query ignores its unused theme byte. Invalid SET IDs and
operations are rejected without changing selection or persistent configuration.

| Status | Value | Meaning |
| --- | --- | --- |
| APPLIED | 0 | Selection is stored and the active non-clock presentation is ready. |
| SAVED_DEFERRED | 1 | Selection is stored; clock/sleep currently owns the display. |
| UNSUPPORTED | 2 | Extension/theme is not supported. |
| INVALID | 3 | Invalid request operation or theme ID. |
| BUSY | 4 | Retry the same bounded transaction later. |
| FAILED | 5 | Persistence or presentation could not be confirmed. |

The firmware only writes NVS when the choice changes. A failed persistent
write rolls selection back before requesting a redraw. Success is finalized
after the ordinary display update. A repeated SET for the current ID creates
no extra persistent write or presentation. Generic command OK remains a
heartbeat/framing acknowledgment and cannot confirm a theme.

PC transactions are matched by request ID and serial connection generation.
Retries are bounded; old replies cannot confirm a newer selection. A generation
guard is checked inside the serial write lock, preventing an old worker from
sending into a replacement connection. Theme responses bypass the slower audio
callback queue. Optional capability-query timeout does not tear down a healthy
older firmware connection. Firmware flashing suspends/cancels old transactions.

## Validation

Run the native release gate on Linux with GCC/G++:

```sh
python tools/native_theme_regression.py --download --verify
python -m unittest desktop.tests.test_firmware_device_theme_protocol -v
```

LVGL 8.3.11 is pinned and downloaded with a verified archive hash. The gate
compares native RGB565 captures with the original v0.4.34 baseline for all
16 clocks at four fixed times. It checks theme transitions and repeated live
updates in one LVGL process, and compares the packaged PC preview pixels with
the production rendering path. Host heap numbers do not establish target RAM,
frame rate, SPI timing, or physical-panel color accuracy.

The release workflow additionally builds the actual ESP32-S3 firmware, runs
the desktop suite and connection stress jobs on Windows, and produces the
Windows installer/portable package. Physical hardware validation remains a
separate step; these automated gates do not claim that a device was flashed.
