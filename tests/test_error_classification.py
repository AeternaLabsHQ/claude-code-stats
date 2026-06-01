import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _classify_tool_error, _classify_api_error


class ClassifyToolErrorTest(unittest.TestCase):
    def test_cancelled_parallel_call_is_user(self):
        src, cat = _classify_tool_error(
            "<tool_use_error>Cancelled: parallel tool call Bash(ls)</tool_use_error>", "Bash")
        self.assertEqual(src, "user")
        self.assertEqual(cat, "cancelled")

    def test_user_rejection_is_user(self):
        src, cat = _classify_tool_error(
            "The user doesn't want to proceed with this tool use. The tool use was rejected.", "Edit")
        self.assertEqual(src, "user")
        self.assertEqual(cat, "rejected")

    def test_hook_error_is_hook(self):
        src, cat = _classify_tool_error(
            "PreToolUse:Edit hook error: [python3 hook.py] failed", "Edit")
        self.assertEqual(src, "hook")
        self.assertEqual(cat, "hook_error")

    def test_file_not_found_is_tool(self):
        src, cat = _classify_tool_error("File does not exist.", "Read")
        self.assertEqual(src, "tool")
        self.assertEqual(cat, "file_not_found")

    def test_exit_code_is_tool(self):
        src, cat = _classify_tool_error("Exit code 2", "Bash")
        self.assertEqual(src, "tool")
        self.assertEqual(cat, "exit_code")

    def test_edit_not_unique_is_tool(self):
        src, cat = _classify_tool_error(
            "Found 2 matches of the string to replace, but replace_all is false.", "Edit")
        self.assertEqual(src, "tool")
        self.assertEqual(cat, "edit_not_unique")

    # --- regression: the bug the user spotted ---
    # tool output that incidentally contains backend/limit keywords must NOT
    # be miscategorised as a backend error.
    def test_edit_on_limit_code_not_rate_limit(self):
        src, cat = _classify_tool_error(
            '<tool_use_error>String to replace not found in file.\n'
            'String: if "usage limit reached" in text or "plan limit reached"</tool_use_error>', "Edit")
        self.assertEqual(src, "tool")
        self.assertNotEqual(cat, "rate_limit")

    def test_bash_test_output_mentioning_429_not_rate_limit(self):
        src, cat = _classify_tool_error(
            "Exit code 1\nTAP version 13\n# tests handling of 429 rate_limit_error responses\nnot ok 3", "Bash")
        self.assertEqual(src, "tool")
        self.assertNotEqual(cat, "rate_limit")

    def test_traceback_mentioning_timeout_stays_tool(self):
        src, cat = _classify_tool_error(
            "Exit code 1\nTraceback (most recent call last):\n  raise TimeoutError('timed out')", "Bash")
        self.assertEqual(src, "tool")


class ClassifyApiErrorTest(unittest.TestCase):
    def test_plan_limit(self):
        self.assertEqual(_classify_api_error("You've hit your limit · resets 6pm (Europe/Berlin)"), "rate_limit")

    def test_org_usage_limit(self):
        self.assertEqual(_classify_api_error("You've hit your org's monthly usage limit"), "rate_limit")

    def test_overloaded(self):
        self.assertEqual(_classify_api_error(
            'API Error: 529 {"type":"error","error":{"type":"overloaded_error"}}'), "server_overload")

    def test_auth(self):
        self.assertEqual(_classify_api_error(
            'Please run /login · API Error: 401 {"type":"authentication_error"}'), "auth")

    def test_server_error(self):
        self.assertEqual(_classify_api_error("API Error: 500 Internal server error."), "server_error")

    def test_connection(self):
        self.assertEqual(_classify_api_error("API Error: Stream idle timeout - partial response received"), "connection")

    def test_invalid_request(self):
        self.assertEqual(_classify_api_error("Prompt is too long"), "invalid_request")

    def test_content_filter(self):
        self.assertEqual(_classify_api_error("API Error: Output blocked by content filtering policy"), "content_filter")


if __name__ == "__main__":
    unittest.main()
