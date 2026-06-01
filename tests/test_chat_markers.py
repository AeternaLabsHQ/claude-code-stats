import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _extract_command_label


class ExtractCommandLabelTest(unittest.TestCase):
    def test_plain_name_with_slash(self):
        self.assertEqual(_extract_command_label("<command-name>/close</command-name>"), "/close")

    def test_name_without_slash_gets_one(self):
        self.assertEqual(
            _extract_command_label("<command-message>x</command-message><command-name>close</command-name>"),
            "/close")

    def test_name_with_args(self):
        self.assertEqual(
            _extract_command_label("<command-name>code-review</command-name><command-args>ultra</command-args>"),
            "/code-review ultra")

    def test_stdout_only_has_no_label(self):
        # local-command stdout is command *output*, not an invocation
        self.assertEqual(_extract_command_label("<local-command-stdout>done</local-command-stdout>"), "")

    def test_no_command_tag(self):
        self.assertEqual(_extract_command_label("just text"), "")


if __name__ == "__main__":
    unittest.main()
