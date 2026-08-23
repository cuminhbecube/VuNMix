import pathlib
import sys
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from controller_state import HardwareStateMixin
from protocol import (
    Command,
    DisplayMode,
    MeterData,
    ModeStates,
    SessionData,
    SessionIndex,
    SessionInfo,
    VolumeData,
)


class FakeAudioItem:
    def __init__(self, item_id, name, volume, *, muted=False, is_default=False):
        self.id = item_id
        self.name = name
        self.volume = volume
        self.is_muted = muted
        self.is_default = is_default

    def to_session_data(self):
        return SessionData(
            name=self.name,
            data=VolumeData(
                id=self.id,
                is_default=self.is_default,
                volume=self.volume,
                is_muted=self.is_muted,
            ),
        )


class FakeAudio:
    def __init__(self, items_by_mode):
        self.items_by_mode = items_by_mode
        self.volume_calls = []
        self.default_calls = []

    def get_sessions_for_mode(self, mode):
        return list(self.items_by_mode.get(mode, []))

    def get_session_count(self, mode):
        return len(self.get_sessions_for_mode(mode))

    def set_volume(self, mode, index, volume, is_muted):
        self.volume_calls.append((mode, index, volume, is_muted))

    def set_default_device(self, mode, index):
        self.default_calls.append((mode, index))
        items = self.items_by_mode.get(mode, [])
        for i, item in enumerate(items):
            item.is_default = i == index


class FakeSerial:
    def __init__(self):
        self.session_infos = []
        self.sessions = []
        self.mode_states = []

    def send_session_info(self, info):
        self.session_infos.append(info)
        return True

    def send_session(self, cmd, session):
        self.sessions.append((cmd, session))
        return True

    def send_mode_states(self, states):
        self.mode_states.append(states)
        return True

    def send_app_icon(self, *args, **kwargs):
        return True


class FakeMediaService:
    def execute_control(self, action):
        pass


class ControllerHarness(HardwareStateMixin):
    def __init__(self, audio, mode, current_session, current_index=0):
        self.audio = audio
        self.serial = FakeSerial()
        self.media_service = FakeMediaService()
        self._session_info = SessionInfo(
            mode=mode,
            current=current_index,
            sessions=[1, 1, 1],
        )
        self._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        self._sessions[SessionIndex.INDEX_CURRENT] = current_session
        self._mode_states = ModeStates()
        self._meter_data = MeterData()
        self._sent_icon_ids = set()


class VolumeIdentityGuardTests(unittest.TestCase):
    def test_delayed_app_volume_after_switch_to_output_is_dropped(self):
        output = FakeAudioItem(11, "Speakers", 24, is_default=True)
        audio = FakeAudio({DisplayMode.MODE_OUTPUT: [output]})
        controller = ControllerHarness(
            audio,
            DisplayMode.MODE_OUTPUT,
            output.to_session_data(),
        )

        # Reproduce the race: SESSION_INFO has already moved the controller to
        # Output and refreshed CURRENT_SESSION, then an old app frame arrives.
        stale_app_volume = VolumeData(id=77, volume=83, is_muted=False)
        controller._on_hw_message(
            Command.VOLUME_CURR_CHANGE,
            stale_app_volume.pack(),
        )

        self.assertEqual(audio.volume_calls, [])
        self.assertEqual(audio.default_calls, [])
        self.assertEqual(
            controller._sessions[SessionIndex.INDEX_CURRENT].data.id,
            11,
        )
        self.assertEqual(
            controller._sessions[SessionIndex.INDEX_CURRENT].data.volume,
            24,
        )

    def test_matching_current_session_volume_is_applied(self):
        output = FakeAudioItem(11, "Speakers", 24, is_default=True)
        audio = FakeAudio({DisplayMode.MODE_OUTPUT: [output]})
        controller = ControllerHarness(
            audio,
            DisplayMode.MODE_OUTPUT,
            output.to_session_data(),
        )

        current_volume = VolumeData(id=11, volume=61, is_muted=True)
        controller._on_hw_message(
            Command.VOLUME_CURR_CHANGE,
            current_volume.pack(),
        )

        self.assertEqual(
            audio.volume_calls,
            [(DisplayMode.MODE_OUTPUT, 0, 61, True)],
        )
        self.assertEqual(
            controller._sessions[SessionIndex.INDEX_CURRENT].data.volume,
            61,
        )
        self.assertTrue(
            controller._sessions[SessionIndex.INDEX_CURRENT].data.is_muted
        )

    def test_matching_identity_wins_over_stale_numeric_index(self):
        other = FakeAudioItem(12, "HDMI", 30)
        selected = FakeAudioItem(11, "Speakers", 24, is_default=True)
        audio = FakeAudio({DisplayMode.MODE_OUTPUT: [other, selected]})
        controller = ControllerHarness(
            audio,
            DisplayMode.MODE_OUTPUT,
            selected.to_session_data(),
            current_index=0,
        )

        controller._on_hw_message(
            Command.VOLUME_CURR_CHANGE,
            VolumeData(id=11, volume=55).pack(),
        )

        self.assertEqual(
            audio.volume_calls,
            [(DisplayMode.MODE_OUTPUT, 1, 55, False)],
        )

    def test_stale_default_request_cannot_change_windows_default(self):
        output = FakeAudioItem(11, "Speakers", 24, is_default=False)
        audio = FakeAudio({DisplayMode.MODE_OUTPUT: [output]})
        controller = ControllerHarness(
            audio,
            DisplayMode.MODE_OUTPUT,
            output.to_session_data(),
        )

        controller._on_hw_message(
            Command.VOLUME_CURR_CHANGE,
            VolumeData(id=77, is_default=True, volume=90).pack(),
        )

        self.assertEqual(audio.volume_calls, [])
        self.assertEqual(audio.default_calls, [])


if __name__ == "__main__":
    unittest.main()
