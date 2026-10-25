"""Original clock identity and actual native LVGL theme lifecycle regressions.

The mandatory Ubuntu release job runs the same helper with --download --verify.
Desktop discovery does not download a compiler or vendor tree implicitly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("native_theme_regression", ROOT / "tools/native_theme_regression.py")
NATIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NATIVE)


class OriginalClockSourceTests(unittest.TestCase):
    def test_original_clock_and_font_sources_match_released_baseline(self):
        baseline = NATIVE.verify_sources()
        self.assertEqual(len(baseline["clock_frames_sha256"]), 64)
        self.assertEqual(baseline["lvgl_version"], "8.3.11")


class ThemeNativeLvglTests(unittest.TestCase):
    def test_original_clock_pixels_theme_lifetimes_and_shipped_previews(self):
        if not NATIVE.toolchain_available() or NATIVE.available_lvgl() is None:
            self.skipTest("Native tools/cache absent; mandatory Ubuntu gate runs --download --verify")
        result = NATIVE.verify_native(NATIVE.obtain_lvgl())
        self.assertEqual(result["immutable_original_clock_frames"], 64)
        self.assertEqual(result["clocks"]["theme_changes_while_clock"], 512)
        self.assertEqual(result["clocks"]["theme_changes_while_sleeping"], 512)
        self.assertEqual(result["shipped_previews_pixel_equal"], 8)
        self.assertGreaterEqual(result["lifecycle"]["theme_mode_rounds"], 192)
        self.assertGreaterEqual(result["lifecycle"]["dynamic_pixel_checks"], 1344)
        self.assertEqual(result["lifecycle"]["marquee_pixel_checks"], 23)


if __name__ == "__main__":
    unittest.main()
