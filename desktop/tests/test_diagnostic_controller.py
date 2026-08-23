import pathlib
import sys
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from diagnostic_controller import DiagnosticAppController


class _Config:
    com_port = "COM14"
    favorite_apps = []
    update_interval_ms = 500

    class _Settings:
        pass

    device_settings = _Settings()


class DiagnosticControllerTests(unittest.TestCase):
    def test_diagnostic_report_tracks_firmware_identity(self):
        with (
            mock.patch("diagnostic_controller.AppController.__init__", return_value=None),
            mock.patch("diagnostic_controller.DiagnosticSerialService") as serial_cls,
        ):
            controller = object.__new__(DiagnosticAppController)
            controller.config = _Config()
            controller._firmware_update_lock = mock.MagicMock()
            controller._firmware_updating = False
            controller._firmware_version = "v0.5.0"
            controller._firmware_protocol = 1
            controller._last_update_log = r"C:\logs\update.log"
            controller.serial = serial_cls.return_value
            controller.serial.health_snapshot.return_value = {
                "port": "COM19",
                "rx_frames": 10,
                "tx_frames": 20,
                "crc_errors": 1,
                "reconnect_count": 2,
            }

            report = controller.diagnostic_report()

        self.assertIn("Firmware version: v0.5.0", report)
        self.assertIn("port: COM19", report)
        self.assertIn("crc_errors: 1", report)


if __name__ == "__main__":
    unittest.main()
