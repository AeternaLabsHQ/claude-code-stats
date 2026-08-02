import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _day_from_ms, split_session_by_day

# 2026-06-10 and 2026-06-12 (UTC) in ms
TS_10 = 1781092800000
TS_12 = 1781251200000


def _bucket(**kw):
    base = {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        "cost": 0.0, "calls": 0,
    }
    base.update(kw)
    return base


class DayFromMsTest(unittest.TestCase):
    def test_utc_day_string(self):
        self.assertEqual(_day_from_ms(TS_10), "2026-06-10")
        self.assertEqual(_day_from_ms(TS_12), "2026-06-12")


class SplitSessionByDayTest(unittest.TestCase):
    def test_distributes_across_days(self):
        daily_models = {
            "2026-06-10": {"opus": _bucket(output_tokens=100, cost=2.0, calls=1)},
            "2026-06-12": {"opus": _bucket(output_tokens=50, cost=1.0, calls=1)},
        }
        model_totals = {"opus": _bucket(output_tokens=150, cost=3.0, calls=2)}
        per_day_models, per_day_messages = split_session_by_day(
            daily_models, model_totals, {}, 0, start_day="2026-06-10")
        self.assertEqual(per_day_models["2026-06-10"]["opus"]["cost"], 2.0)
        self.assertEqual(per_day_models["2026-06-12"]["opus"]["cost"], 1.0)
        self.assertNotIn("2026-06-11", per_day_models)
        self.assertEqual(sorted(per_day_models), ["2026-06-10", "2026-06-12"])

    def test_untimestamped_remainder_goes_to_start_day(self):
        daily_models = {
            "2026-06-12": {"opus": _bucket(output_tokens=100, cost=2.0, calls=1)},
        }
        model_totals = {"opus": _bucket(output_tokens=150, cost=3.0, calls=2)}
        per_day_models, _ = split_session_by_day(
            daily_models, model_totals, {}, 0, start_day="2026-06-10")
        self.assertEqual(per_day_models["2026-06-10"]["opus"]["cost"], 1.0)
        self.assertEqual(per_day_models["2026-06-10"]["opus"]["output_tokens"], 50)
        self.assertEqual(per_day_models["2026-06-12"]["opus"]["cost"], 2.0)
        total = sum(d["opus"]["cost"] for d in per_day_models.values())
        self.assertAlmostEqual(total, 3.0)

    def test_empty_daily_models_all_on_start_day(self):
        model_totals = {"opus": _bucket(output_tokens=80, cost=1.6, calls=1)}
        per_day_models, _ = split_session_by_day(
            {}, model_totals, {}, 0, start_day="2026-05-11")
        self.assertEqual(per_day_models["2026-05-11"]["opus"]["cost"], 1.6)
        self.assertEqual(list(per_day_models.keys()), ["2026-05-11"])

    def test_messages_distributed_with_remainder_on_start(self):
        per_day_messages_in = {"2026-06-11": 5, "2026-06-12": 3}
        _, per_day_messages = split_session_by_day(
            {}, {}, per_day_messages_in, total_message_count=10,
            start_day="2026-06-10")
        self.assertEqual(per_day_messages["2026-06-11"], 5)
        self.assertEqual(per_day_messages["2026-06-12"], 3)
        self.assertEqual(per_day_messages["2026-06-10"], 2)
        self.assertEqual(sum(per_day_messages.values()), 10)

    def test_float_drift_does_not_create_phantom_start_day(self):
        # attributed cost exceeds total by a sub-micro epsilon (simulates
        # float-summation drift); no phantom start_day bucket must appear.
        daily_models = {
            "2026-06-12": {"opus": _bucket(output_tokens=100, cost=2.0000001, calls=1)},
        }
        model_totals = {"opus": _bucket(output_tokens=100, cost=2.0, calls=1)}
        per_day_models, _ = split_session_by_day(
            daily_models, model_totals, {}, 0, start_day="2026-06-10")
        self.assertNotIn("2026-06-10", per_day_models)
        self.assertEqual(list(per_day_models), ["2026-06-12"])


class SubagentAbsorbTest(unittest.TestCase):
    """Exercises the REAL absorb/link functions instead of re-implementing
    the merge loop inline (the old test stayed green even when the real
    wiring regressed)."""

    def _parent(self):
        return {
            "session_id": "parent",
            "models": defaultdict(lambda: _bucket()),
            "daily_models": defaultdict(lambda: defaultdict(lambda: _bucket())),
            "subagents": [],
            "agent_dispatches": [],
            "message_count": 5,
            "tools": {},
            "is_subagent": False,
            "parent_session_id": "",
        }

    def _sub(self, parent_id="parent"):
        return {
            "session_id": "agent-a1",
            "models": {"opus": _bucket(input_tokens=10, output_tokens=40,
                                       cost=0.5, calls=1)},
            "daily_models": {
                "2026-06-12": {"opus": _bucket(cost=0.5, calls=1)},
                "2026-06-11": {"haiku": _bucket(cost=0.2, calls=1)},
            },
            "subagents": [],
            "agent_dispatches": [],
            "message_count": 3,
            "tools": {"Read": 2},
            "is_subagent": True,
            "parent_session_id": parent_id,
            "agent_id": "a1",
            "agent_type": "explore",
            "agent_description": "look around",
        }

    def test_absorb_merges_totals_and_daily(self):
        from extract_stats import _absorb_subagent
        parent = self._parent()
        parent["models"]["opus"] = _bucket(cost=1.0, calls=1)
        parent["daily_models"]["2026-06-12"]["opus"] = _bucket(cost=1.0, calls=1)
        _absorb_subagent(parent, self._sub(), "explore", "look around")
        self.assertAlmostEqual(parent["models"]["opus"]["cost"], 1.5)
        self.assertAlmostEqual(
            parent["daily_models"]["2026-06-12"]["opus"]["cost"], 1.5)
        self.assertAlmostEqual(
            parent["daily_models"]["2026-06-11"]["haiku"]["cost"], 0.2)
        self.assertEqual(parent["subagents"][0]["tokens"], 50)

    def test_link_subagents_absorbs_and_removes(self):
        from extract_stats import _link_subagents
        sessions = {"parent": self._parent(), "agent-a1": self._sub()}
        orphans = _link_subagents(sessions)
        self.assertEqual(orphans, 0)
        self.assertNotIn("agent-a1", sessions)
        self.assertAlmostEqual(sessions["parent"]["models"]["opus"]["cost"], 0.5)

    def test_link_subagents_keeps_orphans(self):
        from extract_stats import _link_subagents
        sessions = {"agent-a1": self._sub(parent_id="GONE")}
        orphans = _link_subagents(sessions)
        self.assertEqual(orphans, 1)
        self.assertIn("agent-a1", sessions)


if __name__ == "__main__":
    unittest.main()
