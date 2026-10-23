"""Update ownership and cancellation regressions without Windows or hardware."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock


DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))

import app_updater
from firmware_release import should_auto_update_firmware
from update_coordinator import UpdateCoordinator, start_firmware_thread


def actual_class(filename, class_name, methods, **extra):
    """Compile actual method bodies without constructing Windows/Tk services."""
    tree = ast.parse((DESKTOP / filename).read_text(encoding="utf-8"))
    source = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    cls = ast.ClassDef(name=class_name, bases=[], keywords=[], decorator_list=[], body=[
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name in methods
    ])
    namespace = {
        "threading": threading, "time": time, "log": logging.getLogger("update-test"),
        "UpdateInfo": object, "FirmwareReleaseInfo": object, "APP_VERSION": "0.4.31",
        "should_auto_update_firmware": should_auto_update_firmware,
        "start_firmware_thread": start_firmware_thread,
        **extra,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 str(DESKTOP / filename), "exec"), namespace)
    return namespace[class_name]


class CapturedThread:
    created = []

    def __init__(self, target=None, **kwargs):
        self.target = target
        self.name = kwargs.get("name")
        self.__class__.created.append(self)

    def start(self):
        pass


class UpdateLifecycleTests(unittest.TestCase):
    def setUp(self):
        CapturedThread.created = []
        self.info = SimpleNamespace(tag="v0.4.32", version="0.4.32")
        cls = actual_class("gui.py", "TrayApp", {
            "_start_app_update_install", "_check_app_update_worker", "_auto_firmware_update_worker",
        })
        self.tray = cls()
        self.tray.controller = SimpleNamespace(updates=UpdateCoordinator())
        self.tray._dispatch_ui = mock.Mock()
        self.tray._app_updater = mock.Mock()
        self.tray._update_check_lock = threading.Lock()
        self.tray._notified_update_tag = None

    def firmware_controller(self, filename="diagnostic_controller.py", sleep=lambda _: None):
        name = "DiagnosticAppController" if filename.startswith("diagnostic") else "AppController"
        cls = actual_class(filename, name, {"start_firmware_update"},
                           time=SimpleNamespace(sleep=sleep, monotonic=time.monotonic))
        controller = cls()
        controller.updates = self.tray.controller.updates
        controller._firmware_updating = False
        controller._running = False
        controller.config = SimpleNamespace(com_port="COM14")
        controller.serial = mock.Mock(port="COM14")
        return controller

    def test_app_reserves_download_and_handoff_against_firmware_and_duplicate_requests(self):
        controller = self.firmware_controller()
        self.tray.controller = controller
        settings_cls = actual_class("gui.py", "SettingsDialog", {"start_app_update"})
        settings = settings_cls()
        settings.on_install_app_update = self.tray._start_app_update_install
        settings.set_app_update_checking = mock.Mock()
        settings._app_update_status_var = mock.Mock()
        with mock.patch("threading.Thread", CapturedThread):
            settings.start_app_update(self.info)
            self.assertFalse(controller.start_firmware_update("unused.bin"))
            self.tray._check_app_update_worker(manual=True)
            self.tray._app_updater.check_latest.assert_not_called()
            settings.start_app_update(self.info)  # an already queued second prompt
            self.assertEqual(len(CapturedThread.created), 1)
            CapturedThread.created[0].target()
            self.tray._app_updater.download_and_install.assert_called_once()
            self.assertTrue(controller.updates.busy)
            self.assertFalse(controller.start_firmware_update("unused.bin"))
            self.assertFalse(self.tray._start_app_update_install(self.info))

    def test_firmware_reserves_before_worker_start_and_blocks_installer(self):
        for filename in ("app_controller.py", "diagnostic_controller.py"):
            with self.subTest(filename=filename):
                self.tray.controller = SimpleNamespace(updates=UpdateCoordinator())
                controller = self.firmware_controller(filename)
                self.tray.controller = controller
                CapturedThread.created = []
                with mock.patch("threading.Thread", CapturedThread):
                    self.assertTrue(controller.start_firmware_update("unused.bin"))
                    self.assertTrue(controller._firmware_updating)
                    self.assertFalse(self.tray._start_app_update_install(self.info))
                    self.assertEqual(len(CapturedThread.created), 1)
                self.tray._app_updater.download_and_install.assert_not_called()

    def test_app_download_failure_releases_reservation_for_retry(self):
        self.tray._app_updater.download_and_install.side_effect = app_updater.UpdateError("offline")
        with mock.patch("threading.Thread", CapturedThread):
            self.assertTrue(self.tray._start_app_update_install(self.info))
            CapturedThread.created[0].target()
            self.assertFalse(self.tray.controller.updates.busy)
            self.assertTrue(self.tray._start_app_update_install(self.info))

    def test_thread_creation_failures_release_app_and_firmware_reservations(self):
        with mock.patch("threading.Thread") as factory:
            factory.return_value.start.side_effect = RuntimeError("cannot start thread")
            with self.assertRaises(RuntimeError):
                self.tray._start_app_update_install(self.info)
            self.assertFalse(self.tray.controller.updates.busy)
            for filename in ("app_controller.py", "diagnostic_controller.py"):
                controller = self.firmware_controller(filename)
                with self.assertRaises(RuntimeError):
                    controller.start_firmware_update("unused.bin")
                self.assertFalse(controller.updates.busy)
                self.assertFalse(controller._firmware_updating)

    def auto_check(self):
        tray = self.tray
        tray.config = SimpleNamespace(auto_firmware_update_enabled=True)
        tray.controller.is_connected = True
        tray.controller.firmware_updating = False
        tray.controller.firmware_version = "0.4.30"
        tray._update_stop = mock.Mock()
        tray._update_stop.wait.return_value = False
        tray._update_stop.is_set.return_value = False
        tray._firmware_auto_lock = threading.Lock()
        tray._auto_firmware_attempted = set()
        tray._firmware_release_client = SimpleNamespace(get_version=mock.Mock(return_value=self.info))
        tray._ensure_settings_dialog = mock.Mock()
        tray._schedule_firmware_retry = mock.Mock()
        return tray

    def test_disabling_auto_firmware_during_settle_wait_prevents_lookup(self):
        tray = self.auto_check()
        def disable(_seconds):
            tray.config.auto_firmware_update_enabled = False
            return False
        tray._update_stop.wait.side_effect = disable
        tray._auto_firmware_update_worker()
        tray._firmware_release_client.get_version.assert_not_called()
        tray._dispatch_ui.assert_not_called()

    def test_disabling_auto_firmware_during_metadata_request_prevents_dispatch(self):
        tray = self.auto_check()
        def disable(_version):
            tray.config.auto_firmware_update_enabled = False
            return self.info
        tray._firmware_release_client.get_version.side_effect = disable
        tray._auto_firmware_update_worker()
        tray._dispatch_ui.assert_not_called()
        self.assertFalse(tray._auto_firmware_attempted)

    def test_disabling_auto_firmware_before_queued_ui_callback_cancels_attempt(self):
        tray = self.auto_check()
        tray._auto_firmware_update_worker()
        callback = tray._dispatch_ui.call_args.args[0]
        tray.config.auto_firmware_update_enabled = False
        callback()
        tray._ensure_settings_dialog.assert_not_called()
        self.assertFalse(tray._auto_firmware_attempted)

    def test_disabling_auto_firmware_during_download_prevents_flash(self):
        cls = actual_class("gui.py", "SettingsDialog", {
            "start_firmware_release_update", "_firmware_release_start_failed",
        })
        dialog = cls()
        dialog.config = SimpleNamespace(auto_firmware_update_enabled=True)
        dialog.controller = SimpleNamespace(can_update_firmware=True, start_firmware_update=mock.Mock())
        dialog._firmware_release_loading = False
        dialog._firmware_progress = mock.Mock()
        dialog._firmware_status_var = mock.Mock()
        dialog._ui_call = lambda callback: callback()
        def download(*args, **kwargs):
            dialog.config.auto_firmware_update_enabled = False
            return Path("unused.bin")
        dialog._firmware_release_client = SimpleNamespace(download=download)
        with mock.patch("threading.Thread", CapturedThread):
            dialog.start_firmware_release_update(self.info, automatic=True)
            CapturedThread.created[0].target()
        dialog.controller.start_firmware_update.assert_not_called()
        self.assertFalse(dialog._firmware_release_loading)
        dialog._firmware_status_var.set.assert_called_with("Auto FW update cancelled")

    def test_last_moment_cancel_releases_firmware_but_started_flash_finishes(self):
        for filename in ("app_controller.py", "diagnostic_controller.py"):
            for cancel_before_flash in (True, False):
                with self.subTest(filename=filename, cancel_before_flash=cancel_before_flash):
                    self.tray.controller = SimpleNamespace(updates=UpdateCoordinator())
                    enabled = [True]
                    def pause(_seconds):
                        if cancel_before_flash:
                            enabled[0] = False
                    controller = self.firmware_controller(filename, sleep=pause)
                    def flash(*args, **kwargs):
                        enabled[0] = False  # cancellation cannot abort a started write
                        return SimpleNamespace(log_path="test.log")
                    stub = SimpleNamespace(flash_firmware=mock.Mock(side_effect=flash),
                                           FirmwareUpdateError=RuntimeError)
                    complete = mock.Mock()
                    with mock.patch.dict(sys.modules, {"firmware_updater": stub}), \
                         mock.patch("threading.Thread", CapturedThread):
                        controller.start_firmware_update("unused.bin", on_complete=complete,
                                                         should_start=lambda: enabled[0])
                        CapturedThread.created[-1].target()
                    self.assertEqual(stub.flash_firmware.call_count, 0 if cancel_before_flash else 1)
                    self.assertEqual(complete.call_args.args[0], not cancel_before_flash)
                    self.assertFalse(controller.updates.busy)
                    self.assertFalse(controller._firmware_updating)

    def test_stale_cleanup_cannot_release_next_update(self):
        updates = UpdateCoordinator()
        first = updates.try_begin("firmware")
        updates.finish(first)
        second = updates.try_begin("app")
        updates.finish(first)
        self.assertTrue(updates.busy)
        updates.finish(second)
        self.assertFalse(updates.busy)


class UpdateDownloadIsolationTests(unittest.TestCase):
    def test_failed_duplicate_cannot_delete_successful_download_staging_file(self):
        payload = b"test-installer" * 1024
        digest = hashlib.sha256(payload).hexdigest()
        first_ready, second_done = threading.Event(), threading.Event()
        local = threading.local()
        real_replace = app_updater.os.replace

        class Response:
            headers = {"Content-Length": str(len(payload))}
            def __init__(self):
                self.sent = False
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, _size):
                if local.role == "second":
                    raise TimeoutError("duplicate failed")
                if self.sent:
                    return b""
                self.sent = True
                return payload

        def replace(source, destination):
            if local.role == "first":
                first_ready.set()
                if not second_done.wait(3):
                    raise RuntimeError("test deadline")
            real_replace(source, destination)

        info = SimpleNamespace(installer_name="VuNMix-Windows-Setup-0.4.32.exe",
                               installer_url="https://example.invalid/test.exe", tag="v0.4.32")
        updater = app_updater.AppUpdater("0.4.31")
        def download(role):
            local.role = role
            try:
                return updater._download_installer(info, digest)
            finally:
                if role == "second":
                    second_done.set()

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app_updater, "UPDATE_DIR", Path(directory)), \
             mock.patch.object(app_updater.urllib.request, "urlopen", side_effect=lambda *a, **k: Response()), \
             mock.patch.object(app_updater.os, "replace", side_effect=replace):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(download, "first")
                self.assertTrue(first_ready.wait(2))
                second = pool.submit(download, "second")
                with self.assertRaises(app_updater.UpdateError):
                    second.result(timeout=2)
                installed = first.result(timeout=2)
            self.assertEqual(installed.read_bytes(), payload)
            self.assertEqual(list(Path(directory).iterdir()), [installed])


if __name__ == "__main__":
    unittest.main()
