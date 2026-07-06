import pathlib
import sys
import types
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

try:
    import serial  # noqa: F401
except ModuleNotFoundError:
    serial_stub = types.ModuleType("serial")
    serial_stub.SerialException = OSError
    serial_stub.Serial = object
    sys.modules["serial"] = serial_stub

from protocol import Command
from serial_service import SerialService


class SerialServiceTests(unittest.TestCase):
    def test_time_sync_uses_three_wire_bytes(self):
        service = SerialService("COM_TEST")
        sent = []
        service.send_command = lambda command, payload=b"": sent.append((command, payload)) or True

        self.assertTrue(service.send_time_sync(23, 59, 58))
        self.assertEqual(sent, [(Command.TIME_SYNC, b"\x17\x3b\x3a")])


if __name__ == "__main__":
    unittest.main()
