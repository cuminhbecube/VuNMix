"""Connection-aware GUI wrappers for VuNMix.

Kept separate from the legacy gui.py while the desktop UI is still monolithic.
Issue #10 will eventually fold this back into the refactored views.
"""

from gui import SettingsDialog, TrayApp


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
            if serial_service.is_connected or "verifying" in status:
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

        # Follow the active COM number when Windows renumbers the same board.
        active_port = getattr(serial_service, "port", "")
        if active_port and hasattr(self, "_com_var"):
            self._com_var.set(active_port)

        if hasattr(self, "btn_firmware"):
            self.btn_firmware.configure(
                state="normal" if self.controller.can_update_firmware else "disabled"
            )

        self._window.after(500, self._update_status_loop)


class ConnectionTrayApp(TrayApp):
    """Tray app that uses the connection-aware settings dialog."""

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
