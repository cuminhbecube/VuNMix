import pathlib
import sys
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from audio_policy import (
    AudioPolicyRouter,
    IID_21H2,
    IID_DOWNLEVEL,
    MMDEVAPI_PREFIX,
    RENDER_INTERFACE_SUFFIX,
    SET_PERSISTED_ENDPOINT_VTBL_INDEX,
    routing_capability,
)


class AudioPolicyTests(unittest.TestCase):
    def test_supported_windows_builds_choose_expected_interface(self):
        old = routing_capability(17133)
        self.assertFalse(old.supported)

        rs4 = routing_capability(17134)
        self.assertTrue(rs4.supported)
        self.assertEqual(rs4.interface_iid, IID_DOWNLEVEL)

        before_21h2 = routing_capability(21389)
        self.assertEqual(before_21h2.interface_iid, IID_DOWNLEVEL)

        variant_21h2 = routing_capability(21390)
        self.assertTrue(variant_21h2.supported)
        self.assertEqual(variant_21h2.interface_iid, IID_21H2)

        win11 = routing_capability(22000)
        self.assertEqual(win11.interface_iid, IID_21H2)

    def test_device_id_is_encoded_like_windows_volume_mixer_policy(self):
        raw = "{0.0.0.00000000}.{ABCDEF01-2345-6789-ABCD-EF0123456789}"
        encoded = AudioPolicyRouter._policy_device_id(raw)
        self.assertEqual(encoded, f"{MMDEVAPI_PREFIX}{raw}{RENDER_INTERFACE_SUFFIX}")
        self.assertEqual(AudioPolicyRouter._policy_device_id(encoded), encoded)
        self.assertEqual(AudioPolicyRouter._policy_device_id(""), "")

    def test_vtable_slot_matches_iinspectable_plus_eartrumpet_layout(self):
        self.assertEqual(SET_PERSISTED_ENDPOINT_VTBL_INDEX, 25)


if __name__ == "__main__":
    unittest.main()
