"""GitHub Release based self-update support for VuNMix Desktop."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


log = logging.getLogger(__name__)

REPOSITORY = "cuminhbecube/VuNMix"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASE_DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
USER_AGENT = "VuNMix-Updater/1.0"
UPDATE_DIR = Path(
    os.environ.get(
        "LOCALAPPDATA",
        os.path.join(os.path.expanduser("~"), "AppData", "Local"),
    )
) / "VuNMix" / "updates"

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_SETUP_RE = re.compile(r"^VuNMix-Windows-Setup-(\d+\.\d+\.\d+)\.exe$")


class UpdateError(RuntimeError):
    """Raised when a release cannot be safely downloaded or installed."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag: str
    release_url: str
    installer_name: str
    installer_url: str
    checksums_url: str
    notes: str = ""


def version_tuple(value: str) -> Optional[tuple[int, int, int]]:
    match = _SEMVER_RE.fullmatch((value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer_version(current: str, candidate: str) -> bool:
    current_tuple = version_tuple(current)
    candidate_tuple = version_tuple(candidate)
    if current_tuple is None or candidate_tuple is None:
        return False
    return candidate_tuple > current_tuple


def parse_sha256sums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts
        name = name.lstrip("*").strip()
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) and name:
            checksums[name] = digest.lower()
    return checksums


class AppUpdater:
    """Check, verify and launch signed VuNMix release installers."""

    def __init__(self, current_version: str, timeout: float = 10.0):
        self.current_version = current_version
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
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError(f"Network error while checking updates: {exc}") from exc

    @staticmethod
    def _asset_url(release: dict, name: str) -> Optional[str]:
        for asset in release.get("assets", []):
            if asset.get("name") == name:
                url = str(asset.get("browser_download_url") or "")
                if url.startswith(RELEASE_DOWNLOAD_PREFIX):
                    return url
        return None

    def release_to_update(self, release: dict) -> Optional[UpdateInfo]:
        if release.get("draft") or release.get("prerelease"):
            return None

        tag = str(release.get("tag_name") or "").strip()
        version = tag[1:] if tag.startswith("v") else tag
        if not is_newer_version(self.current_version, version):
            return None

        expected_name = f"VuNMix-Windows-Setup-{version}.exe"
        if not _SETUP_RE.fullmatch(expected_name):
            return None

        installer_url = self._asset_url(release, expected_name)
        checksums_url = self._asset_url(release, "SHA256SUMS.txt")
        if not installer_url or not checksums_url:
            raise UpdateError(
                f"Release {tag} is missing the Windows installer or SHA256SUMS.txt."
            )

        return UpdateInfo(
            version=version,
            tag=tag or f"v{version}",
            release_url=str(release.get("html_url") or ""),
            installer_name=expected_name,
            installer_url=installer_url,
            checksums_url=checksums_url,
            notes=str(release.get("body") or ""),
        )

    def check_latest(self) -> Optional[UpdateInfo]:
        if version_tuple(self.current_version) is None:
            log.info(
                "Skipping automatic update comparison for non-release build %s",
                self.current_version,
            )
            return None

        try:
            payload = json.loads(self._request(LATEST_RELEASE_API).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateError("GitHub returned invalid release metadata.") from exc

        info = self.release_to_update(payload)
        if info:
            log.info(
                "App update available: current=%s latest=%s",
                self.current_version,
                info.tag,
            )
        else:
            log.info("App is up to date: %s", self.current_version)
        return info

    def _expected_installer_hash(self, info: UpdateInfo) -> str:
        try:
            text = self._request(info.checksums_url).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UpdateError("Release checksum file is not valid UTF-8.") from exc
        checksums = parse_sha256sums(text)
        digest = checksums.get(info.installer_name)
        if not digest:
            raise UpdateError(
                f"SHA256SUMS.txt does not contain {info.installer_name}."
            )
        return digest

    def _download_installer(
        self,
        info: UpdateInfo,
        expected_hash: str,
        progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        final_path = UPDATE_DIR / info.installer_name
        temp_path = final_path.with_suffix(final_path.suffix + ".part")

        request = urllib.request.Request(
            info.installer_url,
            headers={"User-Agent": USER_AGENT},
        )

        hasher = hashlib.sha256()
        downloaded = 0
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                total = int(response.headers.get("Content-Length") or 0)
                with open(temp_path, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 256)
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
                            progress(fraction, f"Downloading {info.tag}...")
                    handle.flush()
                    os.fsync(handle.fileno())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise UpdateError(f"Failed to download {info.installer_name}: {exc}") from exc

        actual_hash = hasher.hexdigest().lower()
        if actual_hash != expected_hash.lower():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise UpdateError(
                "Downloaded installer failed SHA-256 verification. "
                f"Expected {expected_hash}, got {actual_hash}."
            )

        os.replace(temp_path, final_path)
        if progress:
            progress(1.0, "Installer verified.")
        return final_path

    @staticmethod
    def installer_command(installer_path: Path) -> list[str]:
        return [
            str(installer_path),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]

    def launch_installer(self, installer_path: Path) -> None:
        command = self.installer_command(installer_path)

        if os.name == "nt":
            # Inno Setup updates Program Files and therefore needs elevation.
            # ShellExecute with the "runas" verb triggers the normal Windows
            # UAC consent dialog; CreateProcess/Popen may fail with error 740.
            import ctypes

            params = subprocess.list2cmdline(command[1:])
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                str(installer_path),
                params,
                None,
                1,
            )
            if int(result) <= 32:
                raise UpdateError(
                    f"Windows could not start the update installer (ShellExecute={result})."
                )
            return

        try:
            subprocess.Popen(command, close_fds=True)
        except OSError as exc:
            raise UpdateError(f"Could not start update installer: {exc}") from exc

    def download_and_install(
        self,
        info: UpdateInfo,
        progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        if progress:
            progress(0.02, f"Checking {info.tag}...")
        expected_hash = self._expected_installer_hash(info)
        if progress:
            progress(0.05, "Checksum loaded.")
        installer_path = self._download_installer(info, expected_hash, progress)
        self.launch_installer(installer_path)
        log.info("Launched app installer: %s", installer_path)
        return installer_path
