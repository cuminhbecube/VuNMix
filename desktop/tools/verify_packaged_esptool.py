"""Verify critical PyInstaller package data for VuNMix."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys


def _normalize_version(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("v") or value.startswith("ci-") or value.startswith("dev-"):
        return value
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?", value):
        return f"v{value}"
    return value


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


def _verify_build_metadata(root: pathlib.Path, files: list[pathlib.Path]) -> None:
    metadata_files = [path for path in files if path.name == "build-metadata.json"]
    if len(metadata_files) != 1:
        raise SystemExit(
            "Packaged app must contain exactly one build-metadata.json; "
            f"found {len(metadata_files)}."
        )

    try:
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise SystemExit(f"Invalid packaged build metadata: {exc}") from exc

    for key in ("version", "git_sha", "build_date", "protocol_version"):
        if key not in metadata or metadata[key] in (None, ""):
            raise SystemExit(f"Packaged build metadata is missing '{key}'.")

    expected_version = _normalize_version(
        os.environ.get("VUNMIX_VERSION") or os.environ.get("VERSION") or ""
    )
    if expected_version and metadata["version"] != expected_version:
        raise SystemExit(
            "Packaged desktop version mismatch: "
            f"expected {expected_version}, got {metadata['version']}"
        )

    expected_sha = (
        os.environ.get("VUNMIX_GIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or ""
    ).strip()
    if expected_sha and metadata["git_sha"] != expected_sha:
        raise SystemExit(
            "Packaged desktop git SHA mismatch: "
            f"expected {expected_sha}, got {metadata['git_sha']}"
        )

    print(
        "VuNMix build metadata: "
        f"version={metadata['version']} "
        f"protocol={metadata['protocol_version']} "
        f"git={metadata['git_sha']} "
        f"built={metadata['build_date']}"
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

    _verify_build_metadata(root, files)

    print(f"Packaged esptool files: {len(esptool_files)}")
    print("ESP32-S3 flasher-stub files:")
    for path in stub_files:
        print(f"  - {path.relative_to(root)}")


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("dist/VuNMix")
    verify(target)
