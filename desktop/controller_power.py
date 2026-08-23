"""Windows power-state monitor used by the VuNMix desktop controller."""

from __future__ import annotations

import threading

import win32api
import win32con
import win32gui


class PowerMonitor:
    """Deliver suspend/resume notifications from a hidden Win32 window."""

    def __init__(self, on_sleep, on_resume):
        self.on_sleep = on_sleep
        self.on_resume = on_resume
        self.hwnd = None
        self._thread = threading.Thread(
            target=self._run_message_loop,
            daemon=True,
            name="PowerMonitor",
        )
        self._thread.start()

    def _run_message_loop(self):
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = "VuNMixPowerMonitor"
        wc.hInstance = win32api.GetModuleHandle(None)

        try:
            win32gui.RegisterClass(wc)
        except win32gui.error:
            pass

        self.hwnd = win32gui.CreateWindow(
            "VuNMixPowerMonitor",
            "VuNMix Power Monitor",
            0,
            0,
            0,
            win32con.CW_USEDEFAULT,
            win32con.CW_USEDEFAULT,
            0,
            0,
            wc.hInstance,
            None,
        )
        win32gui.PumpMessages()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            if wparam == win32con.PBT_APMSUSPEND:
                if self.on_sleep:
                    self.on_sleep()
            elif wparam == win32con.PBT_APMRESUMEAUTOMATIC:
                if self.on_resume:
                    self.on_resume()
        elif msg == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def stop(self):
        if self.hwnd:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.hwnd = None
