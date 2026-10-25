"""Require all eight native device previews in the actual Windows package."""
from pathlib import Path
import sys

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))

from device_theme_preview import THEME_ASSET_NAMES


def verify(package_root: Path) -> None:
    root = package_root.resolve()
    directories = [root / "assets/device_themes", root / "_internal/assets/device_themes"]
    bundled = [directory for directory in directories if directory.is_dir()]
    if len(bundled) != 1:
        raise SystemExit("Expected exactly one bundled assets/device_themes directory")
    source = DESKTOP / "assets/device_themes"
    names = [name + ".png" for name in THEME_ASSET_NAMES] + ["manifest.json"]
    for name in names:
        actual = bundled[0] / name
        if not actual.is_file() or actual.read_bytes() != (source / name).read_bytes():
            raise SystemExit(f"Missing or stale packaged device preview: {name}")
    print("Packaged device themes match all eight production previews and manifest.")


if __name__ == "__main__":
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/VuNMix"))
