"""
VuNMix Serial Service — Fixed COM port communication with hardware.

No auto-scanning: connects directly to configured COM port.
Runs a background read thread to receive commands from the hardware.
"""

import logging
import threading
import time
from typing import Callable, Optional

import serial

from protocol import (
    Command, COMMAND_PAYLOAD_SIZE,
    SessionInfo, SessionData, VolumeData, MeterData, DeviceSettings, ModeStates,
    AppIconMeta, AppIconChunk, PcStatsData, MediaInfoData, MediaControlData,
    SESSION_COMMANDS, VOLUME_COMMANDS,
    FrameParser, encode_frame,
)

log = logging.getLogger(__name__)


class SerialService:
    """Manages serial communication with VuNMix hardware on a fixed COM port."""

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
        self._read_thread: Optional[threading.Thread] = None
        self._running = False
        self._write_lock = threading.Lock()
        self._icon_lock = threading.Lock()
        self._connect_lock = threading.Lock()
        self._parser = FrameParser()

        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_message: Optional[Callable[[Command, bytes], None]] = None
        self.on_version: Optional[Callable[[str], None]] = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> bool:
        """Connect to the fixed COM port. Returns True on success."""
        with self._connect_lock:
            if self.is_connected:
                return True
            try:
                connection = serial.Serial()
                connection.port = self.port
                connection.baudrate = self.baudrate
                connection.timeout = 0.05
                connection.write_timeout = 0.5
                connection.dtr = False
                connection.rts = False
                connection.open()
                time.sleep(0.3)
                connection.reset_input_buffer()
                connection.reset_output_buffer()
                self._parser.reset()
                self._serial = connection
                log.info("Connected to %s", self.port)
            except (serial.SerialException, OSError) as e:
                log.warning("Failed to connect to %s: %s", self.port, e)
                self._serial = None
                return False

        # Handshake/audio enumeration must not block the serial reader.
        if self.on_connected:
            def notify_connected():
                if self._serial is connection and connection.is_open:
                    self.on_connected()

            threading.Thread(
                target=notify_connected,
                daemon=True,
                name="DeviceConnected",
            ).start()
        return True

    def disconnect(self):
        """Close serial port."""
        with self._connect_lock:
            connection = self._serial
            self._serial = None
        if connection:
            try:
                connection.close()
            except (serial.SerialException, OSError) as exc:
                log.debug("Error while closing serial port: %s", exc)
            self._parser.reset()
            log.info("Disconnected from %s", self.port)
            if self.on_disconnected:
                self.on_disconnected()

    def start(self):
        """Start background read thread."""
        if self._read_thread and self._read_thread.is_alive():
            return
        self._running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True, name="SerialRead")
        self._read_thread.start()

    def stop(self):
        """Stop background read thread and disconnect."""
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=2.0)
            self._read_thread = None
        self.disconnect()

    def send_command(self, cmd: Command, payload: bytes = b'') -> bool:
        """Send a command byte + optional payload to hardware."""
        if not self.is_connected:
            return False
        with self._write_lock:
            try:
                connection = self._serial
                if connection is None or not connection.is_open:
                    return False
                connection.write(encode_frame(cmd, payload))
                connection.flush()
                return True
            except (serial.SerialException, OSError, ValueError) as e:
                log.error(f"Write error: {e}")
                self.disconnect()
                return False

    def send_test(self) -> bool:
        """Send TEST command to verify hardware presence."""
        return self.send_command(Command.TEST)

    def send_settings(self, settings: DeviceSettings) -> bool:
        return self.send_command(Command.SETTINGS, settings.pack())

    def send_session_info(self, info: SessionInfo) -> bool:
        return self.send_command(Command.SESSION_INFO, info.pack())

    def send_session(self, cmd: Command, session: SessionData) -> bool:
        assert cmd in SESSION_COMMANDS
        return self.send_command(cmd, session.pack())

    def send_volume(self, cmd: Command, vol: VolumeData) -> bool:
        assert cmd in VOLUME_COMMANDS
        return self.send_command(cmd, vol.pack())

    def send_mode_states(self, states: ModeStates) -> bool:
        return self.send_command(Command.MODE_STATES, states.pack())

    def send_time_sync(self, hour: int, minute: int, second: int) -> bool:
        """Send current time to hardware (3 bytes: hour, minute, second)."""
        payload = bytes((hour, minute, second))
        return self.send_command(Command.TIME_SYNC, payload)

    def send_meter(self, meter: MeterData) -> bool:
        return self.send_command(Command.METER_LEVEL, meter.pack())

    def send_app_icon(self, app_id: int, data: bytes, width: int = 16, height: int = 16) -> bool:
        if not data:
            return False
        # Metadata and chunks are one transaction. Without this lock a second
        # sender can replace the active icon between chunks on the firmware.
        with self._icon_lock:
            if not self.send_command(Command.APP_ICON_META, AppIconMeta(app_id, width, height, len(data)).pack()):
                return False
            for index, offset in enumerate(range(0, len(data), 60)):
                if not self.send_command(
                    Command.APP_ICON_CHUNK,
                    AppIconChunk(app_id, index, data[offset:offset + 60]).pack(),
                ):
                    return False
                time.sleep(0.006)
        return True

    def send_pc_stats(self, stats: PcStatsData) -> bool:
        return self.send_command(Command.PC_STATS, stats.pack())

    def send_media_info(self, info: MediaInfoData) -> bool:
        return self.send_command(Command.MEDIA_INFO, info.pack())

    def _read_loop(self):
        """Background thread: parse framed messages from hardware."""
        reconnect_delay = 1.0

        while self._running:
            # Auto-reconnect
            if not self.is_connected:
                if self.connect():
                    reconnect_delay = 1.0
                else:
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 1.5, 10.0)
                    continue

            try:
                connection = self._serial
                if connection is None:
                    continue
                waiting = connection.in_waiting
                raw = connection.read(max(1, min(waiting, 256)))
                if not raw:
                    continue

                for cmd, payload in self._parser.feed(raw):
                    if cmd == Command.TEST:
                        version = payload.decode('ascii', errors='replace').strip()
                        log.info("Device version: %s", version)
                        if self.on_version:
                            self.on_version(version)
                        continue

                    if cmd == Command.OK:
                        continue

                    expected_size = COMMAND_PAYLOAD_SIZE.get(cmd)
                    if expected_size is None or len(payload) != expected_size:
                        log.warning(
                            "Invalid payload size for %s: got %d, expected %s",
                            cmd.name, len(payload), expected_size,
                        )
                        continue

                    if self.on_message:
                        self.on_message(cmd, payload)

            except (serial.SerialException, OSError) as e:
                log.error(f"Serial read error: {e}", exc_info=True)
                self.disconnect()
                time.sleep(0.5)
            except Exception as e:
                log.exception("Unexpected serial parser/callback error: %s", e)
