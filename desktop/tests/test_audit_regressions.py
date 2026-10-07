"""Regression scenarios for the eight long-running audit findings."""
import ast
import logging
import pathlib
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from test_app_controller import AppController
from test_audio_automation import _Audio
from audio_automation_service import AudioAutomationService, DuckingRule
from controller_device import DeviceLifecycleMixin
from controller_state import HardwareStateMixin
from controller_workers import SyncWorkersMixin
from protocol import DisplayMode, SessionInfo, SessionData, SessionIndex

DESKTOP = pathlib.Path(__file__).resolve().parents[1]


def extracted_class(filename, class_name, methods, namespace):
    """Use actual method bodies without importing Windows/UI dependencies."""
    tree = ast.parse((DESKTOP / filename).read_text(encoding='utf-8'))
    source = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    cls = ast.ClassDef(name=class_name, bases=[], keywords=[], decorator_list=[],
                       body=[n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in methods])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, str(DESKTOP / filename), 'exec'), namespace)
    return namespace[class_name]


class AuditRegressions(unittest.TestCase):
    def test_reconnect_storm_coalesces_blocked_initial_enumeration(self):
        class Controller(DeviceLifecycleMixin):
            pass
        controller = Controller()
        controller._connection_lock = threading.RLock()
        controller._device_connected = True
        controller.serial = SimpleNamespace(is_connected=True)
        started, release = threading.Event(), threading.Event()
        controller.audio = SimpleNamespace(refresh=lambda: (started.set(), release.wait(2)))
        controller._push_full_state = mock.Mock(return_value=True)
        workers = set()
        try:
            for token in range(1, 201):
                controller._handshake_token = token
                controller._schedule_initial_state_sync(token)
                workers.add(controller._initial_sync_thread)
                self.assertTrue(started.wait(1))
            self.assertEqual(len(workers), 1)
        finally:
            release.set()
            for worker in workers:
                worker.join(2)
        controller._push_full_state.assert_called_once()

    def test_blocked_worker_is_replaced_only_after_old_generation_exits(self):
        controller = AppController.__new__(AppController)
        controller._worker_lock = threading.RLock()
        controller._worker_stop = threading.Event()
        controller._running = True
        controller._sync_thread = None
        release, entered, replacement = threading.Event(), threading.Event(), threading.Event()
        events = []
        def target(stop):
            events.append(stop)
            if len(events) == 1:
                entered.set()
                release.wait(2)
            else:
                replacement.set()
                stop.wait(2)
        controller._start_worker('_sync_thread', target, 'AuditWorker')
        self.assertTrue(entered.wait(1))
        old = controller._sync_thread
        events[0].set()
        controller._worker_stop = threading.Event()
        for _ in range(200):
            controller._start_worker('_sync_thread', target, 'AuditWorker')
        self.assertIs(controller._sync_thread, old)
        release.set()
        self.assertTrue(replacement.wait(1))
        controller._running = False
        controller._worker_stop.set()
        current = controller._sync_thread
        if current:
            current.join(2)
        self.assertEqual(len(events), 2)
        self.assertIsNot(events[0], events[1])
        self.assertTrue(events[0].is_set())

    def test_audio_selection_survives_reorder_and_rejects_deleted_identity(self):
        service_class = extracted_class('audio_service.py', 'AudioService', {'_selected_item'}, {})
        service = service_class()
        a = SimpleNamespace(_device_id='', _session_identifier='A')
        b = SimpleNamespace(_device_id='', _session_identifier='B')
        service.get_sessions_for_mode = lambda mode: [b, a]
        self.assertIs(service._selected_item(3, 0, a), a)
        service.get_sessions_for_mode = lambda mode: [b]
        self.assertIsNone(service._selected_item(3, 0, a))

    def _duck_service(self, directory):
        audio = _Audio()
        service = AudioAutomationService(audio, str(pathlib.Path(directory) / 'automation.json'))
        service.save_ducking_rule(DuckingRule(name='Voice', trigger_pattern='Discord', target_patterns=['Spotify'],
                                           reduction_percent=50, attack_ms=0, release_ms=0))
        return service, audio

    def test_recovery_does_not_restore_currently_active_ducking(self):
        with tempfile.TemporaryDirectory() as directory:
            service, audio = self._duck_service(directory)
            service.tick_ducking({'Discord': 1}, 1)
            self.assertEqual(audio.apps[1].volume, 40)
            self.assertEqual(service.recover_pending(), 0)
            service.tick_ducking({'Discord': 1}, 2)
            self.assertEqual(audio.apps[1].volume, 40)
            service.tick_ducking({}, 3)
            self.assertEqual(audio.apps[1].volume, 80)
            self.assertFalse(service.has_pending_recovery())

    def test_vanished_sessions_are_bounded_and_expire(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch('audio_automation_service.time.time', return_value=100):
            service, audio = self._duck_service(directory)
            original = audio.apps[1]
            for number in range(300):
                audio.apps = [SimpleNamespace(**{**vars(original), '_session_identifier': str(number), 'volume': 80})]
                service.tick_ducking({'Discord': 1}, number)
            audio.apps = []
            service.tick_ducking({'Discord': 1}, 301)
            self.assertEqual(len(service._duck_states), 0)
            self.assertLessEqual(len(service._recovery), 256)
            with mock.patch('audio_automation_service.time.time', return_value=131):
                service.recover_pending()
            self.assertFalse(service._recovery)

    def test_steady_ducking_does_not_write_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            service, audio = self._duck_service(directory)
            service.tick_ducking({'Discord': 1}, 1)
            with mock.patch('audio_automation_service.os.fsync') as fsync:
                for tick in range(100):
                    service.tick_ducking({'Discord': 1}, 2 + tick / 10)
                    service.recover_pending()
                fsync.assert_not_called()
            # Real changes still persist immediately for crash recovery.
            loaded = AudioAutomationService(audio, service.path)
            self.assertEqual(loaded.recover_pending(), 1)
            self.assertEqual(audio.apps[1].volume, 80)

    def test_meter_rebuilds_when_identity_changes_at_same_index(self):
        class Controller(SyncWorkersMixin, HardwareStateMixin):
            pass
        controller = Controller()
        controller._running = controller._device_connected = True
        controller._is_sleeping = False
        controller._session_info = SessionInfo(mode=DisplayMode.MODE_APPLICATION, current=0)
        controller._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        a = SimpleNamespace(id=1, name='A', _session_identifier='A')
        b = SimpleNamespace(id=2, name='B', _session_identifier='B')
        items, created, closed = [a], [], []
        def create(mode, index, *, expected_item):
            created.append(expected_item.name)
            return expected_item.name
        def read(meter):
            if meter == 'A':
                items[:] = [b]
            else:
                controller._running = False
            return (0.5, 0.5)
        controller.audio = SimpleNamespace(get_sessions_for_mode=lambda mode: list(items),
                                         create_peak_meter=create, close_peak_meter=closed.append,
                                         read_stereo_peak_meter=read)
        controller.serial = SimpleNamespace(send_meter=lambda meter: None, is_connected=True)
        with mock.patch('controller_workers.time.sleep'):
            controller._meter_loop()
        self.assertEqual(created, ['A', 'B'])
        self.assertIn('A', closed)
        self.assertIn('B', closed)

    def test_ninth_icon_eviction_causes_resend_on_return(self):
        controller = HardwareStateMixin()
        controller._sent_icon_ids = set()
        controller.serial = SimpleNamespace(send_app_icon=mock.Mock(return_value=True))
        with mock.patch('controller_state.app_icon_rgb565', return_value=b'icon'):
            for identifier in range(1, 10):
                controller._send_app_icon_if_needed(DisplayMode.MODE_APPLICATION,
                                                    SimpleNamespace(id=identifier, name=str(identifier)))
            self.assertNotIn(1, controller._sent_icon_ids)
            controller._send_app_icon_if_needed(DisplayMode.MODE_APPLICATION, SimpleNamespace(id=1, name='1'))
        self.assertEqual(controller.serial.send_app_icon.call_count, 10)
        self.assertEqual(len(controller._sent_icon_ids), 8)

    def test_failed_firmware_lookup_is_retryable_with_single_backoff_timer(self):
        cls = extracted_class('gui.py', 'TrayApp', {'_auto_firmware_update_worker', '_schedule_firmware_retry'},
                              {'log': logging.getLogger('audit'), 'threading': threading, 'APP_VERSION': '0.4.18',
                               'should_auto_update_firmware': lambda *args, **kwargs: True})
        tray = cls()
        tray.config = SimpleNamespace(auto_firmware_update_enabled=True)
        tray.controller = SimpleNamespace(is_connected=True, firmware_updating=False, firmware_version='0.4.17')
        tray._update_stop = mock.Mock()
        tray._update_stop.wait.return_value = False
        tray._firmware_auto_lock = threading.Lock()
        tray._auto_firmware_attempted = set()
        tray._dispatch_ui = mock.Mock()
        tray._firmware_release_client = SimpleNamespace(get_version=mock.Mock(side_effect=[OSError('offline'), SimpleNamespace(tag='v0.4.18')]))
        with mock.patch('threading.Timer') as timer:
            timer.return_value.is_alive.return_value = True
            tray._auto_firmware_update_worker()
            self.assertFalse(tray._auto_firmware_attempted)
            tray._schedule_firmware_retry()
            self.assertEqual(timer.call_count, 1)
            self.assertEqual(timer.call_args.args[0], 60)
            tray._auto_firmware_update_worker()
            tray._auto_firmware_update_worker()
        self.assertEqual(tray._firmware_release_client.get_version.call_count, 2)
        self.assertIn(('0.4.17', '0.4.18'), tray._auto_firmware_attempted)


if __name__ == '__main__':
    unittest.main()
