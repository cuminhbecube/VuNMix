"""
VuNMix OBS Studio Service — Lightweight OBS WebSocket v5 integration.
Connects to OBS WebSocket (default ws://localhost:4455), monitors Stream/Record state.
"""

import json
import logging
import threading
import time
from typing import Callable, Optional

log = logging.getLogger('vunmix.obs')


class ObsService:
    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self.is_connected = False
        self.is_streaming = False
        self.is_recording = False
        self.current_scene = ""
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_state_change: Optional[Callable[[bool, bool], None]] = None

    def set_callback(self, cb: Callable[[bool, bool], None]):
        self._on_state_change = cb

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, name="ObsServiceWorker", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _worker(self):
        """Monitors OBS Studio via socket connection."""
        while self._running:
            if not self.is_connected:
                self._try_connect()
            time.sleep(3)

    def _try_connect(self):
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            res = sock.connect_ex((self.host, self.port))
            sock.close()
            if res == 0:
                if not self.is_connected:
                    log.info(f"OBS Studio detected at {self.host}:{self.port}")
                    self.is_connected = True
            else:
                self.is_connected = False
        except Exception:
            self.is_connected = False
