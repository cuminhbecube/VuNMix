import pathlib
import unittest


REPO_DIR = pathlib.Path(__file__).resolve().parents[2]
GUI_PATH = REPO_DIR / "desktop" / "gui.py"


class SettingsLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GUI_PATH.read_text(encoding="utf-8")

    def test_save_button_is_reserved_at_bottom(self):
        self.assertIn(
            "save_btn.pack(side='bottom', fill='x', padx=12, pady=(4, 8))",
            self.source,
        )
        self.assertLess(
            self.source.index("save_btn.pack(side='bottom'"),
            self.source.index("# Content rows stay compact"),
        )

    def test_settings_rows_do_not_expand_vertically(self):
        self.assertIn("content.pack(fill='x', padx=12)", self.source)
        self.assertIn(
            'row = ctk.CTkFrame(parent, fg_color="transparent", height=26)',
            self.source,
        )
        self.assertIn("row.pack(fill='x', pady=1)", self.source)

    def test_bottom_cards_use_compact_spacing(self):
        self.assertIn(
            "favorites_frame.pack(fill='x', padx=12, pady=(3, 1))",
            self.source,
        )
        self.assertIn(
            "update_frame.pack(fill='x', padx=12, pady=(3, 1))",
            self.source,
        )
        self.assertIn(
            "firmware_frame.pack(fill='x', padx=12, pady=(3, 1))",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
