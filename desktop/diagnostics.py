"""VuNMix logging and diagnostic helpers.

Runtime diagnostics live under %LOCALAPPDATA%/VuNMix so installed builds can
always write logs without requiring administrator privileges.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Mapping

from build_info import APP_VERSION, BUILD_DATE, GIT_SHA, PROTOCOL_VERSION
from config import CONFIG_DIR

LOG_DIR = os.path.join(CONFIG_DIR, "logs")
UPDATE_LOG_DIR = os.path.join(LOG_DIR, "firmware-updates")
MAIN_LOG_FILE = os.path.join(LOG_DIR, "vunmix.log")


def ensure_log_dirs() -> None:
    os.makedirs(UPDATE_LOG_DIR, exist_ok=True)


def configure_logging(debug: bool = False) -> str:
    """Configure process-wide rotating logging and return the main log path."""
    ensure_log_dirs()
    level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s [%(threadName)s] [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = RotatingFileHandler(
        MAIN_LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=4,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    import sys

    if sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    logging.getLogger("comtypes").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    return MAIN_LOG_FILE


def _safe_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


class FirmwareUpdateJournal:
    """One dedicated log file for one firmware update attempt."""

    def __init__(self, preferred_port: str, firmware_path: str):
        ensure_log_dirs()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"firmware-update-{stamp}-{os.getpid()}.log"
        self.path = os.path.join(UPDATE_LOG_DIR, filename)
        self.started = time.monotonic()
        self._logger = logging.getLogger(f"firmware.update.{stamp}.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = True
        self._handler = logging.FileHandler(self.path, encoding="utf-8")
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        self._logger.addHandler(self._handler)
        self.event(
            "start",
            preferred_port=preferred_port,
            firmware=str(pathlib.Path(firmware_path).expanduser()),
            app_version=APP_VERSION,
            protocol=PROTOCOL_VERSION,
            git_sha=GIT_SHA,
        )

    @property
    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    def event(self, phase: str, *, level: int = logging.INFO, **fields: Any) -> None:
        payload = {
            "phase": phase,
            "elapsed_s": round(self.elapsed, 3),
            **{key: _safe_value(value) for key, value in fields.items()},
        }
        self._logger.log(level, json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def close(self) -> None:
        try:
            self._handler.flush()
        finally:
            self._logger.removeHandler(self._handler)
            self._handler.close()


def build_diagnostic_report(
    serial_health: Mapping[str, Any],
    *,
    firmware_version: str = "unknown",
    firmware_protocol: Any = "unknown",
    firmware_updating: bool = False,
    last_update_log: str = "",
) -> str:
    """Create a clipboard-friendly plain-text diagnostic snapshot."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "VuNMix Diagnostic Report",
        f"Generated UTC: {now}",
        f"Desktop version: {APP_VERSION}",
        f"Desktop protocol: {PROTOCOL_VERSION}",
        f"Desktop git SHA: {GIT_SHA}",
        f"Desktop build date: {BUILD_DATE}",
        f"Firmware version: {firmware_version or 'unknown'}",
        f"Firmware protocol: {firmware_protocol}",
        f"Firmware updating: {_safe_value(firmware_updating)}",
        f"Last update log: {last_update_log or '-'}",
        "",
        "Serial health:",
    ]
    for key in sorted(serial_health):
        lines.append(f"  {key}: {_safe_value(serial_health[key])}")
    lines.extend(["", f"Main log: {MAIN_LOG_FILE}", f"Log folder: {LOG_DIR}"])
    return "\n".join(lines)


def open_log_folder() -> None:
    ensure_log_dirs()
    if os.name == "nt":
        os.startfile(LOG_DIR)  # type: ignore[attr-defined]
        return
    raise OSError(f"Open the log folder manually: {LOG_DIR}")
