import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from media_controller import MediaAppController
from media_service import MEDIA_ARTWORK_BYTES, MediaSnapshot
from protocol import AppIconChunk, Command, DisplayMode, MediaInfoData
from serial_service import SerialService


class _Audio:
    def __init__(self):
        self.items = [
            SimpleNamespace(
                id=42,
                name="Spotify",
                _process_path=r"C:\\Users\\test\\Spotify.exe",
            ),
            SimpleNamespace(
                id=17,
                name="Discord",
                _process_path=r"C:\\Users\\test\\Discord.exe",
            ),
        ]

    def get_sessions_for_mode(self, mode):
        return list(self.items) if mode == DisplayMode.MODE_APPLICATION else []


class _Media:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_current_snapshot(self):
        return self.snapshot

    def cached_snapshot(self):
        return self.snapshot


class _Serial:
    def __init__(self):
        self.is_connected = True
        self.calls = []

    def send_app_icon(self, app_id, data, width=16, height=16):
        self.calls.append((app_id, bytes(data), width, height))
        return True


class MediaControllerTests(unittest.TestCase):
    def _controller(self, snapshot):
        controller = object.__new__(MediaAppController)
        controller._connection_lock = threading.RLock()
        controller._device_connected = True
        controller._is_sleeping = False
        controller._sent_icon_ids = set()
        controller._last_artwork_key = ""
        controller._last_artwork_target = 0
        controller._last_artwork_send_at = -1e12
        controller._artwork_send_count = 0
        controller.serial = _Serial()
        controller.audio = _Audio()
        controller.media_service = _Media(snapshot)
        return controller

    @staticmethod
    def _snapshot(key="cover-a", source="Spotify.exe", fill=0x11):
        return MediaSnapshot(
            info=MediaInfoData(
                is_playing=1,
                title="Song",
                artist="Artist",
                position_sec=12,
                duration_sec=120,
            ),
            source_app=source,
            artwork_key=key,
            artwork_rgb565=bytes([fill]) * MEDIA_ARTWORK_BYTES,
            backend="smtc",
        )

    def test_artwork_targets_media_app_and_same_digest_is_not_resent(self):
        controller = self._controller(self._snapshot())

        with mock.patch("media_controller.time.monotonic", side_effect=[10.0]):
            self.assertTrue(controller._send_artwork_once())
            # Same digest+target exits before reading the clock again.
            self.assertFalse(controller._send_artwork_once())

        self.assertEqual(len(controller.serial.calls), 1)
        app_id, data, width, height = controller.serial.calls[0]
        self.assertEqual(app_id, 42)
        self.assertEqual(len(data), 512)
        self.assertEqual((width, height), (16, 16))
        self.assertIn(42, controller._sent_icon_ids)
        self.assertEqual(controller.media_artwork_send_count, 1)

    def test_changed_artwork_is_throttled_then_sent(self):
        controller = self._controller(self._snapshot(key="cover-a", fill=0x11))

        with mock.patch("media_controller.time.monotonic", return_value=10.0):
            self.assertTrue(controller._send_artwork_once())

        controller.media_service.snapshot = self._snapshot(key="cover-b", fill=0x22)
        with mock.patch("media_controller.time.monotonic", return_value=10.5):
            self.assertFalse(controller._send_artwork_once())
        with mock.patch("media_controller.time.monotonic", return_value=12.0):
            self.assertTrue(controller._send_artwork_once())

        self.assertEqual(len(controller.serial.calls), 2)
        self.assertEqual(controller.serial.calls[-1][1], bytes([0x22]) * 512)
        self.assertEqual(controller.media_artwork_send_count, 2)

    def test_unknown_source_does_not_consume_icon_namespace(self):
        controller = self._controller(self._snapshot(source="Unknown.Player.exe"))
        self.assertFalse(controller._send_artwork_once())
        self.assertEqual(controller.serial.calls, [])
        self.assertEqual(controller.media_artwork_send_count, 0)

    def test_serial_transport_splits_512_bytes_into_nine_bounded_chunks(self):
        service = object.__new__(SerialService)
        service._icon_lock = threading.Lock()
        sent = []

        def send_command(command, payload=b""):
            sent.append((command, bytes(payload)))
            return True

        service.send_command = send_command
        data = bytes(range(256)) * 2

        with mock.patch("serial_service.time.sleep"):
            self.assertTrue(service.send_app_icon(42, data, width=16, height=16))

        self.assertEqual(sent[0][0], Command.APP_ICON_META)
        chunks = [payload for command, payload in sent if command == Command.APP_ICON_CHUNK]
        self.assertEqual(len(chunks), 9)
        lengths = [payload[2] for payload in chunks]
        self.assertEqual(lengths[:-1], [60] * 8)
        self.assertEqual(lengths[-1], 32)
        self.assertTrue(all(length <= 60 for length in lengths))
        decoded = [AppIconChunk.unpack(payload) for payload in chunks]
        rebuilt = b"".join(chunk.data for chunk in decoded)
        self.assertEqual(rebuilt, data)


if __name__ == "__main__":
    unittest.main()
