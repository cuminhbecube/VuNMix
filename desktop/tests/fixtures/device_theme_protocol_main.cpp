#include "Communications.cpp"
#include "DeviceThemeControl.h"
#include <cstdlib>

ThemeTestSerial Serial;
DeviceSettings g_Settings;
SessionInfo g_SessionInfo;
SessionData g_Sessions[4];
ModeStates g_ModeStates;
MeterData g_MeterData;
uint32_t g_HeartbeatTimeout = 0, g_Now = 10000, g_LastSteps = 0;
TimeData g_TimeData;
uint32_t g_TimeSyncMillis = 0;
bool g_TimeValid = false;
PcStatsData g_PcStats;
bool g_PcStatsValid = false;
MediaInfoData g_MediaInfo;
bool g_MediaInfoValid = false;
namespace Display {
    void ReceiveAppIconMeta(const AppIconMeta*) {}
    void ReceiveAppIconChunk(const AppIconChunk*) {}
}

using DeviceThemeProtocol::Request;
using DeviceThemeProtocol::Status;
static uint8_t selectedTheme = 2;
static unsigned writes = 0, selections = 0;
static bool failPersist = false;
static bool selectTheme(uint8_t theme) { ++selections; selectedTheme = theme; return true; }
static bool persistTheme(uint8_t) { ++writes; return !failPersist; }

static void controlChecks() {
    for (unsigned clock = 0; clock < 16; ++clock) {
        g_Settings.clockStyle = clock & 7;
        g_Settings.clockStyleHigh = (clock >> 3) & 1;
        const DeviceSettings before = g_Settings;
        for (unsigned deferred = 0; deferred < 2; ++deferred) {
            for (unsigned theme = 0; theme < 8; ++theme) {
                selectedTheme = 2; writes = selections = 0;
                const Request request = {1, static_cast<uint8_t>(theme), 0x1234};
                const auto result = DeviceThemeControl::Prepare(
                    request, selectedTheme, deferred, selectTheme, persistTheme);
                assert(result.status == (deferred ? Status::SAVED_DEFERRED : Status::APPLIED));
                assert(result.render == (!deferred && theme != 2));
                assert(selectedTheme == theme);
                assert(writes == (theme != 2 ? 1U : 0U));
                assert(selections == writes);
                assert(memcmp(&before, &g_Settings, sizeof(before)) == 0);
            }
        }
    }
    selectedTheme = 2; writes = selections = 0;
    const Request query = {0, 255, 7};
    assert(DeviceThemeControl::Prepare(query, selectedTheme, false, selectTheme, persistTheme).status == Status::APPLIED);
    assert(writes == 0 && selections == 0 && selectedTheme == 2);
    for (uint8_t invalid : {8, 127, 255}) {
        const Request request = {1, invalid, 8};
        assert(DeviceThemeControl::Prepare(request, selectedTheme, false, selectTheme, persistTheme).status == Status::INVALID);
    }
    const Request badOperation = {255, 0, 9};
    assert(DeviceThemeControl::Prepare(badOperation, selectedTheme, false, selectTheme, persistTheme).status == Status::INVALID);
    assert(writes == 0 && selections == 0);
    failPersist = true;
    const Request failure = {1, 6, 10};
    const auto failed = DeviceThemeControl::Prepare(failure, selectedTheme, false, selectTheme, persistTheme);
    assert(failed.status == Status::FAILED && !failed.render && selectedTheme == 2);
    assert(writes == 1 && selections == 2);
    failPersist = false;
    const auto denied = DeviceThemeControl::Prepare(failure, selectedTheme, false,
        [](uint8_t) { return false; }, persistTheme);
    assert(denied.status == Status::FAILED && !denied.render && writes == 1);
    printf("control checks passed\n");
}

int main(int argc, char** argv) {
    assert(argc >= 2);
    if (strcmp(argv[1], "control") == 0) { controlChecks(); return 0; }
    assert(argc == 4);
    const bool deferred = atoi(argv[2]) != 0;
    const char* hex = argv[3];
    assert(strlen(hex) % 2 == 0);
    for (size_t i = 0; i < strlen(hex); i += 2) {
        char byte[3] = {hex[i], hex[i+1], 0};
        Serial.input.push_back(static_cast<uint8_t>(strtoul(byte, nullptr, 16)));
    }
    Communications::Initialize();
    unsigned themeRequests = 0;
    for (unsigned step = 0; step < 128; ++step) {
        const Command command = Communications::Read();
        if (command == Command::NONE && !Serial.available()) break;
        if (command == Command::UI_THEME) {
            Request request = {};
            assert(Communications::TakeDeviceThemeRequest(request));
            Request duplicate = {};
            assert(!Communications::TakeDeviceThemeRequest(duplicate));
            const auto result = DeviceThemeControl::Prepare(
                request, selectedTheme, deferred, selectTheme, persistTheme);
            Communications::SendDeviceThemeStatus(request.requestId, result.status, selectedTheme);
            ++themeRequests;
        }
    }
    printf("%u %u %u %u %u %u %u\n", themeRequests, writes, selections,
           selectedTheme, unsigned(Communications::CrcErrors()),
           unsigned(Communications::ProtocolErrors()), unsigned(GetClockStyle(g_Settings)));
    for (uint8_t byte : Serial.output) printf("%02x", unsigned(byte));
    printf("\n");
}
