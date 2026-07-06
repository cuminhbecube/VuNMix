import os
import sys
import unittest
from unittest.mock import patch


DESKTOP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DESKTOP_DIR not in sys.path:
    sys.path.insert(0, DESKTOP_DIR)

from audio_capture import find_input_capture_device


class InputMeterTests(unittest.TestCase):
    @patch("audio_capture.sd.query_hostapis")
    @patch("audio_capture.sd.query_devices")
    def test_input_capture_prefers_matching_wasapi_device(
            self, query_devices, query_hostapis):
        query_devices.return_value = [
            {
                "name": "Microphone (USB Audio Device)",
                "max_input_channels": 1,
                "default_samplerate": 44100.0,
                "hostapi": 0,
            },
            {
                "name": "Microphone (USB Audio Device)",
                "max_input_channels": 2,
                "default_samplerate": 48000.0,
                "hostapi": 1,
            },
        ]
        query_hostapis.side_effect = [
            {"name": "MME"},
            {"name": "Windows WASAPI"},
        ]

        self.assertEqual(
            find_input_capture_device("Microphone (USB Audio Device)"),
            (1, 2, 48000.0),
        )

    @patch("audio_capture.sd.query_devices", return_value=[])
    def test_missing_input_capture_device_returns_none(self, _query_devices):
        self.assertIsNone(
            find_input_capture_device("Missing microphone")
        )


if __name__ == "__main__":
    unittest.main()
