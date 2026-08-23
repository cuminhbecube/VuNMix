import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from audio_automation_service import (
    AudioAutomationService,
    DuckingRule,
    RoutingRule,
)
from protocol import DisplayMode


class _Audio:
    def __init__(self):
        self.outputs = [
            SimpleNamespace(
                id=1,
                name="Speakers",
                volume=70,
                is_muted=False,
                _device_id="DEV_SPEAKERS",
            ),
            SimpleNamespace(
                id=2,
                name="USB Headset",
                volume=60,
                is_muted=False,
                _device_id="DEV_HEADSET",
            ),
        ]
        self.apps = [
            SimpleNamespace(
                id=10,
                name="Discord",
                volume=90,
                is_muted=False,
                _process_id=1001,
                _process_path=r"C:\\Discord\\Discord.exe",
                _session_identifier="discord-session",
            ),
            SimpleNamespace(
                id=11,
                name="Spotify",
                volume=80,
                is_muted=False,
                _process_id=1002,
                _process_path=r"C:\\Spotify\\Spotify.exe",
                _session_identifier="spotify-session",
            ),
            SimpleNamespace(
                id=12,
                name="Game",
                volume=75,
                is_muted=False,
                _process_id=1003,
                _process_path=r"C:\\Games\\Game.exe",
                _session_identifier="game-session",
            ),
        ]
        self.volume_calls = []

    def get_sessions_for_mode(self, mode):
        if mode == DisplayMode.MODE_OUTPUT:
            return list(self.outputs)
        if mode == DisplayMode.MODE_APPLICATION:
            return list(self.apps)
        return []

    def set_volume(self, mode, index, volume, muted):
        self.volume_calls.append((mode, index, int(volume), bool(muted)))
        item = self.get_sessions_for_mode(mode)[index]
        item.volume = int(volume)
        item.is_muted = bool(muted)


class _Router:
    def __init__(self):
        self.set_calls = []
        self.clear_calls = []

    def set_process_output(self, pid, device_id):
        self.set_calls.append((int(pid), str(device_id)))

    def clear_process_output(self, pid):
        self.clear_calls.append(int(pid))


class AudioAutomationTests(unittest.TestCase):
    def _service(self, directory, audio=None):
        return AudioAutomationService(
            audio or _Audio(),
            path=str(pathlib.Path(directory) / "audio_automation.json"),
        )

    def test_routing_rule_maps_process_to_device_and_clears_when_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = _Audio()
            service = self._service(directory, audio)
            service.save_routing_rule(
                RoutingRule(
                    name="Chat to headset",
                    app_pattern="discord*",
                    device_pattern="headset",
                )
            )
            router = _Router()

            self.assertEqual(service.apply_routing_rules(router), 1)
            self.assertEqual(router.set_calls, [(1001, "DEV_HEADSET")])
            self.assertEqual(service.apply_routing_rules(router), 0)

            service.set_routing_enabled(False)
            self.assertEqual(service.apply_routing_rules(router), 1)
            self.assertEqual(router.clear_calls, [1001])

    def test_ducking_attack_and_release_restore_exact_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = _Audio()
            service = self._service(directory, audio)
            service.save_ducking_rule(
                DuckingRule(
                    name="Chat ducks music",
                    trigger_pattern="discord",
                    target_patterns=["spotify"],
                    reduction_percent=50,
                    threshold=0.01,
                    attack_ms=0,
                    release_ms=0,
                )
            )

            service.tick_ducking({"Discord": 0.5}, 1.0)
            self.assertEqual(audio.apps[1].volume, 40)
            self.assertTrue(service.has_pending_recovery())

            service.tick_ducking({"Discord": 0.0}, 2.0)
            self.assertEqual(audio.apps[1].volume, 80)
            self.assertFalse(service.has_pending_recovery())

    def test_manual_volume_change_updates_baseline_during_duck(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = _Audio()
            service = self._service(directory, audio)
            service.save_ducking_rule(
                DuckingRule(
                    name="Chat ducks music",
                    trigger_pattern="discord",
                    target_patterns=["spotify"],
                    reduction_percent=50,
                    threshold=0.01,
                    attack_ms=0,
                    release_ms=0,
                )
            )

            service.tick_ducking({"Discord": 0.5}, 1.0)
            self.assertEqual(audio.apps[1].volume, 40)

            # User changes Spotify from the expected ducked 40% to 30%.
            # The corresponding unducked intent is therefore 60%.
            audio.apps[1].volume = 30
            service.tick_ducking({"Discord": 0.5}, 2.0)
            self.assertEqual(audio.apps[1].volume, 30)

            service.tick_ducking({"Discord": 0.0}, 3.0)
            self.assertEqual(audio.apps[1].volume, 60)

    def test_strongest_active_ducking_rule_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = _Audio()
            service = self._service(directory, audio)
            service.save_ducking_rule(
                DuckingRule(
                    name="Chat 25",
                    trigger_pattern="discord",
                    target_patterns=["spotify"],
                    reduction_percent=25,
                    threshold=0.01,
                    attack_ms=0,
                    release_ms=0,
                )
            )
            service.save_ducking_rule(
                DuckingRule(
                    name="Game 60",
                    trigger_pattern="game",
                    target_patterns=["spotify"],
                    reduction_percent=60,
                    threshold=0.01,
                    attack_ms=0,
                    release_ms=0,
                )
            )

            service.tick_ducking({"Discord": 0.5, "Game": 0.5}, 1.0)
            self.assertEqual(audio.apps[1].volume, 32)

    def test_crash_recovery_restores_only_if_volume_still_matches_duck(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = _Audio()
            service = self._service(directory, audio)
            service.save_ducking_rule(
                DuckingRule(
                    name="Chat ducks music",
                    trigger_pattern="discord",
                    target_patterns=["spotify"],
                    reduction_percent=50,
                    threshold=0.01,
                    attack_ms=0,
                    release_ms=500,
                )
            )
            service.tick_ducking({"Discord": 0.5}, 1.0)
            self.assertEqual(audio.apps[1].volume, 40)

            # Simulate process crash: new service reads recovery journal while
            # the target audio session remains at the engine-applied 40%.
            recovered = self._service(directory, audio)
            self.assertTrue(recovered.has_pending_recovery())
            self.assertEqual(recovered.recover_pending(), 1)
            self.assertEqual(audio.apps[1].volume, 80)
            self.assertFalse(recovered.has_pending_recovery())

            # Create another crash journal, then let the user move the volume
            # after the crash. Restart must preserve that manual value.
            service2 = self._service(directory, audio)
            service2.save_ducking_rule(
                DuckingRule(
                    name="Again",
                    trigger_pattern="discord",
                    target_patterns=["spotify"],
                    reduction_percent=50,
                    threshold=0.01,
                    attack_ms=0,
                    release_ms=0,
                )
            )
            service2.tick_ducking({"Discord": 0.5}, 2.0)
            self.assertEqual(audio.apps[1].volume, 40)
            audio.apps[1].volume = 35

            recovered2 = self._service(directory, audio)
            self.assertEqual(recovered2.recover_pending(), 0)
            self.assertEqual(audio.apps[1].volume, 35)
            self.assertFalse(recovered2.has_pending_recovery())

    def test_rules_and_enable_flags_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.save_routing_rule(RoutingRule("Game route", "game", "speakers"))
            service.save_ducking_rule(
                DuckingRule("Chat duck", "discord", ["spotify"], 35, 0.03, 100, 800)
            )
            service.set_routing_enabled(False)
            service.set_ducking_enabled(False)

            reloaded = self._service(directory)
            self.assertFalse(reloaded.routing_enabled)
            self.assertFalse(reloaded.ducking_enabled)
            self.assertEqual(reloaded.routing_rules[0].name, "Game route")
            self.assertEqual(reloaded.ducking_rules[0].reduction_percent, 35)


if __name__ == "__main__":
    unittest.main()
