"""Device lifecycle/handshake behavior shared by the desktop controller."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import comtypes

from protocol import Command, DisplayMode, PROTOCOL_VERSION, SessionInfo


log = logging.getLogger(__name__)


class DeviceLifecycleMixin:
    """Power transitions, serial verification and initial-state handshake."""

    def _on_pc_sleep(self):
        log.info("PC entering sleep mode. Suspending VuNMix device.")
        self._is_sleeping = True
        self.serial.send_command(Command.SLEEP)

    def _on_pc_resume(self):
        log.info("PC resuming from sleep. Waking VuNMix device.")
        self._is_sleeping = False
        # Best-effort immediate wake for systems whose USB CDC link survived
        # suspend. The serialized recovery worker retries after re-enumeration.
        self.serial.send_command(Command.OK)

        with self._connection_lock:
            current = getattr(self, "_resume_recovery_thread", None)
            if current is not None and current.is_alive():
                return
            self._resume_recovering = True

            def recover_once():
                try:
                    self._recover_after_resume()
                finally:
                    with self._connection_lock:
                        self._resume_recovering = False

            worker = threading.Thread(
                target=recover_once,
                daemon=True,
                name="ResumeSync",
            )
            self._resume_recovery_thread = worker
            worker.start()

    def _recover_after_resume(self) -> bool:
        """Retry wake/state recovery while USB is settling after resume."""
        deadline = time.monotonic() + 12.0
        while self._running and not self._is_sleeping and time.monotonic() < deadline:
            if not self.is_connected:
                time.sleep(0.25)
                continue

            # OK is the explicit firmware host-wake signal. Do this before
            # SETTINGS/state so stale telemetry cannot implicitly wake display.
            if not self.serial.send_command(Command.OK):
                time.sleep(0.25)
                continue

            log.info("Pushing full state to recover device after sleep...")
            comtypes.CoInitialize()
            try:
                if not self.serial.send_settings(self.config.device_settings):
                    time.sleep(0.25)
                    continue
                time.sleep(0.1)
                self.audio.refresh()
                mode = self._session_info.mode
                if mode == DisplayMode.MODE_SPLASH:
                    mode = DisplayMode.MODE_OUTPUT
                if not self._push_full_state(mode):
                    raise ConnectionError("Failed to restore full state after resume")
                return True
            except Exception:
                log.exception("Resume state recovery failed; retrying")
                time.sleep(0.25)
            finally:
                comtypes.CoUninitialize()

        if self._running and not self._is_sleeping:
            log.warning("VuNMix resume recovery timed out waiting for device")
        return False

    def _on_device_connected(self):
        """Called when the COM port opens; protocol identity is not verified yet."""
        log.info("Serial port opened, verifying VuNMix firmware...")
        with self._connection_lock:
            self._device_connected = False
            self._update_only_connected = False
            self._handshake_token += 1
            token = self._handshake_token
        time.sleep(0.2)
        if not self.serial.send_test():
            return

        def handshake_watchdog():
            time.sleep(10.0)
            with self._connection_lock:
                timed_out = (
                    token == self._handshake_token
                    and not self._device_connected
                    and (
                        not self._update_only_connected
                        or self._handshake_in_progress
                    )
                )
            if timed_out:
                log.warning("VuNMix handshake timed out; reconnecting")
                self.serial.disconnect()

        threading.Thread(
            target=handshake_watchdog,
            daemon=True,
            name="HandshakeWatchdog",
        ).start()

    def _complete_handshake(self, token: int):
        def link_is_current() -> bool:
            with self._connection_lock:
                return (
                    token == self._handshake_token
                    and self.serial.is_connected
                )

        def clear_if_current() -> bool:
            with self._connection_lock:
                if token != self._handshake_token:
                    return False
                self._handshake_in_progress = False
                return True

        if not link_is_current():
            # A stale handshake must never clear the in-progress flag owned by
            # a newer reconnect generation.
            clear_if_current()
            return

        try:
            # A reconnect while the PC is awake must explicitly release any
            # host-sleep latch left in firmware. During actual PC sleep, keep
            # the latch intact even if the COM port briefly re-enumerates.
            if not self._is_sleeping:
                if not self.serial.send_command(Command.OK):
                    raise ConnectionError("Failed to send wake command")
                time.sleep(0.02)
                if not link_is_current():
                    return

            if not self.serial.send_settings(self.config.device_settings):
                raise ConnectionError("Failed to send settings during handshake")
            time.sleep(0.1)
            if not link_is_current():
                return

            now = datetime.now()
            if not self.serial.send_time_sync(now.hour, now.minute, now.second):
                raise ConnectionError("Failed to send time sync during handshake")
            time.sleep(0.05)
            if not link_is_current():
                return

            comtypes.CoInitialize()
            try:
                self.audio.refresh()
                if not link_is_current():
                    return
                if not self._push_full_state(DisplayMode.MODE_OUTPUT):
                    raise ConnectionError("Failed to send full state during handshake")
                log.info(
                    "Initial state sent: output=%d input=%d apps=%d",
                    self.audio.get_session_count(DisplayMode.MODE_OUTPUT),
                    self.audio.get_session_count(DisplayMode.MODE_INPUT),
                    self.audio.get_session_count(DisplayMode.MODE_APPLICATION),
                )
            finally:
                comtypes.CoUninitialize()

            # Do not expose Connected merely because Windows opened the COM
            # port. We only reach this point after a valid TEST response and
            # successful initial state transfer.
            with self._connection_lock:
                if token != self._handshake_token or not self.serial.is_connected:
                    if token == self._handshake_token:
                        self._handshake_in_progress = False
                    return
                self._device_connected = True
                self._update_only_connected = True
                self._handshake_in_progress = False

            if self.on_connection_changed:
                self.on_connection_changed(True)

            if self.on_device_ready:
                try:
                    self.on_device_ready()
                except Exception:
                    log.exception("Device-ready callback failed")
        except Exception:
            log.exception("Failed to initialize device after handshake")
            if clear_if_current():
                self.serial.disconnect()

    def _on_device_disconnected(self):
        """Called when serial port closes."""
        log.info("Device disconnected")
        with self._connection_lock:
            self._handshake_token += 1
            self._device_connected = False
            self._update_only_connected = False
            self._handshake_in_progress = False
            self._sent_icon_ids.clear()
            self._session_info = SessionInfo()
        if self.on_connection_changed:
            self.on_connection_changed(False)

    def _on_version(self, version: str):
        firmware_version, separator, protocol_value = version.rpartition(";P=")
        if not separator:
            log.error("Rejecting firmware without protocol version: %s", version)
            with self._connection_lock:
                self._update_only_connected = True
            return
        try:
            firmware_protocol = int(protocol_value)
        except ValueError:
            log.error("Rejecting firmware with invalid protocol version: %s", version)
            with self._connection_lock:
                self._update_only_connected = True
            return
        if firmware_protocol != PROTOCOL_VERSION:
            log.error(
                "Protocol mismatch: desktop=%d firmware=%d (%s)",
                PROTOCOL_VERSION,
                firmware_protocol,
                firmware_version,
            )
            with self._connection_lock:
                self._update_only_connected = True
            return
        log.info(
            "Firmware version: %s (protocol %d)",
            firmware_version,
            firmware_protocol,
        )
        with self._connection_lock:
            if self._device_connected or getattr(self, "_handshake_in_progress", False):
                return
            self._update_only_connected = True
            self._handshake_in_progress = True
            token = self._handshake_token
        threading.Thread(
            target=self._complete_handshake,
            args=(token,),
            daemon=True,
            name="DeviceHandshake",
        ).start()
