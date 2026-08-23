import pathlib
import sys
import threading
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from controller_state import HardwareStateMixin
from controller_workers import SyncWorkersMixin
from protocol import DisplayMode, SessionData, SessionIndex, SessionInfo, VolumeData


class _Item:
    def __init__(self, item_id, name, volume, muted=False):
        self.id = item_id
        self.name = name
        self.volume = volume
        self.is_muted = muted
        self.is_default = False

    def to_session_data(self):
        return SessionData(
            name=self.name,
            data=VolumeData(
                id=self.id,
                volume=self.volume,
                is_muted=self.is_muted,
            ),
        )


class _Audio:
    def __init__(self, items, on_read=None):
        self.items = list(items)
        self.on_read = on_read
        self.read_indices = []

    def get_sessions_for_mode(self, mode):
        return list(self.items)

    def read_current_volume(self, mode, index):
        self.read_indices.append((mode, index))
        if self.on_read:
            self.on_read()
        return self.items[index].to_session_data().data


class _Serial:
    def __init__(self):
        self.volume_frames = []

    def send_volume(self, command, volume):
        self.volume_frames.append((command, volume))
        return True


class _Harness(HardwareStateMixin, SyncWorkersMixin):
    def __init__(self, audio, selected, current_index=0):
        self.audio = audio
        self.serial = _Serial()
        self._state_lock = threading.RLock()
        self._selection_epoch = 10
        self._selection_transitioning = False
        self._session_info = SessionInfo(
            mode=DisplayMode.MODE_OUTPUT,
            current=current_index,
            sessions=[len(audio.items), 1, 1],
        )
        self._sessions = [SessionData() for _ in range(SessionIndex.INDEX_MAX)]
        self._sessions[SessionIndex.INDEX_CURRENT] = selected.to_session_data()


class PeriodicSelectionSyncTests(unittest.TestCase):
    def test_stable_selection_syncs_volume(self):
        selected = _Item(11, "Speakers", 55)
        audio = _Audio([selected])
        controller = _Harness(audio, _Item(11, "Speakers", 24))

        self.assertTrue(controller._sync_current_volume_once())
        self.assertEqual(audio.read_indices, [(DisplayMode.MODE_OUTPUT, 0)])
        self.assertEqual(len(controller.serial.volume_frames), 1)
        self.assertEqual(
            controller._sessions[SessionIndex.INDEX_CURRENT].data.volume,
            55,
        )

    def test_identity_resolves_target_when_numeric_index_is_stale(self):
        other = _Item(12, "HDMI", 70)
        selected = _Item(11, "Speakers", 55)
        audio = _Audio([other, selected])
        controller = _Harness(
            audio,
            _Item(11, "Speakers", 24),
            current_index=0,
        )

        self.assertTrue(controller._sync_current_volume_once())
        self.assertEqual(audio.read_indices, [(DisplayMode.MODE_OUTPUT, 1)])
        self.assertEqual(controller.serial.volume_frames[0][1].id, 11)
        self.assertEqual(controller.serial.volume_frames[0][1].volume, 55)

    def test_sync_result_is_dropped_when_mode_changes_during_windows_read(self):
        selected = _Item(11, "Speakers", 55)
        controller = None

        def change_mode():
            with controller._state_lock:
                controller._selection_epoch += 1
                controller._session_info.mode = DisplayMode.MODE_APPLICATION
                controller._sessions[SessionIndex.INDEX_CURRENT] = SessionData(
                    name="Spotify",
                    data=VolumeData(id=77, volume=80),
                )

        audio = _Audio([selected], on_read=change_mode)
        controller = _Harness(audio, _Item(11, "Speakers", 24))

        self.assertFalse(controller._sync_current_volume_once())
        self.assertEqual(controller.serial.volume_frames, [])
        self.assertEqual(
            controller._sessions[SessionIndex.INDEX_CURRENT].data.id,
            77,
        )

    def test_sync_is_skipped_while_selection_transition_is_open(self):
        selected = _Item(11, "Speakers", 55)
        audio = _Audio([selected])
        controller = _Harness(audio, _Item(11, "Speakers", 24))
        controller._selection_transitioning = True

        self.assertFalse(controller._sync_current_volume_once())
        self.assertEqual(audio.read_indices, [])
        self.assertEqual(controller.serial.volume_frames, [])

    def test_mismatched_windows_identity_is_not_sent(self):
        selected = _Item(12, "Speakers", 55)
        audio = _Audio([selected])
        controller = _Harness(audio, _Item(11, "Speakers", 24))

        self.assertFalse(controller._sync_current_volume_once())
        self.assertEqual(controller.serial.volume_frames, [])


if __name__ == "__main__":
    unittest.main()
