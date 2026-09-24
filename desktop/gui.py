"""
VuNMix GUI — System tray application with pystray.

Provides:
- Tray icon with connection status indicator
- Menu: Settings, Reconnect, Exit
- Simple settings dialog via tkinter
"""

import logging
import math
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import customtkinter as ctk
from typing import Optional
import serial.tools.list_ports

from PIL import Image, ImageDraw

from build_info import APP_VERSION
from app_updater import AppUpdater, UpdateInfo, version_tuple
from firmware_release import (
    FirmwareReleaseClient,
    FirmwareReleaseInfo,
    should_auto_update_firmware,
)

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
            if not os.path.exists(pythonw):
                pythonw = sys.executable
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
    """Generate a 64x64 tray icon (Red when connected, Grey when disconnected)."""
    target_color = (255, 60, 60) if connected else (130, 130, 130)
    
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

    def __init__(
        self,
        config,
        controller,
        on_save,
        on_close=None,
        on_check_app_update=None,
        on_install_app_update=None,
    ):
        self.config = config
        self.controller = controller
        self.on_save = on_save
        self.on_close = on_close
        self.on_check_app_update = on_check_app_update
        self.on_install_app_update = on_install_app_update
        self._window: Optional[tk.Tk] = None
        self._ui_thread_id: Optional[int] = None
        self._window_commands = queue.Queue()
        self._drag_x = 0
        self._drag_y = 0
        self._firmware_release_client = FirmwareReleaseClient()
        self._firmware_release_loading = False

    def initialize(self):
        """Create the single Tcl/Tk interpreter on the process main thread."""
        if self._window is not None:
            return
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("VuNMix Tk UI must be initialized on MainThread")
        self._ui_thread_id = threading.get_ident()
        self._create_window()

    def run_loop(self):
        """Run the Tk main loop on the same thread that created the interpreter."""
        self.initialize()
        if threading.get_ident() != self._ui_thread_id:
            raise RuntimeError("VuNMix Tk mainloop must run on its owning thread")
        log.info("Starting Tk UI loop on MainThread")
        self._window.mainloop()
        log.info("Tk UI loop stopped")

    def show(self):
        """Thread-safe request to show the persistent settings window."""
        self._window_commands.put(("show", None))

    def request_shutdown(self):
        """Thread-safe request to tear Tcl/Tk down on its owning thread."""
        self._window_commands.put(("shutdown", None))

    def _create_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._window = ctk.CTk()
        self._window.overrideredirect(True)
        
        window_width = 320
        window_height = 700
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
        header = ctk.CTkFrame(main_frame, fg_color="transparent", height=32)
        header.pack(fill='x', padx=12, pady=(6, 0))
        header.pack_propagate(False)
        title_lbl = ctk.CTkLabel(header, text="VuNMix", font=ctk.CTkFont(size=16, weight="bold"))
        title_lbl.pack(side='left')
        
        close_btn = ctk.CTkButton(header, text="✕", width=26, height=24, fg_color="transparent", 
                                  hover_color="#dc3545", font=ctk.CTkFont(size=14), command=self._on_window_close)
        close_btn.pack(side='right')

        # Bind drag events on header and title
        for widget in (header, title_lbl):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)

        # Connection row: COM Port + dropdown + Connect/Disconnect
        conn_row = ctk.CTkFrame(main_frame, fg_color="transparent", height=28)
        conn_row.pack(fill='x', padx=12, pady=(2, 1))
        conn_row.pack_propagate(False)
        ctk.CTkLabel(conn_row, text="COM Port", font=ctk.CTkFont(size=12)).pack(side='left')
        
        self._com_var = tk.StringVar(value=self.config.com_port)
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if self.config.com_port not in ports and self.config.com_port:
            ports.append(self.config.com_port)
        
        self.btn_toggle_conn = ctk.CTkButton(conn_row, text="Connect", command=self._toggle_connect, width=75, height=22,
                                             font=ctk.CTkFont(size=11, weight="bold"))
        self.btn_toggle_conn.pack(side='right')
        
        ctk.CTkOptionMenu(conn_row, variable=self._com_var, values=ports if ports else ["None"], width=90, height=22).pack(side='right', padx=6)

        # Reserve the footer before packing the settings body. This keeps Save
        # visible even when more settings or status rows are added later.
        save_btn = ctk.CTkButton(
            main_frame,
            text="Save Settings",
            command=self._save,
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        save_btn.pack(side='bottom', fill='x', padx=12, pady=(4, 8))

        # Content rows stay compact and consume only their requested height.
        content = ctk.CTkFrame(main_frame, fg_color="transparent")
        content.pack(fill='x', padx=12)

        def add_row(parent, label_text, widget_builder):
            row = ctk.CTkFrame(parent, fg_color="transparent", height=26)
            row.pack(fill='x', pady=1)
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

        # Runtime color controls. Keep all four existing protocol colors but
        # expose them in one compact row so the settings window stays usable.
        self._led_color_values = {
            "volume_min_color": self.config.device_settings.volume_min_color.to_list(),
            "volume_max_color": self.config.device_settings.volume_max_color.to_list(),
            "mix_channel_a_color": self.config.device_settings.mix_channel_a_color.to_list(),
            "mix_channel_b_color": self.config.device_settings.mix_channel_b_color.to_list(),
        }
        self._led_color_buttons = {}

        def build_led_color_row(parent):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            for key, label in (
                ("volume_min_color", "V-"),
                ("volume_max_color", "V+"),
                ("mix_channel_a_color", "A"),
                ("mix_channel_b_color", "B"),
            ):
                rgb = self._led_color_values[key]
                hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
                button = ctk.CTkButton(
                    frame,
                    text=label,
                    width=27,
                    height=23,
                    fg_color=hex_color,
                    hover_color=hex_color,
                    command=lambda selected=key: self._choose_led_color(selected),
                )
                button.pack(side="left", padx=1)
                self._led_color_buttons[key] = button
            return frame

        add_row(content, "LED Colors V-/V+/A/B", build_led_color_row)

        # Sleep Timeout is shown in minutes; the wire/config representation
        # remains seconds for compatibility with existing firmware/configs.
        sleep_seconds = max(0, int(self.config.device_settings.sleep_after_seconds))
        sleep_minutes = math.ceil(sleep_seconds / 60) if sleep_seconds else 0
        self._sleep_var = tk.StringVar(value=str(sleep_minutes))
        add_row(content, "Sleep Timeout (minutes)", lambda r: ctk.CTkEntry(r, textvariable=self._sleep_var, width=55, height=24))

        # Clock Standby Timeout (minutes, 0=disabled, default=10)
        self._clock_standby_var = tk.StringVar(value=str(self.config.device_settings.clock_standby_minutes))
        add_row(content, "Clock Standby (min)", lambda r: ctk.CTkEntry(r, textvariable=self._clock_standby_var, width=55, height=24))

        # Clock visual style
        from protocol import CLOCK_STYLE_NAMES
        clock_style_index = max(0, min(len(CLOCK_STYLE_NAMES) - 1, int(self.config.device_settings.clock_style)))
        self._clock_style_var = tk.StringVar(value=CLOCK_STYLE_NAMES[clock_style_index])
        add_row(content, "Clock Style", lambda r: ctk.CTkOptionMenu(
            r,
            variable=self._clock_style_var,
            values=CLOCK_STYLE_NAMES,
            width=120,
            height=24,
        ))

        # Continuous Scroll
        self._scroll_var = tk.BooleanVar(value=self.config.device_settings.continuous_scroll)
        add_row(content, "Continuous Scroll", lambda r: ctk.CTkSwitch(r, text="", variable=self._scroll_var, switch_width=36, switch_height=18))

        # Run on Startup
        self._startup_var = tk.BooleanVar(value=self.config.run_on_startup)
        add_row(content, "Run on Startup", lambda r: ctk.CTkSwitch(r, text="", variable=self._startup_var, switch_width=36, switch_height=18))

        # Automatic desktop app release checks
        self._auto_update_var = tk.BooleanVar(value=self.config.auto_update_enabled)
        add_row(content, "Auto App Update", lambda r: ctk.CTkSwitch(r, text="", variable=self._auto_update_var, switch_width=36, switch_height=18))

        # Automatic firmware sync to the exact Desktop App release version.
        self._auto_firmware_update_var = tk.BooleanVar(
            value=self.config.auto_firmware_update_enabled
        )
        add_row(content, "Auto FW Update", lambda r: ctk.CTkSwitch(
            r,
            text="",
            variable=self._auto_firmware_update_var,
            switch_width=36,
            switch_height=18,
        ))

        # Auto Sleep (default off)
        self._sleep_enabled_var = tk.BooleanVar(value=self.config.device_settings.sleep_enabled)
        add_row(content, "Auto Sleep", lambda r: ctk.CTkSwitch(r, text="", variable=self._sleep_enabled_var, switch_width=36, switch_height=18))

        # Favorite apps
        favorites_frame = ctk.CTkFrame(main_frame, fg_color="#191919", corner_radius=8)
        favorites_frame.pack(fill='x', padx=12, pady=(3, 1))
        favorites_top = ctk.CTkFrame(favorites_frame, fg_color="transparent")
        favorites_top.pack(fill='x', padx=8, pady=(4, 0))
        ctk.CTkLabel(
            favorites_top,
            text="App Favorites",
            font=ctk.CTkFont(size=12),
        ).pack(side='left')
        ctk.CTkButton(
            favorites_top,
            text="Choose",
            width=78,
            height=22,
            command=self._choose_favorite_apps,
        ).pack(side='right')
        self._favorites_status_var = tk.StringVar()
        self._refresh_favorites_label()
        ctk.CTkLabel(
            favorites_frame,
            textvariable=self._favorites_status_var,
            font=ctk.CTkFont(size=10),
            text_color="#a0a0a0",
            anchor="w",
        ).pack(fill='x', padx=8, pady=(0, 3))

        # Desktop app update
        update_frame = ctk.CTkFrame(main_frame, fg_color="#191919", corner_radius=8)
        update_frame.pack(fill='x', padx=12, pady=(3, 1))
        update_top = ctk.CTkFrame(update_frame, fg_color="transparent")
        update_top.pack(fill='x', padx=8, pady=(4, 0))
        ctk.CTkLabel(
            update_top,
            text=f"Desktop App  {APP_VERSION}",
            font=ctk.CTkFont(size=12),
        ).pack(side='left')
        self.btn_app_update = ctk.CTkButton(
            update_top,
            text="Check",
            width=70,
            height=22,
            command=self._manual_check_app_update,
        )
        self.btn_app_update.pack(side='right')
        self._app_update_status_var = tk.StringVar(value="Automatic release checks enabled")
        ctk.CTkLabel(
            update_frame,
            textvariable=self._app_update_status_var,
            font=ctk.CTkFont(size=10),
            text_color="#a0a0a0",
            anchor="w",
        ).pack(fill='x', padx=8, pady=(0, 3))

        # Firmware update
        firmware_frame = ctk.CTkFrame(main_frame, fg_color="#191919", corner_radius=8)
        firmware_frame.pack(fill='x', padx=12, pady=(3, 1))
        firmware_top = ctk.CTkFrame(firmware_frame, fg_color="transparent")
        firmware_top.pack(fill='x', padx=8, pady=(4, 0))
        ctk.CTkLabel(
            firmware_top,
            text="Device Firmware",
            font=ctk.CTkFont(size=12),
        ).pack(side='left')
        firmware_actions = ctk.CTkFrame(firmware_top, fg_color="transparent")
        firmware_actions.pack(side='right')
        self.btn_firmware_versions = ctk.CTkButton(
            firmware_actions,
            text="Versions",
            width=70,
            height=22,
            command=self._choose_firmware_release,
        )
        self.btn_firmware_versions.pack(side='left', padx=(0, 4))
        self.btn_firmware = ctk.CTkButton(
            firmware_actions,
            text=".bin",
            width=48,
            height=22,
            command=self._select_firmware,
        )
        self.btn_firmware.pack(side='left')

        self._firmware_progress = ctk.CTkProgressBar(
            firmware_frame,
            height=4,
            progress_color="#00bcd4",
        )
        self._firmware_progress.pack(fill='x', padx=8, pady=(1, 1))
        self._firmware_progress.set(0)
        self._firmware_status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            firmware_frame,
            textvariable=self._firmware_status_var,
            font=ctk.CTkFont(size=10),
            text_color="#a0a0a0",
        ).pack(anchor='w', padx=8, pady=(0, 3))

        # Keep the interpreter alive from process start, but do not show
        # Settings until the tray callback asks for it.  This avoids creating
        # or destroying Tcl interpreters from worker/pystray threads.
        self._window.withdraw()
        self._update_status_loop()
        self._process_window_commands()

    def _process_window_commands(self):
        """Drain UI work exclusively on the Tcl/Tk owning thread."""
        if self._ui_thread_id is not None and threading.get_ident() != self._ui_thread_id:
            raise RuntimeError("Tk command pump executed on the wrong thread")

        try:
            while True:
                command, payload = self._window_commands.get_nowait()
                if command == "show" and self._window:
                    self._window.deiconify()
                    self._window.lift()
                    self._window.focus_force()
                elif command == "call" and payload is not None:
                    try:
                        payload()
                    except Exception:
                        log.exception("Queued Tk callback failed")
                elif command == "shutdown":
                    self._shutdown_from_ui()
                    return
        except queue.Empty:
            pass

        if self._window is not None:
            try:
                self._window.after(50, self._process_window_commands)
            except tk.TclError:
                pass

    def _shutdown_from_ui(self):
        """Destroy Tcl/Tk only from its owner thread."""
        window = self._window
        self._window = None
        if window is None:
            return
        log.info("Destroying Tk UI on MainThread")
        try:
            window.quit()
        except tk.TclError:
            pass
        try:
            window.destroy()
        except tk.TclError:
            pass

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        x = self._window.winfo_x() + event.x - self._drag_x
        y = self._window.winfo_y() + event.y - self._drag_y
        self._window.geometry(f"+{x}+{y}")

    def _on_window_close(self):
        if self._window:
            # Keep one Tcl interpreter alive. Recreating Tk roots on new
            # threads is unstable after repeated/long-lived tray sessions.
            self._window.withdraw()
        if self.on_close:
            self.on_close()

    def _update_status_loop(self):
        if not self._window or not self._window.winfo_exists():
            return
        if self.controller._device_connected:
            self.btn_toggle_conn.configure(text="Disconnect", fg_color="#dc3545", hover_color="#c82333")
        else:
            self.btn_toggle_conn.configure(text="Connect", fg_color="#28a745", hover_color="#218838")
        self.btn_toggle_conn.configure(
            state="disabled" if self.controller.firmware_updating else "normal"
        )
        if hasattr(self, "btn_firmware"):
            firmware_ready = (
                self.controller.can_update_firmware
                and not self._firmware_release_loading
            )
            state = "normal" if firmware_ready else "disabled"
            self.btn_firmware.configure(state=state)
            if hasattr(self, "btn_firmware_versions"):
                self.btn_firmware_versions.configure(state=state)

            if (
                not self.controller.firmware_updating
                and not self._firmware_release_loading
                and hasattr(self, "_firmware_status_var")
                and (
                    self._firmware_status_var.get() == "Ready"
                    or self._firmware_status_var.get().startswith("FW ")
                )
            ):
                current_fw = getattr(self.controller, "firmware_version", "unknown")
                self._firmware_status_var.set(
                    f"FW {current_fw} · PC {APP_VERSION}"
                )
        self._window.after(500, self._update_status_loop)

    def _ui_call(self, callback):
        # Worker threads must never call Tk methods directly.  Queue the
        # callback and let _process_window_commands execute it on MainThread.
        self._window_commands.put(("call", callback))

    def _manual_check_app_update(self):
        if not self.on_check_app_update:
            return
        if hasattr(self, "btn_app_update"):
            self.btn_app_update.configure(state="disabled")
        if hasattr(self, "_app_update_status_var"):
            self._app_update_status_var.set("Checking GitHub release...")
        self.on_check_app_update(True)

    def set_app_update_checking(self, checking: bool):
        if hasattr(self, "btn_app_update"):
            self.btn_app_update.configure(
                state="disabled" if checking else "normal"
            )

    def set_app_update_status(self, text: str):
        if hasattr(self, "_app_update_status_var"):
            self._app_update_status_var.set(text)
        self.set_app_update_checking(False)

    def prompt_app_update(self, info: UpdateInfo, automatic: bool = False):
        self.set_app_update_status(f"New version available: {info.tag}")
        title = "VuNMix Update Available"
        message = (
            f"Current version: {APP_VERSION}\n"
            f"New version: {info.tag}\n\n"
            "Download the official installer, verify SHA-256, and update now?"
        )
        if messagebox.askyesno(title, message, parent=self._window):
            self.start_app_update(info)
        elif automatic:
            log.info("Automatic app update prompt dismissed for %s", info.tag)

    def start_app_update(self, info: UpdateInfo):
        if not self.on_install_app_update:
            return
        self.set_app_update_checking(True)
        self._app_update_status_var.set(f"Preparing {info.tag}...")
        self.on_install_app_update(info)

    def set_app_update_progress(self, value: float, text: str):
        # Keep the settings UI compact: the download percentage is shown in
        # the status line while the updater performs checksum verification.
        percent = max(0, min(100, int(round(float(value) * 100))))
        self._app_update_status_var.set(f"{text} {percent}%")

    def _choose_firmware_release(self):
        if not self.controller.can_update_firmware:
            messagebox.showwarning("Firmware Update", "Connect VuNMix first.")
            return
        if self._firmware_release_loading:
            return

        self._firmware_release_loading = True
        self._firmware_progress.set(0)
        self._firmware_status_var.set("Loading firmware versions...")

        def worker():
            try:
                releases = self._firmware_release_client.list_releases(limit=30)
                self._ui_call(
                    lambda found=releases: self._show_firmware_release_picker(found)
                )
            except Exception as exc:
                log.exception("Firmware release list failed")
                self._ui_call(
                    lambda error=str(exc): self._firmware_release_list_failed(error)
                )

        threading.Thread(
            target=worker,
            daemon=True,
            name="FirmwareReleaseList",
        ).start()

    def _firmware_release_list_failed(self, message: str):
        self._firmware_release_loading = False
        self._firmware_progress.set(0)
        self._firmware_status_var.set(f"Release check failed: {message}")

    def _show_firmware_release_picker(self, releases):
        self._firmware_release_loading = False
        if not releases:
            self._firmware_status_var.set("No firmware releases found.")
            messagebox.showwarning(
                "Firmware Versions",
                "No stable release with a firmware image and SHA256SUMS.txt was found.",
                parent=self._window,
            )
            return

        picker = ctk.CTkToplevel(self._window)
        picker.title("Firmware Versions")
        picker.geometry("290x190")
        picker.attributes("-topmost", True)
        picker.transient(self._window)
        picker.grab_set()

        current = getattr(self.controller, "firmware_version", "unknown")
        ctk.CTkLabel(
            picker,
            text=f"Device: {current}    Desktop: {APP_VERSION}",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(14, 8))

        by_tag = {info.tag: info for info in releases}
        preferred = next(
            (info.tag for info in releases if info.version == APP_VERSION.lstrip("v")),
            releases[0].tag,
        )
        selected = tk.StringVar(value=preferred)
        ctk.CTkOptionMenu(
            picker,
            variable=selected,
            values=list(by_tag),
            width=180,
            height=28,
        ).pack(padx=12, pady=6)

        ctk.CTkLabel(
            picker,
            text="Official GitHub release · SHA-256 verified",
            font=ctk.CTkFont(size=10),
            text_color="#a0a0a0",
        ).pack(pady=(2, 8))

        buttons = ctk.CTkFrame(picker, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(0, 10))

        def install_selected():
            info = by_tag.get(selected.get())
            if info is None:
                return
            confirmed = messagebox.askyesno(
                "Firmware Update",
                f"Flash firmware {info.tag}?\n\n"
                f"Current device: {current}\n"
                f"Desktop App: {APP_VERSION}",
                parent=picker,
            )
            if not confirmed:
                return
            picker.grab_release()
            picker.destroy()
            self.start_firmware_release_update(info, automatic=False)

        ctk.CTkButton(
            buttons,
            text="Install",
            command=install_selected,
            width=90,
            height=28,
        ).pack(side="right")
        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=picker.destroy,
            width=80,
            height=28,
            fg_color="#444444",
        ).pack(side="right", padx=6)

        self._firmware_status_var.set(
            f"{len(releases)} firmware version(s) available"
        )

    def start_firmware_release_update(
        self,
        info: FirmwareReleaseInfo,
        automatic: bool = False,
    ):
        if not self.controller.can_update_firmware:
            if not automatic:
                messagebox.showwarning(
                    "Firmware Update",
                    "Connect VuNMix first.",
                    parent=self._window,
                )
            return

        self._firmware_release_loading = True
        self._firmware_progress.set(0)
        prefix = "Auto " if automatic else ""
        self._firmware_status_var.set(
            f"{prefix}downloading firmware {info.tag}..."
        )

        def worker():
            try:
                def on_download(value, text):
                    self._ui_call(
                        lambda v=value, t=text:
                            self._set_firmware_progress(v * 0.20, t)
                    )

                firmware = self._firmware_release_client.download(
                    info,
                    progress=on_download,
                )

                def on_flash(value, text):
                    self._ui_call(
                        lambda v=value, t=text:
                            self._set_firmware_progress(0.20 + (v * 0.80), t)
                    )

                def on_complete(success, message):
                    self._ui_call(
                        lambda ok=success, msg=message:
                            self._firmware_complete(
                                ok,
                                msg,
                                automatic=automatic,
                                target_version=info.version,
                            )
                    )

                started = self.controller.start_firmware_update(
                    str(firmware),
                    on_progress=on_flash,
                    on_complete=on_complete,
                )
                if not started:
                    self._ui_call(
                        lambda: self._firmware_release_start_failed(
                            "Another firmware update is already running."
                        )
                    )
            except Exception as exc:
                log.exception("Firmware release update failed")
                self._ui_call(
                    lambda error=str(exc):
                        self._firmware_release_start_failed(error)
                )

        threading.Thread(
            target=worker,
            daemon=True,
            name="FirmwareReleaseInstall",
        ).start()

    def _firmware_release_start_failed(self, message: str):
        self._firmware_release_loading = False
        self._firmware_progress.set(0)
        self._firmware_status_var.set(f"Firmware update failed: {message}")

    def _select_firmware(self):
        if not self.controller.can_update_firmware:
            messagebox.showwarning("Firmware Update", "Connect VuNMix first.")
            return

        path = filedialog.askopenfilename(
            parent=self._window,
            title="Select VuNMix firmware.bin",
            filetypes=[("ESP32 firmware", "*.bin")],
        )
        if not path:
            return

        try:
            from firmware_updater import validate_firmware
            firmware = validate_firmware(path)
        except Exception as exc:
            messagebox.showerror("Invalid Firmware", str(exc))
            return

        confirmed = messagebox.askyesno(
            "Update Firmware",
            "The device will disconnect for about one minute.\n\n"
            f"Flash {firmware.name} now?",
            parent=self._window,
        )
        if not confirmed:
            return

        self._firmware_release_loading = True
        self._firmware_progress.set(0)
        self._firmware_status_var.set("Preparing device...")

        def on_progress(value, text):
            self._ui_call(
                lambda: self._set_firmware_progress(value, text)
            )

        def on_complete(success, message):
            self._ui_call(
                lambda: self._firmware_complete(success, message)
            )

        if not self.controller.start_firmware_update(
            str(firmware),
            on_progress=on_progress,
            on_complete=on_complete,
        ):
            self._firmware_release_loading = False
            self._firmware_status_var.set("Another update is already running.")

    def _set_firmware_progress(self, value, text):
        self._firmware_progress.set(max(0.0, min(1.0, float(value))))
        self._firmware_status_var.set(text)

    def _refresh_favorites_label(self):
        favorites = sorted(set(self.config.favorite_apps))
        if favorites:
            text = ", ".join(favorites[:4])
            if len(favorites) > 4:
                text += f" +{len(favorites) - 4}"
        else:
            text = "No favorite apps selected"
        if hasattr(self, "_favorites_status_var"):
            self._favorites_status_var.set(text)

    def _choose_favorite_apps(self):
        if not self._window or not self._window.winfo_exists():
            return

        try:
            self.controller.audio.refresh()
        except Exception:
            log.exception("Failed to refresh app list for favorites")

        from protocol import DisplayMode
        apps = self.controller.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        names = sorted({item.name.lower().removesuffix(".exe") for item in apps if item.name})
        for existing in self.config.favorite_apps:
            if existing not in names:
                names.append(existing)

        picker = ctk.CTkToplevel(self._window)
        picker.title("App Favorites")
        picker.geometry("260x360")
        picker.attributes("-topmost", True)
        picker.transient(self._window)
        frame = ctk.CTkScrollableFrame(picker)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        vars_by_name = {}
        selected = set(self.config.favorite_apps)
        if not names:
            ctk.CTkLabel(frame, text="No active audio apps found.").pack(anchor="w", pady=4)
        for name in names:
            var = tk.BooleanVar(value=name in selected)
            vars_by_name[name] = var
            ctk.CTkCheckBox(frame, text=name, variable=var).pack(anchor="w", pady=3)

        buttons = ctk.CTkFrame(picker, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def apply_selection():
            self.config.favorite_apps = sorted(
                name for name, var in vars_by_name.items() if var.get()
            )
            self.controller.audio.set_favorite_apps(self.config.favorite_apps)
            self._refresh_favorites_label()
            picker.destroy()

        ctk.CTkButton(buttons, text="Apply", command=apply_selection, height=28).pack(side="right")
        ctk.CTkButton(buttons, text="Cancel", command=picker.destroy, height=28, fg_color="#444444").pack(side="right", padx=6)

    def _firmware_complete(
        self,
        success,
        message,
        automatic: bool = False,
        target_version: str = "",
    ):
        self._firmware_release_loading = False
        self._firmware_progress.set(1.0 if success else 0.0)
        if success:
            version = target_version or getattr(
                self.controller,
                "firmware_version",
                "",
            )
            display_version = str(version or "")
            if display_version and not display_version.startswith("v"):
                display_version = f"v{display_version}"
            self._firmware_status_var.set(
                f"Firmware {display_version} updated"
                if display_version
                else "Update complete"
            )
            if not automatic:
                messagebox.showinfo(
                    "Firmware Update",
                    message,
                    parent=self._window,
                )
        else:
            self._firmware_status_var.set(
                "Auto FW update failed" if automatic else "Update failed"
            )
            if not automatic:
                messagebox.showerror(
                    "Firmware Update",
                    message,
                    parent=self._window,
                )

    def _toggle_connect(self):
        if self.controller.firmware_updating:
            return
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

    def _choose_led_color(self, key):
        values = self._led_color_values.get(key)
        if not values:
            return

        initial = "#{:02x}{:02x}{:02x}".format(*values)
        rgb, hex_color = colorchooser.askcolor(
            color=initial,
            parent=self._window,
            title="Choose LED color",
        )
        if rgb is None or hex_color is None:
            return

        selected = [max(0, min(255, int(round(channel)))) for channel in rgb]
        self._led_color_values[key] = selected
        button = self._led_color_buttons.get(key)
        if button is not None:
            button.configure(fg_color=hex_color, hover_color=hex_color)

        # Preview on hardware without mutating the saved config until Save.
        if self.controller._device_connected:
            import copy
            from protocol import Color, Command

            preview_settings = copy.deepcopy(self.config.device_settings)
            for color_key, color_values in self._led_color_values.items():
                setattr(
                    preview_settings,
                    color_key,
                    Color.from_list(color_values),
                )
            self.controller.serial.send_command(
                Command.SETTINGS,
                preview_settings.pack(),
            )

    def _save(self):
        try:
            old_port = self.config.com_port
            new_port = self._com_var.get().strip()
            
            self.config.com_port = new_port
            self.config.run_on_startup = self._startup_var.get()
            self.config.auto_update_enabled = self._auto_update_var.get()
            self.config.auto_firmware_update_enabled = (
                self._auto_firmware_update_var.get()
            )
            self.config.favorite_apps = sorted(set(self.config.favorite_apps))
            sleep_minutes = max(0, int(self._sleep_var.get()))
            self.config.device_settings.sleep_after_seconds = min(
                65535, sleep_minutes * 60
            )
            self.config.device_settings.sleep_enabled = self._sleep_enabled_var.get()
            self.config.device_settings.clock_standby_minutes = max(0, min(255, int(self._clock_standby_var.get())))
            from protocol import CLOCK_STYLE_NAMES, STANDBY_LED_NAMES
            clock_style_name = self._clock_style_var.get()
            self.config.device_settings.clock_style = (
                CLOCK_STYLE_NAMES.index(clock_style_name)
                if clock_style_name in CLOCK_STYLE_NAMES
                else 0
            )
            led_name = self._led_mode_var.get()
            self.config.device_settings.standby_led_mode = STANDBY_LED_NAMES.index(led_name) if led_name in STANDBY_LED_NAMES else 0
            self.config.device_settings.continuous_scroll = self._scroll_var.get()
            self.config.device_settings.led_brightness = int(self._brightness_var.get())

            from protocol import Color
            for key, values in self._led_color_values.items():
                setattr(
                    self.config.device_settings,
                    key,
                    Color.from_list(values),
                )

            self.config.save()
            self.controller.audio.set_favorite_apps(self.config.favorite_apps)
            
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
        self._settings_dialog = None
        self._app_updater = AppUpdater(APP_VERSION)
        self._update_check_lock = threading.Lock()
        self._update_stop = threading.Event()
        self._latest_app_update = None
        self._notified_update_tag = None
        self._update_watcher_started = False
        self._firmware_release_client = FirmwareReleaseClient()
        self._firmware_auto_lock = threading.Lock()
        self._auto_firmware_attempted = set()
        self.controller.on_device_ready = self._on_device_ready

    def _create_settings_dialog(self):
        return SettingsDialog(
            self.config,
            self.controller,
            on_save=self._on_settings_saved,
            on_close=self._on_settings_closed,
            on_check_app_update=self._request_app_update_check,
            on_install_app_update=self._start_app_update_install,
        )

    def _ensure_settings_dialog(self):
        if self._settings_dialog is None:
            self._settings_dialog = self._create_settings_dialog()
        return self._settings_dialog

    def _dispatch_ui(self, callback):
        """Marshal tray/worker UI updates onto the Tk main thread."""
        self._ensure_settings_dialog()._ui_call(callback)

    def run(self):
        """Start the tray application (blocking)."""
        import pystray
        from pystray import MenuItem, Menu

        is_conn = bool(self.controller._device_connected)
        icon_image = create_tray_icon(is_conn)
        status_text = f"VuNMix - {'Connected' if is_conn else 'Disconnected'}"

        def make_preset_action(p_name):
            return lambda icon, item: self.controller.preset_service.apply_preset(p_name)

        preset_items = [
            MenuItem(name, make_preset_action(name))
            for name in self.controller.preset_service.get_preset_names()
        ]

        menu = Menu(
            MenuItem('VuNMix', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(lambda item: f"Status: {'Connected' if self.controller._device_connected else 'Disconnected'}", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('🎵 Audio Presets', Menu(*preset_items)),
            Menu.SEPARATOR,
            MenuItem('Settings', self._on_settings, default=True),
            MenuItem('Check app update', self._on_check_app_update),
            MenuItem('Reconnect', self._on_reconnect),
            Menu.SEPARATOR,
            MenuItem('Exit', self._on_exit),
        )

        # Tcl/Tk must exist on MainThread before detached tray callbacks can
        # request Settings or enqueue other UI work.
        dialog = self._ensure_settings_dialog()
        dialog.initialize()

        self._icon = pystray.Icon('VuNMix', icon_image, status_text, menu)

        # Wire connection status updates
        self.controller.on_connection_changed = self._on_connection_status

        # If already connected before icon.run() was reached
        if self.controller._device_connected:
            self._on_connection_status(True)
            self._on_device_ready()

        # pystray documents run_detached() specifically for integration with
        # another library that owns the process main loop (Tk in our case).
        self._icon.run_detached()
        self._start_app_update_watcher()
        dialog.run_loop()

    def _on_device_ready(self):
        """Check firmware only after the normal protocol handshake is complete."""
        threading.Thread(
            target=self._auto_firmware_update_worker,
            daemon=True,
            name="FirmwareAutoCheck",
        ).start()

    def _auto_firmware_update_worker(self):
        if not getattr(self.config, "auto_firmware_update_enabled", True):
            return

        current = str(
            getattr(self.controller, "firmware_version", "unknown") or "unknown"
        )
        if not should_auto_update_firmware(
            current,
            APP_VERSION,
            enabled=True,
        ):
            return

        attempt_key = (current, APP_VERSION)
        with self._firmware_auto_lock:
            if attempt_key in self._auto_firmware_attempted:
                return
            self._auto_firmware_attempted.add(attempt_key)

        try:
            info = self._firmware_release_client.get_version(APP_VERSION)
            if info is None:
                log.warning(
                    "No firmware asset matches Desktop App %s",
                    APP_VERSION,
                )
                self._dispatch_ui(
                    lambda: self._ensure_settings_dialog()._firmware_status_var.set(
                        f"No firmware matches PC {APP_VERSION}"
                    )
                )
                return

            log.info(
                "Auto firmware sync: device=%s desktop=%s release=%s",
                current,
                APP_VERSION,
                info.tag,
            )
            self._dispatch_ui(
                lambda found=info:
                    self._ensure_settings_dialog().start_firmware_release_update(
                        found,
                        automatic=True,
                    )
            )
        except Exception as exc:
            log.warning("Automatic firmware check failed: %s", exc)
            self._dispatch_ui(
                lambda error=str(exc):
                    self._ensure_settings_dialog()._firmware_status_var.set(
                        f"Auto FW check failed: {error}"
                    )
            )

    def _start_app_update_watcher(self):
        if self._update_watcher_started:
            return
        if not self.config.auto_update_enabled:
            return
        if version_tuple(APP_VERSION) is None:
            log.info("Automatic app update disabled for non-release build %s", APP_VERSION)
            return

        self._update_watcher_started = True

        def watcher():
            # Let startup/serial discovery settle before the first network call.
            if self._update_stop.wait(8.0):
                return
            while not self._update_stop.is_set():
                if self.config.auto_update_enabled:
                    self._check_app_update_worker(manual=False)
                if self._update_stop.wait(6 * 60 * 60):
                    return

        threading.Thread(
            target=watcher,
            daemon=True,
            name="AppUpdateWatch",
        ).start()

    def _request_app_update_check(self, manual: bool = True):
        threading.Thread(
            target=self._check_app_update_worker,
            args=(manual,),
            daemon=True,
            name="AppUpdateCheck",
        ).start()

    def _check_app_update_worker(self, manual: bool):
        if not self._update_check_lock.acquire(blocking=False):
            if manual:
                self._dispatch_ui(
                    lambda: self._ensure_settings_dialog().set_app_update_status(
                        "Update check already running."
                    )
                )
            return
        try:
            info = self._app_updater.check_latest()
            self._latest_app_update = info

            if info is None:
                if manual:
                    self._dispatch_ui(
                        lambda: self._ensure_settings_dialog().set_app_update_status(
                            f"Up to date: {APP_VERSION}"
                        )
                    )
                return

            should_prompt = manual or self._notified_update_tag != info.tag
            self._notified_update_tag = info.tag
            if should_prompt:
                self._dispatch_ui(
                    lambda found=info, auto=not manual:
                        self._ensure_settings_dialog().prompt_app_update(found, auto)
                )
        except Exception as exc:
            log.warning("App update check failed: %s", exc)
            if manual:
                self._dispatch_ui(
                    lambda error=str(exc):
                        self._ensure_settings_dialog().set_app_update_status(
                            f"Check failed: {error}"
                        )
                )
        finally:
            self._update_check_lock.release()

    def _start_app_update_install(self, info: UpdateInfo):
        def worker():
            try:
                def on_progress(value, text):
                    self._dispatch_ui(
                        lambda v=value, t=text:
                            self._ensure_settings_dialog().set_app_update_progress(v, t)
                    )

                path = self._app_updater.download_and_install(
                    info,
                    progress=on_progress,
                )
                log.info("App update installer started: %s", path)
                self._dispatch_ui(
                    lambda found=info: self._finish_app_update_launch(found)
                )
            except Exception as exc:
                log.exception("App update failed")
                self._dispatch_ui(
                    lambda error=str(exc):
                        self._ensure_settings_dialog().set_app_update_status(
                            f"Update failed: {error}"
                        )
                )

        threading.Thread(
            target=worker,
            daemon=True,
            name="AppUpdateInstall",
        ).start()

    def _finish_app_update_launch(self, info: UpdateInfo):
        """Show the handoff briefly, then release the running executable."""
        dialog = self._ensure_settings_dialog()
        dialog.set_app_update_status(
            f"Installing {info.tag}. VuNMix is closing..."
        )
        if dialog._window is not None:
            dialog._window.after(250, self._shutdown_for_app_update)
        else:
            self._shutdown_for_app_update()

    def _shutdown_for_app_update(self):
        """Exit cleanly so Inno Setup can replace VuNMix.exe and restart it."""
        log.info("Closing VuNMix for desktop app update")
        self._update_stop.set()
        if self._settings_dialog is not None:
            self._settings_dialog.request_shutdown()
        if self._icon is not None:
            self._icon.stop()

    def _on_connection_status(self, connected: bool):
        """Update tray state through the main-thread UI dispatcher."""
        log.info("Tray connection state changed: %s", "connected" if connected else "disconnected")

        def apply():
            if self._icon is not None:
                try:
                    self._icon.icon = create_tray_icon(connected)
                    self._icon.title = f"VuNMix - {'Connected' if connected else 'Disconnected'}"
                    self._icon.update_menu()
                except Exception as exc:
                    log.warning("Failed to update tray icon state: %s", exc)

        self._dispatch_ui(apply)

    def _on_settings(self, icon, item):
        if self._settings_open:
            return
        self._settings_open = True
        self._ensure_settings_dialog().show()

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
                self.controller._push_updated_state()

        if self.config.auto_update_enabled:
            self._start_app_update_watcher()

    def _on_check_app_update(self, icon=None, item=None):
        dialog = self._ensure_settings_dialog()
        self._dispatch_ui(lambda: dialog.set_app_update_checking(True))
        self._request_app_update_check(manual=True)

    def _on_reconnect(self, icon, item):
        log.info("Manual reconnect requested")
        self.controller.serial.disconnect()
        self.controller.serial.connect()

    def _on_exit(self, icon, item):
        log.info("Exit requested")
        self._update_stop.set()
        if self._settings_dialog is not None:
            self._settings_dialog.request_shutdown()
        if self._icon is not None:
            self._icon.stop()
