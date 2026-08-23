"""Safe ESP32-S3 application firmware updater for VuNMix."""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Optional

from device_discovery import load_device_identity, resolve_port_name
from diagnostics import FirmwareUpdateJournal


log = logging.getLogger(__name__)

APP_OFFSET = 0x10000
APP_PARTITION_SIZE = 0x640000
_STUB_MISSING_MARKER = "Flasher stub data is missing"


class FirmwareValidationError(ValueError):
    pass


class FirmwareUpdateError(RuntimeError):
    """User-facing updater failure with a stable diagnostic error code."""

    def __init__(self, code: str, user_message: str, *, detail: str = "", log_path: str = ""):
        self.code = code
        self.user_message = user_message
        self.detail = detail
        self.log_path = log_path
        super().__init__(f"{code}: {user_message}")


@dataclass(frozen=True)
class FirmwareFlashResult:
    port: str
    firmware_path: str
    elapsed_seconds: float
    log_path: str
    used_rom_fallback: bool = False


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


def _resolve_flash_port(preferred_port: str) -> str:
    """Resolve the device's current COM port before entering bootloader."""
    identity = load_device_identity()
    resolved = resolve_port_name(preferred_port, identity=identity)
    if not resolved:
        raise FirmwareUpdateError(
            "COM_NOT_FOUND",
            "VuNMix USB device was not found.",
            detail="Reconnect the device or select its current COM port.",
        )
    if resolved != preferred_port:
        log.info("VuNMix COM changed: %s -> %s", preferred_port, resolved)
    return resolved


def _classify_write_error(exc: BaseException, *, log_path: str = "") -> FirmwareUpdateError:
    text = str(exc)
    lower = text.lower()
    if any(token in lower for token in (
        "could not open port", "cannot open", "access is denied", "permissionerror",
        "port is busy", "device does not recognize", "file not found",
    )):
        return FirmwareUpdateError(
            "COM_ACCESS",
            "The serial port cannot be opened.",
            detail=text,
            log_path=log_path,
        )
    if any(token in lower for token in (
        "failed to connect", "no serial data", "timed out", "timeout",
        "packet header", "bootloader",
    )):
        return FirmwareUpdateError(
            "BOOTLOADER_TIMEOUT",
            "ESP32-S3 did not enter the bootloader in time.",
            detail=text,
            log_path=log_path,
        )
    return FirmwareUpdateError(
        "WRITE_FAILED",
        "Firmware write failed.",
        detail=text,
        log_path=log_path,
    )


def _emit_progress(
    callback: Optional[Callable[[float, str], None]],
    value: float,
    text: str,
) -> None:
    if callback:
        callback(max(0.0, min(1.0, float(value))), text)


def flash_firmware(
    port: str,
    path: str,
    progress: Optional[Callable[[float, str], None]] = None,
) -> FirmwareFlashResult:
    """Flash one ESP32-S3 application image at APP_OFFSET.

    Progress is phase-based because esptool's embedded ``main`` entry point does
    not expose a stable per-block callback. Every attempt receives a dedicated
    structured log with port, image, phase, elapsed time and failure detail.
    """
    journal = FirmwareUpdateJournal(port, path)
    used_rom_fallback = False
    started = time.monotonic()

    try:
        _emit_progress(progress, 0.02, "Validating ESP32-S3 firmware...")
        journal.event("validate")
        try:
            firmware = validate_firmware(path)
        except FirmwareValidationError as exc:
            journal.event("validate_failed", level=logging.ERROR, error=str(exc))
            raise FirmwareUpdateError(
                "IMAGE_INVALID",
                "Selected file is not a valid VuNMix ESP32-S3 firmware image.",
                detail=str(exc),
                log_path=journal.path,
            ) from exc

        journal.event("validated", firmware_size=firmware.stat().st_size)
        _emit_progress(progress, 0.08, "Finding VuNMix USB device...")
        try:
            flash_port = _resolve_flash_port(port)
        except FirmwareUpdateError as exc:
            exc.log_path = journal.path
            journal.event("port_failed", level=logging.ERROR, code=exc.code, error=exc.detail or exc.user_message)
            raise

        journal.event("port_resolved", preferred_port=port, flash_port=flash_port)

        from esptool import main as esptool_main

        _emit_progress(progress, 0.15, f"Preparing bootloader on {flash_port}...")
        journal.event("prepare_esptool", flash_port=flash_port, offset=hex(APP_OFFSET), baud=115200)

        args = [
            "--chip", "esp32s3",
            "--port", flash_port,
            "--baud", "115200",
            "--before", "default_reset",
            "--after", "hard_reset",
            "write_flash",
            "--no-compress",
            "--flash_mode", "keep",
            "--flash_freq", "keep",
            "--flash_size", "keep",
            hex(APP_OFFSET), str(firmware),
        ]

        _emit_progress(progress, 0.25, f"Writing firmware on {flash_port}...")
        journal.event("write_start", flash_port=flash_port)
        try:
            _run_esptool(esptool_main, args)
        except Exception as exc:
            if _STUB_MISSING_MARKER not in str(exc):
                error = _classify_write_error(exc, log_path=journal.path)
                journal.event("write_failed", level=logging.ERROR, code=error.code, error=error.detail)
                raise error from exc

            used_rom_fallback = True
            log.warning("esptool flasher stub data unavailable; retrying via ROM bootloader")
            journal.event("stub_missing", level=logging.WARNING, error=str(exc))
            _emit_progress(progress, 0.30, "Flasher stub unavailable. Retrying with ROM bootloader...")

            fallback_args = list(args)
            command_index = fallback_args.index("write_flash")
            fallback_args.insert(command_index, "--no-stub")
            journal.event("rom_fallback_start")
            try:
                _run_esptool(esptool_main, fallback_args)
            except Exception as retry_exc:
                error = _classify_write_error(retry_exc, log_path=journal.path)
                journal.event("rom_fallback_failed", level=logging.ERROR, code=error.code, error=error.detail)
                raise error from retry_exc

        elapsed = max(0.0, time.monotonic() - started)
        journal.event("write_complete", elapsed_s=round(elapsed, 3), rom_fallback=used_rom_fallback)
        _emit_progress(progress, 0.82, "Firmware written. Waiting for USB reset...")
        time.sleep(2.0)
        _emit_progress(progress, 0.86, "Device reset complete. Reconnecting...")
        journal.event("reset_complete")

        return FirmwareFlashResult(
            port=flash_port,
            firmware_path=str(firmware),
            elapsed_seconds=elapsed,
            log_path=journal.path,
            used_rom_fallback=used_rom_fallback,
        )
    except FirmwareUpdateError:
        raise
    except Exception as exc:
        error = _classify_write_error(exc, log_path=journal.path)
        journal.event("unexpected_failure", level=logging.ERROR, code=error.code, error=error.detail)
        raise error from exc
    finally:
        journal.close()
