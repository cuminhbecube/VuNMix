#ifndef VUNMIX_NATIVE_THEME_ARDUINO_H
#define VUNMIX_NATIVE_THEME_ARDUINO_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" uint32_t millis(void);
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
using std::min;
using std::max;

// Host adapter for operations used by the actual production drawing modules.
class String {
    std::string value;
public:
    String() = default;
    String(const char *text) : value(text ? text : "") {}
    String(std::string text) : value(std::move(text)) {}
    String(unsigned char number) : value(std::to_string(number)) {}
    String(int number) : value(std::to_string(number)) {}
    const char *c_str() const { return value.c_str(); }
    unsigned length() const { return static_cast<unsigned>(value.size()); }
    String substring(unsigned first, unsigned last) const { return value.substr(first, last - first); }
    String operator+(const char *other) const { return value + other; }
    String operator+(char other) const { return value + other; }
    String &operator+=(const char *other) { value += other; return *this; }
};

enum { OUTPUT = 1, HIGH = 1, LOW = 0 };
extern void native_gpio_write(int pin, int value);
inline void digitalWrite(int pin, int value) { native_gpio_write(pin, value); }
inline void pinMode(int, int) { std::abort(); }
inline void delay(unsigned) { std::abort(); }
#else
uint32_t millis(void);
#endif
#endif
