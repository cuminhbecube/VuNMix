import pathlib
import sys
import threading
import types
import unittest
from types import SimpleNamespace
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from app_controller import AppController
from controller_device import DeviceLifecycleMixin
from controller_state import HardwareStateMixin
from gui import TrayApp
from protocol import DisplayMode, SessionData, SessionIndex, SessionInfo, VolumeData
from serial_service import SerialService


class FakePort:
    def __init__(self, device="COM77"):
        self.device = device
        self.vid = 0x303A
        self.pid = 0x1001
        self.serial_number = "QA-VUNMIX"
        self.location = "1-9"
        self.product = "VuNMix"
        self.manufacturer = "QA"


class FakeSerialConnection:
    def __init__(self):
        self.port = None
        self.baudrate = None
        self.timeout = None
        self.write_timeout = None
        self.dtr = None
        self.rts = None
        self.is_open = False
        self.in_waiting = 0

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def write(self, data):
        return len(data)

    def flush(self):
        pass

    def read(self, _count):
        return b""


class SerialLifecycleStressTests(unittest.TestCase):
    def test_100_independent_connect_disconnect_cycles_reset_transport_state(self):
        port = FakePort()
        service = SerialService(
            "COM77",
            device_identity=None,
            port_provider=lambda: [port],
        )
        service._device_identity = None
        disconnects = []
        service.on_disconnected = lambda: disconnects.append(1)

        with (
            mock.patch("serial_service.serial.Serial", side_effect=FakeSerialConnection),
            mock.patch("serial_service.time.sleep", return_value=None),
        ):
            for cycle in range(100):
                self.assertTrue(service.connect(), cycle)
                self.assertTrue(service.is_connected, cycle)
                service._last_protocol_rx = 10.0
                service._last_test_response = 11.0
                service._last_ok_response = 12.0
                service.disconnect()
                self.assertFalse(service.is_connected, cycle)
                self.assertEqual(service.last_protocol_rx, 0.0, cycle)
                self.assertEqual(service.last_test_response, 0.0, cycle)
                self.assertEqual(service.last_ok_response, 0.0, cycle)

        self.assertEqual(len(disconnects), 100)

    def test_parallel_disconnect_is_idempotent_and_callback_fires_once(self):
        port = FakePort()
        service = SerialService(
            "COM77",
            device_identity=None,
            port_provider=lambda: [port],
        )
        service._device_identity = None
        callback_count = 0
        callback_lock = threading.Lock()

        def disconnected():
            nonlocal callback_count
            with callback_lock:
                callback_count += 1

        service.on_disconnected = disconnected

        with (
            mock.patch("serial_service.serial.Serial", side_effect=FakeSerialConnection),
            mock.patch("serial_service.time.sleep", return_value=None),
        ):
            self.assertTrue(service.connect())
            workers = [threading.Thread(target=service.disconnect) for _ in range(24)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=2.0)
                self.assertFalse(worker.is_alive())

        self.assertFalse(service.is_connected)
        self.assertEqual(callback_count, 1)

    def test_stop_does_not_attempt_to_join_its_own_serial_thread(self):
        service = SerialService(
            "COM77",
            device_identity=None,
            port_provider=lambda: [],
        )
        service._read_thread = threading.current_thread()
        service._running = True

        # A callback running on SerialRead must be able to stop transport
        # without RuntimeError("cannot join current thread").
        service.stop()

        self.assertFalse(service._running)
        self.assertIsNone(service._read_thread)


class FakeLifecycleSerial:
    def __init__(self):
        self.is_connected = True
        self.disconnect_calls = 0
        self.commands = []
        self.settings_calls = 0
        self.time_calls = 0

    def send_test(self):
        return True

    def send_command(self, command):
        self.commands.append(command)
        return True

    def send_settings(self, _settings):
        self.settings_calls += 1
        return True

    def send_time_sync(self, _h, _m, _s):
        self.time_calls += 1
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False


class FakeAudio:
    def refresh(self):
        pass

    def get_session_count(self, _mode):
        return 1


class LifecycleHarness(DeviceLifecycleMixin):
    def __init__(self):
        self.serial = FakeLifecycleSerial()
        self.audio = FakeAudio()
        self.config = SimpleNamespace(device_settings=object())
        self._connection_lock = threading.RLock()
        self._device_connected = False
        self._update_only_connected = False
        self._handshake_in_progress = False
        self._handshake_token = 3
        self._is_sleeping = False
        self._running = True
        self._session_info = SimpleNamespace(mode=DisplayMode.MODE_OUTPUT)
        self._sent_icon_ids = set()
        self.on_connection_changed = mock.Mock()
        self.on_device_ready = mock.Mock()
        self.full_state_ok = True
        self.full_state_calls = 0

    @property
    def is_connected(self):
        return self._device_connected

    def _push_full_state(self, _mode):
        self.full_state_calls += 1
        return self.full_state_ok


class HandshakeStressTests(unittest.TestCase):
    def test_100_disconnect_callbacks_invalidate_old_handshake_tokens(self):
        controller = LifecycleHarness()
        start = controller._handshake_token

        for cycle in range(100):
            controller.serial.is_connected = True
            controller._device_connected = True
            controller._update_only_connected = True
            controller._handshake_in_progress = bool(cycle % 2)
            controller._on_device_disconnected()
            self.assertFalse(controller._device_connected, cycle)
            self.assertFalse(controller._update_only_connected, cycle)
            self.assertFalse(controller._handshake_in_progress, cycle)

        self.assertEqual(controller._handshake_token, start + 100)

    def test_stalled_compatible_handshake_is_disconnected_by_watchdog(self):
        controller = LifecycleHarness()
        targets = []

        class CapturedThread:
            def __init__(self, target=None, **_kwargs):
                self.target = target

            def start(self):
                targets.append(self.target)

        with (
            mock.patch("controller_device.threading.Thread", CapturedThread),
            mock.patch("controller_device.time.sleep", return_value=None),
        ):
            controller._on_device_connected()

        self.assertEqual(len(targets), 1)
        controller._update_only_connected = True
        controller._handshake_in_progress = True
        targets[0]()

        self.assertEqual(controller.serial.disconnect_calls, 1)

    def test_protocol_mismatch_update_only_mode_is_not_killed_by_watchdog(self):
        controller = LifecycleHarness()
        targets = []

        class CapturedThread:
            def __init__(self, target=None, **_kwargs):
                self.target = target

            def start(self):
                targets.append(self.target)

        with (
            mock.patch("controller_device.threading.Thread", CapturedThread),
            mock.patch("controller_device.time.sleep", return_value=None),
        ):
            controller._on_device_connected()

        controller._update_only_connected = True
        controller._handshake_in_progress = False
        targets[0]()

        self.assertEqual(controller.serial.disconnect_calls, 0)

    def test_handshake_rejects_failed_full_state_transfer(self):
        controller = LifecycleHarness()
        controller.full_state_ok = False

        with (
            mock.patch("controller_device.time.sleep", return_value=None),
            mock.patch("controller_device.comtypes.CoInitialize", return_value=None),
            mock.patch("controller_device.comtypes.CoUninitialize", return_value=None),
        ):
            controller._complete_handshake(controller._handshake_token)

        self.assertFalse(controller._device_connected)
        self.assertEqual(controller.serial.disconnect_calls, 1)
        controller.on_connection_changed.assert_not_called()
        controller.on_device_ready.assert_not_called()


    def test_stale_handshake_generation_cannot_clear_new_handshake_flag(self):
        controller = LifecycleHarness()
        controller._handshake_token = 20
        controller._handshake_in_progress = True

        with (
            mock.patch("controller_device.time.sleep", return_value=None),
            mock.patch("controller_device.comtypes.CoInitialize", return_value=None),
            mock.patch("controller_device.comtypes.CoUninitialize", return_value=None),
        ):
            controller._complete_handshake(19)

        self.assertTrue(controller._handshake_in_progress)
        self.assertEqual(controller.serial.disconnect_calls, 0)
        self.assertEqual(controller.full_state_calls, 0)

    def test_old_handshake_aborts_before_writing_state_to_new_connection(self):
        controller = LifecycleHarness()
        controller._handshake_token = 30
        controller._handshake_in_progress = True

        def replace_connection_generation():
            controller._handshake_token = 31
            controller._handshake_in_progress = True

        controller.audio.refresh = replace_connection_generation

        with (
            mock.patch("controller_device.time.sleep", return_value=None),
            mock.patch("controller_device.comtypes.CoInitialize", return_value=None),
            mock.patch("controller_device.comtypes.CoUninitialize", return_value=None),
        ):
            controller._complete_handshake(30)

        self.assertEqual(controller.full_state_calls, 0)
        self.assertTrue(controller._handshake_in_progress)
        self.assertEqual(controller.serial.disconnect_calls, 0)


class ResumeStormTests(unittest.TestCase):
    def test_50_resume_events_coalesce_to_one_recovery_worker(self):
        controller = LifecycleHarness()
        created = []

        class FakeThread:
            def __init__(self, target=None, name=None, **_kwargs):
                self.target = target
                self.name = name
                self._alive = False
                created.append(self)

            def start(self):
                self._alive = True

            def is_alive(self):
                return self._alive

        with mock.patch("controller_device.threading.Thread", FakeThread):
            for _ in range(50):
                controller._on_pc_resume()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].name, "ResumeSync")
        self.assertTrue(getattr(controller, "_resume_recovering", False))


class _StateItem:
    def __init__(self, item_id=1, name="Speakers"):
        self.id = item_id
        self.name = name
        self.is_default = True

    def to_session_data(self):
        return SessionData(
            name=self.name,
            data=VolumeData(id=self.id, volume=42),
        )


class _StateAudio:
    def __init__(self):
        self.items = [_StateItem()]

    def get_session_count(self, _mode):
        return 1

    def get_sessions_for_mode(self, _mode):
        return list(self.items)


class _StateSerial:
    def __init__(self, fail_at=""):
        self.fail_at = fail_at

    def send_session_info(self, _info):
        return self.fail_at != "info"

    def send_mode_states(self, _states):
        return self.fail_at != "modes"

    def send_session(self, command, _session):
        if self.fail_at == "current" and int(command) == 3:
            return False
        return True

    def send_app_icon(self, *_args, **_kwargs):
        return True


class StateTransferHarness(HardwareStateMixin):
    def __init__(self, fail_at=""):
        self.audio = _StateAudio()
        self.serial = _StateSerial(fail_at)
        self._state_lock = threading.RLock()
        self._selection_epoch = 0
        self._selection_transitioning = False
        self._session_info = SessionInfo(mode=DisplayMode.MODE_OUTPUT)
        self._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        self._sent_icon_ids = set()


class StateTransferStressTests(unittest.TestCase):
    def test_required_handshake_frames_report_partial_write_failures_repeatedly(self):
        for fail_at in ("info", "modes", "current"):
            for cycle in range(40):
                controller = StateTransferHarness(fail_at)
                self.assertFalse(
                    controller._push_full_state(DisplayMode.MODE_OUTPUT),
                    (fail_at, cycle),
                )

    def test_complete_handshake_state_transfer_succeeds_repeatedly(self):
        for cycle in range(100):
            controller = StateTransferHarness()
            self.assertTrue(
                controller._push_full_state(DisplayMode.MODE_OUTPUT),
                cycle,
            )


class CountingService:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


class AppStartStopStressTests(unittest.TestCase):
    def test_start_is_idempotent_and_does_not_duplicate_sync_workers(self):
        controller = AppController.__new__(AppController)
        controller._running = False
        controller._power_monitor = None
        controller.serial = CountingService()
        controller.weather_service = CountingService()
        controller.obs_service = CountingService()
        controller._sync_thread = None
        controller._meter_thread = None

        created_threads = []

        class FakeThread:
            def __init__(self, target=None, name=None, **_kwargs):
                self.target = target
                self.name = name
                created_threads.append(self)

            def start(self):
                pass

            def join(self, timeout=None):
                pass

        with (
            mock.patch("app_controller.PowerMonitor", return_value=object()),
            mock.patch("app_controller.threading.Thread", FakeThread),
        ):
            controller.start()
            controller.start()

        self.assertEqual(controller.serial.start_calls, 1)
        self.assertEqual(controller.weather_service.start_calls, 1)
        self.assertEqual(controller.obs_service.start_calls, 1)
        self.assertEqual([t.name for t in created_threads], ["AudioSync", "AudioMeter"])


class FirmwareAutoUpdateStressTests(unittest.TestCase):
    def test_100_ready_events_coalesce_to_one_auto_firmware_worker(self):
        app = TrayApp.__new__(TrayApp)
        app._firmware_auto_lock = threading.Lock()
        created = []

        class FakeThread:
            def __init__(self, target=None, name=None, **_kwargs):
                self.target = target
                self.name = name
                self._alive = False
                created.append(self)

            def start(self):
                self._alive = True

            def is_alive(self):
                return self._alive

        with mock.patch("gui.threading.Thread", FakeThread):
            for _ in range(100):
                app._on_device_ready()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].name, "FirmwareAutoCheck")


if __name__ == "__main__":
    unittest.main()
