import pathlib
import sys
import types
import unittest

DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

# Create a mock sounddevice module with various device naming styles
mock_sd = types.ModuleType("sounddevice")

mock_devices = [
    {"name": "Speakers (Realtek(R) Audio)", "max_input_channels": 0, "hostapi": 0, "default_samplerate": 48000.0},
    {"name": "Microphone (Realtek Audio)", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 48000.0},
    {"name": "Realtek High Definition Audio: Microphone", "max_input_channels": 2, "hostapi": 1, "default_samplerate": 44100.0},
    {"name": "Stereo Mix (Realtek(R) Audio)", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 48000.0},
]

mock_hostapis = [
    {"name": "Windows WASAPI"},
    {"name": "MME"},
]

mock_sd.query_devices = lambda *args, **kwargs: mock_devices
mock_sd.query_hostapis = lambda idx: mock_hostapis[idx] if idx < len(mock_hostapis) else {"name": "Other"}
sys.modules["sounddevice"] = mock_sd

from audio_capture import find_input_capture_device


class AudioCaptureRobustnessTests(unittest.TestCase):
    def test_exact_match(self):
        result = find_input_capture_device("Microphone (Realtek Audio)")
        self.assertIsNotNone(result)
        index, channels, sample_rate = result
        self.assertEqual(index, 1)
        self.assertEqual(channels, 2)

    def test_fuzzy_trademark_match(self):
        # pycaw gives "Microphone (Realtek(R) Audio)", PortAudio has "Microphone (Realtek Audio)"
        result = find_input_capture_device("Microphone (Realtek(R) Audio)")
        self.assertIsNotNone(result)
        index, channels, sample_rate = result
        self.assertEqual(index, 1)

    def test_token_match_alternate_order(self):
        # target has "Realtek Audio Microphone"
        result = find_input_capture_device("Realtek High Definition Microphone")
        self.assertIsNotNone(result)
        index, channels, sample_rate = result
        self.assertIn(index, (1, 2))

    def test_fallback_to_default_input_when_unknown(self):
        result = find_input_capture_device("USB Generic Wireless Mic That Does Not Exist")
        self.assertIsNotNone(result)
        index, channels, sample_rate = result
        self.assertEqual(index, 1)  # Falls back to WASAPI default input


if __name__ == "__main__":
    unittest.main()
