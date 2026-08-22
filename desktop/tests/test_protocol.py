import pathlib
import sys
import tempfile
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from config import AppConfig
from protocol import (
    Color,
    Command,
    DeviceSettings,
    AppIconChunk,
    AppIconMeta,
    PcStatsData,
    MediaInfoData,
    MediaControlData,
    FrameParser,
    MeterData,
    ModeStates,
    SessionData,
    SessionInfo,
    VolumeData,
    encode_frame,
)


class ProtocolTests(unittest.TestCase):
    def test_packed_struct_sizes_match_firmware(self):
        self.assertEqual(len(Color().pack()), 3)
        self.assertEqual(len(VolumeData().pack()), 2)
        self.assertEqual(len(MeterData().pack()), 2)
        self.assertEqual(len(SessionData().pack()), 32)
        self.assertEqual(len(SessionInfo().pack()), 5)
        self.assertEqual(len(DeviceSettings().pack()), 19)
        self.assertEqual(len(ModeStates().pack()), 6)
        self.assertEqual(len(AppIconMeta().pack()), 5)
        self.assertEqual(len(AppIconChunk(data=b"x" * 60).pack()), 63)
        self.assertEqual(len(PcStatsData().pack()), 13)
        self.assertEqual(len(MediaInfoData().pack()), 61)
        self.assertEqual(len(MediaControlData().pack()), 1)

    def test_frame_parser_handles_fragmentation_noise_and_multiple_frames(self):
        first = encode_frame(Command.OK)
        second = encode_frame(Command.VOLUME_CURR_CHANGE, VolumeData(volume=42).pack())
        parser = FrameParser()

        self.assertEqual(parser.feed(b"boot noise" + first[:3]), [])
        frames = parser.feed(first[3:] + second)

        self.assertEqual(frames[0], (Command.OK, b""))
        self.assertEqual(frames[1][0], Command.VOLUME_CURR_CHANGE)
        self.assertEqual(VolumeData.unpack(frames[1][1]).volume, 42)

    def test_frame_parser_recovers_after_bad_crc(self):
        damaged = bytearray(encode_frame(Command.MODE_STATES, ModeStates().pack()))
        damaged[-1] ^= 0xFF
        valid = encode_frame(Command.OK)

        self.assertEqual(FrameParser().feed(bytes(damaged) + valid), [(Command.OK, b"")])

    def test_utf8_name_is_not_split_mid_character(self):
        original = "A" * 28 + chr(0x1ED9)
        packed = SessionData(name=original).pack()
        decoded = SessionData.unpack(packed).name

        self.assertNotIn("\uFFFD", decoded)
        self.assertEqual(decoded, "A" * 28)

    def test_settings_are_clamped_to_wire_ranges(self):
        settings = DeviceSettings.from_config({
            "sleep_after_seconds": -10,
            "acceleration_percentage": 999,
            "led_brightness": 999,
            "clock_standby_minutes": -1,
            "volume_min_color": [-1, 300, 10],
        })
        unpacked = DeviceSettings.unpack(settings.pack())

        self.assertEqual(unpacked.sleep_after_seconds, 0)
        self.assertEqual(unpacked.acceleration_percentage, 100)
        self.assertEqual(unpacked.led_brightness, 255)
        self.assertEqual(unpacked.clock_standby_minutes, 0)
        self.assertEqual(unpacked.volume_min_color.to_list(), [0, 255, 10])

    def test_meter_levels_are_clamped(self):
        packed = MeterData(current=150, alternate=-4).pack()
        self.assertEqual(MeterData.unpack(packed), MeterData(100, 0))

    def test_config_round_trip_uses_atomic_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "config.json"
            expected = AppConfig(com_port="COM7", update_interval_ms=10)
            expected.save(str(path))
            loaded = AppConfig.load(str(path))

            self.assertEqual(loaded.com_port, "COM7")
            self.assertEqual(loaded.update_interval_ms, 50)
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
