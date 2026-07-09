"""
VuNMix App Controller — Orchestrator connecting Audio ↔ Serial.

Handles:
- Initial handshake (TEST → SETTINGS → SESSION_INFO → sessions)
- Periodic sync of audio state to hardware
- Processing hardware commands (volume knob, mode change, navigation)
- Applying volume changes from hardware to Windows
"""

import logging
import math
import threading
import time
from datetime import datetime
from typing import Optional

import comtypes
import win32api
import win32con
import win32gui

from protocol import (
    Command, DisplayMode, SessionIndex,
    SessionInfo, SessionData, VolumeData, MeterData, DeviceSettings, ModeStates,
    SESSION_COMMANDS, VOLUME_COMMANDS,
)
from config import AppConfig
from serial_service import SerialService
from audio_service import AudioService
from app_icon import app_icon_rgb565

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
        elif msg == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def stop(self):
        if self.hwnd:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.hwnd = None



class AppController:
    """Main controller: bridges audio sessions ↔ serial hardware."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.serial = SerialService(port=config.com_port)
        self.audio = AudioService()
        self.audio.set_favorite_apps(config.favorite_apps)

        # Firmware state mirrors
        self._session_info = SessionInfo()
        self._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        self._mode_states = ModeStates()
        self._meter_data = MeterData()
        self._device_connected = False
        self._is_sleeping = False
        self._handshake_token = 0
        self._sent_icon_ids = set()

        # Sync thread
        self._sync_thread: Optional[threading.Thread] = None
        self._meter_thread: Optional[threading.Thread] = None
        self._firmware_update_lock = threading.Lock()
        self._firmware_updating = False
        self._running = False

        # Wire serial callbacks
        self.serial.on_connected = self._on_device_connected
        self.serial.on_disconnected = self._on_device_disconnected
        self.serial.on_message = self._on_hw_message
        self.serial.on_version = self._on_version

        # Public callbacks for GUI
        self.on_connection_changed: Optional[callable] = None

        # Power monitor
        self._power_monitor: Optional[PowerMonitor] = None

    def start(self):
        """Start serial reader and periodic sync."""
        log.info("AppController starting...")
        if self._power_monitor is None:
            self._power_monitor = PowerMonitor(self._on_pc_sleep, self._on_pc_resume)
        self._running = True
        self.serial.start()

        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True, name="AudioSync")
        self._sync_thread.start()
        self._meter_thread = threading.Thread(target=self._meter_loop, daemon=True, name="AudioMeter")
        self._meter_thread.start()

    def stop(self):
        """Stop everything."""
        log.info("AppController stopping...")
        if self._power_monitor is not None:
            self._power_monitor.stop()
            self._power_monitor = None
        self._running = False
        self.serial.stop()
        if self._sync_thread:
            self._sync_thread.join(timeout=3.0)
            self._sync_thread = None
        if self._meter_thread:
            self._meter_thread.join(timeout=3.0)
            self._meter_thread = None

    @property
    def is_connected(self) -> bool:
        return self._device_connected

    @property
    def firmware_updating(self) -> bool:
        return self._firmware_updating

    def start_firmware_update(self, path, on_progress=None, on_complete=None) -> bool:
        """Stop protocol traffic, flash firmware in a worker, then reconnect."""
        if not self._firmware_update_lock.acquire(blocking=False):
            return False
        self._firmware_updating = True

        def worker():
            success = False
            message = ""
            try:
                from firmware_updater import flash_firmware
                self.serial.stop()
                time.sleep(0.5)
                flash_firmware(
                    self.config.com_port,
                    path,
                    progress=on_progress,
                )
                success = True
                message = "Firmware update completed successfully."
            except Exception as exc:
                log.exception("Firmware update failed")
                message = str(exc)
            finally:
                self._firmware_updating = False
                self._firmware_update_lock.release()
                if self._running:
                    self.serial.start()
                if on_complete:
                    on_complete(success, message)

        threading.Thread(
            target=worker,
            daemon=False,
            name="FirmwareUpdate",
        ).start()
        return True

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
        """Called when the COM port opens; protocol identity is not verified yet."""
        log.info("Serial port opened, verifying VuNMix firmware...")
        self._device_connected = False
        self._handshake_token += 1
        token = self._handshake_token
        time.sleep(0.2)
        self.serial.send_test()

        def handshake_watchdog():
            time.sleep(10.0)
            if token == self._handshake_token and not self._device_connected:
                log.warning("VuNMix handshake timed out; reconnecting")
                self.serial.disconnect()

        threading.Thread(
            target=handshake_watchdog,
            daemon=True,
            name="HandshakeWatchdog",
        ).start()

    def _complete_handshake(self, token: int):
        if token != self._handshake_token or not self.serial.is_connected:
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
        self._handshake_token += 1
        self._device_connected = False
        self._sent_icon_ids.clear()
        self._session_info = SessionInfo()
        if self.on_connection_changed:
            self.on_connection_changed(False)

    def _on_version(self, version: str):
        log.info(f"Firmware version: {version}")
        if self._device_connected:
            return
        self._device_connected = True
        token = self._handshake_token
        if self.on_connection_changed:
            self.on_connection_changed(True)
        threading.Thread(
            target=self._complete_handshake,
            args=(token,),
            daemon=True,
            name="DeviceHandshake",
        ).start()

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
        elif cmd == Command.METER_LEVEL:
            self._meter_data = MeterData.unpack(payload)

    def _handle_session_info_from_hw(self, info: SessionInfo):
        """Hardware changed mode or navigated — send appropriate sessions."""
        mode_changed = info.mode != self._session_info.mode

        # Device Health is rendered fully on the firmware from local counters.
        # Do not push audio sessions/volume here: there is no Windows audio
        # target for this mode, and treating it like an app mode can create
        # confusing "No sessions" traffic while the user is debugging.
        if info.mode == DisplayMode.MODE_HEALTH:
            info.current = 0
            self._session_info = info
            if mode_changed:
                self.serial.send_session_info(info)
                self.serial.send_mode_states(self._mode_states)
            return

        if mode_changed:
            # Use the cache immediately. A full Windows audio enumeration can
            # take around one second and made every mode change feel blocked.
            # The sync loop refreshes the selected volume in the background.
            items = self.audio.get_sessions_for_mode(info.mode)
            info.current = self._preferred_index(info.mode, items, info.current)
            # Keep the firmware's index aligned with the item selected here.
            # PC -> firmware SESSION_INFO does not echo back.
            self.serial.send_session_info(info)

        self._session_info = info
        self._push_sessions_for_mode(info.mode, info.current)

    def _apply_volume_to_windows(self, session_idx: int, vol: VolumeData):
        """Apply volume change from hardware knob to Windows."""
        mode = self._session_info.mode
        if mode == DisplayMode.MODE_HEALTH:
            return
        items = self.audio.get_sessions_for_mode(mode)

        # Determine which Windows session to modify
        if session_idx == SessionIndex.INDEX_CURRENT:
            win_idx = self._session_info.current
        elif session_idx == SessionIndex.INDEX_ALTERNATE:
            if mode != DisplayMode.MODE_GAME:
                return
            win_idx = self._find_audio_item_index(items, self._sessions[SessionIndex.INDEX_ALTERNATE])
        else:
            return

        if win_idx is not None and 0 <= win_idx < len(items):
            self.audio.set_volume(mode, win_idx, vol.volume, vol.is_muted)
            log.info(f"Applied vol={vol.volume}% muted={vol.is_muted} to {items[win_idx].name}")
            
            # If hardware marked this as default and it isn't yet, apply to Windows
            if vol.is_default and not items[win_idx].is_default:
                self.audio.set_default_device(mode, win_idx)
                # Re-push sessions so the UI/hardware updates with the new default flags
                self._handle_session_info_from_hw(self._session_info)

    def _find_audio_item_index(self, items, session: SessionData) -> Optional[int]:
        """Find the Windows audio item represented by a firmware session snapshot."""
        target_id = session.data.id
        target_name = session.name
        for i, item in enumerate(items):
            item_session = item.to_session_data()
            if item_session.data.id == target_id and item_session.name == target_name:
                return i
        for i, item in enumerate(items):
            if item.to_session_data().data.id == target_id:
                return i
        return None

    # ─── Push State to Hardware ────────────────────────────────────────
    @staticmethod
    def _preferred_index(mode: int, items, fallback: int = 0) -> int:
        """Choose the Windows default endpoint, or a safe existing index."""
        if not items:
            return 0

        if mode in (DisplayMode.MODE_OUTPUT, DisplayMode.MODE_INPUT):
            default_idx = next(
                (idx for idx, item in enumerate(items) if item.is_default),
                None,
            )
            if default_idx is not None:
                return default_idx

        return max(0, min(int(fallback), len(items) - 1))

    def _push_full_state(self, mode: int):
        """Send complete state for a display mode to hardware."""
        n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
        n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
        n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)
        if mode == DisplayMode.MODE_HEALTH:
            self._session_info = SessionInfo(
                mode=mode,
                current=0,
                sessions=[max(n_output, 1), max(n_input, 1), max(n_app, 1)],
            )
            self._mode_states = ModeStates(states=[0, 1, 1, 0, 0, 0])
            self.serial.send_session_info(self._session_info)
            self.serial.send_mode_states(self._mode_states)
            return

        items = self.audio.get_sessions_for_mode(mode)
        current_idx = self._preferred_index(mode, items)

        self._session_info = SessionInfo(
            mode=mode,
            current=current_idx,
            sessions=[max(n_output, 1), max(n_input, 1), max(n_app, 1)],
        )
        self._mode_states = ModeStates(states=[0, 1, 1, 0, 0, 0])

        # Send session info
        self.serial.send_session_info(self._session_info)

        # Send mode states
        self.serial.send_mode_states(self._mode_states)

        # Send sessions
        self._push_sessions_for_mode(mode, current_idx)

    def _push_updated_state(self):
        """Re-push state after a refresh, preserving current index if possible."""
        mode = self._session_info.mode
        if mode == DisplayMode.MODE_HEALTH:
            n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
            n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
            n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)
            self._session_info.current = 0
            self._session_info.sessions = [max(n_output, 1), max(n_input, 1), max(n_app, 1)]
            self.serial.send_session_info(self._session_info)
            self.serial.send_mode_states(self._mode_states)
            return

        items = self.audio.get_sessions_for_mode(mode)
        
        n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
        n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
        n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)
        
        current_idx = self._session_info.current
        selected_snapshot = self._sessions[SessionIndex.INDEX_CURRENT]
        matched_idx = self._find_audio_item_index(items, selected_snapshot) if selected_snapshot.name else None
        if matched_idx is not None:
            current_idx = matched_idx
        elif items and current_idx >= len(items):
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
        if mode == DisplayMode.MODE_HEALTH:
            return

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
        self._send_app_icon_if_needed(mode, items[current_idx])

        # Previous
        if count > 1:
            prev_idx = (current_idx - 1) % count
            prev = items[prev_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_PREVIOUS] = prev
            self.serial.send_session(Command.PREVIOUS_SESSION, prev)
            self._send_app_icon_if_needed(mode, items[prev_idx])

        # Next
        if count > 1:
            next_idx = (current_idx + 1) % count
            nxt = items[next_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_NEXT] = nxt
            self.serial.send_session(Command.NEXT_SESSION, nxt)
            self._send_app_icon_if_needed(mode, items[next_idx])

    def _send_app_icon_if_needed(self, mode: int, item):
        if mode not in (DisplayMode.MODE_APPLICATION, DisplayMode.MODE_GAME):
            return
        if item.id <= 0 or item.id in self._sent_icon_ids:
            return
        try:
            data = app_icon_rgb565(item.name, getattr(item, "_process_path", ""))
            if self.serial.send_app_icon(item.id, data):
                self._sent_icon_ids.add(item.id)
        except Exception:
            log.debug("Failed to send app icon for %s", item.name, exc_info=True)

    # ─── Periodic Sync ─────────────────────────────────────────────────
    def _sync_loop(self):
        """Periodically refresh audio sessions and sync volume to hardware."""
        interval = self.config.update_interval_ms / 1000.0
        last_heartbeat = time.monotonic()
        last_full_refresh = time.monotonic()
        last_time_sync = time.monotonic()

        while self._running:
            time.sleep(interval)

            if not self._device_connected or self._is_sleeping:
                continue

            now = time.monotonic()
            
            # Send heartbeat every 2 seconds to prevent hardware timeout
            if now - last_heartbeat >= 2.0:
                self.serial.send_command(Command.OK)
                last_heartbeat = now

            # Send time sync every 30 seconds
            if now - last_time_sync >= 30.0:
                dt = datetime.now()
                self.serial.send_time_sync(dt.hour, dt.minute, dt.second)
                last_time_sync = now

            if self._session_info.mode in (DisplayMode.MODE_SPLASH, DisplayMode.MODE_HEALTH):
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

    @staticmethod
    def _peak_to_level(peak: float) -> int:
        """Map WASAPI's linear peak to a readable -60 dB..0 dB meter."""
        if peak <= 0.001:
            return 0
        db = 20.0 * math.log10(min(1.0, peak))
        return max(0, min(100, round((db + 60.0) * (100.0 / 60.0))))

    def _meter_loop(self):
        """Send smoothed live peak levels without blocking volume sync."""
        current_meter = None
        alternate_meter = None
        selection_key = None
        shown_current = 0
        shown_alternate = 0
        last_sent = (-1, -1)
        next_retry = 0.0

        comtypes.CoInitialize()
        try:
            while self._running:
                time.sleep(1.0 / 15.0)

                if (not self._device_connected or self._is_sleeping or
                        self._session_info.mode in (DisplayMode.MODE_SPLASH, DisplayMode.MODE_HEALTH)):
                    self.audio.close_peak_meter(current_meter)
                    self.audio.close_peak_meter(alternate_meter)
                    current_meter = None
                    alternate_meter = None
                    if last_sent != (0, 0) and self.serial.is_connected:
                        self.serial.send_meter(MeterData())
                    last_sent = (0, 0)
                    shown_current = 0
                    shown_alternate = 0
                    selection_key = None
                    continue

                mode = self._session_info.mode
                current_idx = self._session_info.current
                items = self.audio.get_sessions_for_mode(mode)
                alternate_idx = None
                if mode == DisplayMode.MODE_GAME:
                    alternate_idx = self._find_audio_item_index(
                        items,
                        self._sessions[SessionIndex.INDEX_ALTERNATE],
                    )

                key = (mode, current_idx, alternate_idx)
                now = time.monotonic()
                if key != selection_key or (
                    current_meter is None and now >= next_retry
                ):
                    self.audio.close_peak_meter(current_meter)
                    self.audio.close_peak_meter(alternate_meter)
                    current_meter = None
                    alternate_meter = None
                    selection_key = key
                    next_retry = now + 1.0
                    try:
                        current_meter = self.audio.create_peak_meter(mode, current_idx)
                    except Exception:
                        current_meter = None
                    try:
                        alternate_meter = (
                            self.audio.create_peak_meter(mode, alternate_idx)
                            if alternate_idx is not None else None
                        )
                    except Exception:
                        alternate_meter = None

                try:
                    target_current = self._peak_to_level(
                        self.audio.read_peak_meter(current_meter)
                    )
                    target_alternate = self._peak_to_level(
                        self.audio.read_peak_meter(alternate_meter)
                    )
                except Exception:
                    self.audio.close_peak_meter(current_meter)
                    self.audio.close_peak_meter(alternate_meter)
                    current_meter = None
                    alternate_meter = None
                    next_retry = now + 1.0
                    target_current = 0
                    target_alternate = 0

                # Fast attack, slower decay gives a stable, readable meter.
                shown_current = max(target_current, shown_current - 7)
                shown_alternate = max(target_alternate, shown_alternate - 7)
                levels = (shown_current, shown_alternate)
                if levels != last_sent:
                    self.serial.send_meter(MeterData(*levels))
                    last_sent = levels
        finally:
            self.audio.close_peak_meter(current_meter)
            self.audio.close_peak_meter(alternate_meter)
            comtypes.CoUninitialize()
