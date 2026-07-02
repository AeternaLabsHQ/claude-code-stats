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


class CacheEffTrivialFilterTest(unittest.TestCase):
    def test_one_message_session_excluded_from_cache_eff_series(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-eff1-"))
        data = _build(tmp, [
            assistant_line(msg_id="m1",
                           usage_extra={"cache_read_input_tokens": 500}),
        ])
        days = [d["date"] for d in data["daily_cache_efficiency"]]
        self.assertEqual(days, [])

    def test_three_message_session_included(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-eff3-"))
        data = _build(tmp, [
            user_line(),
            assistant_line(msg_id="m1",
                           usage_extra={"cache_read_input_tokens": 500}),
            assistant_line(msg_id="m2", ts="2026-06-10T10:01:00Z",
                           usage_extra={"cache_read_input_tokens": 500}),
        ])
        days = [d["date"] for d in data["daily_cache_efficiency"]]
        self.assertEqual(days, ["2026-06-10"])


class SubagentFlagExportTest(unittest.TestCase):
    def test_orphan_subagent_flagged_in_session_list(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-subflag-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "S1.jsonl",
                    [user_line(), assistant_line()])
        # Orphan subagent: parent transcript PARENT-GONE was cleaned up,
        # so the agent session survives as a standalone session.
        write_jsonl(
            pd / "proj1" / "PARENT-GONE" / "subagents" / "agent-a1.jsonl",
            [user_line(session_id="agent-a1"),
             assistant_line(session_id="agent-a1", msg_id="m2")])
        with patched_sources(pd) as es:
            sessions = es.parse_session_transcripts()
            data = es.build_dashboard_data(sessions, {}, {}, [])
        by_id = {s["session_id"]: s for s in data["sessions"]}
        self.assertIn("agent-a1", by_id)
        self.assertIs(by_id["agent-a1"]["is_subagent"], True)
        self.assertIs(by_id["S1"]["is_subagent"], False)


if __name__ == "__main__":
    unittest.main()
