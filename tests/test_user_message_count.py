import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _is_real_user_prompt, _classify_user_entry


def _user(content, **extra):
    obj = {"type": "user", "message": {"role": "user", "content": content}}
    obj.update(extra)
    return obj


class IsRealUserPromptTest(unittest.TestCase):
    def test_plain_string_prompt_counts(self):
        self.assertTrue(_is_real_user_prompt(_user("Fix the bug please")))

    def test_text_block_prompt_counts(self):
        self.assertTrue(_is_real_user_prompt(
            _user([{"type": "text", "text": "do the thing"}])))

    def test_tool_result_does_not_count(self):
        # Claude Code records tool results on the user channel.
        self.assertFalse(_is_real_user_prompt(
            _user([{"type": "tool_result", "tool_use_id": "abc",
                    "content": "file contents"}])))

    def test_tool_result_mixed_with_text_does_not_count(self):
        self.assertFalse(_is_real_user_prompt(
            _user([{"type": "tool_result", "tool_use_id": "x", "content": "y"},
                   {"type": "text", "text": "trailing"}])))

    def test_slash_command_wrapper_does_not_count(self):
        self.assertFalse(_is_real_user_prompt(
            _user("<command-name>close</command-name>")))

    def test_local_command_wrapper_does_not_count(self):
        self.assertFalse(_is_real_user_prompt(
            _user("<local-command-stdout>output</local-command-stdout>")))

    def test_interrupt_marker_does_not_count(self):
        self.assertFalse(_is_real_user_prompt(
            _user("[Request interrupted by user]")))

    def test_meta_entry_does_not_count(self):
        self.assertFalse(_is_real_user_prompt(
            _user("some system note", isMeta=True)))

    def test_empty_content_does_not_count(self):
        self.assertFalse(_is_real_user_prompt(_user("")))
        self.assertFalse(_is_real_user_prompt(_user([])))


class ClassifyUserEntryTest(unittest.TestCase):
    def test_categories(self):
        cases = {
            "prompt": _user("real message"),
            "tool_result": _user([{"type": "tool_result", "tool_use_id": "a", "content": "x"}]),
            "command": _user("<command-name>close</command-name>"),
            "interrupt": _user("[Request interrupted by user]"),
            "meta": _user("note", isMeta=True),
        }
        for expected, obj in cases.items():
            self.assertEqual(_classify_user_entry(obj), expected, expected)

    def test_precedence_tool_result_over_meta(self):
        obj = _user([{"type": "tool_result", "tool_use_id": "a", "content": "x"}], isMeta=True)
        self.assertEqual(_classify_user_entry(obj), "tool_result")

    def test_empty_buckets_as_meta(self):
        self.assertEqual(_classify_user_entry(_user("")), "meta")

    def test_compact_summary_is_not_a_prompt(self):
        # Compaction is recorded as type:"user" + isCompactSummary:true with a
        # plain-string content; it must not count as a typed prompt.
        obj = _user("This session is being continued from a previous "
                    "conversation that ran out of context...",
                    isCompactSummary=True)
        self.assertEqual(_classify_user_entry(obj), "meta")
        self.assertFalse(_is_real_user_prompt(obj))


if __name__ == "__main__":
    unittest.main()
