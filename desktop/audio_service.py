"""
VuNMix Audio Service — Windows audio session management via pycaw.

Enumerates output devices, input devices, and per-app audio sessions.
Maps them to firmware's SessionData format for serial transport.
Listens for Windows volume changes and notifies the controller.
"""

import logging
import threading
import time
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import comtypes
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER

from pycaw.pycaw import (
    AudioUtilities,
    IAudioEndpointVolume,
    IAudioMeterInformation,
    ISimpleAudioVolume,
)

from ctypes import POINTER, HRESULT, c_wchar_p, c_uint32
from comtypes import IUnknown, GUID, COMMETHOD, CoCreateInstance, CLSCTX_ALL

class IPolicyConfig(IUnknown):
    _iid_ = GUID('{F8679F50-850A-41CF-9C72-430F290290C8}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetMixFormat'),
        COMMETHOD([], HRESULT, 'GetDeviceFormat'),
        COMMETHOD([], HRESULT, 'ResetDeviceFormat'),
        COMMETHOD([], HRESULT, 'SetDeviceFormat'),
        COMMETHOD([], HRESULT, 'GetProcessingPeriod'),
        COMMETHOD([], HRESULT, 'SetProcessingPeriod'),
        COMMETHOD([], HRESULT, 'GetShareMode'),
        COMMETHOD([], HRESULT, 'SetShareMode'),
        COMMETHOD([], HRESULT, 'GetPropertyValue'),
        COMMETHOD([], HRESULT, 'SetPropertyValue'),
        COMMETHOD([], HRESULT, 'SetDefaultEndpoint', (['in'], c_wchar_p, 'PCWSTR'), (['in'], c_uint32, 'role')),
        COMMETHOD([], HRESULT, 'SetEndpointVisibility')
    ]

from protocol import SessionData, VolumeData, DisplayMode
from audio_capture import InputPeakMeter, find_input_capture_device

log = logging.getLogger(__name__)


@dataclass
class AudioItem:
    """Internal representation of an audio device or session."""
    id: int            # Unique ID (hashed)
    name: str          # Display name (max 29 chars)
    volume: int        # 0-100
    is_muted: bool
    is_default: bool = False
    _process_id: int = 0
    _process_path: str = ""
    _device_id: str = ""
    _session_identifier: str = ""

    def to_session_data(self) -> SessionData:
        """Convert to firmware SessionData struct."""
        return SessionData(
            name=self.name[:29],
            data=VolumeData(
                id=self.id & 0x7F,
                is_default=self.is_default,
                volume=min(self.volume, 100),
                is_muted=self.is_muted,
            )
        )


class AudioService:
    """Manages Windows audio sessions and maps them to VuNMix protocol."""

    def __init__(self):
        self._output_devices: List[AudioItem] = []
        self._input_devices: List[AudioItem] = []
        self._app_sessions: List[AudioItem] = []
        self._stable_id_map: Dict[str, int] = {}
        self._favorite_apps = set()
        self._lock = threading.Lock()
        # pycaw/comtypes ultimately dispatches through ctypes.  The desktop
        # controller reaches it from SerialRead, AudioSync and AudioMeter, so
        # concurrent calls can crash the frozen process inside _ctypes.pyd.
        self._com_lock = threading.RLock()

        # Callbacks
        self.on_sessions_changed: Optional[Callable] = None

    @contextmanager
    def _com_scope(self):
        """Serialize all WASAPI/COM calls across desktop worker threads."""
        with self._com_lock:
            comtypes.CoInitialize()
            try:
                yield
            finally:
                comtypes.CoUninitialize()

    def set_favorite_apps(self, names):
        """Set favorite application names; favorites are sorted first."""
        normalized = {
            str(name).lower().removesuffix(".exe").strip()
            for name in names
            if str(name).strip()
        }
        with self._lock:
            self._favorite_apps = normalized
            self._app_sessions.sort(key=self._app_sort_key)

    def _app_sort_key(self, item: AudioItem):
        name = item.name.lower().removesuffix(".exe")
        return (0 if name in self._favorite_apps else 1, name)

    def refresh(self):
        """Refresh all audio devices and sessions from Windows."""
        with self._com_scope():
            self._refresh_output_devices()
            self._refresh_input_devices()
            self._refresh_app_sessions()

    def check_system_changes(self) -> bool:
        """Check if default devices have changed, requiring a full refresh."""
        with self._com_scope():
            try:
                # Check Output
                default_out = AudioUtilities.GetSpeakers()
                out_id = default_out.GetId() if default_out else None
                with self._lock:
                    current_default_out = next((d._device_id for d in self._output_devices if d.is_default), None)
                if out_id != current_default_out:
                    return True

                # Check Input
                default_in = AudioUtilities.GetMicrophone()
                in_id = default_in.GetId() if default_in else None
                with self._lock:
                    current_default_in = next((d._device_id for d in self._input_devices if d.is_default), None)
                return in_id != current_default_in
            except Exception:
                return False

    def get_sessions_for_mode(self, mode: int) -> List[AudioItem]:
        """Get audio items for the given display mode."""
        with self._lock:
            if mode == DisplayMode.MODE_OUTPUT:
                return list(self._output_devices)
            elif mode == DisplayMode.MODE_INPUT:
                return list(self._input_devices)
            elif mode == DisplayMode.MODE_APPLICATION:
                return list(self._app_sessions)
            elif mode == DisplayMode.MODE_GAME:
                return list(self._app_sessions)
            return []

    def get_session_count(self, mode: int) -> int:
        return len(self.get_sessions_for_mode(mode))

    def set_volume(self, mode: int, index: int, volume: int, is_muted: bool):
        """Apply volume change from hardware to Windows audio."""
        with self._com_scope():
            items = self.get_sessions_for_mode(mode)
            if index < 0 or index >= len(items):
                return
            item = items[index]
            vol_float = max(0.0, min(1.0, volume / 100.0))

            from pycaw.pycaw import AudioUtilities
            if item._device_id:
                try:
                    devices = AudioUtilities.GetAllDevices()
                    for d in devices:
                        if d.id == item._device_id:
                            endpoint_vol = d.EndpointVolume
                            if endpoint_vol:
                                endpoint_vol.SetMasterVolumeLevelScalar(vol_float, None)
                                endpoint_vol.SetMute(is_muted, None)
                                item.volume = volume
                                item.is_muted = is_muted
                            break
                except Exception as e:
                    log.error(f"Failed to set endpoint volume: {e}")
            elif item._process_id:
                try:
                    sessions = AudioUtilities.GetAllSessions()
                    for session in sessions:
                        try:
                            if self._session_matches(session, item):
                                vol_interface = session.SimpleAudioVolume
                                if vol_interface:
                                    vol_interface.SetMasterVolume(vol_float, None)
                                    vol_interface.SetMute(is_muted, None)
                                    item.volume = volume
                                    item.is_muted = is_muted
                                break
                        except Exception:
                            pass
                except Exception as e:
                    log.error(f"Failed to set session volume: {e}")

    def set_default_device(self, mode: int, index: int):
        """Mark a device as default and apply to Windows."""
        succeeded = False
        selected = None
        with self._com_scope():
            items = self.get_sessions_for_mode(mode)
            if index < 0 or index >= len(items) or not items[index]._device_id:
                return

            selected = items[index]
            try:
                CLSID_PolicyConfigClient = GUID('{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}')
                policyConfig = CoCreateInstance(CLSID_PolicyConfigClient, IPolicyConfig, CLSCTX_ALL)
                policyConfig.SetDefaultEndpoint(selected._device_id, 0)
                policyConfig.SetDefaultEndpoint(selected._device_id, 1)
                policyConfig.SetDefaultEndpoint(selected._device_id, 2)
                succeeded = True
                log.info("Set Windows default audio device to %s", selected.name)
            except Exception as e:
                log.error("Failed to set Windows default device: %s", e)

        if succeeded and selected is not None:
            with self._lock:
                target = self._output_devices if mode == DisplayMode.MODE_OUTPUT else self._input_devices
                for item in target:
                    item.is_default = item._device_id == selected._device_id

    def _refresh_output_devices(self):
        """Enumerate output audio devices."""
        with self._lock:
            self._output_devices.clear()
        try:
            from pycaw.pycaw import AudioUtilities
            
            default_id = None
            default_speaker = AudioUtilities.GetSpeakers()
            if default_speaker:
                default_id = default_speaker.id

            devices = AudioUtilities.GetAllDevices()
            temp_devices = []
            for d in devices:
                if str(d.state) == 'AudioDeviceState.Active' and d.id.startswith('{0.0.0.'):
                    try:
                        endpoint_vol = d.EndpointVolume
                        if not endpoint_vol:
                            continue

                        vol = int(endpoint_vol.GetMasterVolumeLevelScalar() * 100)
                        muted = bool(endpoint_vol.GetMute())
                        is_default = (d.id == default_id)

                        item = AudioItem(
                            id=0,
                            name=d.FriendlyName[:29],
                            volume=vol,
                            is_muted=muted,
                            is_default=is_default,
                            _device_id=d.id,
                        )
                        temp_devices.append(item)
                    except Exception as e:
                        log.debug(f"Skipping output device {d.FriendlyName}: {e}")

            temp_devices.sort(key=lambda x: x.name.lower())
            self._assign_protocol_ids(temp_devices, lambda item: item._device_id)
            
            with self._lock:
                self._output_devices.extend(temp_devices)
        except Exception as e:
            log.error(f"Failed to enumerate output devices: {e}")

    def _refresh_input_devices(self):
        """Enumerate input (microphone) devices."""
        with self._lock:
            self._input_devices.clear()
        try:
            from pycaw.pycaw import AudioUtilities
            
            default_id = None
            default_mic = AudioUtilities.GetMicrophone()
            if default_mic:
                default_id = default_mic.GetId()

            devices = AudioUtilities.GetAllDevices()
            temp_devices = []
            for d in devices:
                if str(d.state) == 'AudioDeviceState.Active' and d.id.startswith('{0.0.1.'):
                    try:
                        endpoint_vol = d.EndpointVolume
                        if not endpoint_vol:
                            continue

                        vol = int(endpoint_vol.GetMasterVolumeLevelScalar() * 100)
                        muted = bool(endpoint_vol.GetMute())
                        is_default = (d.id == default_id)

                        item = AudioItem(
                            id=0,
                            name=d.FriendlyName[:29],
                            volume=vol,
                            is_muted=muted,
                            is_default=is_default,
                            _device_id=d.id,
                        )
                        temp_devices.append(item)
                    except Exception as e:
                        log.debug(f"Skipping input device {d.FriendlyName}: {e}")

            temp_devices.sort(key=lambda x: x.name.lower())
            self._assign_protocol_ids(temp_devices, lambda item: item._device_id)
            
            with self._lock:
                self._input_devices.extend(temp_devices)
        except Exception as e:
            log.error(f"Failed to enumerate input devices: {e}")

    def _refresh_app_sessions(self):
        """Enumerate per-application audio sessions."""
        with self._lock:
            self._app_sessions.clear()
        try:
            sessions = AudioUtilities.GetAllSessions()
            temp_sessions = []
            fallback_occurrences: Dict[tuple, int] = {}
            for session in sessions:
                try:
                    pid = session.ProcessId
                    if pid == 0 or pid is None:
                        continue
                    proc = session.Process
                    if proc is None:
                        continue
                    try:
                        process_path = proc.exe()
                    except Exception:
                        process_path = ""
                    name = proc.name()
                    if name.lower().endswith('.exe'):
                        name = name[:-4]
                    name = name[:29]
                    identifier = self._get_session_identifier(session)
                    if not identifier:
                        fallback_key = (pid, name)
                        occurrence = fallback_occurrences.get(fallback_key, 0)
                        fallback_occurrences[fallback_key] = occurrence + 1
                        identifier = f"fallback:{pid}:{name}:{occurrence}"

                    vol_interface = session.SimpleAudioVolume
                    vol = int(vol_interface.GetMasterVolume() * 100)
                    muted = bool(vol_interface.GetMute())

                    item = AudioItem(
                        id=0,
                        name=name,
                        volume=vol,
                        is_muted=muted,
                        _process_id=pid,
                        _process_path=process_path,
                        _session_identifier=identifier,
                    )
                    temp_sessions.append(item)
                except Exception as e:
                    log.debug(f"Skipping session: {e}")
                    
            temp_sessions.sort(key=self._app_sort_key)
            self._assign_protocol_ids(temp_sessions, lambda item: item._session_identifier)
            with self._lock:
                self._app_sessions.extend(temp_sessions)
        except Exception as e:
            log.error(f"Failed to enumerate app sessions: {e}")

    def read_current_volume(self, mode: int, index: int) -> Optional[VolumeData]:
        """Read the current volume from Windows for a specific session."""
        with self._com_scope():
            items = self.get_sessions_for_mode(mode)
            if index < 0 or index >= len(items):
                return None
            item = items[index]

            from pycaw.pycaw import AudioUtilities
            if item._device_id:
                try:
                    devices = AudioUtilities.GetAllDevices()
                    for d in devices:
                        if d.id == item._device_id:
                            endpoint_vol = d.EndpointVolume
                            if endpoint_vol:
                                vol = int(endpoint_vol.GetMasterVolumeLevelScalar() * 100)
                                muted = bool(endpoint_vol.GetMute())
                                item.volume = vol
                                item.is_muted = muted
                            break
                except Exception:
                    pass
            elif item._process_id:
                try:
                    sessions = AudioUtilities.GetAllSessions()
                    for session in sessions:
                        try:
                            if self._session_matches(session, item):
                                vol_interface = session.SimpleAudioVolume
                                if vol_interface:
                                    vol = int(vol_interface.GetMasterVolume() * 100)
                                    muted = bool(vol_interface.GetMute())
                                    item.volume = vol
                                    item.is_muted = muted
                                break
                        except Exception:
                            pass
                except Exception:
                    pass

            return item.to_session_data().data

    def create_peak_meter(self, mode: int, index: int):
        """Create an IAudioMeterInformation interface in the calling thread."""
        with self._com_lock:
            items = self.get_sessions_for_mode(mode)
            if index < 0 or index >= len(items):
                return None
            item = items[index]

            if item._device_id:
                if mode == DisplayMode.MODE_INPUT:
                    device = find_input_capture_device(item.name)
                    if device is not None:
                        device_index, channels, sample_rate = device
                        return InputPeakMeter(device_index, channels, sample_rate)

                for device in AudioUtilities.GetAllDevices():
                    if device.id == item._device_id:
                        interface = device._dev.Activate(
                            IAudioMeterInformation._iid_,
                            CLSCTX_ALL,
                            None,
                        )
                        return cast(interface, POINTER(IAudioMeterInformation))
                return None

            for session in AudioUtilities.GetAllSessions():
                if self._session_matches(session, item):
                    return session._ctl.QueryInterface(IAudioMeterInformation)
            return None

    def read_peak_meter(self, meter) -> float:
        with self._com_lock:
            if meter is None:
                return 0.0
            try:
                val = float(meter.GetPeakValue())
                return max(0.0, min(1.0, val))
            except Exception:
                return 0.0

    def read_stereo_peak_meter(self, meter) -> Tuple[float, float]:
        with self._com_lock:
            if meter is None:
                return 0.0, 0.0
            try:
                if hasattr(meter, "GetChannelsPeakValues"):
                    return meter.GetChannelsPeakValues()
                count = meter.GetMeteringChannelCount()
                if count >= 2:
                    import ctypes
                    arr = (ctypes.c_float * count)()
                    meter.GetChannelsPeakValues(count, arr)
                    return max(0.0, min(1.0, float(arr[0]))), max(0.0, min(1.0, float(arr[1])))
                val = float(meter.GetPeakValue())
                clamped = max(0.0, min(1.0, val))
                return clamped, clamped
            except Exception:
                try:
                    val = float(meter.GetPeakValue())
                    clamped = max(0.0, min(1.0, val))
                    return clamped, clamped
                except Exception:
                    return 0.0, 0.0

    def close_peak_meter(self, meter):
        with self._com_lock:
            if meter is None:
                return
            try:
                close = getattr(meter, "close", None)
                if close is not None:
                    close()
            except Exception:
                pass

    @staticmethod
    def _get_session_identifier(session) -> str:
        for attribute in ("InstanceIdentifier", "Identifier"):
            try:
                value = getattr(session, attribute, "")
                if value:
                    return str(value)
            except Exception:
                continue
        return ""

    @classmethod
    def _session_matches(cls, session, item: AudioItem) -> bool:
        identifier = cls._get_session_identifier(session)
        if item._session_identifier and not item._session_identifier.startswith("fallback:") and identifier:
            return identifier == item._session_identifier
        if session.ProcessId != item._process_id:
            return False
        try:
            process = session.Process
            name = process.name() if process else ""
            if name.lower().endswith(".exe"):
                name = name[:-4]
            return name[:29] == item.name
        except Exception:
            return False

    def _assign_protocol_ids(self, items: List[AudioItem], key_getter):
        """Map stable Windows identifiers into persistent, unique non-zero 7-bit IDs."""
        with self._lock:
            current_keys = {str(key_getter(item) or item.name) for item in items}
            if len(self._stable_id_map) > 120:
                self._stable_id_map = {k: v for k, v in self._stable_id_map.items() if k in current_keys}

            used_ids = set(self._stable_id_map.values())
            for item in items:
                key = str(key_getter(item) or item.name)
                if key in self._stable_id_map:
                    item.id = self._stable_id_map[key]
                else:
                    candidate = (zlib.crc32(key.encode("utf-8", errors="replace")) % 127) + 1
                    start = candidate
                    while candidate in used_ids:
                        candidate = 1 if candidate == 127 else candidate + 1
                        if candidate == start:
                            break
                    self._stable_id_map[key] = candidate
                    used_ids.add(candidate)
                    item.id = candidate
