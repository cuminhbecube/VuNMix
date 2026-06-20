"""
VuNMix Audio Service — Windows audio session management via pycaw.

Enumerates output devices, input devices, and per-app audio sessions.
Maps them to firmware's SessionData format for serial transport.
Listens for Windows volume changes and notifies the controller.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import comtypes
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER

from pycaw.pycaw import (
    AudioUtilities,
    IAudioEndpointVolume,
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

log = logging.getLogger(__name__)


@dataclass
class AudioItem:
    """Internal representation of an audio device or session."""
    id: int            # Unique ID (hashed)
    name: str          # Display name (max 29 chars)
    volume: int        # 0-100
    is_muted: bool
    is_default: bool = False
    # Internal reference for pycaw
    _endpoint_vol: Optional[object] = field(default=None, repr=False)
    _session_vol: Optional[object] = field(default=None, repr=False)
    _process_id: int = 0
    _device_id: str = ""

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
        self._lock = threading.Lock()

        # Callbacks
        self.on_sessions_changed: Optional[Callable] = None

    def refresh(self):
        """Refresh all audio devices and sessions from Windows."""
        comtypes.CoInitialize()
        try:
            self._refresh_output_devices()
            self._refresh_input_devices()
            self._refresh_app_sessions()
        finally:
            comtypes.CoUninitialize()

    def check_system_changes(self) -> bool:
        """Check if default devices have changed, requiring a full refresh."""
        try:
            from pycaw.pycaw import AudioUtilities
            
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
            if in_id != current_default_in:
                return True
                
            return False
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
        comtypes.CoInitialize()
        try:
            items = self.get_sessions_for_mode(mode)
            if index < 0 or index >= len(items):
                return
            item = items[index]
            vol_float = max(0.0, min(1.0, volume / 100.0))

            if item._endpoint_vol is not None:
                try:
                    item._endpoint_vol.SetMasterVolumeLevelScalar(vol_float, None)
                    item._endpoint_vol.SetMute(is_muted, None)
                    item.volume = volume
                    item.is_muted = is_muted
                except Exception as e:
                    log.error(f"Failed to set endpoint volume: {e}")
            elif item._session_vol is not None:
                try:
                    item._session_vol.SetMasterVolume(vol_float, None)
                    item._session_vol.SetMute(is_muted, None)
                    item.volume = volume
                    item.is_muted = is_muted
                except Exception as e:
                    log.error(f"Failed to set session volume: {e}")
        finally:
            comtypes.CoUninitialize()

    def set_default_device(self, mode: int, index: int):
        """Mark a device as default and apply to Windows."""
        items = self.get_sessions_for_mode(mode)
        for i, item in enumerate(items):
            item.is_default = (i == index)
            if i == index and item._device_id:
                try:
                    comtypes.CoInitialize()
                    CLSID_PolicyConfigClient = GUID('{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}')
                    policyConfig = CoCreateInstance(CLSID_PolicyConfigClient, IPolicyConfig, CLSCTX_ALL)
                    policyConfig.SetDefaultEndpoint(item._device_id, 0)
                    policyConfig.SetDefaultEndpoint(item._device_id, 1)
                    policyConfig.SetDefaultEndpoint(item._device_id, 2)
                    log.info(f"Set Windows default audio device to {item.name}")
                except Exception as e:
                    log.error(f"Failed to set Windows default device: {e}")
                finally:
                    comtypes.CoUninitialize()

    def _refresh_output_devices(self):
        """Enumerate output audio devices."""
        with self._lock:
            self._output_devices.clear()
        try:
            from pycaw.pycaw import AudioUtilities
            
            default_id = None
            default_speaker = AudioUtilities.GetSpeakers()
            if default_speaker:
                default_id = default_speaker.GetId()

            devices = AudioUtilities.GetAllDevices()
            out_idx = 1
            temp_devices = []
            for d in devices:
                if str(d.state) == 'AudioDeviceState.Active' and d.id.startswith('{0.0.0.'):
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
                        _endpoint_vol=endpoint_vol,
                        _device_id=d.id,
                    )
                    temp_devices.append(item)
                    
            temp_devices.sort(key=lambda x: x.name.lower())
            for i, item in enumerate(temp_devices):
                item.id = i + 1
            
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
            in_idx = 101 # Offset to avoid collision with output ids if needed
            temp_devices = []
            for d in devices:
                if str(d.state) == 'AudioDeviceState.Active' and d.id.startswith('{0.0.1.'):
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
                        _endpoint_vol=endpoint_vol,
                        _device_id=d.id,
                    )
                    temp_devices.append(item)
                    
            temp_devices.sort(key=lambda x: x.name.lower())
            for i, item in enumerate(temp_devices):
                item.id = in_idx + i
            
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
            for session in sessions:
                if session.Process is None:
                    continue
                try:
                    vol_interface = session.SimpleAudioVolume
                    vol = int(vol_interface.GetMasterVolume() * 100)
                    muted = bool(vol_interface.GetMute())
                    pid = session.Process.pid
                    name = session.Process.name()
                    # Remove .exe extension for cleaner display
                    if name.lower().endswith('.exe'):
                        name = name[:-4]
                    # Truncate to 29 chars (firmware limit)
                    name = name[:29]
                    item = AudioItem(
                        id=pid & 0x7F,
                        name=name,
                        volume=vol,
                        is_muted=muted,
                        _session_vol=vol_interface,
                        _process_id=pid,
                    )
                    temp_sessions.append(item)
                except Exception as e:
                    log.debug(f"Skipping session: {e}")
                    
            temp_sessions.sort(key=lambda x: x.name.lower())
            with self._lock:
                self._app_sessions.extend(temp_sessions)
        except Exception as e:
            log.error(f"Failed to enumerate app sessions: {e}")

    def read_current_volume(self, mode: int, index: int) -> Optional[VolumeData]:
        """Read the current volume from Windows for a specific session."""
        comtypes.CoInitialize()
        try:
            items = self.get_sessions_for_mode(mode)
            if index < 0 or index >= len(items):
                return None
            item = items[index]

            if item._endpoint_vol is not None:
                try:
                    vol = int(item._endpoint_vol.GetMasterVolumeLevelScalar() * 100)
                    muted = bool(item._endpoint_vol.GetMute())
                    item.volume = vol
                    item.is_muted = muted
                except Exception:
                    pass
            elif item._session_vol is not None:
                try:
                    vol = int(item._session_vol.GetMasterVolume() * 100)
                    muted = bool(item._session_vol.GetMute())
                    item.volume = vol
                    item.is_muted = muted
                except Exception:
                    pass

            return item.to_session_data().data
        finally:
            comtypes.CoUninitialize()
