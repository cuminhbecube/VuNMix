#pragma once

#include "Config.h"

namespace Display {
    void Initialize();
    void Update();
    void SplashScreen();
    void KeyTestScreen();
    void InfoScreen(bool touchAvailable);
    void ClockScreen(uint8_t hour, uint8_t minute, uint8_t second);
    
    void DeviceSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode);
    void DeviceEditScreen(SessionData* session, const char* label, DisplayMode mode);
    
    void ApplicationSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode);
    void ApplicationEditScreen(SessionData* session, DisplayMode mode);
    
    void GameSelectScreen(SessionData* session, char channel, bool canScrollLeft, bool canScrollRight, DisplayMode mode);
    void GameEditScreen(SessionData* altSession, SessionData* curSession, DisplayMode mode);
    void HealthScreen(
        bool pcConnected,
        uint32_t uptimeSeconds,
        uint32_t serialAgeMs,
        uint32_t freeHeap,
        uint32_t minFreeHeap,
        uint32_t maxAllocHeap,
        uint32_t rxFrames,
        uint32_t txFrames,
        uint32_t crcErrors,
        uint32_t protocolErrors,
        Command lastCommand,
        Command lastErrorCommand,
        uint8_t currentMode,
        uint8_t currentIndex,
        uint8_t outputCount,
        uint8_t inputCount,
        uint8_t appCount,
        bool touchReady,
        uint32_t touchSamples
    );
    void SetMeterLevels(uint8_t current, uint8_t alternate);
    void ReceiveAppIconMeta(const AppIconMeta* meta);
    void ReceiveAppIconChunk(const AppIconChunk* chunk);
    
    void UpdateTimers(uint32_t deltaTime);
    void ResetTimers();
    void Sleep();
}
