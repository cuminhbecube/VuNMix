import pathlib
import unittest


REPO_DIR = pathlib.Path(__file__).resolve().parents[2]


class UiThreadingRegressionTests(unittest.TestCase):
    def test_tk_is_not_created_on_background_thread(self):
        source = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")

        self.assertIn("VuNMix Tk UI must be initialized on MainThread", source)
        self.assertIn("threading.current_thread() is not threading.main_thread()", source)
        self.assertNotIn('name="SettingsTk"', source)
        self.assertNotIn("target=self._create_window", source)

    def test_worker_ui_callbacks_use_queue_not_tk_after(self):
        source = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")

        start = source.index("    def _ui_call(self, callback):")
        end = source.index("\n    def _select_firmware", start)
        ui_call = source[start:end]

        self.assertIn('self._window_commands.put(("call", callback))', ui_call)
        self.assertNotIn(".after(", ui_call)
        self.assertNotIn("winfo_exists", ui_call)

    def test_tray_runs_detached_while_tk_owns_main_loop(self):
        base = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")
        connection = (REPO_DIR / "desktop" / "connection_ui.py").read_text(encoding="utf-8")

        self.assertIn("self._icon.run_detached()", base)
        self.assertIn("dialog.run_loop()", base)
        self.assertIn("self._icon.run_detached()", connection)
        self.assertIn("dialog.run_loop()", connection)
        self.assertNotIn("self._icon.run()\n", base)
        self.assertNotIn("self._icon.run()\n", connection)

    def test_tk_shutdown_occurs_on_command_pump(self):
        source = (REPO_DIR / "desktop" / "gui.py").read_text(encoding="utf-8")

        self.assertIn('self._window_commands.put(("shutdown", None))', source)
        self.assertIn('elif command == "shutdown":', source)
        self.assertIn("window.destroy()", source)

    def test_worker_tray_refreshes_are_marshaled(self):
        source = (REPO_DIR / "desktop" / "connection_ui.py").read_text(encoding="utf-8")

        self.assertIn("self._dispatch_ui(self._safe_update_menu)", source)
        self.assertIn("def _on_obs_state_changed(self):", source)


if __name__ == "__main__":
    unittest.main()
