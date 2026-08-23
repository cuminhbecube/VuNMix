"""VuNMix OBS Studio Service — OBS WebSocket v5 integration.

Implements the OBS WebSocket v5 Hello/Identify authentication flow, request /
response correlation, event subscriptions, reconnect backoff and common stream,
record, scene and audio-input controls.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


log = logging.getLogger("vunmix.obs")

# General | Scenes | Inputs | Outputs
EVENT_SUBSCRIPTIONS = 1 | 4 | 8 | 64
RPC_VERSION = 1


class ObsError(RuntimeError):
    pass


class ObsConnectionError(ObsError):
    pass


class ObsRequestError(ObsError):
    def __init__(self, request_type: str, code: int, comment: str = ""):
        self.request_type = request_type
        self.code = int(code)
        self.comment = comment or "OBS rejected the request"
        super().__init__(f"{request_type} failed ({self.code}): {self.comment}")


@dataclass
class ObsState:
    connected: bool = False
    streaming: bool = False
    recording: bool = False
    current_scene: str = ""
    scenes: List[str] = field(default_factory=list)
    input_mutes: Dict[str, bool] = field(default_factory=dict)
    stream_timecode: str = ""
    stream_duration_ms: int = 0
    dropped_frames: int = 0
    total_frames: int = 0
    reconnecting: bool = False
    last_error: str = ""


@dataclass
class _PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    response: Optional[dict] = None
    error: Optional[BaseException] = None


def _obs_authentication(password: str, salt: str, challenge: str) -> str:
    """Return the OBS WebSocket v5 authentication response."""
    secret = hashlib.sha256((password + salt).encode("utf-8")).digest()
    secret_b64 = base64.b64encode(secret)
    auth = hashlib.sha256(secret_b64 + challenge.encode("utf-8")).digest()
    return base64.b64encode(auth).decode("ascii")


class ObsService:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
        *,
        mic_input: str = "Mic/Aux",
        desktop_input: str = "Desktop Audio",
        websocket_factory=None,
    ):
        self.host = os.environ.get("VUNMIX_OBS_HOST", host)
        self.port = int(os.environ.get("VUNMIX_OBS_PORT", str(port)))
        self.password = os.environ.get("VUNMIX_OBS_PASSWORD", password)
        self.mic_input = os.environ.get("VUNMIX_OBS_MIC_INPUT", mic_input)
        self.desktop_input = os.environ.get("VUNMIX_OBS_DESKTOP_INPUT", desktop_input)
        self._websocket_factory = websocket_factory

        # Preserve the public attributes used by existing controller code.
        self.is_connected = False
        self.is_streaming = False
        self.is_recording = False
        self.current_scene = ""
        self.scenes: List[str] = []
        self.input_mutes: Dict[str, bool] = {}
        self.stream_timecode = ""
        self.stream_duration_ms = 0
        self.dropped_frames = 0
        self.total_frames = 0
        self.last_error = ""

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._pending_lock = threading.Lock()
        self._pending: Dict[str, _PendingRequest] = {}
        self._on_state_change: Optional[Callable[[bool, bool], None]] = None
        self._on_state: Optional[Callable[[ObsState], None]] = None
        self._refresh_lock = threading.Lock()
        self._refresh_in_progress = False
        self._last_refresh = 0.0

    def set_callback(self, cb: Callable[[bool, bool], None]):
        """Backward-compatible stream/record callback."""
        self._on_state_change = cb

    def set_state_callback(self, cb: Callable[[ObsState], None]):
        self._on_state = cb

    def snapshot(self) -> ObsState:
        with self._state_lock:
            return ObsState(
                connected=self.is_connected,
                streaming=self.is_streaming,
                recording=self.is_recording,
                current_scene=self.current_scene,
                scenes=list(self.scenes),
                input_mutes=dict(self.input_mutes),
                stream_timecode=self.stream_timecode,
                stream_duration_ms=self.stream_duration_ms,
                dropped_frames=self.dropped_frames,
                total_frames=self.total_frames,
                reconnecting=self._running and not self.is_connected,
                last_error=self.last_error,
            )

    def _notify(self):
        state = self.snapshot()
        if self._on_state_change:
            try:
                self._on_state_change(state.streaming, state.recording)
            except Exception:
                log.exception("OBS legacy state callback failed")
        if self._on_state:
            try:
                self._on_state(state)
            except Exception:
                log.exception("OBS state callback failed")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker,
            name="ObsServiceWorker",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._running = False
        self._close_socket("service stopped")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def wait_until_connected(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if self.is_connected:
                return True
            time.sleep(0.05)
        return self.is_connected

    def _create_connection(self):
        if self._websocket_factory is not None:
            return self._websocket_factory(
                f"ws://{self.host}:{self.port}",
                timeout=3.0,
            )
        import websocket

        return websocket.create_connection(
            f"ws://{self.host}:{self.port}",
            timeout=3.0,
            enable_multithread=True,
        )

    @staticmethod
    def _decode_message(raw) -> dict:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ObsConnectionError("OBS returned a non-text WebSocket message")
        message = json.loads(raw)
        if not isinstance(message, dict) or "op" not in message:
            raise ObsConnectionError("Invalid OBS WebSocket message")
        return message

    def _connect_once(self):
        ws = self._create_connection()
        try:
            hello = self._decode_message(ws.recv())
            if hello.get("op") != 0:
                raise ObsConnectionError("OBS did not send Hello")
            hello_data = hello.get("d") or {}
            server_rpc = int(hello_data.get("rpcVersion", RPC_VERSION))
            identify_data = {
                "rpcVersion": min(RPC_VERSION, server_rpc),
                "eventSubscriptions": EVENT_SUBSCRIPTIONS,
            }
            auth = hello_data.get("authentication")
            if auth:
                identify_data["authentication"] = _obs_authentication(
                    self.password,
                    str(auth.get("salt", "")),
                    str(auth.get("challenge", "")),
                )

            ws.send(json.dumps({"op": 1, "d": identify_data}))
            identified = self._decode_message(ws.recv())
            if identified.get("op") != 2:
                raise ObsConnectionError("OBS authentication/Identify failed")

            try:
                ws.settimeout(1.0)
            except Exception:
                pass

            self._ws = ws
            with self._state_lock:
                self.is_connected = True
                self.last_error = ""
            log.info(
                "Connected to OBS WebSocket v5 at %s:%d (server=%s)",
                self.host,
                self.port,
                hello_data.get("obsWebSocketVersion", "unknown"),
            )
            self._notify()
            self._schedule_refresh(force=True)
        except Exception:
            try:
                ws.close()
            except Exception:
                pass
            raise

    def _worker(self):
        reconnect_delay = 1.0
        while self._running:
            if not self.is_connected:
                try:
                    self._connect_once()
                    reconnect_delay = 1.0
                except Exception as exc:
                    self.last_error = str(exc)
                    log.warning("OBS connect failed: %s", exc)
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 1.7, 10.0)
                    continue

            ws = self._ws
            if ws is None:
                self._mark_disconnected("OBS socket unavailable")
                continue

            try:
                raw = ws.recv()
                if raw in (None, ""):
                    raise ObsConnectionError("OBS closed the WebSocket")
                self._handle_message(self._decode_message(raw))
            except Exception as exc:
                if self._is_timeout(exc):
                    self._schedule_refresh()
                    continue
                log.warning("OBS connection lost: %s", exc)
                self._mark_disconnected(str(exc))

    @staticmethod
    def _is_timeout(exc: BaseException) -> bool:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        return "timeout" in name or "timed out" in text

    def _close_socket(self, reason: str = ""):
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if self.is_connected:
            self._mark_disconnected(reason or "socket closed", close_socket=False)

    def _mark_disconnected(self, reason: str, *, close_socket: bool = True):
        if close_socket:
            ws = self._ws
            self._ws = None
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
        with self._state_lock:
            self.is_connected = False
            self.is_streaming = False
            self.is_recording = False
            self.last_error = reason
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        error = ObsConnectionError(reason or "OBS disconnected")
        for item in pending:
            item.error = error
            item.event.set()
        self._notify()

    def _send_json(self, message: dict):
        ws = self._ws
        if not self.is_connected or ws is None:
            raise ObsConnectionError("OBS is not connected")
        with self._send_lock:
            ws.send(json.dumps(message))

    def _request(self, request_type: str, request_data: Optional[dict] = None, timeout: float = 4.0) -> dict:
        request_id = uuid.uuid4().hex
        pending = _PendingRequest()
        with self._pending_lock:
            self._pending[request_id] = pending
        try:
            self._send_json({
                "op": 6,
                "d": {
                    "requestType": request_type,
                    "requestId": request_id,
                    "requestData": request_data or {},
                },
            })
            if not pending.event.wait(timeout=max(0.1, timeout)):
                raise ObsConnectionError(f"OBS request timed out: {request_type}")
            if pending.error:
                raise pending.error
            response = pending.response or {}
            status = response.get("requestStatus") or {}
            if not status.get("result", False):
                raise ObsRequestError(
                    request_type,
                    int(status.get("code", 0)),
                    str(status.get("comment", "")),
                )
            return response.get("responseData") or {}
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def _handle_message(self, message: dict):
        op = message.get("op")
        data = message.get("d") or {}
        if op == 7:
            request_id = str(data.get("requestId", ""))
            with self._pending_lock:
                pending = self._pending.get(request_id)
            if pending:
                pending.response = data
                pending.event.set()
        elif op == 5:
            self._handle_event(str(data.get("eventType", "")), data.get("eventData") or {})

    def _handle_event(self, event_type: str, data: dict):
        changed = False
        with self._state_lock:
            if event_type == "StreamStateChanged":
                self.is_streaming = bool(data.get("outputActive", False))
                changed = True
            elif event_type == "RecordStateChanged":
                self.is_recording = bool(data.get("outputActive", False))
                changed = True
            elif event_type == "CurrentProgramSceneChanged":
                self.current_scene = str(data.get("sceneName", ""))
                changed = True
            elif event_type == "InputMuteStateChanged":
                name = str(data.get("inputName", ""))
                if name:
                    self.input_mutes[name] = bool(data.get("inputMuted", False))
                    changed = True
            elif event_type in ("SceneCreated", "SceneRemoved", "SceneListChanged"):
                self._schedule_refresh(force=True)
            elif event_type == "ExitStarted":
                changed = False

        if event_type == "ExitStarted":
            self._mark_disconnected("OBS is exiting")
            return
        if changed:
            self._notify()

    def _schedule_refresh(self, *, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_refresh < 5.0:
            return
        with self._refresh_lock:
            if self._refresh_in_progress:
                return
            self._refresh_in_progress = True
            self._last_refresh = now

        def run():
            try:
                self.refresh_state()
            except Exception as exc:
                if self.is_connected:
                    log.debug("OBS state refresh failed: %s", exc)
            finally:
                with self._refresh_lock:
                    self._refresh_in_progress = False

        threading.Thread(target=run, daemon=True, name="ObsStateRefresh").start()

    def refresh_state(self):
        stream = self._request("GetStreamStatus")
        record = self._request("GetRecordStatus")
        scene_list = self._request("GetSceneList")

        mutes = {}
        for input_name in (self.mic_input, self.desktop_input):
            if not input_name:
                continue
            try:
                mute = self._request("GetInputMute", {"inputName": input_name})
                mutes[input_name] = bool(mute.get("inputMuted", False))
            except ObsRequestError as exc:
                # Default OBS input names are user-configurable; a missing input
                # is not a connection failure.
                log.debug("OBS input unavailable (%s): %s", input_name, exc)

        with self._state_lock:
            self.is_streaming = bool(stream.get("outputActive", False))
            self.is_recording = bool(record.get("outputActive", False))
            self.current_scene = str(scene_list.get("currentProgramSceneName", ""))
            scenes = scene_list.get("scenes") or []
            self.scenes = [
                str(item.get("sceneName", ""))
                for item in scenes
                if isinstance(item, dict) and item.get("sceneName")
            ]
            self.input_mutes.update(mutes)
            self.stream_timecode = str(stream.get("outputTimecode", ""))
            self.stream_duration_ms = int(stream.get("outputDuration", 0) or 0)
            self.dropped_frames = int(stream.get("outputSkippedFrames", 0) or 0)
            self.total_frames = int(stream.get("outputTotalFrames", 0) or 0)
        self._notify()
        return self.snapshot()

    def set_streaming(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self.is_streaming:
            return
        self._request("StartStream" if enabled else "StopStream")
        with self._state_lock:
            self.is_streaming = enabled
        self._notify()

    def toggle_streaming(self):
        self.set_streaming(not self.is_streaming)

    def set_recording(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self.is_recording:
            return
        self._request("StartRecord" if enabled else "StopRecord")
        with self._state_lock:
            self.is_recording = enabled
        self._notify()

    def toggle_recording(self):
        self.set_recording(not self.is_recording)

    def switch_scene(self, scene_name: str):
        scene_name = str(scene_name or "").strip()
        if not scene_name:
            raise ValueError("scene_name is required")
        self._request("SetCurrentProgramScene", {"sceneName": scene_name})
        with self._state_lock:
            self.current_scene = scene_name
        self._notify()

    def set_input_mute(self, input_name: str, muted: bool):
        input_name = str(input_name or "").strip()
        if not input_name:
            raise ValueError("input_name is required")
        muted = bool(muted)
        self._request("SetInputMute", {"inputName": input_name, "inputMuted": muted})
        with self._state_lock:
            self.input_mutes[input_name] = muted
        self._notify()

    def toggle_input_mute(self, input_name: str):
        current = self.input_mutes.get(input_name)
        if current is None:
            response = self._request("GetInputMute", {"inputName": input_name})
            current = bool(response.get("inputMuted", False))
        self.set_input_mute(input_name, not current)

    def set_mic_muted(self, muted: bool):
        self.set_input_mute(self.mic_input, muted)

    def set_desktop_muted(self, muted: bool):
        self.set_input_mute(self.desktop_input, muted)
