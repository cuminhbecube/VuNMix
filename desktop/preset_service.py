"""
VuNMix Preset Service — Manage and apply system-wide Audio Profiles / Sound Presets.
"""

import logging
from typing import Dict, Any, Optional

log = logging.getLogger('vunmix.preset')

DEFAULT_PRESETS: Dict[str, Dict[str, Any]] = {
    "🎮 Gaming": {
        "master_volume": 80,
        "mic_volume": 85,
        "apps": {
            "discord": 90,
            "spotify": 35,
            "chrome": 20,
            "msedge": 20,
        },
    },
    "🎧 Work / Focus": {
        "master_volume": 60,
        "mic_volume": 75,
        "apps": {
            "spotify": 70,
            "chrome": 80,
            "msedge": 80,
            "discord": 0,
        },
    },
    "🎬 Cinema / Movie": {
        "master_volume": 90,
        "mic_volume": 0,
        "apps": {
            "vlc": 100,
            "netflix": 100,
            "chrome": 50,
            "spotify": 0,
        },
    },
    "🌙 Night Mode": {
        "master_volume": 35,
        "mic_volume": 50,
        "apps": {
            "spotify": 30,
            "chrome": 25,
            "discord": 40,
        },
    },
}


class PresetService:
    def __init__(self, audio_service, config_presets: Optional[Dict[str, Dict[str, Any]]] = None):
        self.audio = audio_service
        self.presets: Dict[str, Dict[str, Any]] = dict(DEFAULT_PRESETS)
        if config_presets:
            self.presets.update(config_presets)

    def get_preset_names(self) -> list:
        return list(self.presets.keys())

    def get_preset(self, name: str) -> Optional[Dict[str, Any]]:
        return self.presets.get(name)

    def save_preset(self, name: str, preset_data: Dict[str, Any]):
        self.presets[name] = preset_data

    def delete_preset(self, name: str) -> bool:
        if name in self.presets:
            del self.presets[name]
            return True
        return False

    def capture_current_as_preset(self, name: str) -> Dict[str, Any]:
        """Snapshot current Windows master volume, mic, and running apps into a preset."""
        preset = {
            "master_volume": 70,
            "mic_volume": 80,
            "apps": {}
        }
        try:
            # Output devices
            outputs = self.audio.get_output_devices()
            if outputs:
                preset["master_volume"] = outputs[0].volume
            # Input devices
            inputs = self.audio.get_input_devices()
            if inputs:
                preset["mic_volume"] = inputs[0].volume
            # Apps
            apps = self.audio.get_app_sessions()
            for app in apps:
                preset["apps"][app.name.lower()] = app.volume
        except Exception as e:
            log.error(f"Failed to capture current mix: {e}")

        self.presets[name] = preset
        return preset

    def apply_preset(self, name: str) -> bool:
        """Apply a named preset to all active audio endpoints and applications."""
        preset = self.presets.get(name)
        if not preset:
            log.warning(f"Preset '{name}' not found.")
            return False

        log.info(f"Applying Audio Preset: {name}")
        try:
            # Apply Master Output Volume
            if "master_volume" in preset:
                target_vol = int(preset["master_volume"])
                outputs = self.audio.get_output_devices()
                for i, dev in enumerate(outputs):
                    if dev.is_default or i == 0:
                        self.audio.set_device_volume(dev.name, target_vol)
                        break

            # Apply Mic Input Volume
            if "mic_volume" in preset:
                target_mic = int(preset["mic_volume"])
                inputs = self.audio.get_input_devices()
                for i, dev in enumerate(inputs):
                    if dev.is_default or i == 0:
                        self.audio.set_device_volume(dev.name, target_mic)
                        break

            # Apply per-app volumes
            app_targets = preset.get("apps", {})
            if app_targets:
                apps = self.audio.get_app_sessions()
                for app in apps:
                    app_name_lower = app.name.lower()
                    for target_key, vol in app_targets.items():
                        target_key_lower = target_key.lower()
                        if target_key_lower in app_name_lower or app_name_lower in target_key_lower:
                            self.audio.set_session_volume(app.name, int(vol))
                            break
            return True
        except Exception as e:
            log.error(f"Error applying preset {name}: {e}")
            return False
