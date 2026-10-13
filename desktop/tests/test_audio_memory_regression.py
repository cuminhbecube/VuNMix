"""Regression tests for bounded Windows Audio COM enumeration.

The tests avoid real devices so they can run on a clean Windows CI runner.
"""

import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from audio_service import AudioItem, AudioService
from controller_workers import SyncWorkersMixin
from protocol import DisplayMode


class _Endpoint:
    def GetMasterVolumeLevelScalar(self):
        return 0.50

    def GetMute(self):
        return False


class _Device:
    def __init__(self, identifier, name):
        self.id = identifier
        self.FriendlyName = name
        self.state = "AudioDeviceState.Active"
        self.EndpointVolume = _Endpoint()


class AudioRefreshMemoryTests(unittest.TestCase):
    def setUp(self):
        self.audio = AudioService()

    def test_refresh_enumerates_windows_endpoints_once_not_twice(self):
        output = _Device("{0.0.0.00000000}.out", "Speakers")
        input_ = _Device("{0.0.1.00000000}.in", "Microphone")
        with (
            mock.patch("audio_service.AudioUtilities.GetAllDevices",
                       return_value=[output, input_]) as enumerate_devices,
            mock.patch("audio_service.AudioUtilities.GetSpeakers",
                       return_value=SimpleNamespace(id=output.id)),
            mock.patch("audio_service.AudioUtilities.GetMicrophone",
                       return_value=SimpleNamespace(GetId=lambda: input_.id)),
            mock.patch("audio_service.AudioUtilities.GetAllSessions",
                       return_value=[]),
        ):
            for _ in range(50):
                self.audio.refresh()
                self.assertEqual(
                    len(self.audio.get_sessions_for_mode(DisplayMode.MODE_OUTPUT)), 1
                )
                self.assertEqual(
                    len(self.audio.get_sessions_for_mode(DisplayMode.MODE_INPUT)), 1
                )
            self.assertEqual(enumerate_devices.call_count, 50)

    def test_failed_enumeration_does_not_erase_last_valid_snapshot(self):
        previous = AudioItem(
            id=7, name="Speakers", volume=50, is_muted=False,
            _device_id="{0.0.0.00000000}.out",
        )
        self.audio._output_devices = [previous]
        with (
            mock.patch("audio_service.AudioUtilities.GetAllDevices",
                       side_effect=RuntimeError("transient COM error")),
            mock.patch("audio_service.AudioUtilities.GetAllSessions",
                       return_value=[]),
        ):
            self.audio.refresh()
        self.assertEqual(
            self.audio.get_sessions_for_mode(DisplayMode.MODE_OUTPUT), [previous]
        )


class _Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


class _Worker(SyncWorkersMixin):
    def __init__(self):
        self._running = True
        self._device_connected = True
        self._is_sleeping = False
        self._resume_recovering = False
        self._session_info = SimpleNamespace(mode=DisplayMode.MODE_OUTPUT)
        self._state_lock = threading.RLock()
        self.config = SimpleNamespace(update_interval_ms=200)
        self.audio = mock.Mock()
        self.audio.get_sessions_for_mode.return_value = []
        self.audio.check_system_changes.return_value = False
        self.serial = mock.Mock()
        self.system_monitor = mock.Mock()
        self.media_service = mock.Mock()
        self._sync_current_volume_once = mock.Mock()
        self._push_updated_state = mock.Mock()


class AudioPollingMemoryTests(unittest.TestCase):
    def test_fast_tick_does_not_trigger_fast_com_enumeration(self):
        worker = _Worker()
        clock = _Clock()

        def advance_time(seconds):
            clock.now += seconds
            if clock.now >= 12.2:
                worker._running = False

        with (
            mock.patch("controller_workers.time.monotonic",
                       side_effect=clock.monotonic),
            mock.patch("controller_workers.time.sleep",
                       side_effect=advance_time),
            mock.patch("controller_workers.comtypes.CoInitialize") as init,
            mock.patch("controller_workers.comtypes.CoUninitialize") as uninit,
        ):
            worker._sync_loop()

        self.assertEqual(init.call_count, 1)
        self.assertEqual(uninit.call_count, 1)
        self.assertEqual(worker.audio.refresh.call_count, 1)
        self.assertGreaterEqual(worker.audio.check_system_changes.call_count, 4)
        self.assertLessEqual(worker.audio.check_system_changes.call_count, 6)
        self.assertLessEqual(worker._sync_current_volume_once.call_count, 17)
        self.assertGreater(worker._sync_current_volume_once.call_count, 10)
        self.assertGreaterEqual(worker.serial.send_pc_stats.call_count, 10)


if __name__ == "__main__":
    unittest.main()
