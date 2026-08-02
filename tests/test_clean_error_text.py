import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _clean_error_text


class CleanErrorTextTest(unittest.TestCase):
    def test_strips_ansi_color_codes(self):
        s = "Exit code 1\n\x1b[1m\x1b[37m=== Deploying ===\x1b[39m\x1b[22m done"
        self.assertEqual(_clean_error_text(s), "Exit code 1\n=== Deploying === done")

    def test_strips_carriage_returns(self):
        self.assertEqual(_clean_error_text("line1\r\nline2\r\n"), "line1\nline2")

    def test_plain_text_unchanged(self):
        s = "No such tool available: TodoWrite. TodoWrite exists but is not enabled."
        self.assertEqual(_clean_error_text(s), s)

    def test_preserves_newlines_and_trims_trailing_ws(self):
        self.assertEqual(_clean_error_text("a\nb\n   \n"), "a\nb")

    def test_strips_cursor_and_other_csi(self):
        # non-color CSI sequences (cursor moves, erase) must go too
        self.assertEqual(_clean_error_text("\x1b[2K\x1b[1Gprogress: 50%"), "progress: 50%")

    def test_handles_non_string(self):
        self.assertEqual(_clean_error_text(None), "")


if __name__ == "__main__":
    unittest.main()
