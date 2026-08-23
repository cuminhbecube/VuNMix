"""Hardware-message handling and session-state push logic for VuNMix."""

from __future__ import annotations

import logging
from typing import Optional

from app_icon import app_icon_rgb565
from protocol import (
    Command,
    DisplayMode,
    MediaControlData,
    MeterData,
    ModeStates,
    SessionData,
    SessionIndex,
    SessionInfo,
    VolumeData,
    SESSION_COMMANDS,
    VOLUME_COMMANDS,
)


log = logging.getLogger(__name__)


class HardwareStateMixin:
    """Translate protocol messages into Windows audio state and vice versa."""

    def _on_hw_message(self, cmd: Command, payload: bytes):
        """Process a message received from hardware."""
        if cmd == Command.SESSION_INFO:
            info = SessionInfo.unpack(payload)
            log.debug("HW→PC SESSION_INFO: mode=%s, current=%s", info.mode, info.current)
            self._handle_session_info_from_hw(info)

        elif cmd in SESSION_COMMANDS:
            idx = int(cmd) - int(Command.CURRENT_SESSION)
            session = SessionData.unpack(payload)
            log.debug("HW→PC %s: name=%s", cmd.name, session.name)
            self._sessions[idx] = session

        elif cmd in VOLUME_COMMANDS:
            idx = int(cmd) - int(Command.VOLUME_CURR_CHANGE)
            vol = VolumeData.unpack(payload)
            log.debug(
                "HW→PC %s: vol=%s, muted=%s",
                cmd.name,
                vol.volume,
                vol.is_muted,
            )
            self._sessions[idx].data = vol
            self._apply_volume_to_windows(idx, vol)

        elif cmd == Command.MODE_STATES:
            self._mode_states = ModeStates.unpack(payload)
            log.debug("HW→PC MODE_STATES: %s", self._mode_states.states)
        elif cmd == Command.METER_LEVEL:
            self._meter_data = MeterData.unpack(payload)
        elif cmd == Command.MEDIA_CONTROL:
            ctrl = MediaControlData.unpack(payload)
            log.debug("HW→PC MEDIA_CONTROL: action=%s", ctrl.action)
            self.media_service.execute_control(ctrl.action)

    def _handle_session_info_from_hw(self, info: SessionInfo):
        """Hardware changed mode or navigated — send appropriate sessions."""
        mode_changed = info.mode != self._session_info.mode

        # Device Health is rendered fully on firmware from local counters. Do
        # not echo mode state from the serial callback during the transition.
        if info.mode == DisplayMode.MODE_HEALTH:
            info.current = 0
            self._session_info = info
            return

        if mode_changed:
            items = self.audio.get_sessions_for_mode(info.mode)
            info.current = self._preferred_index(info.mode, items, info.current)
            self.serial.send_session_info(info)

        self._session_info = info
        self._push_sessions_for_mode(info.mode, info.current)

    def _apply_volume_to_windows(self, session_idx: int, vol: VolumeData):
        """Apply a volume change from the hardware knob to Windows."""
        mode = self._session_info.mode
        if mode == DisplayMode.MODE_HEALTH:
            return
        items = self.audio.get_sessions_for_mode(mode)

        if session_idx == SessionIndex.INDEX_CURRENT:
            win_idx = self._session_info.current
        elif session_idx == SessionIndex.INDEX_ALTERNATE:
            if mode != DisplayMode.MODE_GAME:
                return
            win_idx = self._find_audio_item_index(
                items,
                self._sessions[SessionIndex.INDEX_ALTERNATE],
            )
        else:
            return

        if win_idx is not None and 0 <= win_idx < len(items):
            self.audio.set_volume(mode, win_idx, vol.volume, vol.is_muted)
            log.info(
                "Applied vol=%s%% muted=%s to %s",
                vol.volume,
                vol.is_muted,
                items[win_idx].name,
            )

            if vol.is_default and not items[win_idx].is_default:
                self.audio.set_default_device(mode, win_idx)
                self._handle_session_info_from_hw(self._session_info)

    def _find_audio_item_index(self, items, session: SessionData) -> Optional[int]:
        """Find the Windows audio item represented by a firmware snapshot."""
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
        self.serial.send_session_info(self._session_info)
        self.serial.send_mode_states(self._mode_states)
        self._push_sessions_for_mode(mode, current_idx)

    def _push_updated_state(self):
        """Re-push state after a refresh, preserving current item if possible."""
        mode = self._session_info.mode
        if mode == DisplayMode.MODE_HEALTH:
            n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
            n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
            n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)
            self._session_info.current = 0
            self._session_info.sessions = [
                max(n_output, 1),
                max(n_input, 1),
                max(n_app, 1),
            ]
            self.serial.send_session_info(self._session_info)
            self.serial.send_mode_states(self._mode_states)
            return

        items = self.audio.get_sessions_for_mode(mode)
        n_output = self.audio.get_session_count(DisplayMode.MODE_OUTPUT)
        n_input = self.audio.get_session_count(DisplayMode.MODE_INPUT)
        n_app = self.audio.get_session_count(DisplayMode.MODE_APPLICATION)

        current_idx = self._session_info.current
        selected_snapshot = self._sessions[SessionIndex.INDEX_CURRENT]
        matched_idx = (
            self._find_audio_item_index(items, selected_snapshot)
            if selected_snapshot.name
            else None
        )
        if matched_idx is not None:
            current_idx = matched_idx
        elif items and current_idx >= len(items):
            current_idx = len(items) - 1
        elif not items:
            current_idx = 0

        self._session_info.sessions = [
            max(n_output, 1),
            max(n_input, 1),
            max(n_app, 1),
        ]
        self._session_info.current = current_idx

        self.serial.send_session_info(self._session_info)
        self.serial.send_mode_states(self._mode_states)
        self._push_sessions_for_mode(mode, current_idx)

    def _push_sessions_for_mode(self, mode: int, current_idx: int):
        """Send current/previous/next sessions for a mode."""
        if mode == DisplayMode.MODE_HEALTH:
            return

        items = self.audio.get_sessions_for_mode(mode)
        if not items:
            self.serial.send_session(Command.CURRENT_SESSION, SessionData(name="No sessions"))
            return

        count = len(items)
        current_idx %= count

        cur = items[current_idx].to_session_data()
        self._sessions[SessionIndex.INDEX_CURRENT] = cur
        self.serial.send_session(Command.CURRENT_SESSION, cur)
        self._send_app_icon_if_needed(mode, items[current_idx])

        if count > 1:
            prev_idx = (current_idx - 1) % count
            prev = items[prev_idx].to_session_data()
            self._sessions[SessionIndex.INDEX_PREVIOUS] = prev
            self.serial.send_session(Command.PREVIOUS_SESSION, prev)
            self._send_app_icon_if_needed(mode, items[prev_idx])

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
