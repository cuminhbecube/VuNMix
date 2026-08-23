import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

try:
    import esptool  # noqa: F401
except ModuleNotFoundError:
    esptool_stub = types.ModuleType("esptool")
    esptool_stub.main = lambda _args: None
    sys.modules["esptool"] = esptool_stub

from firmware_updater import (
    FirmwareValidationError,
    flash_firmware,
    validate_firmware,
)


class FirmwareUpdaterTests(unittest.TestCase):
    def test_rejects_non_bin_and_invalid_images(self):
        with tempfile.TemporaryDirectory() as directory:
            text = pathlib.Path(directory) / "firmware.txt"
            text.write_bytes(b"\xE9" + b"\0" * 4095)

            with self.assertRaises(FirmwareValidationError):
                validate_firmware(str(text))

            invalid = pathlib.Path(directory) / "firmware.bin"
            invalid.write_bytes(b"\0" * 4096)

            with self.assertRaises(FirmwareValidationError):
                validate_firmware(str(invalid))

    def test_flash_writes_image_in_one_esptool_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = pathlib.Path(directory) / "firmware.bin"
            firmware.write_bytes(b"\xE9" * (0x40000 * 2 + 17))

            calls = []
            progress = []

            with (
                mock.patch(
                    "firmware_updater.validate_firmware",
                    return_value=firmware,
                ),
                mock.patch(
                    "firmware_updater._resolve_flash_port",
                    return_value="COM_TEST",
                ),
                mock.patch(
                    "esptool.main",
                    side_effect=lambda args: calls.append(list(args)),
                ),
                mock.patch("firmware_updater.time.sleep"),
            ):
                flash_firmware(
                    "COM_TEST",
                    str(firmware),
                    progress=lambda value, text: progress.append((value, text)),
                )

            self.assertEqual(len(calls), 1)
            self.assertNotIn("--no-stub", calls[0])
            self.assertIn("0x10000", calls[0])
            self.assertIn(str(firmware), calls[0])
            self.assertEqual(progress[-1][0], 1.0)

    def test_flash_uses_resolved_com_after_device_renumber(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = pathlib.Path(directory) / "firmware.bin"
            firmware.write_bytes(b"\xE9" * 8192)
            calls = []

            with (
                mock.patch(
                    "firmware_updater.validate_firmware",
                    return_value=firmware,
                ),
                mock.patch(
                    "firmware_updater._resolve_flash_port",
                    return_value="COM19",
                ) as resolver,
                mock.patch(
                    "esptool.main",
                    side_effect=lambda args: calls.append(list(args)),
                ),
                mock.patch("firmware_updater.time.sleep"),
            ):
                flash_firmware("COM14", str(firmware))

            resolver.assert_called_once_with("COM14")
            self.assertEqual(len(calls), 1)
            port_index = calls[0].index("--port") + 1
            self.assertEqual(calls[0][port_index], "COM19")

    def test_flash_supports_windowed_pyinstaller_without_stdio(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = pathlib.Path(directory) / "firmware.bin"
            firmware.write_bytes(b"\xE9" * 8192)

            observed = {}

            def fake_esptool_main(_args):
                observed["stdin"] = sys.stdin
                observed["stdout"] = sys.stdout
                observed["stderr"] = sys.stderr
                sys.stdout.flush()
                sys.stderr.flush()

            original_stdin = sys.stdin
            original_stdout = sys.stdout
            original_stderr = sys.stderr

            try:
                sys.stdin = None
                sys.stdout = None
                sys.stderr = None

                with (
                    mock.patch(
                        "firmware_updater.validate_firmware",
                        return_value=firmware,
                    ),
                    mock.patch(
                        "firmware_updater._resolve_flash_port",
                        return_value="COM_TEST",
                    ),
                    mock.patch(
                        "esptool.main",
                        side_effect=fake_esptool_main,
                    ),
                    mock.patch("firmware_updater.time.sleep"),
                ):
                    flash_firmware("COM_TEST", str(firmware))

                self.assertIsNotNone(observed["stdin"])
                self.assertIsNotNone(observed["stdout"])
                self.assertIsNotNone(observed["stderr"])

                self.assertIsNone(sys.stdin)
                self.assertIsNone(sys.stdout)
                self.assertIsNone(sys.stderr)

            finally:
                sys.stdin = original_stdin
                sys.stdout = original_stdout
                sys.stderr = original_stderr

    def test_missing_stub_retries_with_no_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = pathlib.Path(directory) / "firmware.bin"
            firmware.write_bytes(b"\xE9" * 8192)

            calls = []

            def fake_esptool_main(args):
                calls.append(list(args))

                if len(calls) == 1:
                    raise RuntimeError(
                        "Flasher stub data is missing for ESP32-S3."
                    )

            with (
                mock.patch(
                    "firmware_updater.validate_firmware",
                    return_value=firmware,
                ),
                mock.patch(
                    "firmware_updater._resolve_flash_port",
                    return_value="COM_TEST",
                ),
                mock.patch(
                    "esptool.main",
                    side_effect=fake_esptool_main,
                ),
                mock.patch("firmware_updater.time.sleep"),
            ):
                flash_firmware("COM_TEST", str(firmware))

            self.assertEqual(len(calls), 2)
            self.assertNotIn("--no-stub", calls[0])
            self.assertIn("--no-stub", calls[1])
            self.assertLess(
                calls[1].index("--no-stub"),
                calls[1].index("write_flash"),
            )


if __name__ == "__main__":
    unittest.main()
