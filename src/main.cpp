#include <Arduino.h>

#include "Config.h"
#include "Display.h"
#include "VideoPlayer.h"
#include "Communications.h"
#include "Input.h"
#include <Adafruit_NeoPixel.h>

//********************************************************
// *** VARIABLES
//*******************************************************
// State
DeviceSettings g_Settings;
SessionInfo g_SessionInfo;
SessionData g_Sessions[SessionIndex::INDEX_MAX];
ModeStates g_ModeStates;
uint8_t g_DisplayDirty;
bool g_DisplayAsleep;

// Time & Sleep
uint32_t g_Now;
uint32_t g_HeartbeatTimeout;
uint32_t g_LastActivity;
uint32_t g_NextPixelUpdate;
uint32_t g_LastSteps;

// Lighting
Adafruit_NeoPixel g_Pixels(PIXELS_COUNT, PIN_PIXELS, NEO_GRB + NEO_KHZ800);

void ResetState();
bool CanScrollLeft();
bool CanScrollRight();
uint8_t GetIndexForMode(DisplayMode mode);
bool ProcessEncoderRotation();
bool ProcessEncoderButton();
bool ProcessSleep();
bool ProcessDisplayScroll();
void UpdateDisplay();
void UpdateLighting();
void LightingSleep();
void LightingColorWave();
void LightingVolume(SessionData *item, Color *c1, Color *c2);
Color LerpColor(Color *c1, Color *c2, uint8_t coeff);

//---------------------------------------------------------
void setup()
{
    Serial.begin(115200);
    delay(2000); // Give USB CDC time to enumerate
    Serial.println("\n\n--- MAXMIX BOOT START ---");
    Serial.flush();

    Serial.println("ResetState()...");
    ResetState();

    Serial.println("Input::Initialize()...");
    Input::Initialize();

    Serial.println("Playing Intro Video...");
    VideoPlayer::Play("/intro.avi");

    Serial.println("Display::Initialize()...");
    Serial.flush();
    Display::Initialize();

    Serial.println("Communications::Initialize()...");
    Communications::Initialize();

    Serial.println("Pixels Init (10 LEDs on GPIO 45)...");
    Serial.flush();
    g_Pixels.begin();
    g_Pixels.setBrightness(PIXELS_BRIGHTNESS);
    g_Pixels.clear();
    g_Pixels.show();
    delay(50); // Let NeoPixel latch

    g_LastActivity = millis();
    g_Now = millis();
    
    Serial.println("--- SETUP COMPLETE ---");
    Serial.flush();
    Display::SplashScreen();
}

//---------------------------------------------------------
void loop()
{
    uint32_t last = g_Now;
    g_Now = millis();

    Input::Update();

    Command command = Communications::Read();
    g_DisplayDirty = (command != Command::NONE && command != Command::ERROR);
    if (command == Command::CURRENT_SESSION || command == Command::ALTERNATE_SESSION ||
        command == Command::VOLUME_CURR_CHANGE || command == Command::VOLUME_ALT_CHANGE)
    {
        g_LastActivity = g_Now;
        g_DisplayDirty = true;
    }

    // Drain any device-initiated messages (queued by Write()) AFTER Read()'s OK response
    Communications::SendPending();

    if (ProcessEncoderRotation())
    {
        g_LastActivity = g_Now;
        g_DisplayDirty = true;
    }

    if (ProcessEncoderButton())
    {
        g_LastActivity = g_Now;
        g_DisplayDirty = true;
    }

    if (ProcessSleep())
    {
        g_DisplayDirty = true;
    }

    if (g_DisplayDirty || ProcessDisplayScroll())
    {
        UpdateDisplay();
    }

    Display::Update();
    Display::UpdateTimers(g_Now - last);
    g_DisplayDirty = false;

    // Update Lighting at 30Hz
    if (g_Now - g_NextPixelUpdate < 0x80000000U)
    {
        g_NextPixelUpdate = g_Now + 33;
        UpdateLighting();
    }

    // Reset / Disconnect if no serial activity.
    if ((g_SessionInfo.mode != DisplayMode::MODE_SPLASH) && (g_Now - g_HeartbeatTimeout < 0x80000000U))
        ResetState();
}

//---------------------------------------------------------
void ResetState()
{
    // State
    g_Settings = DeviceSettings();
    g_SessionInfo = SessionInfo();
    g_Sessions[SessionIndex::INDEX_PREVIOUS] = SessionData();
    g_Sessions[SessionIndex::INDEX_CURRENT] = SessionData();
    g_Sessions[SessionIndex::INDEX_ALTERNATE] = SessionData();
    g_Sessions[SessionIndex::INDEX_NEXT] = SessionData();
    g_ModeStates = ModeStates();
    g_DisplayDirty = true;
    g_DisplayAsleep = false;

    // Time & Sleep
    g_Now = millis();
    g_HeartbeatTimeout = 0;
    g_LastActivity = g_Now;
    g_NextPixelUpdate = 0;
    g_LastSteps = 0;
}

// Volume processing
int8_t g_PreviousSteps = 0;
int8_t ComputeAcceleratedVolume(int8_t encoderDelta, uint32_t deltaTime, int16_t volume)
{
    if (encoderDelta == 0) return volume;
    // Removed FixedPoints logic, just simple multiplication
    int16_t step = abs(encoderDelta);
    if (step < 1) step = 1;
    if (encoderDelta > 0) volume += step;
    else volume -= step;
    
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

    if (g_DisplayAsleep || g_SessionInfo.mode == DisplayMode::MODE_SPLASH) return true;

    bool inGameMode = g_SessionInfo.mode == DisplayMode::MODE_GAME;
    if ((inGameMode && g_ModeStates.states[g_SessionInfo.mode] == STATE_GAME_EDIT) || (!inGameMode && g_ModeStates.states[g_SessionInfo.mode] == STATE_EDIT))
    {
        if (!inGameMode) {
            ComputeVolumeChange(SessionIndex::INDEX_CURRENT, encoderSteps, deltaTime);
        } else {
            ComputeVolumeChange(SessionIndex::INDEX_ALTERNATE, encoderSteps, deltaTime);
            if (g_Sessions[SessionIndex::INDEX_ALTERNATE].data.id != g_Sessions[SessionIndex::INDEX_CURRENT].data.id) {
                uint8_t prev = g_Sessions[SessionIndex::INDEX_CURRENT].data.volume;
                g_Sessions[SessionIndex::INDEX_CURRENT].data.volume = 100 - g_Sessions[SessionIndex::INDEX_ALTERNATE].data.volume;
                if (prev != g_Sessions[SessionIndex::INDEX_CURRENT].data.volume)
                    Communications::Write(Command::VOLUME_CURR_CHANGE);
            } else {
                g_Sessions[SessionIndex::INDEX_CURRENT].data.volume = g_Sessions[SessionIndex::INDEX_ALTERNATE].data.volume;
            }
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

    if (readButtonEvent == Input::tap)
    {
        if (g_DisplayAsleep) return true;
        g_ModeStates.states[g_SessionInfo.mode] = (g_ModeStates.states[g_SessionInfo.mode] + 1) % (g_SessionInfo.mode != DisplayMode::MODE_GAME ? STATE_MAX : STATE_GAME_MAX);
        Communications::Write(Command::MODE_STATES);

        if (g_SessionInfo.mode == DisplayMode::MODE_INPUT || g_SessionInfo.mode == DisplayMode::MODE_OUTPUT)
        {
            for (uint8_t i = 0; i < SessionIndex::INDEX_MAX; i++) g_Sessions[i].data.isDefault = false;
            g_Sessions[SessionIndex::INDEX_CURRENT].data.isDefault = true;
            Communications::Write(Command::VOLUME_CURR_CHANGE);
        }
        else if (g_SessionInfo.mode == DisplayMode::MODE_GAME && g_ModeStates.states[g_SessionInfo.mode] == STATE_SELECT_B)
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
        memset(g_Sessions[SessionIndex::INDEX_CURRENT].name, 0, sizeof(g_Sessions[SessionIndex::INDEX_CURRENT].name));
        Communications::Write(Command::SESSION_INFO);
        Display::ResetTimers();
        return true;
    }
    return false;
}

bool ProcessSleep()
{
    if (g_Settings.sleepAfterSeconds == 0)
    {
        g_DisplayAsleep = false;
        return false;
    }

    // Don't sleep while in splash/waiting mode (no PC connected yet)
    if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
    {
        if (g_DisplayAsleep)
        {
            g_DisplayAsleep = false;
            return true; // state changed, need redraw
        }
        return false;
    }

    bool lastState = g_DisplayAsleep;
    uint32_t activityTimeDelta = g_Now - g_LastActivity;
    if (activityTimeDelta > (uint32_t)g_Settings.sleepAfterSeconds * 1000)
        g_DisplayAsleep = true;
    else
        g_DisplayAsleep = false;

    return lastState != g_DisplayAsleep;
}

bool ProcessDisplayScroll()
{
    return false; // Scrolling disabled for simple TFT UI
}

void UpdateDisplay()
{
    if (g_DisplayAsleep)
    {
        Display::Sleep();
        return;
    }

    if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH)
    {
        if (g_ModeStates.states[g_SessionInfo.mode] == STATE_LOGO)
            Display::SplashScreen();
        else
            Display::InfoScreen();
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
void UpdateLighting()
{
    if (g_DisplayAsleep) LightingSleep();
    else if (g_SessionInfo.mode == DisplayMode::MODE_SPLASH) LightingColorWave();
    else if (g_SessionInfo.mode == DisplayMode::MODE_GAME)
        LightingVolume(&g_Sessions[SessionIndex::INDEX_CURRENT], &g_Settings.mixChannelAColor, &g_Settings.mixChannelBColor);
    else LightingVolume(&g_Sessions[SessionIndex::INDEX_CURRENT], &g_Settings.volumeMinColor, &g_Settings.volumeMaxColor);
    g_Pixels.show();
}

void LightingBlackOut() { g_Pixels.clear(); }

void LightingSleep()
{
    static uint8_t fxHue = 0;
    fxHue += 2; // Slower wave for sleep mode

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        uint8_t phase = fxHue + i * (256 / PIXELS_COUNT);
        uint8_t bright = g_Pixels.sine8(phase) / 2; // 50% brightness
        
        uint8_t pixelHue8 = fxHue + i * (255 / PIXELS_COUNT);
        uint16_t pixelHue16 = pixelHue8 * 256;
        
        uint32_t color = g_Pixels.ColorHSV(pixelHue16, 255, bright);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

void LightingColorWave()
{
    // Mô phỏng chính xác thuật toán ColorWave (FastLED) từ 's3 test led'
    static uint8_t fxHue = 0;
    
    // UpdateLighting() trong VuNMix được gọi mỗi 33ms.
    // Nguyên bản (FastLED): cộng 3 mỗi 20ms (~150 đơn vị/giây)
    // Để giữ nguyên tốc độ, ta cộng 5 mỗi 33ms (~150 đơn vị/giây)
    fxHue += 5;

    for (uint8_t i = 0; i < PIXELS_COUNT; i++)
    {
        // Tính phase giống hệt thuật toán: fxHue + i * (256 / NUM_LEDS)
        uint8_t phase = fxHue + i * (256 / PIXELS_COUNT);
        uint8_t bright = g_Pixels.sine8(phase); // sine8 của NeoPixel trả về 0-255
        
        // Tính màu pixelHue (0-255) giống hệt FastLED
        uint8_t pixelHue8 = fxHue + i * (255 / PIXELS_COUNT);
        
        // Chuyển Hue (0-255) sang chuẩn Adafruit_NeoPixel (0-65535)
        uint16_t pixelHue16 = pixelHue8 * 256;
        
        uint32_t color = g_Pixels.ColorHSV(pixelHue16, 255, bright);
        g_Pixels.setPixelColor(i, g_Pixels.gamma32(color));
    }
}

void LightingVolume(SessionData *item, Color *c1, Color *c2)
{
    if (!item->data.isMuted)
    {
        uint32_t volAcc = ((uint32_t)item->data.volume * 255 * PIXELS_COUNT) / 100;
        for (int i = 0; i < PIXELS_COUNT; i++)
        {
            uint32_t amp = min(volAcc, (uint32_t)255);
            if(volAcc >= amp) volAcc -= amp;
            else volAcc = 0;
            Color c = LerpColor(c1, c2, amp);
            g_Pixels.setPixelColor(i, c.r, c.g, c.b);
        }
    }
    else
    {
        int32_t t = millis();
        int32_t period = 500;
        uint8_t amp = (period - abs(t % (2 * period) - period)) * 255 / period;
        Color c = LerpColor(c1, c2, amp);
        uint32_t color32 = ((uint32_t)c.r << 16) | ((uint32_t)c.g << 8) | (uint32_t)c.b;
        g_Pixels.fill(color32);
    }
}

Color LerpColor(Color *c1, Color *c2, uint8_t coeff)
{
    uint8_t r = c1->r + ((int)(c2->r - c1->r) * coeff) / 255;
    uint8_t g = c1->g + ((int)(c2->g - c1->g) * coeff) / 255;
    uint8_t b = c1->b + ((int)(c2->b - c1->b) * coeff) / 255;
    return {r, g, b};
}