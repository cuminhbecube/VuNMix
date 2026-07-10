import pathlib
import sys
import threading
import types
import unittest
from dataclasses import dataclass


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

# The selection helper is pure, but app_controller also owns Windows-only
# integration classes. Minimal stubs keep this regression test independent
# from a particular Python/pywin32 installation.
for module_name in ("win32api", "win32con", "win32gui"):
    sys.modules.setdefault(module_name, types.ModuleType(module_name))

previous_comtypes = sys.modules.get("comtypes")
comtypes_stub = types.ModuleType("comtypes")
comtypes_stub.CoInitialize = lambda: None
comtypes_stub.CoUninitialize = lambda: None
sys.modules["comtypes"] = comtypes_stub

previous_audio_service = sys.modules.get("audio_service")
audio_service_stub = types.ModuleType("audio_service")
audio_service_stub.AudioService = object
sys.modules["audio_service"] = audio_service_stub

try:
    import serial  # noqa: F401
except ModuleNotFoundError:
    serial_stub = types.ModuleType("serial")
    serial_stub.SerialException = OSError
    serial_stub.Serial = object
    sys.modules["serial"] = serial_stub

from app_controller import AppController
if previous_audio_service is None:
    del sys.modules["audio_service"]
else:
    sys.modules["audio_service"] = previous_audio_service
if previous_comtypes is None:
    del sys.modules["comtypes"]
else:
    sys.modules["comtypes"] = previous_comtypes

from protocol import (
    Command,
    DisplayMode,
    SessionData,
    SessionIndex,
    SessionInfo,
    VolumeData,
    ModeStates,
)


@dataclass
class Item:
    is_default: bool = False
    name: str = "Device"
    volume: int = 50
    id: int = 1

    def to_session_data(self):
        return SessionData(
            name=self.name,
            data=VolumeData(
                id=self.id,
                is_default=self.is_default,
                volume=self.volume,
            ),
        )


class CachedAudio:
    def __init__(self, items):
        self.items = items
        self.refresh_calls = 0

    def refresh(self):
        self.refresh_calls += 1

    def get_sessions_for_mode(self, _mode):
        return list(self.items)


class RecordingSerial:
    def __init__(self):
        self.info = []
        self.sessions = []
        self.mode_states = []

    def send_session_info(self, info):
        self.info.append(info)

    def send_session(self, command, session):
        self.sessions.append((command, session))

    def send_mode_states(self, states):
        self.mode_states.append(states)


class PreferredSessionTests(unittest.TestCase):
    def test_incompatible_firmware_is_update_only(self):
        controller = AppController.__new__(AppController)
        controller.serial = object()
        controller._connection_lock = threading.RLock()
        controller._device_connected = False
        controller._update_only_connected = False

        controller._on_version("v0.4-VU")
        controller._on_version("v0.4-VU;P=2")

        self.assertFalse(controller._device_connected)
        self.assertTrue(controller._update_only_connected)

    def test_peak_meter_db_mapping(self):
        self.assertEqual(AppController._peak_to_level(0.0), 0)
        self.assertEqual(AppController._peak_to_level(1.0), 100)
        self.assertGreater(AppController._peak_to_level(0.1), 60)

    def test_output_uses_windows_default_even_at_nonzero_index(self):
        items = [Item(), Item(is_default=True), Item()]
        self.assertEqual(
            AppController._preferred_index(DisplayMode.MODE_OUTPUT, items),
            1,
        )

    def test_input_uses_windows_default_even_when_fallback_differs(self):
        items = [Item(), Item(), Item(is_default=True)]
        self.assertEqual(
            AppController._preferred_index(DisplayMode.MODE_INPUT, items, 1),
            2,
        )

    def test_application_preserves_valid_selection(self):
        items = [Item(), Item(), Item()]
        self.assertEqual(
            AppController._preferred_index(DisplayMode.MODE_APPLICATION, items, 2),
            2,
        )

    def test_missing_default_clamps_fallback(self):
        items = [Item(), Item()]
        self.assertEqual(
            AppController._preferred_index(DisplayMode.MODE_OUTPUT, items, 99),
            1,
        )
        self.assertEqual(
            AppController._preferred_index(DisplayMode.MODE_OUTPUT, [], 99),
            0,
        )

    def test_mode_change_uses_cache_without_blocking_audio_refresh(self):
        controller = AppController.__new__(AppController)
        controller.audio = CachedAudio([
            Item(name="First", id=1),
            Item(is_default=True, name="Default input", volume=74, id=2),
        ])
        controller.serial = RecordingSerial()
        controller._session_info = SessionInfo(mode=DisplayMode.MODE_OUTPUT)
        controller._sessions = [
            SessionData() for _ in range(SessionIndex.INDEX_MAX)
        ]

        info = SessionInfo(
            mode=DisplayMode.MODE_INPUT,
            current=0,
            sessions=[1, 2, 1],
        )
        controller._handle_session_info_from_hw(info)

        self.assertEqual(controller.audio.refresh_calls, 0)
        self.assertEqual(controller._session_info.current, 1)
        self.assertEqual(controller.serial.info[-1].current, 1)
        current_commands = [
            session for command, session in controller.serial.sessions
            if command == Command.CURRENT_SESSION
        ]
        self.assertEqual(current_commands[-1].name, "Default input")

    def test_health_mode_does_not_push_audio_sessions(self):
        controller = AppController.__new__(AppController)
        controller.audio = CachedAudio([Item(name="Speaker", id=1)])
        controller.serial = RecordingSerial()
        controller._session_info = SessionInfo(mode=DisplayMode.MODE_GAME, current=2)
        controller._mode_states = ModeStates()
        controller._sessions = [
            SessionData() for _ in range(SessionIndex.INDEX_MAX)
        ]

        controller._handle_session_info_from_hw(
            SessionInfo(mode=DisplayMode.MODE_HEALTH, current=3, sessions=[2, 3, 4])
        )

        self.assertEqual(controller._session_info.mode, DisplayMode.MODE_HEALTH)
        self.assertEqual(controller._session_info.current, 0)
        self.assertEqual(controller.serial.info, [])
        self.assertEqual(controller.serial.mode_states, [])
        self.assertEqual(controller.serial.sessions, [])
        self.assertEqual(controller.audio.refresh_calls, 0)


if __name__ == "__main__":
    unittest.main()
