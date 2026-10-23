"""Exercise the real Windows Tk pages, clock selection and persistent Save."""
import pathlib
import sys
import unittest
from unittest import mock

DESKTOP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))


@unittest.skipUnless(sys.platform == "win32", "Windows Tk smoke test")
class ControlCenterSmokeTests(unittest.TestCase):
    def test_personal_logo_and_native_window_icons_survive_ctk_delay(self):
        import customtkinter as ctk
        import tkinter as tk
        from app_branding import load_logo, resource_path
        from build_info import APP_VERSION
        from config import AppConfig
        from connection_ui import ConnectionSettingsDialog
        from firmware_release import FirmwareReleaseInfo
        from tools.capture_control_center import make_controller

        controller, service_calls = make_controller(False)
        dialog = ConnectionSettingsDialog(AppConfig(), controller, on_save=mock.Mock())
        callback_errors = []
        icon_path = pathlib.Path(resource_path("assets/icon.ico")).resolve()

        def assert_icon_after_ctk_delay(window):
            # CTkToplevel schedules its own icon at 200ms. Query the actual
            # Windows bitmap after both that callback and our reapply run.
            settled = tk.BooleanVar(master=dialog._window, value=False)
            dialog._window.after(350, settled.set, True)
            dialog._window.wait_variable(settled)
            dialog._window.update_idletasks()
            self.assertEqual(pathlib.Path(window.iconbitmap()).resolve(), icon_path)

        try:
            with mock.patch("gui.serial.tools.list_ports.comports", return_value=[]):
                dialog.initialize()
            dialog._window.report_callback_exception = (
                lambda kind, error, tb: callback_errors.append(f"{kind.__name__}: {error}"))
            dialog._window.deiconify()
            dialog._window.update_idletasks()

            self.assertTrue(icon_path.is_file())
            self.assertIsInstance(dialog._header_logo_image, ctk.CTkImage)
            self.assertIs(dialog._header_logo_label.cget("image"), dialog._header_logo_image)
            self.assertEqual(dialog._header_logo_image.cget("size"), (40, 40))
            header_art = dialog._header_logo_image.cget("dark_image")
            self.assertEqual(header_art.mode, "RGBA")
            self.assertEqual(header_art.tobytes(), load_logo(80).tobytes())
            self.assertTrue(dialog._header_logo_label.winfo_ismapped())
            assert_icon_after_ctk_delay(dialog._window)

            version = APP_VERSION.lstrip("v")
            release = FirmwareReleaseInfo(
                version=version, tag=f"v{version}", release_url="",
                firmware_name=f"VuNMix-Firmware-{version}.bin",
                firmware_url="", checksums_url="",
            )
            # Open the production pickers from fixture data. Do not invoke
            # the loaders, installation, selection Apply, or any services.
            for title, show in (
                ("Firmware Versions", lambda: dialog._show_firmware_release_picker([release])),
                ("App Favorites", lambda: dialog._show_favorite_apps_picker(["Spotify", "Discord"])),
            ):
                with self.subTest(picker=title):
                    before = set(dialog._window.winfo_children())
                    show()
                    pickers = [child for child in dialog._window.winfo_children()
                               if child not in before and isinstance(child, ctk.CTkToplevel)]
                    self.assertEqual(len(pickers), 1)
                    picker = pickers[0]
                    try:
                        self.assertEqual(picker.title(), title)
                        assert_icon_after_ctk_delay(picker)
                    finally:
                        picker.grab_release()
                        picker.destroy()

            self.assertEqual(service_calls, [])
            dialog.on_save.assert_not_called()
            self.assertEqual(callback_errors, [])
        finally:
            dialog._shutdown_from_ui()

    def test_routes_fit_and_clock_selection_and_save_stay_consistent(self):
        import customtkinter as ctk
        from config import AppConfig
        from connection_ui import ConnectionSettingsDialog
        from fluent_theme import ACCENT, ACCENT_TEXT, BG, SECTIONS
        from protocol import CLOCK_STYLE_NAMES
        from tools.capture_control_center import make_controller, widget_report

        controller, service_calls = make_controller(False)
        controller.audio.set_favorite_apps = mock.Mock()
        on_save = mock.Mock()
        dialog = ConnectionSettingsDialog(AppConfig(), controller, on_save=on_save)
        callback_errors = []

        def render():
            dialog._refresh_control_center()
            dialog._window.update_idletasks()
            dialog._window.update()
            dialog._window.update_idletasks()

        def assert_visible_layout(context):
            render()
            problems = [row for row in widget_report(dialog._window)
                        if row["outside_parent"] or row["hidden_managed"]
                        or row.get("image_clipped", False)]
            self.assertEqual(problems, [], f"{context}: {problems}")
            self.assertTrue(dialog._save_button.winfo_ismapped(), context)
            page = dialog._tabs.tab(dialog._tabs.get())
            self.assertEqual(page.winfo_y(), 0, "Page stack must not reserve a hidden tab header")

        try:
            with mock.patch("gui.serial.tools.list_ports.comports", return_value=[]):
                dialog.initialize()
            dialog._window.report_callback_exception = (
                lambda kind, error, tb: callback_errors.append(f"{kind.__name__}: {error}"))
            dialog._window.deiconify()
            render()
            self.assertEqual(dialog._window.cget("fg_color"), BG)
            self.assertEqual(dialog._save_button.cget("fg_color"), ACCENT)
            self.assertEqual(dialog._save_button.cget("text_color"), ACCENT_TEXT)
            self.assertEqual(len(dialog._sidebar_buttons), len(SECTIONS))
            self.assertIn("disconnected", dialog._update_center_var.get().lower())

            collapsed = dialog._sidebar_collapsed
            dialog._toggle_fluent_sidebar()
            self.assertNotEqual(dialog._sidebar_collapsed, collapsed)
            dialog._toggle_fluent_sidebar()
            self.assertEqual(dialog._sidebar_collapsed, collapsed)
            dialog._sidebar_manual_override = False

            # Populated fixtures expose clipping that empty-audio smoke tests miss.
            for width, height in ((1040, 680), (960, 640), (780, 560)):
                dialog._window.geometry(f"{width}x{height}+0+0")
                render()
                for name in SECTIONS:
                    dialog._fluent_navigate(name)
                    self.assertEqual(dialog._tabs.get(), name)
                    assert_visible_layout(f"{width}x{height} / {name}")
                dialog._fluent_navigate("Audio")
                for source in ("Output", "Input", "Applications", "Game Mixer"):
                    dialog._fluent_audio_source_changed(source)
                    self.assertEqual(dialog._audio_page_index, 0)
                    assert_visible_layout(f"{width}x{height} / Audio / {source}")
                for name in ("Profiles", "Media / OBS", "Mixer"):
                    dialog._fluent_show_audio_page(name)
                    assert_visible_layout(f"{width}x{height} / Audio / {name}")
                dialog._fluent_navigate("Clock")
                render()
                page_size = dialog._clock_gallery_page_size
                for page in range((len(CLOCK_STYLE_NAMES) + page_size - 1) // page_size):
                    dialog._show_clock_gallery_page(page)
                    assert_visible_layout(f"{width}x{height} / Clock page {page + 1}")
                    for index, tile in dialog._clock_tiles.items():
                        self.assertEqual(bool(tile.winfo_ismapped()), index // page_size == page)

            # A deliberately expanded menu must also fit the minimum window.
            dialog._sidebar_manual_override = True
            dialog._set_fluent_sidebar_collapsed(False)
            for name in SECTIONS:
                dialog._fluent_navigate(name)
                assert_visible_layout(f"780x560 expanded menu / {name}")
            dialog._fluent_navigate("Clock")
            render()
            self.assertEqual(dialog._clock_gallery_page_size, 4)

            # Every wire ID selects a real image and the matching gallery page.
            for index, name in enumerate(CLOCK_STYLE_NAMES):
                dialog._fluent_choose_clock(index)
                render()
                self.assertEqual(dialog._clock_style_var.get(), name)
                self.assertEqual(dialog._clock_preview_var.get(), name)
                self.assertEqual(dialog._clock_gallery_page,
                                 index // dialog._clock_gallery_page_size)
                self.assertEqual(dialog._clock_tiles[index].cget("border_color"), ACCENT)
                self.assertTrue(dialog._clock_tiles[index].winfo_ismapped())
                self.assertEqual(dialog._clock_image_key[1], index)
                self.assertIsInstance(dialog._clock_selected_image, ctk.CTkImage)
                dialog._fluent_navigate("Overview")
                render()
                self.assertEqual(dialog._overview_clock_caption.get(), name)
                self.assertEqual(dialog._clock_image_key[:2], ("Overview", index))
                dialog._fluent_navigate("Clock")

            # Save is an in-place operation; feedback must reflect edited values.
            dialog._fluent_navigate("Settings")
            dialog._startup_var.set(not dialog._startup_var.get())
            self.assertEqual(dialog._save_status_var.get(), "Unsaved changes")
            with (
                mock.patch.object(dialog.config, "save") as save_config,
                mock.patch("gui.set_run_on_startup"),
            ):
                dialog._save_button.invoke()
            save_config.assert_called_once()
            on_save.assert_called_once_with(False)
            controller.audio.set_favorite_apps.assert_called_once()
            self.assertEqual(dialog._save_status_var.get(), "Settings saved")
            self.assertNotEqual(dialog._window.state(), "withdrawn")
            self.assertEqual(dialog.config.device_settings.clock_style, 15)
            self.assertEqual(service_calls, [])
            self.assertEqual(callback_errors, [])
        finally:
            dialog._shutdown_from_ui()


if __name__ == "__main__":
    unittest.main()
