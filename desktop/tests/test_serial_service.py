import pathlib
import sys
import types
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

try:
    import serial  # noqa: F401
except ModuleNotFoundError:
    serial_stub = types.ModuleType("serial")
    serial_stub.SerialException = OSError
    serial_stub.Serial = object
    tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    list_ports_stub.comports = lambda: []
    tools_stub.list_ports = list_ports_stub
    serial_stub.tools = tools_stub
    sys.modules["serial"] = serial_stub
    sys.modules["serial.tools"] = tools_stub
    sys.modules["serial.tools.list_ports"] = list_ports_stub

from device_discovery import DeviceIdentity
from protocol import Command
from serial_service import SerialService


class FakePort:
    def __init__(self, device, *, vid=None, pid=None, serial_number=None, location=None):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.serial_number = serial_number
        self.location = location
        self.product = None
        self.manufacturer = None


class FakeSerial:
    def __init__(self):
        self.port = None
        self.baudrate = None
        self.timeout = None
        self.write_timeout = None
        self.dtr = None
        self.rts = None
        self.is_open = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass


class SerialServiceTests(unittest.TestCase):
    def test_time_sync_uses_three_wire_bytes(self):
        service = SerialService(
            "COM_TEST",
            device_identity=DeviceIdentity(vid=0x303A, pid=0x1001),
            port_provider=lambda: [],
        )
        sent = []
        service.send_command = lambda command, payload=b"": sent.append((command, payload)) or True

        self.assertTrue(service.send_time_sync(23, 59, 58))
        self.assertEqual(sent, [(Command.TIME_SYNC, b"\x17\x3b\x3a")])

    def test_connect_follows_remembered_device_after_com_renumber(self):
        identity = DeviceIdentity(
            vid=0x303A,
            pid=0x1001,
            serial_number="VU123",
            location="1-2",
        )
        current = FakePort(
            "COM19",
            vid=0x303A,
            pid=0x1001,
            serial_number="VU123",
            location="1-2",
        )
        service = SerialService(
            "COM14",
            device_identity=identity,
            port_provider=lambda: [current],
        )

        with (
            mock.patch("serial_service.serial.Serial", side_effect=FakeSerial),
            mock.patch("serial_service.time.sleep"),
        ):
            self.assertTrue(service.connect())

        self.assertEqual(service.port, "COM19")
        self.assertEqual(service.preferred_port, "COM19")
        self.assertTrue(service.is_connected)

    def test_ambiguous_identical_boards_are_not_opened(self):
        ports = [
            FakePort("COM7", vid=0x303A, pid=0x1001, serial_number="A"),
            FakePort("COM8", vid=0x303A, pid=0x1001, serial_number="B"),
        ]
        service = SerialService(
            "COM14",
            device_identity=None,
            port_provider=lambda: ports,
        )
        # Avoid loading any persisted identity from the real test machine.
        service._device_identity = None

        with mock.patch("serial_service.serial.Serial") as serial_factory:
            self.assertFalse(service.connect())

        serial_factory.assert_not_called()
        self.assertIn("Searching", service.status)


if __name__ == "__main__":
    unittest.main()
