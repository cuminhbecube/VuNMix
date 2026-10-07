"""Volume/meter hot paths must not reopen every endpoint property store."""

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from audio_service import AudioItem, AudioService, IAudioEndpointVolume, IAudioMeterInformation
from protocol import DisplayMode


class EndpointMemoryTests(unittest.TestCase):
    def test_1000_volume_polls_only_open_selected_endpoint(self):
        service = AudioService()
        service._output_devices = [AudioItem(7, "Speaker", 0, False, _device_id="selected")]
        volume = mock.Mock()
        volume.GetMasterVolumeLevelScalar.return_value = 0.42
        volume.GetMute.return_value = False
        enumerator = mock.Mock()
        enumerator.GetDevice.return_value.Activate.return_value.QueryInterface.return_value = volume
        with (
            mock.patch("audio_service.AudioUtilities.GetDeviceEnumerator", return_value=enumerator),
            mock.patch("audio_service.AudioUtilities.GetAllDevices", side_effect=AssertionError("full enumeration")),
        ):
            for _ in range(1000):
                result = service.read_current_volume(DisplayMode.MODE_OUTPUT, 0)
                self.assertEqual(result.id, 7)
                self.assertEqual(result.volume, 42)
            service.set_volume(DisplayMode.MODE_OUTPUT, 0, 25, True)
        self.assertEqual(enumerator.GetDevice.call_count, 1001)
        enumerator.GetDevice.assert_called_with("selected")
        volume.SetMasterVolumeLevelScalar.assert_called_once_with(0.25, None)
        volume.SetMute.assert_called_once_with(True, None)
        enumerator.GetDevice.return_value.Activate.return_value.QueryInterface.assert_called_with(IAudioEndpointVolume)

    def test_output_meter_only_opens_selected_endpoint(self):
        service = AudioService()
        service._output_devices = [AudioItem(7, "Speaker", 0, False, _device_id="selected")]
        enumerator = mock.Mock()
        with (
            mock.patch("audio_service.AudioUtilities.GetDeviceEnumerator", return_value=enumerator),
            mock.patch("audio_service.AudioUtilities.GetAllDevices", side_effect=AssertionError("full enumeration")),
        ):
            meter = service.create_peak_meter(DisplayMode.MODE_OUTPUT, 0)
        enumerator.GetDevice.assert_called_once_with("selected")
        self.assertIs(meter, enumerator.GetDevice.return_value.Activate.return_value.QueryInterface.return_value)
        enumerator.GetDevice.return_value.Activate.return_value.QueryInterface.assert_called_once_with(IAudioMeterInformation)

    def test_default_speaker_wrapper_uses_id_and_checks_microphone(self):
        service = AudioService()
        service._output_devices = [AudioItem(1, "Speaker", 0, False, is_default=True, _device_id="out")]
        service._input_devices = [AudioItem(2, "Mic", 0, False, is_default=True, _device_id="in")]
        with (
            mock.patch("audio_service.AudioUtilities.GetSpeakers", return_value=type("Speaker", (), {"id": "out"})()),
            mock.patch("audio_service.AudioUtilities.GetMicrophone") as microphone,
        ):
            microphone.return_value.GetId.return_value = "in"
            self.assertFalse(service.check_system_changes())
            microphone.return_value.GetId.return_value = "new-mic"
            self.assertTrue(service.check_system_changes())


if __name__ == "__main__":
    unittest.main()
