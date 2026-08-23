"""Runtime build/version metadata for VuNMix Desktop."""

from __future__ import annotations

import os
import re

from protocol import PROTOCOL_VERSION


def normalize_version(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "dev"
    if value.startswith("v") or value.startswith("ci-") or value.startswith("dev-"):
        return value
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?", value):
        return f"v{value}"
    return value


try:
    from _build_metadata import APP_VERSION, BUILD_DATE, GIT_SHA
except ImportError:
    APP_VERSION = normalize_version(
        os.environ.get("VUNMIX_VERSION") or os.environ.get("VERSION") or "dev"
    )
    GIT_SHA = (
        os.environ.get("VUNMIX_GIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or "unknown"
    ).strip()
    BUILD_DATE = (os.environ.get("VUNMIX_BUILD_DATE") or "development").strip()


SHORT_GIT_SHA = GIT_SHA[:12] if GIT_SHA and GIT_SHA != "unknown" else "unknown"


def build_summary() -> str:
    return (
        f"VuNMix {APP_VERSION} | protocol {PROTOCOL_VERSION} | "
        f"git {SHORT_GIT_SHA} | built {BUILD_DATE}"
    )
