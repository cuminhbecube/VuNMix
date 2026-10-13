#!/usr/bin/env python3
"""Fail closed if a release silently drops published VuNMix features.

This inventory intentionally checks code-level commitments, not GUI screenshots
or hardware behavior. Hardware testing remains a separate release gate.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_CLOCKS = (
    "Neon Digital", "Minimal", "Flip Cards", "Analog",
    "Orbit", "Binary", "Terminal", "Retro LCD",
    "Nixie", "Word Clock", "Pixel Art", "Dot Matrix",
    "ClockClock", "Barcode", "Polygon", "Math Clock",
)
REQUIRED_FILES = (
    "desktop/app_controller.py",
    "desktop/audio_service.py",
    "desktop/app_updater.py",
    "desktop/firmware_updater.py",
    "desktop/firmware_release.py",
    "desktop/connection_ui.py",
    "desktop/obs_service.py",
    "desktop/media_service.py",
    "desktop/audio_automation_controller.py",
    "src/ui/modules/DisplayClockStyles.inc",
    "src/ui/modules/DisplayClockArt.inc",
    "src/ui/modules/DisplayClockArtDigits.inc",
    "src/ui/modules/DisplayClockArtWords.inc",
    "src/ui/modules/DisplayClockArtHands.inc",
    "src/ui/modules/DisplayClockArtHelpers.inc",
    "desktop/tests/test_clock_firmware.py",
    "desktop/tests/test_audio_memory_regression.py",
)
REQUIRED_UI_TOKENS = (
    "DisplayClockStyles.inc", "DisplayClockArt.inc", "DisplayClock.inc",
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def clock_styles() -> list[str]:
    tree = ast.parse((ROOT / "desktop/protocol.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CLOCK_STYLE_NAMES"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("Protocol CLOCK_STYLE_NAMES was removed")


def validate() -> None:
    missing = [file for file in REQUIRED_FILES if not (ROOT / file).is_file()]
    require(not missing, f"Required feature source files missing: {missing}")
    styles = clock_styles()
    require(tuple(styles) == EXPECTED_CLOCKS,
            f"Clock inventory changed: expected 16 published styles, got {styles!r}")
    protocol = (ROOT / "desktop/protocol.py").read_text(encoding="utf-8")
    for name in ("MODE_OUTPUT", "MODE_INPUT", "MODE_APPLICATION", "MODE_GAME",
                 "MODE_HEALTH", "CLOCK_STYLE_NAMES"):
        require(name in protocol, f"Protocol mode or clock API removed: {name}")
    firmware = (ROOT / "src/ui/DisplayScreens.inc").read_text(encoding="utf-8")
    for name in REQUIRED_UI_TOKENS:
        require(name in firmware, f"Firmware renderer no longer includes {name}")
    source = (ROOT / "src/ui/modules/DisplayClock.inc").read_text(encoding="utf-8")
    require("BuildArtClock(clockStyle)" in source,
            "Firmware art clock renderer was disconnected")
    require("BuildExtraClock(clockStyle)" in source,
            "Firmware style renderer was disconnected")
    gui = (ROOT / "desktop/gui.py").read_text(encoding="utf-8")
    require("CLOCK_STYLE_NAMES" in gui, "Desktop clock selector missing")
    require("self._clock_style_var" in gui, "Desktop clock binding missing")
    source = (ROOT / "desktop/controller_workers.py").read_text(encoding="utf-8")
    monitor = (ROOT / "desktop/resource_monitor.py").read_text(encoding="utf-8")
    require("ProcessResourceTracker" in source and "VuNMix process memory:" in monitor,
            "Long-running bounded RSS memory telemetry was removed")
    print(f"Feature contracts PASS: {len(styles)} clock styles, "
          f"{len(REQUIRED_FILES)} source components, audio/firmware/update/health")


if __name__ == "__main__":
    try:
        validate()
    except (AssertionError, OSError, ValueError, SyntaxError) as exc:
        print(f"ERROR: release feature contract failed: {exc}", file=sys.stderr)
        sys.exit(1)
