"""Faithful, deterministic previews of the sixteen ESP32 clock styles.

Geometry, palette, labels and time rules mirror src/ui/modules/DisplayClock*.inc
at the device's native 320 x 240 resolution. The bundled masks are the actual
LVGL Montserrat and one-bit DSEG glyphs, including advances and kerning. No OS
font substitution, Tk objects, network access or device connection is involved.

This is a desktop rasterizer, not a screenshot from a connected device: Pillow
and LVGL can differ slightly at curved/diagonal edges, and the physical RGB565
panel quantizes the source colors. Layouts are never redesigned for thumbnails.
"""

from __future__ import annotations

from datetime import datetime, time
from functools import lru_cache
import math
import operator

from PIL import Image, ImageChops, ImageDraw

from clock_font_data import load_clock_fonts
from protocol import ClockStyle


CLOCK_PREVIEW_SIZE = (320, 240)
CLOCK_PREVIEW_SAMPLE_TIME = time(10, 24, 36)
_AA = 4
_BACKGROUNDS = (
    0x000000, 0x141218, 0x0B0B0D, 0x090B10, 0x080D19, 0x0A1015,
    0x030A05, 0x17211C, 0x100C08, 0x10171D, 0x090E29, 0x060806,
    0x111820, 0x090F14, 0x080F19, 0x101018,
)
_ART_TITLES = ("NIXIE", "WORD CLOCK", "PIXEL ART", "DOT MATRIX",
               "CLOCKCLOCK", "BARCODE", "POLYGON", "MATH CLOCK")
_DIGITS = (
    (14, 17, 19, 21, 25, 17, 14), (4, 12, 4, 4, 4, 4, 14),
    (14, 17, 1, 2, 4, 8, 31), (30, 1, 1, 14, 1, 1, 30),
    (2, 6, 10, 18, 31, 2, 2), (31, 16, 16, 30, 1, 1, 30),
    (14, 16, 16, 30, 17, 17, 14), (31, 1, 2, 4, 8, 8, 8),
    (14, 17, 17, 14, 17, 17, 14), (14, 17, 17, 15, 1, 1, 14),
)
_HAND_DIGITS = (
    (7, 17, 2, 2, 1, 3), (24, 2, 24, 2, 24, 2), (6, 17, 11, 3, 1, 18),
    (6, 17, 6, 17, 6, 3), (2, 2, 1, 17, 24, 2), (7, 18, 1, 17, 6, 3),
    (7, 18, 7, 17, 1, 3), (6, 17, 24, 2, 24, 2), (7, 17, 1, 3, 1, 3),
    (7, 17, 1, 17, 6, 3),
)
_WORDS = (
    "IT IS", "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
    "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN",
    "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN", "TWENTY",
    "THIRTY", "FORTY", "FIFTY", "HOURS", "MINUTES",
)


def _rgb(color: int) -> tuple[int, int, int]:
    return (color >> 16 & 255, color >> 8 & 255, color & 255)


@lru_cache(maxsize=600)
def _glyph_mask(font_name: str, code: int) -> Image.Image:
    font = load_clock_fonts()[font_name]
    offset, _, width, height, _, _ = font["glyphs"][code]
    bpp = font["bpp"]
    bitmap = font["bitmap"]
    maximum = (1 << bpp) - 1
    pixels = bytearray(width * height)
    for pixel in range(len(pixels)):
        bit = pixel * bpp
        value = (bitmap[offset + bit // 8] >> (8 - bpp - bit % 8)) & maximum
        pixels[pixel] = value * 255 // maximum
    return Image.frombytes("L", (width, height), bytes(pixels))


def _advance(font: dict, code: int, next_code: int) -> int:
    """LVGL rounds every advance after applying 1/16-pixel kerning."""
    advance = font["glyphs"][code][1]
    if "kern_values" in font and next_code in font["glyphs"]:
        left = font["kern_left"][code - 31]
        right = font["kern_right"][next_code - 31]
        if left and right:
            kern = font["kern_values"][(left - 1) * font["kern_right_count"] + right - 1]
            advance += (kern * font["kern_scale"]) >> 4
    return (advance + 8) >> 4


@lru_cache(maxsize=256)
def _text_mask(font_name: str, text: str, letter_space: int = 0) -> Image.Image:
    font = load_clock_fonts()[font_name]
    codes = [ord(char) for char in text]
    advances = [_advance(font, code, codes[i + 1] if i + 1 < len(codes) else 0)
                for i, code in enumerate(codes)]
    width = sum(advances) + max(0, len(codes) - 1) * letter_space
    mask = Image.new("L", (max(1, width), font["line_height"]))
    x = 0
    for code, advance in zip(codes, advances):
        _, _, box_w, box_h, ofs_x, ofs_y = font["glyphs"][code]
        if box_w and box_h:
            gx = x + ofs_x
            gy = font["line_height"] - font["base_line"] - box_h - ofs_y
            glyph = _glyph_mask(font_name, code)
            box = (gx, gy, gx + box_w, gy + box_h)
            mask.paste(ImageChops.lighter(mask.crop(box), glyph), (gx, gy))
        x += advance + letter_space
    return mask


class _Canvas:
    """Shapes are supersampled; the device glyph masks keep native pixels."""

    def __init__(self, background: int, size: tuple[int, int] = CLOCK_PREVIEW_SIZE):
        self.image = Image.new("RGB", (size[0] * _AA, size[1] * _AA), _rgb(background))
        self.draw = ImageDraw.Draw(self.image)

    def rect(self, x, y, width, height, color, radius=0, border=0, border_color=0):
        box = (x * _AA, y * _AA, (x + width) * _AA - 1, (y + height) * _AA - 1)
        if radius:
            self.draw.rounded_rectangle(box, radius=radius * _AA, fill=_rgb(color),
                                        outline=_rgb(border_color) if border else None,
                                        width=border * _AA)
        else:
            self.draw.rectangle(box, fill=_rgb(color),
                                outline=_rgb(border_color) if border else None,
                                width=border * _AA)

    def line(self, x1, y1, x2, y2, color, width=2):
        self.draw.line(((x1 * _AA + _AA // 2, y1 * _AA + _AA // 2),
                        (x2 * _AA + _AA // 2, y2 * _AA + _AA // 2)),
                       fill=_rgb(color), width=width * _AA)

    def arc(self, cx, cy, radius, width, start, end, color, rounded=False):
        if start == end:
            return
        self.draw.arc(((cx - radius) * _AA, (cy - radius) * _AA,
                       (cx + radius) * _AA - 1, (cy + radius) * _AA - 1),
                      start=start, end=end, fill=_rgb(color), width=width * _AA)
        if rounded and end - start < 360:
            for angle in (start, end):
                angle = math.radians(angle)
                x = cx + math.cos(angle) * (radius - width / 2)
                y = cy + math.sin(angle) * (radius - width / 2)
                self.draw.ellipse(((x - width / 2) * _AA, (y - width / 2) * _AA,
                                   (x + width / 2) * _AA - 1, (y + width / 2) * _AA - 1),
                                  fill=_rgb(color))

    def text(self, text, font, color, x, y, *, horizontal="center", vertical="top", letter_space=0):
        mask = _text_mask(str(font), text, letter_space)
        width, height = mask.size
        if horizontal == "center":
            x -= width // 2
        elif horizontal == "right":
            x -= width
        if vertical == "center":
            y -= height // 2
        elif vertical == "bottom":
            y -= height
        self.image.paste(_rgb(color), (x * _AA, y * _AA),
                         mask.resize((width * _AA, height * _AA), Image.Resampling.NEAREST))

    def art_text(self, x, y, width, text, font, color):
        # lv_draw_label centers inside a fixed-width area, unlike lv_obj_align.
        mask_width = _text_mask(str(font), text).width
        self.text(text, font, color, x + (width - mask_width) // 2, y, horizontal="left")

    def finish(self):
        return self.image.resize((self.image.width // _AA, self.image.height // _AA), Image.Resampling.BOX)


def _draw_digital(canvas, style, hour, minute, second):
    time_hm = f"{hour:02d}:{minute:02d}"
    if style == ClockStyle.NEON_DIGITAL:
        canvas.text(f"{hour:02d}", "dseg90", 0x06B6D4, 75, 118, vertical="center")
        if second % 2 == 0:
            canvas.text(":", "dseg90", 0x06B6D4, 160, 113, vertical="center")
        canvas.text(f"{minute:02d}", "dseg90", 0x06B6D4, 245, 118, vertical="center")
        canvas.text("VuNMix Studio", 12, 0xCBC4D2, 160, 232, vertical="bottom")
    elif style == ClockStyle.MINIMAL:
        canvas.text(time_hm, "dseg90", 0xF5F7FA, 160, 104, vertical="center", letter_space=2)
        canvas.text(f"SECONDS  {second:02d}", 16, 0x8C939D, 160, 178, vertical="center")
        canvas.text("VUNMIX  /  CLOCK", 10, 0x06B6D4, 160, 16, letter_space=2)
    else:
        for x, value in ((8, hour), (164, minute)):
            canvas.rect(x, 53, 148, 126, 0x1B1B1E, 12, 1, 0x303035)
            canvas.text(f"{value:02d}", "dseg90", 0xF4F4F4, x + 74, 116, vertical="center")
            canvas.rect(x + 3, 115, 142, 2, 0x08080A)
        canvas.text(":", 36, 0x73737A, 160, 115, vertical="center")
        canvas.text(f"SECONDS  {second:02d}", 12, 0x8B8B92, 160, 228, vertical="bottom")
        canvas.text("FLIP CLOCK", 10, 0x696970, 160, 12, letter_space=2)


def _draw_analog(canvas, hour, minute, second):
    canvas.rect(68, 24, 184, 184, 0x11141A, 92, 1, 0x2D333B)
    # LVGL meter content excludes 16px padding and a 1px border: radius 75.
    # The firmware uses 60 ticks over a full range including both endpoints.
    for tick in range(60):
        angle = math.radians((tick * 3600 // 59) / 10 + 270)
        major = tick % 5 == 0
        inner = 64 if major else 68
        if major:
            canvas.text(str(tick * 60 // 59), 14, 0xFAFAFA,
                        160 + int(56 * math.cos(angle)), 116 + int(56 * math.sin(angle)),
                        vertical="center")
        canvas.line(160 + inner * math.cos(angle), 116 + inner * math.sin(angle),
                    160 + 75 * math.cos(angle), 116 + 75 * math.sin(angle),
                    0xD8DEE9 if major else 0x59616C, 3 if major else 2)
    for value, length, color, width in (
        ((hour % 12) * 5 + minute // 12, 33, 0xF5F7FA, 6),
        (minute, 47, 0x06B6D4, 4), (second, 55, 0xFF5B67, 2),
    ):
        angle = math.radians(value * 6 + 270)
        canvas.line(160, 116, 160 + int(length * math.cos(angle)),
                    116 + int(length * math.sin(angle)), color, width)
    # LVGL's default dark meter theme supplies this center cap.
    canvas.rect(153, 109, 15, 15, 0xFAFAFA, 8)
    canvas.text("VUNMIX  ANALOG", 10, 0x7D8590, 160, 233, vertical="bottom", letter_space=2)


def _draw_extra(canvas, style, hour, minute, second):
    hm = f"{hour:02d}:{minute:02d}"
    if style == ClockStyle.ORBIT:
        canvas.arc(160, 120, 94, 7, -90, 270, 0x202B43)
        canvas.arc(160, 120, 94, 7, -90, second * 6 - 90, 0x78B9FF, rounded=True)
        canvas.text(hm, 36, 0xEEF5FF, 160, 112, vertical="center")
        canvas.text(f"{second:02d}", 16, 0x78B9FF, 160, 152, vertical="center")
        canvas.text("ORBIT", 10, 0x6C819D, 160, 7)
        canvas.text("VUNMIX / 24H", 10, 0x6C819D, 160, 233, vertical="bottom")
    elif style == ClockStyle.BINARY:
        for col, (heading, value, color) in enumerate(zip(("HOUR", "MIN", "SEC"),
                (hour, minute, second), (0x70D6FF, 0xBD9AFF, 0x7DE6B5))):
            x = 82 + col * 78
            canvas.text(heading, 12, color, x, 27)
            for row in range(6):
                canvas.rect(x - 8, 57 + row * 22, 16, 16,
                            color if value & (1 << (5 - row)) else 0x18232D, 8, 1, color)
            canvas.text(f"{value:02d}", 20, color, x, 190)
        for row in range(6):
            canvas.text(str(1 << (5 - row)), 10, 0x536673, 20, 60 + row * 22, horizontal="left")
        canvas.text("BINARY / VUNMIX", 10, 0x536673, 160, 234, vertical="bottom")
    elif style == ClockStyle.TERMINAL:
        canvas.text("VUNMIX / TERMINAL", 12, 0x4A9964, 18, 20, horizontal="left")
        canvas.text("> clock --24h", 16, 0x88B696, 18, 60, horizontal="left")
        canvas.text(f"{hm}:{second:02d}", 36, 0x83FFA5, 18, 118, horizontal="left", vertical="center")
        canvas.text("> standby  " if second % 2 else "> standby _", 14, 0x4A9964,
                    18, 159, horizontal="left")
        canvas.text("LOCAL TIME / 24H", 10, 0x357048, 18, 223, horizontal="left", vertical="bottom")
    else:
        canvas.text("VUNMIX / RETRO LCD", 12, 0xB7C4AC, 160, 18)
        canvas.rect(16, 54, 288, 132, 0xB4C99A, 8, 3, 0x64775A)
        # Child alignment is relative to the LCD's content, inside its 3px border.
        canvas.text("24H", 10, 0x536246, 289, 66, horizontal="right")
        canvas.text(hm, 36, 0x263A25, 160, 114, vertical="center", letter_space=4)
        canvas.text(f"SEC {second:02d}", 14, 0x536246, 160, 168, vertical="bottom")
        canvas.text("QUARTZ / DIGITAL", 10, 0x879B81, 160, 222, vertical="bottom")


def _word_active(index, value):
    return index == value + 1 if value < 20 else (index == 19 + value // 10 or
                                                 (value % 10 != 0 and index == value % 10 + 1))


def _draw_art(canvas, style, hour, minute, second):
    digits = (hour // 10, hour % 10, minute // 10, minute % 10)
    if style == ClockStyle.NIXIE:
        for i, digit in enumerate(digits):
            x = i * 72 + 3
            canvas.rect(x, 8, 66, 122, 0x503321, 24)
            canvas.rect(x + 2, 10, 62, 118, 0x1E1712, 22)
            canvas.rect(x + 8, 22, 3, 80, 0x4C3527, 1)
            canvas.art_text(x + 5, 44, 56, "8", 36, 0x42241A)
            canvas.art_text(x + 5, 44, 56, str(digit), 36, 0xFF973B)
            canvas.rect(x + 2, 127, 62, 12, 0x72604B, 3)
    elif style == ClockStyle.WORD_CLOCK:
        for i, word in enumerate(_WORDS):
            hours, minutes = _word_active(i, hour), _word_active(i, minute)
            color = (0xEAF0F6 if i == 0 else 0x78CAFF if i == 25 else 0xF2BB71 if i == 26
                     else 0xFFFFFF if hours and minutes else 0x78CAFF if hours
                     else 0xF2BB71 if minutes else 0x293744)
            canvas.art_text((i % 3) * 96, (i // 3) * 17, 96, word, 12, color)
    elif style in (ClockStyle.PIXEL_ART, ClockStyle.DOT_MATRIX):
        rounded = style == ClockStyle.DOT_MATRIX
        for i, digit in enumerate(digits):
            left = 14 + i * 60 + (20 if i >= 2 else 0)
            for row in range(7):
                for col in range(5):
                    lit = _DIGITS[digit][row] & (1 << (4 - col))
                    color = (0xFFAF47 if rounded else 0x81D4FF) if lit else 0x182029
                    canvas.rect(left + col * 10, 32 + row * 10, 8, 8, color, 4 if rounded else 0)
        for y in (52, 82):
            canvas.rect(139, y, 8, 8, 0xE9B670, 4 if rounded else 0)
        if not rounded:
            for i in range(18):
                height = 10 + (i * 7) % 22
                canvas.rect(i * 16, 156 - height, 14, height, 0x223B68 if i % 2 else 0x172A4F)
                canvas.rect(i * 16 + 5, 156 - height + 4, 3, 3, 0xF3D68C)
    elif style == ClockStyle.CLOCKCLOCK:
        dx, dy = (0, 10, 0, -10, -7), (-10, 0, 10, 0, 7)
        for i, digit in enumerate(digits):
            for dial in range(6):
                x, y = 35 + i * 62 + dial % 2 * 28, 33 + dial // 2 * 42
                canvas.rect(x - 13, y - 13, 26, 26, 0x24313B, 13)
                canvas.rect(x - 11, y - 11, 22, 22, 0x101820, 11)
                pose = _HAND_DIGITS[digit][dial]
                for direction in (pose // 5, pose % 5):
                    canvas.line(x, y, x + dx[direction], y + dy[direction],
                                0x35414C if direction == 4 else 0xE3EAF2, 3)
    elif style == ClockStyle.BARCODE:
        digits += (second // 10, second % 10)
        for i in range(24):
            bit = (digits[i // 4] >> (3 - i % 4)) & 1
            canvas.rect(12 + i * 11, 8, 7 if bit else 3, 99, 0xDCECF3)
        canvas.art_text(0, 119, 288, f"{hour:02d}:{minute:02d}:{second:02d}", 20, 0x79CBD6)
    elif style == ClockStyle.POLYGON:
        xs = (144, 178, 204, 214, 204, 178, 144, 110, 84, 74, 84, 110)
        ys = (12, 20, 44, 78, 112, 136, 144, 136, 112, 78, 44, 20)
        dx, dy = (-7, 0, 7, 7, 0, -7), (-4, -8, -4, 4, 8, 4)
        for i, (x, y) in enumerate(zip(xs, ys)):
            active = i == hour % 12
            for side in range(6):
                next_side = (side + 1) % 6
                canvas.line(x + dx[side], y + dy[side], x + dx[next_side], y + dy[next_side],
                            0x71E8DC if active else 0x344656, 3 if active else 1)
        canvas.art_text(105, 59, 78, f"{minute:02d}", 36, 0xDFECFA)
        for i in range(6):
            px, color = 113 + i * 12, 0xB59EFF if i == minute // 10 else 0x344656
            canvas.line(px, 110, px + 4, 102, color)
            canvas.line(px + 4, 102, px + 8, 110, color)
            canvas.line(px + 8, 110, px, 110, color)
    elif style == ClockStyle.MATH_CLOCK:
        for i, (value, title) in enumerate(zip((hour, minute), ("HOURS", "MINUTES"))):
            canvas.art_text(0, i * 78, 288, title, 12, 0x7E85A6)
            formula = f"{value // 2} x 2" if value % 2 == 0 else f"{value + 7} - 7"
            canvas.art_text(0, 21 + i * 78, 288, formula, 36, 0xEFC589 if i else 0xB3B9FF)


@lru_cache(maxsize=32)
def _render_native(style, hour, minute, second):
    background = _BACKGROUNDS[style]
    canvas = _Canvas(background)
    if style <= ClockStyle.FLIP_CARDS:
        _draw_digital(canvas, style, hour, minute, second)
    elif style == ClockStyle.ANALOG:
        _draw_analog(canvas, hour, minute, second)
    elif style <= ClockStyle.RETRO_LCD:
        _draw_extra(canvas, style, hour, minute, second)
    else:
        canvas.text(_ART_TITLES[style - 8], 12, 0x9AB2CA, 160, 12)
        art = _Canvas(background, (288, 156))
        _draw_art(art, style, hour, minute, second)
        canvas.image.paste(art.image, (16 * _AA, 42 * _AA))
        canvas.text(f"{hour:02d}:{minute:02d}:{second:02d} / 24H", 14, 0xA0B7C7,
                    160, 228, vertical="bottom")
    return canvas.finish()


def render_clock_preview(style_index: int, size: tuple[int, int] = CLOCK_PREVIEW_SIZE,
                         *, now: datetime | time | None = None) -> Image.Image:
    """Return an independent RGB preview; ``None`` uses the fixed gallery time.

    Pass ``now=datetime.now()`` for a ticking preview. All protocol IDs 0..15
    are preserved; out-of-range integer IDs fall back to Neon like firmware.
    Requested sizes are letterboxed, never stretched, to preserve the device's
    4:3 layout. Output dimensions are bounded to 2048px per axis. The small
    native-frame and glyph caches are bounded and never retain Tk resources.
    """
    style_index = operator.index(style_index)
    if not 0 <= style_index < len(_BACKGROUNDS):
        style_index = int(ClockStyle.NEON_DIGITAL)
    if len(size) != 2:
        raise ValueError("Clock preview size must contain width and height")
    width, height = (operator.index(value) for value in size)
    if not (0 < width <= 2048 and 0 < height <= 2048):
        raise ValueError("Clock preview dimensions must be between 1 and 2048 pixels")
    if now is None:
        now = CLOCK_PREVIEW_SAMPLE_TIME
    if not isinstance(now, (datetime, time)):
        raise TypeError("now must be a datetime or time")
    native = _render_native(style_index, now.hour, now.minute, now.second)
    if (width, height) == CLOCK_PREVIEW_SIZE:
        return native.copy()
    ratio = min(width / CLOCK_PREVIEW_SIZE[0], height / CLOCK_PREVIEW_SIZE[1])
    scaled_size = (max(1, round(CLOCK_PREVIEW_SIZE[0] * ratio)),
                   max(1, round(CLOCK_PREVIEW_SIZE[1] * ratio)))
    scaled = native.resize(scaled_size, Image.Resampling.LANCZOS)
    if scaled_size == (width, height):
        return scaled
    output = Image.new("RGB", (width, height), (0, 0, 0))
    output.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    return output
