"""Verify the Control Center layout remains scrollable with an always-visible Save."""
import pathlib
import unittest


REPO_DIR = pathlib.Path(__file__).resolve().parents[2]
GUI_PATH = REPO_DIR / "desktop" / "gui.py"


class SettingsLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GUI_PATH.read_text(encoding="utf-8")

    def test_save_button_is_reserved_at_bottom_before_tabs(self):
        self.assertIn(
            "save_btn.pack(side='bottom', fill='x', padx=12, pady=(4, 8))",
            self.source,
        )
        self.assertLess(
            self.source.index("save_btn.pack(side='bottom'"),
            self.source.index("self._tabs = ctk.CTkTabview("),
        )

    def test_sections_scroll_and_reuse_original_config_controls(self):
        self.assertIn("ctk.CTkScrollableFrame(", self.source)
        for name in ("Overview", "Audio", "Clock", "Device", "Updates", "Settings"):
            self.assertIn(f'"{name}"', self.source)
        self.assertIn('row = ctk.CTkFrame(parent, fg_color="transparent", height=26)', self.source)
        self.assertIn("row.pack(fill='x', pady=1)", self.source)
        self.assertIn("self._clock_style_var", self.source)
        self.assertIn("self._led_color_values", self.source)

    def test_long_sections_stay_in_their_own_tabs(self):
        self.assertIn('favorites_frame = ctk.CTkFrame(self._tabs.tab("Audio")', self.source)
        self.assertIn('update_frame = ctk.CTkFrame(self._tabs.tab("Updates")', self.source)
        self.assertIn('firmware_frame = ctk.CTkFrame(self._tabs.tab("Updates")', self.source)
        self.assertIn('add_row(clock_content, "Clock Style"', self.source)
        self.assertIn('add_row(preferences_content, "Auto FW Update"', self.source)

    def test_dashboard_sampling_and_tk_lifecycle_are_bounded(self):
        self.assertIn("self._last_audio_snapshot < 2.5", self.source)
        self.assertIn("items[:8]", self.source)
        self.assertIn("self._last_overview_snapshot >= 5.0", self.source)
        self.assertIn("self._window.withdraw()", self.source)


if __name__ == "__main__":
    unittest.main()
