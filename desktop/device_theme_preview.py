"""Load native LVGL appearance frames without redrawing device typography."""
from functools import lru_cache

from PIL import Image

from app_branding import resource_path
from protocol import DeviceTheme

THEME_PREVIEW_SIZE = (320, 240)
THEME_ASSET_NAMES = (
    "classic", "windows_dark", "studio", "paper", "orbit", "pixel", "blocks", "terminal",
)


@lru_cache(maxsize=8)
def _native_frame(theme_id: int):
    theme_id = int(DeviceTheme(theme_id))
    filename = f"assets/device_themes/{THEME_ASSET_NAMES[theme_id]}.png"
    with Image.open(resource_path(filename)) as image:
        if image.size != THEME_PREVIEW_SIZE or image.mode != "RGB":
            raise ValueError(f"Invalid native device preview: {filename}")
        image.load()
        return image.copy()


def load_theme_preview(theme_id: int) -> Image.Image:
    """Return an independent 320×240 RGB sample; never a live device capture."""
    return _native_frame(int(DeviceTheme(theme_id))).copy()
