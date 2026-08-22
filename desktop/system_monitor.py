"""
VuNMix System Monitor — Real-time PC hardware telemetry provider.

Reads CPU usage %, RAM %, Memory used/total MB, Network I/O KB/s,
and GPU utilization % & temperature (NVIDIA via NVML / DirectX fallback).
"""

import ctypes
import logging
import os
import time
from typing import Optional

import psutil

from protocol import PcStatsData

log = logging.getLogger(__name__)


class SystemMonitor:
    """Collects PC performance metrics at 1Hz without blocking."""

    def __init__(self):
        self._last_net_time = time.monotonic()
        self._last_net_bytes = self._get_net_bytes()
        self._nvml_initialized = False
        self._nvml_handle = None
        self._init_nvml()
        # Prime psutil cpu measurement
        psutil.cpu_percent(interval=None)

    def _init_nvml(self):
        """Try loading NVIDIA NVML for real-time GPU metrics if available."""
        try:
            # Common paths on Windows for nvml.dll
            for path in (
                "nvml.dll",
                os.path.expandvars(r"%SystemRoot%\System32\nvml.dll"),
                os.path.expandvars(r"%ProgramFiles%\NVIDIA Corporation\NVSMI\nvml.dll"),
            ):
                if os.path.exists(path) or path == "nvml.dll":
                    try:
                        nvml = ctypes.CDLL(path)
                        if nvml.nvmlInit_v2() == 0:
                            handle = ctypes.c_void_p()
                            if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                                self._nvml = nvml
                                self._nvml_handle = handle
                                self._nvml_initialized = True
                                log.info("NVIDIA NVML initialized for GPU telemetry.")
                                break
                    except Exception:
                        continue
        except Exception:
            self._nvml_initialized = False

    def _get_net_bytes(self):
        try:
            counters = psutil.net_io_counters()
            return counters.bytes_recv, counters.bytes_sent
        except Exception:
            return 0, 0

    def _get_gpu_metrics(self):
        """Read GPU load % and temperature (°C) via NVML if available."""
        if not self._nvml_initialized or not self._nvml_handle:
            return 0, 0
        try:
            # struct c_nvmlUtilization_t: uint32_t gpu, uint32_t memory
            class NvmlUtilization(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            util = NvmlUtilization()
            temp = ctypes.c_uint()
            gpu_load = 0
            gpu_temp = 0

            if self._nvml.nvmlDeviceGetUtilizationRates(self._nvml_handle, ctypes.byref(util)) == 0:
                gpu_load = int(util.gpu)
            if self._nvml.nvmlDeviceGetTemperature(self._nvml_handle, 0, ctypes.byref(temp)) == 0:
                gpu_temp = int(temp.value)

            return gpu_load, gpu_temp
        except Exception:
            return 0, 0

    def get_pc_stats(self) -> PcStatsData:
        """Capture a snapshot of system performance metrics."""
        now = time.monotonic()
        dt = max(0.1, now - self._last_net_time)

        # CPU
        try:
            cpu_usage = int(round(psutil.cpu_percent(interval=None)))
        except Exception:
            cpu_usage = 0

        # RAM
        try:
            mem = psutil.virtual_memory()
            ram_usage = int(round(mem.percent))
            ram_used_mb = int(mem.used // (1024 * 1024))
            ram_total_mb = int(mem.total // (1024 * 1024))
        except Exception:
            ram_usage, ram_used_mb, ram_total_mb = 0, 0, 0

        # Network
        try:
            recv_bytes, sent_bytes = self._get_net_bytes()
            prev_recv, prev_sent = self._last_net_bytes
            self._last_net_bytes = (recv_bytes, sent_bytes)
            self._last_net_time = now

            down_kbps = int(max(0, (recv_bytes - prev_recv) / dt / 1024.0))
            up_kbps = int(max(0, (sent_bytes - prev_sent) / dt / 1024.0))
        except Exception:
            down_kbps, up_kbps = 0, 0

        # GPU
        gpu_usage, gpu_temp = self._get_gpu_metrics()

        return PcStatsData(
            cpu_usage=min(100, max(0, cpu_usage)),
            cpu_temp=0,
            gpu_usage=min(100, max(0, gpu_usage)),
            gpu_temp=min(255, max(0, gpu_temp)),
            ram_usage=min(100, max(0, ram_usage)),
            ram_used_mb=min(65535, max(0, ram_used_mb)),
            ram_total_mb=min(65535, max(0, ram_total_mb)),
            net_down_kbps=min(65535, max(0, down_kbps)),
            net_up_kbps=min(65535, max(0, up_kbps)),
        )
