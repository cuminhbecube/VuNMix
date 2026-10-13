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
