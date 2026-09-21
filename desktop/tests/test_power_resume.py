import pathlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_DIR = DESKTOP_DIR.parent
sys.path.insert(0, str(DESKTOP_DIR))

previous_comtypes = sys.modules.get("comtypes")
comtypes_stub = types.ModuleType("comtypes")
comtypes_stub.CoInitialize = lambda: None
comtypes_stub.CoUninitialize = lambda: None
sys.modules["comtypes"] = comtypes_stub

from controller_device import DeviceLifecycleMixin
from protocol import Command, DisplayMode, SessionInfo

if previous_comtypes is None:
    del sys.modules["comtypes"]
else:
    sys.modules["comtypes"] = previous_comtypes


class RecordingSerial:
    def __init__(self):
        self.commands = []
        self.settings = []
        self.is_connected = True

    def send_command(self, command):
        self.commands.append(command)
        return True

    def send_settings(self, settings):
        self.settings.append(settings)
        return True


class RecordingAudio:
    def __init__(self):
        self.refresh_calls = 0

    def refresh(self):
        self.refresh_calls += 1


class PowerHarness(DeviceLifecycleMixin):
    def __init__(self):
        self.serial = RecordingSerial()
        self.audio = RecordingAudio()
        self.config = SimpleNamespace(device_settings=object())
        self._session_info = SessionInfo(mode=DisplayMode.MODE_SPLASH)
        self._running = True
        self._is_sleeping = False
        self._connected = True
        self.pushed_modes = []

    @property
    def is_connected(self):
        return self._connected

    def _push_full_state(self, mode):
        self.pushed_modes.append(mode)


class ResumeRecoveryTests(unittest.TestCase):
    def test_sleep_sends_explicit_sleep_command(self):
        controller = PowerHarness()

        controller._on_pc_sleep()

        self.assertTrue(controller._is_sleeping)
        self.assertEqual(controller.serial.commands, [Command.SLEEP])

    def test_resume_recovery_wakes_before_settings_and_full_state(self):
        controller = PowerHarness()

        with mock.patch("controller_device.time.sleep", return_value=None):
            recovered = controller._recover_after_resume()

        self.assertTrue(recovered)
        self.assertEqual(controller.serial.commands[0], Command.OK)
        self.assertEqual(len(controller.serial.settings), 1)
        self.assertEqual(controller.audio.refresh_calls, 1)
        self.assertEqual(controller.pushed_modes, [DisplayMode.MODE_OUTPUT])

    def test_resume_recovery_does_not_wake_during_new_suspend(self):
        controller = PowerHarness()
        controller._is_sleeping = True

        recovered = controller._recover_after_resume()

        self.assertFalse(recovered)
        self.assertEqual(controller.serial.commands, [])
        self.assertEqual(controller.serial.settings, [])
        self.assertEqual(controller.pushed_modes, [])


class FirmwareDisplayPowerTests(unittest.TestCase):
    def test_display_power_is_centralized_and_wake_precedes_clock_render(self):
        display_header = (REPO_DIR / "src" / "Display.h").read_text(encoding="utf-8")
        display_core = (
            REPO_DIR / "src" / "ui" / "modules" / "DisplayCoreState.inc"
        ).read_text(encoding="utf-8")
        shell_lifecycle = (
            REPO_DIR / "src" / "ui" / "modules" / "DisplayShellLifecycle.inc"
        ).read_text(encoding="utf-8")
        game_lifecycle = (
            REPO_DIR / "src" / "ui" / "modules" / "DisplayGameLifecycle.inc"
        ).read_text(encoding="utf-8")
        main_source = (REPO_DIR / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("void Wake();", display_header)
        self.assertIn("void Wake()", display_core)
        self.assertIn("void Sleep()", display_core)
        self.assertNotIn("digitalWrite(PIN_TFT_BL, HIGH)", shell_lifecycle)
        self.assertNotIn("void Sleep()", game_lifecycle)

        update_start = main_source.index("void UpdateDisplay()")
        update_end = main_source.index("// Lighting", update_start)
        update_display = main_source[update_start:update_end]
        self.assertLess(
            update_display.index("if (g_DisplayAsleep)"),
            update_display.index("if (g_ClockMode && g_TimeValid)"),
        )
        self.assertLess(
            update_display.index("Display::Wake();"),
            update_display.index("if (g_ClockMode && g_TimeValid)"),
        )

    def test_host_sleep_and_idle_sleep_are_independent(self):
        main_source = (REPO_DIR / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("bool g_IdleDisplayAsleep = false;", main_source)
        self.assertIn(
            "bool nextState = g_PcAsleep || g_IdleDisplayAsleep;",
            main_source,
        )
        self.assertIn("command == Command::OK && g_PcAsleep", main_source)
        self.assertIn("g_Settings.sleepAfterSeconds == 0", main_source)


if __name__ == "__main__":
    unittest.main()
