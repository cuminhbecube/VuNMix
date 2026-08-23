"""VuNMix desktop application controller.

The controller now owns service lifetime and shared state only. Protocol/device
lifecycle, hardware state translation, and background workers live in focused
mixins so feature controllers can extend one responsibility at a time without
turning this file back into a monolith.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from audio_service import AudioService
from config import AppConfig
from controller_device import DeviceLifecycleMixin
from controller_power import PowerMonitor
from controller_state import HardwareStateMixin
from controller_workers import SyncWorkersMixin
from media_service import MediaService
from obs_service import ObsService
from preset_service import PresetService
from protocol import MeterData, ModeStates, SessionData, SessionIndex, SessionInfo
from serial_service import SerialService
from system_monitor import SystemMonitor
from weather_service import WeatherService


log = logging.getLogger(__name__)


class AppController(DeviceLifecycleMixin, HardwareStateMixin, SyncWorkersMixin):
    """Composition root bridging Windows audio services and VuNMix hardware."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.serial = SerialService(port=config.com_port)
        self.audio = AudioService()
        self.audio.set_favorite_apps(config.favorite_apps)
        self.system_monitor = SystemMonitor()
        self.media_service = MediaService()
        self.preset_service = PresetService(self.audio)
        self.weather_service = WeatherService()
        self.obs_service = ObsService()

        # Protocol state mirrors.
        self._session_info = SessionInfo()
        self._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        self._mode_states = ModeStates()
        self._meter_data = MeterData()
        self._device_connected = False
        self._update_only_connected = False
        self._is_sleeping = False
        self._handshake_token = 0
        self._sent_icon_ids = set()
        self._connection_lock = threading.RLock()

        # Worker/lifecycle state.
        self._sync_thread: Optional[threading.Thread] = None
        self._meter_thread: Optional[threading.Thread] = None
        self._firmware_update_lock = threading.Lock()
        self._firmware_updating = False
        self._running = False
        self._power_monitor: Optional[PowerMonitor] = None

        self.serial.on_connected = self._on_device_connected
        self.serial.on_disconnected = self._on_device_disconnected
        self.serial.on_message = self._on_hw_message
        self.serial.on_version = self._on_version

        self.on_connection_changed: Optional[callable] = None

    def start(self):
        """Start serial transport and the normal synchronization workers."""
        log.info("AppController starting...")
        if self._power_monitor is None:
            self._power_monitor = PowerMonitor(self._on_pc_sleep, self._on_pc_resume)
        self._running = True
        self.serial.start()

        self._sync_thread = threading.Thread(
            target=self._sync_loop,
            daemon=True,
            name="AudioSync",
        )
        self._sync_thread.start()
        self._meter_thread = threading.Thread(
            target=self._meter_loop,
            daemon=True,
            name="AudioMeter",
        )
        self._meter_thread.start()
        self.weather_service.start()
        self.obs_service.start()

    def stop(self):
        """Stop all services and workers."""
        log.info("AppController stopping...")
        self.weather_service.stop()
        self.obs_service.stop()
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
        with self._connection_lock:
            return self._device_connected

    @property
    def firmware_updating(self) -> bool:
        return self._firmware_updating

    @property
    def can_update_firmware(self) -> bool:
        """Whether a TEST-identified serial target is safe enough to flash."""
        with self._connection_lock:
            return (
                self._update_only_connected
                and self.serial.is_connected
                and not self._firmware_updating
            )

    def start_firmware_update(self, path, on_progress=None, on_complete=None) -> bool:
        """Stop protocol traffic, flash in a worker, then verify reconnect."""
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
                if self._running:
                    self.serial.start()
                    deadline = time.monotonic() + 15.0
                    while time.monotonic() < deadline:
                        if self.is_connected:
                            success = True
                            message = "Firmware updated and device reconnected."
                            break
                        time.sleep(0.1)
                    if not success:
                        message = (
                            "Firmware flashed, but the device did not reconnect "
                            "within 15 seconds."
                        )
                else:
                    success = True
                    message = (
                        "Firmware image flashed. Start VuNMix to verify reconnect."
                    )
            except Exception as exc:
                log.exception("Firmware update failed")
                message = str(exc)
            finally:
                self._firmware_updating = False
                self._firmware_update_lock.release()
                if self._running and not self.serial.is_connected:
                    self.serial.start()
                if on_complete:
                    on_complete(success, message)

        threading.Thread(
            target=worker,
            daemon=False,
            name="FirmwareUpdate",
        ).start()
        return True
