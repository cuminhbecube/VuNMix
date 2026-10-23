"""Device-faithful clock previews, without Tk or installed system fonts."""

from datetime import datetime, time
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import ImageChops

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "desktop"))

from clock_font_data import load_clock_fonts
from clock_preview import (CLOCK_PREVIEW_SIZE, _draw_art, _render_native,
                           _text_mask, render_clock_preview)
from protocol import ClockStyle, CLOCK_STYLE_NAMES


class ClockPreviewTests(unittest.TestCase):
    def test_every_wire_style_is_a_distinct_complete_image(self):
        frames = [render_clock_preview(style) for style in ClockStyle]
        self.assertEqual(len(frames), len(CLOCK_STYLE_NAMES))
        self.assertEqual(len({hashlib.sha256(frame.tobytes()).digest() for frame in frames}), 16)
        for frame in frames:
            self.assertEqual(frame.size, CLOCK_PREVIEW_SIZE)
            self.assertEqual(frame.mode, "RGB")
            self.assertGreater(len(frame.getcolors(320 * 240)), 4)

    def test_sample_time_is_deterministic_and_caller_cannot_modify_cache(self):
        first = render_clock_preview(0)
        expected = render_clock_preview(0, now=time(10, 24, 36))
        self.assertIsNone(ImageChops.difference(first, expected).getbbox())
        first.paste((255, 0, 0), (0, 0, 320, 240))
        self.assertIsNone(ImageChops.difference(render_clock_preview(0), expected).getbbox())
        self.assertEqual(render_clock_preview(100).tobytes(), expected.tobytes())

    def test_device_fonts_keep_native_metrics_and_binary_dseg_masks(self):
        fonts = load_clock_fonts()
        self.assertEqual(set(fonts), {"dseg90", "10", "12", "14", "16", "20", "36"})
        self.assertEqual((fonts["dseg90"]["line_height"], fonts["dseg90"]["base_line"]), (90, 0))
        self.assertEqual(_text_mask("dseg90", "88").size, (146, 90))
        self.assertEqual(_text_mask("dseg90", "23:59", 2).size, (318, 90))
        self.assertEqual(set(_text_mask("dseg90", "88").tobytes()), {0, 255})
        self.assertEqual(_text_mask("12", "VUNMIX").height, 15)
        self.assertGreater(len(set(_text_mask("36", "10:24").tobytes())), 10)

    def test_neon_blinks_only_the_colon_and_keeps_full_digits(self):
        even = render_clock_preview(ClockStyle.NEON_DIGITAL, now=time(23, 59, 0))
        odd = render_clock_preview(ClockStyle.NEON_DIGITAL, now=time(23, 59, 1))
        difference = ImageChops.difference(even, odd)
        self.assertEqual(difference.getbbox(), (154, 90, 165, 138))
        # Exact source DSEG foreground and the original black screen.
        self.assertIn((6, 182, 212), [color for _, color in even.getcolors(320 * 240)])
        self.assertEqual(even.getpixel((0, 0)), (0, 0, 0))

    def test_binary_preview_encodes_actual_time_in_all_eighteen_dots(self):
        colors = ((112, 214, 255), (189, 154, 255), (125, 230, 181))
        for moment in (time(0, 0, 0), time(23, 59, 59), time(10, 24, 36)):
            frame = render_clock_preview(ClockStyle.BINARY, now=moment)
            for col, value in enumerate((moment.hour, moment.minute, moment.second)):
                for row in range(6):
                    expected = colors[col] if value & (1 << (5 - row)) else (24, 35, 45)
                    self.assertEqual(frame.getpixel((82 + col * 78, 65 + row * 22)), expected)

    def test_seconds_updates_and_24_hour_rollover_match_each_style(self):
        for style in ClockStyle:
            with self.subTest(style=style.name):
                before = render_clock_preview(style, now=datetime(2026, 1, 1, 23, 59, 59))
                after = render_clock_preview(style, now=datetime(2026, 1, 2, 0, 0, 0))
                self.assertIsNotNone(ImageChops.difference(before, after).getbbox())
                a = render_clock_preview(style, now=time(10, 24, 36))
                b = render_clock_preview(style, now=time(10, 24, 37))
                self.assertIsNotNone(ImageChops.difference(a, b).getbbox())
        # Matrix HH:MM content is stable; only its seconds footer changes.
        a = render_clock_preview(ClockStyle.PIXEL_ART, now=time(10, 24, 36))
        b = render_clock_preview(ClockStyle.PIXEL_ART, now=time(10, 24, 37))
        self.assertIsNone(ImageChops.difference(a.crop((16, 42, 304, 198)),
                                              b.crop((16, 42, 304, 198))).getbbox())

    def test_scaling_preserves_device_aspect_and_bounds_memory(self):
        native = render_clock_preview(ClockStyle.TERMINAL)
        square = render_clock_preview(ClockStyle.TERMINAL, (320, 320))
        self.assertEqual(square.size, (320, 320))
        self.assertEqual(square.getpixel((160, 0)), (0, 0, 0))
        self.assertEqual(square.crop((0, 40, 320, 280)).tobytes(), native.tobytes())
        self.assertEqual(render_clock_preview(3, (640, 480)).size, (640, 480))
        self.assertEqual(render_clock_preview(3, (160, 120)).size, (160, 120))
        for size in ((0, 240), (-1, 240), (4096, 4096), (320,)):
            with self.assertRaises(ValueError):
                render_clock_preview(0, size)
        with self.assertRaises(TypeError):
            render_clock_preview(0, now="10:24:36")
        self.assertEqual(_render_native.cache_info().maxsize, 32)


class _DrawRecorder:
    def __init__(self):
        self.commands = []

    def rect(self, x, y, width, height, color, radius=0):
        self.commands.append(("R", x, y, width, height, color, radius))

    def line(self, x1, y1, x2, y2, color, width=2):
        self.commands.append(("L", x1, y1, x2, y2, color, width))

    def art_text(self, x, y, width, text, font, color):
        self.commands.append(("T", x, y, width, font, color, text))


class ClockPreviewFirmwareParityTests(unittest.TestCase):
    def test_all_art_draw_commands_match_actual_cpp_for_forty_clock_states(self):
        """Compare against production C++ code, not a second expected layout."""
        compiler = shutil.which("g++")
        if not compiler:
            self.skipTest("Host C++ compiler unavailable")
        source = (REPO / "desktop/tests/fixtures/clock_art_preview_stub.hpp").read_text()
        for name in ("DisplayClockArtHelpers", "DisplayClockArtDigits",
                     "DisplayClockArtWords", "DisplayClockArtHands"):
            source += '\n#include "' + (REPO / f"src/ui/modules/{name}.inc").as_posix() + '"\n'
        source += r'''
int main() {
    const int times[][3] = {{0,0,0}, {10,24,36}, {23,59,59}, {12,12,0}, {1,1,1}};
    lv_draw_ctx_t ctx; const lv_area_t base{0,0,287,155};
    for (const auto& time: times) for (int style=8; style<16; ++style) {
        s_artHour=time[0]; s_artMinute=time[1]; s_artSecond=time[2];
        printf("S\t%d\t%d\t%d\t%d\n", style, time[0], time[1], time[2]);
        switch(style) {
            case 8: DrawNixie(&ctx,base); break;
            case 9: DrawWordClock(&ctx,base); break;
            case 10: DrawMatrixTime(&ctx,base,false); break;
            case 11: DrawMatrixTime(&ctx,base,true); break;
            case 12: DrawClockClock(&ctx,base); break;
            case 13: DrawBarcode(&ctx,base); break;
            case 14: DrawPolygon(&ctx,base); break;
            case 15: DrawMathClock(&ctx,base); break;
        }
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cpp, binary = directory / "clock-art.cpp", directory / "clock-art-test"
            cpp.write_text(source, encoding="utf-8")
            build = subprocess.run([compiler, "-std=c++17", str(cpp), "-o", str(binary)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
        cases = {}
        current = None
        for line in run.stdout.splitlines():
            fields = line.split("\t")
            if fields[0] == "S":
                current = tuple(map(int, fields[1:]))
                cases[current] = []
            elif fields[0] == "T":
                cases[current].append(("T", *map(int, fields[1:6]), fields[6]))
            else:
                cases[current].append((fields[0], *map(int, fields[1:])))
        self.assertEqual(len(cases), 40)
        for (style, hour, minute, second), expected in cases.items():
            with self.subTest(style=style, hour=hour, minute=minute, second=second):
                recorder = _DrawRecorder()
                _draw_art(recorder, style, hour, minute, second)
                self.assertEqual(recorder.commands, expected)


if __name__ == "__main__":
    unittest.main()
