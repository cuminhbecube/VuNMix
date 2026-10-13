"""Bounded identity-aware Windows audio action dispatcher.

Never run Windows COM calls on Tk's event loop. Drop superseded requests,
never start a worker per slider movement, and never change volume on tab change.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import queue
import threading

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioIntent:
    action: str
    mode: int
    index: int
    item: object
    volume: int = 0
    muted: bool = False

    def __post_init__(self):
        if self.action not in ("volume", "default"):
            raise ValueError(f"unsupported Windows audio action: {self.action}")


class AudioActionDispatcher:
    def __init__(self, audio_service, max_pending: int = 16):
        self.audio = audio_service
        self._queue = queue.Queue(maxsize=max(1, max_pending))
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    def submit(self, intent: AudioIntent) -> bool:
        with self._lock:
            if self._stop.is_set():
                return False
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._worker, daemon=True, name="VuNMixUiAudio"
                )
                self._thread.start()
            try:
                self._queue.put_nowait(intent)
            except queue.Full:
                # The oldest command loses to the newest explicitly requested
                # state; do not allow a background queue to grow indefinitely.
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(intent)
                except queue.Full:
                    return False
            return True

    def close(self):
        with self._lock:
            self._stop.set()

    def _worker(self):
        while not self._stop.is_set():
            try:
                request = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                # The expected_item check in AudioService resolves by stable
                # endpoint/session identity, not by the stale list index.
                if request.action == "volume":
                    self.audio.set_volume(
                        request.mode, request.index, request.volume, request.muted,
                        expected_item=request.item,
                    )
                else:
                    self.audio.set_default_device(
                        request.mode, request.index, expected_item=request.item
                    )
            except Exception:
                log.exception("VuNMix UI audio operation failed")
            finally:
                self._queue.task_done()
