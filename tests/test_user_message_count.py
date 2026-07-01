import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _classify_user_entry


def _user(content, **extra):
    obj = {"type": "user", "message": {"role": "user", "content": content}}
    obj.update(extra)
    return obj


class ClassifyUserEntryTest(unittest.TestCase):
    def test_plain_string_prompt_is_prompt(self):
        self.assertEqual(_classify_user_entry(_user("Fix the bug please")),
                         "prompt")

    def test_text_block_prompt_is_prompt(self):
        self.assertEqual(
            _classify_user_entry(_user([{"type": "text",
                                         "text": "do the thing"}])),
            "prompt")

    def test_tool_result_is_not_a_prompt(self):
        # Claude Code records tool results on the user channel.
        self.assertEqual(
            _classify_user_entry(_user([{"type": "tool_result",
                                         "tool_use_id": "abc",
                                         "content": "file contents"}])),
            "tool_result")

    def test_tool_result_mixed_with_text_is_tool_result(self):
        self.assertEqual(
            _classify_user_entry(_user([
                {"type": "tool_result", "tool_use_id": "x", "content": "y"},
                {"type": "text", "text": "trailing"}])),
            "tool_result")

    def test_slash_command_wrapper_is_command(self):
        self.assertEqual(
            _classify_user_entry(_user("<command-name>close</command-name>")),
            "command")

    def test_local_command_wrapper_is_command(self):
        self.assertEqual(
            _classify_user_entry(
                _user("<local-command-stdout>output</local-command-stdout>")),
            "command")

    def test_interrupt_marker_is_interrupt(self):
        self.assertEqual(
            _classify_user_entry(_user("[Request interrupted by user]")),
            "interrupt")

    def test_meta_entry_is_meta(self):
        self.assertEqual(
            _classify_user_entry(_user("some system note", isMeta=True)),
            "meta")

    def test_empty_content_is_meta(self):
        self.assertEqual(_classify_user_entry(_user("")), "meta")
        self.assertEqual(_classify_user_entry(_user([])), "meta")

    def test_precedence_tool_result_over_meta(self):
        obj = _user([{"type": "tool_result", "tool_use_id": "a",
                      "content": "x"}], isMeta=True)
        self.assertEqual(_classify_user_entry(obj), "tool_result")

    def test_compact_summary_is_meta_not_prompt(self):
        # Compaction is recorded as type:"user" + isCompactSummary:true with
        # a plain-string content; it must not count as a typed prompt.
        obj = _user("This session is being continued from a previous "
                    "conversation that ran out of context...",
                    isCompactSummary=True)
        self.assertEqual(_classify_user_entry(obj), "meta")


if __name__ == "__main__":
    unittest.main()
