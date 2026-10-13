"""Bounded process resource diagnostics for long-running Windows sessions.

Sampling happens every five minutes in AudioSync; never touches Tk or COM.
It records a bounded history, not a growing list of per-frame observations.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time

import psutil


@dataclass(frozen=True)
class ResourceSample:
    timestamp: float
    rss_bytes: int
    private_bytes: int | None
    threads: int
    handles: int | None


class ProcessResourceTracker:
    def __init__(self, process=None, capacity: int = 24):
        self.process = process if process is not None else psutil.Process()
        self.samples = deque(maxlen=max(2, int(capacity)))

    def capture(self, now: float | None = None) -> ResourceSample:
        info = self.process.memory_info()
        private = getattr(info, "private", None)
        # USS is a useful Windows alternative when memory_info lacks private.
        if private is None:
            try:
                private = getattr(self.process.memory_full_info(), "uss", None)
            except (OSError, psutil.Error):
                private = None
        handles = None
        if hasattr(self.process, "num_handles"):
            try:
                handles = self.process.num_handles()
            except (OSError, psutil.Error):
                pass
        sample = ResourceSample(
            timestamp=time.monotonic() if now is None else now,
            rss_bytes=int(info.rss),
            private_bytes=None if private is None else int(private),
            threads=int(self.process.num_threads()),
            handles=handles,
        )
        self.samples.append(sample)
        return sample

    def suspected_growth(self, minimum_bytes: int = 128 * 1024 * 1024,
                         minimum_window_seconds: float = 3600.0) -> bool:
        """Raise a *diagnostic* signal, not a declaration of a leak.

        Require an hour of history, meaningful absolute growth, and near-
        monotonic growth across checkpoints to avoid false alarms on caches.
        """
        if len(self.samples) < 4:
            return False
        entries = list(self.samples)
        if entries[-1].timestamp - entries[0].timestamp < minimum_window_seconds:
            return False
        if entries[-1].rss_bytes - entries[0].rss_bytes < minimum_bytes:
            return False
        increases = sum(b.rss_bytes >= a.rss_bytes for a, b in zip(entries, entries[1:]))
        return increases >= int((len(entries) - 1) * 0.75)

    @staticmethod
    def format(sample: ResourceSample) -> str:
        mib = 1024 * 1024
        private = "unknown" if sample.private_bytes is None else f"{sample.private_bytes / mib:.1f}"
        handles = "n/a" if sample.handles is None else str(sample.handles)
        return (
            f"VuNMix process memory: rss={sample.rss_bytes / mib:.1f}MiB "
            f"private={private}MiB threads={sample.threads} handles={handles}"
        )
