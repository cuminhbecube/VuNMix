"""USB failure regressions on the transport used by the desktop entry point."""

import pathlib
import sys
import threading
import types
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

try:
    import serial
except ModuleNotFoundError:
    # The transport tests also run on hosts without Windows/pyserial installed.
    serial = types.ModuleType("serial")
    serial.SerialException = OSError
    serial.Serial = object
    tools_stub = types.ModuleType("serial.tools")
    ports_stub = types.ModuleType("serial.tools.list_ports")
    ports_stub.comports = lambda: []
    tools_stub.list_ports = ports_stub
    serial.tools = tools_stub
    sys.modules["serial"] = serial
    sys.modules["serial.tools"] = tools_stub
    sys.modules["serial.tools.list_ports"] = ports_stub

from controller_state import HardwareStateMixin
from device_discovery import DeviceIdentity
from diagnostic_serial import DiagnosticSerialService
from protocol import Command


class FakeConnection:
    def __init__(self):
        self.is_open = True
        self.close_count = 0

    def close(self):
        self.close_count += 1
        self.is_open = False


class IconController(HardwareStateMixin):
    def __init__(self, service):
        self.serial = service
        self._icon_cache_lock = threading.RLock()
        self._sent_icon_ids = set()


class ObservedWriteLock:
    """A normal lock with an event for a sender queued behind an active write."""

    def __init__(self, icon_waiting):
        self._lock = threading.Lock()
        self._icon_waiting = icon_waiting
        self.owner = None

    def __enter__(self):
        if threading.current_thread().name == "RegressionIcon":
            self._icon_waiting.set()
        self._lock.acquire()
        self.owner = threading.get_ident()
        return self

    def __exit__(self, *args):
        self.owner = None
        self._lock.release()


class DiagnosticDisconnectRegressionTests(unittest.TestCase):
    def make_service(self):
        service = DiagnosticSerialService(
            "COM_TEST",
            device_identity=DeviceIdentity(vid=0x303A, pid=0x1001),
            port_provider=lambda: [],
        )
        service._serial = FakeConnection()
        service._active_port = "COM_TEST"
        service._connection_generation = 7
        service._connected_since = 123.0
        return service

    def test_stale_disconnect_preserves_new_handle_and_uptime(self):
        service = self.make_service()
        current = service._serial
        service.on_disconnected = mock.Mock()

        service.disconnect(expected_connection=FakeConnection())

        self.assertIs(service._serial, current)
        self.assertTrue(current.is_open)
        self.assertEqual(current.close_count, 0)
        self.assertEqual(service._connection_generation, 7)
        self.assertEqual(service._connected_since, 123.0)
        service.on_disconnected.assert_not_called()

    def test_current_disconnect_closes_transport_and_resets_uptime(self):
        service = self.make_service()
        current = service._serial
        service.on_disconnected = mock.Mock()

        service.disconnect(expected_connection=current)

        self.assertIsNone(service._serial)
        self.assertFalse(current.is_open)
        self.assertEqual(current.close_count, 1)
        self.assertEqual(service._connection_generation, 8)
        self.assertIsNone(service._connected_since)
        service.on_disconnected.assert_called_once_with()

    def test_disconnect_callback_reconnect_keeps_replacement_uptime(self):
        service = self.make_service()
        previous = service._serial
        replacement = FakeConnection()

        def reconnect():
            # A disconnect observer can allow a new connection before the
            # diagnostic override returns from the base lifecycle callback.
            with service._connect_lock:
                service._serial = replacement
                service._connected_since = 456.0

        service.on_disconnected = reconnect
        service.disconnect(expected_connection=previous)

        self.assertFalse(previous.is_open)
        self.assertIs(service._serial, replacement)
        self.assertTrue(replacement.is_open)
        self.assertEqual(service._connected_since, 456.0)

    def test_write_error_returns_false_and_disconnects_real_desktop_transport(self):
        service = self.make_service()
        current = service._serial
        current.write = mock.Mock(side_effect=serial.SerialException("USB removed"))
        service.on_disconnected = mock.Mock()

        self.assertFalse(service.send_command(Command.OK))

        self.assertIsNone(service._serial)
        self.assertEqual(current.close_count, 1)
        self.assertIsNone(service._connected_since)
        self.assertEqual(service._tx_frames, 0)
        service.on_disconnected.assert_called_once_with()

    def test_late_write_failure_cannot_disconnect_replacement_transport(self):
        service = self.make_service()
        previous = service._serial
        replacement = FakeConnection()
        service.on_disconnected = mock.Mock()

        def fail_after_reconnect(payload):
            with service._connect_lock:
                service._serial = replacement
                service._connection_generation += 1
                service._connected_since = 456.0
            raise serial.SerialException("old USB write finished after reconnect")

        previous.write = fail_after_reconnect
        self.assertFalse(service.send_command(Command.OK))

        self.assertIs(service._serial, replacement)
        self.assertTrue(replacement.is_open)
        self.assertEqual(replacement.close_count, 0)
        self.assertEqual(service._connection_generation, 8)
        self.assertEqual(service._connected_since, 456.0)
        service.on_disconnected.assert_not_called()

    def test_read_error_cleans_up_instead_of_escaping_reader(self):
        service = self.make_service()
        stop = threading.Event()
        service._running = True

        class ReadFailure(FakeConnection):
            @property
            def in_waiting(self):
                raise serial.SerialException("USB removed")

        current = service._serial = ReadFailure()
        service.on_disconnected = stop.set
        service._read_loop(stop)

        self.assertTrue(stop.is_set())
        self.assertIsNone(service._serial)
        self.assertEqual(current.close_count, 1)
        self.assertIsNone(service._connected_since)

    def test_write_failure_and_queued_icon_complete_without_lock_inversion(self):
        service = self.make_service()
        controller = IconController(service)
        writer_entered = threading.Event()
        icon_waiting = threading.Event()
        service._write_lock = ObservedWriteLock(icon_waiting)
        callback_under_write_lock = []
        worker_errors = []
        results = {}
        connection = service._serial

        def fail_write(payload):
            writer_entered.set()
            if not icon_waiting.wait(5):
                raise AssertionError("icon sender never queued for write lock")
            connection.is_open = False
            raise serial.SerialException("USB removed with icon transfer queued")

        def disconnected():
            if service._write_lock.owner == threading.get_ident():
                # Record the regression without leaving deadlocked test
                # threads behind when run against an unfixed implementation.
                callback_under_write_lock.append(True)
                return
            with controller._icon_cache_lock:
                controller._clear_sent_icons()

        def run(name, action):
            try:
                results[name] = action()
            except BaseException as error:
                worker_errors.append(error)

        connection.write = fail_write
        service.on_disconnected = disconnected
        heartbeat = threading.Thread(
            target=run,
            args=("heartbeat", lambda: service.send_command(Command.OK)),
            daemon=True,
            name="RegressionHeartbeat",
        )
        icon = threading.Thread(
            target=run,
            args=("icon", lambda: controller._send_cached_icon(1, b"rgb565")),
            daemon=True,
            name="RegressionIcon",
        )
        heartbeat.start()
        self.assertTrue(writer_entered.wait(5))
        icon.start()
        heartbeat.join(5)
        icon.join(5)

        self.assertFalse(heartbeat.is_alive(), "heartbeat deadlocked during disconnect")
        self.assertFalse(icon.is_alive(), "icon sender deadlocked during disconnect")
        self.assertEqual(worker_errors, [])
        self.assertEqual(callback_under_write_lock, [])
        self.assertEqual(results, {"heartbeat": False, "icon": False})
        self.assertIsNone(service._serial)
        self.assertEqual(connection.close_count, 1)


if __name__ == "__main__":
    unittest.main()
