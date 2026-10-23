#pragma once

#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using byte = uint8_t;
#define IRAM_ATTR
#define INPUT_PULLUP 1
#define OUTPUT 2
#define LOW 0
#define HIGH 1
#define FALLING 2
#define constrain(value, low, high) ((value) < (low) ? (low) : ((value) > (high) ? (high) : (value)))

static uint32_t testMillis = 0;
static bool testInterruptLow = true;
static uint8_t testReport[6] = {};
static bool testReadFails = false;

inline uint32_t millis() { return testMillis; }
inline void delay(uint32_t milliseconds) { testMillis += milliseconds; }
inline void delayMicroseconds(uint32_t) {}
inline void pinMode(uint8_t, int) {}
inline void digitalWrite(uint8_t, int) {}
inline int digitalRead(uint8_t) { return testInterruptLow ? LOW : HIGH; }
inline int digitalPinToInterrupt(uint8_t pin) { return pin; }
inline void attachInterrupt(int, void (*)(), int) {}
inline void noInterrupts() {}
inline void interrupts() {}

constexpr int LIST_MAX = 6;
enum KeyState { IDLE, PRESSED, HOLD, RELEASED };
struct Key {
    bool stateChanged = false;
    char kchar = 0;
    KeyState kstate = IDLE;
};

#define makeKeymap(keys) reinterpret_cast<char*>(keys)
class Keypad {
public:
    Key key[LIST_MAX];
    Keypad(char*, byte*, byte*, byte, byte) {}
    bool getKeys() { return false; }
    void setHoldTime(unsigned) {}
    void setDebounceTime(unsigned) {}
};

class TouchWireStub {
    uint8_t reg = 0;
    size_t cursor = 0;
    bool wroteRegister = false;
public:
    void begin(uint8_t, uint8_t) {}
    void end() {}
    void setClock(unsigned) {}
    void beginTransmission(uint8_t) { wroteRegister = false; }
    void write(uint8_t value) {
        if (!wroteRegister) reg = value;
        wroteRegister = true;
    }
    int endTransmission(bool = true) { return testReadFails ? 1 : 0; }
    size_t requestFrom(int, int length, int) { cursor = 0; return length; }
    int available() { return 0; }
    int read() {
        if (reg == 0xA7) return 0xB5;
        return cursor < sizeof(testReport) ? testReport[cursor++] : 0;
    }
};
static TouchWireStub Wire;
