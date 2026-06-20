#pragma once

#include "Config.h"

namespace Display {
    void Initialize();
    void Update();
    void SplashScreen();
    void KeyTestScreen();
    void InfoScreen();
    
    void DeviceSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode);
    void DeviceEditScreen(SessionData* session, const char* label, DisplayMode mode);
    
    void ApplicationSelectScreen(SessionData* session, bool canScrollLeft, bool canScrollRight, DisplayMode mode);
    void ApplicationEditScreen(SessionData* session, DisplayMode mode);
    
    void GameSelectScreen(SessionData* session, char channel, bool canScrollLeft, bool canScrollRight, DisplayMode mode);
    void GameEditScreen(SessionData* altSession, SessionData* curSession, DisplayMode mode);
    
    void UpdateTimers(uint32_t deltaTime);
    void ResetTimers();
    void Sleep();
}
