import pathlib
import sys
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_DIR = DESKTOP_DIR.parent
sys.path.insert(0, str(DESKTOP_DIR))

from app_controller import AppController
from controller_device import DeviceLifecycleMixin
from controller_state import HardwareStateMixin
from controller_workers import SyncWorkersMixin
from protocol import Command, PROTOCOL_VERSION


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_app_controller_is_orchestration_shell(self):
        source = (DESKTOP_DIR / "app_controller.py").read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 240)
        self.assertTrue(issubclass(AppController, DeviceLifecycleMixin))
        self.assertTrue(issubclass(AppController, HardwareStateMixin))
        self.assertTrue(issubclass(AppController, SyncWorkersMixin))
        self.assertNotIn("def _sync_loop", source)
        self.assertNotIn("def _on_hw_message", source)
        self.assertNotIn("class PowerMonitor", source)

    def test_display_cpp_is_thin_composition_root(self):
        source = (REPO_DIR / "src" / "Display.cpp").read_text(encoding="utf-8")
        implementation = REPO_DIR / "src" / "ui" / "DisplayScreens.inc"
        self.assertLess(len(source.splitlines()), 20)
        self.assertIn('ui/DisplayScreens.inc', source)
        self.assertTrue(implementation.exists())
        self.assertGreater(implementation.stat().st_size, 50_000)

    def test_protocol_v1_wire_ids_are_unchanged(self):
        self.assertEqual(PROTOCOL_VERSION, 1)
        expected = {
            "TEST": 1,
            "OK": 2,
            "SETTINGS": 3,
            "SESSION_INFO": 4,
            "CURRENT_SESSION": 5,
            "ALTERNATE_SESSION": 6,
            "PREVIOUS_SESSION": 7,
            "NEXT_SESSION": 8,
            "VOLUME_CURR_CHANGE": 9,
            "VOLUME_ALT_CHANGE": 10,
            "VOLUME_PREV_CHANGE": 11,
            "VOLUME_NEXT_CHANGE": 12,
            "MODE_STATES": 13,
            "DEBUG": 14,
            "SLEEP": 15,
            "TIME_SYNC": 16,
            "METER_LEVEL": 17,
            "APP_ICON_META": 18,
            "APP_ICON_CHUNK": 19,
            "PC_STATS": 20,
            "MEDIA_INFO": 21,
            "MEDIA_CONTROL": 22,
        }
        self.assertEqual({name: int(getattr(Command, name)) for name in expected}, expected)


if __name__ == "__main__":
    unittest.main()
