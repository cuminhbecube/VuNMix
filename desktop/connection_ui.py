"""Connection-aware GUI wrappers for VuNMix.

Kept separate from the legacy gui.py while the desktop UI is still monolithic.
Issue #10 will eventually fold this back into the refactored views.
"""

import logging

from build_info import APP_VERSION
from gui import SettingsDialog, TrayApp, create_tray_icon


log = logging.getLogger(__name__)


class ConnectionSettingsDialog(SettingsDialog):
    """Show discovery/reconnect state instead of a binary Connect label."""

    def _update_status_loop(self):
        if not self._window or not self._window.winfo_exists():
            return

        connected = bool(self.controller._device_connected)
        serial_service = self.controller.serial

        if connected:
            text = "Disconnect"
            color = "#dc3545"
            hover = "#c82333"
        else:
            status = (getattr(serial_service, "status", "") or "").lower()
            if "protocol mismatch" in status:
                text = "P mismatch"
            elif serial_service.is_connected or "verifying" in status:
                text = "Verify..."
            elif "connecting" in status:
                text = "Connecting"
            elif "search" in status or "waiting" in status:
                text = "Searching"
            else:
                text = "Connect"
            color = "#28a745"
            hover = "#218838"

        self.btn_toggle_conn.configure(
            text=text,
            fg_color=color,
            hover_color=hover,
            state="disabled" if self.controller.firmware_updating else "normal",
        )

        active_port = getattr(serial_service, "port", "")
        if active_port and hasattr(self, "_com_var"):
            self._com_var.set(active_port)

        if hasattr(self, "btn_firmware"):
            self.btn_firmware.configure(
                state="normal" if self.controller.can_update_firmware else "disabled"
            )

        self._window.after(500, self._update_status_loop)


class ConnectionTrayApp(TrayApp):
    """Tray app with versioned labels, diagnostics, OBS and connection state."""

    def run(self):
        import pystray
        from pystray import Menu, MenuItem

        is_conn = bool(self.controller._device_connected)
        icon_image = create_tray_icon(is_conn)
        status_text = (
            f"VuNMix {APP_VERSION} - "
            f"{'Connected' if is_conn else 'Disconnected'}"
        )

        def make_preset_action(p_name):
            return lambda icon, item: self.controller.preset_service.apply_preset(p_name)

        preset_items = [
            MenuItem(name, make_preset_action(name))
            for name in self.controller.preset_service.get_preset_names()
        ]

        obs = self.controller.obs_service
        obs_menu = Menu(
            MenuItem(
                lambda item: (
                    f"OBS: {obs.current_scene or 'Connected'}"
                    if obs.is_connected
                    else "OBS: Disconnected"
                ),
                None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            MenuItem(
                lambda item: "Stop streaming" if obs.is_streaming else "Start streaming",
                self._on_obs_toggle_stream,
                enabled=lambda item: obs.is_connected,
            ),
            MenuItem(
                lambda item: "Stop recording" if obs.is_recording else "Start recording",
                self._on_obs_toggle_record,
                enabled=lambda item: obs.is_connected,
            ),
            Menu.SEPARATOR,
            MenuItem(
                lambda item: (
                    "Unmute Mic"
                    if obs.input_mutes.get(obs.mic_input, False)
                    else "Mute Mic"
                ),
                self._on_obs_toggle_mic,
                enabled=lambda item: obs.is_connected,
            ),
            MenuItem(
                lambda item: (
                    "Unmute Desktop"
                    if obs.input_mutes.get(obs.desktop_input, False)
                    else "Mute Desktop"
                ),
                self._on_obs_toggle_desktop,
                enabled=lambda item: obs.is_connected,
            ),
            Menu.SEPARATOR,
            MenuItem(
                "Next scene",
                self._on_obs_next_scene,
                enabled=lambda item: obs.is_connected and len(obs.scenes) > 1,
            ),
            MenuItem(
                lambda item: self._obs_stats_label(),
                None,
                enabled=False,
            ),
        )

        menu = Menu(
            MenuItem(f"VuNMix {APP_VERSION}", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(
                lambda item: (
                    "Status: Connected"
                    if self.controller._device_connected
                    else f"Status: {self.controller.serial.status}"
                ),
                None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            MenuItem("🎵 Audio Presets", Menu(*preset_items)),
            MenuItem("🎥 OBS Studio", obs_menu),
            Menu.SEPARATOR,
            MenuItem("Settings", self._on_settings, default=True),
            MenuItem("Reconnect", self._on_reconnect),
            Menu.SEPARATOR,
            MenuItem("Copy diagnostics", self._on_copy_diagnostics),
            MenuItem("Open log folder", self._on_open_log_folder),
            Menu.SEPARATOR,
            MenuItem("Exit", self._on_exit),
        )

        self._icon = pystray.Icon("VuNMix", icon_image, status_text, menu)
        self.controller.on_connection_changed = self._on_connection_status
        obs.set_state_callback(lambda state: self._on_obs_state_changed())

        if self.controller._device_connected:
            self._on_connection_status(True)

        self._icon.run()

    def _on_connection_status(self, connected: bool):
        log.info(
            "Tray connection state changed: %s",
            "connected" if connected else "disconnected",
        )
        if self._icon is not None:
            try:
                self._icon.icon = create_tray_icon(connected)
                self._icon.title = (
                    f"VuNMix {APP_VERSION} - "
                    f"{'Connected' if connected else 'Disconnected'}"
                )
                self._icon.update_menu()
            except Exception as exc:
                log.warning("Failed to update tray icon state: %s", exc)

    def _on_obs_state_changed(self):
        if self._icon is not None:
            try:
                self._icon.update_menu()
            except Exception as exc:
                log.debug("Failed to refresh OBS tray menu: %s", exc)

    def _obs_stats_label(self):
        obs = self.controller.obs_service
        if not obs.is_connected:
            return "Stream stats: unavailable"
        if not obs.is_streaming:
            return "Stream stats: idle"
        timecode = obs.stream_timecode or "running"
        if obs.total_frames:
            return f"{timecode} · dropped {obs.dropped_frames}/{obs.total_frames}"
        return timecode

    def _run_obs_action(self, label, action):
        def worker():
            try:
                action()
                log.info("OBS action completed: %s", label)
            except Exception:
                log.exception("OBS action failed: %s", label)
            finally:
                self._on_obs_state_changed()

        import threading

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"ObsTray-{label}",
        ).start()

    def _on_obs_toggle_stream(self, icon, item):
        self._run_obs_action("toggle-stream", self.controller.obs_service.toggle_streaming)

    def _on_obs_toggle_record(self, icon, item):
        self._run_obs_action("toggle-record", self.controller.obs_service.toggle_recording)

    def _on_obs_toggle_mic(self, icon, item):
        obs = self.controller.obs_service
        self._run_obs_action("toggle-mic", lambda: obs.toggle_input_mute(obs.mic_input))

    def _on_obs_toggle_desktop(self, icon, item):
        obs = self.controller.obs_service
        self._run_obs_action(
            "toggle-desktop",
            lambda: obs.toggle_input_mute(obs.desktop_input),
        )

    def _on_obs_next_scene(self, icon, item):
        obs = self.controller.obs_service
        scenes = list(obs.scenes)
        if len(scenes) < 2:
            return
        try:
            current_index = scenes.index(obs.current_scene)
        except ValueError:
            current_index = -1
        next_scene = scenes[(current_index + 1) % len(scenes)]
        self._run_obs_action("next-scene", lambda: obs.switch_scene(next_scene))

    def _on_copy_diagnostics(self, icon, item):
        try:
            import win32clipboard

            report = self.controller.diagnostic_report()
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(report, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            log.info("Diagnostic report copied to clipboard")
        except Exception:
            log.exception("Failed to copy diagnostic report")

    def _on_open_log_folder(self, icon, item):
        try:
            self.controller.open_log_folder()
        except Exception:
            log.exception("Failed to open VuNMix log folder")

    def _on_settings(self, icon, item):
        if self._settings_open:
            return
        self._settings_open = True
        if self._settings_dialog is None:
            self._settings_dialog = ConnectionSettingsDialog(
                self.config,
                self.controller,
                on_save=self._on_settings_saved,
                on_close=self._on_settings_closed,
            )
        self._settings_dialog.show()
