"""Safe ESP32-S3 application firmware updater for VuNMix."""

import logging
import os
import pathlib
import sys
import time
from contextlib import contextmanager
from typing import Callable, Optional


log = logging.getLogger(__name__)

APP_OFFSET = 0x10000
APP_PARTITION_SIZE = 0x640000
_STUB_MISSING_MARKER = "Flasher stub data is missing"


class FirmwareValidationError(ValueError):
    pass


@contextmanager
def _ensure_standard_streams():
    """Provide usable stdio streams for PyInstaller windowed builds."""
    original_stdin = sys.stdin
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    opened_streams = []

    try:
        if sys.stdin is None:
            stream = open(os.devnull, "r", encoding="utf-8")
            sys.stdin = stream
            opened_streams.append(stream)

        if sys.stdout is None:
            stream = open(os.devnull, "w", encoding="utf-8")
            sys.stdout = stream
            opened_streams.append(stream)

        if sys.stderr is None:
            stream = open(os.devnull, "w", encoding="utf-8")
            sys.stderr = stream
            opened_streams.append(stream)

        yield
    finally:
        sys.stdin = original_stdin
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        for stream in opened_streams:
            try:
                stream.close()
            except Exception:
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


def _run_esptool(esptool_main, args) -> None:
    """Run esptool safely inside a PyInstaller windowed application."""
    try:
        with _ensure_standard_streams():
            esptool_main(args)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(f"esptool stopped with code {exc.code}") from exc


def flash_firmware(
    port: str,
    path: str,
    progress: Optional[Callable[[float, str], None]] = None,
) -> None:
    """Flash one ESP32-S3 application image at APP_OFFSET.

    The normal path uses esptool's fast RAM flasher stub. If a packaged build
    somehow does not contain the stub data, retry through the ESP32-S3 ROM
    bootloader with --no-stub instead of aborting the firmware update.
    """
    firmware = validate_firmware(path)

    from esptool import main as esptool_main

    if progress:
        progress(0.0, "Writing firmware image...")

    args = [
        "--chip",
        "esp32s3",
        "--port",
        port,
        "--baud",
        "115200",
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
        "--no-compress",
        "--flash_mode",
        "keep",
        "--flash_freq",
        "keep",
        "--flash_size",
        "keep",
        hex(APP_OFFSET),
        str(firmware),
    ]

    try:
        _run_esptool(esptool_main, args)

    except Exception as exc:
        if _STUB_MISSING_MARKER not in str(exc):
            raise RuntimeError(f"Firmware write failed: {exc}") from exc

        # The PyInstaller build should contain the stub data because VuNMix.spec
        # collects the entire esptool package. Keep this fallback so an updater
        # can still recover if packaging changes or stub files are missing.
        log.warning(
            "esptool flasher stub data is unavailable; retrying via ROM bootloader"
        )

        if progress:
            progress(
                0.02,
                "Flasher stub unavailable. Retrying with ESP32-S3 ROM bootloader...",
            )

        fallback_args = list(args)
        command_index = fallback_args.index("write_flash")
        fallback_args.insert(command_index, "--no-stub")

        try:
            _run_esptool(esptool_main, fallback_args)
        except Exception as retry_exc:
            raise RuntimeError(
                f"Firmware write failed using ROM bootloader fallback: {retry_exc}"
            ) from retry_exc

    if progress:
        progress(1.0, "Firmware updated. Reconnecting...")

    time.sleep(2.0)
