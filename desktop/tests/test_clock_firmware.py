"""Execute the actual C++ renderer against a small LVGL ownership double."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]


class ClockFirmwareTests(unittest.TestCase):
    def test_native_settings_layout_matches_python_packets(self):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('Host C++ compiler unavailable')
        import sys
        sys.path.insert(0, str(REPO / 'desktop'))
        from protocol import DeviceSettings
        header = (REPO / 'src/Structs.h').read_text()
        native = header[header.index('struct __attribute__((__packed__)) Color'):header.index('struct __attribute__((__packed__)) ModeStates')]
        source = '#include <cstdint>\n#include <cstdio>\n' + native + r"""
int main() {
    for (int style=0; style<16; ++style) for (int sleep=0; sleep<2; ++sleep) {
        DeviceSettings settings;
        settings.clockStyle=style&7; settings.clockStyleHigh=style>>3;
        settings.sleepEnabled=sleep; settings.standbyLedMode=16;
        const auto* bytes=reinterpret_cast<const uint8_t*>(&settings);
        for (unsigned i=0; i<sizeof(settings); ++i) printf("%02x", bytes[i]);
        printf("\n");
    }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            cpp, binary = root / 'settings.cpp', root / 'settings-test'
            cpp.write_text(source)
            build = subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        expected = [DeviceSettings(sleep_after_seconds=300, clock_style=style, sleep_enabled=bool(sleep), standby_led_mode=16).pack().hex()
                    for style in range(16) for sleep in range(2)]
        self.assertEqual(result.stdout.splitlines(), expected)

    def test_clock_widgets_are_reused_and_reset_across_all_styles(self):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('Host C++ compiler unavailable; firmware CI compiles real LVGL')
        theme = (REPO / 'src/ui/modules/DisplayThemeShell.inc').read_text()
        state = theme[theme.index('    // Clock Standby'):theme.index('    // Helpers')]
        lifecycle = (REPO / 'src/ui/modules/DisplayShellLifecycle.inc').read_text()
        reset = lifecycle[lifecycle.index('        s_clockHM = nullptr;'):lifecycle.index('        s_faderA = nullptr;', lifecycle.index('        s_clockHM = nullptr;'))]
        source = (REPO / 'desktop/tests/fixtures/clock_lvgl_stub.hpp').read_text() + state
        source += 'static void FullReset() { objects.clear(); s_currentScreen=ScreenType::NONE;\n' + reset + '}\n'
        for name in ('DisplayClockStyles', 'DisplayClockArtHelpers', 'DisplayClockArtDigits',
                     'DisplayClockArtWords', 'DisplayClockArtHands', 'DisplayClockArt', 'DisplayClock'):
            source += '#include "' + (REPO / ('src/ui/modules/' + name + '.inc')).as_posix() + '"\n'
        source += r'''
int main() {
    for (int cycle=0; cycle<20; ++cycle) {
        for (uint8_t style=0; style<16; ++style) {
            g_Settings.clockStyle=style;
            ClockScreen(23,59,59);
            const int created=allocations;
            const size_t live=objects.size();
            for (int tick=0; tick<3600; ++tick) ClockScreen(12,tick/60,tick%60);
            assert(allocations==created && objects.size()==live);
            // Same seconds, different hour/minute must still update.
            ClockScreen(1,2,7); ClockScreen(3,4,7);
            if (style==1 || style==4 || style==7) assert(s_clockHM->text=="03:04");
            if (style==6) assert(s_clockHM->text=="03:04:07");
            if (style==0 || style==2 || style==5) {
                assert(s_clockHM->text=="03"); assert(s_clockSec->text=="04");
            }
            if (style>=8) assert(s_clockSecond->text=="03:04:07 / 24H");
            if (style==4) assert(s_clockProgress->value==7);
            if (style==5) {
                ClockScreen(23,59,59);
                const uint8_t values[3]={23,59,59};
                const uint32_t colors[3]={0x70D6FF,0xBD9AFF,0x7DE6B5};
                for (int col=0; col<3; ++col) for (int row=0; row<6; ++row) {
                    auto* dot=s_clockBinary[col][row];
                    assert(dot->bg==((values[col] & (1<<(5-row))) ? colors[col] : 0x18232D));
                }
            }
            // Fixed-size new-style shapes stay within their parent bounds.
            if (style>=4) for (auto& owned: objects) {
                auto* obj=owned.get();
                if (obj->w && obj->h) {
                    assert(obj->x>=0 && obj->y>=0);
                    assert(obj->x+obj->w<=obj->parent->w && obj->y+obj->h<=obj->parent->h);
                }
            }
        }
    }
    for (int value=0; value<60; ++value) {
        int reconstructed=0;
        for (int word=1; word<25; ++word) if(ClockWordActive(word,value))
            reconstructed += word<=20 ? word-1 : (word-19)*10;
        assert(reconstructed==value);
    }
    FullReset();
    assert(objects.empty() && !s_clockArt && !s_clockProgress && !s_clockBinary[0][0]);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            cpp, binary = root / 'clock.cpp', root / 'clock-test'
            cpp.write_text(source)
            build = subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
