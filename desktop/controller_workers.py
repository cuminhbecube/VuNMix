"""Periodic audio/state synchronization workers for VuNMix."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime

import comtypes

from protocol import (
    Command,
    DisplayMode,
    MeterData,
    SessionData,
    SessionIndex,
    VolumeData,
)


log = logging.getLogger(__name__)


class SyncWorkersMixin:
    """Background workers that keep Windows audio and hardware state aligned."""

    def _sync_current_volume_once(self) -> bool:
        """Push one Windows volume change only for a stable selected identity.

        SESSION_INFO and CURRENT_SESSION are delivered as separate protocol
        frames and are updated by SerialRead while this worker runs in parallel.
        Capture an epoch+identity, resolve by identity (not numeric index), then
        revalidate after the Windows read before changing cache or USB state.
        """
        with self._state_lock:
            if self._selection_transitioning:
                return False
            mode = self._session_info.mode
            if mode in (DisplayMode.MODE_SPLASH, DisplayMode.MODE_HEALTH):
                return False
            epoch = self._selection_epoch
            selected = self._sessions[SessionIndex.INDEX_CURRENT]
            expected_id = int(selected.data.id)
            expected_name = selected.name

        if expected_id <= 0 or not expected_name:
            return False

        items = self.audio.get_sessions_for_mode(mode)
        expected = SessionData(
            name=expected_name,
            data=VolumeData(id=expected_id),
        )
        read_idx = self._find_audio_item_index(items, expected)
        if read_idx is None:
            return False

        vol = self.audio.read_current_volume(mode, read_idx)
        if vol is None or int(vol.id) != expected_id:
            log.debug(
                "Skipped periodic volume sync after identity mismatch: mode=%s expected=%s got=%s",
                mode,
                expected_id,
                getattr(vol, "id", None),
            )
            return False

        with self._state_lock:
            current = self._sessions[SessionIndex.INDEX_CURRENT]
            if (
                self._selection_transitioning
                or self._selection_epoch != epoch
                or self._session_info.mode != mode
                or int(current.data.id) != expected_id
                or current.name != expected_name
            ):
                log.debug("Skipped periodic volume sync across selection transition")
                return False

            if vol.volume == current.data.volume and vol.is_muted == current.data.is_muted:
                return False

            self._sessions[SessionIndex.INDEX_CURRENT].data = vol
            # Keep the state lock through send_volume so SerialRead cannot
            # commit a new selection locally between revalidation and transmit.
            self.serial.send_volume(Command.VOLUME_CURR_CHANGE, vol)
            return True

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

            with self._state_lock:
                current_mode = self._session_info.mode
            if current_mode in (
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

                self._sync_current_volume_once()
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
