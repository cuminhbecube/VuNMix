import hashlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

import firmware_release
from firmware_release import (
    FirmwareReleaseClient,
    FirmwareReleaseInfo,
    should_auto_update_firmware,
)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self._stream.read(size)


class FirmwareReleaseTests(unittest.TestCase):
    def test_auto_update_only_upgrades_to_newer_desktop_release(self):
        self.assertTrue(
            should_auto_update_firmware("v0.4.10", "0.4.11", enabled=True)
        )
        self.assertFalse(
            should_auto_update_firmware("0.4.11", "0.4.11", enabled=True)
        )
        self.assertFalse(
            should_auto_update_firmware("0.4.12", "0.4.11", enabled=True)
        )
        self.assertFalse(
            should_auto_update_firmware("0.4.10", "0.4.11", enabled=False)
        )
        self.assertFalse(
            should_auto_update_firmware("unknown", "0.4.11", enabled=True)
        )
        self.assertFalse(
            should_auto_update_firmware("0.4.10", "ci-abcdef0", enabled=True)
        )

    def test_release_requires_matching_firmware_and_checksums(self):
        client = FirmwareReleaseClient()
        release = {
            "tag_name": "v0.4.11",
            "html_url": "https://github.com/cuminhbecube/VuNMix/releases/tag/v0.4.11",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "VuNMix-Firmware-0.4.11.bin",
                    "browser_download_url":
                        "https://github.com/cuminhbecube/VuNMix/releases/download/v0.4.11/"
                        "VuNMix-Firmware-0.4.11.bin",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url":
                        "https://github.com/cuminhbecube/VuNMix/releases/download/v0.4.11/"
                        "SHA256SUMS.txt",
                },
            ],
        }

        info = client.release_to_info(release)
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.4.11")
        self.assertEqual(info.tag, "v0.4.11")

        release["assets"] = release["assets"][:1]
        self.assertIsNone(client.release_to_info(release))

    def test_release_list_sorts_versions_newest_first(self):
        client = FirmwareReleaseClient()
        payload = []
        for version in ("0.4.9", "0.4.11", "0.4.10"):
            payload.append({
                "tag_name": f"v{version}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": f"VuNMix-Firmware-{version}.bin",
                        "browser_download_url":
                            f"https://github.com/cuminhbecube/VuNMix/releases/download/"
                            f"v{version}/VuNMix-Firmware-{version}.bin",
                    },
                    {
                        "name": "SHA256SUMS.txt",
                        "browser_download_url":
                            f"https://github.com/cuminhbecube/VuNMix/releases/download/"
                            f"v{version}/SHA256SUMS.txt",
                    },
                ],
            })

        with mock.patch.object(client, "_request_json", return_value=payload):
            releases = client.list_releases()

        self.assertEqual(
            [item.version for item in releases],
            ["0.4.11", "0.4.10", "0.4.9"],
        )

    def test_download_verifies_hash_before_flash_validation(self):
        payload = b"firmware-image-data" * 400
        digest = hashlib.sha256(payload).hexdigest()
        info = FirmwareReleaseInfo(
            version="0.4.11",
            tag="v0.4.11",
            release_url="",
            firmware_name="VuNMix-Firmware-0.4.11.bin",
            firmware_url=(
                "https://github.com/cuminhbecube/VuNMix/releases/download/"
                "v0.4.11/VuNMix-Firmware-0.4.11.bin"
            ),
            checksums_url=(
                "https://github.com/cuminhbecube/VuNMix/releases/download/"
                "v0.4.11/SHA256SUMS.txt"
            ),
        )
        client = FirmwareReleaseClient()

        with tempfile.TemporaryDirectory() as directory:
            target_dir = pathlib.Path(directory)
            with (
                mock.patch.object(
                    client,
                    "_expected_hash",
                    return_value=digest,
                ),
                mock.patch(
                    "firmware_release.urllib.request.urlopen",
                    return_value=_FakeResponse(payload),
                ),
                mock.patch(
                    "firmware_release.FIRMWARE_CACHE_DIR",
                    target_dir,
                ),
                mock.patch(
                    "firmware_updater.validate_firmware",
                    side_effect=lambda path: pathlib.Path(path),
                ) as validator,
            ):
                path = client.download(info)

            self.assertEqual(path.read_bytes(), payload)
            validator.assert_called_once_with(str(path))


if __name__ == "__main__":
    unittest.main()
