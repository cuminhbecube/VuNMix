#pragma once

#include <Arduino.h>

enum class InputEvent {
    None,
    PrevTab,
    NextTab,
    Mute,
    VolDown,
    VolUp,
    PlayPause
};

namespace Input {
    void Initialize();
    void Update();

    // These variables act as the interface to the main loop, simulating the rotary encoder
    extern volatile int8_t g_EncoderSteps;
    // We will simulate ButtonEvents library events: none, tap, doubleTap, hold
    enum ButtonEvent { none, tap, doubleTap, hold };
    extern volatile ButtonEvent g_ButtonEvent;
}
