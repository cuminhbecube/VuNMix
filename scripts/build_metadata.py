"""PlatformIO pre-build hook for VuNMix release/build metadata."""

Import("env")

import datetime as _dt
import os
import pathlib
import re


def _normalize_version(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "dev"
    if value.startswith("v") or value.startswith("ci-") or value.startswith("dev-"):
        return value
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?", value):
        return f"v{value}"
    return value


def _cpp_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'\\"{escaped}\\"'


VERSION = _normalize_version(
    os.environ.get("VUNMIX_VERSION") or os.environ.get("VERSION") or "dev"
)
GIT_SHA = (
    os.environ.get("VUNMIX_GIT_SHA")
    or os.environ.get("GITHUB_SHA")
    or "unknown"
).strip()
BUILD_DATE = (
    os.environ.get("VUNMIX_BUILD_DATE")
    or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
).strip()

print(f"VuNMix firmware version: {VERSION}")
print(f"VuNMix firmware git SHA: {GIT_SHA}")
print(f"VuNMix firmware build date: {BUILD_DATE}")

env.Append(
    CPPDEFINES=[
        ("VUNMIX_VERSION", _cpp_string(VERSION)),
        ("VUNMIX_GIT_SHA", _cpp_string(GIT_SHA)),
        ("VUNMIX_BUILD_DATE", _cpp_string(BUILD_DATE)),
    ]
)


def _verify_firmware_metadata(target, source, env):
    firmware = pathlib.Path(env.subst("$BUILD_DIR")) / (
        env.subst("$PROGNAME") + ".bin"
    )
    if not firmware.is_file():
        raise RuntimeError(f"Firmware image missing for metadata verification: {firmware}")

    payload = firmware.read_bytes()
    expected = (VERSION, GIT_SHA, BUILD_DATE)
    missing = [value for value in expected if value.encode("utf-8") not in payload]
    if missing:
        raise RuntimeError(
            "Firmware build metadata was not embedded: " + ", ".join(missing)
        )

    print("VuNMix firmware metadata verified in firmware.bin")


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", _verify_firmware_metadata)
