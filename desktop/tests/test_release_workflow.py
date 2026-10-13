import pathlib
import unittest


REPO_DIR = pathlib.Path(__file__).resolve().parents[2]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_versioned_release_branch_is_supported(self):
        workflow = (REPO_DIR / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('"release/v*"', workflow)
        self.assertIn('refs/heads/release/v*', workflow)
        self.assertIn('TAG="${GITHUB_REF_NAME#release/}"', workflow)
        self.assertIn("IS_RELEASE=\"true\"", workflow)

    def test_release_guard_requires_ancestor_and_immutable_tag(self):
        workflow = (REPO_DIR / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("feature_contracts:", workflow)
        self.assertIn("scripts/verify_feature_contracts.py", workflow)
        self.assertIn("already published. Create the next patch version", workflow)
        self.assertNotIn("--clobber", workflow)
        self.assertNotIn("-F force=true", workflow)

    def test_feature_contracts_guard_all_published_clock_styles(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, str(REPO_DIR / "scripts" / "verify_feature_contracts.py")],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("16 clock styles", result.stdout)

    def test_release_assets_keep_expected_names(self):
        workflow = (REPO_DIR / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        for name in (
            "VuNMix-Firmware-${VERSION}.bin",
            "VuNMix-Firmware-Full-${VERSION}.zip",
            "VuNMix-Windows-Portable-${VERSION}.zip",
            "VuNMix-Windows-Setup-${VERSION}.exe",
            "SHA256SUMS.txt",
        ):
            self.assertIn(name, workflow)


if __name__ == "__main__":
    unittest.main()
