"""Bounded, connection-scoped device appearance transactions; no Tk or COM.

The PC preference is separate from the device's confirmed configuration.
Only a correlated UI_THEME response can confirm a change. A silent old
firmware disables this optional feature without affecting transport health.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time

from protocol import (
    DeviceTheme, ThemeOperation, ThemeRequest, ThemeResponse, ThemeStatus,
    THEME_SCHEMA_VERSION,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThemeSyncSnapshot:
    desired_id: int | None
    confirmed_id: int | None
    supported_mask: int | None
    phase: str
    message: str
    connected: bool


@dataclass
class _Pending:
    request: ThemeRequest
    generation: int
    attempts: int = 0
    deadline: float = 0.0


class DeviceThemeCoordinator:
    """One worker, one current request, and the latest saved user preference.

    ``poll`` is also exposed for deterministic tests with an injected clock;
    normal application callers only start/stop, set desired state, and deliver
    lifecycle/response notifications. The sender must guard its actual write
    with the supplied transport generation, not merely check it beforehand.
    """

    def __init__(self, sender, desired_id=None, *, clock=time.monotonic,
                 timeout=1.5, max_attempts=3):
        self._sender = sender
        self._clock = clock
        self._timeout = max(0.01, float(timeout))
        self._max_attempts = max(1, int(max_attempts))
        self._condition = threading.Condition(threading.RLock())
        self._desired = self._valid_id(desired_id)
        self._confirmed = None
        self._supported = None
        self._generation = None
        self._pending = None
        self._query_needed = False
        self._set_needed = False
        self._next_id = 0
        self._phase = "disconnected"
        self._message = "Connect VuNMix to verify its display theme."
        self._running = False
        self._worker_epoch = 0
        self._thread = None

    @staticmethod
    def _valid_id(value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Device theme must be an integer ID or unset")
        return int(DeviceTheme(value))

    def snapshot(self) -> ThemeSyncSnapshot:
        with self._condition:
            return ThemeSyncSnapshot(self._desired, self._confirmed, self._supported,
                                     self._phase, self._message, self._generation is not None)

    def start(self):
        with self._condition:
            if self._running:
                return
            self._running = True
            self._worker_epoch += 1
            self._thread = threading.Thread(target=self._run, args=(self._worker_epoch,),
                                            name="DeviceThemeSync", daemon=True)
            self._thread.start()

    def stop(self):
        with self._condition:
            self._running = False
            self._worker_epoch += 1
            self.disconnected()
            worker = self._thread
            self._condition.notify_all()
        if worker and worker is not threading.current_thread():
            worker.join(timeout=1.0)

    def connected(self, generation: int):
        with self._condition:
            if self._generation == generation:
                return
            self._generation = generation
            self._pending = None
            self._confirmed = self._supported = None
            self._query_needed = True
            self._set_needed = False
            self._state("querying", "Checking device theme support…")

    def disconnected(self):
        with self._condition:
            self._generation = None
            self._pending = None
            self._confirmed = self._supported = None
            self._query_needed = self._set_needed = False
            self._state("disconnected", "Saved on PC; waiting for a device."
                        if self._desired is not None else "Connect VuNMix to verify its display theme.")

    def set_desired(self, value):
        value = self._valid_id(value)
        with self._condition:
            if value == self._desired and self._phase not in ("error", "timeout"):
                return
            self._desired = value
            if self._pending and self._pending.request.operation == ThemeOperation.SET:
                # The old SET may already be on the wire. Send the latest value
                # even if it equals an older confirmed value; do not assume the
                # superseded request had no effect.
                self._pending = None
            if self._generation is None:
                self.disconnected()
            elif self._supported is None or value is None:
                self._query_needed = True
                self._set_needed = False
                self._state("querying", "Checking device theme support…")
            else:
                self._set_needed = True
                self._state("applying", "Saved on PC; applying the selected theme…")

    def retry(self):
        """Requery after an explicit retry/resume; never restart the link."""
        with self._condition:
            if self._generation is None:
                return
            self._pending = None
            self._query_needed = True
            self._set_needed = False
            self._state("querying", "Checking device theme support…")

    def _state(self, phase, message):
        self._phase, self._message = phase, message
        self._condition.notify_all()

    def _new_request(self, operation, theme_id):
        self._next_id = self._next_id % 65535 + 1
        return _Pending(ThemeRequest(operation, theme_id, self._next_id), self._generation)

    def poll(self):
        """Perform at most one bounded serial write; all waits are in the worker."""
        with self._condition:
            if self._generation is None:
                return None
            now = self._clock()
            pending = self._pending
            if pending is not None and now < pending.deadline:
                return None
            if pending is not None and pending.attempts >= self._max_attempts:
                self._pending = None
                self._query_needed = self._set_needed = False
                if pending.request.operation == ThemeOperation.QUERY:
                    self._state("unsupported", "Device did not report theme support. Update firmware or retry.")
                else:
                    self._state("timeout", "Saved on PC; device confirmation timed out. Retry.")
                return None
            if pending is None:
                if self._query_needed:
                    pending = self._new_request(ThemeOperation.QUERY, 0)
                elif self._set_needed and self._desired is not None:
                    if self._supported is None:
                        return None
                    if not self._supported & (1 << self._desired):
                        self._set_needed = False
                        self._state("unsupported", "This theme needs newer firmware. The saved choice is kept on PC.")
                        return None
                    pending = self._new_request(ThemeOperation.SET, self._desired)
                else:
                    return None
                self._pending = pending
            pending.attempts += 1
            pending.deadline = now + self._timeout
        # Never hold the coordinator lock while serial callbacks can disconnect.
        try:
            self._sender(pending.request, pending.generation)
        except Exception:
            log.exception("Device theme request failed; bounded retry remains pending")
        return pending.request

    def handle_response(self, payload: bytes, generation: int) -> bool:
        try:
            response = ThemeResponse.unpack(payload)
        except (ValueError, TypeError):
            log.warning("Ignoring malformed device theme response")
            return False
        with self._condition:
            pending = self._pending
            if (pending is None or generation != self._generation
                    or generation != pending.generation
                    or response.request_id != pending.request.request_id):
                return False
            if response.schema_version != THEME_SCHEMA_VERSION:
                self._pending = None
                self._query_needed = self._set_needed = False
                self._state("unsupported", "Device theme schema is not supported by this desktop version.")
                return True
            if response.status == ThemeStatus.BUSY:
                self._state(self._phase, "Device is busy; retrying theme synchronization…")
                return True
            self._pending = None
            self._query_needed = self._set_needed = False
            self._supported = response.supported_mask
            if response.status not in (ThemeStatus.APPLIED, ThemeStatus.SAVED_DEFERRED):
                self._state("unsupported" if response.status == ThemeStatus.UNSUPPORTED else "error",
                            "Device does not support this theme." if response.status == ThemeStatus.UNSUPPORTED
                            else "Saved on PC; device could not confirm the theme. Retry.")
                return True
            if (not response.supported_mask & (1 << response.configured_theme_id)
                    or (pending.request.operation == ThemeOperation.SET
                        and response.configured_theme_id != pending.request.theme_id)):
                self._state("error", "Device returned an inconsistent theme confirmation. Retry.")
                return True
            self._confirmed = response.configured_theme_id
            if self._desired is not None and self._desired != self._confirmed:
                self._set_needed = True
                self._state("applying", "Saved on PC; applying the selected theme…")
            elif response.status == ThemeStatus.SAVED_DEFERRED:
                self._state("deferred", "Saved on device; display changes after clock or sleep.")
            else:
                self._state("applied", "Confirmed on device.")
            return True

    def _run(self, epoch):
        while True:
            with self._condition:
                if not self._running or epoch != self._worker_epoch:
                    return
            self.poll()
            with self._condition:
                if not self._running or epoch != self._worker_epoch:
                    return
                delay = 1.0
                if self._pending is not None:
                    delay = max(0.01, min(1.0, self._pending.deadline - self._clock()))
                elif self._generation is not None and (self._query_needed or self._set_needed):
                    delay = 0.01
                self._condition.wait(timeout=delay)
