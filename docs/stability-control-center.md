# VuNMix Stability and Control Center implementation

Work branch: `feat/stability-control-center-20261013`.
Based on released `v0.4.24`, preserving every published 16-clock style.

## Changes in this branch

### 1. Release safety / feature preservation
- `.github/workflows/release.yml` tests feature contracts before builds.
- For published release candidates, complete Git history is fetched; latest
  published release tag **must be an ancestor** of the current commit.
- Existing release tags and assets are immutable; publish a *new* version
  rather than force-updating an old tag.
- `scripts/verify_feature_contracts.py` locks 16 ClockStyle names, renderer
  modules, desktop clock selector and critical audio/media/update modules.
- These static contracts complement, never replace, Windows tests and
  the firmware renderer test (1,152,000 simulated clock ticks).

### 2. RAM / resource telemetry
- `desktop/resource_monitor.py`: bounded latest 24 resource samples.
- AudioSync writes RSS/private bytes, threads and handles every 300 seconds.
- Suspected sustained RSS growth (>=128MiB over >=1h, mainly monotonic)
  emits a diagnostic warning, **not** an automatic restart.
- Real 24–72h Windows PC soak still required. A passing CI run cannot prove
  real device COM/native memory is leak-free.

### 3. Hardware / UX stability
- See `docs/hardware-qa-matrix.md` for 11 uncompleted physical test cases.
- Features such as USB reconnect/firmware ROM fallback and APP/GAME safe
  volume navigation already have automated regression tests.
- Do **not** mark firmware flash or master-volume tests passed without a
  physical ESP32-S3 and Windows audio endpoint.

### 4. Update Center
- Existing desktop installer and firmware release downloader verify SHA256.
- `desktop/update_center.py` provides independent compatibility guidance.
- In the UI, firmware v0.4.21+ unlocks all 16 clock styles; older firmware
  exposes eight styles. Unknown/disconnected firmware is never called compatible.
- Manual flash requires the existing explicit version/file action and connection gate.\n- Automatic firmware sync can run on connection when the saved `Auto FW Update` preference is enabled; this behavior is retained from previous versions.
- Future follow-up: formal manifest with hardware id, protocol capabilities,
  signed releases and recovery verification.

### 5. Windows Control Center
- `desktop/gui.py`: 820x680 maximum, responsive to smaller displays,
  persistent MainThread Tk root, independent per-tab scrolling and fixed Save.
- **Overview:** real USB/firmware state, clock selection, bounded local RSS
  snapshot, and safe navigation shortcuts.
- **Audio:** read-only snapshot for output, input and applications (8 items per
  class maximum); rebuilds only when data changes, max 2.5s refresh.
- **Clock:** all 16 published styles, searchable through the existing
  dropdown and an informational preview; settings and firmware wire compatible.
- **Device:** standby LED, brightness, colors, sleep timeout.
- **Updates:** versions and compatibility status, existing SHA256-verified
  Windows updater and explicit firmware version/file selection.
- **Settings:** startup and automatic updater preferences, sleep switches.
- The existing system tray, controller API, audio worker, firmware protocol
  and COM thread ownership are retained. Audio list is intentionally read-only;
  do not call COM volume setters directly from a Tk callback.
- Preview is a text summary, **not** a rendered LVGL pixel-perfect preview.

### 6. Documentation
- README now identifies all 16 clock styles and exact protocol extension bits.
- Clock details: `docs/standby-clock-styles.md`.
- Hardware validation: `docs/hardware-qa-matrix.md`.

## Release prerequisites
1. Windows full unittest suite PASS and feature contract PASS.
2. Five independent connection/crash stress rounds PASS.
3. ESP32-S3 PlatformIO firmware build PASS.
4. Packaged Windows portable/setup + esptool stub test PASS.
5. Physical H04 and H07 from QA matrix must be recorded before the word
   **hardware validated** may be used.
6. Increment version rather than rewriting `v0.4.24` or any published tag.

## Next increments
- Move Control Center view construction out of `gui.py` into isolated
  component modules, after Windows Tk smoke validation of this first UI.
- Add Update Center release manifest and copy-paste recovery diagnostics.
- Investigate native COM USS and handles with real workload if soak suggests
  sustained growth; avoid adding arbitrary timeouts or background restarts.
