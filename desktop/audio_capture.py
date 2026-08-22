"""Lightweight microphone peak capture for VuNMix Input mode."""

from array import array

import sounddevice as sd


class InputPeakMeter:
    """PortAudio capture stream exposing peak and stereo channel peak methods."""

    def __init__(self, device_index: int, channels: int, sample_rate: float):
        self._peak = 0.0
        self._peak_l = 0.0
        self._peak_r = 0.0
        self._channels = max(1, min(2, channels))
        self._stream = sd.RawInputStream(
            device=device_index,
            channels=self._channels,
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
            self._peak_l = 0.0
            self._peak_r = 0.0
            return
        if self._channels >= 2 and len(samples) >= 2:
            left_samples = samples[0::2]
            right_samples = samples[1::2]
            self._peak_l = min(1.0, max(abs(s) for s in left_samples) / 32768.0) if left_samples else 0.0
            self._peak_r = min(1.0, max(abs(s) for s in right_samples) / 32768.0) if right_samples else 0.0
            self._peak = max(self._peak_l, self._peak_r)
        else:
            self._peak = min(1.0, max(abs(sample) for sample in samples) / 32768.0)
            self._peak_l = self._peak
            self._peak_r = self._peak

    def GetPeakValue(self) -> float:
        return self._peak

    def GetChannelsPeakValues(self) -> tuple:
        return self._peak_l, self._peak_r

    def close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()


def find_input_capture_device(name: str):
    """Resolve a pycaw endpoint name to its preferred PortAudio device with robust fallback."""
    import re

    def clean_tokens(s: str) -> set:
        cleaned = re.sub(r'[\(\)\[\]\,\.\-\_\'\"\®\™]', ' ', s.casefold())
        return {w for w in cleaned.split() if w not in ('r', 'tm', 'audio', 'device', 'high', 'definition')}

    target_clean = " ".join(name.casefold().split())
    target_tokens = clean_tokens(name)

    matches = []
    default_wasapi = None
    default_any = None

    try:
        devices = sd.query_devices()
    except Exception:
        return None

    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        cand_name = str(device.get("name", ""))
        cand_clean = " ".join(cand_name.casefold().split())
        cand_tokens = clean_tokens(cand_name)
        try:
            host_name = str(sd.query_hostapis(device["hostapi"])["name"])
        except Exception:
            host_name = ""

        is_wasapi = 0 if host_name == "Windows WASAPI" else 1

        if default_wasapi is None and is_wasapi == 0:
            default_wasapi = (index, int(device["max_input_channels"]), float(device["default_samplerate"]))
        if default_any is None:
            default_any = (index, int(device["max_input_channels"]), float(device["default_samplerate"]))

        if cand_clean == target_clean:
            score = 0
        elif target_clean in cand_clean or cand_clean in target_clean:
            score = 1
        elif target_tokens and cand_tokens and (target_tokens.issubset(cand_tokens) or cand_tokens.issubset(target_tokens)):
            score = 2
        elif target_tokens and cand_tokens and len(target_tokens.intersection(cand_tokens)) > 0:
            score = 3
        else:
            continue

        matches.append((
            score,
            is_wasapi,
            index,
            int(device["max_input_channels"]),
            float(device["default_samplerate"]),
        ))

    if matches:
        matches.sort()
        _, _, index, channels, sample_rate = matches[0]
        return index, channels, sample_rate

    if default_wasapi is not None:
        return default_wasapi

    return default_any
