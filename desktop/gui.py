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


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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
    """Generate a 64x64 tray icon."""
    target_color = (255, 60, 60) if connected else (150, 150, 150)
    
    try:
        img = Image.open(resource_path(os.path.join("assets", "logo.png"))).convert("RGBA")
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
        
        # Colorize logo: use target color for RGB, keep original Alpha
        r, g, b, a = img.split()
        solid_color = Image.new('RGB', img.size, target_color)
        img = Image.merge('RGBA', (*solid_color.split(), a))
    except Exception as e:
        log.warning(f"Could not load logo: {e}")
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        bg_color = target_color + (255,)
        draw.ellipse([2, 2, 62, 62], fill=bg_color, outline=(60, 60, 80, 255), width=2)
        draw.text((22, 15), "V", fill=(255, 255, 255, 200))

    return img


class SettingsDialog:
    """Simple tkinter settings dialog."""

    def __init__(self, config, controller, on_save, on_close=None):
        self.config = config
        self.controller = controller
        self.on_save = on_save
        self.on_close = on_close
        self._window: Optional[tk.Tk] = None
        self._drag_x = 0
        self._drag_y = 0

    def show(self):
        """Show settings dialog (runs in its own thread)."""
        thread = threading.Thread(target=self._create_window, daemon=True)
        thread.start()

    def _create_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._window = ctk.CTk()
        self._window.overrideredirect(True)
        
        window_width = 320
        window_height = 460
        screen_width = self._window.winfo_screenwidth()
        screen_height = self._window.winfo_screenheight()
        x = screen_width - window_width - 15
        y = screen_height - window_height - 50
        self._window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self._window.attributes('-topmost', True)

        # Use Win32 API to clip window to rounded rectangle (no dark corners)
        self._window.update_idletasks()
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetParent(self._window.winfo_id())
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, 24, 24)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

        # Handle window close to notify TrayApp
        self._window.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Main container
        main_frame = ctk.CTkFrame(self._window, corner_radius=12, border_width=1, border_color="#333333")
        main_frame.pack(fill='both', expand=True)

        # Header (draggable)
        header = ctk.CTkFrame(main_frame, fg_color="transparent", height=36)
        header.pack(fill='x', padx=12, pady=(10, 2))
        header.pack_propagate(False)
        title_lbl = ctk.CTkLabel(header, text="VuNMix", font=ctk.CTkFont(size=16, weight="bold"))
        title_lbl.pack(side='left')
        
        close_btn = ctk.CTkButton(header, text="✕", width=28, height=28, fg_color="transparent", 
                                  hover_color="#dc3545", font=ctk.CTkFont(size=14), command=self._on_window_close)
        close_btn.pack(side='right')

        # Bind drag events on header and title
        for widget in (header, title_lbl):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)

        # Connection row: COM Port + dropdown + Connect/Disconnect
        conn_row = ctk.CTkFrame(main_frame, fg_color="transparent", height=30)
        conn_row.pack(fill='x', padx=12, pady=(4, 2))
        conn_row.pack_propagate(False)
        ctk.CTkLabel(conn_row, text="COM Port", font=ctk.CTkFont(size=12)).pack(side='left')
        
        self._com_var = tk.StringVar(value=self.config.com_port)
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if self.config.com_port not in ports and self.config.com_port:
            ports.append(self.config.com_port)
        
        self.btn_toggle_conn = ctk.CTkButton(conn_row, text="Connect", command=self._toggle_connect, width=75, height=24,
                                             font=ctk.CTkFont(size=11, weight="bold"))
        self.btn_toggle_conn.pack(side='right')
        
        ctk.CTkOptionMenu(conn_row, variable=self._com_var, values=ports if ports else ["None"], width=90, height=24).pack(side='right', padx=6)

        # Content rows
        content = ctk.CTkFrame(main_frame, fg_color="transparent")
        content.pack(fill='both', expand=True, padx=12)

        def add_row(parent, label_text, widget_builder):
            row = ctk.CTkFrame(parent, fg_color="transparent", height=30)
            row.pack(fill='x', pady=3)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=label_text, font=ctk.CTkFont(size=12)).pack(side='left')
            widget = widget_builder(row)
            widget.pack(side='right')
            return row

        # Standby LED
        from protocol import STANDBY_LED_NAMES
        current_led_name = STANDBY_LED_NAMES[self.config.device_settings.standby_led_mode] if self.config.device_settings.standby_led_mode < len(STANDBY_LED_NAMES) else STANDBY_LED_NAMES[0]
        self._led_mode_var = tk.StringVar(value=current_led_name)
        add_row(content, "Standby LED", lambda r: ctk.CTkOptionMenu(r, variable=self._led_mode_var, values=STANDBY_LED_NAMES, width=120, height=24))

        # LED Brightness
        self._brightness_var = tk.DoubleVar(value=self.config.device_settings.led_brightness)
        add_row(content, "LED Brightness", lambda r: ctk.CTkSlider(r, from_=0, to=255, variable=self._brightness_var, width=120, height=14, command=self._on_brightness_change))

        # Sync Interval
        self._interval_var = tk.StringVar(value=str(self.config.update_interval_ms))
        add_row(content, "Sync Interval (ms)", lambda r: ctk.CTkEntry(r, textvariable=self._interval_var, width=55, height=24))

        # Sleep Timeout (default 60s)
        self._sleep_var = tk.StringVar(value=str(self.config.device_settings.sleep_after_seconds))
        add_row(content, "Sleep Timeout (s)", lambda r: ctk.CTkEntry(r, textvariable=self._sleep_var, width=55, height=24))

        # Continuous Scroll
        self._scroll_var = tk.BooleanVar(value=self.config.device_settings.continuous_scroll)
        add_row(content, "Continuous Scroll", lambda r: ctk.CTkSwitch(r, text="", variable=self._scroll_var, switch_width=36, switch_height=18))

        # Run on Startup (default on)
        self._startup_var = tk.BooleanVar(value=self.config.run_on_startup)
        add_row(content, "Run on Startup", lambda r: ctk.CTkSwitch(r, text="", variable=self._startup_var, switch_width=36, switch_height=18))

        # Auto Sleep (default off)
        self._sleep_enabled_var = tk.BooleanVar(value=self.config.device_settings.sleep_enabled)
        add_row(content, "Auto Sleep", lambda r: ctk.CTkSwitch(r, text="", variable=self._sleep_enabled_var, switch_width=36, switch_height=18))

        # Save Button
        save_btn = ctk.CTkButton(main_frame, text="Save Settings", command=self._save, height=32, font=ctk.CTkFont(size=12, weight="bold"))
        save_btn.pack(fill='x', padx=12, pady=(6, 12))

        self._update_status_loop()
        self._window.mainloop()

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        x = self._window.winfo_x() + event.x - self._drag_x
        y = self._window.winfo_y() + event.y - self._drag_y
        self._window.geometry(f"+{x}+{y}")

    def _on_window_close(self):
        if self._window:
            self._window.destroy()
        if self.on_close:
            self.on_close()

    def _update_status_loop(self):
        if not self._window or not self._window.winfo_exists():
            return
        if self.controller._device_connected:
            self.btn_toggle_conn.configure(text="Disconnect", fg_color="#dc3545", hover_color="#c82333")
        else:
            self.btn_toggle_conn.configure(text="Connect", fg_color="#28a745", hover_color="#218838")
        self._window.after(500, self._update_status_loop)

    def _toggle_connect(self):
        if self.controller._device_connected:
            self.controller.stop()
        else:
            port = self._com_var.get().strip()
            if port:
                self.config.com_port = port
                self.config.save()
                self.controller.stop()
                self.controller.serial.port = port
                self.controller.start()

    def _save(self):
        try:
            old_port = self.config.com_port
            new_port = self._com_var.get().strip()
            
            self.config.com_port = new_port
            self.config.update_interval_ms = int(self._interval_var.get())
            self.config.run_on_startup = self._startup_var.get()
            self.config.device_settings.sleep_after_seconds = int(self._sleep_var.get())
            self.config.device_settings.sleep_enabled = self._sleep_enabled_var.get()
            from protocol import STANDBY_LED_NAMES
            led_name = self._led_mode_var.get()
            self.config.device_settings.standby_led_mode = STANDBY_LED_NAMES.index(led_name) if led_name in STANDBY_LED_NAMES else 0
            self.config.device_settings.continuous_scroll = self._scroll_var.get()
            self.config.device_settings.led_brightness = int(self._brightness_var.get())
            self.config.save()
            
            set_run_on_startup(self.config.run_on_startup)
            
            port_changed = (old_port != new_port)
            if self.on_save:
                self.on_save(port_changed)
                
            self._on_window_close()
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid value: {e}")

    def _on_brightness_change(self, value):
        from protocol import Command
        if self.controller._device_connected:
            import copy
            preview_settings = copy.deepcopy(self.config.device_settings)
            preview_settings.led_brightness = int(value)
            self.controller.serial.send_command(Command.SETTINGS, preview_settings.pack())


class TrayApp:
    """System tray application using pystray."""

    def __init__(self, config, controller):
        self.config = config
        self.controller = controller
        self._icon = None
        self._settings_open = False

    def run(self):
        """Start the tray application (blocking)."""
        import pystray
        from pystray import MenuItem, Menu

        icon_image = create_tray_icon(False)

        menu = Menu(
            MenuItem('VuNMix', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(lambda item: f"Status: {'Connected' if self.controller._device_connected else 'Disconnected'}", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Settings', self._on_settings, default=True),
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
            self._icon.update_menu()

    def _on_settings(self, icon, item):
        if self._settings_open:
            return
        self._settings_open = True
        dialog = SettingsDialog(self.config, self.controller,
                                on_save=self._on_settings_saved,
                                on_close=self._on_settings_closed)
        dialog.show()

    def _on_settings_closed(self):
        self._settings_open = False

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

