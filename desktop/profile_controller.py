"""Context-aware audio profile controller."""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterable, Optional

from audio_profile_service import AudioProfileService
from diagnostic_controller import DiagnosticAppController
from protocol import Command, MediaControlData, SessionInfo


log = logging.getLogger("vunmix.profile_controller")
PROFILE_MEDIA_ACTION_CYCLE = 10


class ProfileDebouncer:
    """Require a trigger to remain stable before allowing one profile switch."""

    def __init__(self, debounce_seconds: float = 1.5, min_switch_interval: float = 3.0):
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self.min_switch_interval = max(0.0, float(min_switch_interval))
        self._candidate: Optional[str] = None
        self._candidate_since = 0.0
        self._last_applied: Optional[str] = None
        self._last_switch_at = -1e12

    def observe(self, candidate: Optional[str], now: float) -> Optional[str]:
        if not candidate:
            self._candidate = None
            self._candidate_since = now
            return None
        if candidate != self._candidate:
            self._candidate = candidate
            self._candidate_since = now
            return None
        if candidate == self._last_applied:
            return None
        if now - self._candidate_since < self.debounce_seconds:
            return None
        if now - self._last_switch_at < self.min_switch_interval:
            return None
        return candidate

    def mark_applied(self, name: str, now: float) -> None:
        self._last_applied = name
        self._last_switch_at = now
        self._candidate = name
        self._candidate_since = now


class ProfileAppController(DiagnosticAppController):
    """Adds persistent profiles, explicit hardware selection and context auto-switch."""

    def __init__(self, config):
        super().__init__(config)
        self.profile_service = AudioProfileService(self.audio)
        # Keep existing tray/settings code compatible while migrating the old
        # preset concept to richer persistent profiles.
        self.preset_service = self.profile_service
        self._profile_stop = threading.Event()
        self._profile_thread: Optional[threading.Thread] = None
        self._profile_debouncer = ProfileDebouncer()

    def start(self):
        super().start()
        self._profile_stop.clear()
        if self._profile_thread is None or not self._profile_thread.is_alive():
            self._profile_thread = threading.Thread(
                target=self._profile_loop,
                daemon=True,
                name="AudioProfileSwitch",
            )
            self._profile_thread.start()

    def stop(self):
        self._profile_stop.set()
        if self._profile_thread and self._profile_thread.is_alive():
            self._profile_thread.join(timeout=2.0)
        self._profile_thread = None
        super().stop()

    @property
    def active_profile(self) -> str:
        return self.profile_service.active_profile

    @property
    def auto_profile_switching(self) -> bool:
        return self.profile_service.auto_switch_enabled

    @property
    def hardware_mode_profile_switching(self) -> bool:
        return self.profile_service.hardware_mode_switch_enabled

    def set_auto_profile_switching(self, enabled: bool) -> None:
        self.profile_service.set_auto_switch_enabled(enabled)
        # Clear pending trigger so reenabling always observes a fresh stable
        # context rather than immediately applying a stale candidate.
        self._profile_debouncer = ProfileDebouncer()
        log.info("Automatic audio profile switching: %s", "on" if enabled else "off")

    def toggle_auto_profile_switching(self) -> bool:
        enabled = not self.auto_profile_switching
        self.set_auto_profile_switching(enabled)
        return enabled

    def set_hardware_mode_profile_switching(self, enabled: bool) -> None:
        self.profile_service.set_hardware_mode_switch_enabled(enabled)
        log.info(
            "Hardware-tab audio profile switching: %s",
            "on" if enabled else "off",
        )

    def toggle_hardware_mode_profile_switching(self) -> bool:
        enabled = not self.hardware_mode_profile_switching
        self.set_hardware_mode_profile_switching(enabled)
        return enabled

    def apply_profile(self, name: str, *, source: str = "manual") -> bool:
        applied = self.profile_service.apply_profile(name, source=source)
        if applied:
            self._profile_debouncer.mark_applied(name, time.monotonic())
        return applied

    def cycle_profile(self, *, source: str = "hardware") -> Optional[str]:
        name = self.profile_service.cycle_profile(source=source)
        if name:
            self._profile_debouncer.mark_applied(name, time.monotonic())
        return name

    def _on_hw_message(self, cmd: Command, payload: bytes):
        # Long-press/explicit hardware profile cycle can be encoded as the
        # reserved media action without changing the binary frame format.
        if cmd == Command.MEDIA_CONTROL:
            ctrl = MediaControlData.unpack(payload)
            if ctrl.action == PROFILE_MEDIA_ACTION_CYCLE:
                name = self.cycle_profile(source="hardware")
                log.info("Hardware cycled audio profile to %s", name or "none")
                return

        if cmd == Command.SESSION_INFO:
            previous_mode = int(self._session_info.mode)
            info = SessionInfo.unpack(payload)
            super()._on_hw_message(cmd, payload)
            if int(info.mode) != previous_mode:
                # APP/GAME are navigation tabs. profile_for_hardware_mode()
                # returns None unless the separate safety gate was explicitly
                # enabled by the user.
                profile = self.profile_service.profile_for_hardware_mode(int(info.mode))
                if profile and profile != self.active_profile:
                    self.apply_profile(profile, source="hardware-mode")
            return

        super()._on_hw_message(cmd, payload)

    @staticmethod
    def _foreground_process_name() -> str:
        try:
            import psutil
            import win32gui
            import win32process

            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return ""
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return ""
            return psutil.Process(pid).name()
        except Exception:
            return ""

    @staticmethod
    def _running_process_names() -> Iterable[str]:
        try:
            import psutil

            result = []
            for proc in psutil.process_iter(["name"]):
                try:
                    name = proc.info.get("name")
                    if name:
                        result.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return result
        except Exception:
            return []

    def _profile_loop(self):
        while not self._profile_stop.wait(0.75):
            if not self.profile_service.auto_switch_enabled:
                continue
            try:
                candidate = self.profile_service.match_context(
                    focused_app=self._foreground_process_name(),
                    running_apps=self._running_process_names(),
                    obs_streaming=bool(self.obs_service.is_streaming),
                )
                now = time.monotonic()
                ready = self._profile_debouncer.observe(candidate, now)
                if ready and ready != self.active_profile:
                    if self.profile_service.apply_profile(ready, source="auto"):
                        self._profile_debouncer.mark_applied(ready, now)
            except Exception:
                # Auto switching is optional context automation; a transient
                # process/OBS failure must never take down the mixer.
                log.exception("Audio profile auto-switch iteration failed")
