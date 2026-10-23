"""Settings transactions, user COM intent and Tk ownership without a GUI."""

import ast
from dataclasses import asdict
import logging
import math
from pathlib import Path
import queue
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock


DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))

from config import AppConfig
from protocol import CLOCK_STYLE_NAMES, STANDBY_LED_NAMES


def _actual_class(filename, class_name, methods, *, base=None, **extra):
    """Execute production method bodies without loading Windows audio or Tk."""
    tree = ast.parse((DESKTOP / filename).read_text(encoding="utf-8"))
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == class_name)
    node = ast.ClassDef(
        name=class_name, bases=[ast.Name(id="Base", ctx=ast.Load())] if base else [],
        keywords=[], decorator_list=[],
        body=[method for method in original.body
              if isinstance(method, ast.FunctionDef) and method.name in methods],
    )
    namespace = dict(
        Base=base, math=math, threading=threading, time=time, queue=queue,
        log=logging.getLogger("settings-state-test"), tk=SimpleNamespace(TclError=RuntimeError),
        messagebox=mock.Mock(), set_run_on_startup=mock.Mock(), APP_VERSION="0.4.32",
        INPUT="#292929", CARD_HOVER="#343434", TEXT="#FFFFFF", ACCENT="#60CDFF", MUTED="#999999",
    )
    namespace.update(extra)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 str(DESKTOP / filename), "exec"), namespace)
    return namespace[class_name], namespace


class _Variable:
    """Only the variable API used by settings; every write invokes its traces."""
    def __init__(self, value):
        self.value = value
        self.traces = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in self.traces:
            callback("variable", "", "write")

    def trace_add(self, mode, callback):
        assert mode == "write"
        self.traces.append(callback)


class SettingsStateTests(unittest.TestCase):
    def setUp(self):
        base, self.namespace = _actual_class("gui.py", "SettingsDialog", {
            "_save", "_track_settings_changes", "_settings_form_snapshot",
            "_on_com_selected", "_mark_settings_dirty", "_ui_call", "_process_window_commands",
        })
        cls, _ = _actual_class("connection_ui.py", "ConnectionSettingsDialog",
                               {"_update_status_loop"}, base=base)
        self.dialog = dialog = cls()
        dialog.config = AppConfig(com_port="COM14", favorite_apps=["spotify"])
        dialog.config.save = mock.Mock()
        dialog.controller = SimpleNamespace(
            _device_connected=True, firmware_updating=False, can_update_firmware=True,
            serial=SimpleNamespace(port="COM14", status="Connected", is_connected=True),
            audio=mock.Mock(),
        )
        dialog._window = mock.Mock()
        dialog._window.winfo_exists.return_value = True
        dialog._ui_thread_id = threading.get_ident()
        dialog._window_commands = queue.Queue()
        dialog.btn_toggle_conn = mock.Mock()
        dialog._refresh_control_center = mock.Mock()
        dialog._firmware_release_loading = False
        dialog._com_selection_pending = False
        dialog.on_save = mock.Mock()
        dialog._com_var = _Variable("COM14")
        dialog._startup_var = _Variable(False)
        dialog._auto_update_var = _Variable(True)
        dialog._auto_firmware_update_var = _Variable(True)
        dialog._sleep_var = _Variable("5")
        dialog._sleep_enabled_var = _Variable(True)
        dialog._clock_standby_var = _Variable("10")
        dialog._clock_style_var = _Variable(CLOCK_STYLE_NAMES[0])
        dialog._led_mode_var = _Variable(STANDBY_LED_NAMES[0])
        dialog._scroll_var = _Variable(True)
        dialog._brightness_var = _Variable(96.0)
        dialog._save_status_var = _Variable("All changes saved")
        dialog._led_color_values = {
            name: getattr(dialog.config.device_settings, name).to_list()
            for name in ("volume_min_color", "volume_max_color", "mix_channel_a_color", "mix_channel_b_color")
        }
        dialog._track_settings_changes()

    def test_invalid_either_timeout_leaves_configuration_and_side_effects_untouched(self):
        for sleep, clock in (("", "10"), ("5", "bad"), ("1.5", "10")):
            with self.subTest(sleep=sleep, clock=clock):
                self.setUp()
                dialog = self.dialog
                before, saved = asdict(dialog.config), dialog._saved_form_snapshot
                dialog._startup_var.set(True)
                dialog._com_var.set("COM7")
                dialog._on_com_selected("COM7")
                dialog._sleep_var.set(sleep)
                dialog._clock_standby_var.set(clock)
                dialog._save()
                self.assertEqual(asdict(dialog.config), before)
                self.assertEqual(dialog._saved_form_snapshot, saved)
                dialog.config.save.assert_not_called()
                dialog.controller.audio.set_favorite_apps.assert_not_called()
                dialog.on_save.assert_not_called()
                self.namespace["set_run_on_startup"].assert_not_called()
                self.namespace["messagebox"].showerror.assert_called_once()
                self.assertIs(self.namespace["messagebox"].showerror.call_args.kwargs["parent"], dialog._window)
                self.assertEqual(dialog._save_status_var.get(), "Unsaved changes")

    def test_successful_save_normalizes_values_maps_wire_ids_and_keeps_window_open(self):
        dialog = self.dialog
        dialog._sleep_var.set("2000")
        dialog._clock_standby_var.set("999")
        dialog._clock_style_var.set(CLOCK_STYLE_NAMES[15])
        dialog._led_mode_var.set(STANDBY_LED_NAMES[16])
        dialog._startup_var.set(True)
        dialog._auto_update_var.set(False)
        dialog._sleep_enabled_var.set(False)
        dialog._led_color_values["volume_min_color"] = [12, 34, 56]
        dialog._save()
        settings = dialog.config.device_settings
        self.assertEqual(settings.sleep_after_seconds, 65535)
        self.assertEqual(settings.clock_standby_minutes, 255)
        self.assertEqual(settings.clock_style, 15)
        self.assertEqual(settings.standby_led_mode, 16)
        self.assertEqual(settings.volume_min_color.to_list(), [12, 34, 56])
        self.assertFalse(settings.sleep_enabled)
        self.assertTrue(dialog.config.run_on_startup)
        self.assertFalse(dialog.config.auto_update_enabled)
        self.assertEqual(dialog._sleep_var.get(), "1093")
        self.assertEqual(dialog._clock_standby_var.get(), "255")
        self.assertEqual(dialog._saved_form_snapshot, dialog._settings_form_snapshot())
        self.assertEqual(dialog._save_status_var.get(), "Settings saved")
        dialog.config.save.assert_called_once_with()
        dialog.on_save.assert_called_once_with(False)
        dialog.controller.audio.set_favorite_apps.assert_called_once_with(["spotify"])
        self.namespace["set_run_on_startup"].assert_called_once_with(True)
        self.namespace["messagebox"].showerror.assert_not_called()
        dialog._window.withdraw.assert_not_called()
        dialog._window.destroy.assert_not_called()

    def test_dirty_tracking_clears_when_variables_colors_and_favorites_are_reverted(self):
        dialog = self.dialog
        dialog._startup_var.set(True)
        self.assertEqual(dialog._save_status_var.get(), "Unsaved changes")
        dialog._startup_var.set(False)
        self.assertEqual(dialog._save_status_var.get(), "All changes saved")
        original = list(dialog._led_color_values["volume_min_color"])
        dialog._led_color_values["volume_min_color"] = [7, 8, 9]
        dialog._mark_settings_dirty()
        self.assertEqual(dialog._save_status_var.get(), "Unsaved changes")
        dialog._led_color_values["volume_min_color"] = original
        dialog.config.favorite_apps = ["spotify", "discord"]
        dialog._mark_settings_dirty()
        self.assertEqual(dialog._save_status_var.get(), "Unsaved changes")
        dialog.config.favorite_apps = ["spotify", "spotify"]
        dialog._mark_settings_dirty()
        self.assertEqual(dialog._save_status_var.get(), "All changes saved")

    def test_discovery_updates_unpinned_port_without_marking_form_dirty(self):
        dialog = self.dialog
        dialog.controller.serial.port = "COM7"
        dialog._update_status_loop()
        self.assertEqual(dialog._com_var.get(), "COM7")
        dialog._mark_settings_dirty()
        self.assertEqual(dialog._save_status_var.get(), "All changes saved")

    def test_explicit_com_choice_survives_poll_even_if_it_equals_saved_configuration(self):
        dialog = self.dialog
        dialog.controller.serial.port = "COM7"
        dialog._update_status_loop()
        for choice, dirty in (("COM9", True), ("COM14", False)):
            with self.subTest(choice=choice):
                dialog._com_var.set(choice)
                dialog._on_com_selected(choice)
                dialog._update_status_loop()
                self.assertEqual(dialog._com_var.get(), choice)
                self.assertEqual(dialog._save_status_var.get(),
                                 "Unsaved changes" if dirty else "All changes saved")

    def test_saved_com_choice_survives_poll_while_controller_still_has_old_port(self):
        dialog = self.dialog
        dialog._com_var.set("COM9")
        dialog._on_com_selected("COM9")
        dialog._save()
        dialog.on_save.assert_called_once_with(True)
        self.assertEqual(dialog.config.com_port, "COM9")
        self.assertEqual(dialog.controller.serial.port, "COM14")
        dialog._update_status_loop()
        self.assertEqual(dialog._com_var.get(), "COM9")
        self.assertEqual(dialog._saved_form_snapshot, dialog._settings_form_snapshot())

    def test_worker_callbacks_touch_ui_only_after_main_thread_pumps_queue(self):
        dialog = self.dialog
        observed = []
        worker = threading.Thread(target=lambda: dialog._ui_call(
            lambda: observed.append(threading.get_ident())))
        worker.start()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(observed, [])
        dialog._window.after.assert_not_called()
        dialog._window.winfo_exists.assert_not_called()
        dialog._process_window_commands()
        self.assertEqual(observed, [threading.get_ident()])
        dialog._window.after.assert_called_once()


class _CapturedThread:
    created = []

    def __init__(self, *, target, **kwargs):
        self.target = target
        self.running = False
        self.name = kwargs.get("name")
        self.__class__.created.append(self)

    def start(self):
        self.running = True

    def is_alive(self):
        return self.running

    def run(self):
        try:
            self.target()
        finally:
            self.running = False


class SettingsPortRestartTests(unittest.TestCase):
    def setUp(self):
        _CapturedThread.created = []
        cls, _ = _actual_class("gui.py", "TrayApp", {"_on_settings_saved", "_apply_pending_port_changes"},
                               threading=SimpleNamespace(Thread=_CapturedThread))
        self.tray = tray = cls()
        tray.config = AppConfig(com_port="COM14", auto_update_enabled=False)
        tray.controller = SimpleNamespace(
            serial=SimpleNamespace(port="COM14"), stop=mock.Mock(), start=mock.Mock(),
        )
        tray._controller_restart_thread = None
        tray._controller_restart_lock = threading.Lock()
        tray._pending_port_restart = None

    def _request_port(self, port):
        self.tray.config.com_port = port
        self.tray._on_settings_saved(True)

    def test_two_saves_before_worker_runs_use_latest_target(self):
        self._request_port("COM7")
        self._request_port("COM9")
        self.assertEqual(len(_CapturedThread.created), 1)
        _CapturedThread.created[0].run()
        self.assertEqual(self.tray.controller.serial.port, "COM9")
        self.tray.controller.start.assert_called_once()

    def test_save_during_staged_shutdown_replaces_target_before_reopening_serial(self):
        opened = []
        self.tray.controller.stop.side_effect = lambda: self._request_port("COM9")
        self.tray.controller.start.side_effect = lambda: opened.append(self.tray.controller.serial.port)
        self._request_port("COM7")
        _CapturedThread.created[0].run()
        self.assertEqual(opened, ["COM9"])
        self.assertEqual(len(_CapturedThread.created), 1)

    def test_save_arriving_during_start_gets_a_subsequent_restart(self):
        opened = []
        def on_start():
            opened.append(self.tray.controller.serial.port)
            if len(opened) == 1:
                self._request_port("COM9")
        self.tray.controller.start.side_effect = on_start
        self._request_port("COM7")
        _CapturedThread.created[0].run()
        self.assertEqual(opened, ["COM7", "COM9"])
        self.assertEqual(len(_CapturedThread.created), 1)
        self.assertIsNone(self.tray._controller_restart_thread)

    def test_failed_restart_releases_worker_so_later_save_can_retry(self):
        self.tray.controller.stop.side_effect = [RuntimeError("stopping failed"), None]
        self._request_port("COM7")
        with self.assertLogs("settings-state-test", level="ERROR"):
            _CapturedThread.created[0].run()
        self._request_port("COM9")
        self.assertEqual(len(_CapturedThread.created), 2)
        _CapturedThread.created[1].run()
        self.assertEqual(self.tray.controller.serial.port, "COM9")
        self.tray.controller.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
