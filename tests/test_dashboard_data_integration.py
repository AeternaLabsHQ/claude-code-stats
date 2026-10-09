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


class CostByTypeTest(unittest.TestCase):
    def test_cost_by_type_adds_up_with_tiered_haiku(self):
        # One Haiku 5.5 call under 100k, one over: the long one is billed at
        # 5x. The input/output/cache split must still add up to the total,
        # which a token-totals x one-rate recomputation would miss.
        tmp = Path(tempfile.mkdtemp(prefix="cs-tiers-"))
        data = _build(tmp, [
            user_line(),
            assistant_line(msg_id="m1", model="claude-haiku-5-5",
                           output_tokens=10_000,
                           usage_extra={"cache_read_input_tokens": 50_000}),
            assistant_line(msg_id="m2", ts="2026-06-10T10:01:00Z",
                           model="claude-haiku-5-5", output_tokens=10_000,
                           usage_extra={"cache_read_input_tokens": 150_000}),
            assistant_line(msg_id="m3", ts="2026-06-10T10:02:00Z"),
        ])
        cbt = data["cost_by_token_type"]
        parts = cbt["input"] + cbt["output"] + cbt["cache_read"] + cbt["cache_write"]
        self.assertAlmostEqual(parts, data["kpi"]["total_cost"], places=2)
        # Haiku output: 10k at $0.50 + 10k at $2.50 = $0.03, plus Opus 4.8's
        # 100 output tokens at $25 = $0.0025.
        self.assertAlmostEqual(cbt["output"], 0.0325, places=2)
        # Savings use each call's own tier: 50k x (0.10-0.01) + 150k x (0.50-0.05).
        self.assertAlmostEqual(cbt["cache_savings"], 0.07, places=2)
