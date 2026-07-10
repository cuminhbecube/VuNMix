"""Safe ESP32-S3 application firmware updater for VuNMix."""

import logging
import pathlib
import time
from typing import Callable, Optional


log = logging.getLogger(__name__)

APP_OFFSET = 0x10000
APP_PARTITION_SIZE = 0x640000
class FirmwareValidationError(ValueError):
    pass


def validate_firmware(path: str) -> pathlib.Path:
    firmware = pathlib.Path(path).expanduser().resolve()
    if not firmware.is_file():
        raise FirmwareValidationError("Firmware file does not exist.")
    if firmware.suffix.lower() != ".bin":
        raise FirmwareValidationError("Select a PlatformIO firmware.bin file.")

    size = firmware.stat().st_size
    if size < 4096:
        raise FirmwareValidationError("Firmware image is too small.")
    if size > APP_PARTITION_SIZE:
        raise FirmwareValidationError(
            f"Firmware exceeds the {APP_PARTITION_SIZE // 1024} KiB app partition."
        )

    try:
        from esptool.bin_image import LoadFirmwareImage
        image = LoadFirmwareImage("esp32s3", str(firmware))
    except Exception as exc:
        raise FirmwareValidationError(
            "The file is not a valid ESP32-S3 application image."
        ) from exc

    if getattr(image, "chip_id", None) != 9:
        raise FirmwareValidationError("Firmware target is not ESP32-S3.")
    return firmware


def flash_firmware(
    port: str,
    path: str,
    progress: Optional[Callable[[float, str], None]] = None,
) -> None:
    """Flash the complete app image in one esptool transaction.

    Resetting after every chunk can boot a partially written application if the
    USB link is interrupted. A single transaction keeps the chip in the
    bootloader until all image data has been written and verified by esptool.
    """
    firmware = validate_firmware(path)
    from esptool import main as esptool_main

    if progress:
        progress(0.0, "Writing firmware image...")
    args = [
        "--chip", "esp32s3",
        "--port", port,
        "--baud", "115200",
        "--before", "default_reset",
        "--after", "hard_reset",
        "write_flash",
        "--no-compress",
        "--flash_mode", "keep",
        "--flash_freq", "keep",
        "--flash_size", "keep",
        hex(APP_OFFSET),
        str(firmware),
    ]
    try:
        esptool_main(args)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(f"esptool stopped with code {exc.code}") from exc
    except Exception as exc:
        raise RuntimeError(f"Firmware write failed: {exc}") from exc

    if progress:
        progress(1.0, "Firmware updated. Reconnecting...")
    time.sleep(2.0)
