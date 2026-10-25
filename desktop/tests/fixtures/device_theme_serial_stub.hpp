#pragma once
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
using std::min;
struct ThemeTestSerial {
    std::vector<uint8_t> input, output;
    size_t cursor = 0;
    int available() const { return static_cast<int>(input.size() - cursor); }
    int read() { return cursor < input.size() ? input[cursor++] : -1; }
    size_t write(const uint8_t* bytes, size_t size) {
        output.insert(output.end(), bytes, bytes + size); return size;
    }
};
extern ThemeTestSerial Serial;
