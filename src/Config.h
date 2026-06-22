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
#ifndef VERSION
    #define VERSION "v0.1-ESP32"
#endif

//********************************************************
// *** CONSTS
//********************************************************

// --- Serial Comms
static const uint32_t BAUD_RATE = 76800; // Unused for USB CDC, but kept for compatibility
static const uint64_t SERIAL_TIMEOUT = 10;

// --- Pins for ESP32-S3
static const uint8_t  PIN_PIXELS = 45;   // NeoPixel data (per hardware.md)
static const uint8_t  PIN_TFT_BL = 8;   // TFT backlight

// Matrix Keys
static const uint8_t  PIN_KEY_R0 = 38;
static const uint8_t  PIN_KEY_R1 = 41;
static const uint8_t  PIN_KEY_C0 = 42;
static const uint8_t  PIN_KEY_C1 = 40;
static const uint8_t  PIN_KEY_C2 = 39;

// Touch (I2C) - for future use
static const uint8_t  PIN_TOUCH_SDA = 5;
static const uint8_t  PIN_TOUCH_SCL = 4;
static const uint8_t  PIN_TOUCH_INT = 3;
static const uint8_t  PIN_TOUCH_RST = 2;

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
static const uint16_t DISPLAY_HEIGHT = 240;

static const uint32_t DEVICE_RESET_AFTER_INACTIVTY = 5000;
