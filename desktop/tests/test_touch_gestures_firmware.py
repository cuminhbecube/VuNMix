"""Run the production touch input and action dispatch against I/O doubles."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]


def extract_function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class TouchGesturesFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("Host C++ compiler unavailable")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        fixture = (REPO / "desktop/tests/fixtures/touch_input_stub.hpp").as_posix()
        for name in ("Arduino.h", "Keypad.h", "Wire.h"):
            (root / name).write_text('#include "' + fixture + '"\n', encoding="utf-8")
        main = (REPO / "src/main.cpp").read_text(encoding="utf-8")
        source = '#include "' + (REPO / "src/Input.cpp").as_posix() + '"\n'
        source += r'''
bool g_DisplayAsleep = false;
bool g_ClockMode = false;
uint32_t g_Now = 0, g_LastSteps = 0;
SessionInfo g_SessionInfo;
SessionData g_Sessions[4];
ModeStates g_ModeStates;
std::vector<Command> commands;
namespace Communications {
    void Write(Command command) { commands.push_back(command); }
    void SendMediaControl(uint8_t) {}
}
namespace Display { void ResetTimers() {} }
void PreviousSession() {}
void NextSession() {}
uint8_t GetIndexForMode(DisplayMode) { return 0; }
'''
        source += extract_function(main, "bool ProcessEncoderButton()\n") + "\n"
        source += extract_function(main, "bool ProcessTouch()\n") + "\n"
        source += r'''
using Input::TouchEvent;

static void report(uint32_t now, uint8_t gesture, uint8_t fingers,
                   uint16_t x = 100, uint16_t y = 100) {
    testMillis = g_Now = now;
    testReport[0] = gesture;
    testReport[1] = fingers;
    testReport[2] = x >> 8;
    testReport[3] = x & 0xFF;
    testReport[4] = y >> 8;
    testReport[5] = y & 0xFF;
    Input::Update();
}

static void expect(TouchEvent wanted) {
    TouchEvent actual = Input::ConsumeTouchEvent();
    if (actual != wanted) {
        fprintf(stderr, "At %u ms: expected event %u, got %u\n",
                (unsigned)testMillis, (unsigned)wanted, (unsigned)actual);
        std::abort();
    }
}

static void applyTouch() { ProcessTouch(); ProcessEncoderButton(); }

int main(int argc, char** argv) {
    assert(argc == 2);
    Input::Initialize();
    g_SessionInfo.mode = MODE_OUTPUT;
    g_SessionInfo.sessions[0] = g_SessionInfo.sessions[1] = g_SessionInfo.sessions[2] = 2;
    g_ModeStates.states[MODE_OUTPUT] = STATE_NAVIGATE;
    strcpy(g_Sessions[INDEX_CURRENT].name, "Headphones");
    g_Sessions[INDEX_CURRENT].data.id = 2;
    g_Sessions[INDEX_CURRENT].data.volume = 50;
    const char* scenario = argv[1];

    if (strcmp(scenario, "single") == 0) {
        report(1000, 0, 1); expect(TouchEvent::None);
        report(1100, 0, 0); expect(TouchEvent::None);
        report(1450, 0, 0); expect(TouchEvent::None);
        // A single tap completes even when subsequent I2C reads fail.
        testReadFails = true;
        report(1451, 0, 0); expect(TouchEvent::Tap);
        report(2000, 0, 0); expect(TouchEvent::None);
    } else if (strcmp(scenario, "software_double") == 0) {
        report(1000, 0, 1); applyTouch();
        report(1100, 0, 0); applyTouch();
        assert(commands.empty());
        report(1200, 0, 1); applyTouch();
        report(1300, 0, 0); applyTouch();
        assert(g_ModeStates.states[MODE_OUTPUT] == STATE_NAVIGATE);
        assert(!g_Sessions[INDEX_CURRENT].data.isDefault);
        assert(g_Sessions[INDEX_CURRENT].data.isMuted);
        assert(commands.size() == 1 && commands[0] == Command::VOLUME_CURR_CHANGE);
        report(2000, 0, 0); applyTouch();
        assert(commands.size() == 1);
    } else if (strcmp(scenario, "hardware_taps") == 0) {
        report(1000, 0, 1);
        report(1050, 0x05, 1); expect(TouchEvent::None);
        report(1100, 0x05, 0); expect(TouchEvent::None);
        report(1250, 0x05, 0); expect(TouchEvent::None);
        report(1451, 0x05, 0); expect(TouchEvent::Tap);
        report(1800, 0x05, 0); expect(TouchEvent::None);
        // Gesture-only reports are supported when the brief down was not sampled.
        report(1900, 0, 0);
        report(2000, 0x05, 0); expect(TouchEvent::None);
        report(2050, 0, 0);
        report(2200, 0x05, 0); expect(TouchEvent::DoubleTap);
        report(2700, 0x05, 0); expect(TouchEvent::None);
    } else if (strcmp(scenario, "mixed_taps") == 0) {
        report(1000, 0, 1); report(1100, 0, 0);
        report(1125, 0, 0);
        // A late hardware TAP confirms the same coordinate contact.
        report(1150, 0x05, 0); expect(TouchEvent::None);
        report(1200, 0, 1); report(1300, 0x05, 0);
        expect(TouchEvent::DoubleTap);
        report(1800, 0, 0); expect(TouchEvent::None);
        report(2000, 0, 1); report(2100, 0x05, 0);
        report(2200, 0, 1); report(2300, 0, 0);
        expect(TouchEvent::DoubleTap);
        report(2800, 0, 0); expect(TouchEvent::None);
        report(3000, 0, 1); report(3100, 0, 0);
        report(3300, 0x0B, 0); expect(TouchEvent::DoubleTap);
        report(3800, 0x0B, 0); expect(TouchEvent::None);
    } else if (strcmp(scenario, "long_press") == 0) {
        report(1000, 0, 1);
        report(2000, 0x0C, 1); expect(TouchEvent::LongPress);
        report(2100, 0, 1); expect(TouchEvent::None);
        report(2400, 0x0C, 1); expect(TouchEvent::None);
        report(2700, 0, 0); expect(TouchEvent::None);
        report(3000, 0, 1);
        report(3900, 0, 0); expect(TouchEvent::LongPress);
        report(4400, 0, 0); expect(TouchEvent::None);
    } else if (strcmp(scenario, "wake_only") == 0) {
        g_DisplayAsleep = true;
        report(1000, 0, 1); applyTouch();
        report(1100, 0, 0); applyTouch();
        report(1200, 0, 1); applyTouch();
        report(1300, 0, 0); applyTouch();
        g_DisplayAsleep = false; // Main-loop idle policy wakes after consuming the gesture.
        report(1800, 0, 0); applyTouch();
        assert(commands.empty() && !g_Sessions[INDEX_CURRENT].data.isMuted);
        g_DisplayAsleep = true;
        report(2000, 0, 1);
        report(3000, 0x0C, 1); applyTouch();
        g_DisplayAsleep = false;
        report(3600, 0, 0); applyTouch();
        assert(commands.empty() && g_SessionInfo.mode == MODE_OUTPUT);
    } else if (strcmp(scenario, "window_and_wrap") == 0) {
        report(1000, 0, 1); report(1100, 0, 0);
        report(1450, 0, 1); expect(TouchEvent::None);
        report(1500, 0, 1); expect(TouchEvent::None);
        report(1600, 0, 0); expect(TouchEvent::DoubleTap);
        report(2100, 0, 0); expect(TouchEvent::None);
        uint32_t start = UINT32_MAX - 150U;
        report(start, 0, 1); report(start + 50U, 0, 0);
        report(start + 150U, 0, 1); report(start + 250U, 0, 0);
        expect(TouchEvent::DoubleTap);
        report(start + 700U, 0, 0); expect(TouchEvent::None);
        report(start + 800U, 0, 1); report(start + 850U, 0, 0);
        report(start + 1201U, 0, 0); expect(TouchEvent::Tap);
    } else if (strcmp(scenario, "swipes_and_separate_actions") == 0) {
        const TouchEvent rotation3[] = {TouchEvent::SwipeRight, TouchEvent::SwipeLeft,
                                       TouchEvent::SwipeUp, TouchEvent::SwipeDown};
        for (uint8_t gesture = 1; gesture <= 4; ++gesture) {
            uint32_t start = 1000 + gesture * 1000;
            report(start, 0, 1);
            report(start + 100, gesture, 1); expect(rotation3[gesture - 1]);
            report(start + 600, gesture, 0); expect(TouchEvent::None);
        }
        report(6000, 0, 1, 100, 100);
        report(6100, 0, 1, 100, 200);
        report(6150, 0, 0, 100, 200); expect(TouchEvent::SwipeRight);
        report(7000, 0, 1); report(7100, 0, 0);
        report(7200, 0, 1);
        report(7500, 0, 1); expect(TouchEvent::None);
        report(8200, 0x0C, 1);
        expect(TouchEvent::Tap); expect(TouchEvent::LongPress);
        report(8700, 0, 0); expect(TouchEvent::None);
    } else {
        return 2;
    }
    expect(TouchEvent::None);
    return 0;
}
'''
        cpp = root / "touch-input.cpp"
        cls.binary = root / ("touch-input.exe" if os.name == "nt" else "touch-input")
        cpp.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [compiler, "-std=c++17", "-Wall", "-Wextra", "-I", str(root), str(cpp), "-o", str(cls.binary)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_scenario(self, scenario):
        result = subprocess.run(
            [str(self.binary), scenario], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_single_tap_waits_for_window_without_another_report(self):
        self.run_scenario("single")

    def test_double_tap_mutes_without_selecting_another_default_device(self):
        self.run_scenario("software_double")

    def test_hardware_taps_are_deferred_and_repeated_reports_are_ignored(self):
        self.run_scenario("hardware_taps")

    def test_hardware_and_software_recognizers_share_pending_taps(self):
        self.run_scenario("mixed_taps")

    def test_long_press_owns_contact_until_release(self):
        self.run_scenario("long_press")

    def test_waking_double_tap_and_long_press_do_not_leak_an_action(self):
        self.run_scenario("wake_only")

    def test_second_contact_window_and_millis_rollover(self):
        self.run_scenario("window_and_wrap")

    def test_swipes_and_distinct_pending_actions_are_preserved(self):
        self.run_scenario("swipes_and_separate_actions")


if __name__ == "__main__":
    unittest.main()
