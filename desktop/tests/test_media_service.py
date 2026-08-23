import io
import pathlib
import sys
import unittest
from unittest import mock

from PIL import Image


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

import media_service
from media_service import (
    MEDIA_ACTION_NEXT,
    MEDIA_ACTION_PLAY_PAUSE,
    MEDIA_ACTION_PREVIOUS,
    MEDIA_ACTION_STOP,
    MEDIA_ARTWORK_BYTES,
    MediaService,
)
from protocol import MediaInfoData


class MediaServiceTests(unittest.TestCase):
    @staticmethod
    def _png_bytes(color=(30, 120, 220)):
        image = Image.new("RGB", (64, 32), color)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_artwork_is_cropped_to_fixed_16x16_rgb565(self):
        encoded = MediaService._convert_artwork(self._png_bytes())
        self.assertEqual(len(encoded), MEDIA_ARTWORK_BYTES)
        self.assertEqual(MEDIA_ARTWORK_BYTES, 512)
        # One RGB565 pixel is two little-endian bytes; a flat image should
        # therefore produce the same pair across the entire tile.
        self.assertEqual(encoded[:2] * (MEDIA_ARTWORK_BYTES // 2), encoded)

    def test_refresh_uses_smtc_timeline_and_deduplicates_artwork_conversion(self):
        service = MediaService()
        raw_art = self._png_bytes((200, 50, 10))
        result = {
            "info": MediaInfoData(
                is_playing=1,
                position_sec=42,
                duration_sec=240,
                title="Track A",
                artist="Artist A",
            ),
            "source_app": "Spotify.exe",
            "artwork": raw_art,
        }

        with (
            mock.patch.object(media_service, "MediaManager", object()),
            mock.patch.object(service, "_run_async", side_effect=[result, result]),
            mock.patch.object(
                service,
                "_convert_artwork",
                wraps=service._convert_artwork,
            ) as converter,
        ):
            first = service.refresh(force=True)
            second = service.refresh(force=True)

        self.assertEqual(first.info.title, "Track A")
        self.assertEqual(first.info.artist, "Artist A")
        self.assertEqual(first.info.position_sec, 42)
        self.assertEqual(first.info.duration_sec, 240)
        self.assertEqual(first.source_app, "Spotify.exe")
        self.assertEqual(len(first.artwork_rgb565), 512)
        self.assertEqual(first.artwork_key, second.artwork_key)
        converter.assert_called_once_with(raw_art)

    def test_transient_empty_smtc_properties_keep_last_track(self):
        service = MediaService()
        valid = {
            "info": MediaInfoData(
                is_playing=1,
                position_sec=10,
                duration_sec=100,
                title="Stable title",
                artist="Stable artist",
            ),
            "source_app": "player.exe",
            "artwork": b"",
        }
        empty = {
            "info": MediaInfoData(),
            "source_app": "player.exe",
            "artwork": b"",
        }

        with (
            mock.patch.object(media_service, "MediaManager", object()),
            mock.patch.object(service, "_run_async", side_effect=[valid, empty]),
            mock.patch.object(media_service.time, "monotonic", side_effect=[100.0, 101.0]),
        ):
            first = service.refresh(force=True)
            second = service.refresh(force=True)

        self.assertEqual(first.info.title, "Stable title")
        self.assertEqual(second.info.title, "Stable title")
        self.assertEqual(second.info.artist, "Stable artist")

    def test_media_action_ids_match_firmware_contract(self):
        self.assertEqual(MEDIA_ACTION_PLAY_PAUSE, 1)
        self.assertEqual(MEDIA_ACTION_NEXT, 2)
        self.assertEqual(MEDIA_ACTION_PREVIOUS, 3)
        self.assertEqual(MEDIA_ACTION_STOP, 4)

        service = MediaService()
        with (
            mock.patch.object(media_service, "MediaManager", None),
            mock.patch.object(service, "_send_media_key", return_value=True) as sender,
        ):
            for action in (1, 2, 3, 4):
                self.assertTrue(service.execute_control(action))

        self.assertEqual(
            [call.args[0] for call in sender.call_args_list],
            [1, 2, 3, 4],
        )
        self.assertFalse(service.execute_control(99))


if __name__ == "__main__":
    unittest.main()
