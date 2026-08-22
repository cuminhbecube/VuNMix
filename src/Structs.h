#pragma once

#include "Config.h"

struct __attribute__((__packed__)) SessionInfo
{
    DisplayMode mode;    // 8 bits
    uint8_t current;     // 8 bits
    uint8_t sessions[3]; // 24 bits - output, input, application
    // 40 bits - 5 bytes

    SessionInfo() : mode(DisplayMode::MODE_SPLASH), current(0), sessions{0} {}
};
static_assert(sizeof(SessionInfo) == 5, "Invalid Expected Message Size");

struct __attribute__((__packed__)) VolumeData
{
    uint8_t id : 7;     // 7 bits
    bool isDefault : 1; // 1 bit
    uint8_t volume : 7; // 7 bits
    bool isMuted : 1;   // 1 bit
    // 16 bits - 2 bytes

    VolumeData() : id(0), isDefault(false), volume(0), isMuted(false) {}
};
static_assert(sizeof(VolumeData) == 2, "Invalid Expected Message Size");

struct __attribute__((__packed__)) MeterData
{
    uint8_t current;
    uint8_t alternate;

    MeterData() : current(0), alternate(0) {}
};
static_assert(sizeof(MeterData) == 2, "Invalid Expected Message Size");

struct __attribute__((__packed__)) AppIconMeta
{
    uint8_t id;
    uint8_t width;
    uint8_t height;
    uint16_t dataLength;

    AppIconMeta() : id(0), width(0), height(0), dataLength(0) {}
};
static_assert(sizeof(AppIconMeta) == 5, "Invalid Expected Message Size");

struct __attribute__((__packed__)) AppIconChunk
{
    uint8_t id;
    uint8_t index;
    uint8_t length;
    uint8_t data[60];

    AppIconChunk() : id(0), index(0), length(0), data{0} {}
};
static_assert(sizeof(AppIconChunk) == 63, "Invalid Expected Message Size");

struct __attribute__((__packed__)) SessionData
{
    char name[30]; // 240 bits
    VolumeData data; // 24 bits
    // 256 bits - 32 bytes

    // name & data use { } initializers
    SessionData() : name{0}, data{} {}
};
static_assert(sizeof(SessionData) == 32, "Invalid Expected Message Size");

struct __attribute__((__packed__)) Color
{
    uint8_t r; // 8 bits
    uint8_t g; // 8 bits
    uint8_t b; // 8 bits

    Color() : r(0), g(0), b(0) {}
    Color(uint8_t r, uint8_t g, uint8_t b) : r(r), g(g), b(b) {}
}; // 24 bits - 3 bytes
static_assert(sizeof(Color) == 3, "Invalid Expected Message Size");

struct __attribute__((__packed__)) TimeData
{
    uint8_t hour;    // 0-23
    uint8_t minute;  // 0-59
    uint8_t second;  // 0-59

    TimeData() : hour(0), minute(0), second(0) {}
};
static_assert(sizeof(TimeData) == 3, "Invalid Expected Message Size");

struct __attribute__((__packed__)) DeviceSettings
{
    uint16_t sleepAfterSeconds;         // 16 Bits
    uint8_t accelerationPercentage : 7; // 7 Bits
    bool continuousScroll : 1;          // 1 Bit
    bool sleepEnabled;                  // 8 Bits (bool)
    uint8_t standbyLedMode;             // 8 Bits (0=ColorWave,1=Rainbow,...,15=Off)
    Color volumeMinColor;               // 24 Bits
    Color volumeMaxColor;               // 24 Bits
    Color mixChannelAColor;             // 24 Bits
    Color mixChannelBColor;             // 24 Bits
    uint8_t ledBrightness;              // 8 Bits
    uint8_t clockStandbyMinutes;        // 8 Bits (0=disabled, default=10)
    // 19 bytes

    DeviceSettings() : sleepAfterSeconds(300), accelerationPercentage(60), continuousScroll(true), sleepEnabled(true), standbyLedMode(0),
                 volumeMinColor(0, 0, 255), volumeMaxColor(255, 0, 0), mixChannelAColor(0, 0, 255), mixChannelBColor(255, 0, 255),
                 ledBrightness(96), clockStandbyMinutes(10) {}
};
static_assert(sizeof(DeviceSettings) == 19, "Invalid Expected Message Size");

struct __attribute__((__packed__)) ModeStates
{
    uint8_t states[DisplayMode::MODE_MAX]; // 48 bits
    // 48 bits - 6 bytes

    ModeStates() : states{0, 1, 1, 0, 0, 0} {}
    // states{STATE_LOGO, STATE_EDIT, STATE_EDIT, STATE_NAVIGATE, STATE_SELECT_A, STATE_NAVIGATE}
};
static_assert(sizeof(ModeStates) == 6, "Invalid Expected Message Size");

struct __attribute__((__packed__)) PcStatsData
{
    uint8_t cpuUsage;      // 0-100%
    uint8_t cpuTemp;       // °C (or 0 if unavailable)
    uint8_t gpuUsage;      // 0-100%
    uint8_t gpuTemp;       // °C (or 0 if unavailable)
    uint8_t ramUsage;      // 0-100%
    uint16_t ramUsedMB;    // MB
    uint16_t ramTotalMB;   // MB
    uint16_t netDownKBps;  // KB/s
    uint16_t netUpKBps;    // KB/s

    PcStatsData() : cpuUsage(0), cpuTemp(0), gpuUsage(0), gpuTemp(0), ramUsage(0),
                    ramUsedMB(0), ramTotalMB(0), netDownKBps(0), netUpKBps(0) {}
};
static_assert(sizeof(PcStatsData) == 13, "Invalid Expected Message Size");

struct __attribute__((__packed__)) MediaInfoData
{
    uint8_t isPlaying;     // 0=Paused/Stopped, 1=Playing
    uint16_t positionSec;  // Position in seconds
    uint16_t durationSec;  // Duration in seconds
    char title[32];        // Track title (null-terminated)
    char artist[24];       // Artist name (null-terminated)

    MediaInfoData() : isPlaying(0), positionSec(0), durationSec(0), title{0}, artist{0} {}
};
static_assert(sizeof(MediaInfoData) == 61, "Invalid Expected Message Size");

struct __attribute__((__packed__)) MediaControlData
{
    uint8_t action;        // 1=Play/Pause, 2=Next, 3=Prev, 4=Stop

    MediaControlData() : action(0) {}
    explicit MediaControlData(uint8_t act) : action(act) {}
};
static_assert(sizeof(MediaControlData) == 1, "Invalid Expected Message Size");
