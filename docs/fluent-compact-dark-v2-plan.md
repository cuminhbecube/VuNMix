# Fluent Compact Dark v2 — approved design implementation plan

Baseline: main @ v0.4.25, no firmware/protocol/format changes.
References: approved VuNMix dark Windows UI mockups for **Overview** and
**Update Center**. The reference figures are design targets, *not* telemetry.

## Design tokens / compact behavior

| Token | Value |
| --- | --- |
| background / surface / card | #0B1220 / #101B29 / #17283B |
| accent / text / muted / online | #298FDF / #EAF2FA / #96ABC1 / #21C58B |
| error / warning | #E66D77 / #E6AE66 |
| font | Segoe UI, 11/12/14/18 px-equivalent CTk sizes |
| spacing / radius | 6–12 px / 8–10 px |
| default / compact / minimum window | 1120×740 / 960×650 / 780×560 logical px |
| sidebar / collapsed | 156 / 52 px |
| titlebar / row | 42 / 34–40 px |
| UI ownership | single CTk root on MainThread, tray detached, queue marshaling |

At smaller usable screens the geometry is clamped and each content view can
scroll. Prefer responsive hiding/collapsing over clipping. Use title-bar
minimize, maximize and close-to-tray rather than always-on-top popups.

## Component contract mapped to two approved mockups

| Component / page | Source | Data / write path | Acceptance |
| --- | --- | --- | --- |
| Shell, sidebar, title/status | `gui.py`, `fluent_theme.py` | serial port, controller state | six routes, collapsed nav, no second Tk root |
| Overview 4 status cards | `fluent_views.py` | connected, firmware, clock config, RSS (PC) | no fabricated health or percent |
| Overview mixer columns | `fluent_views.py` | `audio.get_sessions_for_mode`, `audio.set_volume` | output/input/apps, mute/slider, session identity guard, debounced worker |
| Clock preview | `fluent_views.py` | `CLOCK_STYLE_NAMES`, wall time | explicitly stylized preview; never claim pixel-perfect LVGL |
| Quick actions | `fluent_views.py` | existing update, firmware, log, diagnostics routes | all buttons actionable |
| OBS/Media/Profiles summary | `fluent_views.py` | `obs_service`, `media_service`, `profile_controller` | action-enabled control or exact status and navigation |
| Audio detail | `fluent_views.py` | live Windows endpoint/session identities | Game Mixer, favorites, profiles, routing, ducking, media and OBS |
| Clock 16-style gallery | `fluent_views.py` | `CLOCK_STYLE_NAMES`, `clock_style_var` | exact 16 IDs; select-and-save and firmware compatibility info |
| Device / Settings | `gui.py`, `fluent_views.py` | DeviceSettings 19-byte wire payload and config | preserve LED colors/mode, brightness, sleep, startup, auto update, favorites |
| Update Center | `fluent_views.py`, `gui.py` | verified GitHub release and firmware update flows | real installed versions, explicit flash, SHA256; no invented install progress |
| Health / logs | `resource_monitor.py`, `diagnostics.py` | PC RSS/threads/handles; ESP metrics only when actually received | never label PC process memory as ESP heap |

## Implementation batches

1. **Baseline & safety:** freeze functional inventory; create branch; document
   component requirements. Existing 16-clock release contract must PASS.
2. **Foundation:** reusable palette, responsive geometry and compact sidebar.
   Keep the legacy six CTkTabview destinations for compatibility; replace
   visible segmented tab navigation with styled sidebar.
3. **Overview:** real status cards, audio mixer, clock preview, quick actions,
   OBS/media/profile strip. Main-thread render, bounded refresh only while visible.
4. **Audio:** identity-aware, debounced COM operations through an isolated
   bounded worker; keep mode navigation read-only. Add Game, routing/ducking,
   media and OBS in panel instead of concealing them in the tray.
5. **Clock:** 16 selectors, previews, firmware capability gates and standby
   preferences; no firmware changes.
6. **Device/Updates/Settings:** compact cards while retaining every existing
   form field, firmware picker, release updater, progress and Save semantics.
7. **Quality gates:** Windows headless-safe model tests + on-Windows Tk smoke,
   actual desktop unit tests, firmware compile, 5x connection/crash stress,
   PyInstaller + Inno Setup, visually inspect screenshot at 1120×740, 960×650,
   780×560 and 125%/150% Windows DPI when screenshot access exists.
8. **Merge/release:** PR and CI success, merge after gates; never retag or
   overwrite v0.4.25. Hardware reconnect/flash and 24–72h soak remain
   explicitly not verified unless observed on actual ESP32 hardware.

## UI event safety

- Serial callback never mutates Tk widgets from background thread.
- Slider actions are debounced and resolve sessions by stable device/session ID.
- Audio writes only for explicit user interaction. Tab changes are read-only.
- Incoming snapshot does not reset an actively dragged slider.
- Asynchronous firmware update uses the existing verification, checksum and
  connection lock; no new automatic flash side effects.
- Error states (disconnected, pending, unsupported firmware) disable unsafe
  actions instead of showing fake success.

## Regression checklist

- [ ] All 16 clocks, same numerical protocol IDs.
- [ ] Six destinations, sidebar navigation, resize / minimize / close-to-tray.
- [ ] Output/Input/App/Game, explicit volume/mute/default controls.
- [ ] OBS stream/record/scene/mic; media control; profiles; routing; ducking.
- [ ] LED colors/animations, brightness, touch, sleep, saved startup options.
- [ ] Firmware versions, verified flash, AppUpdater SHA256 and progress.
- [ ] Favorited applications, COM selection and test/health diagnostics.
- [ ] No unbounded background GUI worker, orphan windows or UI thread misuse.
- [ ] Windows package and firmware compile + stress suites PASS.

Scope note: precise illustration-only features without a firmware data feed
(e.g. ESP CPU %, heap/80MB or a photo-real renderer) are intentionally replaced
with actual available metrics or explanatory placeholders, never made-up values.
