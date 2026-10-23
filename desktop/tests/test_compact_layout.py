"""Guard against vertical overflow in the compact Windows Control Center."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop"))
from fluent_theme import calculate_geometry, SECTIONS, SIDEBAR_COLLAPSED_WIDTH

GUI = (ROOT / "desktop" / "gui.py").read_text(encoding="utf-8")
VIEWS = (ROOT / "desktop" / "fluent_views.py").read_text(encoding="utf-8")


class CompactLayoutContracts(unittest.TestCase):
    def test_960x720_monitor_fits_the_work_area(self):
        result = calculate_geometry(960, 720)
        self.assertLessEqual(result.width, 960)
        self.assertLessEqual(result.height, 620)
        self.assertTrue(result.compact)
        self.assertGreater(SIDEBAR_COLLAPSED_WIDTH, 40)
        self.assertEqual(len(SECTIONS), 6)

    def test_all_six_pages_use_fixed_compact_frames(self):
        # Scrollbars are not a substitute for laying out the desktop app.
        # A separate App Favorites picker can legitimately scroll; the main
        # six-page Control Center itself must not be scroll-dependent.
        dialog_source = GUI.split("    def _build_overview_tab(", 1)[0]
        self.assertNotIn("ctk.CTkScrollableFrame(", dialog_source)
        self.assertNotIn("ctk.CTkScrollableFrame(", VIEWS)
        for p in ('"Device"', '"Clock"', '"Settings"'):
            self.assertIn("self._tabs.tab(" + p + ")", GUI)
        self.assertIn('self._window.bind("<Configure>", self._fluent_window_resized)', GUI)
        self.assertIn("self._set_fluent_sidebar_collapsed(geometry.compact)", GUI)

    def test_updates_does_not_duplicate_sixteen_clock_tiles(self):
        self.assertIn("self.build_fluent_update_clock_shortcuts()", GUI)
        self.assertNotIn("self.build_fluent_clock_gallery(self._updates_gallery_area)", GUI)
        self.assertIn('self._fluent_navigate("Clock")', VIEWS)
        self.assertIn("for index, name in enumerate(CLOCK_STYLE_NAMES):", VIEWS)

    def test_audio_actions_preserved_without_tall_list(self):
        for word in (
            '"Mixer", "Profiles", "Media / OBS"',
            '"Output", "Input", "Applications", "Game Mixer"',
            "self._audio_page_index",
            "list(enumerate(all_items))[start:start + 4]",
            'self._fluent_build_audio_utilities(',
            "_fluent_set_automation", '"routing_enabled"', '"ducking_enabled"',
            "toggle_streaming", "toggle_recording",
            "self._fluent_audio_drag(",
        ):
            self.assertIn(word, VIEWS)
        self.assertIn('ctk.CTkFrame(self._audio_profiles_page', GUI)
        self.assertIn("self._audio_dispatcher.submit(", VIEWS)

    def test_overview_is_one_screen_without_nested_scrolling(self):
        start = VIEWS.index("    def build_fluent_overview(")
        end = VIEWS.index("    def build_fluent_audio(", start)
        overview = VIEWS[start:end]
        self.assertIn('body = ctk.CTkFrame(parent, fg_color="transparent")', overview)
        for heading in ("Audio mixer", "Device clock", "Copy diagnostics", "Firmware"):
            self.assertIn(heading, overview)
        self.assertIn('1 if current == "Overview" else 0', VIEWS)


if __name__ == "__main__":
    unittest.main()
