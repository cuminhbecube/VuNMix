"""Compact Fluent Dark view components for the persistent VuNMix Tk window.

Only visual code and explicit user-intent adapters belong here. Native audio,
firmware, tray, protocol and configuration remain in the existing services.
"""
from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
import customtkinter as ctk

from build_info import APP_VERSION
from fluent_theme import (ACCENT, ACCENT_HOVER, BG, BORDER, CARD, CARD_HOVER,
                          DANGER, MUTED, ONLINE, SURFACE, TEXT, NAV_ICONS,
                          SECTIONS, SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH,
                          audio_percentage)
from fluent_audio import AudioIntent
from protocol import CLOCK_STYLE_NAMES, DisplayMode
from update_center import describe_device_update

log = logging.getLogger(__name__)


class FluentViewsMixin:
    """Reusable view builders mixed into SettingsDialog, all Tk-main-thread."""

    @staticmethod
    def _fluent_card(parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=9,
                            border_width=1, border_color=BORDER)

    @staticmethod
    def _fluent_header(parent, heading, caption=None):
        ctk.CTkLabel(parent, text=heading, text_color=TEXT, anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold")
                     ).pack(fill="x", padx=9, pady=(9, 1))
        if caption:
            ctk.CTkLabel(parent, text=caption, text_color=MUTED, anchor="w",
                         font=ctk.CTkFont(size=11)
                         ).pack(fill="x", padx=9, pady=(0, 7))

    def _fluent_navigate(self, name):
        self._tabs.set(name)
        self._fluent_highlight_nav()

    def _fluent_highlight_nav(self):
        if not hasattr(self, "_sidebar_buttons"):
            return
        current = self._tabs.get()
        for name, button in self._sidebar_buttons.items():
            active = name == current
            if getattr(button, "_vunmix_selected", None) != active:
                button.configure(
                    fg_color="#183D5E" if active else "transparent",
                    text_color="#7DD5FF" if active else MUTED,
                    hover_color=CARD_HOVER,
                )
                button._vunmix_selected = active

    def _build_fluent_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=BG, width=SIDEBAR_WIDTH,
                               corner_radius=8)
        sidebar.pack(side="left", fill="y", padx=(1, 5), pady=1)
        sidebar.pack_propagate(False)
        self._sidebar = sidebar
        self._sidebar_collapsed = False
        self._sidebar_buttons = {}
        self._sidebar_workspace_label = ctk.CTkLabel(
            sidebar, text="WORKSPACE", anchor="w", text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self._sidebar_workspace_label.pack(fill="x", padx=10, pady=(8, 5))
        for index, name in enumerate(SECTIONS):
            button = ctk.CTkButton(
                sidebar, text=f"{NAV_ICONS[index]}   {name}", width=135, height=34,
                corner_radius=7, anchor="w", fg_color="transparent",
                text_color=MUTED, hover_color=CARD_HOVER,
                font=ctk.CTkFont(size=12),
                command=lambda page=name: self._fluent_navigate(page),
            )
            button.pack(fill="x", padx=5, pady=1)
            self._sidebar_buttons[name] = button
        self._sidebar_toggle_button = ctk.CTkButton(
            sidebar, text="‹  Collapse", fg_color="transparent",
            text_color=MUTED, hover_color=CARD_HOVER,
            height=27, command=self._toggle_fluent_sidebar,
        )
        self._sidebar_toggle_button.pack(side="bottom", fill="x", padx=5, pady=6)
        self._fluent_highlight_nav()

    def _set_fluent_sidebar_collapsed(self, collapsed):
        """Preserve one-click access to all six routes on narrow screens."""
        collapsed = bool(collapsed)
        self._sidebar_collapsed = collapsed
        self._sidebar.configure(
            width=SIDEBAR_COLLAPSED_WIDTH if collapsed else SIDEBAR_WIDTH
        )
        if collapsed:
            self._sidebar_workspace_label.pack_forget()
        elif not self._sidebar_workspace_label.winfo_manager():
            self._sidebar_workspace_label.pack(fill="x", padx=10, pady=(8, 5),
                                                before=self._sidebar_buttons[SECTIONS[0]])
        for index, name in enumerate(SECTIONS):
            self._sidebar_buttons[name].configure(
                text=NAV_ICONS[index] if collapsed else f"{NAV_ICONS[index]}   {name}",
                width=36 if collapsed else 135,
                anchor="center" if collapsed else "w",
            )
        self._sidebar_toggle_button.configure(
            text="›" if collapsed else "‹  Collapse",
            width=35 if collapsed else 135,
        )

    def _toggle_fluent_sidebar(self):
        self._set_fluent_sidebar_collapsed(not self._sidebar_collapsed)

    def build_fluent_overview(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=1, pady=1)
        self._fluent_header(body, "Overview")

        self._overview_connection_var = tk.StringVar(value="Disconnected")
        self._overview_firmware_var = tk.StringVar(value="Not verified")
        self._overview_clock_var = tk.StringVar(value="Clock not selected")
        self._overview_memory_var = tk.StringVar(value="PC memory unavailable")
        summaries = ctk.CTkFrame(body, fg_color="transparent")
        summaries.pack(fill="x", padx=4, pady=(0, 4))
        for i in range(4):
            summaries.grid_columnconfigure(i, weight=1, uniform="status")
        for col, (label, icon, value) in enumerate((
            ("USB Connection", "⌁", self._overview_connection_var),
            ("Firmware", "▣", self._overview_firmware_var),
            ("Clock Style", "◷", self._overview_clock_var),
            ("PC Memory", "▤", self._overview_memory_var),
        )):
            card = self._fluent_card(summaries)
            card.grid(row=0, column=col, sticky="nsew", padx=3)
            ctk.CTkLabel(card, text=f"{icon}  {label}", text_color=MUTED,
                         anchor="w", font=ctk.CTkFont(size=11)
                         ).pack(fill="x", padx=8, pady=(4, 0))
            ctk.CTkLabel(card, textvariable=value, text_color=TEXT,
                         anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
                         wraplength=165
                         ).pack(fill="x", padx=8, pady=(0, 5))

        center = ctk.CTkFrame(body, fg_color="transparent")
        center.pack(fill="both", expand=True, padx=4, pady=1)
        center.grid_columnconfigure(0, weight=3)
        center.grid_columnconfigure(1, weight=1)
        audio_box = self._fluent_card(center)
        audio_box.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._fluent_header(audio_box, "Audio Mixer")
        self._overview_audio_host = ctk.CTkFrame(audio_box, fg_color="transparent")
        self._overview_audio_host.pack(fill="both", expand=True, padx=3, pady=(0, 2))
        ctk.CTkButton(
            audio_box, text="All audio / Game Mixer  →", height=26,
            fg_color="#183D5E", text_color=TEXT,
            command=lambda: self._fluent_navigate("Audio"),
        ).pack(fill="x", padx=6, pady=(0, 5))

        clock = self._fluent_card(center)
        clock.grid(row=0, column=1, sticky="nsew")
        self._fluent_header(clock, "Clock Preview")
        self._overview_clock_face = tk.StringVar(value=time.strftime("%H:%M"))
        ctk.CTkLabel(clock, textvariable=self._overview_clock_face,
                     fg_color="#07101C", text_color="#78CCF3",
                     font=ctk.CTkFont(family="Segoe UI", size=34, weight="bold"),
                     corner_radius=8, height=64
                     ).pack(fill="x", padx=6, pady=(0, 4))
        self._overview_clock_caption = tk.StringVar(value="Neon Digital")
        ctk.CTkLabel(clock, textvariable=self._overview_clock_caption,
                     text_color=MUTED, font=ctk.CTkFont(size=11)
                     ).pack(pady=(0, 5))
        ctk.CTkButton(clock, text="Clock gallery  →", height=28,
                      fg_color="#183D5E", text_color=TEXT,
                      command=lambda: self._fluent_navigate("Clock")
                      ).pack(fill="x", padx=6, pady=(0, 5))

        actions = self._fluent_card(body)
        actions.pack(fill="x", padx=4, pady=(3, 3))
        ctk.CTkLabel(actions, text="Quick Actions", text_color=TEXT,
                     anchor="w", font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(fill="x", padx=8, pady=(4, 1))
        row = ctk.CTkFrame(actions, fg_color="transparent")
        row.pack(fill="x", padx=5, pady=(0, 5))
        for label, callback in (
            ("Update Center", lambda: self._fluent_navigate("Updates")),
            ("Flash Firmware", self._select_firmware),
            ("Open Logs", self._fluent_open_logs),
            ("Diagnostics", self._fluent_diagnostics),
        ):
            ctk.CTkButton(
                row, text=label, height=27, fg_color="#183D5E",
                hover_color=CARD_HOVER, font=ctk.CTkFont(size=11),
                command=callback,
            ).pack(side="left", fill="x", expand=True, padx=3)

        strip = self._fluent_card(body)
        strip.pack(fill="x", padx=4, pady=(1, 2))
        self._overview_obs = tk.StringVar(value="OBS: Disconnected")
        self._overview_media = tk.StringVar(value="Media: Idle")
        self._overview_profile = tk.StringVar(value="Profile: Default")
        for variable in (self._overview_obs, self._overview_media,
                         self._overview_profile):
            ctk.CTkLabel(strip, textvariable=variable, anchor="w",
                         text_color=MUTED, font=ctk.CTkFont(size=11),
                         width=190
                         ).pack(side="left", fill="x", expand=True, padx=5, pady=4)

    def build_fluent_audio(self, parent):
        """One activity per viewport, not four eight-row mixers plus tools."""
        self._fluent_header(parent, "Audio Control Center")
        self._audio_page = "Mixer"
        self._audio_page_switcher = ctk.CTkSegmentedButton(
            parent, values=["Mixer", "Profiles", "Media / OBS"],
            height=29, command=self._fluent_show_audio_page,
        )
        self._audio_page_switcher.pack(fill="x", padx=7, pady=(0, 6))
        self._audio_pages_host = ctk.CTkFrame(parent, fg_color="transparent")
        self._audio_pages_host.pack(fill="both", expand=True, padx=5, pady=(0, 3))
        self._audio_mixer_page = ctk.CTkFrame(
            self._audio_pages_host, fg_color="transparent",
        )
        self._audio_profiles_page = ctk.CTkFrame(
            self._audio_pages_host, fg_color="transparent",
        )
        self._audio_media_page = ctk.CTkFrame(
            self._audio_pages_host, fg_color="transparent",
        )
        self._audio_page_frames = {
            "Mixer": self._audio_mixer_page,
            "Profiles": self._audio_profiles_page,
            "Media / OBS": self._audio_media_page,
        }
        self._audio_page_index = 0
        self._audio_source_var = tk.StringVar(value="Output")
        selector = ctk.CTkFrame(self._audio_mixer_page, fg_color="transparent")
        selector.pack(fill="x", padx=4, pady=(1, 3))
        ctk.CTkLabel(
            selector, text="Source", text_color=MUTED, width=50,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(2, 4))
        self._audio_mode_menu = ctk.CTkOptionMenu(
            selector, values=["Output", "Input", "Applications", "Game Mixer"],
            variable=self._audio_source_var, width=140, height=27,
            command=self._fluent_audio_source_changed,
        )
        self._audio_mode_menu.pack(side="left")
        ctk.CTkLabel(
            selector, text="4 items per page · More via Next",
            text_color=MUTED, font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=4)
        self._audio_detail_host = ctk.CTkFrame(
            self._audio_mixer_page, fg_color="transparent",
        )
        self._audio_detail_host.pack(fill="both", expand=True, padx=3, pady=1)
        pager = ctk.CTkFrame(self._audio_mixer_page, fg_color="transparent")
        pager.pack(fill="x", padx=7, pady=4)
        self._audio_page_label = tk.StringVar(value="Page 1 / 1")
        ctk.CTkButton(
            pager, text="‹ Previous", width=96, height=27,
            fg_color="#183D5E",
            command=lambda: self._fluent_audio_change_page(-1),
        ).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            pager, textvariable=self._audio_page_label,
            text_color=MUTED, font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            pager, text="Next ›", width=80, height=27,
            fg_color="#183D5E",
            command=lambda: self._fluent_audio_change_page(1),
        ).pack(side="left", padx=5)
        self._fluent_build_audio_utilities(
            self._audio_profiles_page, self._audio_media_page,
        )
        self._fluent_show_audio_page("Mixer")
        self._audio_page_switcher.set("Mixer")

    def _fluent_show_audio_page(self, name):
        if name not in self._audio_page_frames:
            return
        self._audio_page = name
        for title, page in self._audio_page_frames.items():
            if title == name:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self._audio_render_signature = None
        self._last_audio_snapshot = 0.0

    def _fluent_audio_source_changed(self, name):
        self._audio_source_var.set(name)
        self._audio_page_index = 0
        self._audio_render_signature = None
        self._last_audio_snapshot = 0.0

    def _fluent_audio_change_page(self, direction):
        modes = {
            "Output": DisplayMode.MODE_OUTPUT,
            "Input": DisplayMode.MODE_INPUT,
            "Applications": DisplayMode.MODE_APPLICATION,
            "Game Mixer": DisplayMode.MODE_GAME,
        }
        mode = modes[self._audio_source_var.get()]
        total = len(self.controller.audio.get_sessions_for_mode(mode))
        last = max(0, (total - 1) // 4)
        self._audio_page_index = max(0, min(
            last, self._audio_page_index + direction
        ))
        self._audio_render_signature = None
        self._last_audio_snapshot = 0.0

    def _fluent_build_audio_utilities(self, parent, media_parent=None):
        tools = self._fluent_card(parent)
        tools.pack(fill="x", padx=4, pady=8)
        self._fluent_header(tools, "Profiles · Automation")
        actions = ctk.CTkFrame(tools, fg_color="transparent")
        actions.pack(fill="x", padx=7, pady=(0, 8))
        preset_service = getattr(self.controller, "preset_service", None)
        profile_names = list(preset_service.get_preset_names()) if preset_service else []
        self._profile_choice = tk.StringVar(value=profile_names[0] if profile_names else "None")
        ctk.CTkOptionMenu(
            actions, values=profile_names or ["None"],
            variable=self._profile_choice, width=125, height=29,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            actions, text="Apply", width=66, height=29,
            command=self._fluent_apply_profile,
        ).pack(side="left", padx=3)
        for label, handler in (
            ("Routing", "toggle_routing"),
            ("Ducking", "toggle_ducking"),
            ("Rules", "open_audio_automation_config"),
        ):
            ctk.CTkButton(
                actions, text=label, height=29, width=77, fg_color="#183D5E",
                command=lambda op=handler: self._fluent_run_async(
                    op, lambda: getattr(self.controller, op)()),
            ).pack(side="left", padx=3)

        media = self._fluent_card(media_parent or parent)
        media.pack(fill="x", padx=4, pady=4)
        self._fluent_header(media, "Media & OBS Studio")
        row = ctk.CTkFrame(media, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 8))
        from media_service import (MEDIA_ACTION_PREVIOUS, MEDIA_ACTION_NEXT,
                                   MEDIA_ACTION_PLAY_PAUSE)
        for label, action in (
            ("Previous", MEDIA_ACTION_PREVIOUS),
            ("Play/Pause", MEDIA_ACTION_PLAY_PAUSE),
            ("Next", MEDIA_ACTION_NEXT),
        ):
            ctk.CTkButton(
                row, text=label, height=29, width=85, fg_color="#183D5E",
                command=lambda code=action: self._fluent_run_async(
                    "media", lambda: self.controller.media_service.execute_control(code)),
            ).pack(side="left", padx=3)
        obs = getattr(self.controller, "obs_service", None)
        if obs is None:
            return
        for label, handler in (
            ("OBS Stream", obs.toggle_streaming),
            ("OBS Record", obs.toggle_recording),
        ):
            ctk.CTkButton(
                row, text=label, height=29, width=85, fg_color="#183D5E",
                command=lambda fn=handler: self._fluent_run_async("OBS", fn),
            ).pack(side="left", padx=3)
        row2 = ctk.CTkFrame(media, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(0, 7))
        ctk.CTkButton(
            row2, text="Mute OBS Mic", height=28, fg_color="#183D5E",
            command=lambda: self._fluent_run_async(
                "OBS mic", lambda: obs.toggle_input_mute(obs.mic_input)),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row2, text="Mute Desktop", height=28, fg_color="#183D5E",
            command=lambda: self._fluent_run_async(
                "OBS desktop", lambda: obs.toggle_input_mute(obs.desktop_input)),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row2, text="Next OBS Scene", height=28, fg_color="#183D5E",
            command=self._fluent_next_obs_scene,
        ).pack(side="left", padx=3)

    def _fluent_next_obs_scene(self):
        obs = self.controller.obs_service
        scenes = list(obs.scenes)
        if len(scenes) < 2:
            return
        try:
            current_index = scenes.index(obs.current_scene)
        except ValueError:
            current_index = -1
        next_scene = scenes[(current_index + 1) % len(scenes)]
        self._fluent_run_async("OBS scene",
                               lambda: obs.switch_scene(next_scene))

    def _fluent_apply_profile(self):
        name = self._profile_choice.get()
        if name != "None":
            def apply():
                if hasattr(self.controller, "apply_profile"):
                    self.controller.apply_profile(name, source="ui")
                else:
                    self.controller.preset_service.apply_preset(name)
            self._fluent_run_async("profile", apply)

    def _fluent_run_async(self, label, action):
        def worker():
            try:
                action()
            except Exception:
                log.exception("Control Center action failed: %s", label)
        threading.Thread(
            target=worker, daemon=True, name="VuNMixUiAction"
        ).start()

    def _fluent_open_logs(self):
        self._fluent_run_async("logs", self.controller.open_log_folder)

    def _fluent_diagnostics(self):
        try:
            report = self.controller.diagnostic_report()
            self._window.clipboard_clear()
            self._window.clipboard_append(report)
        except Exception:
            log.exception("Could not copy diagnostics to clipboard")

    def build_fluent_update_heading(self, parent):
        self._fluent_header(parent, "Update Center",
                            "Desktop + ESP32-S3 firmware · SHA-256 verified")
        self._update_center_var = tk.StringVar(value="Checking device compatibility...")
        ctk.CTkLabel(parent, textvariable=self._update_center_var,
                     text_color=MUTED, anchor="w", justify="left",
                     wraplength=700, font=ctk.CTkFont(size=11)
                     ).pack(fill="x", padx=11, pady=(0, 6))
        cols = ctk.CTkFrame(parent, fg_color="transparent")
        cols.pack(fill="x", padx=7, pady=3)
        cols.grid_columnconfigure(0, weight=3)
        cols.grid_columnconfigure(1, weight=2)
        self._updates_left = self._fluent_card(cols)
        self._updates_left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._updates_right = self._fluent_card(cols)
        self._updates_right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        ctk.CTkLabel(self._updates_left, text="Desktop & Firmware",
                     text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(fill="x", padx=10, pady=(10, 2))
        ctk.CTkLabel(self._updates_right, text="Device Preview & Health",
                     text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(fill="x", padx=10, pady=(10, 2))
        self._updates_device_status = tk.StringVar(value="ESP32-S3 — Disconnected")
        ctk.CTkLabel(self._updates_right, textvariable=self._updates_device_status,
                     text_color=MUTED, anchor="w", justify="left",
                     wraplength=300).pack(fill="x", padx=10, pady=(4, 2))
        self._updates_health = tk.StringVar(value="PC health metrics: pending")
        ctk.CTkLabel(self._updates_right, textvariable=self._updates_health,
                     text_color=MUTED, anchor="w", justify="left",
                     wraplength=300).pack(fill="x", padx=10, pady=(1, 9))
        self._updates_gallery_area = self._fluent_card(parent)
        self._updates_gallery_area.pack(fill="x", padx=7, pady=(6, 7))

    def build_fluent_clock_gallery(self, parent, *, include_preview=False):
        self._fluent_header(parent, "Clock Style Gallery · 16 styles")
        if include_preview:
            self._clock_preview_var = tk.StringVar()
            ctk.CTkLabel(
                parent, textvariable=self._clock_preview_var, height=43,
                fg_color="#07101C", text_color="#7DD5FF",
                font=ctk.CTkFont(size=20, weight="bold"), corner_radius=8,
            ).pack(fill="x", padx=9, pady=(0, 8))
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=(2, 10))
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1, uniform="clocks")
        tones = ("#50C8FB", "#C9E1F3", "#B9CDD9", "#C8DBE8",
                 "#49BDEB", "#4CD697", "#78E3A7", "#A6D87C",
                 "#F7AE72", "#E1DED0", "#7ACCF8", "#EFB56C",
                 "#CC87E9", "#F4EEE6", "#64B4EE", "#C4D7EE")
        previews = ("10:24", "10:24", "10  24", "◷ 10:24",
                    "◌ 10:24", "1010 0101", "> 10:24", "10:24",
                    "10:24", "TEN TWENTY FOUR", "10:24", "● ● ●",
                    "10:24", "||| 10:24 |||", "◈ 10:24", "∫ 10:24")
        for index, name in enumerate(CLOCK_STYLE_NAMES):
            frame = self._fluent_card(grid)
            frame.grid(row=index // 4, column=index % 4,
                       sticky="nsew", padx=3, pady=3)
            ctk.CTkButton(
                frame, text=previews[index], height=35, fg_color="#09131F",
                hover_color="#183D5E", text_color=tones[index],
                font=ctk.CTkFont(size=15, weight="bold"),
                command=lambda i=index: self._fluent_choose_clock(i),
            ).pack(fill="x", padx=3, pady=(4, 0))
            ctk.CTkLabel(
                frame, text=f"{index+1}. {name}", text_color=MUTED,
                font=ctk.CTkFont(size=10)
            ).pack(pady=(3, 5))
        if include_preview:
            self._clock_style_var.trace_add(
                "write", lambda *_: self._clock_preview_var.set(
                    f"{self._clock_style_var.get()}   ·   {time.strftime('%H:%M')}"
                )
            )
            self._clock_preview_var.set(
                f"{self._clock_style_var.get()}   ·   {time.strftime('%H:%M')}"
            )

    def _fluent_choose_clock(self, index):
        if index >= len(CLOCK_STYLE_NAMES):
            return
        connected = bool(getattr(self.controller, "_device_connected", False))
        firmware = str(getattr(self.controller, "firmware_version", "unknown"))
        compatibility = describe_device_update(APP_VERSION, firmware, connected)
        if (connected and compatibility.compatible_clock_styles is not None
                and index >= compatibility.compatible_clock_styles):
            from tkinter import messagebox
            messagebox.showwarning(
                "VuNMix Clock",
                "This firmware does not support that clock style. "
                "Update firmware first.",
                parent=self._window,
            )
            return
        self._clock_style_var.set(CLOCK_STYLE_NAMES[index])

    def build_fluent_update_actions(self):
        row = ctk.CTkFrame(self._updates_left, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(2, 8))
        for label, callback in (
            ("Changelog", self._fluent_changelog),
            ("Backup Settings", self._fluent_backup_settings),
            ("Open Logs", self._fluent_open_logs),
        ):
            ctk.CTkButton(
                row, text=label, height=28,
                fg_color="#183D5E", text_color=TEXT,
                command=callback,
            ).pack(side="left", fill="x", expand=True, padx=2)

    def _fluent_changelog(self):
        import webbrowser
        webbrowser.open("https://github.com/cuminhbecube/VuNMix/releases/latest")

    def _fluent_backup_settings(self):
        """Export the existing persisted user config, never an invented backup."""
        import pathlib
        import shutil
        from tkinter import filedialog, messagebox
        from config import CONFIG_DIR
        source = pathlib.Path(CONFIG_DIR) / "config.json"
        if not source.is_file():
            messagebox.showwarning(
                "VuNMix", "No saved config.json found. Save Settings first.",
                parent=self._window,
            )
            return
        destination = filedialog.asksaveasfilename(
            parent=self._window,
            title="Export VuNMix settings",
            initialfile="VuNMix-config-backup.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not destination:
            return
        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            messagebox.showerror("VuNMix", f"Backup failed: {exc}",
                                 parent=self._window)

    def build_fluent_updates_settings(self):
        panel = self._fluent_card(self._updates_right)
        panel.pack(fill="x", padx=7, pady=(4, 8))
        ctk.CTkLabel(panel, text="Display & Power", text_color=TEXT,
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).pack(anchor="w", padx=9, pady=(7, 3))
        ctk.CTkLabel(panel, text="Brightness", text_color=MUTED,
                     anchor="w").pack(fill="x", padx=9)
        ctk.CTkSlider(panel, variable=self._brightness_var, from_=0, to=255,
                      command=self._on_brightness_change,
                      height=14).pack(fill="x", padx=9, pady=(2, 8))
        for label, variable in (
            ("Auto Sleep", self._sleep_enabled_var),
            ("Auto App Update", self._auto_update_var),
            ("Auto FW Update", self._auto_firmware_update_var),
        ):
            ctk.CTkSwitch(panel, text=label, variable=variable,
                          height=28, switch_width=37,
                          switch_height=18).pack(anchor="w", padx=9, pady=2)
        ctk.CTkButton(
            panel, text="More device settings →", fg_color="#183D5E",
            height=27, command=lambda: self._fluent_navigate("Device"),
        ).pack(fill="x", padx=8, pady=8)

    def _fluent_audio_drag(self, key, mode, index, item, muted, amount, label):
        percentage = audio_percentage(amount)
        label.configure(text=f"{percentage}%")
        self._last_audio_interaction = time.monotonic()
        key = (int(mode), getattr(item, "_device_id", "") or
               getattr(item, "_session_identifier", "") or id(item))
        pending = getattr(self, "_audio_slider_jobs", {})
        previous = pending.pop(key, None)
        if previous is not None:
            try:
                self._window.after_cancel(previous)
            except tk.TclError:
                pass

        def submit():
            pending.pop(key, None)
            self._audio_dispatcher.submit(
                AudioIntent("volume", int(mode), index, item, percentage, muted)
            )

        pending[key] = self._window.after(240, submit)
        self._audio_slider_jobs = pending

    def _render_fluent_audio(self, host, count):
        for child in host.winfo_children():
            child.destroy()
        groups = [
            ("Output", DisplayMode.MODE_OUTPUT),
            ("Input", DisplayMode.MODE_INPUT),
            ("Applications", DisplayMode.MODE_APPLICATION),
        ]
        if count > 2:
            groups.append(("Game Mixer", DisplayMode.MODE_GAME))
        for n, (heading, mode) in enumerate(groups):
            card = self._fluent_card(host)
            card.grid(row=0, column=n, sticky="nsew", padx=3)
            host.grid_columnconfigure(n, weight=1, uniform="audio")
            ctk.CTkLabel(card, text=heading, text_color=TEXT,
                         font=ctk.CTkFont(size=12, weight="bold")
                         ).pack(fill="x", padx=7, pady=(7, 5))
            items = self.controller.audio.get_sessions_for_mode(mode)[:count]
            if not items:
                ctk.CTkLabel(card, text="No active sessions", text_color=MUTED,
                             font=ctk.CTkFont(size=10)
                             ).pack(padx=6, pady=7)
            for index, item in enumerate(items):
                section = ctk.CTkFrame(card, fg_color=SURFACE, corner_radius=6)
                section.pack(fill="x", padx=5, pady=3)
                heading_row = ctk.CTkFrame(section, fg_color="transparent")
                heading_row.pack(fill="x", padx=5, pady=(4, 0))
                ctk.CTkLabel(
                    heading_row, text=str(item.name)[:28], text_color=TEXT,
                    font=ctk.CTkFont(size=11), anchor="w",
                ).pack(side="left", fill="x", expand=True)
                if mode != DisplayMode.MODE_APPLICATION and not item.is_default:
                    ctk.CTkButton(
                        heading_row, text="★", width=23, height=19,
                        fg_color="transparent", text_color=MUTED,
                        command=lambda m=mode, idx=index, target=item:
                            self._audio_dispatcher.submit(
                                AudioIntent("default", int(m), idx, target)
                            ),
                    ).pack(side="right")
                vol_row = ctk.CTkFrame(section, fg_color="transparent")
                vol_row.pack(fill="x", padx=4, pady=(0, 4))
                amount = ctk.CTkLabel(vol_row, text=f"{item.volume}%",
                                      text_color=MUTED, width=33,
                                      font=ctk.CTkFont(size=10))
                # Bind the read snapshot identity, never mutable list position
                ctk.CTkSlider(
                    vol_row, from_=0, to=100, width=95, height=15,
                    command=lambda value, m=mode, idx=index, target=item,
                                   muted=item.is_muted, lbl=amount:
                        self._fluent_audio_drag(None, m, idx, target,
                                                muted, value, lbl),
                ).pack(side="left", fill="x", expand=True, padx=(1, 2))
                # Set initial slider value without dispatching a real change.
                slider = vol_row.winfo_children()[-1]
                slider.set(audio_percentage(item.volume))
                amount.pack(side="left")
                ctk.CTkButton(
                    vol_row, text="M" if item.is_muted else "♪",
                    width=26, height=24, fg_color="#223951",
                    command=lambda m=mode, idx=index, target=item:
                        self._audio_dispatcher.submit(
                            AudioIntent("volume", int(m), idx, target,
                                        int(target.volume), not bool(target.is_muted))
                        )
                ).pack(side="right", padx=(2, 0))

    def refresh_fluent_content(self):
        """Main-thread bounded refresh; never enumerate Windows COM here."""
        if not hasattr(self, "_tabs"):
            return
        now = time.monotonic()
        connected = bool(getattr(self.controller, "_device_connected", False))
        firmware = str(getattr(self.controller, "firmware_version", "unknown"))
        port = getattr(self.controller.serial, "port", "") or ""
        self._overview_connection_var.set(
            f"Online · {port}" if connected else "Disconnected"
        )
        self._header_status_var.set("● Connected" if connected else "○ Disconnected")
        self._fluent_highlight_nav()
        self._overview_firmware_var.set(firmware if connected else "Not verified")
        clock_name = self._clock_style_var.get()
        self._overview_clock_var.set(clock_name)
        self._overview_clock_caption.set(clock_name)
        self._overview_clock_face.set(time.strftime("%H:%M"))
        state = describe_device_update(APP_VERSION, firmware, connected)
        self._update_center_var.set(
            f"Desktop {state.desktop_version}   /   Firmware "
            f"{state.firmware_version}  ·  {state.status}"
        )
        self._updates_device_status.set(
            f"ESP32-S3 · {'Connected' if connected else 'Disconnected'} "
            f"· {state.compatible_clock_styles or 'Unknown'} clock styles available"
        )
        if now - self._last_overview_snapshot >= 5.0:
            try:
                import psutil
                proc = psutil.Process()
                ram = proc.memory_info().rss / (1024 * 1024)
                self._overview_memory_var.set(f"{ram:.1f} MiB RSS")
                self._updates_health.set(
                    f"Windows PC process: {ram:.1f} MiB RSS · "
                    f"{proc.num_threads()} threads"
                )
            except Exception:
                self._overview_memory_var.set("PC memory unavailable")
                self._updates_health.set("PC health metrics unavailable")
            self._last_overview_snapshot = now
        if now - getattr(self, "_last_fluent_strip", 0) >= 3.0:
            try:
                obs = self.controller.obs_service
                self._overview_obs.set(
                    "OBS: " + (("LIVE" if obs.is_streaming else
                                  "Connected") if obs.is_connected else "Offline")
                )
            except Exception:
                self._overview_obs.set("OBS: Unavailable")
            try:
                snap = self.controller.media_service.cached_snapshot()
                self._overview_media.set(
                    "Media: " + (snap.info.title[:34] if snap.info.title else "Idle")
                )
            except Exception:
                self._overview_media.set("Media: Unavailable")
            self._overview_profile.set(
                "Profile: " + str(getattr(self.controller, "active_profile", None)
                                  or "Default")
            )
            self._last_fluent_strip = now
        current = self._tabs.get()
        if current not in ("Overview", "Audio") or now - self._last_audio_snapshot < 2.5:
            return
        if now - getattr(self, "_last_audio_interaction", 0) < 1.4:
            return
        try:
            target_host = (self._overview_audio_host if current == "Overview"
                           else self._audio_detail_host)
            # Read snapshots are guarded by AudioService's own state lock.
            snapshot = []
            for mode in (DisplayMode.MODE_OUTPUT, DisplayMode.MODE_INPUT,
                         DisplayMode.MODE_APPLICATION,
                         DisplayMode.MODE_GAME):
                snapshot.extend(
                    (int(mode), item._device_id, item._session_identifier,
                     item.name, item.volume, item.is_muted, item.is_default)
                    for item in self.controller.audio.get_sessions_for_mode(mode)[:8]
                )
            signature = (current, tuple(snapshot))
            if signature != self._audio_render_signature:
                self._render_fluent_audio(target_host, 2 if current == "Overview" else 8)
                self._audio_render_signature = signature
            self._last_audio_snapshot = now
        except Exception:
            log.debug("Could not render Windows Audio preview", exc_info=True)
