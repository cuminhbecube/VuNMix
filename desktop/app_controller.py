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
import win32api
import win32con
import win32gui

from protocol import (
    Command, DisplayMode, SessionIndex,
    SessionInfo, SessionData, VolumeData, DeviceSettings, ModeStates,
    SESSION_COMMANDS, VOLUME_COMMANDS,
)
from config import AppConfig
from serial_service import SerialService
from audio_service import AudioService

log = logging.getLogger(__name__)

class PowerMonitor:
    def __init__(self, on_sleep, on_resume):
        self.on_sleep = on_sleep
        self.on_resume = on_resume
        self.hwnd = None
        self._thread = threading.Thread(target=self._run_message_loop, daemon=True, name="PowerMonitor")
        self._thread.start()

    def _run_message_loop(self):
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = 'VuNMixPowerMonitor'
        wc.hInstance = win32api.GetModuleHandle(None)
        
        try:
            win32gui.RegisterClass(wc)
        except win32gui.error:
            pass
            
        self.hwnd = win32gui.CreateWindow(
            'VuNMixPowerMonitor', 'VuNMix Power Monitor',
            0, 0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT,
            0, 0, wc.hInstance, None
        )
        win32gui.PumpMessages()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            if wparam == win32con.PBT_APMSUSPEND:
                if self.on_sleep:
                    self.on_sleep()
            elif wparam == win32con.PBT_APMRESUMEAUTOMATIC:
                if self.on_resume:
                    self.on_resume()
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def stop(self):
        if self.hwnd:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_QUIT, 0, 0)
            except Exception:
                pass



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
        self._is_sleeping = False

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

        # Power monitor
        self._power_monitor = PowerMonitor(self._on_pc_sleep, self._on_pc_resume)

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
        self._power_monitor.stop()
        self._running = False
        self.serial.stop()
        if self._sync_thread:
            self._sync_thread.join(timeout=3.0)
            self._sync_thread = None

    @property
    def is_connected(self) -> bool:
        return self._device_connected

    def _on_pc_sleep(self):
        log.info("PC entering sleep mode. Suspending VuNMix device.")
        self._is_sleeping = True
        self.serial.send_command(Command.SLEEP)

    def _on_pc_resume(self):
        log.info("PC resuming from sleep. Waking VuNMix device.")
        self._is_sleeping = False
        self.serial.send_command(Command.OK)
        
        def delayed_resume():
            # Wait a bit for USB to settle and device to potentially boot
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

        threading.Thread(target=delayed_resume, daemon=True, name="ResumeSync").start()

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
        self._session_info = info

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
            
            # If hardware marked this as default and it isn't yet, apply to Windows
            if vol.is_default and not items[win_idx].is_default:
                self.audio.set_default_device(mode, win_idx)
                # Re-push sessions so the UI/hardware updates with the new default flags
                self._handle_session_info_from_hw(self._session_info)

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

        # Send mode states
        self.serial.send_mode_states(self._mode_states)

        # Send sessions
        self._push_sessions_for_mode(mode, 0)

    def _push_updated_state(self):
        """Re-push state after a refresh, preserving current index if possible."""
        mode = self._session_info.mode
        items = self.audio.get_sessions_for_mode(mode)
        
        n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
        n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
        n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)
        
        current_idx = self._session_info.current
        if items and current_idx >= len(items):
            current_idx = len(items) - 1
        elif not items:
            current_idx = 0
            
        self._session_info.sessions = [max(n_output, 1), max(n_input, 1), max(n_app, 1)]
        self._session_info.current = current_idx
        
        self.serial.send_session_info(self._session_info)
        self.serial.send_mode_states(self._mode_states)
        self._push_sessions_for_mode(mode, current_idx)

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

        # Previous
        if count > 1:
            prev_idx = (current_idx - 1) % count
            prev = items[prev_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_PREVIOUS] = prev
            self.serial.send_session(Command.PREVIOUS_SESSION, prev)

        # Next
        if count > 1:
            next_idx = (current_idx + 1) % count
            nxt = items[next_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_NEXT] = nxt
            self.serial.send_session(Command.NEXT_SESSION, nxt)

    # ─── Periodic Sync ─────────────────────────────────────────────────
    def _sync_loop(self):
        """Periodically refresh audio sessions and sync volume to hardware."""
        interval = self.config.update_interval_ms / 1000.0
        last_heartbeat = time.monotonic()
        last_full_refresh = time.monotonic()

        while self._running:
            time.sleep(interval)

            if not self._device_connected or self._is_sleeping:
                continue

            now = time.monotonic()
            
            # Send heartbeat every 2 seconds to prevent hardware timeout
            if now - last_heartbeat >= 2.0:
                self.serial.send_command(Command.OK)
                last_heartbeat = now

            if self._session_info.mode == DisplayMode.MODE_SPLASH:
                continue

            # Periodic full refresh to catch new apps (every 5s)
            if now - last_full_refresh >= 5.0:
                comtypes.CoInitialize()
                try:
                    def get_sig():
                        sig = []
                        for m in (DisplayMode.MODE_OUTPUT, DisplayMode.MODE_INPUT, DisplayMode.MODE_APPLICATION):
                            sig.extend((x.id, x.name, x.is_default) for x in self.audio.get_sessions_for_mode(m))
                        return sig

                    old_sig = get_sig()
                    self.audio.refresh()
                    new_sig = get_sig()

                    if old_sig != new_sig:
                        log.info("Audio devices/apps changed in background. Pushing updated state.")
                        self._push_updated_state()
                finally:
                    comtypes.CoUninitialize()
                last_full_refresh = now
                continue

            # Read current volume from Windows and push if changed
            comtypes.CoInitialize()
            try:
                if self.audio.check_system_changes():
                    log.info("System audio changes detected. Refreshing...")
                    self.audio.refresh()
                    self._push_updated_state()
                    continue

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
