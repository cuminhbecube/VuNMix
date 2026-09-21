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

    def test_rebuild_retargets_existing_release_tag(self):
        workflow = (REPO_DIR / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('"repos/${GITHUB_REPOSITORY}/git/refs/tags/${TAG}"', workflow)
        self.assertIn('-f sha="${GITHUB_SHA}"', workflow)
        self.assertIn("-F force=true", workflow)
        self.assertIn("--clobber", workflow)

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
