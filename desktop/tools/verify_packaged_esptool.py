"""Verify that a PyInstaller VuNMix build contains esptool ESP32-S3 stub data."""

from __future__ import annotations

import pathlib
import sys


def _is_esptool_path(path: pathlib.Path) -> bool:
    return "esptool" in path.as_posix().lower()


def _is_esp32s3_stub(path: pathlib.Path) -> bool:
    text = path.as_posix().lower()
    name = path.name.lower()
    return (
        "stub_flasher" in text
        and ("esp32s3" in text or "32s3" in name)
        and path.is_file()
    )


def verify(package_root: pathlib.Path) -> None:
    root = package_root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Packaged app directory does not exist: {root}")

    files = [path for path in root.rglob("*") if path.is_file()]
    esptool_files = [path for path in files if _is_esptool_path(path)]
    stub_files = [path for path in files if _is_esp32s3_stub(path)]

    if not esptool_files:
        raise SystemExit(
            "PyInstaller output does not contain esptool package data. "
            "Check collect_all('esptool') in VuNMix.spec."
        )

    if not stub_files:
        stub_candidates = [
            path for path in esptool_files if "stub" in path.as_posix().lower()
        ]
        detail = "\n".join(f"  - {path.relative_to(root)}" for path in stub_candidates[:40])
        if not detail:
            detail = "  (no stub-related files found)"
        raise SystemExit(
            "ESP32-S3 esptool flasher-stub data is missing from the packaged app.\n"
            "Stub-related packaged files:\n"
            f"{detail}"
        )

    print(f"Packaged esptool files: {len(esptool_files)}")
    print("ESP32-S3 flasher-stub files:")
    for path in stub_files:
        print(f"  - {path.relative_to(root)}")


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("dist/VuNMix")
    verify(target)
