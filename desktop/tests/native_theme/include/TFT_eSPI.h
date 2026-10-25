#pragma once
#include <cstdint>
#include <cstdlib>
static constexpr uint16_t TFT_BLACK = 0;
// Hardware initialization is intentionally unreachable; native LVGL owns flush.
class TFT_eSPI {
public:
    void startWrite() { std::abort(); }
    void setAddrWindow(int, int, unsigned, unsigned) { std::abort(); }
    void pushColors(uint16_t *, unsigned, bool) { std::abort(); }
    void endWrite() { std::abort(); }
    void init() { std::abort(); }
    void setRotation(int) { std::abort(); }
    void fillScreen(uint16_t) { std::abort(); }
};
