"""Exercise the real Windows Tk pages, clock selection and persistent Save."""
import pathlib
import sys
import unittest
from unittest import mock

DESKTOP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))


@unittest.skipUnless(sys.platform == "win32", "Windows Tk smoke test")
class ControlCenterSmokeTests(unittest.TestCase):
    def _assert_personal_logo_and_native_window_icons(self, dialog):
        from contextlib import ExitStack
        import customtkinter as ctk
        import tkinter as tk
        import win32con
        import win32gui
        import win32ui
        from PIL import Image
        from app_branding import load_logo, resource_path
        from build_info import APP_VERSION
        from firmware_release import FirmwareReleaseInfo

        icon_path = pathlib.Path(resource_path("assets/icon.ico")).resolve()

        def render_icon(hicon, width, height, background):
            # This display DC is owned (CreateDC), unlike a borrowed GetDC.
            display_handle = win32gui.CreateDC("DISPLAY", None, None)
            try:
                display_dc = win32ui.CreateDCFromHandle(display_handle)
            except Exception:
                win32gui.DeleteDC(display_handle)
                raise
            with ExitStack() as cleanup:
                cleanup.callback(display_dc.DeleteDC)
                memory_dc = display_dc.CreateCompatibleDC()
                cleanup.callback(memory_dc.DeleteDC)
                bitmap = win32ui.CreateBitmap()
                bitmap.CreateCompatibleBitmap(display_dc, width, height)
                cleanup.callback(win32gui.DeleteObject, bitmap.GetHandle())
                previous = memory_dc.SelectObject(bitmap)
                # Restore before deleting the bitmap or either DC.
                cleanup.callback(memory_dc.SelectObject, previous)
                memory_dc.FillSolidRect((0, 0, width, height), background)
                win32gui.DrawIconEx(memory_dc.GetSafeHdc(), 0, 0, hicon,
                                    width, height, 0, None, win32con.DI_NORMAL)
                info = bitmap.GetInfo()
                self.assertIn(info["bmBitsPixel"], (24, 32))
                raw_mode = "BGRX" if info["bmBitsPixel"] == 32 else "BGR"
                # Ignore the unused fourth byte of a screen-compatible bitmap.
                return Image.frombuffer(
                    "RGB", (width, height), bitmap.GetBitmapBits(True), "raw",
                    raw_mode, info["bmWidthBytes"], 1,
                ).tobytes()

        def assert_icon_after_ctk_delay(window):
            # CTkToplevel sets its own icon at 200ms; our reapply is at 250ms.
            settled = tk.BooleanVar(master=dialog._window, value=False)
            dialog._window.after(350, settled.set, True)
            dialog._window.wait_variable(settled)
            dialog._window.update_idletasks()

            # Tk's ICO setter does not retain a queryable bitmap filename.
            # Inspect the native wrapper instead; GA_ROOT does not follow a
            # transient picker's owner back to the main window.
            wrapper = win32gui.GetAncestor(window.winfo_id(), win32con.GA_ROOT)
            self.assertTrue(wrapper, f"No native wrapper for {window.title()}")
            actual_icon = win32gui.SendMessage(
                wrapper, win32con.WM_GETICON, win32con.ICON_BIG, 0)
            self.assertTrue(actual_icon, f"No native icon for {window.title()}")
            # actual_icon is borrowed from the window: never DestroyIcon it.
            _, _, _, mask, color = win32gui.GetIconInfo(actual_icon)
            try:
                info = win32gui.GetObject(color or mask)
                width = info.bmWidth
                height = info.bmHeight if color else info.bmHeight // 2
            finally:
                # GetIconInfo creates these bitmap copies for the caller.
                for handle in (color, mask):
                    if handle:
                        win32gui.DeleteObject(handle)
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            expected_icon = win32gui.LoadImage(
                0, str(icon_path), win32con.IMAGE_ICON, width, height,
                win32con.LR_LOADFROMFILE)
            self.assertTrue(expected_icon)
            try:
                # Both backgrounds make transparency differences observable.
                for background in (0x000000, 0xFFFFFF):
                    with self.subTest(window=window.title(), background=background):
                        actual = render_icon(actual_icon, width, height, background)
                        expected = render_icon(expected_icon, width, height, background)
                        self.assertEqual(actual, expected,
                                         "Native window icon differs from the personal ICO")
            finally:
                # LoadImage without LR_SHARED returns an owned icon.
                win32gui.DestroyIcon(expected_icon)

        with self.subTest(branding="header"):
            self.assertTrue(icon_path.is_file())
            self.assertIsInstance(dialog._header_logo_image, ctk.CTkImage)
            self.assertIs(dialog._header_logo_label.cget("image"), dialog._header_logo_image)
            self.assertEqual(dialog._header_logo_image.cget("size"), (40, 40))
            header_art = dialog._header_logo_image.cget("dark_image")
            self.assertEqual(header_art.mode, "RGBA")
            self.assertEqual(header_art.tobytes(), load_logo(80).tobytes())
            self.assertTrue(dialog._header_logo_label.winfo_ismapped())
        with self.subTest(branding="main window"):
            assert_icon_after_ctk_delay(dialog._window)

        version = APP_VERSION.lstrip("v")
        release = FirmwareReleaseInfo(
            version=version, tag=f"v{version}", release_url="",
            firmware_name=f"VuNMix-Firmware-{version}.bin",
            firmware_url="", checksums_url="",
        )
        # Open production pickers with fixtures in the same Tk interpreter as
        # the route/save checks. Do not invoke loaders or selection Apply.
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

            self._assert_personal_logo_and_native_window_icons(dialog)
            self.assertEqual(service_calls, [])
            on_save.assert_not_called()
            self.assertEqual(callback_errors, [])

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
