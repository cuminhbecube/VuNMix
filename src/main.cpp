#include <Arduino.h>

#include "Config.h"
#include "Display.h"
#include "VideoPlayer.h"
#include "Communications.h"
#include "Input.h"
#include <Adafruit_NeoPixel.h>
#include <Preferences.h>

//********************************************************
// *** VARIABLES
//*******************************************************
Preferences preferences;
// State
DeviceSettings g_Settings;
DeviceSettings g_PersistedSettings;
bool g_SettingsSavePending = false;
uint32_t g_SettingsChangedAt = 0;
SessionInfo g_SessionInfo;
SessionData g_Sessions[SessionIndex::INDEX_MAX];
ModeStates g_ModeStates;
MeterData g_MeterData;
PcStatsData g_PcStats;
bool g_PcStatsValid = false;
MediaInfoData g_MediaInfo;
bool g_MediaInfoValid = false;
bool g_DisplayDirty;
bool g_DisplayAsleep;
bool g_IdleDisplayAsleep = false;
bool g_PcAsleep = false;

// Time & Sleep
uint32_t g_Now;
uint32_t g_HeartbeatTimeout;
uint32_t g_LastActivity;
uint32_t g_NextPixelUpdate;
uint32_t g_LastSteps;

// Clock Standby
TimeData g_TimeData;
uint32_t g_TimeSyncMillis = 0;
bool g_TimeValid = false;
bool g_ClockMode = false;
uint32_t g_LastVolumeActivity = 0; // tracks last audio/volume change

// Lighting
Adafruit_NeoPixel g_Pixels(PIXELS_COUNT, PIN_PIXELS, NEO_GRB + NEO_KHZ800);

void ResetState();
bool CanScrollLeft();
bool CanScrollRight();
uint8_t GetIndexForMode(DisplayMode mode);
bool ProcessEncoderRotation();
bool ProcessEncoderButton();
bool ProcessTouch();
bool RefreshDisplaySleepState();
bool ProcessSleep();
bool ProcessClockStandby();
bool ProcessDisplayScroll();
void UpdateDisplay();
void GetCurrentTime(uint8_t &h, uint8_t &m, uint8_t &s);
void UpdateLighting();
void LightingStandby();
void LightingColorWave();
void LightingRainbow();
void LightingMeteor();
void LightingTwinkle();
void LightingBreathe();
void LightingConfetti();
void LightingFire();
void LightingOcean();
void LightingLava();
void LightingScanner();
void LightingTheaterChase();
void LightingRunningLights();
void LightingGradient();
void LightingSparkle();
void LightingAurora();
void LightingLedTest();
void LightingAudioVU(uint8_t levelL, uint8_t levelR);
void LightingGameVU(uint8_t levelGame, uint8_t levelVoice);
void LightingVolume(SessionData *item, Color *c1, Color *c2);
void LightingGameVolume();
Color LerpColor(Color *c1, Color *c2, uint8_t coeff);

//---------------------------------------------------------
void setup()
{
    Serial.begin(115200);
    delay(2000); // Give USB CDC time to enumerate

    ResetState();

    preferences.begin("vunmix", false);
    if (preferences.getBytesLength("settings") == sizeof(DeviceSettings)) {
        preferences.getBytes("settings", &g_Settings, sizeof(DeviceSettings));
    }
    g_PersistedSettings = g_Settings;

    Input::Initialize();

    esp_reset_reason_t reason = esp_reset_reason();
    if (reason == ESP_RST_POWERON) {
        VideoPlayer::Play("/intro.avi");
    }

    Display::Initialize();

    Communications::Initialize();

    g_Pixels.begin();
    g_Pixels.setBrightness(g_Settings.ledBrightness);
    g_Pixels.clear();
    g_Pixels.show();
    delay(50); // Let NeoPixel latch

    g_LastActivity = millis();
    g_LastVolumeActivity = millis();
    g_Now = millis();
    
    Display::SplashScreen();
}

//---------------------------------------------------------
void loop()
{
    uint32_t last = g_Now;
    g_Now = millis();

    Input::Update();

    if (Input::g_KeyStatesChanged) {
        Input::g_KeyStatesChanged = false;
        // Any physical key activity should reset the idle/clock timers. When
        // asleep, the first key event is consumed as a wake-only gesture.
        g_LastActivity = g_Now;
        g_LastVolumeActivity = g_Now;
        if (g_DisplayAsleep || g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
            g_DisplayDirty = true;
    }

    static uint32_t lastTouchSampleCounter = 0;
    uint32_t touchSampleCounter = Input::TouchSampleCounter();
    if (touchSampleCounter != lastTouchSampleCounter)
    {
        lastTouchSampleCounter = touchSampleCounter;
        if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
        {
            g_DisplayDirty = true;
            g_LastActivity = g_Now;
        }
    }

    Command command = Communications::Read();
    g_DisplayDirty = g_DisplayDirty || (command != Command::NONE && command != Command::ERROR);

    if (command != Command::NONE && command != Command::ERROR) {
        if (command == Command::SETTINGS) {
            g_Pixels.setBrightness(g_Settings.ledBrightness);
            g_SettingsSavePending = true;
            g_SettingsChangedAt = g_Now;
        }
        else if (command == Command::SLEEP) {
            // Host sleep is independent from the user-configurable idle sleep.
            // Keep it latched until an explicit resume heartbeat (OK) arrives.
            g_PcAsleep = true;
            g_ClockMode = false;
            RefreshDisplaySleepState();
            Display::Sleep();
        }
        else if (command == Command::OK && g_PcAsleep) {
            // The desktop sends OK explicitly on resume. Do not let unrelated
            // telemetry/settings frames wake a PC-suspended display.
            g_PcAsleep = false;
            g_LastActivity = g_Now;
            g_LastVolumeActivity = g_Now;
            g_ClockMode = false;
            RefreshDisplaySleepState();
        }
    }

    if (command == Command::CURRENT_SESSION || command == Command::ALTERNATE_SESSION ||
        command == Command::VOLUME_CURR_CHANGE || command == Command::VOLUME_ALT_CHANGE)
    {
        g_LastActivity = g_Now;
        g_LastVolumeActivity = g_Now; // Track audio changes for clock standby
        g_DisplayDirty = true;
    }

    // Drain any device-initiated messages (queued by Write()) AFTER Read()'s OK response
    Communications::SendPending();

    // Coalesce settings previews/reconnect handshakes into one NVS write.
    if (g_SettingsSavePending && (uint32_t)(g_Now - g_SettingsChangedAt) >= 2000U)
    {
        if (memcmp(&g_Settings, &g_PersistedSettings, sizeof(DeviceSettings)) != 0)
        {
            preferences.putBytes("settings", &g_Settings, sizeof(DeviceSettings));
            g_PersistedSettings = g_Settings;
        }
        g_SettingsSavePending = false;
    }

    if (ProcessEncoderRotation())
    {
        g_LastActivity = g_Now;
        g_LastVolumeActivity = g_Now;
        g_DisplayDirty = true;
    }

    if (ProcessTouch())
    {
        g_LastActivity = g_Now;
        g_LastVolumeActivity = g_Now;
        g_DisplayDirty = true;
    }

    if (ProcessEncoderButton())
    {
        g_LastActivity = g_Now;
        g_LastVolumeActivity = g_Now;
        g_DisplayDirty = true;
    }

    if (ProcessSleep())
    {
        g_DisplayDirty = true;
    }

    if (ProcessClockStandby())
    {
        g_DisplayDirty = true;
    }

    static uint32_t lastHealthRefresh = 0;
    if (g_SessionInfo.mode == DisplayMode::MODE_HEALTH &&
        (uint32_t)(g_Now - lastHealthRefresh) >= 1000U)
    {
        lastHealthRefresh = g_Now;
        g_DisplayDirty = true;
    }

    if (g_DisplayDirty || ProcessDisplayScroll())
    {
        UpdateDisplay();
    }

    Display::Update();
    Display::UpdateTimers(g_Now - last);
    g_DisplayDirty = false;

    // Update lighting at 50 Hz. Meter data arrives slower from Windows, so
    // firmware interpolation keeps motion smooth between USB samples.
    if (g_Now - g_NextPixelUpdate < 0x80000000U)
    {
        g_NextPixelUpdate = g_Now + LED_FRAME_INTERVAL_MS;
        UpdateLighting();
    }

    // Reset / Disconnect if no serial activity.
    if (!g_PcAsleep && (g_SessionInfo.mode != DisplayMode::MODE_SPLASH) && (g_Now - g_HeartbeatTimeout < 0x80000000U))
        ResetState();
}

//---------------------------------------------------------
void ResetState()
{
    // State
    g_SessionInfo = SessionInfo();
    g_Sessions[SessionIndex::INDEX_PREVIOUS] = SessionData();
    g_Sessions[SessionIndex::INDEX_CURRENT] = SessionData();
    g_Sessions[SessionIndex::INDEX_ALTERNATE] = SessionData();
    g_Sessions[SessionIndex::INDEX_NEXT] = SessionData();
    g_ModeStates = ModeStates();
    g_MeterData = MeterData();
    g_DisplayDirty = true;
    g_DisplayAsleep = false;
    g_IdleDisplayAsleep = false;
    g_PcAsleep = false;

    // Time & Sleep
    g_Now = millis();
    g_HeartbeatTimeout = 0;
    g_LastActivity = g_Now;
    g_LastVolumeActivity = g_Now;
    g_NextPixelUpdate = 0;
    g_ClockMode = false;
    g_LastSteps = 0;
}

// Volume processing
int8_t g_PreviousSteps = 0;
int8_t ComputeAcceleratedVolume(int8_t encoderDelta, uint32_t deltaTime, int16_t volume)
{
    if (encoderDelta == 0) return volume;

    int16_t baseSteps = abs((int)encoderDelta);
    uint8_t speedFactor = 0;
    if (deltaTime < 70U) speedFactor = 3;
    else if (deltaTime < 140U) speedFactor = 2;
    else if (deltaTime < 280U) speedFactor = 1;

    int16_t accelerated = baseSteps;
    if (speedFactor > 0 && g_Settings.accelerationPercentage > 0)
    {
        accelerated += (baseSteps * g_Settings.accelerationPercentage * speedFactor + 99) / 100;
    }

    if (encoderDelta > 0) volume += accelerated;
    else volume -= accelerated;
    
    return constrain(volume, 0, 100);
}

void PreviousSession(void)
{
    if (!CanScrollLeft()) return;
    if (g_SessionInfo.current == 0)
        g_SessionInfo.current = g_SessionInfo.sessions[GetIndexForMode(g_SessionInfo.mode)];
    g_SessionInfo.current--;
    g_Sessions[SessionIndex::INDEX_NEXT] = g_Sessions[SessionIndex::INDEX_CURRENT];
    g_Sessions[SessionIndex::INDEX_CURRENT] = g_Sessions[SessionIndex::INDEX_PREVIOUS];
    Communications::Write(Command::SESSION_INFO);
}

void NextSession(void)
{
    if (!CanScrollRight()) return;
    g_SessionInfo.current = (g_SessionInfo.current + 1) % g_SessionInfo.sessions[GetIndexForMode(g_SessionInfo.mode)];
    g_Sessions[SessionIndex::INDEX_PREVIOUS] = g_Sessions[SessionIndex::INDEX_CURRENT];
    g_Sessions[SessionIndex::INDEX_CURRENT] = g_Sessions[SessionIndex::INDEX_NEXT];
    Communications::Write(Command::SESSION_INFO);
}

bool CanScrollLeft(void)
{
    if (!g_Settings.continuousScroll && g_SessionInfo.current == 0)
        return false;
    return g_SessionInfo.sessions[GetIndexForMode(g_SessionInfo.mode)] > 1;
}

bool CanScrollRight(void)
{
    if (!g_Settings.continuousScroll && g_SessionInfo.current >= g_SessionInfo.sessions[GetIndexForMode(g_SessionInfo.mode)] - 1)
        return false;
    return g_SessionInfo.sessions[GetIndexForMode(g_SessionInfo.mode)] > 1;
}

uint8_t GetIndexForMode(DisplayMode mode)
{
    if (mode == DisplayMode::MODE_OUTPUT || mode == DisplayMode::MODE_SPLASH) return 0;
    if (mode == DisplayMode::MODE_INPUT) return 1;
    if (mode == DisplayMode::MODE_GAME || mode == DisplayMode::MODE_APPLICATION) return 2;
    if (mode == DisplayMode::MODE_HEALTH) return 0;
    return 0;
}

void ComputeVolumeChange(int8_t index, int8_t encoderSteps, uint32_t deltaTime)
{
    uint8_t prev = g_Sessions[index].data.volume;
    g_Sessions[index].data.volume = ComputeAcceleratedVolume(encoderSteps, deltaTime, prev);
    if (prev != g_Sessions[index].data.volume)
        Communications::Write((Command)((int8_t)Command::VOLUME_CURR_CHANGE + index));
}

bool ProcessEncoderRotation()
{
    int8_t encoderSteps = 0;
    noInterrupts();
    encoderSteps = Input::g_EncoderSteps;
    Input::g_EncoderSteps = 0;
    interrupts();

    if (encoderSteps == 0) return false;

    uint32_t deltaTime = g_Now - g_LastSteps;
    g_LastSteps = g_Now;

    if (g_DisplayAsleep || g_SessionInfo.mode == DisplayMode::MODE_SPLASH ||
        g_SessionInfo.mode == DisplayMode::MODE_HEALTH) return true;

    bool inGameMode = g_SessionInfo.mode == DisplayMode::MODE_GAME;
    if ((inGameMode && g_ModeStates.states[g_SessionInfo.mode] == STATE_GAME_EDIT) || (!inGameMode && g_ModeStates.states[g_SessionInfo.mode] == STATE_EDIT))
    {
        if (!inGameMode) {
            ComputeVolumeChange(SessionIndex::INDEX_CURRENT, encoderSteps, deltaTime);
        } else {
            ComputeVolumeChange(SessionIndex::INDEX_ALTERNATE, encoderSteps, deltaTime);
        }
    }
    else
    {
        if (encoderSteps > 0) NextSession();
        else PreviousSession();
        Display::ResetTimers();
    }
    return true;
}

bool ProcessEncoderButton()
{
    Input::ButtonEvent readButtonEvent = Input::none;
    noInterrupts();
    readButtonEvent = Input::g_ButtonEvent;
    Input::g_ButtonEvent = Input::none;
    interrupts();

    // The first button event while asleep only wakes the display. This also
    // covers double-tap so waking cannot accidentally mute/reset a volume.
    if (readButtonEvent != Input::none && g_DisplayAsleep)
        return true;

    if (readButtonEvent == Input::tap)
    {
        if (g_DisplayAsleep) return true;
        if (g_SessionInfo.mode == DisplayMode::MODE_HEALTH) return true;
        g_ModeStates.states[g_SessionInfo.mode] = (g_ModeStates.states[g_SessionInfo.mode] + 1) % (g_SessionInfo.mode != DisplayMode::MODE_GAME ? STATE_MAX : STATE_GAME_MAX);
        Communications::Write(Command::MODE_STATES);

        // Pressing a browsed Input/Output device selects it as the Windows
        // default, then enters the edit screen. Previously tap only changed
        // screens, so the desktop never received the isDefault request.
        if ((g_SessionInfo.mode == DisplayMode::MODE_OUTPUT ||
             g_SessionInfo.mode == DisplayMode::MODE_INPUT) &&
            g_ModeStates.states[g_SessionInfo.mode] == STATE_EDIT &&
            !g_Sessions[SessionIndex::INDEX_CURRENT].data.isDefault)
        {
            g_Sessions[SessionIndex::INDEX_CURRENT].data.isDefault = true;
            Communications::Write(Command::VOLUME_CURR_CHANGE);
        }

        if (g_SessionInfo.mode == DisplayMode::MODE_GAME && g_ModeStates.states[g_SessionInfo.mode] == STATE_SELECT_B)
        {
            g_Sessions[SessionIndex::INDEX_ALTERNATE] = g_Sessions[SessionIndex::INDEX_CURRENT];
            Communications::Write(Command::ALTERNATE_SESSION);
            NextSession();
        }
        Display::ResetTimers();
        return true;
    }
    else if (readButtonEvent == Input::doubleTap)
    {
        if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH) return false;
        if (g_SessionInfo.mode == DisplayMode::MODE_HEALTH) return true;
        if (g_SessionInfo.mode != DisplayMode::MODE_GAME)
        {
            g_Sessions[SessionIndex::INDEX_CURRENT].data.isMuted = !g_Sessions[SessionIndex::INDEX_CURRENT].data.isMuted;
            Communications::Write(Command::VOLUME_CURR_CHANGE);
        }
        else
        {
            g_Sessions[SessionIndex::INDEX_CURRENT].data.volume = 50;
            g_Sessions[SessionIndex::INDEX_ALTERNATE].data.volume = 50;
            Communications::Write(Command::VOLUME_CURR_CHANGE);
            Communications::Write(Command::VOLUME_ALT_CHANGE);
        }
        return true;
    }
    else if (readButtonEvent == Input::hold)
    {
        if (g_DisplayAsleep) return true;
        if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH) return false;

        g_SessionInfo.mode = (DisplayMode)((g_SessionInfo.mode + 1) % DisplayMode::MODE_MAX);
        if (g_SessionInfo.sessions[GetIndexForMode(g_SessionInfo.mode)] == 0)
            g_SessionInfo.mode = (DisplayMode)((g_SessionInfo.mode + 1) % DisplayMode::MODE_MAX);
        if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
            g_SessionInfo.mode = DisplayMode::MODE_OUTPUT;
        if (g_SessionInfo.mode == DisplayMode::MODE_GAME)
        {
            g_ModeStates.states[DisplayMode::MODE_GAME] = STATE_SELECT_A;
            Communications::Write(Command::MODE_STATES);
        }
        g_SessionInfo.current = 0;
        // Keep the last valid label/volume visible while the desktop resolves
        // and sends the preferred session for the new mode. Clearing here
        // caused a persistent "---" whenever that response was delayed.
        Communications::Write(Command::SESSION_INFO);
        Display::ResetTimers();
        return true;
    }
    return false;
}

bool ProcessTouch()
{
    Input::TouchEvent event = Input::ConsumeTouchEvent();
    if (event == Input::TouchEvent::None)
        return false;

    // The first gesture wakes an idle-sleeping display without changing
    // anything. Host sleep remains authoritative until the PC resumes.
    if (g_DisplayAsleep)
    {
        g_ClockMode = false;
        return true;
    }

    if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
        return true;

    if (g_SessionInfo.mode == DisplayMode::MODE_HEALTH)
    {
        if (event == Input::TouchEvent::LongPress)
            Input::g_ButtonEvent = Input::hold;
        return true;
    }

    if (event == Input::TouchEvent::Tap)
    {
        Input::g_ButtonEvent = Input::tap;
        return true;
    }
    if (event == Input::TouchEvent::DoubleTap)
    {
        Input::g_ButtonEvent = Input::doubleTap;
        return true;
    }
    if (event == Input::TouchEvent::LongPress)
    {
        Input::g_ButtonEvent = Input::hold;
        return true;
    }

    if (event == Input::TouchEvent::SwipeLeft)
    {
        PreviousSession();
        Display::ResetTimers();
        return true;
    }
    if (event == Input::TouchEvent::SwipeRight)
    {
        NextSession();
        Display::ResetTimers();
        return true;
    }

    int8_t delta = event == Input::TouchEvent::SwipeUp
        ? TOUCH_VOLUME_STEP
        : -TOUCH_VOLUME_STEP;
    int8_t index = (g_SessionInfo.mode == DisplayMode::MODE_GAME &&
                    g_ModeStates.states[g_SessionInfo.mode] == STATE_GAME_EDIT)
        ? SessionIndex::INDEX_ALTERNATE
        : SessionIndex::INDEX_CURRENT;

    uint8_t previous = g_Sessions[index].data.volume;
    g_Sessions[index].data.volume = constrain(
        (int16_t)previous + delta,
        0,
        100
    );
    g_LastSteps = g_Now;

    if (previous != g_Sessions[index].data.volume)
        Communications::Write((Command)((int8_t)Command::VOLUME_CURR_CHANGE + index));

    return true;
}

bool RefreshDisplaySleepState()
{
    bool nextState = g_PcAsleep || g_IdleDisplayAsleep;
    bool changed = nextState != g_DisplayAsleep;
    g_DisplayAsleep = nextState;
    return changed;
}

bool ProcessSleep()
{
    // Idle sleep is user-configurable, but host sleep is not. A zero timeout
    // is treated as "no idle timeout" rather than "sleep immediately".
    if (!g_Settings.sleepEnabled ||
        g_Settings.sleepAfterSeconds == 0 ||
        g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
    {
        g_IdleDisplayAsleep = false;
    }
    else
    {
        uint32_t activityTimeDelta = g_Now - g_LastActivity;
        g_IdleDisplayAsleep =
            activityTimeDelta > (uint32_t)g_Settings.sleepAfterSeconds * 1000UL;
    }

    bool changed = RefreshDisplaySleepState();
    if (g_DisplayAsleep)
        g_ClockMode = false;
    return changed;
}

bool ProcessClockStandby()
{
    // Power-off states always take precedence over the decorative clock.
    if (g_DisplayAsleep || g_PcAsleep)
    {
        if (g_ClockMode) {
            g_ClockMode = false;
            return true;
        }
        return false;
    }

    // Clock standby disabled if clockStandbyMinutes == 0 or no time synced
    if (g_Settings.clockStandbyMinutes == 0 || !g_TimeValid)
    {
        if (g_ClockMode) {
            g_ClockMode = false;
            return true;
        }
        return false;
    }

    // Don't show clock in splash mode
    if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
    {
        if (g_ClockMode) {
            g_ClockMode = false;
            return true;
        }
        return false;
    }

    bool lastState = g_ClockMode;
    uint32_t volumeTimeDelta = g_Now - g_LastVolumeActivity;
    uint32_t clockTimeoutMs = (uint32_t)g_Settings.clockStandbyMinutes * 60UL * 1000UL;

    if (volumeTimeDelta > clockTimeoutMs)
        g_ClockMode = true;
    else
        g_ClockMode = false;

    bool stateChanged = (lastState != g_ClockMode);

    if (g_ClockMode) {
        static uint8_t lastSec = 255;
        uint8_t h, m, s;
        GetCurrentTime(h, m, s);
        if (s != lastSec) {
            lastSec = s;
            return true; // Force UI update every second for the clock
        }
    }

    return stateChanged;
}

void GetCurrentTime(uint8_t &h, uint8_t &m, uint8_t &s)
{
    if (!g_TimeValid) {
        h = 0; m = 0; s = 0;
        return;
    }

    // Calculate elapsed seconds since last sync
    uint32_t elapsedMs = g_Now - g_TimeSyncMillis;
    uint32_t elapsedSec = elapsedMs / 1000;

    // Build total seconds from sync time + elapsed
    uint32_t totalSec = (uint32_t)g_TimeData.hour * 3600UL
                      + (uint32_t)g_TimeData.minute * 60UL
                      + (uint32_t)g_TimeData.second
                      + elapsedSec;

    // Wrap at 24 hours
    totalSec %= 86400UL;

    h = totalSec / 3600;
    m = (totalSec % 3600) / 60;
    s = totalSec % 60;
}

bool ProcessDisplayScroll()
{
    return false; // Scrolling disabled for simple TFT UI
}

void UpdateDisplay()
{
    Display::SetMeterLevels(g_MeterData.current, g_MeterData.alternate);

    // Physical display power is resolved before choosing a UI screen. This
    // guarantees that CLOCK/SPLASH/INFO cannot leave the logical state awake
    // while the backlight remains off.
    if (g_DisplayAsleep)
    {
        Display::Sleep();
        return;
    }

    Display::Wake();

    // Clock standby mode — show fullscreen digital clock
    if (g_ClockMode && g_TimeValid)
    {
        uint8_t h, m, s;
        GetCurrentTime(h, m, s);
        Display::ClockScreen(h, m, s);
        return;
    }

    static bool keyTestMode = false;
    if (g_SessionInfo.mode != DisplayMode::MODE_SPLASH) {
        keyTestMode = false;
    }

    if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
    {
        if (!keyTestMode) {
            keyTestMode = Input::LastTouchEvent() != Input::TouchEvent::None;
            for (int i = 0; i < 6; i++) {
                if (Input::g_RawKeyStates[i]) {
                    keyTestMode = true;
                    break;
                }
            }
        }

        if (keyTestMode) {
            Display::KeyTestScreen();
        } else if (g_ModeStates.states[g_SessionInfo.mode] == STATE_LOGO) {
            Display::SplashScreen();
        } else {
            Display::InfoScreen(Input::TouchAvailable());
        }
    }
    else if (g_SessionInfo.mode == DisplayMode::MODE_HEALTH)
    {
        bool pcConnected = !g_PcAsleep &&
            (g_HeartbeatTimeout != 0) &&
            ((int32_t)(g_HeartbeatTimeout - g_Now) > 0);
        uint32_t serialAgeMs = 0;
        if (g_HeartbeatTimeout != 0)
        {
            uint32_t lastSeen = g_HeartbeatTimeout - DEVICE_RESET_AFTER_INACTIVTY;
            serialAgeMs = g_Now - lastSeen;
        }

        Display::HealthScreen(
            pcConnected,
            g_Now / 1000UL,
            serialAgeMs,
            ESP.getFreeHeap(),
            ESP.getMinFreeHeap(),
            ESP.getMaxAllocHeap(),
            Communications::ReceivedFrames(),
            Communications::TransmittedFrames(),
            Communications::CrcErrors(),
            Communications::ProtocolErrors(),
            Communications::LastCommand(),
            Communications::LastErrorCommand(),
            (uint8_t)g_SessionInfo.mode,
            g_SessionInfo.current,
            g_SessionInfo.sessions[0],
            g_SessionInfo.sessions[1],
            g_SessionInfo.sessions[2],
            Input::TouchAvailable(),
            Input::TouchSampleCounter()
        );
    }
    else if (g_SessionInfo.mode == DisplayMode::MODE_INPUT || g_SessionInfo.mode == DisplayMode::MODE_OUTPUT)
    {
        if (g_ModeStates.states[g_SessionInfo.mode] == STATE_NAVIGATE)
            Display::DeviceSelectScreen(&g_Sessions[SessionIndex::INDEX_CURRENT], CanScrollLeft(), CanScrollRight(), g_SessionInfo.mode);
        else
            Display::DeviceEditScreen(&g_Sessions[SessionIndex::INDEX_CURRENT], g_SessionInfo.mode == DisplayMode::MODE_INPUT ? "In" : "Out", g_SessionInfo.mode);
    }
    else if (g_SessionInfo.mode == DisplayMode::MODE_APPLICATION)
    {
        if (g_ModeStates.states[g_SessionInfo.mode] == STATE_NAVIGATE)
            Display::ApplicationSelectScreen(&g_Sessions[SessionIndex::INDEX_CURRENT], CanScrollLeft(), CanScrollRight(), g_SessionInfo.mode);
        else
            Display::ApplicationEditScreen(&g_Sessions[SessionIndex::INDEX_CURRENT], g_SessionInfo.mode);
    }
    else if (g_SessionInfo.mode == DisplayMode::MODE_GAME)
    {
        if (g_ModeStates.states[g_SessionInfo.mode] != STATE_GAME_EDIT)
            Display::GameSelectScreen(&g_Sessions[SessionIndex::INDEX_CURRENT], g_ModeStates.states[g_SessionInfo.mode] == STATE_SELECT_A ? 'A' : 'B', CanScrollLeft(), CanScrollRight(), g_SessionInfo.mode);
        else
            Display::GameEditScreen(&g_Sessions[SessionIndex::INDEX_ALTERNATE], &g_Sessions[SessionIndex::INDEX_CURRENT], g_SessionInfo.mode);
    }
}

// Lighting
enum class LightingRenderMode : uint8_t
{
    STANDBY,
    SPLASH,
    VOLUME,
    VU,
    LED_TEST
};

static_assert(PIXELS_COUNT == 10, "VuNMix LED layouts assume exactly 10 pixels");

static LightingRenderMode s_lightingRenderMode = LightingRenderMode::SPLASH;
static uint8_t s_meterCurrent = 0;
static uint8_t s_meterAlternate = 0;
static bool s_audioActive = false;
static uint32_t s_audioSilenceSince = 0;
static uint32_t s_lastLightingFrameAt = 0;

static constexpr uint8_t LED_AUDIO_ENTER_LEVEL = 3;
static constexpr uint8_t LED_AUDIO_EXIT_LEVEL = 1;
static constexpr uint32_t LED_AUDIO_RELEASE_MS = 600;
static constexpr uint32_t LED_VOLUME_FEEDBACK_MS = 1800;
static constexpr uint16_t LED_ATTACK_UNITS_PER_SEC = 600;
static constexpr uint16_t LED_RELEASE_UNITS_PER_SEC = 180;

static const uint8_t LED_ALL[PIXELS_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
static const uint8_t LED_STEREO_LEFT[5] = {4, 3, 2, 1, 0};
static const uint8_t LED_STEREO_RIGHT[5] = {5, 6, 7, 8, 9};
static const uint8_t LED_GAME_A[5] = {0, 1, 2, 3, 4};
static const uint8_t LED_GAME_B[5] = {5, 6, 7, 8, 9};

static uint8_t PhysicalLed(uint8_t logical)
{
    if (logical >= PIXELS_COUNT)
        return 0;
    return LED_LOGICAL_TO_PHYSICAL[logical];
}

static void SetLogicalPacked(uint8_t logical, uint32_t color)
{
    if (logical >= PIXELS_COUNT)
        return;
    g_Pixels.setPixelColor(PhysicalLed(logical), color);
}

static uint32_t GammaColor(const Color &color, uint8_t intensity = 255)
{
    uint8_t r = (uint16_t)color.r * intensity / 255U;
    uint8_t g = (uint16_t)color.g * intensity / 255U;
    uint8_t b = (uint16_t)color.b * intensity / 255U;
    return g_Pixels.gamma32(g_Pixels.Color(r, g, b));
}

static uint8_t SmoothMeterValue(uint8_t current, uint8_t target, uint32_t deltaMs)
{
    if (current == target)
        return current;

    uint16_t rate = target > current
        ? LED_ATTACK_UNITS_PER_SEC
        : LED_RELEASE_UNITS_PER_SEC;
    uint16_t step = max<uint16_t>(1, (uint32_t)rate * max<uint32_t>(1, deltaMs) / 1000U);

    if (target > current)
        return (uint8_t)min<uint16_t>(target, current + step);
    return (uint8_t)max<int16_t>(target, (int16_t)current - (int16_t)step);
}

static void UpdateMeterSmoothing(uint32_t deltaMs)
{
    s_meterCurrent = SmoothMeterValue(
        s_meterCurrent,
        min<uint8_t>(100, g_MeterData.current),
        deltaMs
    );
    s_meterAlternate = SmoothMeterValue(
        s_meterAlternate,
        min<uint8_t>(100, g_MeterData.alternate),
        deltaMs
    );
}

static void UpdateAudioActivity()
{
    uint8_t rawPeak = max(g_MeterData.current, g_MeterData.alternate);

    if (rawPeak >= LED_AUDIO_ENTER_LEVEL)
    {
        s_audioActive = true;
        s_audioSilenceSince = 0;
        return;
    }

    if (!s_audioActive || rawPeak > LED_AUDIO_EXIT_LEVEL)
        return;

    if (s_audioSilenceSince == 0)
    {
        s_audioSilenceSince = g_Now;
        return;
    }

    if ((uint32_t)(g_Now - s_audioSilenceSince) >= LED_AUDIO_RELEASE_MS)
    {
        s_audioActive = false;
        s_audioSilenceSince = 0;
    }
}

static LightingRenderMode SelectLightingMode()
{
    // Diagnostic mode is intentionally visible immediately instead of only
    // while sleeping, so PCB LED order can be verified from Settings.
    if (g_Settings.standbyLedMode == 16)
        return LightingRenderMode::LED_TEST;

    if (g_DisplayAsleep)
        return LightingRenderMode::STANDBY;

    if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
        return LightingRenderMode::SPLASH;

    if ((uint32_t)(g_Now - g_LastVolumeActivity) < LED_VOLUME_FEEDBACK_MS)
        return LightingRenderMode::VOLUME;

    return s_audioActive ? LightingRenderMode::VU : LightingRenderMode::VOLUME;
}

void UpdateLighting()
{
    uint32_t deltaMs = s_lastLightingFrameAt == 0
        ? LED_FRAME_INTERVAL_MS
        : (uint32_t)(g_Now - s_lastLightingFrameAt);
    s_lastLightingFrameAt = g_Now;

    UpdateMeterSmoothing(deltaMs);
    UpdateAudioActivity();

    LightingRenderMode nextMode = SelectLightingMode();
    if (nextMode != s_lightingRenderMode)
    {
        // Effects such as meteor/twinkle use the previous pixel buffer as
        // history. Clear it when changing semantic modes so stale volume bars
        // never bleed into a standby animation.
        g_Pixels.clear();
        s_lightingRenderMode = nextMode;
    }

    switch (s_lightingRenderMode)
    {
        case LightingRenderMode::LED_TEST:
            LightingLedTest();
            break;

        case LightingRenderMode::STANDBY:
            LightingStandby();
            break;

        case LightingRenderMode::SPLASH:
            LightingColorWave();
            break;

        case LightingRenderMode::VU:
            if (g_SessionInfo.mode == DisplayMode::MODE_GAME)
            {
                // Game UI defines A=alternate (left) and B=current (right).
                LightingGameVU(s_meterAlternate, s_meterCurrent);
            }
            else
            {
                // Non-game modes carry stereo as current=left, alternate=right.
                LightingAudioVU(s_meterCurrent, s_meterAlternate);
            }
            break;

        case LightingRenderMode::VOLUME:
        default:
            if (g_SessionInfo.mode == DisplayMode::MODE_GAME)
                LightingGameVolume();
            else
                LightingVolume(
                    &g_Sessions[SessionIndex::INDEX_CURRENT],
                    &g_Settings.volumeMinColor,
                    &g_Settings.volumeMaxColor
                );
            break;
    }

    g_Pixels.show();
}

void LightingBlackOut()
{
    g_Pixels.clear();
}

// ─── Standby LED Mode Dispatcher ─────────────────────────────────────────
void LightingStandby()
{
    switch (g_Settings.standbyLedMode)
    {
        case 0:  LightingColorWave();     break;
        case 1:  LightingRainbow();       break;
        case 2:  LightingMeteor();        break;
        case 3:  LightingTwinkle();       break;
        case 4:  LightingBreathe();       break;
        case 5:  LightingConfetti();      break;
        case 6:  LightingFire();          break;
        case 7:  LightingOcean();         break;
        case 8:  LightingLava();          break;
        case 9:  LightingScanner();       break;
        case 10: LightingTheaterChase();  break;
        case 11: LightingRunningLights(); break;
        case 12: LightingGradient();      break;
        case 13: LightingSparkle();       break;
        case 14: LightingAurora();        break;
        case 15: LightingBlackOut();      break;
        case 16: LightingLedTest();       break;
        default: LightingColorWave();     break;
    }
}

void LightingLedTest()
{
    g_Pixels.clear();
    uint8_t logical = (g_Now / 500U) % PIXELS_COUNT;
    SetLogicalPacked(logical, g_Pixels.gamma32(g_Pixels.Color(255, 255, 255)));
}

void LightingColorWave()
{
    static uint8_t fxHue = 0;
    fxHue += 2;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t phase = fxHue + i * (256 / PIXELS_COUNT);
        uint8_t bright = g_Pixels.sine8(phase);
        uint8_t pixelHue8 = fxHue + i * (255 / PIXELS_COUNT);
        uint16_t pixelHue16 = (uint16_t)pixelHue8 * 256U;
        uint32_t color = g_Pixels.ColorHSV(pixelHue16, 255, bright);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

// ─── Rainbow — full-spectrum rotating hue ────────────────────────────────
void LightingRainbow()
{
    static uint8_t fxHue = 0;
    fxHue += 2;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t pixelHue8 = fxHue + i * (255 / PIXELS_COUNT);
        uint16_t pixelHue16 = (uint16_t)pixelHue8 * 256U;
        uint32_t color = g_Pixels.ColorHSV(pixelHue16, 255, 200);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

// ─── Meteor — shooting star with fading tail ─────────────────────────────
void LightingMeteor()
{
    static uint8_t fxHue = 0;
    static uint8_t fxPos = 0;
    static uint8_t frameCount = 0;

    if (++frameCount < 2)
        return;
    frameCount = 0;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        if (random(256) < 100)
        {
            uint32_t color = g_Pixels.getPixelColor(i);
            uint8_t r = ((color >> 16) & 0xFF) * 176 / 256;
            uint8_t g = ((color >> 8) & 0xFF) * 176 / 256;
            uint8_t b = (color & 0xFF) * 176 / 256;
            g_Pixels.setPixelColor(i, r, g, b);
        }
    }

    if (fxPos < PIXELS_COUNT)
    {
        uint16_t hue16 = (uint16_t)fxHue * 256U;
        uint32_t color = g_Pixels.ColorHSV(hue16, 200, 255);
        g_Pixels.setPixelColor(fxPos, g_Pixels.gamma32(color));
    }

    if (++fxPos >= PIXELS_COUNT + 5)
    {
        fxPos = 0;
        fxHue += 45;
    }
}

// ─── Twinkle — random pixels flash and fade ──────────────────────────────
void LightingTwinkle()
{
    static uint8_t frameCount = 0;
    if (++frameCount < 2)
        return;
    frameCount = 0;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint32_t color = g_Pixels.getPixelColor(i);
        uint8_t r = ((color >> 16) & 0xFF) * 230 / 256;
        uint8_t g = ((color >> 8) & 0xFF) * 230 / 256;
        uint8_t b = (color & 0xFF) * 230 / 256;
        g_Pixels.setPixelColor(i, r, g, b);
    }

    uint8_t idx = random(PIXELS_COUNT);
    uint16_t hue16 = (uint16_t)random(256) * 256U;
    uint32_t color = g_Pixels.ColorHSV(hue16, 200, 255);
    g_Pixels.setPixelColor(idx, g_Pixels.gamma32(color));
}

// ─── Breathe — smooth sine breathing with color shift ────────────────────
void LightingBreathe()
{
    static uint8_t fxHue = 0;
    static uint8_t breathePhase = 0;

    uint8_t sinVal = g_Pixels.sine8(breathePhase);
    uint8_t bright = 10 + (uint16_t)sinVal * 210 / 255;
    uint16_t hue16 = (uint16_t)fxHue * 256U;
    uint32_t color = g_Pixels.gamma32(g_Pixels.ColorHSV(hue16, 255, bright));

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
        g_Pixels.setPixelColor(i, color);

    breathePhase += 1;
    if (breathePhase < 1)
        fxHue += 30;
}

// ─── Confetti — random colored sparkles with slow fade ───────────────────
void LightingConfetti()
{
    static uint8_t fxHue = 0;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint32_t color = g_Pixels.getPixelColor(i);
        uint8_t r = ((color >> 16) & 0xFF) * 240 / 256;
        uint8_t g = ((color >> 8) & 0xFF) * 240 / 256;
        uint8_t b = (color & 0xFF) * 240 / 256;
        g_Pixels.setPixelColor(i, r, g, b);
    }

    uint8_t idx = random(PIXELS_COUNT);
    uint16_t hue16 = (uint16_t)(fxHue + random(64)) * 256U;
    uint32_t color = g_Pixels.gamma32(g_Pixels.ColorHSV(hue16, 220, 255));
    uint32_t existing = g_Pixels.getPixelColor(idx);
    uint8_t er = (existing >> 16) & 0xFF;
    uint8_t eg = (existing >> 8) & 0xFF;
    uint8_t eb = existing & 0xFF;
    uint8_t nr = (color >> 16) & 0xFF;
    uint8_t ng = (color >> 8) & 0xFF;
    uint8_t nb = color & 0xFF;
    g_Pixels.setPixelColor(
        idx,
        min(255, (int)er + nr),
        min(255, (int)eg + ng),
        min(255, (int)eb + nb)
    );
    fxHue++;
}

// ─── Fire — WLED-style fire simulation (heat palette) ────────────────────
void LightingFire()
{
    static uint8_t heat[PIXELS_COUNT] = {0};

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t cooldown = random(0, ((55 * 10) / PIXELS_COUNT) + 2);
        heat[i] = heat[i] > cooldown ? heat[i] - cooldown : 0;
    }

    for (uint8_t k = PIXELS_COUNT - 1; k >= 2; k--)
        heat[k] = (heat[k - 1] + heat[k - 2] + heat[k - 2]) / 3;

    if (random(256) < 120)
    {
        uint8_t y = random(2);
        heat[y] = min(255, (int)heat[y] + (int)random(160, 255));
    }

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t t192 = (uint16_t)heat[i] * 191 / 255;
        uint8_t r;
        uint8_t g;
        uint8_t b;
        if (t192 < 64)
        {
            r = t192 * 4;
            g = 0;
            b = 0;
        }
        else if (t192 < 128)
        {
            r = 255;
            g = (t192 - 64) * 4;
            b = 0;
        }
        else
        {
            r = 255;
            g = 255;
            b = (t192 - 128) * 4;
        }
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(g_Pixels.Color(r, g, b)));
    }
}

// ─── Ocean — blue/cyan/teal wave ─────────────────────────────────────────
void LightingOcean()
{
    static uint8_t fxPhase = 0;
    fxPhase += 1;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t wave1 = g_Pixels.sine8(fxPhase + i * 30);
        uint8_t wave2 = g_Pixels.sine8(fxPhase * 2 + i * 50);
        uint8_t bright = (wave1 + wave2) / 2;
        uint8_t r = bright / 8;
        uint8_t g = bright / 3;
        uint8_t b = bright;
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(g_Pixels.Color(r, g, b)));
    }
}

// ─── Lava — red/orange flowing heat ──────────────────────────────────────
void LightingLava()
{
    static uint8_t fxPhase = 0;
    fxPhase += 2;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t wave1 = g_Pixels.sine8(fxPhase + i * 35);
        uint8_t wave2 = g_Pixels.sine8(fxPhase * 3 / 2 + i * 55);
        uint8_t heat = (wave1 + wave2) / 2;
        uint8_t r = heat;
        uint8_t g = heat > 128 ? (heat - 128) * 2 : 0;
        uint8_t b = heat > 200 ? min(255, (int)(heat - 200) * 4) : 0;
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(g_Pixels.Color(r, g, b)));
    }
}

// ─── Scanner — Knight Rider / Larson scanner ─────────────────────────────
void LightingScanner()
{
    static uint8_t fxPos = 0;
    static int8_t fxDir = 1;
    static uint8_t fxHue = 0;
    static uint8_t frameCount = 0;

    if (++frameCount < 2)
        return;
    frameCount = 0;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint32_t color = g_Pixels.getPixelColor(i);
        uint8_t r = ((color >> 16) & 0xFF) * 200 / 256;
        uint8_t g = ((color >> 8) & 0xFF) * 200 / 256;
        uint8_t b = (color & 0xFF) * 200 / 256;
        g_Pixels.setPixelColor(i, r, g, b);
    }

    uint16_t hue16 = (uint16_t)fxHue * 256U;
    uint32_t color = g_Pixels.ColorHSV(hue16, 255, 255);
    g_Pixels.setPixelColor(fxPos, g_Pixels.gamma32(color));

    fxPos += fxDir;
    if (fxPos >= PIXELS_COUNT - 1)
    {
        fxDir = -1;
        fxHue += 20;
    }
    if (fxPos == 0)
    {
        fxDir = 1;
        fxHue += 20;
    }
}

// ─── Theater Chase — classic marquee chase ───────────────────────────────
void LightingTheaterChase()
{
    static uint8_t fxStep = 0;
    static uint8_t fxHue = 0;
    static uint8_t frameCount = 0;

    if (++frameCount < 3)
        return;
    frameCount = 0;

    g_Pixels.clear();
    for (uint8_t i = fxStep; i < PIXELS_COUNT; i += 3)
    {
        uint16_t hue16 = (uint16_t)(fxHue + i * 25) * 256U;
        uint32_t color = g_Pixels.ColorHSV(hue16, 255, 200);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
    fxStep = (fxStep + 1) % 3;
    fxHue += 4;
}

// ─── Running Lights — sinusoidal brightness wave ─────────────────────────
void LightingRunningLights()
{
    static uint8_t fxPhase = 0;
    static uint8_t fxHue = 0;
    fxPhase += 2;
    fxHue += 1;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t bright = g_Pixels.sine8(fxPhase + i * (256 / PIXELS_COUNT));
        uint16_t hue16 = (uint16_t)fxHue * 256U;
        uint32_t color = g_Pixels.ColorHSV(hue16, 255, bright);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

// ─── Gradient — smooth rotating dual-color gradient ──────────────────────
void LightingGradient()
{
    static uint8_t fxHue = 0;
    fxHue += 1;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t ratio = i * 255 / (PIXELS_COUNT - 1);
        uint8_t hue = fxHue + ratio / 2;
        uint16_t hue16 = (uint16_t)hue * 256U;
        uint32_t color = g_Pixels.ColorHSV(hue16, 255, 180);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

// ─── Sparkle — random white flashes on dark ──────────────────────────────
void LightingSparkle()
{
    static uint8_t frameCount = 0;
    if (++frameCount < 3)
        return;
    frameCount = 0;

    g_Pixels.clear();
    uint8_t idx = random(PIXELS_COUNT);
    g_Pixels.setPixelColor(
        idx,
        g_Pixels.gamma32(g_Pixels.Color(255, 255, 255))
    );
}

// ─── Aurora — slow shifting green/purple/blue northern lights ────────────
void LightingAurora()
{
    static uint8_t fxPhase = 0;
    fxPhase += 1;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t wave1 = g_Pixels.sine8(fxPhase * 2 + i * 40);
        uint8_t wave2 = g_Pixels.sine8(fxPhase * 3 + i * 60 + 128);
        uint8_t bright = (wave1 + wave2) / 3;
        uint8_t hue8 = 85 + g_Pixels.sine8(fxPhase + i * 30) / 4;
        uint16_t hue16 = (uint16_t)hue8 * 256U;
        uint32_t color = g_Pixels.ColorHSV(hue16, 200, bright);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

Color LerpColor(Color *c1, Color *c2, uint8_t coeff)
{
    uint8_t r = c1->r + ((int)(c2->r - c1->r) * coeff) / 255;
    uint8_t g = c1->g + ((int)(c2->g - c1->g) * coeff) / 255;
    uint8_t b = c1->b + ((int)(c2->b - c1->b) * coeff) / 255;
    return {r, g, b};
}

static void RenderVolumeBar(
    SessionData *item,
    Color *startColor,
    Color *endColor,
    const uint8_t *logicalPixels,
    uint8_t count)
{
    if (count == 0)
        return;

    if (item->data.isMuted)
    {
        const uint32_t period = 450;
        uint32_t phase = g_Now % (2U * period);
        uint32_t triangle = phase <= period ? phase : (2U * period - phase);
        uint8_t intensity = 32 + (uint32_t)triangle * 223U / period;
        Color pulseColor = *endColor;
        uint32_t packed = GammaColor(pulseColor, intensity);
        for (uint8_t i = 0; i < count; i++)
            SetLogicalPacked(logicalPixels[i], packed);
        return;
    }

    uint8_t volume = min<uint8_t>(100, item->data.volume);
    uint16_t units = (uint16_t)volume * count;
    uint8_t fullPixels = units / 100U;
    uint8_t remainder = units % 100U;

    for (uint8_t i = 0; i < count; i++)
    {
        uint8_t intensity = 0;
        if (i < fullPixels)
            intensity = 255;
        else if (i == fullPixels && fullPixels < count && remainder > 0)
            intensity = (uint16_t)remainder * 255U / 100U;

        uint8_t blend = count <= 1
            ? 0
            : (uint16_t)i * 255U / (count - 1);
        Color color = LerpColor(startColor, endColor, blend);
        SetLogicalPacked(logicalPixels[i], GammaColor(color, intensity));
    }
}

void LightingVolume(SessionData *item, Color *c1, Color *c2)
{
    g_Pixels.clear();
    RenderVolumeBar(item, c1, c2, LED_ALL, PIXELS_COUNT);
}

void LightingGameVolume()
{
    g_Pixels.clear();

    // DisplayGameLifecycle defines alternate as GAME/A and current as VOICE/B.
    RenderVolumeBar(
        &g_Sessions[SessionIndex::INDEX_ALTERNATE],
        &g_Settings.mixChannelAColor,
        &g_Settings.mixChannelAColor,
        LED_GAME_A,
        5
    );
    RenderVolumeBar(
        &g_Sessions[SessionIndex::INDEX_CURRENT],
        &g_Settings.mixChannelBColor,
        &g_Settings.mixChannelBColor,
        LED_GAME_B,
        5
    );
}

static void RenderVuGradientChannel(
    uint8_t level,
    const uint8_t *logicalPixels,
    uint8_t count)
{
    uint16_t units = (uint16_t)min<uint8_t>(100, level) * count;
    uint8_t fullPixels = units / 100U;
    uint8_t remainder = units % 100U;

    for (uint8_t i = 0; i < count; i++)
    {
        uint8_t intensity = 0;
        if (i < fullPixels)
            intensity = 255;
        else if (i == fullPixels && fullPixels < count && remainder > 0)
            intensity = (uint16_t)remainder * 255U / 100U;

        // Safe green -> yellow -> red gradient; never underflows uint16_t.
        uint16_t hue16 = count <= 1
            ? 0
            : (uint32_t)21845U * (count - 1U - i) / (count - 1U);
        uint32_t color = g_Pixels.ColorHSV(hue16, 255, intensity);
        SetLogicalPacked(logicalPixels[i], g_Pixels.gamma32(color));
    }
}

static void RenderVuColorChannel(
    uint8_t level,
    Color *color,
    const uint8_t *logicalPixels,
    uint8_t count)
{
    uint16_t units = (uint16_t)min<uint8_t>(100, level) * count;
    uint8_t fullPixels = units / 100U;
    uint8_t remainder = units % 100U;

    for (uint8_t i = 0; i < count; i++)
    {
        uint8_t intensity = 0;
        if (i < fullPixels)
            intensity = 255;
        else if (i == fullPixels && fullPixels < count && remainder > 0)
            intensity = (uint16_t)remainder * 255U / 100U;

        SetLogicalPacked(logicalPixels[i], GammaColor(*color, intensity));
    }
}

// ─── Stereo VU: 5 LEDs left + 5 LEDs right, growing from center outward ──
void LightingAudioVU(uint8_t levelL, uint8_t levelR)
{
    g_Pixels.clear();
    RenderVuGradientChannel(levelL, LED_STEREO_LEFT, 5);
    RenderVuGradientChannel(levelR, LED_STEREO_RIGHT, 5);
}

// ─── Game VU: independent A/Game and B/Voice channels ────────────────────
void LightingGameVU(uint8_t levelGame, uint8_t levelVoice)
{
    g_Pixels.clear();
    RenderVuColorChannel(levelGame, &g_Settings.mixChannelAColor, LED_GAME_A, 5);
    RenderVuColorChannel(levelVoice, &g_Settings.mixChannelBColor, LED_GAME_B, 5);
}
