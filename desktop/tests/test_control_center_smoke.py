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
            was_collapsed = dialog._sidebar_collapsed
            dialog._toggle_fluent_sidebar()
            self.assertNotEqual(dialog._sidebar_collapsed, was_collapsed)
            dialog._toggle_fluent_sidebar()
            self.assertEqual(dialog._sidebar_collapsed, was_collapsed)

            # The four audio sources and tools are available without a tall
            # four-column/eight-session scrolling mixer.
            for page in ("Mixer", "Profiles", "Media / OBS"):
                dialog._fluent_show_audio_page(page)
                self.assertEqual(dialog._audio_page, page)
            dialog._fluent_show_audio_page("Mixer")
            for source in ("Output", "Input", "Applications", "Game Mixer"):
                dialog._fluent_audio_source_changed(source)
                self.assertEqual(dialog._audio_source_var.get(), source)
                self.assertEqual(dialog._audio_page_index, 0)

            import customtkinter as ctk
            self.assertIsInstance(dialog._tabs.tab("Overview").winfo_children()[0],
                                  ctk.CTkFrame)
            # Verify the page bodies are not scrollable frames.
            for page in ("Device", "Clock", "Settings"):
                body = dialog._tabs.tab(page).winfo_children()[0]
                self.assertIsInstance(body, ctk.CTkFrame)
                self.assertNotIsInstance(body, ctk.CTkScrollableFrame)

            # Layout remains navigable on a 960x650 compact screen.
            dialog._window.geometry("960x650+0+0")
            dialog._window.update_idletasks()
            for page in ("Overview", "Audio", "Clock", "Device", "Updates", "Settings"):
                dialog._fluent_navigate(page)
                dialog._window.update_idletasks()
                self.assertEqual(dialog._tabs.get(), page)
        finally:
            dialog._shutdown_from_ui()


if __name__ == "__main__":
    unittest.main()
