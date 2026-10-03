"""
VuNMix Serial Service — USB-identity based communication with hardware.

Windows COM numbers can change whenever the ESP32-S3 resets or re-enumerates.
The service therefore resolves the current port from a remembered USB identity
and only treats the configured COM number as a preference/manual fallback.
"""

import logging
import queue
import threading
import time
from types import SimpleNamespace
from typing import Callable, Optional

import serial

from device_discovery import (
    DeviceIdentity,
    clear_device_identity,
    list_serial_ports,
    load_device_identity,
    save_device_identity,
    select_device_port,
)
from protocol import (
    Command, COMMAND_PAYLOAD_SIZE,
    SessionInfo, SessionData, VolumeData, MeterData, DeviceSettings, ModeStates,
    AppIconMeta, AppIconChunk, PcStatsData, MediaInfoData, MediaControlData,
    SESSION_COMMANDS, VOLUME_COMMANDS,
    FrameParser, encode_frame,
)

log = logging.getLogger(__name__)


class SerialService:
    """Manage VuNMix serial communication and survive COM renumbering."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        *,
        device_identity: Optional[DeviceIdentity] = None,
        port_provider: Optional[Callable[[], list]] = None,
    ):
        self._preferred_port = str(port or "").strip()
        self._active_port: Optional[str] = None
        self.baudrate = baudrate
        self._device_identity = (
            device_identity if device_identity is not None else load_device_identity()
        )
        self._port_provider = port_provider or list_serial_ports
        self._current_port_info = None
        self._status = "Disconnected"

        self._serial: Optional[serial.Serial] = None
        self._read_thread: Optional[threading.Thread] = None
        self._read_stop_event: Optional[threading.Event] = None
        self._callback_thread: Optional[threading.Thread] = None
        self._callback_stop_event: Optional[threading.Event] = None
        self._callback_queue = queue.Queue(maxsize=256)
        self._connection_generation = 0
        self._running = False
        self._write_lock = threading.Lock()
        self._icon_lock = threading.Lock()
        self._connect_lock = threading.Lock()
        self._parser = FrameParser()
        self._last_protocol_rx = 0.0
        self._last_test_response = 0.0
        self._last_ok_response = 0.0

        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_message: Optional[Callable[[Command, bytes], None]] = None
        self.on_version: Optional[Callable[[str], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None

    @property
    def port(self) -> str:
        """Current COM port, or the preferred port while disconnected."""
        return self._active_port or self._preferred_port

    @port.setter
    def port(self, value: str):
        # GUI/manual port selection means the user intentionally selected a
        # different target. Forget the previous USB identity so it cannot pull
        # the connection back to an old board on the next reconnect.
        self.set_preferred_port(value, forget_identity=True)

    @property
    def preferred_port(self) -> str:
        return self._preferred_port

    @property
    def device_identity(self) -> Optional[DeviceIdentity]:
        return self._device_identity

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def last_protocol_rx(self) -> float:
        """Monotonic timestamp of the last valid VuNMix protocol frame."""
        return self._last_protocol_rx

    @property
    def last_test_response(self) -> float:
        """Monotonic timestamp of the last TEST response from firmware."""
        return self._last_test_response

    @property
    def last_ok_response(self) -> float:
        """Monotonic timestamp of the last firmware ACK."""
        return self._last_ok_response

    def protocol_alive(self, max_age: float = 6.0) -> bool:
        """True only when the device has replied recently at protocol level."""
        if not self.is_connected or self._last_protocol_rx <= 0:
            return False
        return (time.monotonic() - self._last_protocol_rx) <= max(0.1, float(max_age))

    def _set_status(self, text: str):
        if text == self._status:
            return
        self._status = text
        log.debug("Serial status: %s", text)
        if self.on_status:
            try:
                self.on_status(text)
            except Exception:
                log.exception("Serial status callback failed")

    def set_preferred_port(self, port: str, *, forget_identity: bool = False):
        port = str(port or "").strip()
        changed = port.lower() != self._preferred_port.lower()
        self._preferred_port = port
        if changed and forget_identity:
            self._device_identity = None
            clear_device_identity()
            log.info("Manual COM selection changed; cleared remembered USB identity")

    def _enumerate_ports(self) -> list:
        try:
            return list(self._port_provider())
        except Exception as exc:
            log.warning("Serial port enumeration failed: %s", exc)
            return []

    def _resolve_target(self):
        ports = self._enumerate_ports()
        selected = select_device_port(
            ports,
            identity=self._device_identity,
            preferred_port=self._preferred_port,
        )
        if selected is not None:
            return selected

        if not ports and self._preferred_port:
            # Preserve an explicit/manual port when enumeration itself is not
            # available. Opening it will produce the authoritative OS error.
            return SimpleNamespace(
                device=self._preferred_port,
                vid=None,
                pid=None,
                serial_number=None,
                product=None,
                manufacturer=None,
                location=None,
            )
        return None

    def confirm_current_device(self) -> Optional[DeviceIdentity]:
        """Persist USB identity after a valid VuNMix TEST response."""
        info = self._current_port_info
        if info is None and self._active_port:
            for candidate in self._enumerate_ports():
                if str(getattr(candidate, "device", "")).lower() == self._active_port.lower():
                    info = candidate
                    self._current_port_info = candidate
                    break
        if info is None:
            return self._device_identity

        identity = DeviceIdentity.from_port(info)
        if identity.is_useful:
            self._device_identity = identity
            try:
                save_device_identity(identity)
            except OSError as exc:
                log.warning("Could not persist VuNMix USB identity: %s", exc)
            log.info(
                "Remembered VuNMix USB identity: vid=%s pid=%s serial=%s location=%s",
                f"0x{identity.vid:04X}" if identity.vid is not None else "?",
                f"0x{identity.pid:04X}" if identity.pid is not None else "?",
                identity.serial_number or "?",
                identity.location or "?",
            )
        return self._device_identity

    def connect(self) -> bool:
        """Resolve and open the current COM port. Returns True on success."""
        with self._connect_lock:
            if self.is_connected:
                return True

            target = self._resolve_target()
            if target is None:
                self._set_status("Searching for VuNMix")
                return False

            target_port = str(target.device)
            self._set_status(f"Connecting {target_port}")
            try:
                connection = serial.Serial()
                connection.port = target_port
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
                self._last_protocol_rx = 0.0
                self._last_test_response = 0.0
                self._last_ok_response = 0.0
                self._connection_generation += 1
                self._serial = connection
                self._active_port = target_port
                self._preferred_port = target_port
                self._current_port_info = target
                self._set_status(f"Verifying VuNMix on {target_port}")
                log.info("Connected serial port %s", target_port)
            except (serial.SerialException, OSError) as e:
                log.warning("Failed to connect to %s: %s", target_port, e)
                self._serial = None
                self._active_port = None
                self._current_port_info = None
                self._set_status(f"Waiting for VuNMix ({target_port} unavailable)")
                return False

        # Handshake/audio enumeration must not block the serial reader.
        if self.on_connected:
            def notify_connected():
                if self._serial is connection and connection.is_open:
                    try:
                        self.on_connected()
                    except Exception:
                        # A lifecycle observer must not kill the one-shot
                        # notifier or leave an unreported thread exception.
                        log.exception("Serial connected callback failed")

            threading.Thread(
                target=notify_connected,
                daemon=True,
                name="DeviceConnected",
            ).start()
        return True

    def disconnect(self):
        """Close serial port without forgetting the USB device identity."""
        with self._connect_lock:
            connection = self._serial
            active_port = self._active_port
            self._serial = None
            self._active_port = None
            self._current_port_info = None
            if connection is not None:
                self._connection_generation += 1
        if connection:
            try:
                connection.close()
            except (serial.SerialException, OSError) as exc:
                log.debug("Error while closing serial port: %s", exc)
            self._parser.reset()
            self._last_protocol_rx = 0.0
            self._last_test_response = 0.0
            self._last_ok_response = 0.0
            log.info("Disconnected from %s", active_port or self._preferred_port)
            self._set_status("Disconnected")
            if self.on_disconnected:
                try:
                    self.on_disconnected()
                except Exception:
                    # Transport teardown must remain authoritative even when a
                    # higher-level observer fails. Letting this escape can kill
                    # SerialRead and permanently stop automatic reconnect.
                    log.exception("Serial disconnected callback failed")

    def _start_callback_dispatcher(self):
        current = self._callback_thread
        current_stop = self._callback_stop_event
        if (
            current is not None
            and current.is_alive()
            and current_stop is not None
            and not current_stop.is_set()
        ):
            return

        stop_event = threading.Event()
        self._callback_stop_event = stop_event
        worker = threading.Thread(
            target=self._callback_loop,
            args=(stop_event,),
            daemon=True,
            name="SerialCallbacks",
        )
        self._callback_thread = worker
        worker.start()

    def start(self):
        """Start background read/reconnect and ordered callback workers.

        Every start owns a private stop event. This prevents an old SerialRead
        thread that was slow to exit from being resurrected when a later
        reconnect sets the service running again.
        """
        current = self._read_thread
        current_stop = self._read_stop_event
        if (
            current is not None
            and current.is_alive()
            and current_stop is not None
            and not current_stop.is_set()
        ):
            return

        self._running = True
        self._start_callback_dispatcher()
        stop_event = threading.Event()
        self._read_stop_event = stop_event
        worker = threading.Thread(
            target=self._read_loop,
            args=(stop_event,),
            daemon=True,
            name="SerialRead",
        )
        self._read_thread = worker
        worker.start()

    def stop(self):
        """Stop transport workers without allowing stale threads to revive."""
        self._running = False

        read_thread = self._read_thread
        read_stop = self._read_stop_event
        self._read_thread = None
        self._read_stop_event = None
        if read_stop is not None:
            read_stop.set()

        callback_thread = self._callback_thread
        callback_stop = self._callback_stop_event
        self._callback_thread = None
        self._callback_stop_event = None
        if callback_stop is not None:
            callback_stop.set()

        # Close first so a pending Windows read is released before joins.
        self.disconnect()

        current = threading.current_thread()
        if read_thread and read_thread is not current:
            read_thread.join(timeout=1.0)
        if callback_thread and callback_thread is not current:
            callback_thread.join(timeout=1.0)

        # Messages belong to the old transport generation. Never replay them
        # into a new COM connection after firmware update/reconnect.
        try:
            while True:
                self._callback_queue.get_nowait()
        except queue.Empty:
            pass

    def send_command(self, cmd: Command, payload: bytes = b'') -> bool:
        """Send a command byte + optional payload to hardware."""
        if not self.is_connected:
            return False
        with self._write_lock:
            try:
                connection = self._serial
                if connection is None or not connection.is_open:
                    return False
                # write_timeout bounds the only blocking transport operation.
                # Serial.flush() can wait indefinitely for a disappearing USB
                # CDC endpoint on Windows and used to freeze every sender that
                # queued behind _write_lock.
                connection.write(encode_frame(cmd, payload))
                return True
            except (serial.SerialException, OSError, ValueError) as e:
                log.error("Write error: %s", e)
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
            if not self.send_command(
                Command.APP_ICON_META,
                AppIconMeta(app_id, width, height, len(data)).pack(),
            ):
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

    def _enqueue_message(self, generation: int, cmd: Command, payload: bytes):
        item = (generation, cmd, bytes(payload))
        try:
            self._callback_queue.put_nowait(item)
            return
        except queue.Full:
            # A slow WASAPI callback must not stall SerialRead and therefore
            # must not prevent TEST/ACK frames from being processed. Preserve
            # recent user intent by dropping the oldest queued callback.
            try:
                self._callback_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._callback_queue.put_nowait(item)
            except queue.Full:
                log.warning("Dropped serial callback after dispatcher backlog")

    def _callback_loop(self, stop_event: threading.Event):
        while not stop_event.is_set():
            try:
                generation, cmd, payload = self._callback_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if stop_event.is_set():
                break
            if generation != self._connection_generation:
                continue
            callback = self.on_message
            if callback is None:
                continue
            try:
                callback(cmd, payload)
            except Exception:
                log.exception("Serial message callback failed for %s", cmd.name)

    def _read_loop(self, stop_event: threading.Event):
        """Parse frames quickly; heavy controller callbacks run separately."""
        reconnect_delay = 1.0

        while self._running and not stop_event.is_set():
            if not self.is_connected:
                if self.connect():
                    reconnect_delay = 1.0
                else:
                    self._set_status(
                        f"Searching for VuNMix — retry in {reconnect_delay:.1f}s"
                    )
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
                    # An open COM handle is not enough to call the device
                    # connected. Only valid framed traffic proves the PC and
                    # VuNMix firmware are actually communicating.
                    now = time.monotonic()
                    self._last_protocol_rx = now

                    if cmd == Command.TEST:
                        self._last_test_response = now
                        # A TEST response is the protocol-level proof that this
                        # serial target is VuNMix. Only now persist its identity.
                        self.confirm_current_device()
                        version = payload.decode('ascii', errors='replace').strip()
                        log.info("Device version: %s", version)
                        self._set_status(f"VuNMix connected on {self.port}")
                        if self.on_version:
                            self.on_version(version)
                        continue

                    if cmd == Command.OK:
                        self._last_ok_response = now
                        continue

                    expected_size = COMMAND_PAYLOAD_SIZE.get(cmd)
                    if expected_size is None or len(payload) != expected_size:
                        log.warning(
                            "Invalid payload size for %s: got %d, expected %s",
                            cmd.name,
                            len(payload),
                            expected_size,
                        )
                        continue

                    if self.on_message:
                        self._enqueue_message(self._connection_generation, cmd, payload)

            except (serial.SerialException, OSError) as e:
                log.error("Serial read error: %s", e, exc_info=True)
                self.disconnect()
                time.sleep(0.5)
            except Exception as e:
                log.exception("Unexpected serial parser/callback error: %s", e)
