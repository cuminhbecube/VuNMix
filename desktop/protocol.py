"""
VuNMix Serial Protocol — Binary message definitions matching firmware exactly.

Packed structs use little-endian byte order to match ESP32-S3 (Xtensa).
Bitfield packing follows GCC __attribute__((__packed__)) behavior.
"""

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Tuple




# ─── Command Enum (mirrors firmware Enums.h) ───────────────────────────────
class Command(IntEnum):
    ERROR              = -1
    NONE               =  0
    TEST               =  1
    OK                 =  2
    SETTINGS           =  3
    SESSION_INFO       =  4
    CURRENT_SESSION    =  5
    ALTERNATE_SESSION  =  6
    PREVIOUS_SESSION   =  7
    NEXT_SESSION       =  8
    VOLUME_CURR_CHANGE =  9
    VOLUME_ALT_CHANGE  = 10
    VOLUME_PREV_CHANGE = 11
    VOLUME_NEXT_CHANGE = 12
    MODE_STATES        = 13
    DEBUG              = 14
    SLEEP              = 15
    TIME_SYNC          = 16
    METER_LEVEL        = 17
    APP_ICON_META      = 18
    APP_ICON_CHUNK     = 19


class SessionIndex(IntEnum):
    INDEX_CURRENT   = 0
    INDEX_ALTERNATE = 1
    INDEX_PREVIOUS  = 2
    INDEX_NEXT      = 3
    INDEX_MAX       = 4


class DisplayMode(IntEnum):
    MODE_SPLASH      = 0
    MODE_OUTPUT      = 1
    MODE_INPUT       = 2
    MODE_APPLICATION = 3
    MODE_GAME        = 4
    MODE_HEALTH      = 5
    MODE_MAX         = 6


class StandbyLedMode(IntEnum):
    COLOR_WAVE     = 0
    RAINBOW        = 1
    METEOR         = 2
    TWINKLE        = 3
    BREATHE        = 4
    CONFETTI       = 5
    FIRE           = 6
    OCEAN          = 7
    LAVA           = 8
    SCANNER        = 9
    THEATER_CHASE  = 10
    RUNNING_LIGHTS = 11
    GRADIENT       = 12
    SPARKLE        = 13
    AURORA         = 14
    LED_OFF        = 15

STANDBY_LED_NAMES = [
    "Color Wave",
    "Rainbow",
    "Meteor",
    "Twinkle",
    "Breathe",
    "Confetti",
    "Fire",
    "Ocean",
    "Lava",
    "Scanner",
    "Theater Chase",
    "Running Lights",
    "Gradient",
    "Sparkle",
    "Aurora",
    "Off",
]

# Binary frame:
#   magic[2] | command[1] | payload_length[1] | payload | crc16[2]
# CRC-16/CCITT-FALSE covers command, payload_length and payload.
FRAME_MAGIC = b'\xA5\x5A'
MAX_FRAME_PAYLOAD = 64
PROTOCOL_VERSION = 1


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode_frame(cmd: Command, payload: bytes = b'') -> bytes:
    if len(payload) > MAX_FRAME_PAYLOAD:
        raise ValueError(f"Payload too large: {len(payload)} > {MAX_FRAME_PAYLOAD}")
    body = bytes([int(cmd) & 0xFF, len(payload)]) + payload
    return FRAME_MAGIC + body + struct.pack('<H', crc16_ccitt(body))


class FrameParser:
    """Incremental parser that discards noise and resumes at the next valid frame."""

    def __init__(self):
        self._buffer = bytearray()

    def reset(self):
        self._buffer.clear()

    def feed(self, data: bytes) -> List[Tuple[Command, bytes]]:
        if data:
            self._buffer.extend(data)
        frames: List[Tuple[Command, bytes]] = []

        while True:
            magic_at = self._buffer.find(FRAME_MAGIC)
            if magic_at < 0:
                # Retain a possible first magic byte split across reads.
                self._buffer[:] = self._buffer[-1:] if self._buffer.endswith(FRAME_MAGIC[:1]) else b''
                break
            if magic_at:
                del self._buffer[:magic_at]
            if len(self._buffer) < 6:
                break

            payload_len = self._buffer[3]
            if payload_len > MAX_FRAME_PAYLOAD:
                del self._buffer[0]
                continue

            frame_len = 2 + 2 + payload_len + 2
            if len(self._buffer) < frame_len:
                break

            body = bytes(self._buffer[2:4 + payload_len])
            expected_crc = struct.unpack('<H', self._buffer[4 + payload_len:frame_len])[0]
            if crc16_ccitt(body) != expected_crc:
                del self._buffer[0]
                continue

            raw_cmd = body[0]
            try:
                cmd = Command(raw_cmd if raw_cmd < 128 else raw_cmd - 256)
            except ValueError:
                del self._buffer[:frame_len]
                continue

            frames.append((cmd, body[2:]))
            del self._buffer[:frame_len]

        return frames

# ─── Data Structures ───────────────────────────────────────────────────────
@dataclass
class Color:
    """RGB color, 3 bytes packed."""
    r: int = 0
    g: int = 0
    b: int = 0

    def pack(self) -> bytes:
        return struct.pack('<BBB', _clamp_int(self.r, 0, 255),
                           _clamp_int(self.g, 0, 255),
                           _clamp_int(self.b, 0, 255))

    @classmethod
    def unpack(cls, data: bytes) -> 'Color':
        r, g, b = struct.unpack('<BBB', data[:3])
        return cls(r=r, g=g, b=b)

    def to_list(self) -> list:
        return [self.r, self.g, self.b]

    @classmethod
    def from_list(cls, lst: list) -> 'Color':
        if not isinstance(lst, (list, tuple)) or len(lst) < 3:
            raise ValueError("Color must contain three RGB values")
        return cls(r=_clamp_int(lst[0], 0, 255),
                   g=_clamp_int(lst[1], 0, 255),
                   b=_clamp_int(lst[2], 0, 255))


@dataclass
class VolumeData:
    """
    2 bytes, bitfield layout (GCC packed):
      byte0: id(7 bits) | isDefault(1 bit MSB)
      byte1: volume(7 bits) | isMuted(1 bit MSB)
    """
    id: int = 0
    is_default: bool = False
    volume: int = 0
    is_muted: bool = False

    def pack(self) -> bytes:
        byte0 = (_clamp_int(self.id, 0, 127) & 0x7F) | (0x80 if self.is_default else 0)
        byte1 = (_clamp_int(self.volume, 0, 100) & 0x7F) | (0x80 if self.is_muted else 0)
        return bytes([byte0, byte1])

    @classmethod
    def unpack(cls, data: bytes) -> 'VolumeData':
        byte0, byte1 = data[0], data[1]
        return cls(
            id=byte0 & 0x7F,
            is_default=bool(byte0 & 0x80),
            volume=byte1 & 0x7F,
            is_muted=bool(byte1 & 0x80),
        )


@dataclass
class MeterData:
    """Live peak levels for the current and alternate mixer channels."""
    current: int = 0
    alternate: int = 0

    def pack(self) -> bytes:
        return bytes([
            _clamp_int(self.current, 0, 100),
            _clamp_int(self.alternate, 0, 100),
        ])

    @classmethod
    def unpack(cls, data: bytes) -> 'MeterData':
        return cls(
            current=min(data[0], 100),
            alternate=min(data[1], 100),
        )


@dataclass
class AppIconMeta:
    """App icon transfer header: 16x16 RGB565 icons are sent in chunks."""
    id: int = 0
    width: int = 16
    height: int = 16
    data_length: int = 512

    def pack(self) -> bytes:
        return struct.pack(
            '<BBBH',
            _clamp_int(self.id, 0, 127),
            _clamp_int(self.width, 0, 255),
            _clamp_int(self.height, 0, 255),
            _clamp_int(self.data_length, 0, 65535),
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'AppIconMeta':
        app_id, width, height, data_length = struct.unpack('<BBBH', data[:5])
        return cls(app_id, width, height, data_length)


@dataclass
class AppIconChunk:
    """One icon data chunk. Payload is fixed to fit the 64-byte frame limit."""
    id: int = 0
    index: int = 0
    data: bytes = b''

    def pack(self) -> bytes:
        chunk = bytes(self.data[:60])
        return bytes([
            _clamp_int(self.id, 0, 127),
            _clamp_int(self.index, 0, 255),
            len(chunk),
        ]) + chunk.ljust(60, b'\x00')

    @classmethod
    def unpack(cls, data: bytes) -> 'AppIconChunk':
        app_id, index, length = data[0], data[1], min(data[2], 60)
        return cls(app_id, index, bytes(data[3:3 + length]))


@dataclass
class SessionData:
    """
    32 bytes total:
      name[30]: null-terminated ASCII string
      data:     VolumeData (2 bytes)
    """
    name: str = ""
    data: VolumeData = field(default_factory=VolumeData)

    def pack(self) -> bytes:
        name_bytes = _truncate_utf8(str(self.name), 29)
        name_bytes = name_bytes.ljust(30, b'\x00')
        return name_bytes + self.data.pack()

    @classmethod
    def unpack(cls, raw: bytes) -> 'SessionData':
        name_raw = raw[:30]
        # Find null terminator
        null_idx = name_raw.find(b'\x00')
        if null_idx >= 0:
            name = name_raw[:null_idx].decode('utf-8', errors='replace')
        else:
            name = name_raw.decode('utf-8', errors='replace')
        vol = VolumeData.unpack(raw[30:32])
        return cls(name=name, data=vol)


@dataclass
class SessionInfo:
    """
    5 bytes:
      mode:       uint8 (DisplayMode)
      current:    uint8
      sessions[3]: uint8×3 (session counts per mode)
    """
    mode: int = DisplayMode.MODE_SPLASH
    current: int = 0
    sessions: list = field(default_factory=lambda: [0, 0, 0])

    def pack(self) -> bytes:
        sessions = list(self.sessions[:3])
        sessions.extend([0] * (3 - len(sessions)))
        return bytes([
            _clamp_int(self.mode, 0, int(DisplayMode.MODE_MAX) - 1),
            _clamp_int(self.current, 0, 255),
            _clamp_int(sessions[0], 0, 255),
            _clamp_int(sessions[1], 0, 255),
            _clamp_int(sessions[2], 0, 255),
        ])

    @classmethod
    def unpack(cls, data: bytes) -> 'SessionInfo':
        mode = data[0]
        current = data[1]
        sessions = [data[2], data[3], data[4]]
        return cls(mode=mode, current=current, sessions=sessions)


@dataclass
class DeviceSettings:
    """
    19 bytes:
      sleepAfterSeconds:      uint16
      accelerationPercentage: 7 bits | continuousScroll: 1 bit (MSB)
      sleepEnabled:           uint8 (bool)
      standbyLedMode:         uint8 (StandbyLedMode enum)
      volumeMinColor:         Color (3 bytes)
      volumeMaxColor:         Color (3 bytes)
      mixChannelAColor:       Color (3 bytes)
      mixChannelBColor:       Color (3 bytes)
      ledBrightness:          uint8
    """
    sleep_after_seconds: int = 5
    acceleration_percentage: int = 60
    continuous_scroll: bool = True
    sleep_enabled: bool = True
    standby_led_mode: int = 0  # StandbyLedMode.COLOR_WAVE
    volume_min_color: Color = field(default_factory=lambda: Color(0, 0, 255))
    volume_max_color: Color = field(default_factory=lambda: Color(255, 0, 0))
    mix_channel_a_color: Color = field(default_factory=lambda: Color(0, 0, 255))
    mix_channel_b_color: Color = field(default_factory=lambda: Color(255, 0, 255))
    led_brightness: int = 96
    clock_standby_minutes: int = 10  # 0=disabled

    def pack(self) -> bytes:
        sleep_seconds = _clamp_int(self.sleep_after_seconds, 0, 65535)
        acceleration = _clamp_int(self.acceleration_percentage, 0, 100)
        byte2 = (acceleration & 0x7F) | (0x80 if self.continuous_scroll else 0)
        byte3 = 1 if self.sleep_enabled else 0
        byte4 = _clamp_int(self.standby_led_mode, 0, len(STANDBY_LED_NAMES) - 1)
        return struct.pack('<HBBB', sleep_seconds, byte2, byte3, byte4) + \
               self.volume_min_color.pack() + \
               self.volume_max_color.pack() + \
               self.mix_channel_a_color.pack() + \
               self.mix_channel_b_color.pack() + \
               struct.pack('<BB', _clamp_int(self.led_brightness, 0, 255),
                           _clamp_int(self.clock_standby_minutes, 0, 255))

    @classmethod
    def unpack(cls, data: bytes) -> 'DeviceSettings':
        sleep_secs, byte2, byte3, byte4 = struct.unpack('<HBBB', data[:5])
        return cls(
            sleep_after_seconds=sleep_secs,
            acceleration_percentage=byte2 & 0x7F,
            continuous_scroll=bool(byte2 & 0x80),
            sleep_enabled=bool(byte3),
            standby_led_mode=byte4,
            volume_min_color=Color.unpack(data[5:8]),
            volume_max_color=Color.unpack(data[8:11]),
            mix_channel_a_color=Color.unpack(data[11:14]),
            mix_channel_b_color=Color.unpack(data[14:17]),
            led_brightness=struct.unpack('<B', data[17:18])[0] if len(data) >= 18 else 96,
            clock_standby_minutes=struct.unpack('<B', data[18:19])[0] if len(data) >= 19 else 10,
        )

    @classmethod
    def from_config(cls, cfg: dict) -> 'DeviceSettings':
        return cls(
            sleep_after_seconds=_clamp_int(cfg.get('sleep_after_seconds', 300), 0, 65535),
            acceleration_percentage=_clamp_int(cfg.get('acceleration_percentage', 60), 0, 100),
            continuous_scroll=cfg.get('continuous_scroll', True),
            sleep_enabled=cfg.get('sleep_enabled', True),
            standby_led_mode=_clamp_int(cfg.get('standby_led_mode', 0), 0, len(STANDBY_LED_NAMES) - 1),
            volume_min_color=Color.from_list(cfg.get('volume_min_color', [0, 0, 255])),
            volume_max_color=Color.from_list(cfg.get('volume_max_color', [255, 0, 0])),
            mix_channel_a_color=Color.from_list(cfg.get('mix_channel_a_color', [0, 0, 255])),
            mix_channel_b_color=Color.from_list(cfg.get('mix_channel_b_color', [255, 0, 255])),
            led_brightness=_clamp_int(cfg.get('led_brightness', 96), 0, 255),
            clock_standby_minutes=_clamp_int(cfg.get('clock_standby_minutes', 10), 0, 255),
        )


@dataclass
class ModeStates:
    """
    6 bytes: state per display mode.
    Default: {0, 1, 1, 0, 0, 0} = {LOGO, EDIT, EDIT, NAVIGATE, SELECT_A, NAVIGATE}
    """
    states: list = field(default_factory=lambda: [0, 1, 1, 0, 0, 0])

    def pack(self) -> bytes:
        return bytes(_clamp_int(x, 0, 255) for x in self.states[:6]).ljust(6, b'\x00')

    @classmethod
    def unpack(cls, data: bytes) -> 'ModeStates':
        return cls(states=list(data[:6]))


# ─── Message Helpers ───────────────────────────────────────────────────────

# Map commands to their payload sizes (for reading from HW)
COMMAND_PAYLOAD_SIZE = {
    Command.TEST:               0,   # followed by version string + newline
    Command.OK:                 0,
    Command.SETTINGS:           19,
    Command.SESSION_INFO:       5,
    Command.CURRENT_SESSION:    32,
    Command.ALTERNATE_SESSION:  32,
    Command.PREVIOUS_SESSION:   32,
    Command.NEXT_SESSION:       32,
    Command.VOLUME_CURR_CHANGE: 2,
    Command.VOLUME_ALT_CHANGE:  2,
    Command.VOLUME_PREV_CHANGE: 2,
    Command.VOLUME_NEXT_CHANGE: 2,
    Command.MODE_STATES:        6,
    Command.SLEEP:              0,
    Command.TIME_SYNC:          3,
    Command.METER_LEVEL:        2,
    Command.APP_ICON_META:      5,
    Command.APP_ICON_CHUNK:     63,
}

# Commands that represent session data (index = cmd - CURRENT_SESSION)
SESSION_COMMANDS = [
    Command.CURRENT_SESSION,
    Command.ALTERNATE_SESSION,
    Command.PREVIOUS_SESSION,
    Command.NEXT_SESSION,
]

VOLUME_COMMANDS = [
    Command.VOLUME_CURR_CHANGE,
    Command.VOLUME_ALT_CHANGE,
    Command.VOLUME_PREV_CHANGE,
    Command.VOLUME_NEXT_CHANGE,
]


def _clamp_int(value, minimum: int, maximum: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected integer, got {value!r}") from exc
    return max(minimum, min(maximum, value))


def _truncate_utf8(value: str, max_bytes: int) -> bytes:
    encoded = value.encode('utf-8', errors='replace')
    if len(encoded) <= max_bytes:
        return encoded
    encoded = encoded[:max_bytes]
    while encoded:
        try:
            encoded.decode('utf-8')
            return encoded
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return b''
