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

    @staticmethod
    def _worker_wait(stop, seconds):
        if stop is not None:
            return stop.wait(seconds)
        time.sleep(seconds)
        return False

    def _sync_current_volume_once(self, stop=None) -> bool:
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

        vol = self.audio.read_current_volume(mode, read_idx, expected_item=items[read_idx])
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
                or (stop is not None and stop.is_set())
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

    def _heartbeat_loop(self, stop=None):
        """Keep transport liveness independent from WASAPI/audio work.

        Audio enumeration can occasionally stall inside Windows COM. Heartbeat
        must keep running anyway, otherwise firmware resets host state after
        five seconds and the desktop appears connected while the device has
        already fallen back to standby.
        """
        last_heartbeat = time.monotonic()
        pending_since = 0.0
        response_floor = 0.0

        while self._running and (stop is None or not stop.is_set()):
            if self._worker_wait(stop, 0.1):
                break

            if (
                not self._device_connected
                or self._is_sleeping
            ):
                pending_since = 0.0
                response_floor = 0.0
                last_heartbeat = time.monotonic()
                continue

            now = time.monotonic()
            last_ack = getattr(self.serial, "last_ok_response", 0.0)

            if pending_since:
                if last_ack > response_floor:
                    pending_since = 0.0
                    response_floor = 0.0
                elif now - pending_since >= 6.0:
                    log.warning(
                        "VuNMix protocol heartbeat timed out after %.1fs; reconnecting",
                        now - pending_since,
                    )
                    pending_since = 0.0
                    response_floor = 0.0
                    self.serial.disconnect()
                    continue

            if not pending_since and now - last_heartbeat >= 2.0:
                response_floor = last_ack
                if not self.serial.send_command(Command.OK):
                    log.warning("VuNMix heartbeat write failed; reconnecting")
                    response_floor = 0.0
                    self.serial.disconnect()
                    last_heartbeat = now
                    continue
                pending_since = now
                last_heartbeat = now

    def _sync_loop(self, stop=None):
        """Periodically refresh audio sessions and sync volume to hardware.

        Transport heartbeat deliberately lives in _heartbeat_loop so a slow or
        wedged Windows audio call cannot make a healthy USB link flap.
        """
        interval = self.config.update_interval_ms / 1000.0
        last_full_refresh = time.monotonic()
        last_time_sync = time.monotonic()
        last_telemetry_sync = time.monotonic()

        while self._running and (stop is None or not stop.is_set()):
            if self._worker_wait(stop, interval):
                break

            if (
                not self._device_connected
                or self._is_sleeping
                or getattr(self, "_resume_recovering", False)
            ):
                continue

            now = time.monotonic()

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
                try:
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

                        if (stop is None or not stop.is_set()) and old_sig != new_sig:
                            log.info(
                                "Audio devices/apps changed in background. Pushing updated state."
                            )
                            self._push_updated_state()
                    finally:
                        comtypes.CoUninitialize()
                except Exception as exc:
                    log.warning("Full audio refresh failed; keeping sync alive: %s", exc)
                last_full_refresh = now
                continue

            comtypes.CoInitialize()
            try:
                if self.audio.check_system_changes():
                    log.info("System audio changes detected. Refreshing...")
                    self.audio.refresh()
                    if stop is None or not stop.is_set():
                        self._push_updated_state()
                    continue

                if stop is None or not stop.is_set():
                    self._sync_current_volume_once(stop)
            except Exception as exc:
                log.debug("Sync error: %s", exc)
            finally:
                comtypes.CoUninitialize()

    @staticmethod
    def _peak_to_level(peak: float) -> int:
        """Map WASAPI peak to a calmer VU scale with useful headroom.

        The previous linear dB mapping put ordinary program audio around
        80-95%, so both the TFT meter and RGB bar lived near the end stop.
        Keep the same -60 dB..0 dB input window, then apply a square curve:
        typical peaks stay in the middle while true 0 dB peaks can still
        reach 100%.
        """
        if peak <= 0.001:
            return 0
        db = 20.0 * math.log10(min(1.0, peak))
        normalized = max(0.0, min(1.0, (db + 60.0) / 60.0))
        return max(0, min(100, round((normalized ** 2.0) * 100.0)))

    @staticmethod
    def _smooth_meter_level(shown: int, target: int) -> int:
        """Limit meter attack/release so short peaks do not flash full-scale."""
        shown = max(0, min(100, int(shown)))
        target = max(0, min(100, int(target)))
        if target > shown:
            return min(target, shown + 18)
        return max(target, shown - 5)

    def _meter_loop(self, stop=None):
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
            while self._running and (stop is None or not stop.is_set()):
                if self._worker_wait(stop, 1.0 / 15.0):
                    break

                if (
                    not self._device_connected
                    or self._is_sleeping
                    or getattr(self, "_resume_recovering", False)
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

                current_item = items[current_idx] if 0 <= current_idx < len(items) else None
                alternate_item = items[alternate_idx] if alternate_idx is not None else None
                def identity(item):
                    return (getattr(item, "_device_id", ""), getattr(item, "_session_identifier", ""),
                            getattr(item, "id", None), getattr(item, "name", None))
                key = (mode, current_idx, alternate_idx, identity(current_item), identity(alternate_item))
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
                        current_meter = self.audio.create_peak_meter(mode, current_idx, expected_item=current_item) if current_item is not None else None
                    except Exception:
                        current_meter = None
                    try:
                        alternate_meter = (
                            self.audio.create_peak_meter(mode, alternate_idx, expected_item=alternate_item)
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

                shown_current = self._smooth_meter_level(
                    shown_current,
                    target_current,
                )
                shown_alternate = self._smooth_meter_level(
                    shown_alternate,
                    target_alternate,
                )
                levels = (shown_current, shown_alternate)
                if (stop is None or not stop.is_set()) and levels != last_sent:
                    self.serial.send_meter(MeterData(*levels))
                    last_sent = levels
        finally:
            self.audio.close_peak_meter(current_meter)
            self.audio.close_peak_meter(alternate_meter)
            comtypes.CoUninitialize()
