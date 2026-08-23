"""Media-aware controller extension for VuNMix v0.6.0."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app_icon import app_icon_rgb565
from profile_controller import ProfileAppController
from protocol import DisplayMode


log = logging.getLogger("vunmix.media_controller")

# Album art reuses the existing APP_ICON transport and therefore only targets
# an actual 7-bit application-session ID. Unknown SMTC sources are skipped;
# metadata/timeline/control continue to work without artwork in that case.
ARTWORK_SEND_MIN_INTERVAL = 1.5


def _normalise_source(value: str) -> str:
    text = str(value or "").lower().replace(".exe", "")
    return "".join(ch for ch in text if ch.isalnum())


class MediaAppController(ProfileAppController):
    """Adds cached album-art transport without adding load to the sync loop."""

    def __init__(self, config):
        super().__init__(config)
        self._media_art_stop = threading.Event()
        self._media_art_thread: Optional[threading.Thread] = None
        self._last_artwork_key = ""
        self._last_artwork_target = 0
        self._last_artwork_send_at = -1e12
        self._artwork_send_count = 0

    def start(self):
        super().start()
        self._media_art_stop.clear()
        if self._media_art_thread is None or not self._media_art_thread.is_alive():
            self._media_art_thread = threading.Thread(
                target=self._media_artwork_loop,
                daemon=True,
                name="MediaArtworkSync",
            )
            self._media_art_thread.start()

    def stop(self):
        self._media_art_stop.set()
        if self._media_art_thread and self._media_art_thread.is_alive():
            self._media_art_thread.join(timeout=2.0)
        self._media_art_thread = None
        super().stop()

    @property
    def media_artwork_send_count(self) -> int:
        return self._artwork_send_count

    def media_artwork_status(self) -> str:
        snapshot = self.media_service.cached_snapshot()
        if not snapshot.artwork_rgb565:
            return "artwork: none"
        if not self._last_artwork_target:
            return "artwork: cached, source not mapped"
        return (
            f"artwork: 16x16 RGB565, target={self._last_artwork_target}, "
            f"sends={self._artwork_send_count}"
        )

    def _match_media_app_id(self, source_app: str) -> int:
        source = _normalise_source(source_app)
        if not source:
            return 0

        items = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        best_id = 0
        best_score = 0
        for item in items:
            item_name = _normalise_source(getattr(item, "name", ""))
            process_path = _normalise_source(getattr(item, "_process_path", ""))
            if not item_name:
                continue
            score = 0
            if item_name == source:
                score = 100
            elif item_name in source or source in item_name:
                score = 80
            elif item_name in process_path and item_name in source:
                score = 60
            item_id = int(getattr(item, "id", 0) or 0)
            if score > best_score and 0 < item_id <= 127:
                best_score = score
                best_id = item_id
        return best_id

    def _restore_process_icon(self, app_id: int) -> None:
        if app_id <= 0:
            return
        try:
            items = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
            item = next((candidate for candidate in items if int(candidate.id) == app_id), None)
            if not item:
                return
            data = app_icon_rgb565(item.name, getattr(item, "_process_path", ""))
            if self.serial.send_app_icon(app_id, data):
                self._sent_icon_ids.add(app_id)
        except Exception:
            log.debug("Failed to restore process icon id=%d", app_id, exc_info=True)

    def _send_artwork_once(self, *, force: bool = False) -> bool:
        if not self.is_connected or not self.serial.is_connected:
            return False

        snapshot = self.media_service.get_current_snapshot()
        if not snapshot.artwork_key or not snapshot.artwork_rgb565:
            return False

        target = self._match_media_app_id(snapshot.source_app)
        if target <= 0:
            return False

        pair_unchanged = (
            snapshot.artwork_key == self._last_artwork_key
            and target == self._last_artwork_target
        )
        if pair_unchanged and not force:
            return False

        now = time.monotonic()
        if not force and now - self._last_artwork_send_at < ARTWORK_SEND_MIN_INTERVAL:
            return False

        if self._last_artwork_target not in (0, target):
            self._restore_process_icon(self._last_artwork_target)

        # SerialService.send_app_icon limits chunks to 60 bytes and serializes
        # the complete metadata+chunk transaction. 512 bytes means nine chunk
        # frames, and only a new artwork digest/target reaches this path.
        if not self.serial.send_app_icon(target, snapshot.artwork_rgb565, width=16, height=16):
            return False

        self._last_artwork_key = snapshot.artwork_key
        self._last_artwork_target = target
        self._last_artwork_send_at = now
        self._artwork_send_count += 1
        # Prevent the normal app-icon sender from overwriting the fresh album
        # cover on the next periodic session refresh.
        self._sent_icon_ids.add(target)
        log.info(
            "Sent media artwork target=%d source=%s bytes=%d key=%s",
            target,
            snapshot.source_app or "unknown",
            len(snapshot.artwork_rgb565),
            snapshot.artwork_key[:12],
        )
        return True

    def _media_artwork_loop(self):
        while not self._media_art_stop.wait(0.75):
            if not self.is_connected or self._is_sleeping:
                continue
            try:
                self._send_artwork_once()
            except Exception:
                # Artwork is optional. Metadata/audio control must keep working
                # even if a player exposes a malformed thumbnail.
                log.exception("Media artwork sync iteration failed")
