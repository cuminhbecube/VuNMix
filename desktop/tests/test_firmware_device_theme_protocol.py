"""Exercise actual firmware framing/theme control with serial and NVS doubles."""
import binascii
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def frame(command, payload=b""):
    body = bytes((command, len(payload))) + payload
    return b"\xa5\x5a" + body + struct.pack("<H", binascii.crc_hqx(body, 0xFFFF))


def request(operation=1, theme=6, request_id=0x1234):
    return frame(23, struct.pack("<BBH", operation, theme, request_id))


def reply(status, theme, request_id=0x1234):
    return frame(2) + frame(23, struct.pack("<HBBBB", request_id, status, theme, 255, 1))


class FirmwareDeviceThemeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("Host C++ compiler unavailable; mandatory Linux native gate covers this")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        temporary = Path(cls.directory.name)
        stub = ROOT / "desktop/tests/fixtures/device_theme_serial_stub.hpp"
        (temporary / "Arduino.h").write_text('#include "' + stub.as_posix() + '"\n', encoding="utf-8")
        cls.binary = temporary / "theme-protocol"
        result = subprocess.run([
            compiler, "-std=c++17", "-O2", "-I", str(temporary), "-I", str(ROOT / "src"),
            str(ROOT / "desktop/tests/fixtures/device_theme_protocol_main.cpp"), "-o", str(cls.binary),
        ], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def run_frames(self, data, *, deferred=False):
        result = subprocess.run([str(self.binary), "wire", str(int(deferred)), data.hex()],
                                capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        return tuple(map(int, lines[0].split())), bytes.fromhex(lines[1]) if len(lines) > 1 else b""

    def test_all_themes_preserve_all_clock_settings_and_roll_back_failed_store(self):
        result = subprocess.run([str(self.binary), "control"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_apply_has_correlated_reply_and_duplicate_set_does_not_write_again(self):
        state, output = self.run_frames(request() + request())
        self.assertEqual(state[:4], (2, 1, 1, 6))
        self.assertEqual(output, reply(0, 6) * 2)

    def test_clock_or_sleep_selection_is_saved_without_render_request(self):
        state, output = self.run_frames(request(), deferred=True)
        self.assertEqual(state[:4], (1, 1, 1, 6))
        self.assertEqual(output, reply(1, 6))

    def test_query_reports_configuration_without_selecting_or_writing(self):
        state, output = self.run_frames(request(0, 0, 9))
        self.assertEqual(state[:4], (1, 0, 0, 2))
        self.assertEqual(output, reply(0, 2, 9))

    def test_invalid_id_and_operation_preserve_configuration(self):
        for operation, theme in ((1, 8), (1, 255), (2, 0)):
            with self.subTest(operation=operation, theme=theme):
                state, output = self.run_frames(request(operation, theme))
                self.assertEqual(state[:4], (1, 0, 0, 2))
                self.assertEqual(output, reply(3, 2))

    def test_corrupt_or_wrong_length_frame_never_becomes_theme_request(self):
        corrupt = bytearray(request()); corrupt[-1] ^= 0x80
        for data in (bytes(corrupt), frame(23, b"\x01\x06")):
            state, output = self.run_frames(data)
            self.assertEqual(state[:4], (0, 0, 0, 2))
            self.assertEqual(output, b"")
            self.assertEqual(sum(state[4:6]), 1)

    def test_legacy_settings_cannot_overwrite_theme_and_clock_bits_still_work(self):
        # Original packed 19-byte SETTINGS, clock ID15 at byte3 bit1 + byte4 bits5..7.
        settings = struct.pack("<HBBB", 300, 60 | 0x80, 1 | 2, 15 << 5 & 0xFF)
        settings += bytes((0, 0, 255, 255, 0, 0, 0, 0, 255, 255, 0, 255, 96, 10))
        self.assertEqual(len(settings), 19)
        state, output = self.run_frames(request() + frame(3, settings) + request(0, 0, 99))
        self.assertEqual(state[:4], (2, 1, 1, 6))
        self.assertEqual(state[6], 15)
        self.assertEqual(output, reply(0, 6) + frame(2) + reply(0, 6, 99))


if __name__ == "__main__":
    unittest.main()
