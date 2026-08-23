import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from protocol import PROTOCOL_VERSION
from update_center import (
    ReleaseAsset,
    UpdateCenterClient,
    UpdateCenterError,
    is_newer_version,
    parse_manifest,
    verify_sha256,
    version_at_least,
)


class _Opener:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append((request.full_url, timeout))
        if not self.payloads:
            raise AssertionError("No fake response left")
        payload = self.payloads.pop(0)
        if isinstance(payload, BaseException):
            raise payload
        return io.BytesIO(payload)


def _asset(name, content=b"payload"):
    return {
        "name": name,
        "url": f"https://github.com/cuminhbecube/VuNMix/releases/download/v0.8.0/{name}",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


def _manifest(protocol=PROTOCOL_VERSION):
    return {
        "schema": 1,
        "version": "v0.8.0",
        "tag": "v0.8.0",
        "protocol": protocol,
        "minimum_desktop_version": "v0.5.0",
        "minimum_firmware_version": "v0.5.0",
        "release_url": "https://github.com/cuminhbecube/VuNMix/releases/tag/v0.8.0",
        "assets": {
            "firmware": _asset("VuNMix-Firmware-0.8.0.bin"),
            "windows_setup": _asset("VuNMix-Windows-Setup-0.8.0.exe"),
            "windows_portable": _asset("VuNMix-Windows-Portable-0.8.0.zip"),
        },
    }


class UpdateCenterTests(unittest.TestCase):
    def test_manifest_is_strict_and_exposes_required_assets(self):
        manifest = parse_manifest(_manifest())
        self.assertEqual(manifest.version, "v0.8.0")
        self.assertEqual(manifest.protocol, PROTOCOL_VERSION)
        self.assertTrue(manifest.firmware.name.endswith(".bin"))
        self.assertTrue(manifest.windows_setup.name.endswith(".exe"))

    def test_manifest_rejects_untrusted_or_missing_hash(self):
        payload = _manifest()
        payload["assets"]["firmware"]["url"] = "http://example.com/fw.bin"
        with self.assertRaises(UpdateCenterError) as ctx:
            parse_manifest(payload)
        self.assertEqual(ctx.exception.code, "UNTRUSTED_URL")

        payload = _manifest()
        payload["assets"]["firmware"]["sha256"] = ""
        with self.assertRaises(UpdateCenterError) as ctx:
            parse_manifest(payload)
        self.assertEqual(ctx.exception.code, "MANIFEST_INVALID")

    def test_fetch_manifest_rejects_protocol_mismatch(self):
        raw = json.dumps(_manifest(protocol=PROTOCOL_VERSION + 1)).encode("utf-8")
        client = UpdateCenterClient(opener=_Opener(raw))
        with self.assertRaises(UpdateCenterError) as ctx:
            client.fetch_manifest()
        self.assertEqual(ctx.exception.code, "PROTOCOL_MISMATCH")

    def test_download_requires_exact_size_and_sha256(self):
        content = b"verified firmware bytes"
        asset = ReleaseAsset(
            name="firmware.bin",
            url="https://github.com/cuminhbecube/VuNMix/releases/download/v0.8.0/firmware.bin",
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )
        with tempfile.TemporaryDirectory() as directory:
            progress = []
            client = UpdateCenterClient(
                opener=_Opener(content),
                update_dir=directory,
            )
            path = client.download_asset(
                asset,
                progress=lambda done, total: progress.append((done, total)),
            )
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), content)
            self.assertTrue(verify_sha256(path, asset.sha256))
            self.assertEqual(progress[-1], (len(content), len(content)))

            # A verified cached artifact is reused without another HTTP response.
            cached = client.download_asset(asset)
            self.assertEqual(cached, path)

    def test_checksum_mismatch_fails_closed_and_leaves_no_final_file(self):
        content = b"tampered"
        asset = ReleaseAsset(
            name="firmware.bin",
            url="https://github.com/cuminhbecube/VuNMix/releases/download/v0.8.0/firmware.bin",
            sha256=hashlib.sha256(b"expected").hexdigest(),
            size=len(content),
        )
        with tempfile.TemporaryDirectory() as directory:
            client = UpdateCenterClient(opener=_Opener(content), update_dir=directory)
            with self.assertRaises(UpdateCenterError) as ctx:
                client.download_asset(asset)
            self.assertEqual(ctx.exception.code, "CHECKSUM_MISMATCH")
            self.assertFalse((pathlib.Path(directory) / "firmware.bin").exists())

    def test_version_comparison_and_minimum_gate(self):
        self.assertTrue(is_newer_version("v0.8.0", "v0.7.0"))
        self.assertFalse(is_newer_version("v0.7.0", "v0.8.0"))
        self.assertTrue(is_newer_version("v0.8.0", "v0.8.0-rc.1"))
        self.assertTrue(version_at_least("v0.8.0", "v0.5.0"))
        self.assertFalse(version_at_least("v0.4.2", "v0.5.0"))


if __name__ == "__main__":
    unittest.main()
