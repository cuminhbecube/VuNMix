"""Volume automation must not write mute from a stale audio cache."""

from contextlib import nullcontext
import pathlib
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from audio_automation_service import AudioAutomationService, DuckingRule
from audio_service import AudioItem, AudioService
from protocol import DisplayMode


class NativeVolume:
    """Native endpoint/session state deliberately separate from AudioItem."""

    def __init__(self, muted):
        self.volume = 0.8
        self.muted = muted
        self.mute_writes = []

    def SetMasterVolume(self, volume, context):
        self.volume = volume

    def SetMasterVolumeLevelScalar(self, volume, context):
        self.volume = volume

    def SetMute(self, muted, context):
        self.mute_writes.append(muted)
        self.muted = muted


class VolumeOnlyTests(unittest.TestCase):
    def app_fixture(self, cached_muted, native_muted):
        service = AudioService()
        item = AudioItem(
            id=11, name="Spotify", volume=80, is_muted=cached_muted,
            _process_id=1002, _session_identifier="spotify-session",
        )
        service._app_sessions = [item]
        native = NativeVolume(native_muted)
        session = SimpleNamespace(
            InstanceIdentifier="spotify-session", SimpleAudioVolume=native,
        )
        return service, item, native, session

    def test_application_volume_only_preserves_live_mute_with_stale_cache(self):
        for native_muted in (False, True):
            with self.subTest(native_muted=native_muted):
                cached_muted = not native_muted
                service, item, native, session = self.app_fixture(cached_muted, native_muted)
                with (
                    mock.patch.object(service, "_com_scope", return_value=nullcontext()),
                    mock.patch("audio_service.AudioUtilities.GetAllSessions", return_value=[session]),
                ):
                    self.assertTrue(service.set_volume(
                        DisplayMode.MODE_APPLICATION, 0, 25, cached_muted,
                        expected_item=item, preserve_mute=True,
                    ))
                self.assertEqual(native.volume, 0.25)
                self.assertEqual(item.volume, 25)
                self.assertEqual(native.muted, native_muted)
                self.assertEqual(item.is_muted, cached_muted)
                self.assertEqual(native.mute_writes, [])

    def test_endpoint_volume_only_preserves_live_mute_with_stale_cache(self):
        for mode in (DisplayMode.MODE_OUTPUT, DisplayMode.MODE_INPUT):
            for native_muted in (False, True):
                with self.subTest(mode=mode, native_muted=native_muted):
                    service = AudioService()
                    cached_muted = not native_muted
                    item = AudioItem(1, "Endpoint", 80, cached_muted, _device_id="endpoint")
                    if mode == DisplayMode.MODE_OUTPUT:
                        service._output_devices = [item]
                    else:
                        service._input_devices = [item]
                    native = NativeVolume(native_muted)
                    with (
                        mock.patch.object(service, "_com_scope", return_value=nullcontext()),
                        mock.patch.object(service, "_endpoint_volume", return_value=native),
                    ):
                        self.assertTrue(service.set_volume(
                            mode, 0, 25, cached_muted,
                            expected_item=item, preserve_mute=True,
                        ))
                    self.assertEqual(native.volume, 0.25)
                    self.assertEqual(item.volume, 25)
                    self.assertEqual(native.muted, native_muted)
                    self.assertEqual(item.is_muted, cached_muted)
                    self.assertEqual(native.mute_writes, [])

    def test_existing_application_caller_still_sets_volume_and_mute(self):
        for requested_mute in (False, True):
            with self.subTest(requested_mute=requested_mute):
                service, item, native, session = self.app_fixture(not requested_mute, not requested_mute)
                with (
                    mock.patch.object(service, "_com_scope", return_value=nullcontext()),
                    mock.patch("audio_service.AudioUtilities.GetAllSessions", return_value=[session]),
                ):
                    self.assertTrue(service.set_volume(
                        DisplayMode.MODE_APPLICATION, 0, 25, requested_mute, expected_item=item,
                    ))
                self.assertEqual(native.volume, 0.25)
                self.assertEqual(native.muted, requested_mute)
                self.assertEqual(item.is_muted, requested_mute)
                self.assertEqual(native.mute_writes, [requested_mute])

    def test_existing_endpoint_caller_still_sets_volume_and_mute(self):
        service = AudioService()
        item = AudioItem(1, "Speakers", 80, False, _device_id="endpoint")
        service._output_devices = [item]
        native = NativeVolume(False)
        with (
            mock.patch.object(service, "_com_scope", return_value=nullcontext()),
            mock.patch.object(service, "_endpoint_volume", return_value=native),
        ):
            self.assertTrue(service.set_volume(DisplayMode.MODE_OUTPUT, 0, 25, True, expected_item=item))
        self.assertEqual(native.volume, 0.25)
        self.assertTrue(native.muted)
        self.assertTrue(item.is_muted)
        self.assertEqual(native.mute_writes, [True])

    def test_duck_release_cleanup_and_recovery_leave_uncached_windows_mute_alone(self):
        for initial_muted in (False, True):
            for finish in ("release", "cleanup", "crash_recovery"):
                with self.subTest(initial_muted=initial_muted, finish=finish):
                    with tempfile.TemporaryDirectory() as directory:
                        service, item, native, session = self.app_fixture(initial_muted, initial_muted)
                        path = str(pathlib.Path(directory) / "automation.json")
                        automation = AudioAutomationService(service, path=path)
                        automation.save_ducking_rule(DuckingRule(
                            "Chat ducks music", "discord", ["spotify"],
                            reduction_percent=50, threshold=0.01, attack_ms=0, release_ms=0,
                        ))
                        with (
                            mock.patch.object(service, "_com_scope", return_value=nullcontext()),
                            mock.patch("audio_service.AudioUtilities.GetAllSessions", return_value=[session]),
                        ):
                            automation.tick_ducking({"Discord": 0.5}, 1.0)
                            self.assertEqual(native.volume, 0.4)
                            # Windows changes before the next polling refresh;
                            # the desktop's AudioItem still has the old mute.
                            native.muted = not initial_muted
                            self.assertEqual(item.is_muted, initial_muted)
                            if finish == "release":
                                automation.tick_ducking({"Discord": 0.0}, 2.0)
                            elif finish == "cleanup":
                                automation.restore_all_ducked()
                            else:
                                automation = AudioAutomationService(service, path=path)
                                self.assertEqual(automation.recover_pending(), 1)
                        self.assertEqual(native.volume, 0.8)
                        self.assertEqual(native.muted, not initial_muted)
                        self.assertEqual(native.mute_writes, [])
                        self.assertFalse(automation.has_pending_recovery())


if __name__ == "__main__":
    unittest.main()
