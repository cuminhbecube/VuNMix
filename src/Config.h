#pragma once
//********************************************************
// PROJECT: MAXMIX (ESP32-S3 Port)
//********************************************************

#include <Arduino.h>
#include "Enums.h"
#include "Structs.h"

//********************************************************
// *** DEFINES
//********************************************************
#ifndef VUNMIX_VERSION
    #define VUNMIX_VERSION "dev"
#endif

#ifndef VUNMIX_GIT_SHA
    #define VUNMIX_GIT_SHA "unknown"
#endif

#ifndef VUNMIX_BUILD_DATE
    #define VUNMIX_BUILD_DATE "development"
#endif

// Keep the legacy VERSION name used by the TEST handshake, but source it from
// the injected build metadata instead of a hard-coded release string.
#ifndef VERSION
    #define VERSION VUNMIX_VERSION
#endif

// Increment only for an incompatible USB-CDC protocol change. The desktop
// validates this value during TEST before sending state frames.
static constexpr uint8_t PROTOCOL_VERSION = 1;

//********************************************************
// *** CONSTS
//********************************************************

// --- Pins for ESP32-S3
static const uint8_t  PIN_PIXELS = 45;   // NeoPixel data (per hardware.md)
static const uint8_t  PIN_TFT_BL = 8;   // TFT backlight

// Matrix Keys
static const uint8_t  PIN_KEY_R0 = 38;
static const uint8_t  PIN_KEY_R1 = 41;
static const uint8_t  PIN_KEY_C0 = 42;
static const uint8_t  PIN_KEY_C1 = 40;
static const uint8_t  PIN_KEY_C2 = 39;

// Touch (CST816S over I2C)
static const uint8_t  PIN_TOUCH_SDA = 5;
static const uint8_t  PIN_TOUCH_SCL = 4;
static const uint8_t  PIN_TOUCH_INT = 6;
static const uint8_t  PIN_TOUCH_RST = 7;
// The touch sensor is portrait while TFT rotation 1 is landscape.
// Change to 0 if a panel variant already reports landscape gestures.
static const uint8_t  TOUCH_ROTATION = 3;
static const int8_t   TOUCH_VOLUME_STEP = 5;

// --- States
static const uint8_t STATE_NAVIGATE = 0;
static const uint8_t STATE_LOGO = 0;
static const uint8_t STATE_EDIT = 1;
static const uint8_t STATE_INFO = 1;
static const uint8_t STATE_MAX = 2;
static const uint8_t STATE_SELECT_A = 0;
static const uint8_t STATE_SELECT_B = 1;
static const uint8_t STATE_GAME_EDIT = 2;
static const uint8_t STATE_GAME_MAX = 3;

// --- Lighting (WS2812 / NeoPixel)
static const uint8_t PIXELS_COUNT = 10;      // 10 RGB LEDs on GPIO 45
static const uint8_t PIXELS_BRIGHTNESS = 96;

// --- Screen Drawing
static const uint16_t DISPLAY_WIDTH = 320;
static const uint32_t DEVICE_RESET_AFTER_INACTIVTY = 5000;

extern PcStatsData g_PcStats;
extern bool g_PcStatsValid;
extern MediaInfoData g_MediaInfo;
extern bool g_MediaInfoValid;
