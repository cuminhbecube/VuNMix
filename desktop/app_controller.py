"""
VuNMix App Controller — Orchestrator connecting Audio ↔ Serial.

Handles:
- Initial handshake (TEST → SETTINGS → SESSION_INFO → sessions)
- Periodic sync of audio state to hardware
- Processing hardware commands (volume knob, mode change, navigation)
- Applying volume changes from hardware to Windows
"""

import logging
import threading
import time
from typing import Optional

import comtypes

from protocol import (
    Command, DisplayMode, SessionIndex,
    SessionInfo, SessionData, VolumeData, DeviceSettings, ModeStates,
    SESSION_COMMANDS, VOLUME_COMMANDS,
)
from config import AppConfig
from serial_service import SerialService
from audio_service import AudioService

log = logging.getLogger(__name__)


class AppController:
    """Main controller: bridges audio sessions ↔ serial hardware."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.serial = SerialService(port=config.com_port)
        self.audio = AudioService()

        # Firmware state mirrors
        self._session_info = SessionInfo()
        self._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        self._mode_states = ModeStates()
        self._device_connected = False

        # Sync thread
        self._sync_thread: Optional[threading.Thread] = None
        self._running = False

        # Wire serial callbacks
        self.serial.on_connected = self._on_device_connected
        self.serial.on_disconnected = self._on_device_disconnected
        self.serial.on_message = self._on_hw_message
        self.serial.on_version = self._on_version

        # Public callbacks for GUI
        self.on_connection_changed: Optional[callable] = None

    def start(self):
        """Start serial reader and periodic sync."""
        log.info("AppController starting...")
        self._running = True
        self.serial.start()

        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True, name="AudioSync")
        self._sync_thread.start()

    def stop(self):
        """Stop everything."""
        log.info("AppController stopping...")
        self._running = False
        self.serial.stop()
        if self._sync_thread:
            self._sync_thread.join(timeout=3.0)
            self._sync_thread = None

    @property
    def is_connected(self) -> bool:
        return self._device_connected

    # ─── Connection Events ─────────────────────────────────────────────
    def _on_device_connected(self):
        """Called when serial port opens successfully."""
        log.info("Device connected, sending handshake...")
        self._device_connected = True
        if self.on_connection_changed:
            self.on_connection_changed(True)

        # Handshake sequence
        time.sleep(0.2)
        self.serial.send_test()
        time.sleep(0.3)

        # Send settings
        self.serial.send_settings(self.config.device_settings)
        time.sleep(0.1)

        # Refresh audio and push initial state
        comtypes.CoInitialize()
        try:
            self.audio.refresh()
            self._push_full_state(DisplayMode.MODE_OUTPUT)
        finally:
            comtypes.CoUninitialize()

    def _on_device_disconnected(self):
        """Called when serial port closes."""
        log.info("Device disconnected")
        self._device_connected = False
        self._session_info = SessionInfo()
        if self.on_connection_changed:
            self.on_connection_changed(False)

    def _on_version(self, version: str):
        log.info(f"Firmware version: {version}")

    # ─── Hardware Message Handling ─────────────────────────────────────
    def _on_hw_message(self, cmd: Command, payload: bytes):
        """Process a message received from hardware."""
        if cmd == Command.SESSION_INFO:
            info = SessionInfo.unpack(payload)
            log.debug(f"HW→PC SESSION_INFO: mode={info.mode}, current={info.current}")
            self._handle_session_info_from_hw(info)

        elif cmd in SESSION_COMMANDS:
            idx = int(cmd) - int(Command.CURRENT_SESSION)
            session = SessionData.unpack(payload)
            log.debug(f"HW→PC {cmd.name}: name={session.name}")
            self._sessions[idx] = session

        elif cmd in VOLUME_COMMANDS:
            idx = int(cmd) - int(Command.VOLUME_CURR_CHANGE)
            vol = VolumeData.unpack(payload)
            log.debug(f"HW→PC {cmd.name}: vol={vol.volume}, muted={vol.is_muted}")
            self._sessions[idx].data = vol
            self._apply_volume_to_windows(idx, vol)

        elif cmd == Command.MODE_STATES:
            self._mode_states = ModeStates.unpack(payload)
            log.debug(f"HW→PC MODE_STATES: {self._mode_states.states}")

    def _handle_session_info_from_hw(self, info: SessionInfo):
        """Hardware changed mode or navigated — send appropriate sessions."""
        old_mode = self._session_info.mode
        self._session_info = info

        if info.mode != old_mode or info.mode == DisplayMode.MODE_SPLASH:
            # Mode changed, refresh and push new state
            comtypes.CoInitialize()
            try:
                self.audio.refresh()
                self._push_sessions_for_mode(info.mode, info.current)
            finally:
                comtypes.CoUninitialize()
        else:
            # Navigation within same mode — send requested sessions
            comtypes.CoInitialize()
            try:
                self._push_sessions_for_mode(info.mode, info.current)
            finally:
                comtypes.CoUninitialize()

    def _apply_volume_to_windows(self, session_idx: int, vol: VolumeData):
        """Apply volume change from hardware knob to Windows."""
        mode = self._session_info.mode
        items = self.audio.get_sessions_for_mode(mode)

        # Determine which Windows session to modify
        if session_idx == SessionIndex.INDEX_CURRENT:
            win_idx = self._session_info.current
        elif session_idx == SessionIndex.INDEX_ALTERNATE:
            # In GAME mode, alternate might differ
            win_idx = self._session_info.current
        else:
            return

        if 0 <= win_idx < len(items):
            self.audio.set_volume(mode, win_idx, vol.volume, vol.is_muted)
            log.info(f"Applied vol={vol.volume}% muted={vol.is_muted} to {items[win_idx].name}")

    # ─── Push State to Hardware ────────────────────────────────────────
    def _push_full_state(self, mode: int):
        """Send complete state for a display mode to hardware."""
        items = self.audio.get_sessions_for_mode(mode)
        n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
        n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
        n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)

        self._session_info = SessionInfo(
            mode=mode,
            current=0,
            sessions=[max(n_output, 1), max(n_input, 1), max(n_app, 1)],
        )
        self._mode_states = ModeStates(states=[0, 1, 1, 0, 0])

        # Send session info
        self.serial.send_session_info(self._session_info)
        time.sleep(0.05)

        # Send mode states
        self.serial.send_mode_states(self._mode_states)
        time.sleep(0.05)

        # Send sessions
        self._push_sessions_for_mode(mode, 0)

    def _push_sessions_for_mode(self, mode: int, current_idx: int):
        """Send current/prev/next sessions for a mode."""
        items = self.audio.get_sessions_for_mode(mode)
        if not items:
            # Send empty session
            empty = SessionData(name="No sessions")
            self.serial.send_session(Command.CURRENT_SESSION, empty)
            return

        count = len(items)
        current_idx = current_idx % count if count > 0 else 0

        # Current
        cur = items[current_idx].to_session_data()
        self._sessions[SessionIndex.INDEX_CURRENT] = cur
        self.serial.send_session(Command.CURRENT_SESSION, cur)
        time.sleep(0.02)

        # Previous
        if count > 1:
            prev_idx = (current_idx - 1) % count
            prev = items[prev_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_PREVIOUS] = prev
            self.serial.send_session(Command.PREVIOUS_SESSION, prev)
            time.sleep(0.02)

        # Next
        if count > 1:
            next_idx = (current_idx + 1) % count
            nxt = items[next_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_NEXT] = nxt
            self.serial.send_session(Command.NEXT_SESSION, nxt)
            time.sleep(0.02)

    # ─── Periodic Sync ─────────────────────────────────────────────────
    def _sync_loop(self):
        """Periodically refresh audio sessions and sync volume to hardware."""
        interval = self.config.update_interval_ms / 1000.0
        last_heartbeat = time.monotonic()

        while self._running:
            time.sleep(interval)

            if not self._device_connected:
                continue

            # Send heartbeat every 2 seconds to prevent hardware timeout
            now = time.monotonic()
            if now - last_heartbeat >= 2.0:
                self.serial.send_command(Command.OK)
                last_heartbeat = now

            if self._session_info.mode == DisplayMode.MODE_SPLASH:
                continue

            # Read current volume from Windows and push if changed
            comtypes.CoInitialize()
            try:
                mode = self._session_info.mode
                idx = self._session_info.current
                vol = self.audio.read_current_volume(mode, idx)
                if vol and self._sessions[SessionIndex.INDEX_CURRENT].data:
                    old = self._sessions[SessionIndex.INDEX_CURRENT].data
                    if vol.volume != old.volume or vol.is_muted != old.is_muted:
                        self._sessions[SessionIndex.INDEX_CURRENT].data = vol
                        self.serial.send_volume(Command.VOLUME_CURR_CHANGE, vol)
            except Exception as e:
                log.debug(f"Sync error: {e}")
            finally:
                comtypes.CoUninitialize()
