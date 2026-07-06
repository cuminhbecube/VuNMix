"""
VuNMix Configuration — Load/save config.json with fixed COM port settings.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from protocol import DeviceSettings, Color

# Runtime files must be user-writable even when VuNMix is installed in
# C:\Program Files. Keep the old adjacent config as a one-time migration source.
_LEGACY_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
CONFIG_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local')),
    'VuNMix',
)
_CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

_DEFAULT_CONFIG = {
    "com_port": "COM14",
    "update_interval_ms": 500,
    "run_on_startup": False,
    "settings": {
        "sleep_after_seconds": 300,
        "sleep_enabled": True,
        "standby_led_mode": 0,
        "acceleration_percentage": 60,
        "continuous_scroll": True,
        "volume_min_color": [0, 0, 255],
        "volume_max_color": [255, 0, 0],
        "mix_channel_a_color": [0, 0, 255],
        "mix_channel_b_color": [255, 0, 255],
        "led_brightness": 96,
        "clock_standby_minutes": 10,
    }
}


@dataclass
class AppConfig:
    com_port: str = "COM14"
    update_interval_ms: int = 500
    run_on_startup: bool = False
    device_settings: DeviceSettings = field(default_factory=DeviceSettings)

    @classmethod
    def load(cls, path: Optional[str] = None) -> 'AppConfig':
        path = path or _CONFIG_FILE
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if not os.path.exists(path):
            if path == _CONFIG_FILE and os.path.exists(_LEGACY_CONFIG_FILE):
                try:
                    with open(_LEGACY_CONFIG_FILE, 'r', encoding='utf-8') as source:
                        legacy_data = json.load(source)
                    cfg = cls._from_dict(legacy_data)
                    cfg.save(path)
                    return cfg
                except (OSError, ValueError, TypeError, IndexError):
                    pass
            cfg = cls()
            cfg.save(path)
            return cfg

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls._from_dict(data)
        except (OSError, json.JSONDecodeError, ValueError, TypeError, IndexError) as exc:
            print(f"Warning: Invalid configuration {path}: {exc}. Using defaults.")
            cfg = cls()
            try:
                cfg.save(path)
            except OSError:
                pass
            return cfg

    @classmethod
    def _from_dict(cls, data: dict) -> 'AppConfig':
        if not isinstance(data, dict):
            raise ValueError("Configuration root must be an object")
        settings_dict = data.get('settings', _DEFAULT_CONFIG['settings'])
        if not isinstance(settings_dict, dict):
            raise ValueError("'settings' must be an object")
        return cls(
            com_port=str(data.get('com_port', 'COM14')).strip() or 'COM14',
            update_interval_ms=max(50, min(10000, int(data.get('update_interval_ms', 500)))),
            run_on_startup=bool(data.get('run_on_startup', False)),
            device_settings=DeviceSettings.from_config(settings_dict),
        )

    def save(self, path: Optional[str] = None):
        path = path or _CONFIG_FILE
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        data = {
            "com_port": self.com_port,
            "update_interval_ms": self.update_interval_ms,
            "run_on_startup": self.run_on_startup,
            "settings": {
                "sleep_after_seconds": self.device_settings.sleep_after_seconds,
                "sleep_enabled": self.device_settings.sleep_enabled,
                "standby_led_mode": self.device_settings.standby_led_mode,
                "acceleration_percentage": self.device_settings.acceleration_percentage,
                "continuous_scroll": self.device_settings.continuous_scroll,
                "volume_min_color": self.device_settings.volume_min_color.to_list(),
                "volume_max_color": self.device_settings.volume_max_color.to_list(),
                "mix_channel_a_color": self.device_settings.mix_channel_a_color.to_list(),
                "mix_channel_b_color": self.device_settings.mix_channel_b_color.to_list(),
                "led_brightness": self.device_settings.led_brightness,
                "clock_standby_minutes": self.device_settings.clock_standby_minutes,
            }
        }
        temp_path = f"{path}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
