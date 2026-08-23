// VuNMix display composition root.
//
// The behavior-preserving screen implementation now lives under src/ui so the
// public Display.cpp stays a small manager/facade while screen modules are
// refactored independently. DisplayScreens.inc is intentionally included into
// this translation unit to keep all existing file-local LVGL state and avoid
// protocol/UI behavior changes during the v0.7 architecture split.
#include "ui/DisplayScreens.inc"
