"""GitHub Release firmware discovery and download support for VuNMix Desktop."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional


log = logging.getLogger(__name__)

REPOSITORY = "cuminhbecube/VuNMix"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases"
RELEASE_DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
USER_AGENT = "VuNMix-Firmware-Updater/1.0"
FIRMWARE_CACHE_DIR = pathlib.Path(
    os.environ.get(
        "LOCALAPPDATA",
        os.path.join(os.path.expanduser("~"), "AppData", "Local"),
    )
) / "VuNMix" / "firmware"

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_FIRMWARE_RE = re.compile(r"^VuNMix-Firmware-(\d+\.\d+\.\d+)\.bin$")


class FirmwareReleaseError(RuntimeError):
    """Raised when release metadata or a firmware download is not usable."""


@dataclass(frozen=True)
class FirmwareReleaseInfo:
    version: str
    tag: str
    release_url: str
    firmware_name: str
    firmware_url: str
    checksums_url: str


def version_tuple(value: str) -> Optional[tuple[int, int, int]]:
    match = _SEMVER_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def normalized_version(value: str) -> Optional[str]:
    parts = version_tuple(value)
    if parts is None:
        return None
    return ".".join(str(part) for part in parts)


def should_auto_update_firmware(
    firmware_version: str,
    desktop_version: str,
    enabled: bool = True,
) -> bool:
    """Only auto-upgrade older firmware to the exact Desktop App version."""
    if not enabled:
        return False
    firmware = version_tuple(firmware_version)
    desktop = version_tuple(desktop_version)
    if firmware is None or desktop is None:
        return False
    return firmware < desktop


def _parse_sha256sums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        parts = raw_line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts
        name = name.lstrip("*").strip()
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) and name:
            checksums[name] = digest.lower()
    return checksums


class FirmwareReleaseClient:
    """Discover stable VuNMix firmware releases and download verified images."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def _request(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FirmwareReleaseError("Release not found.") from exc
            raise FirmwareReleaseError(
                f"GitHub returned HTTP {exc.code} while checking firmware."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FirmwareReleaseError(
                f"Network error while checking firmware releases: {exc}"
            ) from exc

    def _request_json(self, url: str):
        try:
            return json.loads(self._request(url).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FirmwareReleaseError(
                "GitHub returned invalid firmware release metadata."
            ) from exc

    @staticmethod
    def _asset_url(release: dict, name: str) -> Optional[str]:
        for asset in release.get("assets", []):
            if asset.get("name") != name:
                continue
            url = str(asset.get("browser_download_url") or "")
            if url.startswith(RELEASE_DOWNLOAD_PREFIX):
                return url
        return None

    def release_to_info(self, release: dict) -> Optional[FirmwareReleaseInfo]:
        if release.get("draft") or release.get("prerelease"):
            return None

        tag = str(release.get("tag_name") or "").strip()
        version = normalized_version(tag)
        if version is None:
            return None

        firmware_name = f"VuNMix-Firmware-{version}.bin"
        if not _FIRMWARE_RE.fullmatch(firmware_name):
            return None

        firmware_url = self._asset_url(release, firmware_name)
        checksums_url = self._asset_url(release, "SHA256SUMS.txt")
        if not firmware_url or not checksums_url:
            return None

        return FirmwareReleaseInfo(
            version=version,
            tag=tag or f"v{version}",
            release_url=str(release.get("html_url") or ""),
            firmware_name=firmware_name,
            firmware_url=firmware_url,
            checksums_url=checksums_url,
        )

    def list_releases(self, limit: int = 20) -> list[FirmwareReleaseInfo]:
        limit = max(1, min(100, int(limit)))
        payload = self._request_json(f"{RELEASES_API}?per_page={limit}")
        if not isinstance(payload, list):
            raise FirmwareReleaseError("GitHub release list has an invalid format.")

        releases = []
        for release in payload:
            if not isinstance(release, dict):
                continue
            info = self.release_to_info(release)
            if info is not None:
                releases.append(info)

        releases.sort(
            key=lambda item: version_tuple(item.version) or (0, 0, 0),
            reverse=True,
        )
        return releases

    def get_version(self, version: str) -> Optional[FirmwareReleaseInfo]:
        normalized = normalized_version(version)
        if normalized is None:
            return None

        for tag in (f"v{normalized}", normalized):
            try:
                payload = self._request_json(
                    f"{RELEASES_API}/tags/{tag}"
                )
            except FirmwareReleaseError as exc:
                if str(exc) == "Release not found.":
                    continue
                raise
            if isinstance(payload, dict):
                info = self.release_to_info(payload)
                if info is not None and info.version == normalized:
                    return info
        return None

    def _expected_hash(self, info: FirmwareReleaseInfo) -> str:
        try:
            text = self._request(info.checksums_url).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FirmwareReleaseError(
                "Release checksum file is not valid UTF-8."
            ) from exc

        digest = _parse_sha256sums(text).get(info.firmware_name)
        if not digest:
            raise FirmwareReleaseError(
                f"SHA256SUMS.txt does not contain {info.firmware_name}."
            )
        return digest

    def download(
        self,
        info: FirmwareReleaseInfo,
        progress: Optional[Callable[[float, str], None]] = None,
    ) -> pathlib.Path:
        expected_hash = self._expected_hash(info)

        FIRMWARE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        final_path = FIRMWARE_CACHE_DIR / info.firmware_name
        temp_path = final_path.with_suffix(final_path.suffix + ".part")

        request = urllib.request.Request(
            info.firmware_url,
            headers={"User-Agent": USER_AGENT},
        )
        hasher = hashlib.sha256()
        downloaded = 0

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                total = int(response.headers.get("Content-Length") or 0)
                with open(temp_path, "wb") as handle:
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if progress:
                            fraction = (
                                min(0.98, downloaded / total)
                                if total > 0
                                else 0.5
                            )
                            progress(
                                fraction,
                                f"Downloading firmware {info.tag}...",
                            )
                    handle.flush()
                    os.fsync(handle.fileno())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise FirmwareReleaseError(
                f"Failed to download {info.firmware_name}: {exc}"
            ) from exc

        actual_hash = hasher.hexdigest().lower()
        if actual_hash != expected_hash.lower():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise FirmwareReleaseError(
                "Downloaded firmware failed SHA-256 verification."
            )

        os.replace(temp_path, final_path)

        # Validate the downloaded image before exposing it to the flash path.
        from firmware_updater import validate_firmware

        try:
            validate_firmware(str(final_path))
        except Exception:
            try:
                final_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        if progress:
            progress(1.0, f"Firmware {info.tag} verified.")
        return final_path
