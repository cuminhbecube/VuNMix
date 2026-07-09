"""Small app icon generation for the VuNMix device.

The device protocol uses 16x16 RGB565 bitmaps.  Windows icon extraction can fail
for elevated, UWP, or protected system processes, so the public function first
tries the executable icon and then falls back to a deterministic letter badge.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError:  # Keep protocol/tests usable before dependencies are installed.
    Image = ImageDraw = ImageFont = None


ICON_SIZE = 16
EXTRACT_SIZE = 32


def _color_for_name(name: str) -> tuple[int, int, int]:
    digest = hashlib.sha1(name.lower().encode("utf-8", errors="replace")).digest()
    # Keep colors bright enough on the dark TFT background.
    return (
        80 + digest[0] % 150,
        80 + digest[1] % 150,
        80 + digest[2] % 150,
    )


def _fallback_icon(name: str) -> Image.Image:
    image = Image.new("RGB", (ICON_SIZE, ICON_SIZE), _color_for_name(name))
    draw = ImageDraw.Draw(image)
    letter = (name.strip()[:1] or "?").upper()
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((ICON_SIZE - tw) // 2, (ICON_SIZE - th) // 2 - 1),
        letter,
        fill=(255, 255, 255),
        font=font,
    )
    return image


def _extract_windows_icon(process_path: Optional[str]) -> Optional["Image.Image"]:
    if not process_path or Image is None or not os.path.exists(process_path):
        return None

    try:
        import win32con
        import win32gui
        import win32ui
    except Exception:
        return None

    screen_dc_handle = 0
    hicon = None
    bitmap = None
    mem_dc = None
    dc = None
    try:
        large_icons, small_icons = win32gui.ExtractIconEx(process_path, 0)
        icons = small_icons or large_icons
        if not icons:
            return None
        hicon = icons[0]

        screen_dc_handle = win32gui.GetDC(0)
        dc = win32ui.CreateDCFromHandle(screen_dc_handle)
        mem_dc = dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(dc, EXTRACT_SIZE, EXTRACT_SIZE)
        mem_dc.SelectObject(bitmap)
        mem_dc.FillSolidRect((0, 0, EXTRACT_SIZE, EXTRACT_SIZE), 0x000000)

        win32gui.DrawIconEx(
            mem_dc.GetSafeHdc(),
            0,
            0,
            hicon,
            EXTRACT_SIZE,
            EXTRACT_SIZE,
            0,
            None,
            win32con.DI_NORMAL,
        )

        bmp_info = bitmap.GetInfo()
        bmp_bytes = bitmap.GetBitmapBits(True)
        image = Image.frombuffer(
            "RGB",
            (bmp_info["bmWidth"], bmp_info["bmHeight"]),
            bmp_bytes,
            "raw",
            "BGRX",
            0,
            1,
        )
        return image.copy()
    except Exception:
        return None
    finally:
        try:
            if bitmap is not None:
                win32gui.DeleteObject(bitmap.GetHandle())
        except Exception:
            pass
        try:
            if mem_dc is not None:
                mem_dc.DeleteDC()
        except Exception:
            pass
        try:
            if dc is not None:
                dc.DeleteDC()
        except Exception:
            pass
        try:
            if screen_dc_handle:
                win32gui.ReleaseDC(0, screen_dc_handle)
        except Exception:
            pass
        try:
            if hicon:
                win32gui.DestroyIcon(hicon)
        except Exception:
            pass


def _fallback_rgb565_without_pillow(name: str) -> bytes:
    bg = _color_for_name(name)
    # Tiny deterministic "badge": border + simple diagonal mark. It is less
    # pretty than the Pillow path but preserves icon transport without deps.
    output = bytearray()
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            if x in (0, ICON_SIZE - 1) or y in (0, ICON_SIZE - 1):
                r, g, b = (255, 255, 255)
            elif x == y or x == ICON_SIZE - 1 - y:
                r, g, b = (30, 30, 30)
            else:
                r, g, b = bg
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            output.append(rgb565 & 0xFF)
            output.append((rgb565 >> 8) & 0xFF)
    return bytes(output)


def _to_rgb565_le(image: Image.Image) -> bytes:
    image = image.convert("RGB").resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    output = bytearray()
    for r, g, b in image.getdata():
        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        output.append(rgb565 & 0xFF)
        output.append((rgb565 >> 8) & 0xFF)
    return bytes(output)


@lru_cache(maxsize=128)
def app_icon_rgb565(name: str, process_path: Optional[str] = None) -> bytes:
    if Image is None:
        return _fallback_rgb565_without_pillow(name)
    image = _extract_windows_icon(process_path)
    if image is None:
        image = _fallback_icon(name)
    return _to_rgb565_le(image)
