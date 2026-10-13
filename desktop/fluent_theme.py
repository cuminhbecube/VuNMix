"""Shared Fluent Compact Dark design tokens and layout calculations.

Pure module: importable without tkinter, hardware or a Windows GUI.
"""
from __future__ import annotations

from dataclasses import dataclass

BG = "#0B1220"
SURFACE = "#101B29"
CARD = "#17283B"
CARD_HOVER = "#20344A"
ACCENT = "#298FDF"
ACCENT_HOVER = "#167CC8"
TEXT = "#EAF2FA"
MUTED = "#96ABC1"
ONLINE = "#21C58B"
DANGER = "#E66D77"
BORDER = "#2B4059"

SECTIONS = ("Overview", "Audio", "Clock", "Device", "Updates", "Settings")
NAV_ICONS = ("⌂", "◖", "◷", "▣", "↻", "⚙")

DEFAULT_SIZE = (1120, 740)
COMPACT_SIZE = (960, 650)
MINIMUM_SIZE = (780, 560)
SIDEBAR_WIDTH = 156
SIDEBAR_COLLAPSED_WIDTH = 52


@dataclass(frozen=True)
class WindowGeometry:
    width: int
    height: int
    x: int
    y: int
    compact: bool


def calculate_geometry(screen_width: int, screen_height: int) -> WindowGeometry:
    """Clamp initial geometry to usable work area, without negative coordinates."""
    screen_width = max(1, int(screen_width))
    screen_height = max(1, int(screen_height))
    available_width = max(1, screen_width - 40)
    available_height = max(1, screen_height - 100)
    compact = available_width < DEFAULT_SIZE[0] or available_height < DEFAULT_SIZE[1]
    desired = COMPACT_SIZE if compact else DEFAULT_SIZE
    width = min(desired[0], available_width)
    height = min(desired[1], available_height)
    return WindowGeometry(width, height, max(0, (screen_width - width) // 2),
                          max(0, (screen_height - height) // 2), compact)


def audio_percentage(value: float | int) -> int:
    return max(0, min(100, round(float(value))))
