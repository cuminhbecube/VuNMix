// VuNMix firmware UI is deliberately assembled as one C++ translation unit.
// Each module owns one responsibility/screen family, while textual inclusion
// preserves the legacy file-local LVGL state and initialization semantics.
#include "modules/DisplayCoreState.inc"
#include "modules/DisplayThemeShell.inc"
#include "modules/DisplayShellLifecycle.inc"
#include "modules/DisplayStandalone.inc"
#include "modules/DisplayHealth.inc"
#include "modules/DisplayClockSelect.inc"
#include "modules/DisplayMixerMedia.inc"
#include "modules/DisplayGameLifecycle.inc"
