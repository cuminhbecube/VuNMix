import argparse
import hashlib
import pathlib
import sys
import tempfile
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = DESKTOP_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import generate_release_manifest as generator
from protocol import PROTOCOL_VERSION


class ReleaseManifestGeneratorTests(unittest.TestCase):
    def test_generator_hashes_real_assets_and_emits_release_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            firmware = root / "VuNMix-Firmware-0.8.0.bin"
            setup = root / "VuNMix-Windows-Setup-0.8.0.exe"
            portable = root / "VuNMix-Windows-Portable-0.8.0.zip"
            firmware.write_bytes(b"fw")
            setup.write_bytes(b"setup")
            portable.write_bytes(b"portable")

            args = argparse.Namespace(
                repository="cuminhbecube/VuNMix",
                tag="v0.8.0",
                version="0.8.0",
                firmware=firmware,
                windows_setup=setup,
                windows_portable=portable,
                minimum_desktop_version="v0.5.0",
                minimum_firmware_version="v0.5.0",
            )
            manifest = generator.build_manifest(args)

            self.assertEqual(manifest["version"], "v0.8.0")
            self.assertEqual(manifest["protocol"], PROTOCOL_VERSION)
            self.assertEqual(manifest["assets"]["firmware"]["size"], 2)
            self.assertEqual(
                manifest["assets"]["firmware"]["sha256"],
                hashlib.sha256(b"fw").hexdigest(),
            )
            self.assertEqual(
                manifest["assets"]["windows_setup"]["url"],
                "https://github.com/cuminhbecube/VuNMix/releases/download/v0.8.0/VuNMix-Windows-Setup-0.8.0.exe",
            )

    def test_ci_version_is_normalized_to_parseable_prerelease(self):
        self.assertEqual(generator.normalize_version("ci-abcdef0"), "v0.0.0-ci.abcdef0")


if __name__ == "__main__":
    unittest.main()
