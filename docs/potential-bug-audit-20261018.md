# VuNMix v0.4.30 potential-bug audit

Baseline: `main` at `f1fa6a3` (v0.4.30). Follow-up review of proposed firmware/desktop edge cases.

## Confirmed preventive fixes

1. **USB CDC receive burst integrity** (`src/Communications.cpp`): the 512-byte receive buffer previously discarded the oldest byte on overflow, even when an intact frame was waiting to be parsed. The parser now stops reading when full and retains queued bytes in the serial driver until the next `Read()` iteration. It still resynchronizes on invalid frames. This reduces loss in a large burst but cannot guarantee that an overloaded USB driver never drops traffic.
2. **Reconnect generations** (`desktop/serial_service.py`): the old read/write handle could fail after a manual reconnect and call unqualified `disconnect()`, which closed a newer connection. Exceptions now close only the matching handle. A dedicated parser lock and generation-scoped decoding prevent old data being interpreted in a new connection.
3. **Stale Windows audio cache** (`desktop/audio_service.py`): `read_current_volume()` previously returned the cached `AudioItem` on COM failure/session disappearance, making an old value appear to be fresh. It now returns `None` and allows the polling worker to skip the stale update. COM cleanup remains paired via `_com_scope()`.

## Claims not reproduced

- Outgoing TX queue is **16 commands**, with per-command deduplication, and does not carry desktop-to-device slider updates. `TX_INTERVAL=30ms` applies to this outbound queue; `update_interval_ms` is not required to be equal to it.
- Keypad debounce is 30ms, repeat is 50ms; key scanning and volume consumption run serially in the firmware loop. There is no demonstrated FreeRTOS interrupt race for `g_EncoderSteps`.
- LVGL screen deletion/flush runs in the main firmware loop, not two concurrent LVGL widget threads.
- Audio sessions are **not** collapsed by executable filename; stable identity is intentionally retained. Volume interfaces are fetched inside per-thread COM scopes rather than kept in `_session_vols`.
- Periodic controller workers initialize/uninitialize COM in paired try/finally blocks, and `_com_scope()` initializes its own calling thread. Blanket `except` around all COM calls would hide real faults rather than fix a proven apartment leak.

## Validation

- Regression tests added for stale serial read generation, outdated connection close, vanished/failed Windows audio session and bounded receive ingestion.
- CI must pass ESP32-S3 firmware, Windows unit tests/installer packaging, feature contracts and all five connection stress rounds before a release.
- Physical USB fault injection and extended Windows RAM/COM handle monitoring remain necessary to validate field behavior.
