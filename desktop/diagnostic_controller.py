"""Diagnostic AppController extension for v0.5.0.

Kept separate from the current monolithic controller so issue #10 can later
fold these responsibilities into dedicated services without another large edit.
"""

from __future__ import annotations

import logging
import threading
import time

from app_controller import AppController
from diagnostic_serial import DiagnosticSerialService
from diagnostics import build_diagnostic_report, open_log_folder


log = logging.getLogger(__name__)


class DiagnosticAppController(AppController):
    def __init__(self, config):
        super().__init__(config)

        # Replace the base transport before start() so all normal controller
        # behavior uses the health-counting serial service.
        self.serial = DiagnosticSerialService(port=config.com_port)
        self.serial.on_connected = self._on_device_connected
        self.serial.on_disconnected = self._on_device_disconnected
        self.serial.on_message = self._on_hw_message
        self.serial.on_version = self._on_version

        self._firmware_version = "unknown"
        self._firmware_protocol = "unknown"
        self._last_update_log = ""
        self._last_update_error_code = ""

    @property
    def last_update_log(self) -> str:
        return self._last_update_log

    def _on_version(self, version: str):
        firmware_version, separator, protocol_value = version.rpartition(";P=")
        if separator:
            self._firmware_version = firmware_version or "unknown"
            try:
                self._firmware_protocol = int(protocol_value)
            except ValueError:
                self._firmware_protocol = protocol_value or "invalid"
        else:
            self._firmware_version = version or "unknown"
            self._firmware_protocol = "missing"
        return super()._on_version(version)

    def diagnostic_report(self) -> str:
        return build_diagnostic_report(
            self.serial.health_snapshot(),
            firmware_version=self._firmware_version,
            firmware_protocol=self._firmware_protocol,
            firmware_updating=self.firmware_updating,
            last_update_log=self._last_update_log,
        )

    def open_log_folder(self) -> None:
        open_log_folder()

    def start_firmware_update(self, path, on_progress=None, on_complete=None) -> bool:
        """Flash firmware with phase progress, classified errors and reconnect gate."""
        if not self._firmware_update_lock.acquire(blocking=False):
            return False
        self._firmware_updating = True
        self._last_update_error_code = ""

        def emit(value, text):
            if on_progress:
                try:
                    on_progress(value, text)
                except Exception:
                    log.exception("Firmware progress callback failed")

        def worker():
            success = False
            message = ""
            try:
                from firmware_updater import FirmwareUpdateError, flash_firmware

                emit(0.01, "Pausing VuNMix protocol traffic...")
                preferred_port = self.serial.port or self.config.com_port
                self.serial.stop()
                time.sleep(0.4)

                result = flash_firmware(
                    preferred_port,
                    path,
                    progress=emit,
                )
                self._last_update_log = result.log_path

                # A successful esptool exit only proves bytes were written.
                # Require the application protocol handshake after reset.
                if self._running:
                    emit(0.88, "Waiting for VuNMix to reconnect...")
                    self.serial.start()
                    deadline = time.monotonic() + 15.0
                    started_wait = time.monotonic()
                    while time.monotonic() < deadline:
                        if self.is_connected:
                            emit(1.0, "Firmware updated and VuNMix reconnected.")
                            success = True
                            message = (
                                "Firmware updated successfully and VuNMix reconnected.\n\n"
                                f"Update log: {result.log_path}"
                            )
                            break
                        elapsed = time.monotonic() - started_wait
                        emit(
                            min(0.99, 0.88 + (elapsed / 15.0) * 0.11),
                            f"Reconnecting VuNMix... {elapsed:.1f}s / 15s",
                        )
                        time.sleep(0.25)
                    if not success:
                        self._last_update_error_code = "RECONNECT_TIMEOUT"
                        message = (
                            "Firmware was written, but VuNMix did not complete the protocol "
                            "handshake within 15 seconds.\n\n"
                            "Code: RECONNECT_TIMEOUT\n"
                            f"Update log: {result.log_path}"
                        )
                else:
                    emit(1.0, "Firmware image written.")
                    success = True
                    message = (
                        "Firmware image was written. Start VuNMix to verify reconnect.\n\n"
                        f"Update log: {result.log_path}"
                    )
            except FirmwareUpdateError as exc:
                self._last_update_error_code = exc.code
                if exc.log_path:
                    self._last_update_log = exc.log_path
                log.error(
                    "Firmware update failed code=%s log=%s detail=%s",
                    exc.code,
                    exc.log_path or "-",
                    exc.detail or "-",
                    exc_info=True,
                )
                message = exc.user_message
                message += f"\n\nCode: {exc.code}"
                if exc.log_path:
                    message += f"\nUpdate log: {exc.log_path}"
            except Exception as exc:
                self._last_update_error_code = "UNEXPECTED"
                log.exception("Unexpected firmware update failure")
                message = (
                    "Firmware update failed unexpectedly. See the diagnostic log for details."
                    "\n\nCode: UNEXPECTED"
                )
            finally:
                self._firmware_updating = False
                self._firmware_update_lock.release()
                if self._running and not self.serial.is_connected:
                    self.serial.start()
                if on_complete:
                    try:
                        on_complete(success, message)
                    except Exception:
                        log.exception("Firmware completion callback failed")

        threading.Thread(
            target=worker,
            daemon=False,
            name="FirmwareUpdate",
        ).start()
        return True
