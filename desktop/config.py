"""
VuNMix Configuration — Load/save config.json with fixed COM port settings.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from protocol import DeviceSettings, Color

# Config file lives next to the script
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_CONFIG_DIR, 'config.json')

_DEFAULT_CONFIG = {
    "com_port": "COM14",
    "update_interval_ms": 500,
    "run_on_startup": False,
    "settings": {
        "sleep_after_seconds": 5,
        "acceleration_percentage": 60,
        "continuous_scroll": True,
        "volume_min_color": [0, 0, 255],
        "volume_max_color": [255, 0, 0],
        "mix_channel_a_color": [0, 0, 255],
        "mix_channel_b_color": [255, 0, 255],
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
        if not os.path.exists(path):
            cfg = cls()
            cfg.save(path)
            return cfg

        with open(path, 'r') as f:
            data = json.load(f)

        settings_dict = data.get('settings', _DEFAULT_CONFIG['settings'])
        return cls(
            com_port=data.get('com_port', 'COM14'),
            update_interval_ms=data.get('update_interval_ms', 500),
            run_on_startup=data.get('run_on_startup', False),
            device_settings=DeviceSettings.from_config(settings_dict),
        )

    def save(self, path: Optional[str] = None):
        path = path or _CONFIG_FILE
        data = {
            "com_port": self.com_port,
            "update_interval_ms": self.update_interval_ms,
            "run_on_startup": self.run_on_startup,
            "settings": {
                "sleep_after_seconds": self.device_settings.sleep_after_seconds,
                "acceleration_percentage": self.device_settings.acceleration_percentage,
                "continuous_scroll": self.device_settings.continuous_scroll,
                "volume_min_color": self.device_settings.volume_min_color.to_list(),
                "volume_max_color": self.device_settings.volume_max_color.to_list(),
                "mix_channel_a_color": self.device_settings.mix_channel_a_color.to_list(),
                "mix_channel_b_color": self.device_settings.mix_channel_b_color.to_list(),
            }
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
