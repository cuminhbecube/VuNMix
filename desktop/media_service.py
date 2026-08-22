"""
VuNMix Media Service — Windows Media / Spotify integration & Playback control.

Extracts current track title & artist and executes hardware media commands.
"""

import ctypes
from ctypes import wintypes
import logging
import re
import threading
import time
from typing import Optional, Tuple

import win32gui
import win32process

from protocol import MediaInfoData, MediaControlData

log = logging.getLogger(__name__)

# Windows Virtual-Key codes for media keys
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP       = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


class MediaService:
    """Manages playback metadata reading and media key dispatch."""

    def __init__(self):
        self._last_title = ""
        self._last_artist = ""
        self._is_playing = 0
        self._last_media_info: Optional[MediaInfoData] = None

    def execute_control(self, action: int) -> bool:
        """
        Execute media playback command:
        1 = Play / Pause
        2 = Next Track
        3 = Previous Track
        4 = Stop
        """
        key_map = {
            1: VK_MEDIA_PLAY_PAUSE,
            2: VK_MEDIA_NEXT_TRACK,
            3: VK_MEDIA_PREV_TRACK,
            4: VK_MEDIA_STOP,
        }
        vk = key_map.get(action)
        if not vk:
            return False

        try:
            user32 = ctypes.windll.user32
            # Key down
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.01)
            # Key up (KEYEVENTF_KEYUP = 0x0002)
            user32.keybd_event(vk, 0, 0x0002, 0)
            log.info("Media control action %d dispatched (VK=0x%02X)", action, vk)
            return True
        except Exception as e:
            log.error("Failed to dispatch media key: %s", e)
            return False

    def get_current_media_info(self) -> MediaInfoData:
        """Scan active media player windows to extract current track and artist."""
        title = ""
        artist = ""
        is_playing = 0

        # Enumerate top-level windows looking for known media players (Spotify, etc.)
        def enum_window_callback(hwnd, extra):
            nonlocal title, artist, is_playing
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                window_text = win32gui.GetWindowText(hwnd)
                if not window_text:
                    return True

                # Spotify window title format: "Artist - Track Title" when playing,
                # or "Spotify" / "Spotify Premium" / "Spotify Free" when paused.
                class_name = win32gui.GetClassName(hwnd)
                if "Chrome_WidgetWin_0" in class_name or "Spotify" in window_text:
                    if " - " in window_text and not window_text.startswith("Spotify"):
                        parts = window_text.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                        is_playing = 1
                        return False  # Stop enumeration once found

                # VLC window title format: "filename/track - VLC media player"
                if "VLC media player" in window_text:
                    cleaned = window_text.replace(" - VLC media player", "").strip()
                    if cleaned and cleaned != "VLC media player":
                        if " - " in cleaned:
                            parts = cleaned.split(" - ", 1)
                            artist = parts[0].strip()
                            title = parts[1].strip()
                        else:
                            title = cleaned
                            artist = "VLC"
                        is_playing = 1
                        return False

                return True
            except Exception:
                return True

        try:
            win32gui.EnumWindows(enum_window_callback, None)
        except Exception:
            pass

        return MediaInfoData(
            is_playing=is_playing,
            position_sec=0,
            duration_sec=0,
            title=title[:31],
            artist=artist[:23],
        )
