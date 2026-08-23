import pathlib
import sys
import tempfile
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from tools.verify_packaged_esptool import verify


class PackagedEsptoolVerifierTests(unittest.TestCase):
    def test_accepts_package_with_esp32s3_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            esptool_dir = root / "_internal" / "esptool" / "targets" / "stub_flasher"
            esptool_dir.mkdir(parents=True)
            (esptool_dir / "stub_flasher_32s3.json").write_text("{}", encoding="utf-8")

            verify(root)

    def test_rejects_package_without_esp32s3_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            esptool_dir = root / "_internal" / "esptool"
            esptool_dir.mkdir(parents=True)
            (esptool_dir / "__init__.py").write_text("", encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                verify(root)

            self.assertIn("ESP32-S3", str(context.exception))
            self.assertIn("flasher-stub", str(context.exception))

    def test_rejects_package_without_esptool_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)

            with self.assertRaises(SystemExit) as context:
                verify(root)

            self.assertIn("does not contain esptool", str(context.exception))


if __name__ == "__main__":
    unittest.main()
