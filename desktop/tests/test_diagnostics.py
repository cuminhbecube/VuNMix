import pathlib
import sys
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from diagnostic_serial import CountingFrameParser, DiagnosticSerialService
from diagnostics import build_diagnostic_report
from protocol import Command, encode_frame


class DiagnosticTests(unittest.TestCase):
    def test_counting_parser_tracks_frames_bytes_and_crc_errors(self):
        parser = CountingFrameParser()
        good = encode_frame(Command.OK)
        bad = bytearray(encode_frame(Command.TEST))
        bad[-1] ^= 0xFF

        frames = parser.feed(good + bytes(bad))

        self.assertEqual(frames, [(Command.OK, b"")])
        self.assertEqual(parser.frames, 1)
        self.assertEqual(parser.rx_bytes, len(good) + len(bad))
        self.assertGreaterEqual(parser.crc_errors, 1)

    def test_serial_health_snapshot_has_support_counters(self):
        service = DiagnosticSerialService(port="COM14", port_provider=lambda: [])
        snapshot = service.health_snapshot()
        for key in (
            "port",
            "service_uptime_s",
            "reconnect_count",
            "rx_frames",
            "rx_bytes",
            "tx_frames",
            "tx_bytes",
            "crc_errors",
            "protocol_errors",
        ):
            self.assertIn(key, snapshot)

    def test_report_contains_build_firmware_and_transport_health(self):
        report = build_diagnostic_report(
            {
                "port": "COM19",
                "rx_frames": 123,
                "tx_frames": 456,
                "crc_errors": 2,
                "reconnect_count": 3,
            },
            firmware_version="v0.5.0",
            firmware_protocol=1,
            firmware_updating=False,
            last_update_log=r"C:\Logs\update.log",
        )
        self.assertIn("VuNMix Diagnostic Report", report)
        self.assertIn("Firmware version: v0.5.0", report)
        self.assertIn("Firmware protocol: 1", report)
        self.assertIn("port: COM19", report)
        self.assertIn("crc_errors: 2", report)
        self.assertIn("reconnect_count: 3", report)
        self.assertIn("update.log", report)


if __name__ == "__main__":
    unittest.main()
