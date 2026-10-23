"""Regressions for original artwork, launcher paths and generated Windows icons."""
from contextlib import chdir
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))

from app_branding import (WINDOWS_ICON_SIZES, build_windows_icon,
                          create_tray_icon, load_logo, resource_path)


def visible_pixels(image):
    background = Image.new("RGBA", image.size, "#202020")
    return Image.alpha_composite(background, image).tobytes()


class AppBrandingTests(unittest.TestCase):
    def test_source_logo_loads_from_an_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.assertEqual(Path(resource_path("assets/logo.png")),
                             DESKTOP / "assets" / "logo.png")
            with Image.open(DESKTOP / "assets" / "logo.png") as source:
                original = source.convert("RGBA")
            actual = load_logo(original.width)
            self.assertEqual(actual.getchannel("A").tobytes(),
                             original.getchannel("A").tobytes())
            self.assertEqual(visible_pixels(actual), visible_pixels(original))

    def test_frozen_assets_keep_color_transparency_and_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory) / "assets"
            assets.mkdir()
            Image.new("RGBA", (100, 50), (30, 140, 220, 255)).save(assets / "logo.png")
            with mock.patch.object(sys, "_MEIPASS", directory, create=True):
                self.assertEqual(Path(resource_path("assets/logo.png")), assets / "logo.png")
                logo = load_logo(64)
            self.assertEqual(logo.getbbox(), (0, 16, 64, 48))
            self.assertEqual(logo.getpixel((32, 32)), (30, 140, 220, 255))
            self.assertEqual(logo.getpixel((0, 0))[3], 0)

    def test_connection_badge_does_not_recolor_the_artwork(self):
        original = load_logo(64)
        for connected, badge in ((True, (108, 203, 95, 255)),
                                 (False, (138, 138, 138, 255))):
            with self.subTest(connected=connected):
                tray = create_tray_icon(connected)
                self.assertEqual(tray.crop((0, 0, 64, 48)).tobytes(),
                                 original.crop((0, 0, 64, 48)).tobytes())
                self.assertEqual(tray.crop((0, 48, 48, 64)).tobytes(),
                                 original.crop((0, 48, 48, 64)).tobytes())
                self.assertEqual(tray.getpixel((56, 56)), badge)
        self.assertEqual(load_logo(64).tobytes(), original.tobytes())

    def test_callers_cannot_mutate_shared_logo_artwork(self):
        first = load_logo(64)
        expected = first.tobytes()
        first.paste((1, 2, 3, 255), (0, 0, 64, 64))
        self.assertEqual(load_logo(64).tobytes(), expected)

    def test_windows_icon_contains_all_sizes_and_the_original_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build_windows_icon(destination=Path(directory) / "icon.ico")
            # Tk's Windows loader needs real DIB dimensions in every frame;
            # PNG payloads make older Tk versions select the first small icon.
            encoded = output.read_bytes()
            count = struct.unpack_from("<H", encoded, 4)[0]
            self.assertEqual(count, len(WINDOWS_ICON_SIZES))
            for index in range(count):
                offset = struct.unpack_from("<I", encoded, 6 + 16 * index + 12)[0]
                header_size, width, height = struct.unpack_from("<Iii", encoded, offset)
                self.assertEqual(header_size, 40)
                self.assertIn(width, WINDOWS_ICON_SIZES)
                self.assertEqual(height, width * 2)
            with Image.open(output) as icon:
                self.assertEqual(icon.ico.sizes(), {(size, size) for size in WINDOWS_ICON_SIZES})
                largest = icon.ico.getimage((256, 256)).convert("RGBA")
                self.assertEqual(visible_pixels(largest), visible_pixels(load_logo(256)))
                for size in WINDOWS_ICON_SIZES:
                    frame = icon.ico.getimage((size, size)).convert("RGBA")
                    self.assertEqual(frame.size, (size, size))
                    self.assertEqual(frame.getchannel("A").getextrema(), (0, 255))
            with self.assertRaises(FileNotFoundError):
                build_windows_icon(Path(directory) / "missing.png", output)


if __name__ == "__main__":
    unittest.main()
