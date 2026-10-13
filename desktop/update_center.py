"""Read-only compatibility model backing the Desktop Update Center.

No firmware operation or network request is performed while building a view.
All downloads/flashes remain explicit UI actions using the existing verified
updaters. Firmware v0.4.21+ supports all 16 clock styles.
"""
from __future__ import annotations

from dataclasses import dataclass

from app_updater import version_tuple

SIXTEEN_CLOCK_FIRMWARE = (0, 4, 21)


@dataclass(frozen=True)
class DeviceUpdateState:
    desktop_version: str
    firmware_version: str
    connected: bool
    compatible_clock_styles: int | None
    status: str


def describe_device_update(desktop_version: str, firmware_version: str,
                           connected: bool) -> DeviceUpdateState:
    normalized_desktop = (desktop_version or "unknown").lstrip("v")
    normalized_firmware = (firmware_version or "unknown").lstrip("v")
    firmware_tuple = version_tuple(normalized_firmware)
    styles = (16 if firmware_tuple >= SIXTEEN_CLOCK_FIRMWARE else 8) if firmware_tuple else None
    if not connected:
        status = "Device disconnected — firmware version not verified"
        styles = None
    elif firmware_tuple is None:
        status = "Unknown firmware — verify version before using extra clock styles"
    elif styles < 16:
        status = "Firmware update required for Clock styles 8–15"
    elif normalized_desktop != normalized_firmware:
        status = "Desktop and firmware versions differ — check release compatibility"
    else:
        status = "Desktop and firmware versions aligned"
    return DeviceUpdateState(normalized_desktop, normalized_firmware, connected,
                             styles, status)
