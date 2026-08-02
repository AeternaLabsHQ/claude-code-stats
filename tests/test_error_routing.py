import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _route_tool_error


class RouteToolErrorTest(unittest.TestCase):
    def test_cancelled_is_not_an_error(self):
        # Parallel-call cancellation cascade -> tracked separately, None means
        # "do not count as an error".
        self.assertIsNone(_route_tool_error("user", "cancelled"))

    def test_rejected_counts_as_error_with_own_source(self):
        # Per the user's decision: a declined tool call DOES count toward
        # error_count, under its own source label "rejected".
        self.assertEqual(_route_tool_error("user", "rejected"), "rejected")

    def test_tool_failure_keeps_source(self):
        self.assertEqual(_route_tool_error("tool", "exit_code"), "tool")

    def test_hook_keeps_source(self):
        self.assertEqual(_route_tool_error("hook", "hook_error"), "hook")

    def test_backend_keeps_source(self):
        self.assertEqual(_route_tool_error("backend", "auth"), "backend")


if __name__ == "__main__":
    unittest.main()
