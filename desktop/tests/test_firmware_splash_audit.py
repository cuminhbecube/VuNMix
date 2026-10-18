"""Regression checks for 2026-10-18 firmware display/input audit."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FirmwareSplashAuditTests(unittest.TestCase):
    def test_splash_key_test_exits_after_inactivity_without_sticky_touch_history(self):
        src = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        self.assertIn("keyTestLastInputAt", src)
        self.assertIn("(uint32_t)(g_Now - keyTestLastInputAt) >= 8000U", src)
        self.assertIn("lastSplashRefresh", src)
        self.assertIn("lastSplashTouchSample", src)
        self.assertNotIn("keyTestMode = Input::LastTouchEvent() !=", src)

    def test_persisted_settings_and_game_reset_both_channels(self):
        src = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        reset = src[src.index("void ResetState()\n{"):src.index("// Volume processing")]
        self.assertNotIn("g_Settings = DeviceSettings()", reset)
        self.assertIn("preferences.getBytes(\"settings\", &g_Settings", src)
        self.assertIn("Communications::Write(Command::VOLUME_ALT_CHANGE);", src)


if __name__ == "__main__":
    unittest.main()
