"""Enforce the approved Fluent Compact Dark shell structure and controls."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUI = ROOT / "desktop" / "gui.py"
VIEWS = ROOT / "desktop" / "fluent_views.py"


class FluentLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = GUI.read_text(encoding="utf-8")
        cls.views = VIEWS.read_text(encoding="utf-8")

    def test_native_resizable_window_and_fixed_save(self):
        self.assertIn("calculate_geometry(", self.gui)
        self.assertIn("self._window.minsize(*MINIMUM_SIZE)", self.gui)
        self.assertIn("self._window.title(", self.gui)
        self.assertNotIn("overrideredirect(True)", self.gui)
        self.assertIn(
            "save_btn.pack(side='bottom', fill='x', padx=12, pady=(4, 8))",
            self.gui,
        )
        self.assertLess(
            self.gui.index("save_btn.pack(side='bottom'"),
            self.gui.index("self._tabs = ctk.CTkTabview("),
        )

    def test_sidebar_and_six_routes(self):
        self.assertIn("self._build_fluent_sidebar(shell)", self.gui)
        self.assertIn("self._tabs._segmented_button.grid_forget()", self.gui)
        self.assertIn("for name in SECTIONS:", self.gui)
        self.assertIn("def _toggle_fluent_sidebar", self.views)
        self.assertIn("self._fluent_highlight_nav()", self.views)

    def test_fully_wired_legacy_configuration_fields(self):
        for field in (
            "_clock_style_var", "_brightness_var", "_sleep_var",
            "_led_mode_var", "_led_color_values", "_scroll_var", "_startup_var",
            "_auto_update_var", "_auto_firmware_update_var",
            "_firmware_status_var", "_favorites_status_var",
        ):
            self.assertIn(field, self.gui)
        for tab in ("Audio", "Clock", "Device", "Updates", "Settings"):
            self.assertIn(f'self._tabs.tab("{tab}")', self.gui)
        self.assertIn("self._save", self.gui)

    def test_compact_dashboard_contains_actual_controls(self):
        for part in (
            "Audio Mixer", "Clock Preview", "Quick Actions",
            "OBS", "Media", "Profiles", "Game Mixer",
            "toggle_routing", "toggle_ducking",
            "set_volume(", "16 styles",
        ):
            # set_volume is deliberately restricted to the dispatcher.
            if part == "set_volume(":
                self.assertIn(part,
                    (ROOT / "desktop/fluent_audio.py").read_text(encoding="utf-8"))
            else:
                self.assertIn(part, self.views)


if __name__ == "__main__":
    unittest.main()
