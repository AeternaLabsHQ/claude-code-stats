"""End-to-end checks on build_dashboard_data using minimal JSONL fixtures."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixture_utils import (assistant_line, patched_sources, user_line,
                                 write_jsonl)

TOOLS3 = [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
          {"type": "tool_use", "id": "t2", "name": "Read", "input": {}},
          {"type": "tool_use", "id": "t3", "name": "Bash",
           "input": {"command": "ls"}}]


def _build(tmp, session_lines, plan_history=None):
    pd = tmp / "projects"
    write_jsonl(pd / "proj1" / "S1.jsonl", session_lines)
    with patched_sources(pd, plan_history=plan_history) as es:
        sessions = es.parse_session_transcripts()
        return es.build_dashboard_data(sessions, {}, {}, [])


class ToolCallCountTest(unittest.TestCase):
    def test_total_tool_calls_counts_tool_uses_not_api_calls(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-tools-"))
        data = _build(tmp, [
            user_line(),
            assistant_line(msg_id="m1", content=TOOLS3),
            assistant_line(msg_id="m2", ts="2026-06-10T10:01:00Z"),
        ])
        # 3 tool_use blocks in 2 api calls: the label says "tool calls".
        self.assertEqual(data["error_summary"]["total_tool_calls"], 3)


class EmptyPlanHistoryDataTest(unittest.TestCase):
    def test_dashboard_builds_without_plan_history(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-noplan-"))
        data = _build(tmp, [user_line(), assistant_line()], plan_history=[])
        self.assertIsNone(data["plan"])
        self.assertIsNone(data["plan_recommendation"])
        self.assertEqual(data["kpi"]["actual_plan_cost"], 0)


if __name__ == "__main__":
    unittest.main()
