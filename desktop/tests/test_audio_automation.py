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

    def set_volume(self, mode, index, volume, muted, *, expected_item=None, preserve_mute=False):
        self.volume_calls.append((mode, index, int(volume), bool(muted)))
        item = self.get_sessions_for_mode(mode)[index]
        item.volume = int(volume)
        if not preserve_mute:
            item.is_muted = bool(muted)


class _NativeMuteAudio(_Audio):
    """Windows mute can change before AudioService refreshes its item cache."""

    def __init__(self, muted):
        super().__init__()
        self.apps[1].is_muted = self.native_muted = muted
        self.native_mute_writes = 0

    def set_volume(self, mode, index, volume, muted, *, expected_item=None, preserve_mute=False):
        super().set_volume(mode, index, volume, muted, expected_item=expected_item,
                           preserve_mute=preserve_mute)
        if not preserve_mute:
            self.native_muted = bool(muted)
            self.native_mute_writes += 1


class _Router:
    def __init__(self):
        self.set_calls = []
        self.clear_calls = []

    def set_process_output(self, pid, device_id):
        self.set_calls.append((int(pid), str(device_id)))

    def clear_process_output(self, pid):
        self.clear_calls.append(int(pid))


class _RetryRouter(_Router):
    def __init__(self):
        super().__init__()
        self.active = {}
        self.clear_attempts = 0

    def set_process_output(self, pid, device_id):
        super().set_process_output(pid, device_id)
        self.active[int(pid)] = str(device_id)

    def clear_process_output(self, pid):
        self.clear_attempts += 1
        if self.clear_attempts == 1:
            raise OSError("transient routing backend error")
        super().clear_process_output(pid)
        self.active.pop(int(pid), None)


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

    def test_failed_route_removal_is_retried_after_disabling(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.save_routing_rule(RoutingRule("Chat", "discord", "headset"))
            router = _RetryRouter()
            service.apply_routing_rules(router)
            self.assertEqual(router.active, {1001: "DEV_HEADSET"})

            service.set_routing_enabled(False)
            self.assertEqual(service.apply_routing_rules(router), 0)
            self.assertEqual(router.active, {1001: "DEV_HEADSET"})
            self.assertIn("transient", service.last_routing_error)

            self.assertEqual(service.apply_routing_rules(router), 1)
            self.assertEqual(router.active, {})
            self.assertEqual(router.clear_attempts, 2)
            self.assertEqual(service.last_routing_error, "")

    def test_explicit_cleanup_retains_failed_route_for_periodic_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.save_routing_rule(RoutingRule("Chat", "discord", "headset"))
            router = _RetryRouter()
            service.apply_routing_rules(router)
            service.set_routing_enabled(False)

            service.clear_applied_routes(router)
            self.assertEqual(router.active, {1001: "DEV_HEADSET"})
            service.apply_routing_rules(router)
            self.assertEqual(router.active, {})
            self.assertEqual(router.clear_attempts, 2)

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

    def test_mute_only_changes_survive_release_and_immediate_cleanup(self):
        for initial_muted in (False, True):
            for finish in ("release", "cleanup"):
                with self.subTest(initial_muted=initial_muted, finish=finish):
                    with tempfile.TemporaryDirectory() as directory:
                        audio = _Audio()
                        target = audio.apps[1]
                        target.is_muted = initial_muted
                        service = self._service(directory, audio)
                        service.save_ducking_rule(DuckingRule(
                            "Chat ducks music", "discord", ["spotify"],
                            reduction_percent=50, threshold=0.01,
                            attack_ms=0, release_ms=0,
                        ))
                        service.tick_ducking({"Discord": 0.5}, 1.0)
                        self.assertEqual(target.volume, 40)

                        # A user toggle does not change the numerical volume.
                        target.is_muted = not initial_muted
                        if finish == "release":
                            service.tick_ducking({"Discord": 0.5}, 2.0)
                            service.tick_ducking({"Discord": 0.0}, 3.0)
                        else:
                            # Disable/exit can happen before another worker tick.
                            service.restore_all_ducked()
                        self.assertEqual(target.volume, 80)
                        self.assertEqual(target.is_muted, not initial_muted)
                        self.assertFalse(service.has_pending_recovery())

    def test_crash_recovery_preserves_mute_only_changes(self):
        for initial_muted in (False, True):
            with self.subTest(initial_muted=initial_muted):
                with tempfile.TemporaryDirectory() as directory:
                    audio = _Audio()
                    target = audio.apps[1]
                    target.is_muted = initial_muted
                    service = self._service(directory, audio)
                    service.save_ducking_rule(DuckingRule(
                        "Chat ducks music", "discord", ["spotify"],
                        reduction_percent=50, threshold=0.01,
                        attack_ms=0, release_ms=0,
                    ))
                    service.tick_ducking({"Discord": 0.5}, 1.0)
                    target.is_muted = not initial_muted

                    recovered = self._service(directory, audio)
                    self.assertEqual(recovered.recover_pending(), 1)
                    self.assertEqual(target.volume, 80)
                    self.assertEqual(target.is_muted, not initial_muted)
                    self.assertFalse(recovered.has_pending_recovery())

    def test_all_ducking_writes_preserve_native_mute_with_stale_cache(self):
        for initial_muted in (False, True):
            for phase in ("attack", "release", "cleanup", "recovery"):
                with self.subTest(initial_muted=initial_muted, phase=phase):
                    with tempfile.TemporaryDirectory() as directory:
                        audio = _NativeMuteAudio(initial_muted)
                        service = self._service(directory, audio)
                        service.save_ducking_rule(DuckingRule(
                            "Chat ducks music", "discord", ["spotify"],
                            reduction_percent=50, threshold=0.01,
                            attack_ms=1000 if phase == "attack" else 0,
                            release_ms=0,
                        ))
                        service.tick_ducking({"Discord": 0.5}, 1.0)
                        # The native state changes without a cache refresh.
                        audio.native_muted = not initial_muted
                        self.assertEqual(audio.apps[1].is_muted, initial_muted)

                        if phase == "attack":
                            service.tick_ducking({"Discord": 0.5}, 1.5)
                            self.assertEqual(audio.apps[1].volume, 60)
                        elif phase == "release":
                            service.tick_ducking({}, 2.0)
                        elif phase == "cleanup":
                            service.restore_all_ducked()
                        else:
                            self._service(directory, audio).recover_pending()

                        self.assertEqual(audio.native_muted, not initial_muted)
                        self.assertEqual(audio.native_mute_writes, 0)
                        if phase != "attack":
                            self.assertEqual(audio.apps[1].volume, 80)

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
