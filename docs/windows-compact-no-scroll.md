# VuNMix Windows Compact — no-scroll layout correction

## User report

v0.4.28 Windows Fluent Dark has nested vertical scrolling even on ordinary
desktop windows; controls extend below the viewport, and the layout requires
scrolling to find actions.

## Actual cause (source inspection)

- Overview built a CTkScrollableFrame around four status cards, a large
  clock, a multi-column mixer, buttons and status bar.
- Audio attempted Output/Input/Application/Game in parallel, up to eight
  rows each, then placed Profiles, Automation, OBS and Media *below*.
- Updates duplicated the full 16-style Clock Gallery below the firmware
  update panel while also placing Device settings next to it.
- Clock, Device and Settings had scroll wrappers even though forms can fit.
- The sidebar stayed 156 pixels wide when the user resized narrow.

## Implementation / navigation

| Page | Compact viewport content | All original features |
| --- | --- | --- |
| Overview | 4 quick facts, a single-row Output/Input/App summary, concise clock, four actions and bottom status | Navigate to full mixer, Clock and Updates |
| Audio > Mixer | One of Output/Input/Application/Game at a time; at most 4 rows, page selector | Identity-safe volume/mute/default-device actions; no audio changes on navigation |
| Audio > Profiles | Preset application, routing, ducking, rules, favorite apps | Same controller service callbacks, no storage/protocol changes |
| Audio > Media / OBS | Media previous/play/next, OBS stream/record/mic/desktop/scene | Same existing OBS and media callbacks |
| Clock | 16 RGB565 style selections in a dense 4x4 grid, short preview, standby timeout | 16 unchanged style IDs, firmware compatibility gate, Save pinned |
| Device | Existing LED, four colors, brightness, sleep timeout | All fields visible without scroll |
| Updates | App update, firmware release/bin, progress, status, health and power, link to full Clock Gallery | Same checksum verification and firmware downloader |
| Settings | Startup, auto updates, continuous scroll, sleep | Same persistent config and Save pinned |

**Sizing:** native Windows window, compact starting size up to 960x650;
geometry clamps to a usable 960x720 monitor (at most 920x620);
sidebar auto-collapses to 52px when resizing under 940px unless the user
explicitly toggles it. This is not a zoom/scale hack.

## Regression / acceptance

- Windows CI builds a real six-page CTk instance without connected board;
  tests navigation, audio subpages, source modes, fixed scroll-free forms,
  and compact 960x650 geometry.
- Pure source tests assert no remaining ScrollableFrame in Control Center,
  bounded four-row audio pager, one full 16-clock gallery, preserved actions.
- Firmware and USB protocol untouched. Run existing regression/installer
  and five isolated connection/crash suites.
- On real Windows, inspect 960x720 at DPI 100%, 125%, 150% and normal/maximized
  1920x1080. Pay attention to native taskbar height and large system fonts.
- At ultra-small screens where standard font controls exceed the available
  height, a custom accessible alternate dialog may still be needed; CI
  does not replace physical multi-DPI screenshots.
