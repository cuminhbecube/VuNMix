"""
VuNMix GUI — System tray application with pystray.

Provides:
- Tray icon with connection status indicator
- Menu: Settings, Reconnect, Exit
- Simple settings dialog via tkinter
"""

import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from typing import Optional
import serial.tools.list_ports

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)


def set_run_on_startup(enable: bool):
    """Enable or disable Windows startup via the registry."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "VuNMix"
        
        # Determine executable path
        if getattr(sys, 'frozen', False):
            # Running as a PyInstaller executable
            exe_path = sys.executable
            cmd = f'"{exe_path}"'
        else:
            # Running as a Python script
            exe_path = os.path.abspath(sys.argv[0])
            pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            cmd = f'"{pythonw}" "{exe_path}"'
            
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            log.info("Startup enabled: %s", cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
                log.info("Startup disabled")
            except FileNotFoundError:
                pass
                
        winreg.CloseKey(key)
    except Exception as e:
        log.error("Failed to update registry for startup: %s", e)


def create_tray_icon(connected: bool) -> Image.Image:
    """Generate a 64x64 tray icon. Green circle = connected, red = disconnected."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    bg_color = (20, 20, 30, 255)
    draw.ellipse([2, 2, 62, 62], fill=bg_color, outline=(60, 60, 80, 255), width=2)

    # Status dot
    if connected:
        dot_color = (0, 212, 255, 255)  # Cyan
    else:
        dot_color = (255, 60, 60, 255)  # Red

    draw.ellipse([18, 18, 46, 46], fill=dot_color)

    # "V" letter overlay
    draw.text((22, 15), "V", fill=(255, 255, 255, 200))

    return img


class SettingsDialog:
    """Simple tkinter settings dialog."""

    def __init__(self, config, controller, on_save):
        self.config = config
        self.controller = controller
        self.on_save = on_save
        self._window: Optional[tk.Tk] = None

    def show(self):
        """Show settings dialog (runs in its own thread)."""
        thread = threading.Thread(target=self._create_window, daemon=True)
        thread.start()

    def _create_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._window = ctk.CTk()
        self._window.title("VuNMix Settings")
        self._window.geometry("400x420")
        self._window.resizable(False, False)

        # Title
        title = ctk.CTkLabel(self._window, text="VuNMix Settings", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(pady=(20, 15))

        # COM Port
        frame = ctk.CTkFrame(self._window, fg_color="transparent")
        frame.pack(fill='x', padx=30, pady=10)
        ctk.CTkLabel(frame, text="COM Port:", font=ctk.CTkFont(size=13)).pack(side='left')
        
        self._com_var = tk.StringVar(value=self.config.com_port)
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if self.config.com_port not in ports and self.config.com_port:
            ports.append(self.config.com_port)
            
        com_entry = ctk.CTkOptionMenu(frame, variable=self._com_var, values=ports if ports else ["None"], width=100)
        com_entry.pack(side='left', padx=(10, 10))
        
        # Connect / Disconnect Buttons
        btn_conn = ctk.CTkButton(frame, text="Conn", command=self._connect, width=55, 
                                 fg_color="#28a745", hover_color="#218838", font=ctk.CTkFont(size=12, weight="bold"))
        btn_conn.pack(side='left', padx=3)
        btn_disconn = ctk.CTkButton(frame, text="Disc", command=self._disconnect, width=55, 
                                    fg_color="#dc3545", hover_color="#c82333", font=ctk.CTkFont(size=12, weight="bold"))
        btn_disconn.pack(side='left', padx=3)

        # Update Interval
        frame2 = ctk.CTkFrame(self._window, fg_color="transparent")
        frame2.pack(fill='x', padx=30, pady=10)
        ctk.CTkLabel(frame2, text="Sync Interval (ms):", font=ctk.CTkFont(size=13)).pack(side='left')
        self._interval_var = tk.StringVar(value=str(self.config.update_interval_ms))
        int_entry = ctk.CTkEntry(frame2, textvariable=self._interval_var, width=100)
        int_entry.pack(side='right')

        # Sleep Timeout
        frame3 = ctk.CTkFrame(self._window, fg_color="transparent")
        frame3.pack(fill='x', padx=30, pady=10)
        ctk.CTkLabel(frame3, text="Sleep Timeout (s):", font=ctk.CTkFont(size=13)).pack(side='left')
        self._sleep_var = tk.StringVar(value=str(self.config.device_settings.sleep_after_seconds))
        sleep_entry = ctk.CTkEntry(frame3, textvariable=self._sleep_var, width=100)
        sleep_entry.pack(side='right')

        # Continuous Scroll
        self._scroll_var = tk.BooleanVar(value=self.config.device_settings.continuous_scroll)
        scroll_cb = ctk.CTkSwitch(self._window, text="Continuous Scroll", variable=self._scroll_var, font=ctk.CTkFont(size=13))
        scroll_cb.pack(pady=10)

        # Run on Startup
        self._startup_var = tk.BooleanVar(value=self.config.run_on_startup)
        startup_cb = ctk.CTkSwitch(self._window, text="Run on Windows Startup", variable=self._startup_var, font=ctk.CTkFont(size=13))
        startup_cb.pack(pady=10)

        # Buttons
        btn_frame = ctk.CTkFrame(self._window, fg_color="transparent")
        btn_frame.pack(pady=20)

        save_btn = ctk.CTkButton(btn_frame, text="Save", command=self._save, width=100, font=ctk.CTkFont(size=13, weight="bold"))
        save_btn.pack(side='left', padx=15)

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", command=self._window.destroy, width=100, 
                                   fg_color="#3a3a4e", hover_color="#2b2b3a", font=ctk.CTkFont(size=13))
        cancel_btn.pack(side='left', padx=15)

        self._window.mainloop()

    def _connect(self):
        port = self._com_var.get().strip()
        if port:
            self.config.com_port = port
            self.config.save()
            self.controller.stop()
            self.controller.serial.port = port
            self.controller.start()
            
    def _disconnect(self):
        self.controller.stop()

    def _save(self):
        try:
            old_port = self.config.com_port
            new_port = self._com_var.get().strip()
            
            self.config.com_port = new_port
            self.config.update_interval_ms = int(self._interval_var.get())
            self.config.run_on_startup = self._startup_var.get()
            self.config.device_settings.sleep_after_seconds = int(self._sleep_var.get())
            self.config.device_settings.continuous_scroll = self._scroll_var.get()
            self.config.save()
            
            set_run_on_startup(self.config.run_on_startup)
            
            port_changed = (old_port != new_port)
            if self.on_save:
                self.on_save(port_changed)
                
            self._window.destroy()
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid value: {e}")


class TrayApp:
    """System tray application using pystray."""

    def __init__(self, config, controller):
        self.config = config
        self.controller = controller
        self._icon = None
        self._settings_dialog: Optional[SettingsDialog] = None

    def run(self):
        """Start the tray application (blocking)."""
        import pystray
        from pystray import MenuItem, Menu

        icon_image = create_tray_icon(False)

        menu = Menu(
            MenuItem('VuNMix', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Status: Disconnected', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Settings', self._on_settings),
            MenuItem('Reconnect', self._on_reconnect),
            Menu.SEPARATOR,
            MenuItem('Exit', self._on_exit),
        )

        self._icon = pystray.Icon('VuNMix', icon_image, 'VuNMix - Disconnected', menu)

        # Wire connection status updates
        self.controller.on_connection_changed = self._on_connection_status

        self._icon.run()

    def _on_connection_status(self, connected: bool):
        """Update tray icon and tooltip based on connection status."""
        if self._icon:
            self._icon.icon = create_tray_icon(connected)
            status = "Connected" if connected else "Disconnected"
            self._icon.title = f"VuNMix - {status}"

    def _on_settings(self, icon, item):
        dialog = SettingsDialog(self.config, self.controller, on_save=self._on_settings_saved)
        dialog.show()

    def _on_settings_saved(self, port_changed: bool):
        log.info("Settings saved. Port changed: %s", port_changed)
        if port_changed:
            self.controller.stop()
            self.controller.serial.port = self.config.com_port
            self.controller.start()
        else:
            # Just push updated settings to hardware without resetting port
            from protocol import Command
            if self.controller._device_connected:
                self.controller.serial.send_command(Command.SETTINGS, self.config.device_settings.pack())

    def _on_reconnect(self, icon, item):
        log.info("Manual reconnect requested")
        self.controller.serial.disconnect()
        self.controller.serial.connect()

    def _on_exit(self, icon, item):
        log.info("Exit requested")
        self.controller.stop()
        self._icon.stop()
