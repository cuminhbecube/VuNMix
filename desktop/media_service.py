"""VuNMix media integration using Windows System Media Transport Controls.

Primary metadata/control path is Windows GSMTC through ``winsdk``. A small
window-title fallback is retained for players that do not expose a SMTC session.

Album artwork is reduced on the PC to a 16x16 RGB565 tile (512 bytes). This
fits the existing APP_ICON chunk transport and can be cached/deduplicated
without changing protocol-v1 frame sizes.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import io
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import win32gui

from protocol import MediaInfoData

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winsdk.windows.storage.streams import Buffer, InputStreamOptions
except ImportError:  # tests/non-Windows developer environments
    MediaManager = None
    Buffer = None
    InputStreamOptions = None


log = logging.getLogger(__name__)

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

MEDIA_ACTION_PLAY_PAUSE = 1
MEDIA_ACTION_NEXT = 2
MEDIA_ACTION_PREVIOUS = 3
MEDIA_ACTION_STOP = 4

MEDIA_ARTWORK_SIZE = 16
MEDIA_ARTWORK_BYTES = MEDIA_ARTWORK_SIZE * MEDIA_ARTWORK_SIZE * 2
MAX_SOURCE_ARTWORK_BYTES = 5 * 1024 * 1024
METADATA_GRACE_SECONDS = 5.0
REFRESH_MIN_INTERVAL = 0.45


@dataclass(frozen=True)
class MediaSnapshot:
    info: MediaInfoData
    source_app: str = ""
    artwork_key: str = ""
    artwork_rgb565: bytes = b""
    backend: str = "none"


class MediaService:
    """Read media state, dispatch playback commands and cache album artwork."""

    def __init__(self):
        self._lock = threading.RLock()
        self._last_refresh_at = 0.0
        self._last_valid_at = 0.0
        self._last_snapshot = MediaSnapshot(MediaInfoData())
        self._artwork_source_key = ""
        self._artwork_rgb565 = b""
        self._artwork_key = ""

    @staticmethod
    def _seconds(value) -> int:
        """Convert winsdk TimeSpan/timedelta-like values to whole seconds."""
        if value is None:
            return 0
        try:
            if hasattr(value, "total_seconds"):
                return max(0, int(value.total_seconds()))
            if hasattr(value, "seconds"):
                return max(0, int(value.seconds))
            if hasattr(value, "duration"):
                return max(0, int(value.duration) // 10_000_000)
            return max(0, int(value))
        except Exception:
            return 0

    @staticmethod
    def _playback_is_playing(playback_info) -> bool:
        try:
            status = playback_info.playback_status
            name = str(getattr(status, "name", status)).upper()
            if name == "PLAYING" or name.endswith(".PLAYING"):
                return True
            return int(status) == 4
        except Exception:
            return False

    @staticmethod
    def _run_async(coro):
        """Run a small WinRT coroutine from VuNMix worker/tray threads."""
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            if "running event loop" not in str(exc).lower():
                raise
            result = []
            error = []

            def runner():
                try:
                    result.append(asyncio.run(coro))
                except Exception as inner:
                    error.append(inner)

            thread = threading.Thread(target=runner, daemon=True, name="MediaWinRT")
            thread.start()
            thread.join(timeout=5.0)
            if error:
                raise error[0]
            return result[0] if result else None

    async def _read_thumbnail(self, thumbnail_ref) -> bytes:
        if not thumbnail_ref or Buffer is None or InputStreamOptions is None:
            return b""
        try:
            stream = await thumbnail_ref.open_read_async()
            size = int(getattr(stream, "size", 0) or 0)
            if size <= 0:
                return b""
            capacity = min(size, MAX_SOURCE_ARTWORK_BYTES)
            buffer = Buffer(capacity)
            await stream.read_async(buffer, capacity, InputStreamOptions.READ_AHEAD)
            return bytes(bytearray(buffer))[:MAX_SOURCE_ARTWORK_BYTES]
        except Exception as exc:
            log.debug("Could not read media artwork: %s", exc)
            return b""

    async def _read_smtc(self):
        if MediaManager is None:
            return None
        manager = await MediaManager.request_async()
        session = manager.get_current_session() if manager else None
        if not session:
            return None

        props = await session.try_get_media_properties_async()
        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()

        title = str(getattr(props, "title", "") or "") if props else ""
        artist = str(getattr(props, "artist", "") or "") if props else ""
        source_app = str(getattr(session, "source_app_user_model_id", "") or "")
        is_playing = self._playback_is_playing(playback)

        position = self._seconds(getattr(timeline, "position", None))
        duration = self._seconds(getattr(timeline, "end_time", None))
        start = self._seconds(getattr(timeline, "start_time", None))
        if duration > start:
            duration -= start
            position = max(0, position - start)

        last_updated = getattr(timeline, "last_updated_time", None)
        if is_playing and isinstance(last_updated, datetime):
            try:
                position += max(
                    0,
                    int((datetime.now(last_updated.tzinfo) - last_updated).total_seconds()),
                )
            except Exception:
                pass
        if duration > 0:
            position = min(position, duration)

        thumbnail = b""
        if props:
            thumbnail = await self._read_thumbnail(getattr(props, "thumbnail", None))

        return {
            "info": MediaInfoData(
                is_playing=1 if is_playing else 0,
                position_sec=min(position, 65535),
                duration_sec=min(duration, 65535),
                title=title,
                artist=artist,
            ),
            "source_app": source_app,
            "artwork": thumbnail,
        }

    @staticmethod
    def _window_fallback() -> Optional[MediaInfoData]:
        """Best-effort fallback for legacy players without a SMTC session."""
        found = {"title": "", "artist": "", "playing": 0}

        def enum_window(hwnd, _extra):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                text = win32gui.GetWindowText(hwnd)
                if not text:
                    return True

                class_name = win32gui.GetClassName(hwnd)
                if "Chrome_WidgetWin_0" in class_name or "Spotify" in text:
                    if " - " in text and not text.startswith("Spotify"):
                        artist, title = text.split(" - ", 1)
                        found.update(title=title.strip(), artist=artist.strip(), playing=1)
                        return False

                if "VLC media player" in text:
                    cleaned = text.replace(" - VLC media player", "").strip()
                    if cleaned and cleaned != "VLC media player":
                        if " - " in cleaned:
                            artist, title = cleaned.split(" - ", 1)
                        else:
                            artist, title = "VLC", cleaned
                        found.update(title=title.strip(), artist=artist.strip(), playing=1)
                        return False
                return True
            except Exception:
                return True

        try:
            win32gui.EnumWindows(enum_window, None)
        except Exception:
            return None
        if not found["title"]:
            return None
        return MediaInfoData(
            is_playing=found["playing"],
            position_sec=0,
            duration_sec=0,
            title=found["title"],
            artist=found["artist"],
        )

    @staticmethod
    def _convert_artwork(raw: bytes) -> bytes:
        """Crop/resize artwork and encode 16x16 little-endian RGB565."""
        if not raw or Image is None or ImageOps is None:
            return b""
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                image = ImageOps.fit(
                    opened.convert("RGB"),
                    (MEDIA_ARTWORK_SIZE, MEDIA_ARTWORK_SIZE),
                    method=Image.Resampling.LANCZOS,
                )
                encoded = bytearray()
                for r, g, b in image.getdata():
                    rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                    encoded.extend((rgb565 & 0xFF, (rgb565 >> 8) & 0xFF))
            return bytes(encoded) if len(encoded) == MEDIA_ARTWORK_BYTES else b""
        except Exception as exc:
            log.debug("Could not resize media artwork: %s", exc)
            return b""

    def refresh(self, *, force: bool = False) -> MediaSnapshot:
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_refresh_at < REFRESH_MIN_INTERVAL:
                return self._last_snapshot
            self._last_refresh_at = now

        result = None
        if MediaManager is not None:
            try:
                result = self._run_async(self._read_smtc())
            except Exception as exc:
                log.debug("Windows SMTC media query failed: %s", exc)

        backend = "smtc" if result else "fallback"
        if result:
            info = result["info"]
            source_app = result["source_app"]
            raw_artwork = result["artwork"]
        else:
            info = self._window_fallback() or MediaInfoData()
            source_app = ""
            raw_artwork = b""

        with self._lock:
            previous = self._last_snapshot
            if info.title or info.artist:
                self._last_valid_at = now
            elif previous.info.title and now - self._last_valid_at <= METADATA_GRACE_SECONDS:
                info = MediaInfoData(
                    is_playing=info.is_playing,
                    position_sec=previous.info.position_sec,
                    duration_sec=previous.info.duration_sec,
                    title=previous.info.title,
                    artist=previous.info.artist,
                )
                source_app = source_app or previous.source_app

            if raw_artwork:
                source_key = hashlib.sha256(raw_artwork).hexdigest()
                if source_key != self._artwork_source_key:
                    converted = self._convert_artwork(raw_artwork)
                    if converted:
                        self._artwork_source_key = source_key
                        self._artwork_rgb565 = converted
                        self._artwork_key = hashlib.sha256(converted).hexdigest()

            snapshot = MediaSnapshot(
                info=info,
                source_app=source_app,
                artwork_key=self._artwork_key,
                artwork_rgb565=self._artwork_rgb565,
                backend=backend,
            )
            self._last_snapshot = snapshot
            return snapshot

    def get_current_media_info(self) -> MediaInfoData:
        return self.refresh().info

    def get_current_snapshot(self, *, force: bool = False) -> MediaSnapshot:
        return self.refresh(force=force)

    def cached_snapshot(self) -> MediaSnapshot:
        with self._lock:
            return self._last_snapshot

    async def _execute_smtc_control(self, action: int) -> bool:
        if MediaManager is None:
            return False
        manager = await MediaManager.request_async()
        session = manager.get_current_session() if manager else None
        if not session:
            return False

        if action == MEDIA_ACTION_PLAY_PAUSE:
            return bool(await session.try_toggle_play_pause_async())
        if action == MEDIA_ACTION_NEXT:
            return bool(await session.try_skip_next_async())
        if action == MEDIA_ACTION_PREVIOUS:
            return bool(await session.try_skip_previous_async())
        if action == MEDIA_ACTION_STOP:
            return bool(await session.try_stop_async())
        return False

    @staticmethod
    def _send_media_key(action: int) -> bool:
        key_map = {
            MEDIA_ACTION_PLAY_PAUSE: VK_MEDIA_PLAY_PAUSE,
            MEDIA_ACTION_NEXT: VK_MEDIA_NEXT_TRACK,
            MEDIA_ACTION_PREVIOUS: VK_MEDIA_PREV_TRACK,
            MEDIA_ACTION_STOP: VK_MEDIA_STOP,
        }
        vk = key_map.get(action)
        if not vk:
            return False
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.01)
            user32.keybd_event(vk, 0, 0x0002, 0)
            return True
        except Exception as exc:
            log.error("Failed to dispatch media key: %s", exc)
            return False

    def execute_control(self, action: int) -> bool:
        """Execute 1=Play/Pause, 2=Next, 3=Previous, 4=Stop."""
        if action not in (
            MEDIA_ACTION_PLAY_PAUSE,
            MEDIA_ACTION_NEXT,
            MEDIA_ACTION_PREVIOUS,
            MEDIA_ACTION_STOP,
        ):
            return False

        if MediaManager is not None:
            try:
                if self._run_async(self._execute_smtc_control(action)):
                    log.info("Media control action %d handled through Windows SMTC", action)
                    with self._lock:
                        self._last_refresh_at = 0.0
                    return True
            except Exception as exc:
                log.debug("SMTC media control failed; using media key: %s", exc)

        handled = self._send_media_key(action)
        if handled:
            log.info("Media control action %d dispatched as Windows media key", action)
        return handled
