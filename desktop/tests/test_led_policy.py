import pathlib
import unittest


REPO_DIR = pathlib.Path(__file__).resolve().parents[2]


class LedPolicyRegressionTests(unittest.TestCase):
    def test_firmware_uses_state_machine_and_audio_hysteresis(self):
        source = (REPO_DIR / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("enum class LightingRenderMode", source)
        self.assertIn("LED_AUDIO_RELEASE_MS = 600", source)
        self.assertIn("LED_AUDIO_ENTER_LEVEL = 3", source)
        self.assertIn("LED_AUDIO_EXIT_LEVEL = 1", source)
        self.assertIn("SelectLightingMode()", source)
        self.assertNotIn("activityTimeDelta > 300000", source)

    def test_stereo_and_game_channels_are_not_collapsed(self):
        source = (REPO_DIR / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("LED_STEREO_LEFT[5]", source)
        self.assertIn("LED_STEREO_RIGHT[5]", source)
        self.assertIn("LightingAudioVU(s_meterCurrent, s_meterAlternate)", source)
        self.assertIn("LightingGameVU(s_meterAlternate, s_meterCurrent)", source)
        self.assertIn("INDEX_ALTERNATE", source)
        self.assertIn("INDEX_CURRENT", source)
        self.assertNotIn("uint8_t maxLevel = max(levelL, levelR)", source)

    def test_volume_bar_has_real_off_pixels_and_safe_vu_gradient(self):
        source = (REPO_DIR / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("uint8_t intensity = 0;", source)
        self.assertIn("fullPixels = units / 100U", source)
        self.assertIn("21845U * (count - 1U - i)", source)
        self.assertNotIn("6800 - (i - 6) * 3400", source)

    def test_led_mapping_and_diagnostic_mode_are_explicit(self):
        config = (REPO_DIR / "src" / "Config.h").read_text(encoding="utf-8")
        source = (REPO_DIR / "src" / "main.cpp").read_text(encoding="utf-8")
        gui = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")

        self.assertIn("LED_LOGICAL_TO_PHYSICAL", config)
        self.assertIn("LED_FRAME_INTERVAL_MS = 20", config)
        self.assertIn("LightingLedTest()", source)
        self.assertIn("g_Now / 500U", source)
        self.assertIn("LED Colors V-/V+/A/B", gui)
        self.assertIn("colorchooser.askcolor", gui)


if __name__ == "__main__":
    unittest.main()
