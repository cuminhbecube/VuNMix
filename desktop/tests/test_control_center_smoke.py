"""Build the real six-route Fluent Tk window on Windows CI without hardware."""
import pathlib
import sys
import unittest
from types import SimpleNamespace

DESKTOP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))


@unittest.skipUnless(sys.platform == "win32", "Windows Tk smoke test")
class ControlCenterSmokeTests(unittest.TestCase):
    def test_builds_all_routes_and_keeps_saving_and_updating(self):
        from config import AppConfig
        from connection_ui import ConnectionSettingsDialog
        from protocol import CLOCK_STYLE_NAMES

        controller = SimpleNamespace(
            serial=SimpleNamespace(status="waiting", is_connected=False, port=""),
            audio=SimpleNamespace(get_sessions_for_mode=lambda _mode: []),
            preset_service=SimpleNamespace(get_preset_names=lambda: []),
            obs_service=SimpleNamespace(
                is_connected=False, is_streaming=False, scenes=[], current_scene="",
                toggle_streaming=lambda: None, toggle_recording=lambda: None,
                toggle_input_mute=lambda *_: None, mic_input="Mic",
                desktop_input="Desktop",
            ),
            media_service=SimpleNamespace(
                cached_snapshot=lambda: SimpleNamespace(info=SimpleNamespace(title="")),
                execute_control=lambda *_: True,
            ),
            _device_connected=False,
            firmware_updating=False,
            can_update_firmware=False,
            firmware_version="unknown",
            open_log_folder=lambda: None,
            diagnostic_report=lambda: "offline test",
        )
        dialog = ConnectionSettingsDialog(
            AppConfig(), controller, on_save=lambda *_: None
        )
        try:
            dialog.initialize()
            self.assertEqual(len(CLOCK_STYLE_NAMES), 16)
            for name in ("Overview", "Audio", "Clock", "Device", "Updates", "Settings"):
                self.assertIsNotNone(dialog._tabs.tab(name))
                dialog._fluent_navigate(name)
                self.assertEqual(dialog._tabs.get(), name)
            dialog._fluent_navigate("Overview")
            self.assertEqual(dialog._clock_style_var.get(), CLOCK_STYLE_NAMES[0])
            self.assertIn(CLOCK_STYLE_NAMES[0], dialog._clock_preview_var.get())
            self.assertIn("disconnected", dialog._update_center_var.get().lower())
            self.assertEqual(len(dialog._sidebar_buttons), 6)
            self.assertTrue(dialog._window.winfo_exists())
            dialog._toggle_fluent_sidebar()
            self.assertTrue(dialog._sidebar_collapsed)
            dialog._toggle_fluent_sidebar()
            self.assertFalse(dialog._sidebar_collapsed)
        finally:
            dialog._shutdown_from_ui()


if __name__ == "__main__":
    unittest.main()
