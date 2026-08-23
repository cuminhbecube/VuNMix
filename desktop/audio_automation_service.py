"""Rule-based application routing and crash-safe audio ducking for VuNMix."""

from __future__ import annotations

import copy
import fnmatch
import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from config import CONFIG_DIR
from protocol import DisplayMode


log = logging.getLogger("vunmix.audio_automation")
AUTOMATION_FILE = os.path.join(CONFIG_DIR, "audio_automation.json")
CONFIG_VERSION = 1


def _norm(value: str) -> str:
    return str(value or "").strip().lower().removesuffix(".exe")


def _matches(value: str, pattern: str) -> bool:
    value = _norm(value)
    pattern = _norm(pattern)
    if not value or not pattern:
        return False
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatch(value, pattern)
    return pattern in value or value in pattern


def _clamp_int(value, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _clamp_float(value, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return low


@dataclass
class RoutingRule:
    name: str
    app_pattern: str
    device_pattern: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: dict) -> "RoutingRule":
        return cls(
            name=str(value.get("name", "Routing rule") or "Routing rule"),
            app_pattern=str(value.get("app_pattern", "") or ""),
            device_pattern=str(value.get("device_pattern", "") or ""),
            enabled=bool(value.get("enabled", True)),
        )


@dataclass
class DuckingRule:
    name: str
    trigger_pattern: str
    target_patterns: List[str] = field(default_factory=list)
    reduction_percent: int = 50
    threshold: float = 0.02
    attack_ms: int = 150
    release_ms: int = 600
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: dict) -> "DuckingRule":
        targets = value.get("target_patterns", [])
        if isinstance(targets, str):
            targets = [targets]
        return cls(
            name=str(value.get("name", "Ducking rule") or "Ducking rule"),
            trigger_pattern=str(value.get("trigger_pattern", "") or ""),
            target_patterns=[str(item) for item in targets if str(item).strip()],
            reduction_percent=_clamp_int(value.get("reduction_percent", 50), 0, 100),
            threshold=_clamp_float(value.get("threshold", 0.02), 0.0, 1.0),
            attack_ms=_clamp_int(value.get("attack_ms", 150), 0, 10000),
            release_ms=_clamp_int(value.get("release_ms", 600), 0, 30000),
            enabled=bool(value.get("enabled", True)),
        )


@dataclass
class _DuckTargetState:
    key: str
    name: str
    baseline_volume: int
    baseline_muted: bool
    current_ratio: float = 1.0
    phase: str = "idle"
    phase_started_at: float = 0.0
    phase_start_volume: int = 0
    phase_target_volume: int = 0
    phase_duration_s: float = 0.0
    last_applied_volume: Optional[int] = None
    release_ms: int = 600


class AudioAutomationService:
    """Persistent rule engine for routing and non-destructive ducking."""

    def __init__(self, audio_service, path: Optional[str] = None):
        self.audio = audio_service
        self.path = path or AUTOMATION_FILE
        self._lock = threading.RLock()
        self.routing_enabled = True
        self.ducking_enabled = True
        self.routing_rules: List[RoutingRule] = []
        self.ducking_rules: List[DuckingRule] = []
        self._recovery: Dict[str, dict] = {}
        self._duck_states: Dict[str, _DuckTargetState] = {}
        self._applied_routes: Dict[int, str] = {}
        self.last_routing_error = ""
        self.load()

    # ------------------------------------------------------------------
    # Persistence / configuration
    # ------------------------------------------------------------------
    def load(self) -> None:
        payload = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            payload = {}
        except Exception as exc:
            log.warning("Failed to load audio automation config %s: %s", self.path, exc)
            payload = {}

        with self._lock:
            self.routing_enabled = bool(payload.get("routing_enabled", True))
            self.ducking_enabled = bool(payload.get("ducking_enabled", True))
            self.routing_rules = [
                RoutingRule.from_dict(item)
                for item in payload.get("routing_rules", [])
                if isinstance(item, dict)
            ]
            self.ducking_rules = [
                DuckingRule.from_dict(item)
                for item in payload.get("ducking_rules", [])
                if isinstance(item, dict)
            ]
            recovery = payload.get("recovery", {})
            self._recovery = copy.deepcopy(recovery) if isinstance(recovery, dict) else {}

        if not os.path.exists(self.path):
            try:
                self.save()
            except OSError:
                pass

    def save(self) -> None:
        with self._lock:
            payload = {
                "version": CONFIG_VERSION,
                "routing_enabled": self.routing_enabled,
                "ducking_enabled": self.ducking_enabled,
                "routing_rules": [asdict(rule) for rule in self.routing_rules],
                "ducking_rules": [asdict(rule) for rule in self.ducking_rules],
                "recovery": copy.deepcopy(self._recovery),
            }

        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="audio-automation-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def set_routing_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.routing_enabled = bool(enabled)
        self.save()

    def set_ducking_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.ducking_enabled = bool(enabled)
        self.save()

    def save_routing_rule(self, rule: RoutingRule) -> None:
        with self._lock:
            for index, current in enumerate(self.routing_rules):
                if current.name == rule.name:
                    self.routing_rules[index] = copy.deepcopy(rule)
                    break
            else:
                self.routing_rules.append(copy.deepcopy(rule))
        self.save()

    def delete_routing_rule(self, name: str) -> bool:
        with self._lock:
            before = len(self.routing_rules)
            self.routing_rules = [rule for rule in self.routing_rules if rule.name != name]
            changed = len(self.routing_rules) != before
        if changed:
            self.save()
        return changed

    def save_ducking_rule(self, rule: DuckingRule) -> None:
        with self._lock:
            for index, current in enumerate(self.ducking_rules):
                if current.name == rule.name:
                    self.ducking_rules[index] = copy.deepcopy(rule)
                    break
            else:
                self.ducking_rules.append(copy.deepcopy(rule))
        self.save()

    def delete_ducking_rule(self, name: str) -> bool:
        with self._lock:
            before = len(self.ducking_rules)
            self.ducking_rules = [rule for rule in self.ducking_rules if rule.name != name]
            changed = len(self.ducking_rules) != before
        if changed:
            self.save()
        return changed

    def trigger_patterns(self) -> List[str]:
        if not self.ducking_enabled:
            return []
        with self._lock:
            return [
                rule.trigger_pattern
                for rule in self.ducking_rules
                if rule.enabled and rule.trigger_pattern.strip()
            ]

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    @staticmethod
    def _find_output_device(outputs, pattern: str):
        for output in outputs:
            if _matches(getattr(output, "name", ""), pattern):
                return output
            device_id = str(getattr(output, "_device_id", "") or "")
            if pattern and pattern.lower() in device_id.lower():
                return output
        return None

    def apply_routing_rules(self, router) -> int:
        """Apply first matching routing rule per process and clear stale overrides."""
        apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        outputs = self.audio.get_sessions_for_mode(DisplayMode.MODE_OUTPUT)
        with self._lock:
            rules = [copy.deepcopy(rule) for rule in self.routing_rules if rule.enabled]
            enabled = self.routing_enabled

        desired: Dict[int, str] = {}
        if enabled:
            for app in apps:
                pid = int(getattr(app, "_process_id", 0) or 0)
                if pid <= 0:
                    continue
                for rule in rules:
                    if not _matches(getattr(app, "name", ""), rule.app_pattern):
                        continue
                    output = self._find_output_device(outputs, rule.device_pattern)
                    if output is None:
                        continue
                    device_id = str(getattr(output, "_device_id", "") or "")
                    if device_id:
                        desired[pid] = device_id
                    break

        changes = 0
        for pid, old_device in list(self._applied_routes.items()):
            if desired.get(pid) == old_device:
                continue
            try:
                router.clear_process_output(pid)
                changes += 1
            except Exception as exc:
                self.last_routing_error = str(exc)
                log.warning("Failed to clear route for pid=%d: %s", pid, exc)
            self._applied_routes.pop(pid, None)

        for pid, device_id in desired.items():
            if self._applied_routes.get(pid) == device_id:
                continue
            try:
                router.set_process_output(pid, device_id)
                self._applied_routes[pid] = device_id
                self.last_routing_error = ""
                changes += 1
                log.info("Applied app audio route pid=%d device=%s", pid, device_id)
            except Exception as exc:
                self.last_routing_error = str(exc)
                log.warning("Failed to route pid=%d: %s", pid, exc)
        return changes

    def clear_applied_routes(self, router) -> None:
        for pid in list(self._applied_routes):
            try:
                router.clear_process_output(pid)
            except Exception:
                log.debug("Failed to clear route pid=%d during shutdown", pid, exc_info=True)
            self._applied_routes.pop(pid, None)

    # ------------------------------------------------------------------
    # Ducking / recovery journal
    # ------------------------------------------------------------------
    @staticmethod
    def _session_key(item) -> str:
        identifier = str(getattr(item, "_session_identifier", "") or "")
        if identifier and not identifier.startswith("fallback:"):
            return f"id:{identifier}"
        path = str(getattr(item, "_process_path", "") or "").lower()
        name = _norm(getattr(item, "name", ""))
        return f"app:{path or name}"

    def _write_recovery(self, state: _DuckTargetState) -> None:
        with self._lock:
            self._recovery[state.key] = {
                "name": state.name,
                "baseline_volume": state.baseline_volume,
                "baseline_muted": state.baseline_muted,
                "last_applied_volume": state.last_applied_volume,
            }
        self.save()

    def _clear_recovery(self, key: str) -> None:
        with self._lock:
            if key not in self._recovery:
                return
            self._recovery.pop(key, None)
        self.save()

    def has_pending_recovery(self) -> bool:
        with self._lock:
            return bool(self._recovery)

    def recover_pending(self) -> int:
        """Restore crash journal only if the session is still at our ducked volume.

        If the user changed the volume after a crash, their new value wins and
        the stale journal is discarded rather than overwriting manual intent.
        """
        apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        by_key = {self._session_key(item): (index, item) for index, item in enumerate(apps)}
        restored = 0
        changed = False
        with self._lock:
            recovery = copy.deepcopy(self._recovery)

        for key, record in recovery.items():
            found = by_key.get(key)
            if found is None:
                continue
            index, item = found
            expected = record.get("last_applied_volume")
            current = int(getattr(item, "volume", 0))
            if expected is None or abs(current - int(expected)) <= 1:
                baseline = _clamp_int(record.get("baseline_volume", current), 0, 100)
                muted = bool(record.get("baseline_muted", getattr(item, "is_muted", False)))
                try:
                    self.audio.set_volume(
                        DisplayMode.MODE_APPLICATION,
                        index,
                        baseline,
                        muted,
                    )
                    restored += 1
                except Exception:
                    log.exception("Failed restoring duck recovery for %s", record.get("name", key))
                    continue
            with self._lock:
                self._recovery.pop(key, None)
            changed = True

        if changed:
            self.save()
        return restored

    @staticmethod
    def _active_rule_for_target(
        rules: Sequence[DuckingRule],
        target_name: str,
        trigger_levels: Dict[str, float],
    ) -> Optional[DuckingRule]:
        matches: List[DuckingRule] = []
        for rule in rules:
            if not rule.enabled or not rule.trigger_pattern or not rule.target_patterns:
                continue
            trigger_active = any(
                _matches(trigger_name, rule.trigger_pattern) and float(level) >= rule.threshold
                for trigger_name, level in trigger_levels.items()
            )
            if not trigger_active:
                continue
            if any(_matches(target_name, pattern) for pattern in rule.target_patterns):
                matches.append(rule)
        if not matches:
            return None
        # Strongest reduction wins. Deterministic secondary order keeps the
        # state machine stable if several triggers are active simultaneously.
        return max(matches, key=lambda rule: (rule.reduction_percent, -rule.attack_ms, rule.name))

    @staticmethod
    def _interpolate(start: int, target: int, elapsed: float, duration: float) -> int:
        if duration <= 0.0 or elapsed >= duration:
            return int(target)
        if elapsed <= 0.0:
            return int(start)
        fraction = elapsed / duration
        return int(round(start + (target - start) * fraction))

    def _manual_baseline_update(self, state: _DuckTargetState, item) -> None:
        if state.last_applied_volume is None:
            return
        current = int(getattr(item, "volume", state.last_applied_volume))
        if abs(current - state.last_applied_volume) <= 1:
            return

        # The current value changed without being written by this engine.
        # Interpret it as the user's desired *ducked* value and infer the
        # corresponding unducked baseline so release returns to user intent.
        if state.current_ratio > 0.001:
            baseline = int(round(current / state.current_ratio))
        else:
            baseline = current
        state.baseline_volume = _clamp_int(baseline, 0, 100)
        state.baseline_muted = bool(getattr(item, "is_muted", state.baseline_muted))
        state.last_applied_volume = current
        state.phase_start_volume = current
        state.phase_started_at = 0.0  # caller resets this to current tick
        self._write_recovery(state)
        log.info(
            "Ducking baseline followed manual change for %s -> %d%%",
            state.name,
            state.baseline_volume,
        )

    def tick_ducking(self, trigger_levels: Dict[str, float], now: float) -> int:
        apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        with self._lock:
            rules = [copy.deepcopy(rule) for rule in self.ducking_rules if rule.enabled]
            enabled = self.ducking_enabled
        if not enabled:
            return self.restore_all_ducked(now)

        changes = 0
        seen_keys = set()
        for index, item in enumerate(apps):
            key = self._session_key(item)
            seen_keys.add(key)
            rule = self._active_rule_for_target(rules, getattr(item, "name", ""), trigger_levels)
            state = self._duck_states.get(key)

            if state is not None:
                before_started = state.phase_started_at
                self._manual_baseline_update(state, item)
                if state.phase_started_at == 0.0 and before_started != 0.0:
                    state.phase_started_at = now

            if rule is not None:
                ratio = max(0.0, 1.0 - rule.reduction_percent / 100.0)
                if state is None:
                    current = _clamp_int(getattr(item, "volume", 0), 0, 100)
                    state = _DuckTargetState(
                        key=key,
                        name=str(getattr(item, "name", key)),
                        baseline_volume=current,
                        baseline_muted=bool(getattr(item, "is_muted", False)),
                        current_ratio=ratio,
                        phase="attack",
                        phase_started_at=now,
                        phase_start_volume=current,
                        phase_target_volume=int(round(current * ratio)),
                        phase_duration_s=rule.attack_ms / 1000.0,
                        release_ms=rule.release_ms,
                    )
                    self._duck_states[key] = state
                    self._write_recovery(state)
                else:
                    target = int(round(state.baseline_volume * ratio))
                    if state.phase == "release" or abs(ratio - state.current_ratio) > 1e-6 or target != state.phase_target_volume:
                        state.phase = "attack"
                        state.phase_started_at = now
                        state.phase_start_volume = _clamp_int(getattr(item, "volume", 0), 0, 100)
                        state.phase_target_volume = target
                        state.phase_duration_s = rule.attack_ms / 1000.0
                    state.current_ratio = ratio
                    state.release_ms = max(state.release_ms, rule.release_ms)

                desired = self._interpolate(
                    state.phase_start_volume,
                    state.phase_target_volume,
                    now - state.phase_started_at,
                    state.phase_duration_s,
                )
                if int(getattr(item, "volume", desired)) != desired:
                    self.audio.set_volume(
                        DisplayMode.MODE_APPLICATION,
                        index,
                        desired,
                        bool(getattr(item, "is_muted", False)),
                    )
                    changes += 1
                state.last_applied_volume = desired
                self._write_recovery(state)
                continue

            if state is None:
                continue

            if state.phase != "release":
                state.phase = "release"
                state.phase_started_at = now
                state.phase_start_volume = _clamp_int(getattr(item, "volume", 0), 0, 100)
                state.phase_target_volume = state.baseline_volume
                state.phase_duration_s = state.release_ms / 1000.0

            desired = self._interpolate(
                state.phase_start_volume,
                state.baseline_volume,
                now - state.phase_started_at,
                state.phase_duration_s,
            )
            if int(getattr(item, "volume", desired)) != desired:
                self.audio.set_volume(
                    DisplayMode.MODE_APPLICATION,
                    index,
                    desired,
                    state.baseline_muted,
                )
                changes += 1
            state.last_applied_volume = desired
            self._write_recovery(state)

            if desired == state.baseline_volume and (
                state.phase_duration_s <= 0.0
                or now - state.phase_started_at >= state.phase_duration_s
            ):
                self._duck_states.pop(key, None)
                self._clear_recovery(key)

        # Sessions that disappear remain in the recovery journal. If they are
        # still alive when VuNMix returns, recover_pending() restores only when
        # their current volume still equals our last applied value.
        return changes

    def restore_all_ducked(self, now: float = 0.0) -> int:
        apps = self.audio.get_sessions_for_mode(DisplayMode.MODE_APPLICATION)
        by_key = {self._session_key(item): (index, item) for index, item in enumerate(apps)}
        restored = 0
        for key, state in list(self._duck_states.items()):
            found = by_key.get(key)
            if found is None:
                continue
            index, item = found
            try:
                self.audio.set_volume(
                    DisplayMode.MODE_APPLICATION,
                    index,
                    state.baseline_volume,
                    state.baseline_muted,
                )
                restored += 1
                self._duck_states.pop(key, None)
                self._clear_recovery(key)
            except Exception:
                log.exception("Failed restoring ducked target %s", state.name)
        return restored
