"""USB/serial discovery helpers for VuNMix ESP32-S3 devices.

A COM number is only a temporary Windows address. This module remembers a
stable USB identity and resolves the current COM port whenever the device
re-enumerates after reset, firmware update, sleep, or reconnect.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

import serial.tools.list_ports


ESPRESSIF_VID = 0x303A
# ESP32-S3 USB Serial/JTAG plus the common Arduino/TinyUSB application PID.
KNOWN_VUNMIX_USB_IDS = {
    (ESPRESSIF_VID, 0x1001),
    (ESPRESSIF_VID, 0x4001),
}

_IDENTITY_DIR = Path(
    os.environ.get(
        "LOCALAPPDATA",
        os.path.join(os.path.expanduser("~"), "AppData", "Local"),
    )
) / "VuNMix"
_IDENTITY_FILE = _IDENTITY_DIR / "device_identity.json"


def _text(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


@dataclass(frozen=True)
class DeviceIdentity:
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None
    product: Optional[str] = None
    manufacturer: Optional[str] = None
    location: Optional[str] = None

    @classmethod
    def from_port(cls, port) -> "DeviceIdentity":
        return cls(
            vid=getattr(port, "vid", None),
            pid=getattr(port, "pid", None),
            serial_number=_text(getattr(port, "serial_number", None)),
            product=_text(getattr(port, "product", None)),
            manufacturer=_text(getattr(port, "manufacturer", None)),
            location=_text(getattr(port, "location", None)),
        )

    @classmethod
    def from_dict(cls, data) -> Optional["DeviceIdentity"]:
        if not isinstance(data, dict):
            return None
        try:
            identity = cls(
                vid=int(data["vid"]) if data.get("vid") is not None else None,
                pid=int(data["pid"]) if data.get("pid") is not None else None,
                serial_number=_text(data.get("serial_number")),
                product=_text(data.get("product")),
                manufacturer=_text(data.get("manufacturer")),
                location=_text(data.get("location")),
            )
        except (TypeError, ValueError):
            return None
        return identity if identity.is_useful else None

    @property
    def is_useful(self) -> bool:
        # VID/PID alone can still identify a single attached board. Serial or
        # USB topology location is stronger and distinguishes identical boards.
        return any(
            (
                self.serial_number,
                self.location,
                self.product,
                self.vid is not None and self.pid is not None,
            )
        )

    def to_dict(self) -> dict:
        return asdict(self)


def list_serial_ports() -> list:
    return list(serial.tools.list_ports.comports())


def is_known_vunmix_port(port) -> bool:
    return (getattr(port, "vid", None), getattr(port, "pid", None)) in KNOWN_VUNMIX_USB_IDS


def _identity_score(port, identity: DeviceIdentity) -> int:
    """Return a stable-device match score. Zero means no identity match."""
    vid = getattr(port, "vid", None)
    pid = getattr(port, "pid", None)
    serial_number = _text(getattr(port, "serial_number", None))
    location = _text(getattr(port, "location", None))
    product = _text(getattr(port, "product", None))
    manufacturer = _text(getattr(port, "manufacturer", None))

    # Serial number is the strongest identifier and remains useful if the
    # application and bootloader expose different PIDs.
    if identity.serial_number and serial_number == identity.serial_number:
        if vid == identity.vid or vid == ESPRESSIF_VID:
            return 100

    # USB topology location normally survives COM renumbering on the same
    # physical port, including ESP32-S3 reset/re-enumeration.
    if identity.location and location == identity.location:
        if vid == identity.vid or vid == ESPRESSIF_VID:
            return 90

    # Exact VID/PID plus descriptive strings is useful when no serial is
    # exposed. Ties are intentionally rejected by select_device_port().
    if identity.vid is not None and identity.pid is not None:
        if vid == identity.vid and pid == identity.pid:
            if identity.product and product == identity.product:
                return 80
            if identity.manufacturer and manufacturer == identity.manufacturer:
                return 75
            return 70

    return 0


def select_device_port(
    ports: Iterable,
    *,
    identity: Optional[DeviceIdentity] = None,
    preferred_port: Optional[str] = None,
):
    """Choose the safest current serial port for VuNMix.

    Priority:
      1. Persisted USB identity (serial/location/VID+PID).
      2. Explicit preferred COM when it is a known VuNMix USB device.
      3. A single known ESP32-S3 VuNMix candidate.
      4. Explicit preferred COM as a manual fallback, but only when no
         persisted identity exists.

    If two equally plausible ESP32-S3 devices are present and there is no
    identity/preference to disambiguate them, return None rather than opening
    the wrong device.
    """
    ports = list(ports)
    preferred = (preferred_port or "").strip().lower()
    had_identity = identity is not None

    if identity is not None:
        scored = [(_identity_score(port, identity), port) for port in ports]
        best_score = max((score for score, _ in scored), default=0)
        if best_score > 0:
            best = [port for score, port in scored if score == best_score]
            if len(best) == 1:
                return best[0]
            if preferred:
                for port in best:
                    if str(getattr(port, "device", "")).lower() == preferred:
                        return port
            return None

    known = [port for port in ports if is_known_vunmix_port(port)]
    if preferred:
        for port in known:
            if str(getattr(port, "device", "")).lower() == preferred:
                return port

    if len(known) == 1:
        return known[0]
    if len(known) > 1:
        return None

    # Preserve explicit/manual COM support for USB-UART adapters and older
    # hardware only before a stable identity has been learned. If an identity
    # exists but does not match, opening the old COM could target an unrelated
    # device that inherited the number after Windows re-enumeration.
    if preferred and not had_identity:
        for port in ports:
            if str(getattr(port, "device", "")).lower() == preferred:
                return port

    return None


def resolve_port_name(
    preferred_port: Optional[str],
    *,
    identity: Optional[DeviceIdentity] = None,
    ports: Optional[Iterable] = None,
) -> Optional[str]:
    if ports is None:
        try:
            ports = list_serial_ports()
        except Exception:
            ports = []
    ports = list(ports)
    selected = select_device_port(
        ports,
        identity=identity,
        preferred_port=preferred_port,
    )
    if selected is not None:
        return str(selected.device)

    # If enumeration is unavailable/empty, keep the explicit port so the
    # caller receives the real serial/esptool error rather than a false
    # "device not found" caused by the enumerator itself.
    if not ports and preferred_port:
        return str(preferred_port)
    return None


def load_device_identity(path: Optional[Path] = None) -> Optional[DeviceIdentity]:
    path = Path(path or _IDENTITY_FILE)
    try:
        with path.open("r", encoding="utf-8") as stream:
            return DeviceIdentity.from_dict(json.load(stream))
    except (OSError, ValueError, TypeError):
        return None


def save_device_identity(identity: DeviceIdentity, path: Optional[Path] = None) -> None:
    if not identity.is_useful:
        return
    path = Path(path or _IDENTITY_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(identity.to_dict(), stream, indent=2, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def clear_device_identity(path: Optional[Path] = None) -> None:
    path = Path(path or _IDENTITY_FILE)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
