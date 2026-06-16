"""
VuNMix Serial Service — Fixed COM port communication with hardware.

No auto-scanning: connects directly to configured COM port.
Runs a background read thread to receive commands from the hardware.
"""

import logging
import struct
import threading
import time
from typing import Callable, Optional

import serial

from protocol import (
    Command, COMMAND_PAYLOAD_SIZE,
    SessionInfo, SessionData, VolumeData, DeviceSettings, ModeStates,
    SESSION_COMMANDS, VOLUME_COMMANDS,
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
        self._lock = threading.Lock()

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
        if self.is_connected:
            return True
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.05,       # 50ms read timeout
                write_timeout=0.5,
            )
            # Small delay for USB CDC to settle
            time.sleep(0.3)
            # Flush any stale data
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            log.info(f"Connected to {self.port}")
            if self.on_connected:
                self.on_connected()
            return True
        except (serial.SerialException, OSError) as e:
            log.warning(f"Failed to connect to {self.port}: {e}")
            self._serial = None
            return False

    def disconnect(self):
        """Close serial port."""
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
            log.info(f"Disconnected from {self.port}")
            if self.on_disconnected:
                self.on_disconnected()

    def start(self):
        """Start background read thread."""
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
        with self._lock:
            try:
                # Command is sent as a signed int8
                cmd_byte = struct.pack('b', int(cmd))
                self._serial.write(cmd_byte + payload)
                self._serial.flush()
                return True
            except (serial.SerialException, OSError) as e:
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

    def _read_loop(self):
        """Background thread: read commands from hardware."""
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
                # Read one command byte
                raw = self._serial.read(1)
                if not raw:
                    continue  # timeout, no data

                cmd_val = struct.unpack('b', raw)[0]
                try:
                    cmd = Command(cmd_val)
                except ValueError:
                    log.debug(f"Unknown command byte: {cmd_val}")
                    continue

                # Handle TEST response: command + version string line
                if cmd == Command.TEST:
                    version = self._serial.readline().decode('ascii', errors='replace').strip()
                    log.info(f"Device version: {version}")
                    if self.on_version:
                        self.on_version(version)
                    continue

                # Handle OK: no payload
                if cmd == Command.OK:
                    continue

                # Read payload based on command
                payload_size = COMMAND_PAYLOAD_SIZE.get(cmd, 0)
                if payload_size > 0:
                    payload = self._read_exact(payload_size)
                    if payload is None:
                        log.warning(f"Incomplete payload for {cmd.name}")
                        continue
                else:
                    payload = b''

                # Dispatch to callback
                if self.on_message:
                    self.on_message(cmd, payload)

            except Exception as e:
                log.error(f"Serial read error: {e}", exc_info=True)
                self.disconnect()
                time.sleep(0.5)

    def _read_exact(self, count: int) -> Optional[bytes]:
        """Read exactly `count` bytes with timeout."""
        data = b''
        remaining = count
        deadline = time.monotonic() + 1.0  # 1s max wait
        while remaining > 0 and time.monotonic() < deadline:
            chunk = self._serial.read(remaining)
            if chunk:
                data += chunk
                remaining -= len(chunk)
        return data if len(data) == count else None
