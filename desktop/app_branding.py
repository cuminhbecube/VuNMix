"""VuNMix artwork shared by the desktop UI, tray and Windows package.

The personal logo in assets/logo.png is the source of truth. Generate the
multi-size Windows icon with ``python desktop/app_branding.py --build-icon``.
"""
from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageOps

log = logging.getLogger(__name__)
WINDOWS_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def resource_path(relative_path: str) -> str:
    """Resolve assets independently of the launcher's working directory."""
    root = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return str(Path(root) / relative_path)


@lru_cache(maxsize=4)
def _read_logo(path: str) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _fit_logo(image: Image.Image, size: int) -> Image.Image:
    if not isinstance(size, int) or size <= 0:
        raise ValueError("Logo size must be a positive integer")
    fitted = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(fitted, ((size - fitted.width) // 2,
                                  (size - fitted.height) // 2))
    return canvas


def load_logo(size: int = 64) -> Image.Image:
    """Return an independent RGBA copy of the original, proportionally sized logo."""
    try:
        original = _read_logo(resource_path("assets/logo.png"))
    except (OSError, ValueError) as exc:
        # A damaged source checkout must still be usable. Release verification
        # rejects packages with missing or mismatched branding assets.
        log.warning("Could not load the VuNMix logo: %s", exc)
        original = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(original)
        draw.rounded_rectangle((4, 4, 60, 60), radius=10, fill="#303030")
        draw.line((18, 18, 32, 48, 46, 18), fill="#ffffff", width=7)
    return _fit_logo(original, size)


def create_tray_icon(connected: bool) -> Image.Image:
    """Keep the original artwork; show connection state in a small corner badge."""
    image = load_logo(64)
    draw = ImageDraw.Draw(image)
    draw.ellipse((48, 48, 63, 63),
                 fill="#6ccb5f" if connected else "#8a8a8a",
                 outline="#202020", width=3)
    return image


def build_windows_icon(source: Path | None = None,
                       destination: Path | None = None) -> Path:
    """Build every Windows icon size from the PNG, failing on invalid artwork."""
    source = Path(source) if source is not None else Path(resource_path("assets/logo.png"))
    destination = (Path(destination) if destination is not None
                   else Path(resource_path("assets/icon.ico")))
    with Image.open(source) as original:
        image = _fit_logo(original.convert("RGBA"), max(WINDOWS_ICON_SIZES))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The Tk 8.6 build bundled with Python 3.11 reads ICO frame dimensions as
    # DIB headers. PNG-compressed frames can make it upscale the first 16px
    # image instead of selecting the native size. DIB retains RGBA and works
    # with both Tk and the Windows executable/installer icon loaders.
    image.save(destination, format="ICO", bitmap_format="bmp",
               sizes=[(size, size) for size in WINDOWS_ICON_SIZES])
    return destination


def apply_window_icon(window) -> None:
    """Brand a Tk root or child window, including CTk's delayed Windows reset."""
    import tkinter as tk
    from PIL import ImageTk

    def apply():
        try:
            if not window.winfo_exists():
                return
            if sys.platform == "win32":
                try:
                    window.iconbitmap(resource_path("assets/icon.ico"))
                    return
                except (tk.TclError, OSError):
                    log.warning("Could not load the Windows icon; using the PNG logo")
            images = tuple(ImageTk.PhotoImage(load_logo(size), master=window)
                           for size in (16, 32, 48, 64))
            window.iconphoto(True, *images)
            window._vunmix_icon_images = images
        except tk.TclError:
            # The window may have closed before a pending callback is handled.
            return

    apply()
    if sys.platform != "win32":
        return

    # CTkToplevel 5.2 installs its own icon after 200 ms even after iconbitmap.
    # Reapply on the Tk thread, and cancel if a short-lived picker closes first.
    pending = None

    def reapply():
        nonlocal pending
        pending = None
        apply()

    def cancel(event):
        nonlocal pending
        if event.widget is window and pending is not None:
            try:
                window.after_cancel(pending)
            except tk.TclError:
                pass
            pending = None

    pending = window.after(250, reapply)
    window.bind("<Destroy>", cancel, add="+")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-icon", action="store_true")
    args = parser.parse_args()
    if args.build_icon:
        print(build_windows_icon())
    else:
        parser.print_help()
