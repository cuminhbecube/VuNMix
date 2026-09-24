import pathlib
import sys
import tempfile
import threading
import unittest
from unittest import mock


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
            self.assertIn("/FORCECLOSEAPPLICATIONS", command)
            self.assertIn("/RESTARTAPPLICATIONS", command)
            self.assertTrue(any(arg.startswith("/LOG=") for arg in command))

    def test_installer_forces_old_app_closed_and_relaunches_after_silent_update(self):
        installer = (DESKTOP_DIR / "VuNMix_Installer.iss").read_text(encoding="utf-8")
        self.assertIn("taskkill /F /IM VuNMix.exe", installer)
        self.assertIn("function PrepareToInstall", installer)
        run_line = next(
            line for line in installer.splitlines()
            if line.startswith('Filename: "{app}\\VuNMix.exe"')
        )
        self.assertIn("runasoriginaluser", run_line)
        self.assertNotIn("skipifsilent", run_line)

    def test_update_shutdown_releases_running_app(self):
        from gui import TrayApp

        app = object.__new__(TrayApp)
        app._update_stop = threading.Event()
        app._settings_dialog = mock.Mock()
        app._icon = mock.Mock()

        TrayApp._shutdown_for_app_update(app)

        self.assertTrue(app._update_stop.is_set())
        app._settings_dialog.request_shutdown.assert_called_once_with()
        app._icon.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
