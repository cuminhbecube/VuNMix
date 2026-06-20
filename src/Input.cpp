#include "Input.h"
#include "Config.h"
#include <Keypad.h>
//#if ARDUINO_USB_MODE
//#include "USB.h"
//#include "USBHIDConsumerControl.h"
//USBHIDConsumerControl ConsumerControl;
//#endif

namespace Input {
    volatile int8_t g_EncoderSteps = 0;
    volatile ButtonEvent g_ButtonEvent = none;

    bool g_RawKeyStates[6] = {false, false, false, false, false, false};
    bool g_KeyStatesChanged = false;

    const byte ROWS = 2; 
    const byte COLS = 3; 
    // Map keys to simple characters for Keypad library
    char keys[ROWS][COLS] = {
        {'P', 'M', 'N'}, // Prev, Mute, Next
        {'-', ' ', '+'}  // Vol-, Play, Vol+
    };
    byte rowPins[ROWS] = {PIN_KEY_R0, PIN_KEY_R1}; 
    byte colPins[COLS] = {PIN_KEY_C0, PIN_KEY_C1, PIN_KEY_C2}; 

    Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

    uint32_t lastHoldTime = 0;
    char holdingKey = 0;

    void Initialize() {
// #if ARDUINO_USB_MODE
//         ConsumerControl.begin();
//         USB.begin();
// #endif
        keypad.setHoldTime(500);
        keypad.setDebounceTime(30);
    }

    void Update() {
        if (keypad.getKeys()) {
            for (int i=0; i<LIST_MAX; i++) {
                if (keypad.key[i].stateChanged) {
                    char k = keypad.key[i].kchar;
                    auto state = keypad.key[i].kstate;

                    int keyIndex = -1;
                    if (k == 'P') keyIndex = 0;
                    else if (k == 'M') keyIndex = 1;
                    else if (k == 'N') keyIndex = 2;
                    else if (k == '-') keyIndex = 3;
                    else if (k == ' ') keyIndex = 4;
                    else if (k == '+') keyIndex = 5;

                    if (keyIndex != -1) {
                        if (state == PRESSED || state == HOLD) g_RawKeyStates[keyIndex] = true;
                        else if (state == RELEASED || state == IDLE) g_RawKeyStates[keyIndex] = false;
                        g_KeyStatesChanged = true;
                    }

                    if (state == PRESSED) {
                        if (k == 'P') g_ButtonEvent = hold; // Fake hold for Prev mode? Actually let's just make Prev Tab = hold equivalent? No, Prev Tab should change mode or session. MaxMix: Hold = Mode change, CCW = Prev session.
                        // Let's map Prev Tab to CCW rotation (prev session). Next Tab to CW rotation (next session).
                        // Wait, what about Volume? Vol- = CCW, Vol+ = CW. 
                        // Ah. MaxMix: 
                        // - Mode Navigate: Encoder moves between sessions.
                        // - Mode Edit: Encoder changes volume.
                        // We can't easily decouple them if we just fake encoder steps.
                        // Actually, if we use Vol- / Vol+ we just send encoder steps, and it will change session OR volume depending on state!
                        // That's exactly how MaxMix works!
                        // So: Vol- = -1 step, Vol+ = +1 step.
                        // What about Prev Tab / Next Tab? We can fake a Button Hold (change mode) for Next Tab?
                        
                        if (k == 'M') g_ButtonEvent = tap;
                        if (k == 'N') g_ButtonEvent = hold; // Mode change
                        if (k == 'P') {
                            // double tap = mute in maxmix
                            g_ButtonEvent = doubleTap;
                        }
                        if (k == '-') g_EncoderSteps = g_EncoderSteps - 1;
                        if (k == '+') g_EncoderSteps = g_EncoderSteps + 1;
// #if ARDUINO_USB_MODE
//                         if (k == ' ') ConsumerControl.press(CONSUMER_CONTROL_PLAY_PAUSE);
// #endif
                    }
                    else if (state == RELEASED) {
                        holdingKey = 0;
// #if ARDUINO_USB_MODE
//                         if (k == ' ') ConsumerControl.release();
// #endif
                    }
                    else if (state == HOLD) {
                        holdingKey = k;
                        lastHoldTime = millis();
                    }
                }
            }
        }
        
        // Continuous step generation if held
        if (holdingKey != 0 && millis() - lastHoldTime > 50) { // every 50ms
            if (holdingKey == '-') g_EncoderSteps = g_EncoderSteps - 1;
            if (holdingKey == '+') g_EncoderSteps = g_EncoderSteps + 1;
            lastHoldTime = millis();
        }
    }
}
