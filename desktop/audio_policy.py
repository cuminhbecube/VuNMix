"""Windows per-process output routing for VuNMix.

Windows 10 1803+ exposes the same internal AudioPolicyConfig runtime class used
by the Settings Volume Mixer and EarTrumpet.  The ABI is undocumented, so this
module keeps it isolated behind a small capability checked interface.

References used for the ABI layout:
- EarTrumpet IAudioPolicyConfigFactory downlevel IID
- EarTrumpet 21H2+ IAudioPolicyConfigFactory variant IID
- SetPersistedDefaultAudioEndpoint(processId, flow, role, HSTRING deviceId)
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Optional


log = logging.getLogger("vunmix.audio_policy")

WINDOWS_10_1803_BUILD = 17134
WINDOWS_21H2_INTERFACE_BUILD = 21390
RUNTIME_CLASS = "Windows.Media.Internal.AudioPolicyConfig"

IID_DOWNLEVEL = "2a59116d-6c4f-45e0-a74f-707e3fef9258"
IID_21H2 = "ab3d4648-e242-459f-b02f-541c70306324"

# EDataFlow / ERole values from mmdeviceapi.h.
E_RENDER = 0
E_CONSOLE = 0
E_MULTIMEDIA = 1

# Device interface suffix used by Windows AudioPolicyConfig for render devices.
MMDEVAPI_PREFIX = r"\\?\SWD#MMDEVAPI#"
RENDER_INTERFACE_SUFFIX = "#{e6327cad-dcec-4949-ae8a-991e976a79d2}"

# IInspectable contributes 6 vtable entries after IUnknown. EarTrumpet's
# interface declaration has 19 methods before SetPersistedDefaultAudioEndpoint.
SET_PERSISTED_ENDPOINT_VTBL_INDEX = 6 + 19

RO_INIT_MULTITHREADED = 1
RPC_E_CHANGED_MODE = 0x80010106


class AudioRoutingUnavailable(RuntimeError):
    pass


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        raw = uuid.UUID(value).bytes_le
        guid = cls()
        ctypes.memmove(ctypes.byref(guid), raw, 16)
        return guid


@dataclass(frozen=True)
class RoutingCapability:
    supported: bool
    build: int
    interface_iid: str
    reason: str = ""


def windows_build_number() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def routing_capability(build: Optional[int] = None) -> RoutingCapability:
    build = windows_build_number() if build is None else int(build)
    if sys.platform != "win32" and build == 0:
        return RoutingCapability(False, build, IID_DOWNLEVEL, "Windows only")
    iid = IID_21H2 if build >= WINDOWS_21H2_INTERFACE_BUILD else IID_DOWNLEVEL
    if build < WINDOWS_10_1803_BUILD:
        return RoutingCapability(
            False,
            build,
            iid,
            f"Windows build {WINDOWS_10_1803_BUILD}+ required",
        )
    return RoutingCapability(True, build, iid)


def _failed(hr: int) -> bool:
    return int(hr) < 0


def _hex_hresult(hr: int) -> str:
    return f"0x{ctypes.c_uint32(int(hr)).value:08X}"


class AudioPolicyRouter:
    """Apply/clear persisted render endpoint overrides for a process ID."""

    def __init__(self, *, build: Optional[int] = None):
        self.capability = routing_capability(build)
        if not self.capability.supported:
            raise AudioRoutingUnavailable(self.capability.reason)

    @staticmethod
    def _policy_device_id(device_id: str) -> str:
        device_id = str(device_id or "").strip()
        if not device_id:
            return ""
        if device_id.startswith(MMDEVAPI_PREFIX):
            return device_id
        return f"{MMDEVAPI_PREFIX}{device_id}{RENDER_INTERFACE_SUFFIX}"

    def set_process_output(self, process_id: int, device_id: Optional[str]) -> None:
        """Persist an app render override for Console + Multimedia roles.

        ``device_id=None`` clears the process override and lets Windows use its
        normal/default routing again.
        """
        process_id = int(process_id)
        if process_id <= 0:
            raise ValueError("process_id must be positive")
        self._invoke(process_id, device_id, E_CONSOLE)
        self._invoke(process_id, device_id, E_MULTIMEDIA)

    def clear_process_output(self, process_id: int) -> None:
        self.set_process_output(process_id, None)

    def _invoke(self, process_id: int, device_id: Optional[str], role: int) -> None:
        if sys.platform != "win32":
            raise AudioRoutingUnavailable("Windows only")

        combase = ctypes.WinDLL("combase.dll")
        hstring_type = ctypes.c_void_p
        combase.WindowsCreateString.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.POINTER(hstring_type),
        ]
        combase.WindowsCreateString.restype = ctypes.c_long
        combase.WindowsDeleteString.argtypes = [hstring_type]
        combase.WindowsDeleteString.restype = ctypes.c_long
        combase.RoGetActivationFactory.argtypes = [
            hstring_type,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        combase.RoGetActivationFactory.restype = ctypes.c_long
        combase.RoInitialize.argtypes = [ctypes.c_uint32]
        combase.RoInitialize.restype = ctypes.c_long
        combase.RoUninitialize.argtypes = []
        combase.RoUninitialize.restype = None

        initialized = False
        runtime_hstring = hstring_type()
        device_hstring = hstring_type()
        factory = ctypes.c_void_p()

        init_hr = int(combase.RoInitialize(RO_INIT_MULTITHREADED))
        init_code = ctypes.c_uint32(init_hr).value
        if not _failed(init_hr):
            initialized = True
        elif init_code != RPC_E_CHANGED_MODE:
            raise AudioRoutingUnavailable(
                f"RoInitialize failed {_hex_hresult(init_hr)}"
            )

        try:
            hr = int(
                combase.WindowsCreateString(
                    RUNTIME_CLASS,
                    len(RUNTIME_CLASS),
                    ctypes.byref(runtime_hstring),
                )
            )
            if _failed(hr):
                raise AudioRoutingUnavailable(
                    f"WindowsCreateString(runtime) failed {_hex_hresult(hr)}"
                )

            iid = GUID.from_string(self.capability.interface_iid)
            hr = int(
                combase.RoGetActivationFactory(
                    runtime_hstring,
                    ctypes.byref(iid),
                    ctypes.byref(factory),
                )
            )
            if _failed(hr) or not factory.value:
                raise AudioRoutingUnavailable(
                    f"AudioPolicyConfig activation failed {_hex_hresult(hr)}"
                )

            policy_id = self._policy_device_id(device_id or "")
            if policy_id:
                hr = int(
                    combase.WindowsCreateString(
                        policy_id,
                        len(policy_id),
                        ctypes.byref(device_hstring),
                    )
                )
                if _failed(hr):
                    raise AudioRoutingUnavailable(
                        f"WindowsCreateString(device) failed {_hex_hresult(hr)}"
                    )

            vtbl = ctypes.cast(
                factory,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
            ).contents
            method_address = vtbl[SET_PERSISTED_ENDPOINT_VTBL_INDEX]
            winfunctype = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
            set_endpoint_type = winfunctype(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
            )
            set_endpoint = set_endpoint_type(method_address)
            hr = int(
                set_endpoint(
                    factory,
                    ctypes.c_uint32(process_id),
                    E_RENDER,
                    int(role),
                    device_hstring,
                )
            )
            if _failed(hr):
                raise OSError(
                    f"SetPersistedDefaultAudioEndpoint failed {_hex_hresult(hr)}"
                )
        finally:
            if factory.value:
                try:
                    vtbl = ctypes.cast(
                        factory,
                        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
                    ).contents
                    release_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
                        ctypes.c_ulong,
                        ctypes.c_void_p,
                    )
                    release_type(vtbl[2])(factory)
                except Exception:
                    pass
            if device_hstring.value:
                combase.WindowsDeleteString(device_hstring)
            if runtime_hstring.value:
                combase.WindowsDeleteString(runtime_hstring)
            if initialized:
                combase.RoUninitialize()


def smoke_test_current_process() -> bool:
    """Activate the policy backend and clear this process' persisted route."""
    if not routing_capability().supported:
        return False
    router = AudioPolicyRouter()
    router.clear_process_output(os.getpid())
    return True
