"""Windows power-state monitor used by the VuNMix desktop controller."""

from __future__ import annotations

import logging
import threading

import win32api
import win32con
import win32gui


log = logging.getLogger(__name__)


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

        try:
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
        except Exception:
            # A power-notification helper must never take down the desktop app.
            log.exception("Power monitor message loop failed")
        finally:
            self.hwnd = None

    def _dispatch(self, callback, event_name: str):
        """Run power callbacks outside the Win32 window procedure.

        Windows expects WM_POWERBROADCAST handlers to return promptly. Serial
        I/O or USB teardown during suspend can otherwise block/re-enter the
        window procedure and destabilize the tray/Tk process.
        """
        if callback is None:
            return

        def invoke():
            try:
                callback()
            except Exception:
                log.exception("Power callback failed: %s", event_name)

        threading.Thread(
            target=invoke,
            daemon=True,
            name=f"Power-{event_name}",
        ).start()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            if wparam == win32con.PBT_APMSUSPEND:
                self._dispatch(self.on_sleep, "Suspend")
            elif wparam in {
                win32con.PBT_APMRESUMEAUTOMATIC,
                getattr(win32con, "PBT_APMRESUMESUSPEND", 0x0007),
                getattr(win32con, "PBT_APMRESUMECRITICAL", 0x0006),
            }:
                self._dispatch(self.on_resume, "Resume")
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
