"""Test theme transport on the production DiagnosticSerialService subclass."""
from pathlib import Path
import sys
import threading
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import serial
except ModuleNotFoundError:
    serial = types.ModuleType('serial')
    serial.SerialException = OSError
    serial.Serial = object
    serial.tools = types.ModuleType('serial.tools')
    serial.tools.list_ports = types.ModuleType('serial.tools.list_ports')
    serial.tools.list_ports.comports = lambda: []
    sys.modules.update({'serial': serial, 'serial.tools': serial.tools,
                        'serial.tools.list_ports': serial.tools.list_ports})

from device_discovery import DeviceIdentity
from device_theme import DeviceThemeCoordinator
from diagnostic_serial import DiagnosticSerialService
from protocol import Command, ThemeRequest, ThemeResponse, ThemeOperation, ThemeStatus, encode_frame


class Handle:
    is_open = True
    def __init__(self):
        self.writes = []
    def write(self, data):
        self.writes.append(data)
        return len(data)
    def close(self):
        self.is_open = False


class ThemeTransportTests(unittest.TestCase):
    def make_service(self):
        service = DiagnosticSerialService('COM_TEST', device_identity=DeviceIdentity(vid=1, pid=2),
                                          port_provider=lambda: [])
        service._connection_generation = 8
        service._serial = Handle()
        return service

    def test_guard_reaches_actual_diagnostic_transport_and_preserves_counters(self):
        service = self.make_service()
        request = ThemeRequest(ThemeOperation.SET, 3, 123)
        self.assertFalse(service.send_theme_request(request, expected_generation=7))
        self.assertEqual(service._serial.writes, [])
        self.assertEqual(service.health_snapshot()['tx_frames'], 0)
        self.assertTrue(service.send_theme_request(request, expected_generation=8))
        self.assertEqual(service._serial.writes, [encode_frame(Command.UI_THEME, request.pack())])
        self.assertEqual(service.health_snapshot()['tx_frames'], 1)
        self.assertTrue(service.send_command(Command.OK))
        self.assertEqual(service.health_snapshot()['tx_frames'], 2)

    def test_generation_is_checked_after_waiting_for_write_lock(self):
        service = self.make_service()
        class ReconnectAtLock:
            def __enter__(lock):
                service._connection_generation = 9
                service._serial = Handle()
            def __exit__(lock, *args):
                pass
        service._write_lock = ReconnectAtLock()
        self.assertFalse(service.send_theme_request(ThemeRequest(ThemeOperation.SET, 7, 1),
                                                   expected_generation=8))
        self.assertEqual(service._serial.writes, [])

    def test_serial_stop_used_by_flasher_invalidates_pending_theme_request(self):
        service = self.make_service()
        sync = DeviceThemeCoordinator(
            lambda request, generation: service.send_theme_request(request, expected_generation=generation),
            desired_id=3,
        )
        service.on_disconnected = sync.disconnected
        sync.connected(8)
        query = sync.poll()
        sync.handle_response(ThemeResponse(query.request_id, ThemeStatus.APPLIED, 0, 255).pack(), 8)
        pending = sync.poll()
        handle = service._serial
        service.stop()
        self.assertFalse(handle.is_open)
        self.assertFalse(sync.snapshot().connected)
        self.assertIsNone(sync.poll())
        self.assertFalse(sync.handle_response(
            ThemeResponse(pending.request_id, ThemeStatus.APPLIED, 3, 255).pack(), 8))
        self.assertEqual(sync.snapshot().desired_id, 3)

    def test_theme_ack_bypasses_audio_backlog_but_generic_ok_stays_a_heartbeat(self):
        service = self.make_service()
        reply = ThemeResponse(4, ThemeStatus.APPLIED, 3, 255).pack()
        received = []
        service.on_message = lambda cmd, payload: received.append((cmd, payload))
        service._callback_queue.put((8, Command.SESSION_INFO, b'\x01\x00\x00\x00\x00'))
        class Reader(Handle):
            in_waiting = 30
            def read(self, count):
                if getattr(self, 'done', False):
                    service._running = False
                    return b''
                self.done = True
                return encode_frame(Command.OK) + encode_frame(Command.UI_THEME, reply)
        service._serial = Reader()
        service._running = True
        service._read_loop(threading.Event())
        self.assertEqual(received, [(Command.UI_THEME, reply)])
        self.assertEqual(service._callback_queue.qsize(), 1)
        self.assertGreater(service.last_ok_response, 0)


if __name__ == '__main__':
    unittest.main()
