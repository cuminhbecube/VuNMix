"""Windows dark view components for the persistent VuNMix Tk window.

Only visual code and explicit user-intent adapters belong here. Native audio,
firmware, tray, protocol and configuration remain in the existing services.
"""
from __future__ import annotations

import logging
import math
import threading
import time
import tkinter as tk
from datetime import datetime
import customtkinter as ctk
from PIL import Image, ImageDraw

from build_info import APP_VERSION
from fluent_theme import (ACCENT, ACCENT_HOVER, BG, BORDER, CARD, CARD_HOVER,
                          INPUT, MUTED, ONLINE, SURFACE, TEXT, FONT_FAMILY,
                          SECTIONS, SIDEBAR_WIDTH, SIDEBAR_COLLAPSED_WIDTH,
                          audio_percentage)
from fluent_audio import AudioIntent
from protocol import CLOCK_STYLE_NAMES, DisplayMode
from update_center import describe_device_update

log = logging.getLogger(__name__)


def _navigation_icon(name, color=MUTED):
    """Small, consistent line icons, independent of installed symbol fonts."""
    scale = 3
    canvas = Image.new("RGBA", (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(canvas)

    def line(points, width=1.5):
        draw.line([(round(x * scale), round(y * scale)) for x, y in points],
                  fill=color, width=round(width * scale), joint="curve")

    def rect(box, radius=2):
        draw.rounded_rectangle(tuple(round(v * scale) for v in box),
                               radius=radius * scale, outline=color,
                               width=round(1.5 * scale))

    def circle(box):
        draw.ellipse(tuple(round(v * scale) for v in box),
                     outline=color, width=round(1.5 * scale))

    if name == "Overview":
        line([(3, 11), (12, 3), (21, 11)])
        line([(6, 9), (6, 20), (10, 20), (10, 14), (14, 14),
              (14, 20), (18, 20), (18, 9)])
    elif name == "Audio":
        for x, y in ((5, 8), (12, 16), (19, 10)):
            line([(x, 3), (x, y - 3)])
            line([(x, y + 3), (x, 21)])
            rect((x - 2.4, y - 2.5, x + 2.4, y + 2.5), radius=1)
    elif name == "Clock":
        circle((3, 3, 21, 21))
        line([(12, 6), (12, 12), (16, 14)])
    elif name == "Device":
        rect((5, 2, 19, 22), radius=3)
        rect((8, 5, 16, 14), radius=1)
        circle((10, 16.5, 14, 20.5))
    elif name == "Updates":
        line([(12, 3), (12, 15), (7, 10)])
        line([(12, 15), (17, 10)])
        line([(4, 15), (4, 20), (20, 20), (20, 15)])
    elif name == "Settings":
        circle((6, 6, 18, 18))
        circle((9.5, 9.5, 14.5, 14.5))
        for angle in range(0, 360, 45):
            theta = math.radians(angle)
            line([(12 + 7 * math.cos(theta), 12 + 7 * math.sin(theta)),
                  (12 + 10 * math.cos(theta), 12 + 10 * math.sin(theta))], 2)
    else:
        line([(5, 6), (19, 6)])
        line([(5, 12), (19, 12)])
        line([(5, 18), (19, 18)])
    return ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(20, 20))


class FluentViewsMixin:
    """Reusable view builders mixed into SettingsDialog, all Tk-main-thread."""

    @staticmethod
    def _fluent_card(parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=6,
                            border_width=0)

    @staticmethod
    def _fluent_header(parent, heading, caption=None):
        ctk.CTkLabel(parent, text=heading, text_color=TEXT, anchor="w",
                     height=30,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold")
                     ).pack(fill="x", padx=16, pady=(10, 0 if caption else 10))
        if caption:
            ctk.CTkLabel(parent, text=caption, text_color=MUTED, anchor="w",
                         height=20, font=ctk.CTkFont(size=12)
                         ).pack(fill="x", padx=16, pady=(2, 12))

    @staticmethod
    def _fluent_section_title(parent, title, *, action=None, command=None):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        row.pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkLabel(row, text=title, anchor="w", height=24,
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(side="left", fill="x", expand=True)
        if action:
            ctk.CTkButton(row, text=action, width=88, height=32,
                          fg_color="transparent", border_width=0,
                          text_color=ACCENT, command=command
                          ).pack(side="right")
        return row

    def _fluent_navigate(self, name):
        self._tabs.set(name)
        self._fluent_highlight_nav()
        self._last_audio_snapshot = 0.0
        self._audio_render_signature = None
        if hasattr(self, "_clock_style_var"):
            self._refresh_clock_images(force=True)

    def _fluent_highlight_nav(self):
        if not hasattr(self, "_sidebar_buttons"):
            return
        current = self._tabs.get()
        for name, button in self._sidebar_buttons.items():
            active = name == current
            if getattr(button, "_vunmix_selected", None) != active:
                button.configure(
                    fg_color=CARD if active else "transparent",
                    text_color=TEXT if active else MUTED,
                    hover_color=CARD_HOVER,
                    image=self._sidebar_icons[(name, active)],
                )
                indicator = self._sidebar_indicators[name]
                if active:
                    indicator.place(x=0, rely=0.5, anchor="w")
                else:
                    indicator.place_forget()
                button._vunmix_selected = active

    def _build_fluent_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=BG, width=SIDEBAR_WIDTH,
                               corner_radius=0)
        sidebar.pack(side="left", fill="y", padx=(0, 10), pady=0)
        sidebar.pack_propagate(False)
        self._sidebar = sidebar
        self._sidebar_collapsed = False
        self._sidebar_manual_override = False
        self._sidebar_buttons = {}
        self._sidebar_indicators = {}
        self._sidebar_icons = {
            (name, selected): _navigation_icon(name, TEXT if selected else MUTED)
            for name in SECTIONS for selected in (False, True)
        }
        self._sidebar_workspace_label = ctk.CTkLabel(
            sidebar, text="CONTROL CENTER", anchor="w", text_color=MUTED,
            height=22, font=ctk.CTkFont(size=12),
        )
        self._sidebar_workspace_label.pack(fill="x", padx=14, pady=(14, 12))
        for name in SECTIONS:
            row = ctk.CTkFrame(sidebar, fg_color="transparent", height=42)
            row.pack(fill="x", padx=4, pady=2)
            row.pack_propagate(False)
            button = ctk.CTkButton(
                row, text=name, width=SIDEBAR_WIDTH - 12, height=38,
                image=self._sidebar_icons[(name, False)], compound="left",
                corner_radius=5, border_width=0, anchor="w", fg_color="transparent",
                text_color=MUTED, hover_color=CARD_HOVER,
                font=ctk.CTkFont(size=13), border_spacing=8,
                command=lambda page=name: self._fluent_navigate(page),
            )
            button.pack(fill="both", expand=True, padx=4, pady=1)
            self._sidebar_buttons[name] = button
            self._sidebar_indicators[name] = ctk.CTkFrame(
                row, width=3, height=18, corner_radius=2, fg_color=ACCENT,
            )
        self._sidebar_toggle_button = ctk.CTkButton(
            sidebar, text="Collapse menu", fg_color="transparent",
            image=_navigation_icon("Menu"), compound="left", anchor="w",
            border_width=0, border_spacing=6,
            text_color=MUTED, hover_color=CARD_HOVER,
            height=36, command=self._toggle_fluent_sidebar,
        )
        self._sidebar_toggle_button.pack(side="bottom", fill="x", padx=8, pady=12)
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
            self._sidebar_workspace_label.pack(
                fill="x", padx=14, pady=(14, 12),
                before=self._sidebar_buttons[SECTIONS[0]].master,
            )
        for name in SECTIONS:
            self._sidebar_buttons[name].configure(
                text="" if collapsed else name,
                width=40 if collapsed else SIDEBAR_WIDTH - 12,
                border_spacing=4 if collapsed else 8,
                anchor="center" if collapsed else "w",
            )
        self._sidebar_toggle_button.configure(
            text="" if collapsed else "Collapse menu",
            width=40 if collapsed else SIDEBAR_WIDTH - 12,
            border_spacing=4 if collapsed else 6,
            anchor="center" if collapsed else "w",
        )

    def _toggle_fluent_sidebar(self):
        self._sidebar_manual_override = True
        self._set_fluent_sidebar_collapsed(not self._sidebar_collapsed)

    def _fluent_window_resized(self, event):
        """Keep content wide when the user resizes below desktop width."""
        if (event.widget is not self._window or
                getattr(self, "_sidebar_manual_override", False)):
            return
        width = event.width / ctk.ScalingTracker.get_window_scaling(self._window)
        if width < 940 and not self._sidebar_collapsed:
            self._set_fluent_sidebar_collapsed(True)
        elif width > 1060 and self._sidebar_collapsed:
            self._set_fluent_sidebar_collapsed(False)

    def build_fluent_overview(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self._fluent_header(body, "Overview")

        self._overview_connection_var = tk.StringVar(value="Disconnected")
        self._overview_firmware_var = tk.StringVar(value="Not connected")
        self._overview_clock_var = tk.StringVar(value="Neon Digital")
        self._overview_memory_var = tk.StringVar(value="Not available")
        summaries = self._fluent_card(body)
        summaries.pack(fill="x", padx=16, pady=(0, 12))
        for column, (label, variable) in enumerate((
            ("Device", self._overview_connection_var),
            ("Firmware", self._overview_firmware_var),
            ("App memory", self._overview_memory_var),
        )):
            summaries.grid_columnconfigure(column, weight=1, uniform="status")
            item = ctk.CTkFrame(summaries, fg_color="transparent")
            item.grid(row=0, column=column, sticky="nsew", padx=12, pady=6)
            ctk.CTkLabel(item, text=label, text_color=MUTED, height=18,
                         anchor="w", font=ctk.CTkFont(size=12)
                         ).pack(fill="x")
            ctk.CTkLabel(item, textvariable=variable, text_color=TEXT,
                         height=22, anchor="w", font=ctk.CTkFont(size=13)
                         ).pack(fill="x")

        center = ctk.CTkFrame(body, fg_color="transparent")
        center.pack(fill="both", expand=True, padx=16)
        center.grid_columnconfigure(0, weight=1)
        center.grid_columnconfigure(1, weight=0, minsize=224)
        center.grid_rowconfigure(0, weight=1)
        audio_box = self._fluent_card(center)
        audio_box.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._fluent_section_title(
            audio_box, "Audio mixer", action="Open mixer",
            command=lambda: self._fluent_navigate("Audio"),
        )
        self._overview_audio_host = ctk.CTkFrame(audio_box, fg_color="transparent")
        self._overview_audio_host.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        clock = self._fluent_card(center)
        clock.grid(row=0, column=1, sticky="nsew")
        self._fluent_section_title(clock, "Device clock")
        self._overview_clock_image_label = ctk.CTkLabel(clock, text="", width=176, height=132)
        self._overview_clock_image_label.pack(padx=16, pady=(2, 4))
        self._overview_clock_caption = tk.StringVar(value="Neon Digital")
        ctk.CTkLabel(clock, textvariable=self._overview_clock_caption,
                     text_color=MUTED, height=20, font=ctk.CTkFont(size=12)
                     ).pack(fill="x", padx=12)
        ctk.CTkButton(clock, text="Choose a clock", height=32,
                      command=lambda: self._fluent_navigate("Clock")
                      ).pack(fill="x", padx=12, pady=(2, 6))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(8, 0))
        for column, (label, callback) in enumerate((
            ("Updates", lambda: self._fluent_navigate("Updates")),
            ("Install firmware", self._select_firmware),
            ("Open logs", self._fluent_open_logs),
            ("Copy diagnostics", self._fluent_diagnostics),
        )):
            actions.grid_columnconfigure(column, weight=1, uniform="quick")
            ctk.CTkButton(actions, text=label, height=32, width=100,
                          command=callback
                          ).grid(row=0, column=column, sticky="ew",
                                 padx=(0 if column == 0 else 4,
                                       0 if column == 3 else 4))

        strip = ctk.CTkFrame(body, fg_color="transparent")
        strip.pack(fill="x", padx=16, pady=(6, 6))
        self._overview_obs = tk.StringVar(value="OBS: disconnected")
        self._overview_media = tk.StringVar(value="Media: idle")
        self._overview_profile = tk.StringVar(value="Profile: Default")
        for column, variable in enumerate((self._overview_obs,
                                            self._overview_media,
                                            self._overview_profile)):
            strip.grid_columnconfigure(column, weight=1, uniform="integration")
            ctk.CTkLabel(strip, textvariable=variable, anchor="w", height=18,
                         text_color=MUTED, font=ctk.CTkFont(size=12)
                         ).grid(row=0, column=column, sticky="ew", padx=(0, 8))

    def build_fluent_audio(self, parent):
        """Cached audio state and explicit controls, with one source per page."""
        self._fluent_header(parent, "Audio")
        self._audio_page = "Mixer"
        self._audio_page_switcher = ctk.CTkSegmentedButton(
            parent, values=["Mixer", "Profiles", "Media / OBS"],
            height=34, command=self._fluent_show_audio_page,
        )
        self._audio_page_switcher.pack(fill="x", padx=16, pady=(0, 10))
        self._audio_pages_host = ctk.CTkFrame(parent, fg_color="transparent")
        self._audio_pages_host.pack(fill="both", expand=True, padx=16, pady=(0, 8))
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
        selector.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(selector, text="Source", text_color=MUTED, height=32,
                     font=ctk.CTkFont(size=13)
                     ).pack(side="left", padx=(0, 12))
        self._audio_mode_menu = ctk.CTkOptionMenu(
            selector, values=["Output", "Input", "Applications", "Game Mixer"],
            variable=self._audio_source_var, width=180, height=34,
            command=self._fluent_audio_source_changed,
        )
        self._audio_mode_menu.pack(side="left")
        ctk.CTkLabel(selector, text="Windows audio", text_color=MUTED,
                     height=32, font=ctk.CTkFont(size=12)
                     ).pack(side="right")

        # Reserve the pager first so it stays visible on short displays.
        pager = ctk.CTkFrame(self._audio_mixer_page, fg_color="transparent")
        pager.pack(side="bottom", fill="x", pady=(8, 0))
        self._audio_page_label = tk.StringVar(value="Page 1 of 1")
        ctk.CTkLabel(pager, textvariable=self._audio_page_label, height=32,
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left")
        self._audio_next_button = ctk.CTkButton(
            pager, text="Next", width=80, height=32,
            command=lambda: self._fluent_audio_change_page(1),
        )
        self._audio_next_button.pack(side="right")
        self._audio_previous_button = ctk.CTkButton(
            pager, text="Previous", width=88, height=32,
            command=lambda: self._fluent_audio_change_page(-1),
        )
        self._audio_previous_button.pack(side="right", padx=(0, 8))
        self._audio_detail_host = ctk.CTkFrame(
            self._audio_mixer_page, fg_color="transparent",
        )
        self._audio_detail_host.pack(fill="both", expand=True)
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
        profile = self._fluent_card(parent)
        profile.pack(fill="x", pady=(0, 10))
        self._fluent_section_title(profile, "Audio profile")
        actions = ctk.CTkFrame(profile, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        preset_service = getattr(self.controller, "preset_service", None)
        profile_names = list(preset_service.get_preset_names()) if preset_service else []
        self._profile_choice = tk.StringVar(value=profile_names[0] if profile_names else "None")
        ctk.CTkOptionMenu(actions, values=profile_names or ["None"],
                          variable=self._profile_choice, width=220, height=34
                          ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(actions, text="Apply profile", width=120, height=34,
                      state="normal" if profile_names else "disabled",
                      command=self._fluent_apply_profile
                      ).pack(side="right")

        automation = self._fluent_card(parent)
        automation.pack(fill="x", pady=(0, 2))
        self._fluent_section_title(
            automation, "Automation", action="Edit rules",
            command=lambda: self._fluent_run_async(
                "automation rules", self.controller.open_audio_automation_config),
        )
        self._routing_enabled_var = tk.BooleanVar(
            value=bool(getattr(self.controller, "routing_enabled", False)))
        self._ducking_enabled_var = tk.BooleanVar(
            value=bool(getattr(self.controller, "ducking_enabled", False)))
        for label, caption, attribute, variable in (
            ("App routing", "Send each app to its preferred output.",
             "routing_enabled", self._routing_enabled_var),
            ("Audio ducking", "Lower other apps while a trigger is active.",
             "ducking_enabled", self._ducking_enabled_var),
        ):
            row = ctk.CTkFrame(automation, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkSwitch(
                row, text=label, variable=variable, height=32,
                switch_width=38, switch_height=20, width=172,
                command=lambda attr=attribute, var=variable:
                    self._fluent_set_automation(attr, bool(var.get())),
            ).pack(side="left", padx=(0, 12))
            ctk.CTkLabel(row, text=caption, anchor="w", height=32,
                         text_color=MUTED, font=ctk.CTkFont(size=12)
                         ).pack(side="left", fill="x", expand=True)

        media = self._fluent_card(media_parent or parent)
        media.pack(fill="x", pady=(0, 12))
        self._fluent_section_title(media, "Media playback")
        self._audio_media_status = tk.StringVar(value="No media playing")
        ctk.CTkLabel(media, textvariable=self._audio_media_status,
                     text_color=MUTED, anchor="w", height=22,
                     font=ctk.CTkFont(size=12)
                     ).pack(fill="x", padx=12, pady=(0, 6))
        row = ctk.CTkFrame(media, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))
        from media_service import (MEDIA_ACTION_PREVIOUS, MEDIA_ACTION_NEXT,
                                   MEDIA_ACTION_PLAY_PAUSE)
        for column, (label, action) in enumerate((
            ("Previous", MEDIA_ACTION_PREVIOUS),
            ("Play / pause", MEDIA_ACTION_PLAY_PAUSE),
            ("Next", MEDIA_ACTION_NEXT),
        )):
            row.grid_columnconfigure(column, weight=1, uniform="playback")
            ctk.CTkButton(
                row, text=label, height=34, width=100,
                command=lambda code=action: self._fluent_run_async(
                    "media", lambda: self.controller.media_service.execute_control(code)),
            ).grid(row=0, column=column, sticky="ew", padx=4)

        obs_panel = self._fluent_card(media_parent or parent)
        obs_panel.pack(fill="x")
        self._fluent_section_title(obs_panel, "OBS Studio")
        self._audio_obs_status = tk.StringVar(value="OBS is disconnected")
        ctk.CTkLabel(obs_panel, textvariable=self._audio_obs_status,
                     text_color=MUTED, anchor="w", height=22,
                     font=ctk.CTkFont(size=12)
                     ).pack(fill="x", padx=12, pady=(0, 8))
        self._obs_action_buttons = []
        obs = getattr(self.controller, "obs_service", None)
        if obs is None:
            return
        rows = (
            (("Toggle streaming", obs.toggle_streaming),
             ("Toggle recording", obs.toggle_recording)),
            (("Mute microphone", lambda: obs.toggle_input_mute(obs.mic_input)),
             ("Mute desktop", lambda: obs.toggle_input_mute(obs.desktop_input)),
             ("Next scene", self._fluent_next_obs_scene)),
        )
        for actions in rows:
            row = ctk.CTkFrame(obs_panel, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(0, 10))
            for column, (label, handler) in enumerate(actions):
                row.grid_columnconfigure(column, weight=1, uniform="obs")
                # Scene selection reads only the cached OBS list. All network
                # and control actions still execute outside the Tk loop.
                command = (handler if label == "Next scene" else
                           lambda fn=handler: self._fluent_run_async("OBS", fn))
                button = ctk.CTkButton(
                    row, text=label, height=34, width=100,
                    state="normal" if obs.is_connected else "disabled",
                    command=command,
                )
                button.grid(row=0, column=column, sticky="ew", padx=4)
                self._obs_action_buttons.append(button)

    def _fluent_set_automation(self, attribute, enabled):
        """Capture the switch value on Tk; controller work remains async."""
        self._fluent_run_async(
            attribute, lambda: getattr(self.controller, "set_" + attribute)(enabled),
        )

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
        self._fluent_header(parent, "Updates")
        self._update_center_var = tk.StringVar(value="Checking device compatibility…")
        ctk.CTkLabel(
            parent, textvariable=self._update_center_var, text_color=MUTED,
            anchor="w", height=22, font=ctk.CTkFont(size=12), wraplength=620,
        ).pack(fill="x", padx=16, pady=(0, 12))
        cols = ctk.CTkFrame(parent, fg_color="transparent")
        cols.pack(fill="x", padx=16)
        cols.grid_columnconfigure(0, weight=3, minsize=296)
        cols.grid_columnconfigure(1, weight=2, minsize=202)
        self._updates_left = self._fluent_card(cols)
        self._updates_left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._updates_right = self._fluent_card(cols)
        self._updates_right.grid(row=0, column=1, sticky="nsew")
        self._fluent_section_title(self._updates_left, "Software")
        self._fluent_section_title(self._updates_right, "Device")
        self._updates_device_status = tk.StringVar(value="ESP32-S3 · Disconnected")
        ctk.CTkLabel(
            self._updates_right, textvariable=self._updates_device_status,
            text_color=TEXT, anchor="w", justify="left", height=38,
            font=ctk.CTkFont(size=12), wraplength=225,
        ).pack(fill="x", padx=12, pady=(0, 8))
        self._updates_health = tk.StringVar(value="Waiting for app metrics")
        ctk.CTkLabel(
            self._updates_right, textvariable=self._updates_health,
            text_color=MUTED, anchor="w", justify="left", height=34,
            wraplength=225, font=ctk.CTkFont(size=12),
        ).pack(fill="x", padx=12)
        self._updates_gallery_area = ctk.CTkFrame(parent, fg_color="transparent")
        self._updates_gallery_area.pack(fill="x", padx=16, pady=(12, 0))

    def build_fluent_update_clock_shortcuts(self):
        row = ctk.CTkFrame(self._updates_gallery_area, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(
            row, text="16 clock styles for your device", text_color=MUTED,
            height=32, font=ctk.CTkFont(size=12),
        ).pack(side="left")
        ctk.CTkButton(
            row, text="Explore clocks", height=32, width=128,
            command=lambda: self._fluent_navigate("Clock"),
        ).pack(side="right")

    def build_fluent_clock_gallery(self, parent, *, include_preview=False):
        """Real device frames, a visible selection and two readable pages."""
        self._fluent_header(parent, "Clock", "Choose how your device shows the time.")
        self._clock_preview_var = tk.StringVar(value=self._clock_style_var.get())
        self._clock_gallery_page = 0
        self._clock_gallery_page_size = 8
        self._clock_gallery_columns = 4
        self._clock_thumbnail_images = {}
        self._clock_tiles = {}
        self._clock_gallery_buttons = {}
        self._clock_tile_labels = {}
        self._clock_thumbnail_size = (84, 63)

        # Reserve the saved setting before the gallery consumes remaining room.
        settings = self._fluent_card(parent)
        settings.pack(side="bottom", fill="x", padx=16, pady=(10, 12))
        ctk.CTkLabel(settings, text="Show clock after", height=34,
                     font=ctk.CTkFont(size=13)
                     ).pack(side="left", padx=(12, 10), pady=8)
        ctk.CTkEntry(settings, textvariable=self._clock_standby_var,
                     width=58, height=34, justify="center"
                     ).pack(side="left", pady=8)
        ctk.CTkLabel(settings, text="min of inactivity   ·   0 disables standby",
                     text_color=MUTED, height=34, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=10, pady=8)

        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16)
        self._clock_gallery_content = content
        content.grid_columnconfigure(1 if include_preview else 0, weight=1)
        if include_preview:
            selected = self._fluent_card(content)
            selected.grid(row=0, column=0, sticky="new", padx=(0, 16))
            ctk.CTkLabel(selected, text="Selected style", text_color=ACCENT,
                         anchor="w", height=20, font=ctk.CTkFont(size=12)
                         ).pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(selected, textvariable=self._clock_preview_var,
                         anchor="w", height=28,
                         font=ctk.CTkFont(size=16, weight="bold")
                         ).pack(fill="x", padx=12, pady=(0, 8))
            self._clock_selected_image_label = ctk.CTkLabel(
                selected, text="", width=224, height=168,
            )
            self._clock_selected_image_label.pack(padx=12)
            ctk.CTkLabel(selected, text="Preview uses your PC time.",
                         height=20, text_color=MUTED, font=ctk.CTkFont(size=12)
                         ).pack(fill="x", padx=12, pady=(8, 12))

        gallery = ctk.CTkFrame(content, fg_color="transparent")
        gallery.grid(row=0, column=1 if include_preview else 0, sticky="new")
        self._clock_gallery_range = tk.StringVar(value="Styles 1–8 of 16")
        ctk.CTkLabel(gallery, textvariable=self._clock_gallery_range,
                     anchor="w", height=24, text_color=MUTED,
                     font=ctk.CTkFont(size=12)
                     ).pack(fill="x", pady=(0, 8))
        self._clock_gallery_grid = ctk.CTkFrame(gallery, fg_color="transparent")
        self._clock_gallery_grid.pack(fill="x")
        for column in range(4):
            self._clock_gallery_grid.grid_columnconfigure(
                column, weight=1, uniform="clocks")
        for index, name in enumerate(CLOCK_STYLE_NAMES):
            tile = ctk.CTkFrame(
                self._clock_gallery_grid, fg_color=CARD,
                corner_radius=5, border_width=2, border_color=CARD,
            )
            self._clock_tiles[index] = tile
            image = self._clock_thumbnail(index, self._clock_thumbnail_size)
            button = ctk.CTkButton(
                tile, text="", image=image, width=92, height=71,
                border_width=0, border_spacing=0, corner_radius=0,
                fg_color="#000000", hover_color=INPUT,
                command=lambda i=index: self._fluent_choose_clock(i),
            )
            button.pack(fill="x", padx=6, pady=(6, 0))
            self._clock_gallery_buttons[index] = button
            label = ctk.CTkLabel(
                tile, text=name, text_color=MUTED, height=28,
                font=ctk.CTkFont(size=12), wraplength=90,
            )
            label.pack(fill="x", padx=4, pady=(0, 2))
            label.bind("<Button-1>", lambda _event, i=index: self._fluent_choose_clock(i))
            self._clock_tile_labels[index] = label
        self._clock_gallery_grid.bind("<Configure>", self._resize_clock_gallery)

        pager = ctk.CTkFrame(gallery, fg_color="transparent")
        pager.pack(fill="x", pady=(4, 0))
        self._clock_page_var = tk.StringVar(value="1 / 2")
        self._clock_previous_button = ctk.CTkButton(
            pager, text="Previous", width=88, height=32,
            command=lambda: self._show_clock_gallery_page(self._clock_gallery_page - 1),
        )
        self._clock_previous_button.pack(side="left")
        ctk.CTkLabel(pager, textvariable=self._clock_page_var, text_color=MUTED,
                     height=32, font=ctk.CTkFont(size=12)
                     ).pack(side="left", expand=True)
        self._clock_next_button = ctk.CTkButton(
            pager, text="Next", width=72, height=32,
            command=lambda: self._show_clock_gallery_page(self._clock_gallery_page + 1),
        )
        self._clock_next_button.pack(side="right")
        content.bind("<Configure>", self._resize_clock_gallery)
        self._clock_style_var.trace_add("write", self._clock_style_changed)
        self._clock_style_changed()

    def _clock_thumbnail(self, index, size):
        from clock_preview import render_clock_preview
        key = (index, size)
        if key not in self._clock_thumbnail_images:
            image = render_clock_preview(index, size=(size[0] * 2, size[1] * 2))
            self._clock_thumbnail_images[key] = ctk.CTkImage(
                light_image=image, dark_image=image, size=size,
            )
        return self._clock_thumbnail_images[key]

    def _resize_clock_gallery(self, event):
        # CTkFrame.bind attaches to its drawing canvas. Read the containing
        # frame instead of rejecting that canvas's Configure event.
        if self._clock_gallery_grid.winfo_width() < 100:
            return
        # Use four tiles on a page when an explicitly expanded sidebar leaves
        # little width. Both layouts retain two rows and all sixteen styles.
        logical_width = (self._clock_gallery_grid.winfo_width()
                         / ctk.ScalingTracker.get_widget_scaling(self._clock_gallery_grid))
        logical_height = (self._clock_gallery_content.winfo_height()
                          / ctk.ScalingTracker.get_widget_scaling(self._clock_gallery_content))
        columns = 4 if logical_width >= 352 else 2
        page_size = columns * 2
        if columns != self._clock_gallery_columns:
            first_visible = self._clock_gallery_page * self._clock_gallery_page_size
            selected_name = self._clock_style_var.get()
            selected_index = (CLOCK_STYLE_NAMES.index(selected_name)
                              if selected_name in CLOCK_STYLE_NAMES else 0)
            if first_visible <= selected_index < first_visible + self._clock_gallery_page_size:
                first_visible = selected_index
            self._clock_gallery_columns = columns
            self._clock_gallery_page_size = page_size
            for column in range(4):
                self._clock_gallery_grid.grid_columnconfigure(
                    column, weight=1 if column < columns else 0, minsize=0,
                    uniform="clocks" if column < columns else "")
            self._show_clock_gallery_page(first_visible // page_size)
        max_width = 120 if columns == 4 else 88
        if logical_height >= 200:
            # Heading, pager and tile captions consume 180 logical pixels.
            # Scale the images to the remaining height on short screens.
            height_width = int((logical_height - 180) * 2 / 3) // 4 * 4
            max_width = min(max_width, max(64, height_width))
        width = max(64, min(max_width,
                           (int(logical_width) // columns - 24) // 4 * 4))
        size = (width, width * 3 // 4)
        if size == self._clock_thumbnail_size:
            return
        self._clock_thumbnail_size = size
        # Drop obsolete raster sizes rather than retaining every resize step.
        self._clock_thumbnail_images.clear()
        for index, button in self._clock_gallery_buttons.items():
            button.configure(image=self._clock_thumbnail(index, size),
                             width=size[0] + 8, height=size[1] + 8)
            self._clock_tile_labels[index].configure(wraplength=size[0] + 8)

    def _show_clock_gallery_page(self, page):
        page_size = self._clock_gallery_page_size
        columns = self._clock_gallery_columns
        pages = max(1, (len(CLOCK_STYLE_NAMES) + page_size - 1) // page_size)
        self._clock_gallery_page = max(0, min(pages - 1, int(page)))
        start = self._clock_gallery_page * page_size
        for index, tile in self._clock_tiles.items():
            if start <= index < start + page_size:
                position = index - start
                tile.grid(row=position // columns, column=position % columns,
                          sticky="nsew", padx=3, pady=4)
            else:
                tile.grid_remove()
        last = min(start + page_size, len(CLOCK_STYLE_NAMES))
        self._clock_gallery_range.set(f"Styles {start + 1}–{last} of {len(CLOCK_STYLE_NAMES)}")
        self._clock_page_var.set(f"{self._clock_gallery_page + 1} / {pages}")
        self._clock_previous_button.configure(
            state="normal" if self._clock_gallery_page else "disabled")
        self._clock_next_button.configure(
            state="normal" if self._clock_gallery_page + 1 < pages else "disabled")

    def _clock_style_changed(self, *_):
        name = self._clock_style_var.get()
        index = CLOCK_STYLE_NAMES.index(name) if name in CLOCK_STYLE_NAMES else 0
        self._clock_preview_var.set(CLOCK_STYLE_NAMES[index])
        self._overview_clock_caption.set(CLOCK_STYLE_NAMES[index])
        self._show_clock_gallery_page(index // self._clock_gallery_page_size)
        for tile_index, tile in self._clock_tiles.items():
            active = tile_index == index
            tile.configure(border_color=ACCENT if active else CARD)
            self._clock_tile_labels[tile_index].configure(
                text_color=ACCENT if active else MUTED)
        self._refresh_clock_images(force=True)

    def _refresh_clock_images(self, *, force=False):
        """Only the visible preview ticks; gallery thumbnails stay stable."""
        if not hasattr(self, "_clock_style_var"):
            return
        if not force and not self._window.winfo_viewable():
            return
        current = self._tabs.get()
        if current not in ("Overview", "Clock"):
            return
        name = self._clock_style_var.get()
        index = CLOCK_STYLE_NAMES.index(name) if name in CLOCK_STYLE_NAMES else 0
        now = datetime.now()
        key = (current, index, now.hour, now.minute, now.second)
        if not force and key == getattr(self, "_clock_image_key", None):
            return
        from clock_preview import render_clock_preview
        if current == "Overview":
            size = (176, 132)
            label = self._overview_clock_image_label
        elif hasattr(self, "_clock_selected_image_label"):
            size = (224, 168)
            label = self._clock_selected_image_label
        else:
            return
        raster = render_clock_preview(index, size=(size[0] * 2, size[1] * 2), now=now)
        preview = ctk.CTkImage(light_image=raster, dark_image=raster, size=size)
        label.configure(image=preview)
        # CTk retains the image; keep one explicit reference per view as well.
        if current == "Overview":
            self._overview_clock_image = preview
        else:
            self._clock_selected_image = preview
        self._clock_image_key = key

    def _fluent_choose_clock(self, index):
        if not 0 <= index < len(CLOCK_STYLE_NAMES):
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
        row.pack(fill="x", padx=12, pady=(8, 12))
        for column, (label, callback) in enumerate((
            ("Changelog", self._fluent_changelog),
            ("Backup", self._fluent_backup_settings),
            ("Logs", self._fluent_open_logs),
        )):
            row.grid_columnconfigure(column, weight=1, uniform="update-actions")
            ctk.CTkButton(row, text=label, height=32, width=72,
                          command=callback
                          ).grid(row=0, column=column, sticky="ew", padx=3)

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
        panel = ctk.CTkFrame(self._updates_right, fg_color="transparent")
        panel.pack(fill="x", padx=12, pady=(12, 12))
        ctk.CTkLabel(panel, text="Automatic updates", text_color=TEXT,
                     height=24, anchor="w", font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(fill="x", pady=(0, 6))
        for label, variable in (
            ("Desktop app", self._auto_update_var),
            ("Device firmware", self._auto_firmware_update_var),
        ):
            ctk.CTkSwitch(panel, text=label, variable=variable,
                          height=32, switch_width=38, switch_height=20
                          ).pack(anchor="w", pady=3)
        ctk.CTkButton(
            panel, text="Device settings", height=34,
            command=lambda: self._fluent_navigate("Device"),
        ).pack(fill="x", pady=(14, 0))

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
        """Render cached sessions with their original identity and index.

        Four rows fill the Mixer; Overview shows the default output/input and
        the first application. No enumeration or native audio call runs here.
        """
        for child in host.winfo_children():
            child.destroy()
        compact = count != 0
        if not compact:
            modes = {
                "Output": DisplayMode.MODE_OUTPUT,
                "Input": DisplayMode.MODE_INPUT,
                "Applications": DisplayMode.MODE_APPLICATION,
                "Game Mixer": DisplayMode.MODE_GAME,
            }
            title = self._audio_source_var.get()
            groups = [(title, modes[title])]
        else:
            groups = [
                ("Output", DisplayMode.MODE_OUTPUT),
                ("Input", DisplayMode.MODE_INPUT),
                ("Apps", DisplayMode.MODE_APPLICATION),
            ]
        for heading, mode in groups:
            all_items = self.controller.audio.get_sessions_for_mode(mode)
            if not compact:
                total_pages = max(1, (len(all_items) + 3) // 4)
                self._audio_page_index = min(self._audio_page_index, total_pages - 1)
                start = self._audio_page_index * 4
                items = list(enumerate(all_items))[start:start + 4]
                self._audio_page_label.set(
                    f"Page {self._audio_page_index + 1} of {total_pages}"
                    f"   ·   {len(all_items)} items")
                self._audio_previous_button.configure(
                    state="normal" if self._audio_page_index else "disabled")
                self._audio_next_button.configure(
                    state="normal" if self._audio_page_index + 1 < total_pages else "disabled")
            else:
                indexed = list(enumerate(all_items))
                preferred = next((entry for entry in indexed if entry[1].is_default), None)
                items = [preferred] if preferred else indexed[:count]
            if not items:
                empty = ctk.CTkFrame(host, fg_color="transparent" if compact else CARD,
                                     corner_radius=6)
                empty.pack(fill="x", pady=(0, 6))
                if compact:
                    ctk.CTkLabel(empty, text=heading, text_color=MUTED,
                                 anchor="w", height=20, font=ctk.CTkFont(size=12)
                                 ).pack(fill="x", padx=8, pady=(4, 0))
                    ctk.CTkLabel(empty, text="No active audio", text_color=TEXT,
                                 anchor="w", height=30, font=ctk.CTkFont(size=13)
                                 ).pack(fill="x", padx=8, pady=(0, 4))
                else:
                    ctk.CTkLabel(empty, text="No active audio in this source",
                                 height=32, font=ctk.CTkFont(size=14)
                                 ).pack(fill="x", padx=16, pady=(24, 2))
                    ctk.CTkLabel(
                        empty, text="Connect an audio device or start playback to see it here.",
                        text_color=MUTED, height=24, font=ctk.CTkFont(size=12),
                    ).pack(fill="x", padx=16, pady=(0, 24))
            for index, item in items:
                section = ctk.CTkFrame(host, fg_color="transparent" if compact else CARD,
                                       corner_radius=6)
                section.pack(fill="x", pady=(0, 4))
                heading_row = ctk.CTkFrame(section, fg_color="transparent", height=18)
                heading_row.pack(fill="x", padx=8 if compact else 12, pady=(2, 0))
                if compact:
                    ctk.CTkLabel(heading_row, text=heading, text_color=MUTED,
                                 height=18, width=48, anchor="w",
                                 font=ctk.CTkFont(size=12)
                                 ).pack(side="left", padx=(0, 6))
                name = str(item.name)
                limit = 34 if compact else 72
                if len(name) > limit:
                    name = name[:limit - 1] + "…"
                ctk.CTkLabel(heading_row, text=name, text_color=TEXT,
                             height=18,
                             font=ctk.CTkFont(size=13), anchor="w"
                             ).pack(side="left", fill="x", expand=True)

                controls = ctk.CTkFrame(section, fg_color="transparent", height=32)
                controls.pack(fill="x", padx=8 if compact else 12, pady=(0, 2))
                if not compact and mode in (DisplayMode.MODE_OUTPUT, DisplayMode.MODE_INPUT):
                    if item.is_default:
                        ctk.CTkLabel(controls, text="Default", text_color=MUTED,
                                     width=100, height=32, anchor="w",
                                     font=ctk.CTkFont(size=12)
                                     ).pack(side="left", padx=(0, 12))
                    else:
                        ctk.CTkButton(
                            controls, text="Set default", width=100, height=32,
                            command=lambda m=mode, idx=index, target=item:
                                self._audio_dispatcher.submit(
                                    AudioIntent("default", int(m), idx, target)),
                        ).pack(side="left", padx=(0, 12))
                mute = ctk.CTkButton(
                    controls, text="Unmute" if item.is_muted else "Mute",
                    width=68, height=32,
                    text_color=ACCENT if item.is_muted else TEXT,
                    command=lambda m=mode, idx=index, target=item:
                        self._audio_dispatcher.submit(
                            AudioIntent("volume", int(m), idx, target,
                                        int(target.volume), not bool(target.is_muted))),
                )
                mute.pack(side="right", padx=(8, 0))
                amount = ctk.CTkLabel(
                    controls, text=f"{audio_percentage(item.volume)}%", text_color=MUTED,
                    width=42, height=32, font=ctk.CTkFont(size=12),
                )
                amount.pack(side="right", padx=(8, 0))
                slider = ctk.CTkSlider(
                    controls, from_=0, to=100, width=100, height=20,
                    command=lambda value, m=mode, idx=index, target=item,
                                   muted=item.is_muted, lbl=amount:
                        self._fluent_audio_drag(None, m, idx, target, muted, value, lbl),
                )
                slider.pack(side="left", fill="x", expand=True)
                slider.set(audio_percentage(item.volume))

    def refresh_fluent_content(self):
        """Main-thread bounded refresh; never enumerate Windows COM here."""
        if not hasattr(self, "_tabs"):
            return
        now = time.monotonic()
        connected = bool(getattr(self.controller, "_device_connected", False))
        firmware = str(getattr(self.controller, "firmware_version", "unknown"))
        port = getattr(self.controller.serial, "port", "") or ""
        self._overview_connection_var.set(
            f"Connected · {port}" if connected and port else
            "Connected" if connected else "Disconnected")
        self._header_status_var.set("Connected" if connected else "Disconnected")
        if hasattr(self, "_header_status_label"):
            self._header_status_label.configure(text_color=ONLINE if connected else MUTED)
        self._fluent_highlight_nav()
        self._overview_firmware_var.set(firmware if connected else "Not connected")
        clock_name = self._clock_style_var.get()
        self._overview_clock_var.set(clock_name)
        self._overview_clock_caption.set(clock_name)
        self._refresh_clock_images()
        state = describe_device_update(APP_VERSION, firmware, connected)
        self._update_center_var.set(state.status)
        self._updates_device_status.set(
            f"ESP32-S3 · Connected\nFirmware {state.firmware_version}"
            if connected else "ESP32-S3 · Disconnected\nConnect to check firmware")
        if now - getattr(self, "_last_overview_snapshot", 0) >= 5.0:
            try:
                import psutil
                proc = psutil.Process()
                ram = proc.memory_info().rss / (1024 * 1024)
                self._overview_memory_var.set(f"{ram:.1f} MiB")
                self._updates_health.set(
                    f"App memory {ram:.1f} MiB\n{proc.num_threads()} active threads")
            except Exception:
                self._overview_memory_var.set("Not available")
                self._updates_health.set("App metrics unavailable")
            self._last_overview_snapshot = now
        if now - getattr(self, "_last_fluent_strip", 0) >= 3.0:
            try:
                obs = self.controller.obs_service
                obs_connected = bool(obs.is_connected)
                self._overview_obs.set(
                    "OBS: " + (("live" if obs.is_streaming else "connected")
                               if obs_connected else "disconnected"))
                obs_status = ("Streaming live" if obs.is_streaming else "Connected")
                if obs_connected and getattr(obs, "current_scene", ""):
                    obs_status += f" · {obs.current_scene}"
                self._audio_obs_status.set(
                    obs_status if obs_connected else "Connect OBS WebSocket to use these controls.")
                for button in self._obs_action_buttons:
                    button.configure(state="normal" if obs_connected else "disabled")
            except Exception:
                self._overview_obs.set("OBS: unavailable")
            try:
                snap = self.controller.media_service.cached_snapshot()
                title = str(snap.info.title or "")
                short_title = title[:21] + "…" if len(title) > 22 else title
                self._overview_media.set("Media: " + (short_title or "idle"))
                self._audio_media_status.set(title[:90] or "No media playing")
            except Exception:
                self._overview_media.set("Media: unavailable")
            active_profile = str(getattr(self.controller, "active_profile", None) or "Default")
            self._overview_profile.set("Profile: " + active_profile[:22])
            self._routing_enabled_var.set(bool(getattr(self.controller, "routing_enabled", False)))
            self._ducking_enabled_var.set(bool(getattr(self.controller, "ducking_enabled", False)))
            self._last_fluent_strip = now
        current = self._tabs.get()
        if current == "Audio" and self._audio_page != "Mixer":
            return
        if current not in ("Overview", "Audio") or now - self._last_audio_snapshot < 2.5:
            return
        if now - getattr(self, "_last_audio_interaction", 0) < 1.4:
            return
        try:
            target_host = (self._overview_audio_host if current == "Overview"
                           else self._audio_detail_host)
            # These lists are cached by AudioService. Include later pages in
            # the signature so their changing volumes cannot leave stale UI.
            snapshot = []
            for mode in (DisplayMode.MODE_OUTPUT, DisplayMode.MODE_INPUT,
                         DisplayMode.MODE_APPLICATION, DisplayMode.MODE_GAME):
                snapshot.extend(
                    (int(mode), getattr(item, "_device_id", ""),
                     getattr(item, "_session_identifier", ""),
                     item.name, item.volume, item.is_muted, item.is_default)
                    for item in self.controller.audio.get_sessions_for_mode(mode))
            signature = (
                current,
                self._audio_source_var.get() if current == "Audio" else "",
                self._audio_page_index if current == "Audio" else 0,
                tuple(snapshot),
            )
            if signature != self._audio_render_signature:
                self._render_fluent_audio(target_host, 1 if current == "Overview" else 0)
                self._audio_render_signature = signature
            self._last_audio_snapshot = now
        except Exception:
            log.debug("Could not render Windows Audio preview", exc_info=True)
