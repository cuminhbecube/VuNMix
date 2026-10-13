"""Update Center compatibility never assumes unknown firmware is safe."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from update_center import describe_device_update


class UpdateCenterModelTests(unittest.TestCase):
    def test_matching_versions_support_all_16_clocks(self):
        status = describe_device_update("0.4.24", "v0.4.24", True)
        self.assertEqual(status.compatible_clock_styles, 16)
        self.assertIn("aligned", status.status)

    def test_old_firmware_requires_update_for_extra_clocks(self):
        status = describe_device_update("0.4.24", "v0.4.20", True)
        self.assertEqual(status.compatible_clock_styles, 8)
        self.assertIn("8–15", status.status)

    def test_unknown_and_disconnected_firmware_not_assumed_compatible(self):
        self.assertIsNone(describe_device_update("v0.4.24", "unknown", True).compatible_clock_styles)
        self.assertIsNone(describe_device_update("v0.4.24", "v0.4.24", False).compatible_clock_styles)

    def test_differing_versions_are_visible_to_user(self):
        status = describe_device_update("v0.4.25", "v0.4.24", True)
        self.assertIn("versions differ", status.status)


if __name__ == "__main__":
    unittest.main()
