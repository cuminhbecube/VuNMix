"""Device appearance controls. All methods run on the existing Tk UI thread."""
import tkinter as tk
import customtkinter as ctk

from device_theme import ThemeSyncSnapshot
from device_theme_preview import load_theme_preview
from fluent_theme import ACCENT, CARD, INPUT, MUTED, TEXT
from protocol import DeviceTheme, DEVICE_THEME_NAMES


class DeviceThemeViewsMixin:
    def _build_device_views(self, parent):
        self._fluent_header(parent, "Device")
        self._device_page_var = tk.StringVar(value="Appearance")
        self._device_switcher = ctk.CTkSegmentedButton(
            parent, values=["Appearance", "Lighting & standby"],
            variable=self._device_page_var, command=self._show_device_page,
            height=32, font=ctk.CTkFont(size=13),
        )
        self._device_switcher.pack(fill="x", padx=16, pady=(0, 10))
        self._device_pages_host = ctk.CTkFrame(parent, fg_color="transparent")
        self._device_pages_host.pack(fill="both", expand=True)
        self._device_appearance_page = ctk.CTkFrame(self._device_pages_host, fg_color="transparent")
        self._device_lighting_page = ctk.CTkFrame(self._device_pages_host, fg_color="transparent")
        self._build_device_theme_selector(self._device_appearance_page)
        self._show_device_page("Appearance")
        return self._device_lighting_page

    def _show_device_page(self, name):
        for key, page in (("Appearance", self._device_appearance_page),
                          ("Lighting & standby", self._device_lighting_page)):
            if name == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()

    def _build_device_theme_selector(self, parent):
        desired = getattr(self.config, "device_theme_id", None)
        # Empty preserves an unset preference; the visible choice can follow
        # the queried device without turning that observation into user intent.
        self._device_theme_var = tk.StringVar(value="" if desired is None else str(desired))
        self._device_theme_choice_var = tk.StringVar(value=str(desired or 0))
        self._device_theme_name_var = tk.StringVar(value=DEVICE_THEME_NAMES[desired or 0])
        self._device_theme_summary_var = tk.StringVar()
        self._device_theme_status_var = tk.StringVar()
        self._device_theme_image_key = None
        self._device_theme_preview_size = (320, 240)

        status = ctk.CTkFrame(parent, fg_color="transparent")
        status.pack(side="bottom", fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(status, textvariable=self._device_theme_summary_var, anchor="w",
                     height=20, font=ctk.CTkFont(size=12), text_color=TEXT).pack(fill="x")
        detail = ctk.CTkFrame(status, fg_color="transparent")
        detail.pack(fill="x")
        self._device_theme_retry_button = ctk.CTkButton(
            detail, text="Retry", width=66, height=32,
            command=self._retry_device_theme,
        )
        self._device_theme_retry_button.pack(side="right", padx=(10, 0))
        self._device_theme_status_label = ctk.CTkLabel(
            detail, textvariable=self._device_theme_status_var, anchor="w", justify="left",
            height=32, wraplength=390, font=ctk.CTkFont(size=12), text_color=MUTED,
        )
        self._device_theme_status_label.pack(side="left", fill="x", expand=True)
        self._device_theme_status_width = None
        def resize_status(_event):
            # CTkLabel.bind targets the text child, whose requested width can
            # shrink after wrapping. Measure the stable containing row instead.
            scale = ctk.ScalingTracker.get_widget_scaling(detail)
            width = max(160, int(detail.winfo_width() / scale) - 80)
            if width != self._device_theme_status_width:
                self._device_theme_status_width = width
                self._device_theme_status_label.configure(wraplength=width)
        detail.bind("<Configure>", resize_status)

        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16)
        self._device_theme_content = content
        content.grid_columnconfigure(1, weight=1)
        preview = ctk.CTkFrame(content, fg_color="transparent")
        preview.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        self._device_theme_image_label = ctk.CTkLabel(preview, text="", width=320, height=240)
        self._device_theme_image_label.pack()
        self._device_theme_preview_caption = ctk.CTkLabel(
            preview, text="320×240 sample · Preview only", height=20, width=320,
            text_color=MUTED, font=ctk.CTkFont(size=12),
        )
        self._device_theme_preview_caption.pack(fill="x")
        choices = ctk.CTkFrame(content, fg_color="transparent")
        choices.grid(row=0, column=1, sticky="new")
        self._device_theme_radio_list = choices
        self._device_theme_buttons = {}
        for index, name in enumerate(DEVICE_THEME_NAMES):
            button = ctk.CTkRadioButton(
                choices, text=name, value=str(index), variable=self._device_theme_choice_var,
                command=lambda i=index: self._choose_device_theme(i),
                width=148, height=32, radiobutton_width=18, radiobutton_height=18,
                border_width_unchecked=2, border_width_checked=5,
                fg_color=ACCENT, text_color=TEXT, font=ctk.CTkFont(size=13),
            )
            button.pack(fill="x")
            self._device_theme_buttons[index] = button
        self._device_theme_compact = ctk.CTkFrame(content, fg_color="transparent")
        ctk.CTkLabel(self._device_theme_compact, text="Device theme", anchor="w", height=24,
                     font=ctk.CTkFont(size=13)).pack(fill="x")
        self._device_theme_menu = ctk.CTkOptionMenu(
            self._device_theme_compact, values=list(DEVICE_THEME_NAMES),
            variable=self._device_theme_name_var, width=148, height=32,
            command=lambda name: self._choose_device_theme(DEVICE_THEME_NAMES.index(name)),
        )
        self._device_theme_menu.pack(fill="x")
        ctk.CTkLabel(self._device_theme_compact, text="All 16 clocks\nstay unchanged.",
                     anchor="w", justify="left", height=44, font=ctk.CTkFont(size=12),
                     text_color=MUTED).pack(fill="x", pady=(8, 0))
        content.bind("<Configure>", self._resize_device_theme_preview)
        self._refresh_device_theme()

    def _resize_device_theme_preview(self, _event=None):
        # CTkFrame binds Configure on its internal canvas; measure the public
        # container rather than filtering event.widget against the frame.
        content = self._device_theme_content
        scale = ctk.ScalingTracker.get_widget_scaling(content)
        width, height = int(content.winfo_width() / scale), int(content.winfo_height() / scale)
        if width <= 1 or height <= 1:
            return
        compact = height < 260 or width < 492
        if compact:
            self._device_theme_radio_list.grid_remove()
            self._device_theme_compact.grid(row=0, column=1, sticky="new")
        else:
            self._device_theme_compact.grid_remove()
            self._device_theme_radio_list.grid(row=0, column=1, sticky="new")
        available = min(320, width - 164, (height - 20) * 4 // 3)
        image_width = max(80, available // 4 * 4)
        size = (image_width, image_width * 3 // 4)
        if size != self._device_theme_preview_size:
            self._device_theme_preview_size = size
            self._device_theme_image_label.configure(width=size[0], height=size[1])
            self._device_theme_preview_caption.configure(
                width=size[0], text="320×240 sample · Preview only" if size == (320, 240)
                else "Sample preview · scaled",
            )
            self._refresh_device_theme()

    def _choose_device_theme(self, theme_id):
        theme_id = int(DeviceTheme(theme_id))
        self._device_theme_var.set(str(theme_id))
        self._device_theme_choice_var.set(str(theme_id))
        self._refresh_device_theme()

    def _retry_device_theme(self):
        coordinator = getattr(self.controller, "theme_sync", None)
        if coordinator is not None:
            coordinator.retry()
        self._refresh_device_theme()

    def _refresh_device_theme(self):
        if not hasattr(self, "_device_theme_var"):
            return
        coordinator = getattr(self.controller, "theme_sync", None)
        state = coordinator.snapshot() if coordinator is not None else None
        if not isinstance(state, ThemeSyncSnapshot):
            state = None
        confirmed = state.confirmed_id if state else None
        draft = self._device_theme_var.get()
        shown = int(draft) if draft else confirmed if confirmed is not None else 0
        self._device_theme_choice_var.set(str(shown))
        self._device_theme_name_var.set(DEVICE_THEME_NAMES[shown])
        key = (shown, self._device_theme_preview_size)
        if key != self._device_theme_image_key:
            raster = load_theme_preview(shown)
            self._device_theme_image = ctk.CTkImage(
                light_image=raster, dark_image=raster, size=self._device_theme_preview_size,
            )
            self._device_theme_image_label.configure(image=self._device_theme_image)
            self._device_theme_image_key = key
        desired = getattr(self.config, "device_theme_id", None)
        saved = DEVICE_THEME_NAMES[desired] if desired is not None else "Follow device"
        device = DEVICE_THEME_NAMES[confirmed] if confirmed is not None else "Not verified"
        self._device_theme_summary_var.set(f"Saved on PC: {saved}   ·   Device: {device}")
        self._device_theme_status_var.set(state.message if state else "Connect VuNMix to verify its display theme.")
        refresh = state is not None and state.phase in ("applied", "deferred")
        retry = state is not None and state.connected and (refresh or state.phase in ("error", "timeout", "unsupported"))
        self._device_theme_retry_button.configure(state="normal" if retry else "disabled",
                                                 text="Refresh" if refresh else "Retry")
