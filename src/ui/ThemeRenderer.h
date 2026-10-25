#pragma once

#include <stdint.h>

// Theme presentation never owns audio, clock, input, or sleep state.
// This small copied view model is also used by the native LVGL renderer.
namespace ThemeUI {
enum class Page : uint8_t { Audio, Select, Game, Health, Offline };
struct Session {
    char name[30];
    uint8_t volume;
    bool muted;
    bool isDefault;
    bool available;
};
struct ViewModel {
    Page page;
    uint8_t mode;                 // Existing DisplayMode, unchanged.
    char selectChannel;           // 'A'/'B' only for Game selection.
    Session current, alternate, previous, next;
    bool canPrevious, canNext;
    bool pcConnected;
    uint8_t meterCurrent, meterAlternate;
    bool mediaValid, mediaPlaying;
    char mediaTitle[32], mediaArtist[24];
    uint16_t mediaPosition, mediaDuration;
    bool statsValid;
    uint8_t cpu, cpuTemp, gpu, gpuTemp, ram;
    uint16_t ramUsedMB, ramTotalMB, netDownKBps, netUpKBps;
    uint32_t serialAgeMs, freeHeap, rxFrames;
};

// Exactly one retained native LVGL draw object. Updates reuse the object and
// allocate no widgets, point arrays, or per-theme screen trees.
bool Render(uint8_t themeId, const ViewModel& view);
void Tick();
void Destroy();
bool Exists();
} // namespace ThemeUI
