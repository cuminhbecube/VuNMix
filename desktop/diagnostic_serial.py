"""Diagnostic SerialService extension used by the desktop application."""

from __future__ import annotations

import struct
import time
from typing import Dict

from protocol import (
    FRAME_MAGIC,
    MAX_FRAME_PAYLOAD,
    Command,
    crc16_ccitt,
    encode_frame,
)
from serial_service import SerialService


class CountingFrameParser:
    """Frame parser with persistent counters for support diagnostics."""

    def __init__(self):
        self._buffer = bytearray()
        self.rx_bytes = 0
        self.frames = 0
        self.crc_errors = 0
        self.protocol_errors = 0
        self.discarded_bytes = 0

    def reset(self):
        self._buffer.clear()

    def feed(self, data: bytes):
        if data:
            self.rx_bytes += len(data)
            self._buffer.extend(data)
        frames = []

        while True:
            magic_at = self._buffer.find(FRAME_MAGIC)
            if magic_at < 0:
                retained = 1 if self._buffer.endswith(FRAME_MAGIC[:1]) else 0
                self.discarded_bytes += max(0, len(self._buffer) - retained)
                self._buffer[:] = self._buffer[-1:] if retained else b""
                break
            if magic_at:
                self.discarded_bytes += magic_at
                del self._buffer[:magic_at]
            if len(self._buffer) < 6:
                break

            payload_len = self._buffer[3]
            if payload_len > MAX_FRAME_PAYLOAD:
                self.protocol_errors += 1
                self.discarded_bytes += 1
                del self._buffer[0]
                continue

            frame_len = 2 + 2 + payload_len + 2
            if len(self._buffer) < frame_len:
                break

            body = bytes(self._buffer[2:4 + payload_len])
            expected_crc = struct.unpack("<H", self._buffer[4 + payload_len:frame_len])[0]
            if crc16_ccitt(body) != expected_crc:
                self.crc_errors += 1
                self.discarded_bytes += 1
                del self._buffer[0]
                continue

            raw_cmd = body[0]
            try:
                cmd = Command(raw_cmd if raw_cmd < 128 else raw_cmd - 256)
            except ValueError:
                self.protocol_errors += 1
                self.discarded_bytes += frame_len
                del self._buffer[:frame_len]
                continue

            frames.append((cmd, body[2:]))
            self.frames += 1
            del self._buffer[:frame_len]

        return frames


class DiagnosticSerialService(SerialService):
    """Serial service that records transport health without changing protocol v1."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parser = CountingFrameParser()
        self._started_at = time.monotonic()
        self._connected_since = None
        self._successful_connects = 0
        self._tx_frames = 0
        self._tx_bytes = 0
        self._last_serial_error = ""

    def connect(self) -> bool:
        was_connected = self.is_connected
        result = super().connect()
        if result and not was_connected:
            self._successful_connects += 1
            self._connected_since = time.monotonic()
        return result

    def disconnect(self):
        if self.is_connected:
            self._connected_since = None
        return super().disconnect()

    def send_command(self, cmd: Command, payload: bytes = b"") -> bool:
        result = super().send_command(cmd, payload)
        if result:
            self._tx_frames += 1
            self._tx_bytes += len(encode_frame(cmd, payload))
        return result

    def health_snapshot(self) -> Dict[str, object]:
        now = time.monotonic()
        parser = self._parser
        connected_uptime = (
            round(now - self._connected_since, 1)
            if self._connected_since is not None
            else 0.0
        )
        return {
            "status": self.status,
            "port": self.port,
            "preferred_port": self.preferred_port,
            "connected": self.is_connected,
            "service_uptime_s": round(now - self._started_at, 1),
            "connection_uptime_s": connected_uptime,
            "successful_connects": self._successful_connects,
            "reconnect_count": max(0, self._successful_connects - 1),
            "rx_frames": parser.frames,
            "rx_bytes": parser.rx_bytes,
            "tx_frames": self._tx_frames,
            "tx_bytes": self._tx_bytes,
            "crc_errors": parser.crc_errors,
            "protocol_errors": parser.protocol_errors,
            "discarded_bytes": parser.discarded_bytes,
            "last_serial_error": self._last_serial_error or "-",
        }
