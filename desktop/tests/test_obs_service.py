import base64
import hashlib
import json
import pathlib
import sys
import unittest
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from obs_service import ObsConnectionError, ObsService, _obs_authentication


class _FakeWebSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False
        self.timeout = None

    def recv(self):
        if not self.incoming:
            raise RuntimeError("no more messages")
        return self.incoming.pop(0)

    def send(self, message):
        self.sent.append(json.loads(message))

    def close(self):
        self.closed = True

    def settimeout(self, value):
        self.timeout = value


class ObsServiceTests(unittest.TestCase):
    def test_authentication_matches_obs_websocket_v5_formula(self):
        password = "secret-password"
        salt = "salt-value"
        challenge = "challenge-value"

        secret = hashlib.sha256((password + salt).encode("utf-8")).digest()
        secret_b64 = base64.b64encode(secret).decode("ascii")
        expected = base64.b64encode(
            hashlib.sha256((secret_b64 + challenge).encode("utf-8")).digest()
        ).decode("ascii")

        self.assertEqual(
            _obs_authentication(password, salt, challenge),
            expected,
        )

    def test_connect_performs_hello_identify_authentication(self):
        hello = {
            "op": 0,
            "d": {
                "obsWebSocketVersion": "5.6.0",
                "rpcVersion": 1,
                "authentication": {
                    "challenge": "challenge",
                    "salt": "salt",
                },
            },
        }
        identified = {"op": 2, "d": {"negotiatedRpcVersion": 1}}
        socket = _FakeWebSocket([json.dumps(hello), json.dumps(identified)])
        service = ObsService(
            password="pw",
            websocket_factory=lambda *_args, **_kwargs: socket,
        )

        with mock.patch.object(service, "_schedule_refresh") as refresh:
            service._connect_once()

        self.assertTrue(service.is_connected)
        self.assertEqual(len(socket.sent), 1)
        identify = socket.sent[0]
        self.assertEqual(identify["op"], 1)
        self.assertEqual(identify["d"]["rpcVersion"], 1)
        self.assertGreater(identify["d"]["eventSubscriptions"], 0)
        self.assertEqual(
            identify["d"]["authentication"],
            _obs_authentication("pw", "salt", "challenge"),
        )
        self.assertEqual(socket.timeout, 1.0)
        refresh.assert_called_once_with(force=True)

    def test_control_methods_map_to_obs_v5_requests(self):
        service = ObsService()
        service.is_connected = True
        service._request = mock.Mock(return_value={})

        service.set_streaming(True)
        service.set_streaming(False)
        service.set_recording(True)
        service.set_recording(False)
        service.switch_scene("Gaming")
        service.set_input_mute("Mic/Aux", True)

        calls = service._request.call_args_list
        self.assertEqual(calls[0], mock.call("StartStream"))
        self.assertEqual(calls[1], mock.call("StopStream"))
        self.assertEqual(calls[2], mock.call("StartRecord"))
        self.assertEqual(calls[3], mock.call("StopRecord"))
        self.assertEqual(
            calls[4],
            mock.call("SetCurrentProgramScene", {"sceneName": "Gaming"}),
        )
        self.assertEqual(
            calls[5],
            mock.call(
                "SetInputMute",
                {"inputName": "Mic/Aux", "inputMuted": True},
            ),
        )

    def test_events_synchronize_stream_record_scene_and_mute(self):
        service = ObsService()
        snapshots = []
        service.set_state_callback(lambda state: snapshots.append(state))

        service._handle_event("StreamStateChanged", {"outputActive": True})
        service._handle_event("RecordStateChanged", {"outputActive": True})
        service._handle_event("CurrentProgramSceneChanged", {"sceneName": "Live"})
        service._handle_event(
            "InputMuteStateChanged",
            {"inputName": "Mic/Aux", "inputMuted": True},
        )

        state = service.snapshot()
        self.assertTrue(state.streaming)
        self.assertTrue(state.recording)
        self.assertEqual(state.current_scene, "Live")
        self.assertTrue(state.input_mutes["Mic/Aux"])
        self.assertGreaterEqual(len(snapshots), 4)

    def test_refresh_populates_scene_mutes_and_stream_stats(self):
        service = ObsService(mic_input="Mic", desktop_input="Desktop")
        responses = {
            "GetStreamStatus": {
                "outputActive": True,
                "outputTimecode": "00:01:02.003",
                "outputDuration": 62003,
                "outputSkippedFrames": 7,
                "outputTotalFrames": 3600,
            },
            "GetRecordStatus": {"outputActive": False},
            "GetSceneList": {
                "currentProgramSceneName": "Camera",
                "scenes": [
                    {"sceneName": "Camera"},
                    {"sceneName": "Desktop"},
                ],
            },
        }

        def request(request_type, request_data=None, timeout=4.0):
            if request_type == "GetInputMute":
                return {
                    "inputMuted": request_data["inputName"] == "Mic",
                }
            return responses[request_type]

        service._request = mock.Mock(side_effect=request)
        state = service.refresh_state()

        self.assertTrue(state.streaming)
        self.assertFalse(state.recording)
        self.assertEqual(state.current_scene, "Camera")
        self.assertEqual(state.scenes, ["Camera", "Desktop"])
        self.assertTrue(state.input_mutes["Mic"])
        self.assertFalse(state.input_mutes["Desktop"])
        self.assertEqual(state.stream_timecode, "00:01:02.003")
        self.assertEqual(state.stream_duration_ms, 62003)
        self.assertEqual(state.dropped_frames, 7)
        self.assertEqual(state.total_frames, 3600)

    def test_disconnect_fails_pending_request_and_resets_state(self):
        service = ObsService()
        service.is_connected = True
        service.is_streaming = True
        service.is_recording = True

        pending = mock.Mock()
        pending.event = mock.Mock()
        pending.error = None
        service._pending["abc"] = pending

        service._mark_disconnected("connection lost", close_socket=False)

        self.assertFalse(service.is_connected)
        self.assertFalse(service.is_streaming)
        self.assertFalse(service.is_recording)
        self.assertEqual(service.last_error, "connection lost")
        self.assertIsInstance(pending.error, ObsConnectionError)
        pending.event.set.assert_called_once()
        self.assertEqual(service._pending, {})


if __name__ == "__main__":
    unittest.main()
