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
        self.serial.send_command(Command.OK)

        def delayed_resume():
            # Wait a bit for USB to settle and device to potentially boot.
            time.sleep(2.0)
            if not self.is_connected:
                return
            log.info("Pushing full state to recover device after sleep...")
            comtypes.CoInitialize()
            try:
                self.serial.send_settings(self.config.device_settings)
                time.sleep(0.1)
                self.audio.refresh()
                mode = self._session_info.mode
                if mode == DisplayMode.MODE_SPLASH:
                    mode = DisplayMode.MODE_OUTPUT
                self._push_full_state(mode)
            finally:
                comtypes.CoUninitialize()

        threading.Thread(
            target=delayed_resume,
            daemon=True,
            name="ResumeSync",
        ).start()

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
                    and not self._update_only_connected
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
        with self._connection_lock:
            valid_token = token == self._handshake_token
        if not valid_token or not self.serial.is_connected:
            return

        try:
            self.serial.send_settings(self.config.device_settings)
            time.sleep(0.1)

            now = datetime.now()
            self.serial.send_time_sync(now.hour, now.minute, now.second)
            time.sleep(0.05)

            comtypes.CoInitialize()
            try:
                self.audio.refresh()
                self._push_full_state(DisplayMode.MODE_OUTPUT)
                log.info(
                    "Initial state sent: output=%d input=%d apps=%d",
                    self.audio.get_session_count(DisplayMode.MODE_OUTPUT),
                    self.audio.get_session_count(DisplayMode.MODE_INPUT),
                    self.audio.get_session_count(DisplayMode.MODE_APPLICATION),
                )
            finally:
                comtypes.CoUninitialize()
        except Exception:
            log.exception("Failed to initialize device after handshake")
            if token == self._handshake_token:
                self.serial.disconnect()

    def _on_device_disconnected(self):
        """Called when serial port closes."""
        log.info("Device disconnected")
        with self._connection_lock:
            self._handshake_token += 1
            self._device_connected = False
            self._update_only_connected = False
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
            if self._device_connected:
                return
            self._device_connected = True
            self._update_only_connected = True
            token = self._handshake_token
        if self.on_connection_changed:
            self.on_connection_changed(True)
        threading.Thread(
            target=self._complete_handshake,
            args=(token,),
            daemon=True,
            name="DeviceHandshake",
        ).start()
