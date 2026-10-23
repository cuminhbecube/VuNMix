"""Windows dark design tokens and layout calculations.

Pure module: importable without tkinter, hardware or a Windows GUI.
"""
from __future__ import annotations

from dataclasses import dataclass

BG = "#202020"
SURFACE = "#272727"
CARD = "#2D2D2D"
CARD_HOVER = "#383838"
INPUT = "#343434"
SUBTLE = "#242424"
BORDER = "#414141"
ACCENT = "#60CDFF"
ACCENT_HOVER = "#7AD6FF"
ACCENT_TEXT = "#10202A"
TEXT = "#F4F4F4"
MUTED = "#B8B8B8"
DISABLED = "#777777"
ONLINE = "#92C78A"
DANGER = "#F1A3A6"
FONT_FAMILY = "Segoe UI"
CONTROL_HEIGHT = 34
CONTENT_PAD = 16

SECTIONS = ("Overview", "Audio", "Clock", "Device", "Updates", "Settings")
# Text fallbacks only; the sidebar draws its own consistent line icons.
NAV_ICONS = ("OV", "AU", "CL", "DV", "UP", "ST")

# Single-viewport control center: fit normal laptop screens without zoom.
DEFAULT_SIZE = (1040, 680)
COMPACT_SIZE = (960, 640)
MINIMUM_SIZE = (780, 560)
SIDEBAR_WIDTH = 176
SIDEBAR_COLLAPSED_WIDTH = 56


def apply_windows_theme(ctk):
    """Apply the palette to every CTk control before creating any widgets.

    Accept the toolkit as an argument so geometry/token tests stay independent
    of Tk, a display server and native Windows services. Button fills are
    deliberately neutral; callers opt into accent for the primary action.
    """
    ctk.set_appearance_mode("dark")
    palette = {
        "CTk": {"fg_color": BG},
        "CTkToplevel": {"fg_color": BG},
        "CTkFrame": {"fg_color": CARD, "top_fg_color": SURFACE,
                     "border_color": BORDER, "border_width": 0,
                     "corner_radius": 6},
        "CTkButton": {"fg_color": INPUT, "hover_color": CARD_HOVER,
                      "border_color": BORDER, "border_width": 1,
                      "corner_radius": 5, "text_color": TEXT,
                      "text_color_disabled": DISABLED},
        "CTkLabel": {"text_color": TEXT},
        "CTkEntry": {"fg_color": INPUT, "border_color": BORDER,
                     "border_width": 1, "corner_radius": 5,
                     "text_color": TEXT, "placeholder_text_color": MUTED},
        "CTkCheckBox": {"fg_color": ACCENT, "border_color": MUTED,
                        "hover_color": ACCENT_HOVER, "checkmark_color": ACCENT_TEXT,
                        "text_color": TEXT, "text_color_disabled": DISABLED},
        "CTkSwitch": {"fg_color": BORDER, "progress_color": ACCENT,
                      "button_color": TEXT, "button_hover_color": "#FFFFFF",
                      "text_color": TEXT, "text_color_disabled": DISABLED},
        "CTkRadioButton": {"fg_color": ACCENT, "border_color": MUTED,
                           "hover_color": ACCENT_HOVER, "text_color": TEXT,
                           "text_color_disabled": DISABLED},
        "CTkProgressBar": {"fg_color": BORDER, "border_color": BORDER,
                           "progress_color": ACCENT},
        "CTkSlider": {"fg_color": BORDER, "progress_color": ACCENT,
                      "button_color": ACCENT, "button_hover_color": ACCENT_HOVER},
        "CTkOptionMenu": {"fg_color": INPUT, "button_color": INPUT,
                          "button_hover_color": CARD_HOVER, "corner_radius": 5,
                          "text_color": TEXT, "text_color_disabled": DISABLED},
        "CTkComboBox": {"fg_color": INPUT, "border_color": BORDER,
                        "button_color": INPUT, "button_hover_color": CARD_HOVER,
                        "border_width": 1, "corner_radius": 5,
                        "text_color": TEXT, "text_color_disabled": DISABLED},
        "CTkScrollbar": {"button_color": BORDER,
                         "button_hover_color": DISABLED},
        "CTkSegmentedButton": {"fg_color": SUBTLE, "selected_color": INPUT,
                               "selected_hover_color": CARD_HOVER,
                               "unselected_color": SUBTLE,
                               "unselected_hover_color": CARD,
                               "text_color": TEXT, "text_color_disabled": DISABLED,
                               "corner_radius": 5, "border_width": 3},
        "CTkTextbox": {"fg_color": INPUT, "border_color": BORDER,
                       "text_color": TEXT, "scrollbar_button_color": BORDER,
                       "scrollbar_button_hover_color": DISABLED},
        "CTkScrollableFrame": {"label_fg_color": SURFACE},
        "DropdownMenu": {"fg_color": CARD, "hover_color": CARD_HOVER,
                         "text_color": TEXT},
        "CTkFont": {"family": FONT_FAMILY, "size": 13, "weight": "normal"},
    }
    for widget, values in palette.items():
        ctk.ThemeManager.theme.setdefault(widget, {}).update(values)


@dataclass(frozen=True)
class WindowGeometry:
    width: int
    height: int
    x: int
    y: int
    compact: bool


def calculate_geometry(screen_width: int, screen_height: int, scale: float = 1.0) -> WindowGeometry:
    """Return logical CTk dimensions and centered physical screen coordinates.

    Screen dimensions and the 40px horizontal / 100px vertical work-area
    margins are physical pixels. CTk scales only the geometry string's width
    and height, leaving its x/y offsets unchanged, so those units must remain
    separate when Windows display scaling is above 100 percent.
    """
    import math

    scale = float(scale)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Window scale must be finite and greater than zero")
    screen_width = max(1, int(screen_width))
    screen_height = max(1, int(screen_height))
    available_width = max(1, int(max(1, screen_width - 40) / scale))
    available_height = max(1, int(max(1, screen_height - 100) / scale))
    compact = available_width < DEFAULT_SIZE[0] or available_height < DEFAULT_SIZE[1]
    desired = COMPACT_SIZE if compact else DEFAULT_SIZE
    width = min(desired[0], available_width)
    height = min(desired[1], available_height)
    # Match CTkScalingBaseClass._apply_geometry_scaling's rounding exactly.
    physical_width, physical_height = round(width * scale), round(height * scale)
    return WindowGeometry(width, height, max(0, (screen_width - physical_width) // 2),
                          max(0, (screen_height - physical_height) // 2), compact)


def audio_percentage(value: float | int) -> int:
    return max(0, min(100, round(float(value))))
