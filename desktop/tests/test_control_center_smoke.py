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
            from protocol import CLOCK_STYLE_NAMES
            self.assertEqual(len(CLOCK_STYLE_NAMES), 16)
            for name in ("Overview", "Audio", "Clock", "Device", "Updates", "Settings"):
                self.assertIsNotNone(dialog._tabs.tab(name))
            self.assertEqual(dialog._clock_style_var.get(), CLOCK_STYLE_NAMES[0])
            self.assertIn(CLOCK_STYLE_NAMES[0], dialog._clock_preview_var.get())
            self.assertIn("disconnected", dialog._update_center_var.get().lower())
            self.assertTrue(dialog._window.winfo_exists())
        finally:
            dialog._shutdown_from_ui()


if __name__ == "__main__":
    unittest.main()
