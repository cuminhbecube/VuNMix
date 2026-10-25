#!/usr/bin/env python3
"""Compile production Display.cpp against pinned LVGL; verify original clocks.

The release gate is ``python tools/native_theme_regression.py --download --verify``.
No test substitutes LVGL drawing calls. Cached vendor/build files live outside
the checkout. Clock goldens can only be generated from the pinned git commit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "desktop/tests/native_theme"
GOLDEN = FIXTURES / "original_clocks.json"
BASELINE = "4ee00c424cf34e56eec26a383689197b2b47b4e1"
LVGL_VERSION = "8.3.11"
LVGL_URL = "https://codeload.github.com/lvgl/lvgl/tar.gz/refs/tags/v8.3.11"
LVGL_ARCHIVE_SHA256 = "83b7325a4b78cbb19a39f3ac75346c8086926d7faeab5ff2d825c20da0bbdb46"
LVGL_TREE_SHA256 = "576b9bf2b4c8ea5d53793dee90af6d35d2e422102f40101f790f791ebe52208b"
CACHE = Path(os.environ.get("VUNMIX_NATIVE_CACHE", Path(tempfile.gettempdir()) / "vunmix-native-theme"))
CLOCK_FILES = (
    "DisplayClock.inc", "DisplayClockStyles.inc", "DisplayClockArt.inc",
    "DisplayClockArtHelpers.inc", "DisplayClockArtDigits.inc",
    "DisplayClockArtWords.inc", "DisplayClockArtHands.inc",
)
FONT_FILES = tuple("src/" + name for name in (
    "lv_font_vn_10.c", "lv_font_vn_12.c", "lv_font_vn_14.c", "lv_font_vn_20.c",
    "lv_font_dseg_90_bpp1.c",
))
IMMUTABLE_FILES = tuple("src/ui/modules/" + name for name in CLOCK_FILES) + FONT_FILES
THEMES = (("classic", "Classic"), ("windows_dark", "Windows Dark"),
          ("studio", "Studio"), ("paper", "Paper"), ("orbit", "Orbit"),
          ("pixel", "Pixel"), ("blocks", "Blocks"), ("terminal", "Terminal"))
PREVIEWS = ROOT / "desktop/assets/device_themes"


def sha(path: Path, *, normalized_text: bool = False) -> str:
    data = path.read_bytes()
    if normalized_text:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 180) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Command failed: " + repr(command) + "\n" + result.stdout + result.stderr)
    return result.stdout


def toolchain_available() -> bool:
    return all(shutil.which(tool) for tool in ("gcc", "g++", "ar"))


def vendor_tree_sha(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [p for p in (root / "src").rglob("*") if p.is_file() and p.suffix in (".c", ".h")]
    paths += [root / "lvgl.h", root / "LICENCE.txt"]
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def available_lvgl() -> Path | None:
    explicit = os.environ.get("VUNMIX_LVGL_DIR")
    candidate = Path(explicit) if explicit else CACHE / ("lvgl-" + LVGL_VERSION)
    return candidate if (candidate / "lvgl.h").is_file() else None


def obtain_lvgl(download: bool = False) -> Path:
    candidate = available_lvgl()
    if candidate is None:
        CACHE.mkdir(parents=True, exist_ok=True)
        archive = Path(os.environ.get("VUNMIX_LVGL_ARCHIVE", CACHE / "lvgl-v8.3.11.tar.gz"))
        if not archive.is_file():
            if not download:
                raise RuntimeError("Pinned LVGL unavailable; pass --download or VUNMIX_LVGL_DIR")
            partial = CACHE / "lvgl-download.tmp"
            try:
                with urllib.request.urlopen(LVGL_URL, timeout=60) as response, partial.open("wb") as output:
                    shutil.copyfileobj(response, output)
                if sha(partial) != LVGL_ARCHIVE_SHA256:
                    raise RuntimeError("LVGL archive SHA-256 mismatch")
                archive = CACHE / "lvgl-v8.3.11.tar.gz"
                partial.replace(archive)
            finally:
                partial.unlink(missing_ok=True)
        if sha(archive) != LVGL_ARCHIVE_SHA256:
            raise RuntimeError("Pinned LVGL archive SHA-256 mismatch")
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                destination = (CACHE / member.name).resolve()
                if CACHE.resolve() not in destination.parents or member.issym() or member.islnk():
                    raise RuntimeError("Unexpected path/link in LVGL source archive")
            bundle.extractall(CACHE, filter="data")
        candidate = CACHE / ("lvgl-" + LVGL_VERSION)
    if vendor_tree_sha(candidate) != LVGL_TREE_SHA256:
        raise RuntimeError("LVGL source tree differs from the pinned 8.3.11 archive")
    return candidate


def baseline_snapshot() -> Path:
    """Read only the immutable git tree; never snapshot today's working copy."""
    destination = CACHE / ("baseline-" + BASELINE)
    listed = run(["git", "ls-tree", "-r", "--name-only", BASELINE, "src"], cwd=ROOT).splitlines()
    selected = [name for name in listed if name in FONT_FILES or name.endswith((".h", ".inc"))
                or name == "src/Display.cpp"]
    if not selected:
        raise RuntimeError("Pinned baseline tree is unavailable")
    for name in selected:
        result = subprocess.run(["git", "show", BASELINE + ":" + name], cwd=ROOT,
                                capture_output=True, check=True)
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.stdout)
    return destination


def build(source: Path, lvgl: Path, *, baseline: bool = False) -> Path:
    if not toolchain_available():
        raise RuntimeError("Native release gate requires gcc, g++ and ar")
    source_inputs = [p for p in (source / "src").rglob("*")
                     if p.is_file() and p.suffix in (".h", ".inc", ".c", ".cpp")]
    fixture_inputs = [p for p in FIXTURES.rglob("*") if p.is_file() and p.suffix in (".h", ".cpp")]
    fingerprint = hashlib.sha256()
    for path in sorted(source_inputs + fixture_inputs):
        fingerprint.update(str(path).encode() + b"\0" + path.read_bytes())
    fingerprint.update((str(lvgl) + LVGL_TREE_SHA256 + str(baseline)
                        + run(["g++", "--version"]).splitlines()[0]).encode())
    directory = CACHE / ("build-" + fingerprint.hexdigest()[:20])
    executable = directory / ("theme-regression.exe" if os.name == "nt" else "theme-regression")
    if executable.is_file():
        return executable
    include = directory / "include"
    include.mkdir(parents=True, exist_ok=True)
    (include / "lv_conf.h").write_bytes((source / "src/lv_conf.h").read_bytes())
    flags = ["-O2", "-ffunction-sections", "-fdata-sections",
             "-DLV_CONF_INCLUDE_SIMPLE=1", "-DLV_LVGL_H_INCLUDE_SIMPLE=1",
             "-DVUNMIX_HAS_DEVICE_THEMES=" + ("0" if baseline else "1"),
             "-I" + str(FIXTURES / "include"), "-I" + str(include),
             "-I" + str(lvgl), "-I" + str(source / "src")]
    sources = sorted((lvgl / "src").rglob("*.c")) + [source / name for name in FONT_FILES]
    if not baseline:
        sources += [source / "src/ui/ThemeLogo.c", source / "src/ui/ThemeRenderer.cpp"]
    sources += [FIXTURES / "theme_harness.cpp"]
    commands = []

    def compile_one(item: tuple[int, Path]) -> Path:
        index, path = item
        obj = directory / (str(index) + ".o")
        cpp = path.suffix == ".cpp"
        observer = ["-Dlv_draw_label=native_draw_label"] if path.name == "ThemeRenderer.cpp" else []
        command = ["g++" if cpp else "gcc", "-std=" + ("c++17" if cpp else "c99"),
                   *flags, *observer, "-c", str(path), "-o", str(obj)]
        commands.append({"file": str(path), "arguments": command})
        run(command)
        return obj

    with ThreadPoolExecutor(max_workers=4) as pool:
        objects = list(pool.map(compile_one, enumerate(sources)))
    command = ["g++", "-Wl,--gc-sections", *map(str, objects), "-lm", "-o", str(executable)]
    run(command)
    (directory / "compile_commands.json").write_text(json.dumps(commands, indent=2) + "\n")
    return executable


def verify_sources() -> dict:
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if expected.get("baseline_commit") != BASELINE:
        raise AssertionError("Original clock baseline commit changed")
    for name, digest in expected["immutable_sources_sha256_lf"].items():
        if sha(ROOT / name, normalized_text=True) != digest:
            raise AssertionError("Original clock/font source changed: " + name)
    return expected


def invoke_harness(executable: Path, mode: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    stdout = run([str(executable), mode, str(output)], timeout=180)
    return json.loads(stdout)


def frame_hashes(directory: Path) -> dict[str, str]:
    return {p.stem: sha(p) for p in sorted(directory.glob("clock-*.rgb565"))}


def rgb565_pixels(raw: bytes) -> bytes:
    if len(raw) != 320 * 240 * 2:
        raise AssertionError("Native framebuffer is not exactly 320x240 RGB565")
    rgb = bytearray()
    for (pixel,) in struct.iter_unpack("<H", raw):
        # The exact integer conversion implemented by LVGL lv_color_to32.
        rgb.extend(((((pixel >> 11) & 31) * 263 + 7) >> 5,
                    (((pixel >> 5) & 63) * 259 + 3) >> 6,
                    ((pixel & 31) * 263 + 7) >> 5))
    return bytes(rgb)


def write_png(path: Path, pixels: bytes) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    scanlines = b"".join(b"\0" + pixels[y * 960:(y + 1) * 960] for y in range(240))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 240, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(scanlines, 9)) + chunk(b"IEND", b""))


def export_capture_images(directory: Path) -> None:
    for path in directory.rglob("*.rgb565"):
        pixels = rgb565_pixels(path.read_bytes())
        write_png(path.with_suffix(".png"), pixels)
        path.with_suffix(".ppm").write_bytes(b"P6\n320 240\n255\n" + pixels)


def read_png_pixels(path: Path) -> bytes:
    """Decode the shipped RGB8 preview without requiring Pillow on firmware CI."""
    encoded = path.read_bytes()
    if encoded[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("Invalid PNG signature: " + str(path))
    position, payload, header = 8, bytearray(), None
    while position < len(encoded):
        length = struct.unpack_from(">I", encoded, position)[0]
        kind = encoded[position + 4:position + 8]
        data = encoded[position + 8:position + 8 + length]
        crc = struct.unpack_from(">I", encoded, position + 8 + length)[0]
        if zlib.crc32(kind + data) != crc:
            raise AssertionError("Invalid PNG CRC: " + str(path))
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            payload.extend(data)
        position += length + 12
        if kind == b"IEND":
            break
    if header != (320, 240, 8, 2, 0, 0, 0):
        raise AssertionError("Preview must be 320x240 RGB8, noninterlaced: " + str(path))
    scanlines = zlib.decompress(payload)
    if len(scanlines) != 240 * 961:
        raise AssertionError("Unexpected PNG scanline size")
    pixels = bytearray()
    previous = bytearray(960)
    for y in range(240):
        mode = scanlines[y * 961]
        row = bytearray(scanlines[y * 961 + 1:(y + 1) * 961])
        if mode > 4:
            raise AssertionError("Invalid PNG scanline filter")
        for x in range(960):
            left = row[x - 3] if x >= 3 else 0
            above = previous[x]
            corner = previous[x - 3] if x >= 3 else 0
            if mode == 1:
                predictor = left
            elif mode == 2:
                predictor = above
            elif mode == 3:
                predictor = (left + above) // 2
            elif mode == 4:
                p = left + above - corner
                distances = (abs(p - left), abs(p - above), abs(p - corner))
                predictor = (left, above, corner)[distances.index(min(distances))]
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        pixels.extend(row)
        previous = row
    return bytes(pixels)


def rendering_sources() -> dict[str, str]:
    paths = [p for p in (ROOT / "src/ui").rglob("*") if p.is_file() and p.suffix in (".h", ".inc", ".c", ".cpp")]
    paths += [ROOT / name for name in FONT_FILES]
    paths += [ROOT / "src" / name for name in ("Display.cpp", "Display.h", "Config.h", "Enums.h", "Structs.h", "lv_conf.h")]
    return {p.relative_to(ROOT).as_posix(): sha(p, normalized_text=True) for p in sorted(paths)}


def export_previews(executable: Path, destination: Path, output: Path) -> dict:
    result = invoke_harness(executable, "lifecycle", output)
    destination.mkdir(parents=True, exist_ok=True)
    themes = []
    for index, (slug, name) in enumerate(THEMES):
        raw_path = output / f"theme-{index}-output.rgb565"
        rgb = rgb565_pixels(raw_path.read_bytes())
        image = destination / (slug + ".png")
        write_png(image, rgb)
        if read_png_pixels(image) != rgb:
            raise AssertionError("PNG writer did not preserve native pixels")
        themes.append({"id": index, "name": name, "file": image.name,
                       "sha256": sha(image), "rgb565_sha256": sha(raw_path)})
    manifest = {"schema": 1, "resolution": [320, 240], "scene": "output",
                "renderer": "LVGL 8.3.11", "themes": themes,
                "provenance": "Actual production Display.cpp/ThemeRenderer.cpp; native RGB565 memory flush",
                "fixture": {"name": "Realtek USB Audio", "volume": 68, "is_default": True,
                            "is_muted": False, "pc_connected": True,
                            "current_peak": 36, "alternate_peak": 0},
                "lvgl_archive_sha256": LVGL_ARCHIVE_SHA256,
                "rendering_sources_sha256_lf": rendering_sources(), "native": result}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_previews(output: Path, previews: Path = PREVIEWS) -> int:
    manifest = json.loads((previews / "manifest.json").read_text(encoding="utf-8"))
    expected_catalog = [(index, name, slug + ".png") for index, (slug, name) in enumerate(THEMES)]
    actual_catalog = [(row["id"], row["name"], row["file"]) for row in manifest["themes"]]
    if actual_catalog != expected_catalog or manifest.get("resolution") != [320, 240]:
        raise AssertionError("Shipped device theme preview catalog changed")
    for index, row in enumerate(manifest["themes"]):
        image = previews / row["file"]
        raw = output / f"theme-{index}-output.rgb565"
        if read_png_pixels(image) != rgb565_pixels(raw.read_bytes()):
            raise AssertionError("Shipped preview pixels differ from production firmware: " + row["name"])
        if row["sha256"] != sha(image) or row.get("rgb565_sha256") != sha(raw):
            raise AssertionError("Shipped preview hashes are stale: " + row["name"])
    if manifest.get("rendering_sources_sha256_lf") != rendering_sources():
        raise AssertionError("Preview provenance is stale; regenerate from production renderer")
    return len(THEMES)


def generate_baseline(lvgl: Path) -> None:
    source = baseline_snapshot()
    executable = build(source, lvgl, baseline=True)
    with tempfile.TemporaryDirectory(prefix="vunmix-clock-baseline-") as temp:
        output = Path(temp)
        result = invoke_harness(executable, "clocks", output)
        expected = {
            "baseline_commit": BASELINE, "lvgl_version": LVGL_VERSION,
            "lvgl_archive_sha256": LVGL_ARCHIVE_SHA256, "lvgl_tree_sha256": LVGL_TREE_SHA256,
            "format": "320x240 RGB565 little-endian; native LVGL flush; no resampling",
            "moments": [[0, 0, 0], [10, 8, 36], [12, 34, 1], [23, 59, 59]],
            "immutable_sources_sha256_lf": {name: sha(source / name, normalized_text=True)
                                            for name in IMMUTABLE_FILES},
            "clock_frames_sha256": frame_hashes(output), "native": result,
        }
    if len(expected["clock_frames_sha256"]) != 64:
        raise AssertionError("Baseline must include all 16 original clocks at four times")
    GOLDEN.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print("Generated 64 clock goldens from immutable git commit " + BASELINE)


def verify_native(lvgl: Path, output: Path | None = None) -> dict:
    expected = verify_sources()
    executable = build(ROOT, lvgl)
    with tempfile.TemporaryDirectory(prefix="vunmix-theme-gate-") as temp:
        destination = output or Path(temp)
        clocks = invoke_harness(executable, "clocks", destination / "clocks")
        actual = frame_hashes(destination / "clocks")
        if actual != expected["clock_frames_sha256"]:
            differences = [key for key in sorted(set(actual) | set(expected["clock_frames_sha256"]))
                           if actual.get(key) != expected["clock_frames_sha256"].get(key)]
            raise AssertionError("Original native clock pixels changed: " + ", ".join(differences))
        lifecycle = invoke_harness(executable, "lifecycle", destination / "lifecycle")
        previews = verify_previews(destination / "lifecycle")
        result = {"clocks": clocks, "lifecycle": lifecycle,
                  "immutable_original_clock_frames": len(actual), "baseline_commit": BASELINE,
                  "shipped_previews_pixel_equal": previews}
        if output:
            export_capture_images(output)
            (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch SHA-256 pinned LVGL if missing")
    parser.add_argument("--verify", action="store_true", help="Fail closed on native/source regressions")
    parser.add_argument("--generate-baseline", action="store_true", help="Read only pinned 4ee00c4 git tree")
    parser.add_argument("--export-previews", type=Path, help="Export eight production Output PNGs and manifest")
    parser.add_argument("--output", type=Path, help="Retain raw captures and results outside source")
    args = parser.parse_args()
    if sum((args.verify, args.generate_baseline, args.export_previews is not None)) != 1:
        parser.error("Choose exactly one of --verify, --generate-baseline or --export-previews")
    lvgl = obtain_lvgl(args.download)
    if args.generate_baseline:
        generate_baseline(lvgl)
    elif args.export_previews:
        executable = build(ROOT, lvgl)
        with tempfile.TemporaryDirectory(prefix="vunmix-theme-previews-") as temp:
            output = args.output.resolve() if args.output else Path(temp)
            manifest = export_previews(executable, args.export_previews.resolve(), output)
            if args.output:
                export_capture_images(output)
            print(json.dumps({"preview_directory": str(args.export_previews.resolve()),
                              "native": manifest["native"], "previews": len(manifest["themes"])}, indent=2))
    else:
        result = verify_native(lvgl, args.output.resolve() if args.output else None)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print("Native theme gate FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
