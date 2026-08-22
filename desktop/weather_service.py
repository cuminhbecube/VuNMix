"""
VuNMix Weather Service — Fetches lightweight real-time weather & temperature for Clock Standby.
Uses Open-Meteo free public API (no API key required).
"""

import json
import logging
import threading
import time
import urllib.request
from typing import Optional, Tuple

log = logging.getLogger('vunmix.weather')

# Weather code mapping to LVGL symbol / short text
# WMO Weather interpretation codes (WW)
WEATHER_DESCRIPTIONS = {
    0: ("☀️", "Clear"),
    1: ("🌤️", "Mainly Clear"),
    2: ("⛅", "Partly Cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Depositing Rime Fog"),
    51: ("🌦️", "Light Drizzle"),
    53: ("🌦️", "Moderate Drizzle"),
    55: ("🌧️", "Dense Drizzle"),
    61: ("🌧️", "Slight Rain"),
    63: ("🌧️", "Moderate Rain"),
    65: ("🌧️", "Heavy Rain"),
    71: ("🌨️", "Slight Snow"),
    73: ("🌨️", "Moderate Snow"),
    75: ("❄️", "Heavy Snow"),
    80: ("🌦️", "Rain Showers"),
    81: ("🌧️", "Heavy Showers"),
    82: ("⛈️", "Violent Showers"),
    95: ("⚡", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm w/ Hail"),
}


class WeatherService:
    def __init__(self, latitude: float = 21.0285, longitude: float = 105.8542, city: str = "Hanoi"):
        self.latitude = latitude
        self.longitude = longitude
        self.city = city
        self._temp_c: int = 28
        self._weather_code: int = 0
        self._last_fetch: float = 0
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, name="WeatherServiceWorker", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def get_weather(self) -> Tuple[int, int, str]:
        """Returns (temp_c, weather_code, city)."""
        return self._temp_c, self._weather_code, self.city

    def _worker(self):
        while self._running:
            now = time.monotonic()
            if now - self._last_fetch >= 900 or self._last_fetch == 0:  # Every 15 minutes
                self._fetch()
                self._last_fetch = now
            time.sleep(10)

    def _fetch(self):
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={self.latitude}&longitude={self.longitude}&current=temperature_2m,weather_code"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "VuNMix-Desk/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    current = data.get("current", {})
                    self._temp_c = int(round(current.get("temperature_2m", 28)))
                    self._weather_code = int(current.get("weather_code", 0))
                    log.info(f"Weather updated: {self._temp_c}°C, code {self._weather_code} ({self.city})")
        except Exception as e:
            log.debug(f"Weather fetch failed: {e}")
