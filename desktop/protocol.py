"""
VuNMix Serial Protocol — Binary message definitions matching firmware exactly.

Packed structs use little-endian byte order to match ESP32-S3 (Xtensa).
Bitfield packing follows GCC __attribute__((__packed__)) behavior.
"""

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


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
    MODE_MAX         = 5


# ─── Data Structures ───────────────────────────────────────────────────────
@dataclass
class Color:
    """RGB color, 3 bytes packed."""
    r: int = 0
    g: int = 0
    b: int = 0

    def pack(self) -> bytes:
        return struct.pack('<BBB', self.r, self.g, self.b)

    @classmethod
    def unpack(cls, data: bytes) -> 'Color':
        r, g, b = struct.unpack('<BBB', data[:3])
        return cls(r=r, g=g, b=b)

    def to_list(self) -> list:
        return [self.r, self.g, self.b]

    @classmethod
    def from_list(cls, lst: list) -> 'Color':
        return cls(r=lst[0], g=lst[1], b=lst[2])


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
        byte0 = (self.id & 0x7F) | (0x80 if self.is_default else 0)
        byte1 = (self.volume & 0x7F) | (0x80 if self.is_muted else 0)
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
class SessionData:
    """
    32 bytes total:
      name[30]: null-terminated ASCII string
      data:     VolumeData (2 bytes)
    """
    name: str = ""
    data: VolumeData = field(default_factory=VolumeData)

    def pack(self) -> bytes:
        name_bytes = self.name.encode('ascii', errors='replace')[:29]
        name_bytes = name_bytes.ljust(30, b'\x00')
        return name_bytes + self.data.pack()

    @classmethod
    def unpack(cls, raw: bytes) -> 'SessionData':
        name_raw = raw[:30]
        # Find null terminator
        null_idx = name_raw.find(b'\x00')
        if null_idx >= 0:
            name = name_raw[:null_idx].decode('ascii', errors='replace')
        else:
            name = name_raw.decode('ascii', errors='replace')
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
        return bytes([
            self.mode,
            self.current,
            self.sessions[0],
            self.sessions[1],
            self.sessions[2],
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
    14 bytes:
      sleepAfterSeconds:      uint8
      accelerationPercentage: 7 bits | continuousScroll: 1 bit (MSB)
      volumeMinColor:         Color (3 bytes)
      volumeMaxColor:         Color (3 bytes)
      mixChannelAColor:       Color (3 bytes)
      mixChannelBColor:       Color (3 bytes)
    """
    sleep_after_seconds: int = 5
    acceleration_percentage: int = 60
    continuous_scroll: bool = True
    volume_min_color: Color = field(default_factory=lambda: Color(0, 0, 255))
    volume_max_color: Color = field(default_factory=lambda: Color(255, 0, 0))
    mix_channel_a_color: Color = field(default_factory=lambda: Color(0, 0, 255))
    mix_channel_b_color: Color = field(default_factory=lambda: Color(255, 0, 255))

    def pack(self) -> bytes:
        byte1 = (self.acceleration_percentage & 0x7F) | (0x80 if self.continuous_scroll else 0)
        return bytes([self.sleep_after_seconds, byte1]) + \
               self.volume_min_color.pack() + \
               self.volume_max_color.pack() + \
               self.mix_channel_a_color.pack() + \
               self.mix_channel_b_color.pack()

    @classmethod
    def unpack(cls, data: bytes) -> 'DeviceSettings':
        return cls(
            sleep_after_seconds=data[0],
            acceleration_percentage=data[1] & 0x7F,
            continuous_scroll=bool(data[1] & 0x80),
            volume_min_color=Color.unpack(data[2:5]),
            volume_max_color=Color.unpack(data[5:8]),
            mix_channel_a_color=Color.unpack(data[8:11]),
            mix_channel_b_color=Color.unpack(data[11:14]),
        )

    @classmethod
    def from_config(cls, cfg: dict) -> 'DeviceSettings':
        return cls(
            sleep_after_seconds=cfg.get('sleep_after_seconds', 5),
            acceleration_percentage=cfg.get('acceleration_percentage', 60),
            continuous_scroll=cfg.get('continuous_scroll', True),
            volume_min_color=Color.from_list(cfg.get('volume_min_color', [0, 0, 255])),
            volume_max_color=Color.from_list(cfg.get('volume_max_color', [255, 0, 0])),
            mix_channel_a_color=Color.from_list(cfg.get('mix_channel_a_color', [0, 0, 255])),
            mix_channel_b_color=Color.from_list(cfg.get('mix_channel_b_color', [255, 0, 255])),
        )


@dataclass
class ModeStates:
    """
    5 bytes: state per display mode.
    Default: {0, 1, 1, 0, 0} = {LOGO, EDIT, EDIT, NAVIGATE, SELECT_A}
    """
    states: list = field(default_factory=lambda: [0, 1, 1, 0, 0])

    def pack(self) -> bytes:
        return bytes(self.states[:5]).ljust(5, b'\x00')

    @classmethod
    def unpack(cls, data: bytes) -> 'ModeStates':
        return cls(states=list(data[:5]))


# ─── Message Helpers ───────────────────────────────────────────────────────

# Map commands to their payload sizes (for reading from HW)
COMMAND_PAYLOAD_SIZE = {
    Command.TEST:               0,   # followed by version string + newline
    Command.OK:                 0,
    Command.SETTINGS:           14,
    Command.SESSION_INFO:       5,
    Command.CURRENT_SESSION:    32,
    Command.ALTERNATE_SESSION:  32,
    Command.PREVIOUS_SESSION:   32,
    Command.NEXT_SESSION:       32,
    Command.VOLUME_CURR_CHANGE: 2,
    Command.VOLUME_ALT_CHANGE:  2,
    Command.VOLUME_PREV_CHANGE: 2,
    Command.VOLUME_NEXT_CHANGE: 2,
    Command.MODE_STATES:        5,
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
