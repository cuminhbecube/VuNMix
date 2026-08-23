"""Persistent VuNMix audio profiles and trigger matching."""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from typing import Any, Dict, Iterable, Optional

from config import CONFIG_DIR
from protocol import DisplayMode


log = logging.getLogger("vunmix.profiles")
PROFILE_FILE = os.path.join(CONFIG_DIR, "profiles.json")


def _mix(volume: int, muted: bool = False) -> Dict[str, Any]:
    return {"volume": max(0, min(100, int(volume))), "muted": bool(muted)}


DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "Gaming": {
        "output": _mix(80),
        "mic": _mix(85),
        "apps": {
            "discord": _mix(90),
            "spotify": _mix(35),
        },
        "triggers": {
            "focused_apps": ["steam", "game"],
            "running_apps": [],
            "obs_streaming": False,
            "hardware_modes": [int(DisplayMode.MODE_GAME)],
        },
    },
    "Work": {
        "output": _mix(60),
        "mic": _mix(75),
        "apps": {
            "chrome": _mix(80),
            "msedge": _mix(80),
            "discord": _mix(0, True),
        },
        "triggers": {
            "focused_apps": ["code", "devenv"],
            "running_apps": [],
            "obs_streaming": False,
            "hardware_modes": [int(DisplayMode.MODE_APPLICATION)],
        },
    },
    "Streaming": {
        "output": _mix(70),
        "mic": _mix(90),
        "apps": {
            "obs64": _mix(80),
            "discord": _mix(70),
            "spotify": _mix(25),
        },
        "triggers": {
            "focused_apps": [],
            "running_apps": ["obs64"],
            "obs_streaming": True,
            "hardware_modes": [],
        },
    },
}


def _normalized_process_name(value: str) -> str:
    return str(value or "").strip().lower().removesuffix(".exe")


def _normalized_mix(value: Any, default_volume: int = 0) -> Dict[str, Any]:
    if isinstance(value, dict):
        return _mix(value.get("volume", default_volume), value.get("muted", False))
    return _mix(value if value is not None else default_volume, False)


def normalize_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    data = copy.deepcopy(data or {})
    output = data.get("output", data.get("master_volume", 70))
    mic = data.get("mic", data.get("mic_volume", 80))
    apps = {}
    for name, mix in (data.get("apps") or {}).items():
        key = _normalized_process_name(name)
        if key:
            apps[key] = _normalized_mix(mix)

    triggers = data.get("triggers") or {}
    return {
        "output": _normalized_mix(output, 70),
        "mic": _normalized_mix(mic, 80),
        "apps": apps,
        "triggers": {
            "focused_apps": [
                value for value in (
                    _normalized_process_name(v) for v in triggers.get("focused_apps", [])
                ) if value
            ],
            "running_apps": [
                value for value in (
                    _normalized_process_name(v) for v in triggers.get("running_apps", [])
                ) if value
            ],
            "obs_streaming": bool(triggers.get("obs_streaming", False)),
            "hardware_modes": [
                int(value) for value in triggers.get("hardware_modes", [])
                if isinstance(value, (int, str)) and str(value).lstrip("-").isdigit()
            ],
        },
    }


class AudioProfileService:
    """CRUD, persistence, apply/capture and context matching for mixer profiles."""

    def __init__(self, audio_service, path: Optional[str] = None):
        self.audio = audio_service
        self.path = path or PROFILE_FILE
        self._lock = threading.RLock()
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.active_profile: str = ""
        self.auto_switch_enabled = True
        self.load()

    def load(self) -> None:
        with self._lock:
            profiles = copy.deepcopy(DEFAULT_PROFILES)
            auto_enabled = True
            active = ""
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict):
                    saved = payload.get("profiles", {})
                    if isinstance(saved, dict):
                        for name, data in saved.items():
                            if str(name).strip() and isinstance(data, dict):
                                profiles[str(name).strip()] = normalize_profile(data)
                    auto_enabled = bool(payload.get("auto_switch_enabled", True))
                    active = str(payload.get("active_profile", "") or "")
            except FileNotFoundError:
                pass
            except Exception as exc:
                log.warning("Failed to load profiles %s: %s", self.path, exc)

            self.profiles = {
                name: normalize_profile(data) for name, data in profiles.items()
            }
            self.auto_switch_enabled = auto_enabled
            self.active_profile = active if active in self.profiles else ""

    def save(self) -> None:
        with self._lock:
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, exist_ok=True)
            payload = {
                "version": 1,
                "auto_switch_enabled": self.auto_switch_enabled,
                "active_profile": self.active_profile,
                "profiles": self.profiles,
            }
            fd, tmp = tempfile.mkstemp(prefix="profiles-", suffix=".json.tmp", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass

    def get_preset_names(self) -> list:
        return self.profile_names()

    def profile_names(self) -> list:
        with self._lock:
            return list(self.profiles.keys())

    def get_preset(self, name: str) -> Optional[Dict[str, Any]]:
        return self.get_profile(name)

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            value = self.profiles.get(name)
            return copy.deepcopy(value) if value else None

    def save_preset(self, name: str, preset_data: Dict[str, Any]):
        return self.save_profile(name, preset_data)

    def save_profile(self, name: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("Profile name is required")
        normalized = normalize_profile(profile_data)
        with self._lock:
            self.profiles[name] = normalized
            self.save()
        return copy.deepcopy(normalized)

    def delete_preset(self, name: str) -> bool:
        return self.delete_profile(name)

    def delete_profile(self, name: str) -> bool:
        with self._lock:
            if name not in self.profiles:
                return False
            del self.profiles[name]
            if self.active_profile == name:
                self.active_profile = ""
            self.save()
            return True

    def set_auto_switch_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.auto_switch_enabled = bool(enabled)
            self.save()

    @staticmethod
    def _default_index(items) -> Optional[int]:
        if not items:
            return None
        for index, item in enumerate(items):
            if getattr(item, "is_default", False):
                return index
        return 0

    def capture_current_as_preset(self, name: str) -> Dict[str, Any]:
        outputs = self.audio.get_sessions_for_mode(DisplayMode.MODE_OUTPUT)
        inputs = self.audio.get_sessions_for_mode(DisplayMode.MODE_INPUT)
        apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        out_index = self._default_index(outputs)
        mic_index = self._default_index(inputs)
        profile = {
            "output": _mix(
                outputs[out_index].volume if out_index is not None else 70,
                outputs[out_index].is_muted if out_index is not None else False,
            ),
            "mic": _mix(
                inputs[mic_index].volume if mic_index is not None else 80,
                inputs[mic_index].is_muted if mic_index is not None else False,
            ),
            "apps": {
                _normalized_process_name(item.name): _mix(item.volume, item.is_muted)
                for item in apps if _normalized_process_name(item.name)
            },
            "triggers": {
                "focused_apps": [],
                "running_apps": [],
                "obs_streaming": False,
                "hardware_modes": [],
            },
        }
        self.save_profile(name, profile)
        return self.get_profile(name) or profile

    def _apply_device_mix(self, mode: DisplayMode, mix: Dict[str, Any]) -> None:
        items = self.audio.get_sessions_for_mode(mode)
        index = self._default_index(items)
        if index is None:
            return
        self.audio.set_volume(
            mode,
            index,
            int(mix.get("volume", items[index].volume)),
            bool(mix.get("muted", items[index].is_muted)),
        )

    def apply_preset(self, name: str) -> bool:
        return self.apply_profile(name)

    def apply_profile(self, name: str, *, source: str = "manual") -> bool:
        profile = self.get_profile(name)
        if not profile:
            log.warning("Audio profile not found: %s", name)
            return False
        try:
            self._apply_device_mix(DisplayMode.MODE_OUTPUT, profile["output"])
            self._apply_device_mix(DisplayMode.MODE_INPUT, profile["mic"])
            apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
            targets = profile.get("apps", {})
            for index, item in enumerate(apps):
                item_name = _normalized_process_name(item.name)
                match = next((key for key in targets if key in item_name or item_name in key), None)
                if not match:
                    continue
                mix = targets[match]
                self.audio.set_volume(
                    DisplayMode.MODE_APPLICATION,
                    index,
                    int(mix.get("volume", item.volume)),
                    bool(mix.get("muted", item.is_muted)),
                )
            with self._lock:
                self.active_profile = name
                self.save()
            log.info("Applied audio profile %s (source=%s)", name, source)
            return True
        except Exception:
            log.exception("Failed to apply audio profile %s", name)
            return False

    def cycle_profile(self, *, source: str = "hardware") -> Optional[str]:
        names = self.profile_names()
        if not names:
            return None
        try:
            current = names.index(self.active_profile)
        except ValueError:
            current = -1
        name = names[(current + 1) % len(names)]
        return name if self.apply_profile(name, source=source) else None

    def profile_for_hardware_mode(self, mode: int) -> Optional[str]:
        with self._lock:
            for name, profile in self.profiles.items():
                if int(mode) in profile.get("triggers", {}).get("hardware_modes", []):
                    return name
        return None

    def match_context(
        self,
        *,
        focused_app: str = "",
        running_apps: Iterable[str] = (),
        obs_streaming: bool = False,
    ) -> Optional[str]:
        """Choose exactly one highest-priority profile for the current context."""
        if not self.auto_switch_enabled:
            return None
        focused = _normalized_process_name(focused_app)
        running = {_normalized_process_name(value) for value in running_apps}
        running.discard("")
        best_name = None
        best_score = -1
        with self._lock:
            for order, (name, profile) in enumerate(self.profiles.items()):
                triggers = profile.get("triggers", {})
                score = -1
                if bool(triggers.get("obs_streaming")) and obs_streaming:
                    score = max(score, 300)
                focus_targets = triggers.get("focused_apps", [])
                if focused and any(target in focused or focused in target for target in focus_targets):
                    score = max(score, 200)
                run_targets = set(triggers.get("running_apps", []))
                if run_targets & running:
                    score = max(score, 100)
                # Stable insertion order breaks equal-priority ties and avoids
                # oscillation when several processes are active simultaneously.
                score = score * 1000 - order if score >= 0 else -1
                if score > best_score:
                    best_score = score
                    best_name = name
        return best_name if best_score >= 0 else None
