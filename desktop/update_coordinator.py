"""Serialize desktop installer handoff and device firmware writes."""

from __future__ import annotations

import threading
from typing import Callable, Optional


class UpdateCoordinator:
    """One owner for an entire update operation, including app downloads.

    App updates retain their reservation after launching the installer until
    this process exits. A firmware write can therefore never start between
    downloading the installer and its forced application shutdown.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._owner = None
        self._kind = ""

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._owner is not None

    def try_begin(
        self, kind: str, should_start: Optional[Callable[[], bool]] = None,
    ) -> Optional[object]:
        with self._lock:
            if self._owner is not None or (should_start is not None and not should_start()):
                return None
            self._owner = object()
            self._kind = kind
            return self._owner

    def finish(self, owner: object) -> None:
        """Release only this operation; stale cleanup cannot unlock a new one."""
        with self._lock:
            if self._owner is owner:
                self._owner = None
                self._kind = ""


def start_firmware_thread(controller, reservation, worker) -> bool:
    """Keep firmware ownership paired even if the OS cannot create a thread."""
    try:
        threading.Thread(target=worker, daemon=False, name="FirmwareUpdate").start()
    except Exception:
        controller._firmware_updating = False
        controller.updates.finish(reservation)
        raise
    return True
