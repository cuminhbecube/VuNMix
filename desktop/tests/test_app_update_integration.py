import json
import pathlib
import sys
import tempfile
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_DIR = DESKTOP_DIR.parent
sys.path.insert(0, str(DESKTOP_DIR))

from config import AppConfig


class AppUpdateIntegrationTests(unittest.TestCase):
    def test_auto_update_preference_defaults_on_and_persists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "config.json"

            cfg = AppConfig.load(str(path))
            self.assertTrue(cfg.auto_update_enabled)
            self.assertTrue(cfg.auto_firmware_update_enabled)

            cfg.auto_update_enabled = False
            cfg.auto_firmware_update_enabled = False
            cfg.save(str(path))
            loaded = AppConfig.load(str(path))
            self.assertFalse(loaded.auto_update_enabled)
            self.assertFalse(loaded.auto_firmware_update_enabled)

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("auto_update_enabled", raw)
            self.assertIn("auto_firmware_update_enabled", raw)

    def test_update_worker_marshals_progress_to_main_ui_queue(self):
        source = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")

        self.assertIn('name="AppUpdateWatch"', source)
        self.assertIn('name="AppUpdateCheck"', source)
        self.assertIn('name="AppUpdateInstall"', source)
        self.assertIn("self._dispatch_ui(", source)
        self.assertIn("set_app_update_progress", source)
        self.assertIn("prompt_app_update", source)

    def test_firmware_release_controls_and_auto_sync_are_exposed(self):
        source = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")

        self.assertIn('"Auto FW Update"', source)
        self.assertIn('text="Versions"', source)
        self.assertIn('name="FirmwareReleaseList"', source)
        self.assertIn('name="FirmwareReleaseInstall"', source)
        self.assertIn('name="FirmwareAutoCheck"', source)
        self.assertIn("should_auto_update_firmware(", source)

    def test_connection_tray_exposes_manual_update_check(self):
        source = (REPO_DIR / "desktop" / "connection_ui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('MenuItem("Check app update", self._on_check_app_update)', source)
        self.assertIn("self._start_app_update_watcher()", source)

    def test_installer_supports_restart_manager_self_update(self):
        installer = (REPO_DIR / "desktop" / "VuNMix_Installer.iss").read_text(
            encoding="utf-8"
        )
        self.assertIn("CloseApplications=yes", installer)
        self.assertIn("RestartApplications=yes", installer)
        self.assertIn("PrivilegesRequired=admin", installer)


if __name__ == "__main__":
    unittest.main()
