"""Periodic audio/state synchronization workers for VuNMix."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime

import comtypes

from protocol import Command, DisplayMode, MeterData, SessionIndex


log = logging.getLogger(__name__)


class SyncWorkersMixin:
    """Background workers that keep Windows audio and hardware state aligned."""

    def _sync_loop(self):
        """Periodically refresh audio sessions and sync volume to hardware."""
        interval = self.config.update_interval_ms / 1000.0
        last_heartbeat = time.monotonic()
        last_full_refresh = time.monotonic()
        last_time_sync = time.monotonic()
        last_telemetry_sync = time.monotonic()

        while self._running:
            time.sleep(interval)

            if not self._device_connected or self._is_sleeping:
                continue

            now = time.monotonic()

            if now - last_heartbeat >= 2.0:
                self.serial.send_command(Command.OK)
                last_heartbeat = now

            if now - last_time_sync >= 30.0:
                dt = datetime.now()
                self.serial.send_time_sync(dt.hour, dt.minute, dt.second)
                last_time_sync = now

            if now - last_telemetry_sync >= 1.0:
                try:
                    stats = self.system_monitor.get_pc_stats()
                    self.serial.send_pc_stats(stats)
                    media = self.media_service.get_current_media_info()
                    self.serial.send_media_info(media)
                except Exception as exc:
                    log.warning("Failed to push telemetry: %s", exc)
                last_telemetry_sync = now

            if self._session_info.mode in (
                DisplayMode.MODE_SPLASH,
                DisplayMode.MODE_HEALTH,
            ):
                continue

            if now - last_full_refresh >= 5.0:
                comtypes.CoInitialize()
                try:
                    def get_sig():
                        signature = []
                        for mode in (
                            DisplayMode.MODE_OUTPUT,
                            DisplayMode.MODE_INPUT,
                            DisplayMode.MODE_APPLICATION,
                        ):
                            signature.extend(
                                (item.id, item.name, item.is_default)
                                for item in self.audio.get_sessions_for_mode(mode)
                            )
                        return signature

                    old_sig = get_sig()
                    self.audio.refresh()
                    new_sig = get_sig()

                    if old_sig != new_sig:
                        log.info(
                            "Audio devices/apps changed in background. Pushing updated state."
                        )
                        self._push_updated_state()
                finally:
                    comtypes.CoUninitialize()
                last_full_refresh = now
                continue

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
            except Exception as exc:
                log.debug("Sync error: %s", exc)
            finally:
                comtypes.CoUninitialize()

    @staticmethod
    def _peak_to_level(peak: float) -> int:
        """Map WASAPI linear peak to a readable -60 dB..0 dB meter."""
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

                if (
                    not self._device_connected
                    or self._is_sleeping
                    or self._session_info.mode
                    in (DisplayMode.MODE_SPLASH, DisplayMode.MODE_HEALTH)
                ):
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
                            if alternate_idx is not None
                            else None
                        )
                    except Exception:
                        alternate_meter = None

                try:
                    if mode == DisplayMode.MODE_GAME:
                        target_current = self._peak_to_level(
                            self.audio.read_peak_meter(current_meter)
                        )
                        target_alternate = self._peak_to_level(
                            self.audio.read_peak_meter(alternate_meter)
                        )
                    else:
                        peak_l, peak_r = self.audio.read_stereo_peak_meter(current_meter)
                        target_current = self._peak_to_level(peak_l)
                        target_alternate = self._peak_to_level(peak_r)
                except Exception:
                    self.audio.close_peak_meter(current_meter)
                    self.audio.close_peak_meter(alternate_meter)
                    current_meter = None
                    alternate_meter = None
                    next_retry = now + 1.0
                    target_current = 0
                    target_alternate = 0

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
