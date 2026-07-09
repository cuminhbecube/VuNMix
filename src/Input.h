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

    enum class TouchEvent : uint8_t {
        None,
        Tap,
        DoubleTap,
        LongPress,
        SwipeLeft,
        SwipeRight,
        SwipeUp,
        SwipeDown
    };

    bool TouchAvailable();
    TouchEvent ConsumeTouchEvent();
    TouchEvent LastTouchEvent();
    uint8_t LastTouchRawGesture();
    uint8_t LastTouchFingers();
    uint16_t LastTouchX();
    uint16_t LastTouchY();
    bool TouchIntActive();
    uint32_t TouchSampleCounter();

    // These variables act as the interface to the main loop, simulating the rotary encoder
    extern volatile int8_t g_EncoderSteps;
    // We will simulate ButtonEvents library events: none, tap, doubleTap, hold
    enum ButtonEvent { none, tap, doubleTap, hold };
    extern volatile ButtonEvent g_ButtonEvent;

    // Raw key states for splash screen test: 0=P, 1=M, 2=N, 3=-, 4=Space, 5=+
    extern bool g_RawKeyStates[6];
    extern bool g_KeyStatesChanged;
}
