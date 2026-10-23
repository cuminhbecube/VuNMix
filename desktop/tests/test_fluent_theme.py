"""Windows-sized Fluent layouts and audio safety without a GUI dependency."""
import pathlib
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fluent_theme import (calculate_geometry, DEFAULT_SIZE, COMPACT_SIZE,
                          MINIMUM_SIZE, SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH,
                          audio_percentage, SECTIONS)
from fluent_audio import AudioIntent, AudioActionDispatcher


class FluentGeometryTests(unittest.TestCase):
    def test_default_compact_and_small_monitor(self):
        self.assertEqual(
            (calculate_geometry(1920, 1080).width, calculate_geometry(1920, 1080).height),
            DEFAULT_SIZE,
        )
        self.assertEqual(
            (calculate_geometry(1050, 790).width, calculate_geometry(1050, 790).height),
            COMPACT_SIZE,
        )
        smaller = calculate_geometry(800, 600)
        self.assertLessEqual(smaller.width, 800)
        self.assertLessEqual(smaller.height, 600)
        self.assertGreaterEqual(smaller.x, 0)
        self.assertGreaterEqual(smaller.y, 0)
        self.assertGreater(SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH)
        self.assertEqual(len(SECTIONS), 6)

    def test_clamp_audio_percent(self):
        self.assertEqual(audio_percentage(-10), 0)
        self.assertEqual(audio_percentage(101), 100)
        self.assertEqual(audio_percentage(49.6), 50)

    def test_windows_scaling_keeps_logical_sizes_and_centers_physical_rectangle(self):
        cases = (
            (1366, 768, 1.25, (960, 534, 83, 50)),
            (1920, 1080, 1.5, (960, 640, 240, 60)),
            (2560, 1440, 1.5, (1040, 680, 500, 210)),
        )
        for screen_width, screen_height, scale, expected in cases:
            with self.subTest(screen=(screen_width, screen_height), scale=scale):
                geometry = calculate_geometry(screen_width, screen_height, scale=scale)
                self.assertEqual((geometry.width, geometry.height, geometry.x, geometry.y), expected)
                # CTk rounds logical dimensions after multiplying by window
                # scaling; it passes geometry offsets through unchanged.
                physical_width = round(geometry.width * scale)
                physical_height = round(geometry.height * scale)
                self.assertLessEqual(physical_width, screen_width - 40)
                self.assertLessEqual(physical_height, screen_height - 100)
                self.assertGreaterEqual(geometry.x, 20)
                self.assertGreaterEqual(geometry.y, 50)
                self.assertLessEqual(geometry.x + physical_width, screen_width - 20)
                self.assertLessEqual(geometry.y + physical_height, screen_height - 50)
                self.assertLessEqual(abs(geometry.x - (screen_width - geometry.x - physical_width)), 1)
                self.assertLessEqual(abs(geometry.y - (screen_height - geometry.y - physical_height)), 1)

    def test_default_scaling_retains_existing_geometry(self):
        for screen_width, screen_height in ((1920, 1080), (1050, 790), (960, 720), (800, 600)):
            with self.subTest(screen=(screen_width, screen_height)):
                available_width, available_height = screen_width - 40, screen_height - 100
                compact = available_width < DEFAULT_SIZE[0] or available_height < DEFAULT_SIZE[1]
                desired = COMPACT_SIZE if compact else DEFAULT_SIZE
                width, height = min(desired[0], available_width), min(desired[1], available_height)
                geometry = calculate_geometry(screen_width, screen_height)
                self.assertEqual((geometry.width, geometry.height, geometry.x, geometry.y, geometry.compact),
                                 (width, height, (screen_width - width) // 2,
                                  (screen_height - height) // 2, compact))
                self.assertEqual(geometry, calculate_geometry(screen_width, screen_height, scale=1.0))

    def test_invalid_window_scale_is_rejected(self):
        for scale in (0, -1, float("nan"), float("inf")):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                calculate_geometry(1920, 1080, scale=scale)


class SafeAudioActionTests(unittest.TestCase):
    def test_identity_bound_explicit_volume_and_default(self):
        audio = mock.Mock()
        worker = AudioActionDispatcher(audio, max_pending=2)
        original = object()
        try:
            self.assertTrue(worker.submit(AudioIntent("volume", 1, 3, original, 72, False)))
            self.assertTrue(worker.submit(AudioIntent("default", 1, 3, original)))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and (
                audio.set_volume.call_count != 1 or
                audio.set_default_device.call_count != 1
            ):
                time.sleep(0.01)
            audio.set_volume.assert_called_once_with(
                1, 3, 72, False, expected_item=original
            )
            audio.set_default_device.assert_called_once_with(
                1, 3, expected_item=original
            )
        finally:
            worker.close()
        self.assertFalse(worker.submit(AudioIntent("volume", 1, 0, original, 0)))

    def test_invalid_command_rejected(self):
        with self.assertRaises(ValueError):
            AudioIntent("navigate", 1, 0, object())


if __name__ == "__main__":
    unittest.main()
