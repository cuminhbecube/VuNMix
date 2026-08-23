"""Audio routing + ducking controller extension for VuNMix."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, Optional

from audio_automation_service import AudioAutomationService, _matches
from audio_policy import AudioPolicyRouter, AudioRoutingUnavailable, routing_capability
from media_controller import MediaAppController
from protocol import DisplayMode


log = logging.getLogger("vunmix.audio_automation_controller")
ROUTING_REFRESH_SECONDS = 3.0
DUCKING_TICK_SECONDS = 0.10


class AudioAutomationController(MediaAppController):
    """Run app routing and level-triggered ducking beside normal mixer sync."""

    def __init__(self, config):
        super().__init__(config)
        self.audio_automation = AudioAutomationService(self.audio)
        self._audio_policy_router = None
        try:
            self._audio_policy_router = AudioPolicyRouter()
        except AudioRoutingUnavailable as exc:
            log.info("Per-app audio routing unavailable: %s", exc)
        except Exception:
            log.exception("Could not initialize per-app audio routing backend")

        self._automation_stop = threading.Event()
        self._automation_thread: Optional[threading.Thread] = None
        self._duck_meters: Dict[str, object] = {}
        self._duck_meter_names: Dict[str, str] = {}
        self._duck_meter_signature = ()

    def start(self):
        super().start()
        self._automation_stop.clear()
        if self._automation_thread is None or not self._automation_thread.is_alive():
            self._automation_thread = threading.Thread(
                target=self._automation_loop,
                daemon=True,
                name="AudioRoutingDucking",
            )
            self._automation_thread.start()

    def stop(self):
        self._automation_stop.set()
        if self._automation_thread and self._automation_thread.is_alive():
            self._automation_thread.join(timeout=2.0)
        self._automation_thread = None

        self._close_duck_meters()
        try:
            self.audio_automation.restore_all_ducked(time.monotonic())
        except Exception:
            log.exception("Failed to restore ducked volumes during shutdown")
        if self._audio_policy_router is not None:
            try:
                self.audio_automation.clear_applied_routes(self._audio_policy_router)
            except Exception:
                log.exception("Failed to clear app routes during shutdown")
        super().stop()

    @property
    def routing_enabled(self) -> bool:
        return self.audio_automation.routing_enabled

    @property
    def ducking_enabled(self) -> bool:
        return self.audio_automation.ducking_enabled

    @property
    def routing_supported(self) -> bool:
        return self._audio_policy_router is not None

    def routing_status(self) -> str:
        capability = routing_capability()
        if not capability.supported:
            return f"Routing unavailable: {capability.reason}"
        if self._audio_policy_router is None:
            return "Routing backend unavailable"
        if self.audio_automation.last_routing_error:
            return f"Routing error: {self.audio_automation.last_routing_error}"
        return (
            f"Routing {'on' if self.routing_enabled else 'off'} · "
            f"{len(self.audio_automation.routing_rules)} rule(s)"
        )

    def ducking_status(self) -> str:
        return (
            f"Ducking {'on' if self.ducking_enabled else 'off'} · "
            f"{len(self.audio_automation.ducking_rules)} rule(s) · "
            f"recovery {len(self.audio_automation._recovery)}"
        )

    def set_routing_enabled(self, enabled: bool) -> None:
        self.audio_automation.set_routing_enabled(enabled)
        if not enabled and self._audio_policy_router is not None:
            self.audio_automation.clear_applied_routes(self._audio_policy_router)

    def toggle_routing(self) -> bool:
        enabled = not self.routing_enabled
        self.set_routing_enabled(enabled)
        return enabled

    def set_ducking_enabled(self, enabled: bool) -> None:
        self.audio_automation.set_ducking_enabled(enabled)
        if not enabled:
            self.audio_automation.restore_all_ducked(time.monotonic())

    def toggle_ducking(self) -> bool:
        enabled = not self.ducking_enabled
        self.set_ducking_enabled(enabled)
        return enabled

    def open_audio_automation_config(self) -> None:
        path = os.path.abspath(self.audio_automation.path)
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:  # pragma: no cover - desktop target is Windows
            raise OSError("Opening the audio automation config is only supported on Windows")

    def _close_duck_meters(self):
        for meter in list(self._duck_meters.values()):
            try:
                self.audio.close_peak_meter(meter)
            except Exception:
                pass
        self._duck_meters.clear()
        self._duck_meter_names.clear()
        self._duck_meter_signature = ()

    def _refresh_duck_meters(self):
        patterns = self.audio_automation.trigger_patterns()
        apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        selected = []
        for index, item in enumerate(apps):
            name = str(getattr(item, "name", "") or "")
            if any(_matches(name, pattern) for pattern in patterns):
                selected.append((index, item))

        signature = tuple(
            (
                int(getattr(item, "id", 0) or 0),
                str(getattr(item, "_session_identifier", "") or ""),
                str(getattr(item, "name", "") or ""),
            )
            for _index, item in selected
        )
        if signature == self._duck_meter_signature:
            return

        self._close_duck_meters()
        self._duck_meter_signature = signature
        for index, item in selected:
            key = self.audio_automation._session_key(item)
            try:
                meter = self.audio.create_peak_meter(DisplayMode.MODE_APPLICATION, index)
            except Exception:
                meter = None
            if meter is not None:
                self._duck_meters[key] = meter
                self._duck_meter_names[key] = str(getattr(item, "name", "") or key)

    def _read_trigger_levels(self) -> Dict[str, float]:
        levels: Dict[str, float] = {}
        for key, meter in list(self._duck_meters.items()):
            try:
                level = self.audio.read_peak_meter(meter)
            except Exception:
                level = 0.0
            levels[self._duck_meter_names.get(key, key)] = max(0.0, min(1.0, float(level)))
        return levels

    def _automation_loop(self):
        next_routing = 0.0
        next_recovery = 0.0
        while not self._automation_stop.wait(DUCKING_TICK_SECONDS):
            now = time.monotonic()
            try:
                if now >= next_recovery and self.audio_automation.has_pending_recovery():
                    self.audio_automation.recover_pending()
                    next_recovery = now + 1.0

                if self.ducking_enabled and self.audio_automation.trigger_patterns():
                    self._refresh_duck_meters()
                    trigger_levels = self._read_trigger_levels()
                else:
                    if self._duck_meters:
                        self._close_duck_meters()
                    trigger_levels = {}
                self.audio_automation.tick_ducking(trigger_levels, now)

                if now >= next_routing:
                    next_routing = now + ROUTING_REFRESH_SECONDS
                    if self._audio_policy_router is not None:
                        self.audio_automation.apply_routing_rules(self._audio_policy_router)
            except Exception:
                # Audio automation is an optional layer. A broken rule or a
                # transient endpoint/session must never take down mixer sync.
                log.exception("Audio routing/ducking iteration failed")
                self._close_duck_meters()
