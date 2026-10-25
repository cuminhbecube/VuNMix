"""Real Tk appearance, save/ACK separation, compact layout and clock isolation."""
from datetime import time
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))


@unittest.skipUnless(sys.platform == 'win32' or os.environ.get('VUNMIX_GUI_TESTS') == '1',
                     'Requires a native Tk display')
class DeviceThemeUiTests(unittest.TestCase):
    def test_native_previews_save_ack_and_original_clocks(self):
        from tools.capture_control_center import load_ctk, make_controller, widget_report, settle
        ctk = load_ctk()
        scale = float(os.environ.get('VUNMIX_QA_SCALE', '1'))
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
        if sys.platform != 'win32':
            sys.modules.setdefault('win32gui', types.ModuleType('win32gui'))
        from clock_preview import render_clock_preview
        from config import AppConfig
        from connection_ui import ConnectionSettingsDialog
        from gui import TrayApp
        from device_theme import DeviceThemeCoordinator
        from protocol import Command, DEVICE_THEME_NAMES, CLOCK_STYLE_NAMES, ThemeResponse, ThemeStatus
        from PIL import ImageGrab

        sent, errors, captures = [], [], []
        controller, service_calls = make_controller(True)
        controller.audio.set_favorite_apps = mock.Mock()
        controller.theme_sync = sync = DeviceThemeCoordinator(
            lambda request, generation: sent.append((request, generation)) or True)
        sync.connected(7)
        query = sync.poll()
        sync.handle_response(ThemeResponse(query.request_id, ThemeStatus.APPLIED, 5, 255).pack(), 7)
        config = AppConfig(com_port='COM7', auto_update_enabled=False)
        config.device_settings.clock_style = 15
        config.device_settings.sleep_after_seconds = 301
        original_settings_packet = config.device_settings.pack()
        legacy_frames = []
        controller.serial.send_settings = lambda _settings: legacy_frames.append(Command.SETTINGS) or True
        controller._push_updated_state = lambda: legacy_frames.extend(
            [Command.CURRENT_SESSION, Command.ALTERNATE_SESSION]) or True
        tray = TrayApp(config, controller)
        on_save = mock.Mock(wraps=tray._on_settings_saved)
        dialog = ConnectionSettingsDialog(config, controller, on_save=on_save)
        output = os.environ.get('VUNMIX_THEME_QA_DIR')
        out = Path(output) if output else None
        if out:
            out.mkdir(parents=True, exist_ok=True)
        clock_before = [render_clock_preview(i, now=time(10, 24, 36)).tobytes() for i in range(16)]

        def show_and_check(label):
            dialog._refresh_control_center()
            settle(dialog._window)
            widgets = widget_report(dialog._window)
            problems = [row for row in widgets if row['outside_parent'] or row['hidden_managed']
                        or row.get('image_clipped')]
            self.assertEqual(problems, [], f'{label}: {problems}')
            self.assertEqual(dialog._clock_style_var.get(), CLOCK_STYLE_NAMES[15])
            self.assertEqual(config.device_settings.clock_style, 15)
            width, height = dialog._device_theme_preview_size
            self.assertEqual(width * 3, height * 4)
            self.assertLessEqual(width, 320)
            if out:
                window = dialog._window
                x, y = window.winfo_rootx(), window.winfo_rooty()
                box = (x, y, x + window.winfo_width(), y + window.winfo_height())
                ImageGrab.grab(bbox=box, xdisplay=os.environ.get('DISPLAY')).save(out / (label + '.png'))
            captures.append({'frame': label, 'preview_size': [width, height], 'widgets': widgets})

        try:
            with mock.patch('gui.serial.tools.list_ports.comports', return_value=[]):
                dialog.initialize()
            dialog._window.report_callback_exception = lambda kind, err, tb: errors.append(str(err))
            dialog._window.deiconify()
            dialog._fluent_navigate('Device')
            self.assertEqual(dialog._device_theme_var.get(), '')
            self.assertEqual(dialog._device_theme_image_key[0], 5)
            self.assertIsNone(config.device_theme_id)
            sizes = os.environ.get('VUNMIX_QA_SIZES', '1040x680,780x560').split(',')
            for size in sizes:
                dialog._window.geometry(size + '+0+0')
                for expanded in (False, True):
                    dialog._sidebar_manual_override = True
                    dialog._set_fluent_sidebar_collapsed(not expanded)
                    for index in range(8):
                        dialog._choose_device_theme(index)
                        show_and_check(f'{size}_menu{int(expanded)}_{index}_{DEVICE_THEME_NAMES[index].replace(" ", "_")}')
                        self.assertEqual(dialog._device_theme_image_key[0], index)
                        self.assertEqual(len(sent), 1, 'Preview must not send a theme request')
                    dialog._show_device_page('Lighting & standby')
                    # Appearance layout is the new responsive surface. Preserve
                    # existing lighting behavior and validate it at normal sizes.
                    if int(size.split('x')[1]) >= 534:
                        show_and_check(f'{size}_menu{int(expanded)}_lighting')
                    dialog._show_device_page('Appearance')
            with (mock.patch.object(config, 'save') as save_config,
                  mock.patch('gui.set_run_on_startup') as startup,
                  mock.patch('gui.threading.Thread') as state_thread):
                dialog._save_button.invoke()
            save_config.assert_called_once()
            on_save.assert_called_once_with(False)
            state_thread.assert_not_called()
            startup.assert_not_called()
            controller.audio.set_favorite_apps.assert_not_called()
            self.assertEqual(legacy_frames, [], 'Theme-only Save must not wake the original clock')
            self.assertEqual(config.device_settings.pack(), original_settings_packet)
            self.assertEqual(config.device_settings.sleep_after_seconds, 301)
            self.assertEqual(config.device_theme_id, 7)
            self.assertEqual(sync.snapshot().confirmed_id, 5)
            request = sync.poll()
            self.assertEqual(request.theme_id, 7)
            show_and_check('saved_on_pc_applying')
            sync.handle_response(ThemeResponse(request.request_id, ThemeStatus.SAVED_DEFERRED, 7, 255).pack(), 7)
            show_and_check('saved_on_device_deferred')
            self.assertIn('after clock or sleep', dialog._device_theme_status_var.get())
            self.assertEqual(dialog._device_theme_retry_button.cget('text'), 'Refresh')
            dialog._device_theme_retry_button.invoke()
            self.assertEqual(sync.poll().operation.name, 'QUERY')
            self.assertEqual([render_clock_preview(i, now=time(10, 24, 36)).tobytes() for i in range(16)], clock_before)
            self.assertEqual(service_calls, [])
            self.assertEqual(errors, [])
            # Existing device-setting edits still use the legacy state push.
            with (mock.patch.object(config, 'save'), mock.patch('gui.threading.Thread') as state_thread):
                dialog._brightness_var.set(127)
                dialog._save_button.invoke()
            state_thread.assert_called_once()
            state_thread.call_args.kwargs['target']()
            self.assertEqual(legacy_frames, [Command.SETTINGS, Command.CURRENT_SESSION, Command.ALTERNATE_SESSION])
            self.assertEqual(config.device_settings.sleep_after_seconds, 301)
        finally:
            if dialog._window is not None:
                dialog._shutdown_from_ui()
            ctk.set_widget_scaling(1)
            ctk.set_window_scaling(1)
            if out:
                (out / 'manifest.json').write_text(json.dumps({
                    'backend': 'real Tk; simulated device replies; native sample previews',
                    'scale': scale, 'captures': captures, 'callback_errors': errors,
                    'service_calls': service_calls,
                }, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
