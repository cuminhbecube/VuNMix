#!/usr/bin/env python3
"""Generate VuNMix latest.json from already-built release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from protocol import PROTOCOL_VERSION


VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+.][0-9A-Za-z.-]+)?$")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_record(path: pathlib.Path, repository: str, tag: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    name = path.name
    url = (
        f"https://github.com/{repository}/releases/download/"
        f"{quote(tag, safe='')}/{quote(name, safe='') }"
    )
    return {
        "name": name,
        "url": url,
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def normalize_version(value: str) -> str:
    value = str(value or "").strip()
    if VERSION_RE.fullmatch(value):
        return value if value.startswith("v") else f"v{value}"
    # CI manifests use a synthetic semver so the same strict parser can test
    # them without ever being treated as a published release.
    if value.startswith("ci-"):
        return "v0.0.0-ci." + re.sub(r"[^0-9A-Za-z.-]", "-", value[3:])
    raise ValueError(f"Unsupported manifest version: {value}")


def build_manifest(args) -> dict:
    repository = args.repository.strip()
    if repository.count("/") != 1:
        raise ValueError("repository must be owner/name")
    tag = args.tag.strip()
    if not tag:
        raise ValueError("tag is required")
    return {
        "schema": 1,
        "version": normalize_version(args.version),
        "tag": tag,
        "protocol": PROTOCOL_VERSION,
        "minimum_desktop_version": args.minimum_desktop_version,
        "minimum_firmware_version": args.minimum_firmware_version,
        "release_url": f"https://github.com/{repository}/releases/tag/{quote(tag, safe='')}",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "assets": {
            "firmware": asset_record(args.firmware, repository, tag),
            "windows_setup": asset_record(args.windows_setup, repository, tag),
            "windows_portable": asset_record(args.windows_portable, repository, tag),
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--firmware", required=True, type=pathlib.Path)
    parser.add_argument("--windows-setup", required=True, type=pathlib.Path)
    parser.add_argument("--windows-portable", required=True, type=pathlib.Path)
    parser.add_argument("--minimum-desktop-version", default="v0.5.0")
    parser.add_argument("--minimum-firmware-version", default="v0.5.0")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    manifest = build_manifest(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
