"""VuNMix Update Center backend.

Release metadata is deliberately small and machine-readable. Every downloaded
artifact is accepted only after HTTPS origin validation, exact-size validation
(when supplied by the manifest) and SHA-256 verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from build_info import APP_VERSION
from config import CONFIG_DIR
from protocol import PROTOCOL_VERSION


MANIFEST_SCHEMA = 1
DEFAULT_MANIFEST_URL = (
    "https://github.com/cuminhbecube/VuNMix/releases/latest/download/latest.json"
)
UPDATE_DIR = os.path.join(CONFIG_DIR, "updates")
MAX_MANIFEST_BYTES = 512 * 1024
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
_ALLOWED_HOSTS = {"github.com", "api.github.com"}
_ALLOWED_HOST_SUFFIXES = (".githubusercontent.com", ".github.com")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+.]([0-9A-Za-z.-]+))?$")


class UpdateCenterError(RuntimeError):
    def __init__(self, code: str, message: str, *, detail: str = ""):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ReleaseManifest:
    schema: int
    version: str
    tag: str
    protocol: int
    minimum_desktop_version: str
    minimum_firmware_version: str
    release_url: str
    assets: Dict[str, ReleaseAsset]

    @property
    def firmware(self) -> ReleaseAsset:
        return self.assets["firmware"]

    @property
    def windows_setup(self) -> ReleaseAsset:
        return self.assets["windows_setup"]

    @property
    def windows_portable(self) -> ReleaseAsset:
        return self.assets["windows_portable"]


def parse_version(value: str) -> Optional[Tuple[int, int, int, str]]:
    value = str(value or "").strip()
    match = _VERSION_RE.fullmatch(value)
    if not match:
        return None
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), suffix or ""


def is_newer_version(candidate: str, current: str) -> bool:
    candidate_version = parse_version(candidate)
    current_version = parse_version(current)
    if candidate_version is None:
        return False
    if current_version is None:
        # Development/CI builds should still be able to inspect the current
        # stable release, but the UI labels it as a comparison against dev.
        return True
    candidate_core = candidate_version[:3]
    current_core = current_version[:3]
    if candidate_core != current_core:
        return candidate_core > current_core
    # Stable beats a prerelease at the same core version.
    candidate_suffix = candidate_version[3]
    current_suffix = current_version[3]
    if not candidate_suffix and current_suffix:
        return True
    return False


def version_at_least(current: str, minimum: str) -> bool:
    minimum_version = parse_version(minimum)
    if minimum_version is None:
        return True
    current_version = parse_version(current)
    if current_version is None:
        return False
    if current_version[:3] != minimum_version[:3]:
        return current_version[:3] > minimum_version[:3]
    if not minimum_version[3]:
        return not current_version[3]
    if not current_version[3]:
        return True
    return current_version[3] >= minimum_version[3]


def _validate_https_github_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    hostname = (parsed.hostname or "").lower()
    allowed = hostname in _ALLOWED_HOSTS or any(
        hostname.endswith(suffix) for suffix in _ALLOWED_HOST_SUFFIXES
    )
    if parsed.scheme != "https" or not allowed:
        raise UpdateCenterError(
            "UNTRUSTED_URL",
            "Update metadata points to an untrusted download URL.",
            detail=str(url),
        )
    return str(url)


def _parse_asset(key: str, value: object) -> ReleaseAsset:
    if not isinstance(value, dict):
        raise UpdateCenterError("MANIFEST_INVALID", f"Missing asset metadata: {key}")
    name = str(value.get("name", "") or "")
    if not name or pathlib.PurePath(name).name != name:
        raise UpdateCenterError("MANIFEST_INVALID", f"Invalid asset name: {key}")
    url = _validate_https_github_url(str(value.get("url", "") or ""))
    sha256 = str(value.get("sha256", "") or "").lower()
    if not _SHA256_RE.fullmatch(sha256):
        raise UpdateCenterError("MANIFEST_INVALID", f"Invalid SHA-256 for asset: {key}")
    try:
        size = int(value.get("size", 0))
    except (TypeError, ValueError) as exc:
        raise UpdateCenterError("MANIFEST_INVALID", f"Invalid size for asset: {key}") from exc
    if size <= 0 or size > MAX_DOWNLOAD_BYTES:
        raise UpdateCenterError("MANIFEST_INVALID", f"Unsafe size for asset: {key}")
    return ReleaseAsset(name=name, url=url, sha256=sha256, size=size)


def parse_manifest(payload: object) -> ReleaseManifest:
    if not isinstance(payload, dict):
        raise UpdateCenterError("MANIFEST_INVALID", "Release manifest is not a JSON object.")
    try:
        schema = int(payload.get("schema", 0))
        protocol = int(payload.get("protocol", -1))
    except (TypeError, ValueError) as exc:
        raise UpdateCenterError("MANIFEST_INVALID", "Manifest schema/protocol is invalid.") from exc
    if schema != MANIFEST_SCHEMA:
        raise UpdateCenterError(
            "MANIFEST_SCHEMA",
            f"Unsupported release manifest schema {schema}.",
        )
    version = str(payload.get("version", "") or "")
    tag = str(payload.get("tag", "") or "")
    if parse_version(version) is None:
        raise UpdateCenterError("MANIFEST_INVALID", "Release version is invalid.")
    if not tag:
        raise UpdateCenterError("MANIFEST_INVALID", "Release tag is missing.")
    release_url = _validate_https_github_url(str(payload.get("release_url", "") or ""))
    assets_raw = payload.get("assets", {})
    if not isinstance(assets_raw, dict):
        raise UpdateCenterError("MANIFEST_INVALID", "Release assets are missing.")
    required = ("firmware", "windows_setup", "windows_portable")
    assets = {key: _parse_asset(key, assets_raw.get(key)) for key in required}
    return ReleaseManifest(
        schema=schema,
        version=version,
        tag=tag,
        protocol=protocol,
        minimum_desktop_version=str(payload.get("minimum_desktop_version", "") or ""),
        minimum_firmware_version=str(payload.get("minimum_firmware_version", "") or ""),
        release_url=release_url,
        assets=assets,
    )


def verify_sha256(path: str | os.PathLike, expected: str) -> bool:
    expected = str(expected or "").lower()
    if not _SHA256_RE.fullmatch(expected):
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


class UpdateCenterClient:
    def __init__(
        self,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        *,
        timeout: float = 15.0,
        opener=None,
        update_dir: str = UPDATE_DIR,
    ):
        self.manifest_url = _validate_https_github_url(manifest_url)
        self.timeout = max(1.0, float(timeout))
        self.opener = opener or urllib.request.build_opener()
        self.update_dir = update_dir

    @staticmethod
    def _request(url: str):
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": f"VuNMix/{APP_VERSION}",
                "Accept": "application/json, application/octet-stream;q=0.9, */*;q=0.1",
            },
        )

    def fetch_manifest(self) -> ReleaseManifest:
        try:
            request = self._request(self.manifest_url)
            with self.opener.open(request, timeout=self.timeout) as response:
                data = response.read(MAX_MANIFEST_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateCenterError(
                "MANIFEST_DOWNLOAD",
                "Could not download the VuNMix release manifest.",
                detail=str(exc),
            ) from exc
        if len(data) > MAX_MANIFEST_BYTES:
            raise UpdateCenterError("MANIFEST_INVALID", "Release manifest is too large.")
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateCenterError("MANIFEST_INVALID", "Release manifest is not valid JSON.") from exc
        manifest = parse_manifest(payload)
        if manifest.protocol != PROTOCOL_VERSION:
            raise UpdateCenterError(
                "PROTOCOL_MISMATCH",
                f"Release protocol {manifest.protocol} is incompatible with desktop protocol {PROTOCOL_VERSION}.",
            )
        return manifest

    def check(self, *, firmware_version: str = "") -> dict:
        manifest = self.fetch_manifest()
        desktop_newer = is_newer_version(manifest.version, APP_VERSION)
        firmware_newer = is_newer_version(manifest.version, firmware_version) if firmware_version else True
        desktop_compatible = version_at_least(APP_VERSION, manifest.minimum_desktop_version)
        firmware_compatible = (
            version_at_least(firmware_version, manifest.minimum_firmware_version)
            if firmware_version
            else False
        )
        return {
            "manifest": manifest,
            "installed_desktop": APP_VERSION,
            "installed_firmware": firmware_version or "unknown",
            "desktop_update_available": desktop_newer,
            "firmware_update_available": firmware_newer,
            "desktop_meets_firmware_minimum": desktop_compatible,
            "firmware_meets_desktop_minimum": firmware_compatible,
        }

    def download_asset(
        self,
        asset: ReleaseAsset,
        *,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> pathlib.Path:
        _validate_https_github_url(asset.url)
        if not _SHA256_RE.fullmatch(asset.sha256):
            raise UpdateCenterError("MANIFEST_INVALID", "Asset checksum is invalid.")
        if asset.size <= 0 or asset.size > MAX_DOWNLOAD_BYTES:
            raise UpdateCenterError("MANIFEST_INVALID", "Asset size is unsafe.")

        os.makedirs(self.update_dir, exist_ok=True)
        destination = pathlib.Path(self.update_dir) / asset.name
        if destination.is_file() and destination.stat().st_size == asset.size:
            if verify_sha256(destination, asset.sha256):
                if progress:
                    progress(asset.size, asset.size)
                return destination
            try:
                destination.unlink()
            except OSError:
                pass

        fd, temp_name = tempfile.mkstemp(
            prefix=f"{asset.name}.",
            suffix=".part",
            dir=self.update_dir,
        )
        os.close(fd)
        downloaded = 0
        digest = hashlib.sha256()
        try:
            try:
                request = self._request(asset.url)
                with self.opener.open(request, timeout=self.timeout) as response, open(temp_name, "wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > asset.size or downloaded > MAX_DOWNLOAD_BYTES:
                            raise UpdateCenterError(
                                "DOWNLOAD_SIZE",
                                "Downloaded update is larger than the manifest declares.",
                            )
                        digest.update(chunk)
                        out.write(chunk)
                        if progress:
                            progress(downloaded, asset.size)
                    out.flush()
                    os.fsync(out.fileno())
            except UpdateCenterError:
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise UpdateCenterError(
                    "ASSET_DOWNLOAD",
                    f"Could not download {asset.name}.",
                    detail=str(exc),
                ) from exc

            if downloaded != asset.size:
                raise UpdateCenterError(
                    "DOWNLOAD_SIZE",
                    f"Downloaded size does not match manifest for {asset.name}.",
                    detail=f"expected={asset.size} actual={downloaded}",
                )
            actual_hash = digest.hexdigest()
            if actual_hash != asset.sha256:
                raise UpdateCenterError(
                    "CHECKSUM_MISMATCH",
                    f"SHA-256 verification failed for {asset.name}.",
                    detail=f"expected={asset.sha256} actual={actual_hash}",
                )
            os.replace(temp_name, destination)
            return destination
        finally:
            if os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
