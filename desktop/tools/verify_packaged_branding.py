"""Verify bundled logo assets match the source PNG and generated Windows ICO.

Run after PyInstaller, before packaging: python tools/verify_packaged_branding.py
dist/VuNMix. Both the current _internal/assets layout and the older assets layout
are supported. This checks bundled files; it does not inspect PE icon resources.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


def verify(package_root: Path) -> None:
    root = package_root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Packaged app directory does not exist: {root}")

    source_assets = Path(__file__).resolve().parents[1] / "assets"
    allowed_directories = {root / "assets", root / "_internal" / "assets"}
    verified = []

    for name in ("logo.png", "icon.ico"):
        source = source_assets / name
        if not source.is_file():
            raise SystemExit(
                f"Source branding asset is missing: {source}. "
                "Build VuNMix.spec first to generate assets/icon.ico."
            )

        matches = sorted(path for path in root.rglob(f"assets/{name}")
                         if path.is_file())
        if len(matches) != 1:
            locations = ", ".join(str(path.relative_to(root)) for path in matches)
            raise SystemExit(
                f"Packaged app must contain exactly one assets/{name}; "
                f"found {len(matches)} ({locations or 'none'})."
            )

        packaged = matches[0]
        if packaged.parent not in allowed_directories:
            raise SystemExit(
                f"Packaged branding asset is in an unsupported location: "
                f"{packaged.relative_to(root)}. Expected assets/{name} or "
                f"_internal/assets/{name}."
            )

        try:
            expected = source.read_bytes()
            actual = packaged.read_bytes()
        except OSError as exc:
            raise SystemExit(f"Could not read branding asset {name}: {exc}") from exc

        expected_hash = hashlib.sha256(expected).hexdigest()
        if actual != expected:
            actual_hash = hashlib.sha256(actual).hexdigest()
            raise SystemExit(
                f"Packaged branding asset is stale or modified: "
                f"{packaged.relative_to(root)}. "
                f"Expected source SHA-256 {expected_hash}, got {actual_hash}. "
                "Rebuild the application from the current logo.png and generated icon.ico."
            )
        verified.append((packaged, expected_hash))

    if verified[0][0].parent != verified[1][0].parent:
        raise SystemExit(
            "Packaged logo.png and icon.ico must share the same assets directory; "
            "they are split between the legacy and _internal layouts."
        )

    print("Packaged branding assets match source:")
    for path, digest in verified:
        print(f"  {path.relative_to(root)}  SHA-256 {digest}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/VuNMix")
    verify(target)
