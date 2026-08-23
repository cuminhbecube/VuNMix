import pathlib
import sys
import unittest


DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from build_info import APP_VERSION, PROTOCOL_VERSION, build_summary, normalize_version


class BuildInfoTests(unittest.TestCase):
    def test_normalizes_semver_to_v_prefixed_release(self):
        self.assertEqual(normalize_version("0.5.0"), "v0.5.0")
        self.assertEqual(normalize_version("v0.5.0"), "v0.5.0")
        self.assertEqual(normalize_version("ci-abcdef0"), "ci-abcdef0")

    def test_build_summary_contains_version_and_protocol(self):
        summary = build_summary()
        self.assertIn(APP_VERSION, summary)
        self.assertIn(f"protocol {PROTOCOL_VERSION}", summary)


if __name__ == "__main__":
    unittest.main()
