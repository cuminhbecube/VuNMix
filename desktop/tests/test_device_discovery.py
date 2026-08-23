import pathlib
import sys
import tempfile
import types
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from device_discovery import (
    DeviceIdentity,
    load_device_identity,
    save_device_identity,
    select_device_port,
)


class FakePort:
    def __init__(
        self,
        device,
        *,
        vid=None,
        pid=None,
        serial_number=None,
        product=None,
        manufacturer=None,
        location=None,
    ):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.serial_number = serial_number
        self.product = product
        self.manufacturer = manufacturer
        self.location = location


class DeviceDiscoveryTests(unittest.TestCase):
    def test_remembered_serial_follows_device_to_new_com(self):
        identity = DeviceIdentity(
            vid=0x303A,
            pid=0x1001,
            serial_number="VU123",
            product="USB JTAG/serial debug unit",
            location="1-3",
        )
        ports = [
            FakePort("COM4", vid=0x10C4, pid=0xEA60, serial_number="OTHER"),
            FakePort(
                "COM19",
                vid=0x303A,
                pid=0x1001,
                serial_number="VU123",
                product="USB JTAG/serial debug unit",
                location="1-3",
            ),
        ]

        selected = select_device_port(
            ports,
            identity=identity,
            preferred_port="COM14",
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.device, "COM19")

    def test_serial_identity_survives_application_bootloader_pid_change(self):
        identity = DeviceIdentity(
            vid=0x303A,
            pid=0x4001,
            serial_number="VU123",
            location="1-3",
        )
        bootloader = FakePort(
            "COM22",
            vid=0x303A,
            pid=0x1001,
            serial_number="VU123",
            location="1-3",
        )

        selected = select_device_port([bootloader], identity=identity)

        self.assertIs(selected, bootloader)

    def test_location_follows_device_when_serial_number_is_missing(self):
        identity = DeviceIdentity(
            vid=0x303A,
            pid=0x1001,
            location="2-1.4",
        )
        ports = [
            FakePort("COM9", vid=0x303A, pid=0x1001, location="2-1.5"),
            FakePort("COM10", vid=0x303A, pid=0x1001, location="2-1.4"),
        ]

        selected = select_device_port(ports, identity=identity)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.device, "COM10")

    def test_multiple_identical_boards_are_not_guessed(self):
        ports = [
            FakePort("COM7", vid=0x303A, pid=0x1001, serial_number="A"),
            FakePort("COM8", vid=0x303A, pid=0x1001, serial_number="B"),
        ]

        self.assertIsNone(select_device_port(ports))

    def test_preferred_known_board_disambiguates_multiple_devices(self):
        ports = [
            FakePort("COM7", vid=0x303A, pid=0x1001, serial_number="A"),
            FakePort("COM8", vid=0x303A, pid=0x1001, serial_number="B"),
        ]

        selected = select_device_port(ports, preferred_port="COM8")

        self.assertIsNotNone(selected)
        self.assertEqual(selected.device, "COM8")

    def test_stale_identity_does_not_open_unrelated_reused_com_number(self):
        identity = DeviceIdentity(
            vid=0x303A,
            pid=0x1001,
            serial_number="OLD-BOARD",
        )
        unrelated = FakePort(
            "COM14",
            vid=0x10C4,
            pid=0xEA60,
            serial_number="UART",
        )

        selected = select_device_port(
            [unrelated],
            identity=identity,
            preferred_port="COM14",
        )

        self.assertIsNone(selected)

    def test_identity_round_trip(self):
        identity = DeviceIdentity(
            vid=0x303A,
            pid=0x1001,
            serial_number="VU123",
            product="VuNMix",
            manufacturer="Espressif",
            location="1-3",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "device_identity.json"
            save_device_identity(identity, path)
            loaded = load_device_identity(path)

        self.assertEqual(loaded, identity)


if __name__ == "__main__":
    unittest.main()
