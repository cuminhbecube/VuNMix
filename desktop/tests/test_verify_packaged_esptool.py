import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from tools.verify_packaged_esptool import verify


class PackagedEsptoolVerifierTests(unittest.TestCase):
    def _write_stub(self, root):
        esptool_dir = root / "_internal" / "esptool" / "targets" / "stub_flasher"
        esptool_dir.mkdir(parents=True)
        (esptool_dir / "stub_flasher_32s3.json").write_text("{}", encoding="utf-8")

    def _write_metadata(self, root, *, version="v0.5.0", sha="abc123def456"):
        metadata_dir = root / "_internal"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        (metadata_dir / "build-metadata.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "git_sha": sha,
                    "build_date": "2026-08-23T15:00:00Z",
                    "protocol_version": 1,
                }
            ),
            encoding="utf-8",
        )

    def test_accepts_package_with_stub_and_matching_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._write_stub(root)
            self._write_metadata(root)

            with mock.patch.dict(
                os.environ,
                {"VERSION": "0.5.0", "GITHUB_SHA": "abc123def456"},
                clear=False,
            ):
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

    def test_rejects_version_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._write_stub(root)
            self._write_metadata(root, version="v0.4.9")

            with mock.patch.dict(
                os.environ,
                {"VERSION": "0.5.0", "GITHUB_SHA": "abc123def456"},
                clear=False,
            ):
                with self.assertRaises(SystemExit) as context:
                    verify(root)

            self.assertIn("version mismatch", str(context.exception))


if __name__ == "__main__":
    unittest.main()
