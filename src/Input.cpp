#include "Input.h"
#include "Config.h"
#include <Keypad.h>
#include <Wire.h>
//#if ARDUINO_USB_MODE
//#include "USB.h"
//#include "USBHIDConsumerControl.h"
//USBHIDConsumerControl ConsumerControl;
//#endif

namespace Input {
    static constexpr uint8_t CST816S_ADDRESS = 0x15;
    static constexpr uint8_t REG_GESTURE = 0x01;
    static constexpr uint8_t REG_CHIP_ID = 0xA7;
    static constexpr uint8_t REG_MOTION_MASK = 0xEC;
    static constexpr uint8_t REG_IRQ_CONTROL = 0xFA;
    static constexpr uint8_t REG_LONG_PRESS_TIME = 0xFC;
    static constexpr uint8_t REG_DISABLE_AUTO_SLEEP = 0xFE;

    static volatile bool s_touchInterruptPending = false;
    static bool s_touchAvailable = false;
    static TouchEvent s_touchEvent = TouchEvent::None;
    static TouchEvent s_lastTouchEvent = TouchEvent::None;
    static uint8_t s_lastRawGesture = 0;
    static uint8_t s_lastFingers = 0;
    static uint16_t s_lastX = 0;
    static uint16_t s_lastY = 0;
    static uint32_t s_touchSampleCounter = 0;
    static uint8_t s_lastGesture = 0;
    static uint32_t s_lastGestureAt = 0;
    static uint32_t s_lastTouchPollAt = 0;
    static bool s_touchDown = false;
    static uint16_t s_touchDownX = 0;
    static uint16_t s_touchDownY = 0;
    static uint16_t s_touchLastX = 0;
    static uint16_t s_touchLastY = 0;
    static uint32_t s_touchDownAt = 0;
    static uint32_t s_lastTapAt = 0;

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

    static void IRAM_ATTR TouchInterrupt()
    {
        // I2C must never run in interrupt context.
        s_touchInterruptPending = true;
    }

    static bool WriteTouchRegister(uint8_t reg, uint8_t value)
    {
        Wire.beginTransmission(CST816S_ADDRESS);
        Wire.write(reg);
        Wire.write(value);
        return Wire.endTransmission() == 0;
    }

    static bool ReadTouchRegisters(uint8_t reg, uint8_t *data, size_t length)
    {
        Wire.beginTransmission(CST816S_ADDRESS);
        Wire.write(reg);
        if (Wire.endTransmission(false) != 0)
            return false;

        size_t received = Wire.requestFrom(
            (int)CST816S_ADDRESS,
            (int)length,
            (int)true
        );
        if (received != length)
        {
            while (Wire.available()) Wire.read();
            return false;
        }

        for (size_t i = 0; i < length; ++i)
            data[i] = (uint8_t)Wire.read();
        return true;
    }

    static TouchEvent RotateSwipe(uint8_t gesture)
    {
        // Raw gesture order is up, down, left, right.
        static const TouchEvent rotations[4][4] = {
            {
                TouchEvent::SwipeUp, TouchEvent::SwipeDown,
                TouchEvent::SwipeLeft, TouchEvent::SwipeRight
            },
            {
                TouchEvent::SwipeLeft, TouchEvent::SwipeRight,
                TouchEvent::SwipeDown, TouchEvent::SwipeUp
            },
            {
                TouchEvent::SwipeDown, TouchEvent::SwipeUp,
                TouchEvent::SwipeRight, TouchEvent::SwipeLeft
            },
            {
                TouchEvent::SwipeRight, TouchEvent::SwipeLeft,
                TouchEvent::SwipeUp, TouchEvent::SwipeDown
            }
        };

        if (gesture < 0x01 || gesture > 0x04)
            return TouchEvent::None;
        return rotations[TOUCH_ROTATION % 4][gesture - 1];
    }

    static TouchEvent DecodeGesture(uint8_t gesture)
    {
        switch (gesture)
        {
            case 0x01:
            case 0x02:
            case 0x03:
            case 0x04:
                return RotateSwipe(gesture);
            case 0x05:
                return TouchEvent::Tap;
            case 0x0B:
                return TouchEvent::DoubleTap;
            case 0x0C:
                return TouchEvent::LongPress;
            default:
                return TouchEvent::None;
        }
    }

    static void QueueTouchEvent(TouchEvent event)
    {
        if (event == TouchEvent::None)
            return;

        uint32_t now = millis();
        if (event == s_lastTouchEvent && (uint32_t)(now - s_lastGestureAt) < 90U)
            return;

        s_touchEvent = event;
        s_lastTouchEvent = event;
        s_lastGestureAt = now;
    }

    static void DecodeTouchPoint(uint8_t fingers, uint16_t x, uint16_t y)
    {
        uint32_t now = millis();
        if (fingers > 0)
        {
            if (!s_touchDown)
            {
                s_touchDown = true;
                s_touchDownX = x;
                s_touchDownY = y;
                s_touchDownAt = now;
            }
            s_touchLastX = x;
            s_touchLastY = y;
            return;
        }

        if (!s_touchDown)
            return;

        s_touchDown = false;
        uint32_t duration = now - s_touchDownAt;
        int16_t dx = (int16_t)s_touchLastX - (int16_t)s_touchDownX;
        int16_t dy = (int16_t)s_touchLastY - (int16_t)s_touchDownY;

        // Rotate dx and dy based on TOUCH_ROTATION to match screen orientation
        int16_t rdx = dx;
        int16_t rdy = dy;
        switch (TOUCH_ROTATION % 4) {
            case 1:
                rdx = -dy;
                rdy = dx;
                break;
            case 2:
                rdx = -dx;
                rdy = -dy;
                break;
            case 3:
                rdx = dy;
                rdy = -dx;
                break;
            default:
                break;
        }
        dx = rdx;
        dy = rdy;

        int16_t adx = abs(dx);
        int16_t ady = abs(dy);

        if (duration <= 800U && (adx > 50 || ady > 50))
        {
            if (adx >= ady)
                QueueTouchEvent(dx > 0 ? TouchEvent::SwipeRight : TouchEvent::SwipeLeft);
            else
                QueueTouchEvent(dy > 0 ? TouchEvent::SwipeDown : TouchEvent::SwipeUp);
            return;
        }

        if (duration <= 650U && adx <= 35 && ady <= 35)
        {
            if ((uint32_t)(now - s_lastTapAt) <= 350U)
            {
                s_lastTapAt = 0;
                QueueTouchEvent(TouchEvent::DoubleTap);
            }
            else
            {
                s_lastTapAt = now;
                QueueTouchEvent(TouchEvent::Tap);
            }
        }
        else if (duration > 650U && adx <= 35 && ady <= 35)
        {
            QueueTouchEvent(TouchEvent::LongPress);
        }
    }

    static void InitializeTouch()
    {
        pinMode(PIN_TOUCH_INT, INPUT_PULLUP);
        pinMode(PIN_TOUCH_RST, OUTPUT);
        digitalWrite(PIN_TOUCH_RST, LOW);
        delay(50);
        digitalWrite(PIN_TOUCH_RST, HIGH);
        delay(100);

        Wire.begin(PIN_TOUCH_SDA, PIN_TOUCH_SCL);
        Wire.setClock(400000);

        uint8_t chipId = 0;
        s_touchAvailable = ReadTouchRegisters(REG_CHIP_ID, &chipId, 1);
        if (!s_touchAvailable)
            return;

        // Directional gestures + double click, gesture/change IRQ, one-second
        // long press, and no automatic standby that would hide the I2C device.
        WriteTouchRegister(REG_MOTION_MASK, 0x07);
        WriteTouchRegister(REG_IRQ_CONTROL, 0x31);
        WriteTouchRegister(REG_LONG_PRESS_TIME, 0x01);
        WriteTouchRegister(REG_DISABLE_AUTO_SLEEP, 0x01);

        s_touchInterruptPending = false;
        attachInterrupt(
            digitalPinToInterrupt(PIN_TOUCH_INT),
            TouchInterrupt,
            FALLING
        );
    }

    void Initialize() {
// #if ARDUINO_USB_MODE
//         ConsumerControl.begin();
//         USB.begin();
// #endif
        keypad.setHoldTime(500);
        keypad.setDebounceTime(30);
        InitializeTouch();
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
                        // P = mute, M = toggle Navigate/Edit, N = next mode.
                        if (k == 'M') g_ButtonEvent = tap;
                        if (k == 'N') g_ButtonEvent = hold;
                        if (k == 'P') g_ButtonEvent = doubleTap;
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

        uint32_t now = millis();
        bool intActive = s_touchAvailable && digitalRead(PIN_TOUCH_INT) == LOW;
        bool shouldPollTouch = s_touchAvailable &&
            (s_touchInterruptPending || intActive ||
             (uint32_t)(now - s_lastTouchPollAt) >= 25U);

        if (shouldPollTouch)
        {
            s_touchInterruptPending = false;
            s_lastTouchPollAt = now;

            // Gesture, finger count, X high/low and Y high/low are one report.
            // Coordinates are retained in the read for future direct-hit UI.
            uint8_t report[6] = {0};
            if (ReadTouchRegisters(REG_GESTURE, report, sizeof(report)))
            {
                uint8_t gesture = report[0];
                s_lastRawGesture = gesture;
                s_lastFingers = report[1] & 0x0F;
                s_lastX = (uint16_t)(((report[2] & 0x0F) << 8) | report[3]);
                s_lastY = (uint16_t)(((report[4] & 0x0F) << 8) | report[5]);
                ++s_touchSampleCounter;
                TouchEvent event = DecodeGesture(gesture);

                // One physical gesture can produce several IRQ pulses.
                if (event != TouchEvent::None &&
                    (gesture != s_lastGesture ||
                     (uint32_t)(now - s_lastGestureAt) >= 180U))
                {
                    QueueTouchEvent(event);
                    s_lastGesture = gesture;
                }

                DecodeTouchPoint(s_lastFingers, s_lastX, s_lastY);
            }
        }
    }

    bool TouchAvailable()
    {
        return s_touchAvailable;
    }

    TouchEvent ConsumeTouchEvent()
    {
        TouchEvent event = s_touchEvent;
        s_touchEvent = TouchEvent::None;
        return event;
    }

    TouchEvent LastTouchEvent()
    {
        return s_lastTouchEvent;
    }

    uint8_t LastTouchRawGesture()
    {
        return s_lastRawGesture;
    }

    uint8_t LastTouchFingers()
    {
        return s_lastFingers;
    }

    uint16_t LastTouchX()
    {
        return s_lastX;
    }

    uint16_t LastTouchY()
    {
        return s_lastY;
    }

    bool TouchIntActive()
    {
        return s_touchAvailable && digitalRead(PIN_TOUCH_INT) == LOW;
    }

    uint32_t TouchSampleCounter()
    {
        return s_touchSampleCounter;
    }
}
