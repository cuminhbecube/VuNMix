#pragma once
#include <Arduino.h>

namespace VideoPlayer {
    // Play the embedded MJPEG AVI intro video on TFT screen
    void Play(const char* filepath = nullptr);
}
