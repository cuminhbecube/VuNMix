"""Deterministic appearance protocol, persistence and transaction regressions."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import threading
import unittest

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))

from config import AppConfig
from device_theme import DeviceThemeCoordinator
from device_theme_preview import load_theme_preview, THEME_ASSET_NAMES
from protocol import (Command, DeviceSettings, DeviceTheme, DEVICE_THEME_NAMES,
                      ThemeOperation, ThemeRequest, ThemeResponse, ThemeStatus)


class ThemeProtocolAndConfigTests(unittest.TestCase):
    def test_ids_and_directional_wire_layout_are_exact(self):
        self.assertEqual(int(Command.UI_THEME), 23)
        self.assertEqual([int(theme) for theme in DeviceTheme], list(range(8)))
        self.assertEqual(ThemeRequest(ThemeOperation.SET, 7, 0x1234).pack(), b'\x01\x07\x34\x12')
        reply = ThemeResponse(0x1234, ThemeStatus.SAVED_DEFERRED, 7, 255)
        self.assertEqual(reply.pack(), b'\x34\x12\x01\x07\xff\x01')
        self.assertEqual(ThemeResponse.unpack(reply.pack()), reply)
        for payload in (b'', b'\x00' * 5, b'\x00' * 7, b'\x01\x00\xff\x00\xff\x01'):
            with self.assertRaises(ValueError):
                ThemeResponse.unpack(payload)

    def test_missing_or_invalid_theme_does_not_reset_legacy_preferences(self):
        for value in (None, -1, 8, 99, True, '3', 2.5):
            config = AppConfig._from_dict({'device_theme_id': value,
                                         'settings': {'clock_style': 15, 'led_brightness': 73}})
            self.assertIsNone(config.device_theme_id)
            self.assertEqual(config.device_settings.clock_style, 15)
            self.assertEqual(config.device_settings.led_brightness, 73)

    def test_all_themes_persist_separately_and_never_change_clock_wire_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'config.json')
            for clock in range(16):
                settings = DeviceSettings(clock_style=clock, sleep_enabled=False)
                baseline = settings.pack()
                for theme in range(8):
                    config = AppConfig(device_theme_id=theme, device_settings=settings)
                    config.save(path)
                    loaded = AppConfig.load(path)
                    self.assertEqual(loaded.device_theme_id, theme)
                    self.assertEqual(loaded.device_settings.pack(), baseline)
                    self.assertEqual(len(baseline), 19)
                    self.assertNotIn('device_theme_id', json.loads(Path(path).read_text())['settings'])
            self.assertFalse(Path(path + '.tmp').exists())

    def test_native_preview_assets_are_distinct_valid_and_independent(self):
        manifest = json.loads((DESKTOP / 'assets/device_themes/manifest.json').read_text())
        self.assertEqual(manifest['resolution'], [320, 240])
        self.assertEqual([entry['id'] for entry in manifest['themes']], list(range(8)))
        pixels = set()
        for entry in manifest['themes']:
            theme = entry['id']
            self.assertEqual(entry['name'], DEVICE_THEME_NAMES[theme])
            self.assertEqual(entry['file'], THEME_ASSET_NAMES[theme] + '.png')
            data = (DESKTOP / 'assets/device_themes' / entry['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
            frame = load_theme_preview(theme)
            self.assertEqual((frame.size, frame.mode), ((320, 240), 'RGB'))
            original = frame.tobytes()
            pixels.add(hashlib.sha256(original).hexdigest())
            frame.paste('red', (0, 0, 320, 240))
            self.assertEqual(load_theme_preview(theme).tobytes(), original)
        self.assertEqual(len(pixels), 8)


class ThemeTransactionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.sent = []
        self.sync = DeviceThemeCoordinator(
            lambda request, generation: self.sent.append((request, generation)) or True,
            clock=lambda: self.now, timeout=1.0, max_attempts=3,
        )

    def connect(self, theme=0, *, desired=None, mask=255, generation=7):
        self.sync.set_desired(desired)
        self.sync.connected(generation)
        query = self.sync.poll()
        self.assertEqual(query.operation, ThemeOperation.QUERY)
        self.reply(query, theme, mask=mask, generation=generation)
        return query

    def reply(self, request, theme, status=ThemeStatus.APPLIED, *, mask=255, generation=7, schema=1):
        return self.sync.handle_response(ThemeResponse(request.request_id, status, theme, mask, schema).pack(), generation)

    def test_unset_preference_queries_and_follows_device_without_writing_a_theme(self):
        self.connect(theme=5)
        self.assertIsNone(self.sync.poll())
        self.assertIsNone(self.sync.snapshot().desired_id)
        self.assertEqual(self.sync.snapshot().confirmed_id, 5)
        self.assertEqual(len(self.sent), 1)

    def test_write_success_and_unrelated_ack_do_not_confirm_theme(self):
        self.connect(desired=3)
        request = self.sync.poll()
        self.assertEqual(request.operation, ThemeOperation.SET)
        self.assertEqual(self.sync.snapshot().phase, 'applying')
        self.assertEqual(self.sync.snapshot().confirmed_id, 0)
        self.assertFalse(self.sync.handle_response(b'', 7))
        wrong = ThemeResponse(request.request_id + 1, ThemeStatus.APPLIED, 3, 255)
        self.assertFalse(self.sync.handle_response(wrong.pack(), 7))
        self.assertEqual(self.sync.snapshot().confirmed_id, 0)
        self.assertTrue(self.reply(request, 3))
        self.assertEqual(self.sync.snapshot().phase, 'applied')

    def test_clock_or_sleep_ack_is_explicitly_deferred(self):
        self.connect(desired=2)
        self.reply(self.sync.poll(), 2, ThemeStatus.SAVED_DEFERRED)
        state = self.sync.snapshot()
        self.assertEqual((state.confirmed_id, state.phase), (2, 'deferred'))
        self.assertIn('after clock or sleep', state.message)
        self.assertIsNone(self.sync.poll())

    def test_latest_saved_choice_wins_even_when_returning_to_previous_confirmed_theme(self):
        self.connect()
        self.sync.set_desired(3)
        old = self.sync.poll()
        self.sync.set_desired(0)
        latest = self.sync.poll()
        self.assertEqual(latest.theme_id, 0)
        self.assertNotEqual(old.request_id, latest.request_id)
        self.assertFalse(self.reply(old, 3))
        self.assertTrue(self.reply(latest, 0))
        self.assertEqual(self.sync.snapshot().confirmed_id, 0)

    def test_reconnection_requeries_and_rejects_old_generation_or_request(self):
        self.connect(desired=6)
        old = self.sync.poll()
        self.sync.disconnected()
        self.sync.connected(9)
        query = self.sync.poll()
        self.assertFalse(self.reply(old, 6))
        self.assertFalse(self.reply(query, 0, generation=7))
        self.assertTrue(self.reply(query, 0, generation=9))
        current = self.sync.poll()
        self.assertEqual(current.theme_id, 6)
        self.assertEqual(self.sent[-1][1], 9)

    def test_silent_old_firmware_has_only_three_queries_and_remains_connected(self):
        self.sync.connected(7)
        for _ in range(6):
            self.sync.poll()
            self.now += 1.1
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(len({item[0].request_id for item in self.sent}), 1)
        state = self.sync.snapshot()
        self.assertTrue(state.connected)
        self.assertEqual(state.phase, 'unsupported')

    def test_busy_duplicates_cannot_extend_a_request_forever(self):
        self.sync.connected(7)
        for _ in range(3):
            request = self.sync.poll()
            self.now += 0.5
            self.reply(request, 0, ThemeStatus.BUSY)
            self.now += 0.6
        self.assertIsNone(self.sync.poll())
        self.assertEqual(self.sync.snapshot().phase, 'unsupported')
        self.assertEqual(len(self.sent), 3)

    def test_unsupported_theme_is_kept_as_desired_without_sending_a_set(self):
        self.connect(desired=7, mask=1)
        self.assertIsNone(self.sync.poll())
        self.assertEqual(self.sync.snapshot().phase, 'unsupported')
        self.assertEqual(self.sync.snapshot().desired_id, 7)
        self.assertEqual(len(self.sent), 1)

    def test_unknown_schema_disables_only_the_optional_feature(self):
        self.sync.connected(7)
        query = self.sync.poll()
        self.reply(query, 0, schema=2)
        self.assertEqual(self.sync.snapshot().phase, 'unsupported')
        self.assertTrue(self.sync.snapshot().connected)

    def test_mismatched_configured_theme_never_replaces_confirmed_state(self):
        self.connect(desired=4)
        self.reply(self.sync.poll(), 2)
        self.assertEqual(self.sync.snapshot().phase, 'error')
        self.assertEqual(self.sync.snapshot().confirmed_id, 0)

    def test_failed_set_keeps_preference_and_explicit_retry_queries_actual_state(self):
        self.connect(desired=4)
        self.reply(self.sync.poll(), 0, ThemeStatus.FAILED)
        self.assertEqual(self.sync.snapshot().phase, 'error')
        self.assertEqual(self.sync.snapshot().desired_id, 4)
        self.sync.retry()
        query = self.sync.poll()
        self.assertEqual(query.operation, ThemeOperation.QUERY)
        self.reply(query, 4)
        self.assertEqual(self.sync.snapshot().phase, 'applied')
        self.assertIsNone(self.sync.poll())

    def test_blocked_sender_does_not_block_state_updates_or_ui_snapshot(self):
        entered, release, changed = threading.Event(), threading.Event(), threading.Event()
        def sender(request, generation):
            entered.set()
            return release.wait(2)
        sync = DeviceThemeCoordinator(sender)
        sync.start()
        try:
            sync.connected(1)
            self.assertTrue(entered.wait(1))
            updater = threading.Thread(target=lambda: (sync.set_desired(3), sync.snapshot(), changed.set()))
            updater.start()
            self.assertTrue(changed.wait(1))
            updater.join(timeout=1)
        finally:
            release.set()
            sync.stop()


if __name__ == '__main__':
    unittest.main()
