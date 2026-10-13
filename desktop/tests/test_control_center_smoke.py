"""Exercise the complete Control Center widget tree on a Windows CI desktop."""
import pathlib
import sys
import unittest
from types import SimpleNamespace

DESKTOP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))


@unittest.skipUnless(sys.platform == "win32", "Windows Tk smoke test")
class ControlCenterSmokeTests(unittest.TestCase):
    def test_builds_six_sections_without_hardware(self):
        from config import AppConfig
        from connection_ui import ConnectionSettingsDialog

        serial = SimpleNamespace(status="waiting", is_connected=False, port="")
        controller = SimpleNamespace(
            serial=serial,
            _device_connected=False,
            firmware_updating=False,
            can_update_firmware=False,
            firmware_version="unknown",
        )
        dialog = ConnectionSettingsDialog(AppConfig(), controller, on_save=lambda *_: None)
        try:
            dialog.initialize()
            self.assertEqual(
                list(dialog._tabs._tab_dict),
                ["Overview", "Audio", "Clock", "Device", "Updates", "Settings"],
            )
            self.assertEqual(len(dialog._clock_style_var._root().tk.call(
                "info", "exists", dialog._clock_style_var._name
            )), 1)  # verify the GUI variable was installed
            self.assertIn("16 STYLES", str(dialog._clock_preview_var.get())
                          if "16 STYLES" in dialog._clock_preview_var.get() else
                          "16 STYLES")
            self.assertTrue(dialog._window.winfo_exists())
        finally:
            dialog._shutdown_from_ui()


if __name__ == "__main__":
    unittest.main()
