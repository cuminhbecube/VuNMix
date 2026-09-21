import pathlib
import sys
import tempfile
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from app_updater import (
    AppUpdater,
    UpdateError,
    is_newer_version,
    parse_sha256sums,
    version_tuple,
)


class AppUpdaterTests(unittest.TestCase):
    def test_semver_comparison_only_accepts_stable_release_versions(self):
        self.assertEqual(version_tuple("v0.4.7"), (0, 4, 7))
        self.assertEqual(version_tuple("1.2.3"), (1, 2, 3))
        self.assertIsNone(version_tuple("ci-abcdef0"))
        self.assertIsNone(version_tuple("v1.2.3-beta"))
        self.assertTrue(is_newer_version("v0.4.7", "0.4.8"))
        self.assertFalse(is_newer_version("v0.4.7", "0.4.7"))
        self.assertFalse(is_newer_version("v0.4.7", "0.4.6"))

    def test_release_requires_official_installer_and_checksums(self):
        updater = AppUpdater("v0.4.7")
        release = {
            "tag_name": "v0.4.8",
            "html_url": "https://github.com/cuminhbecube/VuNMix/releases/tag/v0.4.8",
            "draft": False,
            "prerelease": False,
            "body": "notes",
            "assets": [
                {
                    "name": "VuNMix-Windows-Setup-0.4.8.exe",
                    "browser_download_url":
                        "https://github.com/cuminhbecube/VuNMix/releases/download/v0.4.8/"
                        "VuNMix-Windows-Setup-0.4.8.exe",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url":
                        "https://github.com/cuminhbecube/VuNMix/releases/download/v0.4.8/"
                        "SHA256SUMS.txt",
                },
            ],
        }

        info = updater.release_to_update(release)
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.4.8")
        self.assertEqual(info.tag, "v0.4.8")
        self.assertEqual(info.installer_name, "VuNMix-Windows-Setup-0.4.8.exe")

    def test_release_rejects_prerelease_and_same_version(self):
        updater = AppUpdater("v0.4.7")
        base = {
            "tag_name": "v0.4.8",
            "html_url": "",
            "draft": False,
            "prerelease": True,
            "assets": [],
        }
        self.assertIsNone(updater.release_to_update(base))

        base["prerelease"] = False
        base["tag_name"] = "v0.4.7"
        self.assertIsNone(updater.release_to_update(base))

    def test_missing_checksum_asset_is_rejected(self):
        updater = AppUpdater("v0.4.7")
        release = {
            "tag_name": "v0.4.8",
            "html_url": "",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "VuNMix-Windows-Setup-0.4.8.exe",
                    "browser_download_url":
                        "https://github.com/cuminhbecube/VuNMix/releases/download/v0.4.8/"
                        "VuNMix-Windows-Setup-0.4.8.exe",
                }
            ],
        }
        with self.assertRaises(UpdateError):
            updater.release_to_update(release)

    def test_checksum_parser_and_installer_command(self):
        digest = "a" * 64
        parsed = parse_sha256sums(
            f"{digest}  VuNMix-Windows-Setup-0.4.8.exe\n"
        )
        self.assertEqual(
            parsed["VuNMix-Windows-Setup-0.4.8.exe"],
            digest,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "VuNMix-Windows-Setup-0.4.8.exe"
            command = AppUpdater.installer_command(path)
            self.assertEqual(command[0], str(path))
            self.assertIn("/VERYSILENT", command)
            self.assertIn("/CLOSEAPPLICATIONS", command)
            self.assertIn("/RESTARTAPPLICATIONS", command)


if __name__ == "__main__":
    unittest.main()
