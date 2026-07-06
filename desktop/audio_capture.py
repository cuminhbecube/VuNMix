"""Lightweight microphone peak capture for VuNMix Input mode."""

from array import array

import sounddevice as sd


class InputPeakMeter:
    """PortAudio capture stream exposing the same peak method as WASAPI."""

    def __init__(self, device_index: int, channels: int, sample_rate: float):
        self._peak = 0.0
        self._stream = sd.RawInputStream(
            device=device_index,
            channels=max(1, min(2, channels)),
            samplerate=sample_rate,
            dtype="int16",
            blocksize=0,
            latency="low",
            callback=self._on_audio,
        )
        self._stream.start()

    def _on_audio(self, indata, _frames, _time_info, _status):
        samples = array("h")
        samples.frombytes(bytes(indata))
        if not samples:
            self._peak = 0.0
            return
        self._peak = min(1.0, max(abs(sample) for sample in samples) / 32768.0)

    def GetPeakValue(self) -> float:
        return self._peak

    def close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()


def find_input_capture_device(name: str):
    """Resolve a pycaw endpoint name to its preferred PortAudio device."""
    target = " ".join(name.casefold().split())
    matches = []
    for index, device in enumerate(sd.query_devices()):
        if int(device["max_input_channels"]) <= 0:
            continue
        candidate = " ".join(str(device["name"]).casefold().split())
        if candidate != target:
            continue
        host_name = str(sd.query_hostapis(device["hostapi"])["name"])
        # WASAPI maps most directly to the endpoint selected through pycaw.
        priority = 0 if host_name == "Windows WASAPI" else 1
        matches.append((
            priority,
            index,
            int(device["max_input_channels"]),
            float(device["default_samplerate"]),
        ))
    if not matches:
        return None
    _, index, channels, sample_rate = min(matches)
    return index, channels, sample_rate
