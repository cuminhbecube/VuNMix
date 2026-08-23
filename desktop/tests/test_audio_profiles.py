import pathlib
import sys
import tempfile
import unittest
from dataclasses import dataclass


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from audio_profile_service import AudioProfileService
from profile_controller import ProfileDebouncer
from protocol import DisplayMode


@dataclass
class _Item:
    name: str
    volume: int
    is_muted: bool
    is_default: bool = False


class _Audio:
    def __init__(self):
        self.outputs = [_Item("Speakers", 40, False, True)]
        self.inputs = [_Item("Microphone", 50, True, True)]
        self.apps = [
            _Item("Discord", 20, False),
            _Item("Spotify", 90, False),
        ]
        self.calls = []

    def get_sessions_for_mode(self, mode):
        if mode == DisplayMode.MODE_OUTPUT:
            return list(self.outputs)
        if mode == DisplayMode.MODE_INPUT:
            return list(self.inputs)
        if mode == DisplayMode.MODE_APPLICATION:
            return list(self.apps)
        return []

    def set_volume(self, mode, index, volume, muted):
        self.calls.append((mode, index, volume, muted))
        item = self.get_sessions_for_mode(mode)[index]
        item.volume = volume
        item.is_muted = muted


class AudioProfileTests(unittest.TestCase):
    def _service(self, directory):
        return AudioProfileService(
            _Audio(),
            path=str(pathlib.Path(directory) / "profiles.json"),
        )

    def test_create_edit_delete_and_persist_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            profile = {
                "output": {"volume": 72, "muted": False},
                "mic": {"volume": 88, "muted": False},
                "apps": {"discord.exe": {"volume": 66, "muted": True}},
                "triggers": {"focused_apps": ["game.exe"]},
            }
            service.save_profile("Custom", profile)
            service.save_profile("Custom", {**profile, "output": {"volume": 55, "muted": True}})

            reloaded = self._service(directory)
            saved = reloaded.get_profile("Custom")
            self.assertIsNotNone(saved)
            self.assertEqual(saved["output"], {"volume": 55, "muted": True})
            self.assertIn("game", saved["triggers"]["focused_apps"])
            self.assertTrue(reloaded.delete_profile("Custom"))
            self.assertIsNone(reloaded.get_profile("Custom"))
            after_delete = self._service(directory)
            self.assertIsNone(after_delete.get_profile("Custom"))

    def test_default_profile_deletion_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            self.assertIn("Gaming", service.profile_names())
            self.assertTrue(service.delete_profile("Gaming"))
            self.assertNotIn("Gaming", service.profile_names())
            reloaded = self._service(directory)
            self.assertNotIn("Gaming", reloaded.profile_names())

    def test_capture_and_apply_restores_volume_and_mute(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            captured = service.capture_current_as_preset("Snapshot")
            self.assertEqual(captured["output"], {"volume": 40, "muted": False})
            self.assertEqual(captured["mic"], {"volume": 50, "muted": True})
            self.assertEqual(captured["apps"]["discord"], {"volume": 20, "muted": False})

            service.save_profile(
                "Restore",
                {
                    "output": {"volume": 77, "muted": True},
                    "mic": {"volume": 81, "muted": False},
                    "apps": {
                        "discord": {"volume": 64, "muted": True},
                        "spotify": {"volume": 31, "muted": False},
                    },
                    "triggers": {},
                },
            )
            self.assertTrue(service.apply_profile("Restore", source="test"))

            self.assertIn((DisplayMode.MODE_OUTPUT, 0, 77, True), service.audio.calls)
            self.assertIn((DisplayMode.MODE_INPUT, 0, 81, False), service.audio.calls)
            self.assertIn((DisplayMode.MODE_APPLICATION, 0, 64, True), service.audio.calls)
            self.assertIn((DisplayMode.MODE_APPLICATION, 1, 31, False), service.audio.calls)
            self.assertEqual(service.active_profile, "Restore")

    def test_context_priority_is_obs_then_focus_then_running_process(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.save_profile(
                "Process",
                {"triggers": {"running_apps": ["tool"]}},
            )
            service.save_profile(
                "Focus",
                {"triggers": {"focused_apps": ["editor"]}},
            )

            self.assertEqual(
                service.match_context(running_apps=["tool.exe"]),
                "Process",
            )
            self.assertEqual(
                service.match_context(
                    focused_app="editor.exe",
                    running_apps=["tool.exe"],
                ),
                "Focus",
            )
            self.assertEqual(
                service.match_context(
                    focused_app="editor.exe",
                    running_apps=["tool.exe"],
                    obs_streaming=True,
                ),
                "Streaming",
            )

    def test_auto_switch_can_be_disabled_and_hardware_mode_is_mapped(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            self.assertEqual(
                service.profile_for_hardware_mode(DisplayMode.MODE_GAME),
                "Gaming",
            )
            service.set_auto_switch_enabled(False)
            self.assertIsNone(
                service.match_context(focused_app="steam.exe", obs_streaming=True)
            )

    def test_debouncer_prevents_trigger_oscillation_and_repeat_apply(self):
        debouncer = ProfileDebouncer(debounce_seconds=1.0, min_switch_interval=3.0)
        self.assertIsNone(debouncer.observe("Gaming", 0.0))
        self.assertIsNone(debouncer.observe("Work", 0.5))
        self.assertIsNone(debouncer.observe("Work", 1.0))
        self.assertEqual(debouncer.observe("Work", 1.6), "Work")
        debouncer.mark_applied("Work", 1.6)
        self.assertIsNone(debouncer.observe("Work", 10.0))
        self.assertIsNone(debouncer.observe("Gaming", 2.0))
        self.assertIsNone(debouncer.observe("Gaming", 3.1))
        self.assertEqual(debouncer.observe("Gaming", 4.7), "Gaming")


if __name__ == "__main__":
    unittest.main()
