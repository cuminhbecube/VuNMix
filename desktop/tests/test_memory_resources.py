"""Repeated resource lifecycle checks, including failure and cancellation paths."""

import asyncio
import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import audio_capture
import media_service
from media_service import MediaService


class ThumbnailResourceTests(unittest.TestCase):
    def test_oversized_dimensions_rejected_before_pixel_decode(self):
        opened = mock.Mock(width=4097, height=4096)
        context = mock.MagicMock()
        context.__enter__.return_value = opened
        with mock.patch.object(media_service.Image, "open", return_value=context):
            self.assertEqual(MediaService._convert_artwork(b"compressed"), b"")
        opened.convert.assert_not_called()
        context.__exit__.assert_called_once()

    def test_1000_reads_close_each_native_stream(self):
        service = MediaService()
        active = 0
        opened = 0

        class Stream:
            size = 4

            async def read_async(self, *_args):
                return b"tile"

            def close(self):
                nonlocal active
                active -= 1

        async def open_stream():
            nonlocal active, opened
            active += 1
            opened += 1
            return Stream()

        async def repeat():
            for _ in range(1000):
                self.assertEqual(await service._read_thumbnail(ref), b"tile")
                self.assertEqual(active, 0)

        ref = SimpleNamespace(open_read_async=open_stream)
        with (
            mock.patch.object(media_service, "Buffer", side_effect=lambda size: bytearray(size)),
            mock.patch.object(media_service, "InputStreamOptions", SimpleNamespace(READ_AHEAD=0)),
        ):
            asyncio.run(repeat())
        self.assertEqual(opened, 1000)

    def test_empty_oversized_failed_and_cancelled_reads_close_stream(self):
        for kind in ("empty", "oversized", "failed", "cancelled"):
            with self.subTest(kind=kind):
                stream = mock.Mock()
                stream.size = {"empty": 0, "oversized": media_service.MAX_SOURCE_ARTWORK_BYTES + 1}.get(kind, 4)
                error = asyncio.CancelledError() if kind == "cancelled" else OSError("read failed")
                stream.read_async = mock.AsyncMock(side_effect=error)
                ref = SimpleNamespace(open_read_async=mock.AsyncMock(return_value=stream))
                with (
                    mock.patch.object(media_service, "Buffer", side_effect=lambda size: bytearray(size)),
                    mock.patch.object(media_service, "InputStreamOptions", SimpleNamespace(READ_AHEAD=0)),
                ):
                    if kind == "cancelled":
                        with self.assertRaises(asyncio.CancelledError):
                            asyncio.run(MediaService()._read_thumbnail(ref))
                    else:
                        self.assertEqual(asyncio.run(MediaService()._read_thumbnail(ref)), b"")
                stream.close.assert_called_once()
                if kind in ("empty", "oversized"):
                    stream.read_async.assert_not_called()

    def test_track_cache_avoids_reopening_artwork_but_updates_on_change(self):
        props = SimpleNamespace(title="A", artist="Artist", thumbnail=object())
        session = SimpleNamespace(
            source_app_user_model_id="player.exe",
            try_get_media_properties_async=mock.AsyncMock(return_value=props),
            get_playback_info=lambda: SimpleNamespace(playback_status=4),
            get_timeline_properties=lambda: SimpleNamespace(),
        )
        manager = SimpleNamespace(get_current_session=lambda: session)
        service = MediaService()
        clock = [100.0]

        async def poll():
            for _ in range(1000):
                await service._read_smtc()
            self.assertEqual(reader.await_count, 1)
            props.title = "B"
            await service._read_smtc()
            self.assertEqual(reader.await_count, 2)
            clock[0] += media_service.ARTWORK_REFRESH_INTERVAL
            await service._read_smtc()
            self.assertEqual(reader.await_count, 3)

        with (
            mock.patch.object(media_service, "MediaManager", SimpleNamespace(request_async=mock.AsyncMock(return_value=manager))),
            mock.patch.object(service, "_read_thumbnail", new=mock.AsyncMock(return_value=b"art")) as reader,
            mock.patch.object(media_service.time, "monotonic", side_effect=lambda: clock[0]),
        ):
            asyncio.run(poll())

    def test_concurrent_refresh_uses_cached_snapshot_without_second_query(self):
        service = MediaService()
        entered = threading.Event()
        release = threading.Event()

        def slow_query(coro):
            coro.close()
            entered.set()
            release.wait(2)
            return None

        with (
            mock.patch.object(media_service, "MediaManager", object()),
            mock.patch.object(service, "_run_async", side_effect=slow_query) as query,
            mock.patch.object(service, "_window_fallback", return_value=None),
        ):
            worker = threading.Thread(target=lambda: service.refresh(force=True))
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                previous = service.cached_snapshot()
                for _ in range(1000):
                    self.assertIs(service.refresh(force=True), previous)
                self.assertEqual(query.call_count, 1)
            finally:
                release.set()
                worker.join(2)
            self.assertFalse(worker.is_alive())

    def test_async_timeout_cleans_up_and_allows_next_query(self):
        service = MediaService()
        cleaned = []

        async def stuck():
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.append(True)

        async def healthy():
            return 42

        with mock.patch.object(media_service, "MEDIA_QUERY_TIMEOUT", 0.01):
            with self.assertRaises(TimeoutError):
                service._run_async(stuck())
        self.assertEqual(cleaned, [True])
        self.assertEqual(service._run_async(healthy()), 42)

    def test_async_bridge_works_inside_running_event_loop(self):
        service = MediaService()

        async def value():
            return 42

        async def caller():
            self.assertEqual(service._run_async(value()), 42)

        asyncio.run(caller())


class CaptureResourceTests(unittest.TestCase):
    def test_500_failed_starts_close_streams_before_retry(self):
        streams = []

        def make_stream(**_kwargs):
            stream = mock.Mock()
            stream.start.side_effect = OSError("device removed")
            streams.append(stream)
            return stream

        with mock.patch.object(audio_capture.sd, "RawInputStream", side_effect=make_stream, create=True):
            for _ in range(500):
                with self.assertRaisesRegex(OSError, "device removed"):
                    audio_capture.InputPeakMeter(0, 2, 48000)
                streams[-1].close.assert_called_once()

    def test_close_is_idempotent_and_closes_after_stop_error(self):
        stream = mock.Mock()
        with mock.patch.object(audio_capture.sd, "RawInputStream", return_value=stream, create=True):
            meter = audio_capture.InputPeakMeter(0, 2, 48000)
        stream.stop.side_effect = OSError("removed")
        with self.assertRaises(OSError):
            meter.close()
        meter.close()
        stream.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
