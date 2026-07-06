"""Safe ESP32-S3 application firmware updater for VuNMix."""

import contextlib
import io
import logging
import pathlib
import tempfile
import time
from typing import Callable, Optional


log = logging.getLogger(__name__)

APP_OFFSET = 0x10000
APP_PARTITION_SIZE = 0x640000
CHUNK_SIZE = 0x40000


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
    """Flash only the OTA app partition, reconnecting between short chunks."""
    firmware = validate_firmware(path)
    from esptool import main as esptool_main

    with tempfile.TemporaryDirectory(prefix="vunmix-fw-") as directory:
        chunk_dir = pathlib.Path(directory)
        chunks = []
        with firmware.open("rb") as source:
            index = 0
            while True:
                data = source.read(CHUNK_SIZE)
                if not data:
                    break
                chunk = chunk_dir / f"{index:02d}.bin"
                chunk.write_bytes(data)
                chunks.append(chunk)
                index += 1

        total = len(chunks)
        for index, chunk in enumerate(chunks):
            address = APP_OFFSET + index * CHUNK_SIZE
            if progress:
                progress(
                    index / total,
                    f"Writing block {index + 1}/{total}...",
                )

            output = io.StringIO()
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
                hex(address),
                str(chunk),
            ]
            try:
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    esptool_main(args)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise RuntimeError(f"esptool stopped with code {exc.code}") from exc
            except Exception as exc:
                details = output.getvalue().strip()
                if details:
                    log.error("esptool output:\n%s", details)
                raise RuntimeError(
                    f"Firmware write failed at block {index + 1}/{total}: {exc}"
                ) from exc

            log.debug("%s", output.getvalue().strip())
            time.sleep(0.7)

    if progress:
        progress(1.0, "Firmware updated. Reconnecting...")
    time.sleep(2.0)
