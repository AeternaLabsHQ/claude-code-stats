"""build_experiment_summary: per-ID behaviour vs a time-matched baseline."""
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core import experiments
from claudestats_core.experiments import (add_reply, build_experiment_summary,
                                          new_bucket, session_experiment_ids)

FULL = "21e0afd842ce5836"
MODEL = "claude-opus-5"
TOOL = {"type": "tool_use", "name": "Read", "input": {}}
TEXT = {"type": "text", "text": "ok"}


def bucket(n, multi=0.0, text_before=0.0, bash_len=300, out=450, cost=0.01):
    """n replies, every one a tool reply; shares are exact fractions of n."""
    b = new_bucket()
    n_multi = round(n * multi)
    n_text = round(n * text_before)
    for i in range(n):
        blocks = []
        if i < n_text:
            blocks.append(TEXT)
        blocks.append({"type": "tool_use", "name": "Bash",
                       "input": {"command": "x" * bash_len}})
        if i >= n - n_multi:
            blocks.append(TOOL)
        add_reply(b, blocks, out, cost)
    return b


def session(buckets, source="cortex"):
    """buckets: {(model, atis_id, day): bucket}"""
    exp = {}
    for (model, atis, day), b in buckets.items():
        exp.setdefault(f"{model}|{atis}", {})[day] = b
    return {"source": source, "experiments": exp}


def day(offset, base=date(2026, 6, 20)):
    return (base + timedelta(days=offset)).isoformat()


READ = {"type": "tool_use", "name": "Read", "input": {}}


def mixed_bucket(n, multi, bash, bash_len=300, plain=0, out=450):
    """n replies: `multi` with two Read calls, `bash` with one Bash call,
    `plain` text-only (no tools), the rest one Read call. Every tool reply
    with an even index starts with text."""
    b = new_bucket()
    for i in range(n):
        if i < multi:
            blocks = [READ, READ]
        elif i < multi + bash:
            blocks = [{"type": "tool_use", "name": "Bash",
                       "input": {"command": "x" * bash_len}}]
        elif i < multi + bash + plain:
            add_reply(b, [TEXT], out, 0.01)
            continue
        else:
            blocks = [READ]
        if i % 2 == 0:
            blocks = [TEXT] + blocks
        add_reply(b, blocks, out, 0.01)
    return b


def changed_corpus(base_replies=400):
    return {"s1": session({
        (MODEL, "", day(-5)): bucket(base_replies, 0.20, 0.20, 300, 450),
        (MODEL, FULL, day(0)): bucket(300, 0.40, 0.09, 650, 940),
    })}


def model_row(summary, i=0):
    return summary["ids"][i]["models"][0]


class EmptyAndShapeTest(unittest.TestCase):
    def test_empty_inputs(self):
        s = build_experiment_summary({}, {})
        self.assertFalse(s["has_data"])
        self.assertEqual(s["ids"], [])
        self.assertEqual(s["current"], [])
        self.assertEqual(s["thresholds"], {
            "min_replies": 200, "rel_change": 0.4,
            "min_changed_metrics": 2, "baseline_pad_days": 14,
            "min_support": 30})

    def test_sessions_without_experiments_key_are_skipped(self):
        s = build_experiment_summary({"a": {"source": "x"}, "b": {}}, {})
        self.assertFalse(s["has_data"])

    def test_only_blank_id_buckets_means_no_data(self):
        sess = {"s": session({(MODEL, "", day(0)): bucket(10)})}
        s = build_experiment_summary(sess, {})
        self.assertFalse(s["has_data"])
        self.assertEqual(s["ids"], [])

    def test_session_experiment_ids(self):
        sess = session({(MODEL, FULL, day(0)): bucket(1),
                        (MODEL, "", day(0)): bucket(1),
                        ("other", "aaaa", day(0)): bucket(1)})
        self.assertEqual(session_experiment_ids(sess), [FULL, "aaaa"])
        self.assertEqual(session_experiment_ids({}), [])


class VerdictTest(unittest.TestCase):
    def test_changed_verdict(self):
        s = build_experiment_summary(changed_corpus(), {})
        self.assertTrue(s["has_data"])
        e = s["ids"][0]
        self.assertEqual(e["id"], FULL)
        self.assertEqual(e["short"], "21e")
        m = e["models"][0]
        self.assertEqual(m["model"], MODEL)
        self.assertEqual(m["replies"], 300)
        self.assertEqual(m["baseline"]["replies"], 400)
        self.assertEqual(m["verdict"], "changed")
        self.assertAlmostEqual(m["metrics"]["multi_tool_share"], 0.40, 3)
        self.assertAlmostEqual(m["metrics"]["text_before_share"], 0.09, 3)
        self.assertAlmostEqual(m["metrics"]["cost_per_reply"], 0.01, 6)
        self.assertAlmostEqual(m["baseline"]["metrics"]["multi_tool_share"],
                               0.20, 3)
        self.assertAlmostEqual(m["changes"]["multi_tool_share"], 1.0, 2)
        self.assertLess(m["changes"]["text_before_share"], -0.4)
        self.assertGreater(m["changes"]["median_bash_chars"], 0.9)
        self.assertNotIn("cost_per_reply", m["changes"])

    def test_no_effect_verdict(self):
        sess = {"s1": session({
            (MODEL, "", day(-5)): bucket(400, 0.20, 0.20, 300, 450),
            (MODEL, FULL, day(0)): bucket(300, 0.21, 0.21, 310, 460),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertEqual(m["verdict"], "no_effect")

    def test_one_changed_metric_is_not_enough(self):
        sess = {"s1": session({
            (MODEL, "", day(-5)): bucket(400, 0.20, 0.20, 300, 450),
            (MODEL, FULL, day(0)): bucket(300, 0.40, 0.20, 300, 450),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertEqual(m["verdict"], "no_effect")

    def test_insufficient_when_small_baseline(self):
        m = model_row(build_experiment_summary(changed_corpus(150), {}))
        self.assertEqual(m["baseline"]["replies"], 150)
        self.assertEqual(m["verdict"], "insufficient")

    def test_insufficient_when_few_replies(self):
        sess = {"s1": session({
            (MODEL, "", day(-5)): bucket(400, 0.20, 0.20, 300, 450),
            (MODEL, FULL, day(0)): bucket(199, 0.40, 0.09, 650, 940),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertEqual(m["verdict"], "insufficient")

    def test_no_baseline_at_all(self):
        sess = {"s1": session({(MODEL, FULL, day(0)): bucket(300, 0.4)})}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertEqual(m["verdict"], "insufficient")
        self.assertEqual(m["baseline"]["replies"], 0)
        self.assertIsNone(m["baseline"]["metrics"]["median_bash_chars"])
        self.assertIsNone(m["changes"]["multi_tool_share"])

    def test_zero_baseline_metric_gives_none_change(self):
        sess = {"s1": session({
            (MODEL, "", day(-5)): bucket(400, 0.0, 0.20, 300, 450),
            (MODEL, FULL, day(0)): bucket(300, 0.4, 0.20, 300, 450),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertIsNone(m["changes"]["multi_tool_share"])


class SupportFloorTest(unittest.TestCase):
    def sparse_corpus(self):
        # Review case: rare events on both sides. Multi-tool share doubles
        # and Bash commands are twice as long, but 10/8 and 4/3 events are
        # noise, not an effect.
        return {"s1": session({
            (MODEL, "", day(-5)): mixed_bucket(1000, 10, 8, bash_len=300),
            (MODEL, FULL, day(0)): mixed_bucket(200, 4, 3, bash_len=650),
        })}

    def test_min_support_value(self):
        self.assertEqual(getattr(experiments, "MIN_SUPPORT", None), 30)

    def test_sparse_events_are_not_changed(self):
        m = model_row(build_experiment_summary(self.sparse_corpus(), {}))
        self.assertNotEqual(m["verdict"], "changed")
        self.assertEqual(m["verdict"], "no_effect")
        self.assertIsNone(m["changes"]["multi_tool_share"])
        self.assertIsNone(m["changes"]["median_bash_chars"])
        self.assertAlmostEqual(m["changes"]["text_before_share"], 0.0, 2)
        self.assertAlmostEqual(m["changes"]["median_output_tokens"], 0.0, 2)
        # Values are still reported, only the change is withheld.
        self.assertAlmostEqual(m["metrics"]["multi_tool_share"], 0.02, 4)
        self.assertIsNotNone(m["metrics"]["median_bash_chars"])

    def test_support_counts_exported(self):
        m = model_row(build_experiment_summary(self.sparse_corpus(), {}))
        self.assertEqual(m["support"], {
            "replies": 200, "tool_replies": 200, "multi_tool": 4,
            "text_before": 100, "bash_cmds": 3})
        self.assertEqual(m["baseline"]["support"], {
            "replies": 1000, "tool_replies": 1000, "multi_tool": 10,
            "text_before": 500, "bash_cmds": 8})

    def test_multi_tool_needs_support_on_one_side_only(self):
        sess = {"s1": session({
            (MODEL, "", day(-5)): mixed_bucket(1000, 10, 300),
            (MODEL, FULL, day(0)): mixed_bucket(300, 30, 90),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertAlmostEqual(m["changes"]["multi_tool_share"], 9.0, 2)

    def test_bash_needs_support_on_both_sides(self):
        sess = {"s1": session({
            (MODEL, "", day(-5)): mixed_bucket(1000, 100, 500, bash_len=300),
            (MODEL, FULL, day(0)): mixed_bucket(300, 30, 29, bash_len=650),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertIsNone(m["changes"]["median_bash_chars"])
        self.assertIsNotNone(m["changes"]["multi_tool_share"])

    def test_text_before_needs_tool_replies_on_both_sides(self):
        # ID side: 29 tool replies (15 with text first), rest text-only.
        sess = {"s1": session({
            (MODEL, "", day(-5)): mixed_bucket(1000, 100, 500),
            (MODEL, FULL, day(0)): mixed_bucket(300, 0, 29, plain=271),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertEqual(m["support"]["tool_replies"], 29)
        self.assertIsNone(m["changes"]["text_before_share"])

    def test_text_before_needs_enough_text_first_replies(self):
        # Plenty of tool replies, but text-first replies are rare on both
        # sides (20 and 29, both under the floor).
        def few_text(n, n_text):
            b = new_bucket()
            for i in range(n):
                add_reply(b, ([TEXT] if i < n_text else []) + [READ], 450,
                          0.01)
            return b
        sess = {"s1": session({
            (MODEL, "", day(-5)): few_text(1000, 20),
            (MODEL, FULL, day(0)): few_text(300, 29),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        self.assertIsNone(m["changes"]["text_before_share"])

    def test_insufficient_when_too_few_metrics_can_be_judged(self):
        # Mostly text-only replies: only the output-token median can be
        # compared, one metric is fewer than MIN_CHANGED_METRICS.
        sess = {"s1": session({
            (MODEL, "", day(-5)): mixed_bucket(1000, 0, 5, plain=990),
            (MODEL, FULL, day(0)): mixed_bucket(300, 0, 5, plain=290,
                                                out=2000),
        })}
        m = model_row(build_experiment_summary(sess, {}))
        judged = [k for k, v in m["changes"].items() if v is not None]
        self.assertEqual(judged, ["median_output_tokens"])
        self.assertEqual(m["verdict"], "insufficient")


class BaselineWindowTest(unittest.TestCase):
    def test_baseline_window(self):
        sess = {"s1": session({
            (MODEL, "", day(-30)): bucket(100),   # outside (>14 days before)
            (MODEL, "", day(-14)): bucket(10),    # edge, inside
            (MODEL, "", day(-1)): bucket(20),
            (MODEL, FULL, day(0)): bucket(5),
            (MODEL, FULL, day(3)): bucket(5),
            (MODEL, "", day(17)): bucket(7),      # last_day + 14, inside
            (MODEL, "", day(18)): bucket(1000),   # outside
        })}
        b = model_row(build_experiment_summary(sess, {}))["baseline"]
        self.assertEqual(b["replies"], 10 + 20 + 7)
        self.assertEqual(b["from"], day(-14))
        self.assertEqual(b["to"], day(17))

    def test_baseline_window_clamped_to_observed_model_days(self):
        sess = {"s1": session({
            (MODEL, "", day(-3)): bucket(10),
            (MODEL, FULL, day(0)): bucket(5),
            (MODEL, FULL, day(2)): bucket(5),
            ("other-model", "", day(-40)): bucket(10),
            ("other-model", "", day(40)): bucket(10),
        })}
        b = model_row(build_experiment_summary(sess, {}))["baseline"]
        self.assertEqual(b["from"], day(-3))
        self.assertEqual(b["to"], day(2))

    def test_baseline_window_clamp_uses_other_ids_of_same_model(self):
        sess = {"s1": session({
            (MODEL, FULL, day(0)): bucket(5),
            (MODEL, "aaaa000000000000", day(5)): bucket(5),
        })}
        s = build_experiment_summary(sess, {})
        row = next(e for e in s["ids"] if e["id"] == FULL)["models"][0]
        self.assertEqual(row["baseline"]["from"], day(0))
        self.assertEqual(row["baseline"]["to"], day(5))

    def test_baseline_is_same_model_only_and_merges_sources(self):
        sess = {
            "a": session({(MODEL, "", day(-2)): bucket(30),
                          ("other-model", "", day(-2)): bucket(500),
                          (MODEL, FULL, day(0)): bucket(5)}, source="cortex"),
            "b": session({(MODEL, "", day(-1)): bucket(40)}, source="galatea"),
        }
        b = model_row(build_experiment_summary(sess, {}))["baseline"]
        self.assertEqual(b["replies"], 70)

    def test_json_round_trip_buckets_still_work(self):
        sess = json.loads(json.dumps(changed_corpus()))
        m = model_row(build_experiment_summary(sess, {}))
        self.assertEqual(m["verdict"], "changed")


class IdEntryTest(unittest.TestCase):
    def test_id_entry_aggregates_sources_days_sessions(self):
        sess = {
            "a": session({(MODEL, FULL, day(0)): bucket(5),
                          ("m2", FULL, day(0)): bucket(2)}, source="cortex"),
            "b": session({(MODEL, FULL, day(2)): bucket(7)}, source="galatea"),
            "c": session({(MODEL, "", day(2)): bucket(7)}, source="galatea"),
        }
        s = build_experiment_summary(sess, {})
        e = s["ids"][0]
        self.assertEqual(e["first_day"], day(0))
        self.assertEqual(e["last_day"], day(2))
        self.assertEqual(e["sources"], ["cortex", "galatea"])
        self.assertEqual(e["sessions"], 2)
        self.assertEqual(e["days"], {day(0): {"cortex": 7},
                                     day(2): {"galatea": 7}})
        self.assertEqual([m["model"] for m in e["models"]], [MODEL, "m2"])
        self.assertEqual([m["replies"] for m in e["models"]], [12, 2])
        self.assertEqual((e["models"][0]["first_day"],
                          e["models"][0]["last_day"]), (day(0), day(2)))
        self.assertEqual((e["models"][1]["first_day"],
                          e["models"][1]["last_day"]), (day(0), day(0)))

    def test_ids_newest_first(self):
        sess = {"a": session({(MODEL, "aaaa000000000000", day(0)): bucket(1),
                               (MODEL, "bbbb000000000000", day(5)): bucket(1)})}
        s = build_experiment_summary(sess, {})
        self.assertEqual([e["short"] for e in s["ids"]], ["bbb", "aaa"])

    def test_missing_source_does_not_raise(self):
        sess = {"a": {"experiments": {f"{MODEL}|{FULL}": {day(0): bucket(1)}}}}
        e = build_experiment_summary(sess, {})["ids"][0]
        self.assertEqual(len(e["sources"]), 1)


def slot(model, at, atis, org="org-1", entrypoint="cli"):
    return {"model": model, "entrypoint": entrypoint, "org": org, "at": at,
            "data": {"atis": atis} if atis is not None else {}}


class CurrentAssignmentTest(unittest.TestCase):
    def test_current_assignment(self):
        dc = {"oauthAccount": {"organizationUuid": "org-1"},
              "clientDataCacheSlots": {
                  "a": slot(MODEL, 1_700_000_000_000, ""),
                  "b": slot(MODEL + "[1m]", 1_800_000_000_000,
                            "v1.5ddd0466fd524dad.tXYZ.abc"),
                  "c": slot(MODEL, 1_900_000_000_000, "ffff", org="other"),
              }}
        cur = build_experiment_summary({}, dc)["current"]
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["model"], MODEL)
        self.assertEqual(cur[0]["entrypoint"], "cli")
        self.assertEqual(cur[0]["id"], "5ddd0466fd524dad")
        self.assertTrue(cur[0]["at"].startswith("2027-01-15"))
        self.assertTrue(cur[0]["at"].endswith("Z")
                        or "+00:00" in cur[0]["at"])

    def test_no_org_in_account_keeps_all_slots(self):
        dc = {"clientDataCacheSlots": {
            "a": slot("m1", 1, FULL, org="x"),
            "b": slot("m2", 2, "", org="y")}}
        cur = build_experiment_summary({}, dc)["current"]
        self.assertEqual({c["model"]: c["id"] for c in cur},
                         {"m1": FULL, "m2": ""})

    def test_malformed_slots_give_empty_list(self):
        for bad in ([], "garbage", None, 5,
                    {"a": "x", "b": {"model": MODEL},
                     "c": {"model": MODEL, "at": "nope", "org": "o"}}):
            dc = {"oauthAccount": {"organizationUuid": "org-1"},
                  "clientDataCacheSlots": bad}
            self.assertEqual(build_experiment_summary({}, dc)["current"], [],
                             bad)

    def test_malformed_account_does_not_raise(self):
        for acct in ("x", None, [], {"organizationUuid": 5}):
            dc = {"oauthAccount": acct,
                  "clientDataCacheSlots": {"a": slot("m", 1, FULL)}}
            build_experiment_summary({}, dc)

    def test_slot_without_data_means_no_experiment(self):
        dc = {"clientDataCacheSlots": {
            "a": {"model": "m", "entrypoint": "cli", "org": "o", "at": 5}}}
        cur = build_experiment_summary({}, dc)["current"]
        self.assertEqual(cur[0]["id"], "")

    def test_current_alone_does_not_set_has_data(self):
        dc = {"clientDataCacheSlots": {"a": slot("m", 1, FULL)}}
        self.assertFalse(build_experiment_summary({}, dc)["has_data"])


if __name__ == "__main__":
    unittest.main()
