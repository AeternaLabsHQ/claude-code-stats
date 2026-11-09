"""build_experiment_summary: per-ID behaviour vs an interactive,
effort-matched, time-matched baseline with session-robust significance."""
import json
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core import experiments
from claudestats_core.experiments import (METRICS, add_reply, bucket_key,
                                          build_experiment_summary, hist_bin,
                                          new_bucket, session_experiment_ids)

FULL = "21e0afd842ce5836"
MODEL = "claude-opus-5"
TOOL = {"type": "tool_use", "name": "Read", "input": {}}
TEXT = {"type": "text", "text": "ok"}
READ = {"type": "tool_use", "name": "Read", "input": {}}


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


def session(buckets, source="desktop", start=None, late=None):
    """buckets: {(model, atis, day[, entrypoint, effort]): bucket};
    entrypoint defaults to "cli", effort to "high"."""
    exp = {}
    for key, b in buckets.items():
        model, atis, d, ep, eff = (tuple(key) + ("cli", "high"))[:5]
        exp.setdefault(bucket_key(model, atis, ep, eff), {})[d] = b
    s = {"source": source, "experiments": exp}
    if start is not None:
        s["exp_start_ms"] = start
    if late:
        s["experiments_late"] = late
    return s


def day(offset, base=date(2026, 6, 20)):
    return (base + timedelta(days=offset)).isoformat()


def ms(offset, hour=10):
    d = date(2026, 6, 20) + timedelta(days=offset)
    return int(datetime(d.year, d.month, d.day, hour,
                        tzinfo=timezone.utc).timestamp() * 1000)


def corpus(id_buckets, base_buckets, atis=FULL, model=MODEL,
           id_day=0, base_day=-5, ep="cli", effort="high"):
    """One session per bucket on each side."""
    sess = {}
    for i, b in enumerate(base_buckets):
        sess[f"b{i}"] = session({(model, "", day(base_day), ep, effort): b})
    for i, b in enumerate(id_buckets):
        sess[f"i{i}"] = session({(model, atis, day(id_day), ep, effort): b})
    return sess


def alternating(k, n, a, b, **kw):
    """k sessions of n replies; field values alternate per session.
    a and b are dicts of bucket() keyword arguments."""
    return [bucket(n, **{**kw, **(a if i % 2 == 0 else b)}) for i in range(k)]


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


def changed_corpus():
    """20 sessions per side; multi-tool share doubles and text-first share
    drops, both with session-level noise; Bash and output unchanged."""
    base = alternating(20, 20, {"multi": 0.15, "text_before": 0.15},
                       {"multi": 0.25, "text_before": 0.25})
    ids = alternating(20, 20, {"multi": 0.35, "text_before": 0.05},
                      {"multi": 0.45, "text_before": 0.10})
    return corpus(ids, base)


def card(summary, i=0):
    return summary["ids"][i]["models"][0]


def row(c, key):
    return next(r for r in c["rows"] if r["key"] == key)


class EmptyAndShapeTest(unittest.TestCase):
    def test_empty_inputs(self):
        s = build_experiment_summary({}, {})
        self.assertFalse(s["has_data"])
        self.assertEqual(s["ids"], [])
        self.assertEqual(s["current"], [])
        self.assertEqual(s["thresholds"], {
            "min_replies": 200, "rel_change": 0.4,
            "min_changed_metrics": 2, "baseline_pad_days": 14,
            "min_support": 30, "min_sessions": 5, "alpha": 0.05,
            "late_cutoff_days": 7, "active_gap_min": 30,
            "correction_max_chars": 160, "think_min_replies": 20})
        self.assertIsInstance(s["thresholds"]["active_gap_min"], int)

    def test_constants(self):
        self.assertEqual(experiments.MIN_SESSIONS, 5)
        self.assertEqual(experiments.ALPHA, 0.05)
        self.assertEqual(experiments.MIN_SUPPORT, 30)

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

    def test_card_fields(self):
        c = card(build_experiment_summary(changed_corpus(), {}))
        for k in ("model", "replies", "sessions", "first_day", "last_day",
                  "session_start_from", "session_start_to", "entrypoints",
                  "base_entrypoints", "base_sdk_replies", "effort_mix",
                  "base_effort_mix", "unmatched_replies", "late_replies",
                  "base_late_replies", "baseline", "rows", "verdict",
                  "reason"):
            self.assertIn(k, c)
        for k in ("metrics", "changes", "support"):
            self.assertNotIn(k, c)
        self.assertEqual(set(c["baseline"]), {"replies", "sessions", "from",
                                              "to"})
        for r in c["rows"]:
            self.assertEqual(set(r), {"key", "group", "kind", "base",
                                      "value", "change", "lo", "hi", "p",
                                      "n", "base_n", "supported",
                                      "comparable"})


class RowsTest(unittest.TestCase):
    def test_rows_order_and_groups(self):
        c = card(build_experiment_summary(changed_corpus(), {}))
        expected = [
            ("multi_tool_share", "behaviour"),
            ("text_before_share", "behaviour"),
            ("median_bash_chars", "behaviour"),
            ("median_output_tokens", "behaviour"),
            ("cost_per_reply", "context"),
            ("session_cost", "session"),
            ("session_replies", "session"),
            ("session_prompts", "session"),
            ("session_tool_calls", "session"),
            ("session_active_min", "session"),
            ("cost_per_prompt", "session"),
            ("tool_error_rate", "quality"),
            ("repeat_call_rate", "quality"),
            ("rejected_rate", "quality"),
            ("interrupt_rate", "quality"),
            ("correction_rate", "quality"),
            ("re_edit_rate", "quality"),
        ]
        self.assertEqual([(m["key"], m["group"]) for m in METRICS], expected)
        self.assertEqual([(r["key"], r["group"]) for r in c["rows"]],
                         expected)
        self.assertEqual([r["kind"] for r in c["rows"]],
                         [m["kind"] for m in METRICS])
        for r in c["rows"]:
            if r["group"] != "behaviour":
                self.assertFalse(r["comparable"], r["key"])

    def test_row_values_and_counts(self):
        c = card(build_experiment_summary(changed_corpus(), {}))
        r = row(c, "multi_tool_share")
        self.assertAlmostEqual(r["value"], 0.40, 4)
        self.assertAlmostEqual(r["base"], 0.20, 4)
        self.assertAlmostEqual(r["change"], 1.0, 4)
        self.assertEqual((r["n"], r["base_n"]), (400, 400))
        self.assertTrue(r["comparable"])
        self.assertLess(r["p"], 0.001)
        self.assertLess(r["lo"], 1.0)
        self.assertGreater(r["hi"], 1.0)
        t = row(c, "text_before_share")
        self.assertAlmostEqual(t["value"], 0.075, 4)
        self.assertEqual(t["n"], 400)
        b = row(c, "median_bash_chars")
        self.assertEqual(b["n"], 400)
        self.assertEqual(b["value"], b["base"])
        self.assertAlmostEqual(b["change"], 0.0, 4)
        cost = row(c, "cost_per_reply")
        self.assertAlmostEqual(cost["value"], 0.01, 6)
        self.assertEqual(cost["kind"], "usd")
        sr = row(c, "session_replies")
        self.assertEqual((sr["value"], sr["base"]), (20, 20))
        self.assertEqual((sr["n"], sr["base_n"]), (20, 20))

    def test_rounding(self):
        c = card(build_experiment_summary(changed_corpus(), {}))
        for r in c["rows"]:
            for k in ("change", "lo", "hi"):
                if r[k] is not None:
                    self.assertEqual(r[k], round(r[k], 4))
            if r["p"] is not None:
                self.assertEqual(r["p"], float(f"{r['p']:.3g}"))
            nd = {"share": 4, "rate": 4, "int": 1, "usd": 6}[r["kind"]]
            for k in ("value", "base"):
                if r[k] is not None:
                    self.assertEqual(r[k], round(r[k], nd), r["key"])

    def test_quality_rates_standardized(self):
        def qb(n, errors, calls):
            b = bucket(n, 0.2, 0.2)
            b["tool_calls"], b["tool_errors"] = calls, errors
            return b
        base = [qb(40, 2 + i % 2, 40) for i in range(6)]
        ids = [qb(40, 8 + i % 2, 40) for i in range(6)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        r = row(c, "tool_error_rate")
        self.assertEqual(r["kind"], "rate")
        self.assertAlmostEqual(r["base"], 0.0625, 4)
        self.assertAlmostEqual(r["value"], 0.2125, 4)
        self.assertEqual((r["n"], r["base_n"]), (240, 240))
        self.assertIsNotNone(r["p"])
        self.assertFalse(r["comparable"])

    def test_session_group_uses_all_interactive_replies(self):
        # ID sessions also hold an "xhigh" stratum the baseline never has:
        # outside common support for behaviour, inside for per-session rows.
        sess = {}
        for i, n in enumerate((10, 20, 30, 40, 50)):
            sess[f"i{i}"] = session({
                (MODEL, FULL, day(0), "cli", "high"): bucket(n),
                (MODEL, FULL, day(0), "cli", "xhigh"): bucket(5)})
        for i in range(5):
            sess[f"b{i}"] = session({(MODEL, "", day(-1)): bucket(40)})
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["replies"], 175)
        self.assertEqual(c["unmatched_replies"], 25)
        self.assertEqual(row(c, "session_replies")["value"], 35)
        self.assertEqual(row(c, "session_replies")["base"], 40)
        self.assertEqual(row(c, "multi_tool_share")["n"], 150)
        self.assertEqual(row(c, "cost_per_prompt")["kind"], "usd")


class VerdictTest(unittest.TestCase):
    def test_changed_needs_two_significant_moves(self):
        s = build_experiment_summary(changed_corpus(), {})
        self.assertTrue(s["has_data"])
        e = s["ids"][0]
        self.assertEqual(e["id"], FULL)
        self.assertEqual(e["short"], "21e")
        c = e["models"][0]
        self.assertEqual(c["model"], MODEL)
        self.assertEqual(c["replies"], 400)
        self.assertEqual(c["sessions"], 20)
        self.assertEqual(c["baseline"]["replies"], 400)
        self.assertEqual(c["baseline"]["sessions"], 20)
        self.assertEqual(c["verdict"], "changed")
        self.assertIsNone(c["reason"])

    def test_one_significant_move_is_no_effect(self):
        # The 243 shape: multi-tool share 5% -> 8% with plenty of sessions,
        # everything else unchanged.
        base = alternating(20, 50, {"multi": 0.04, "text_before": 0.18},
                           {"multi": 0.06, "text_before": 0.22})
        ids = alternating(20, 50, {"multi": 0.06, "text_before": 0.18},
                          {"multi": 0.10, "text_before": 0.22})
        c = card(build_experiment_summary(corpus(ids, base), {}))
        r = row(c, "multi_tool_share")
        self.assertAlmostEqual(r["change"], 0.6, 4)
        self.assertLess(r["p"], 0.05)
        self.assertTrue(all(row(c, k)["comparable"] for k in (
            "multi_tool_share", "text_before_share", "median_bash_chars",
            "median_output_tokens")))
        self.assertEqual(c["verdict"], "no_effect")
        self.assertIsNone(c["reason"])

    def test_large_move_without_significance_is_not_changed(self):
        lo_hi = (0.1, 0.5, 0.1, 0.5, 0.3)
        wild = (0.0, 1.0, 0.0, 1.0, 1.0)
        base = [bucket(50, v, v) for v in lo_hi]
        ids = [bucket(50, v, v) for v in wild]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        for k in ("multi_tool_share", "text_before_share"):
            r = row(c, k)
            self.assertGreaterEqual(abs(r["change"]), 0.4, k)
            self.assertGreaterEqual(r["p"], 0.05, k)
            self.assertTrue(r["comparable"], k)
        self.assertEqual(c["verdict"], "no_effect")
        self.assertIsNone(c["reason"])

    def test_few_sessions_is_insufficient(self):
        # The 45a case: plenty of replies, but from 3 sessions only.
        base = alternating(20, 20, {"multi": 0.15}, {"multi": 0.25})
        ids = [bucket(100, 0.5, 0.0, 900, 1500) for _ in range(3)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        self.assertEqual(c["replies"], 300)
        self.assertEqual(c["sessions"], 3)
        self.assertEqual(c["verdict"], "insufficient")
        self.assertEqual(c["reason"], "few_sessions")

    def test_few_baseline_sessions_is_insufficient(self):
        base = [bucket(100, 0.2, 0.2) for _ in range(4)]
        ids = alternating(20, 20, {"multi": 0.35}, {"multi": 0.45})
        c = card(build_experiment_summary(corpus(ids, base), {}))
        self.assertEqual(c["reason"], "few_sessions")

    def test_insufficient_when_small_baseline(self):
        base = alternating(10, 15, {"multi": 0.2}, {"multi": 0.2})
        ids = alternating(20, 20, {"multi": 0.35}, {"multi": 0.45})
        c = card(build_experiment_summary(corpus(ids, base), {}))
        self.assertEqual(c["baseline"]["replies"], 150)
        self.assertEqual(c["verdict"], "insufficient")
        self.assertEqual(c["reason"], "few_replies")

    def test_insufficient_when_few_replies(self):
        base = alternating(20, 20, {"multi": 0.15}, {"multi": 0.25})
        ids = [bucket(19, 0.4)] * 10 + [bucket(9, 0.4)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        self.assertEqual(c["replies"], 199)
        self.assertEqual(c["reason"], "few_replies")

    def test_no_baseline_at_all(self):
        sess = {f"i{i}": session({(MODEL, FULL, day(0)): bucket(60, 0.4)})
                for i in range(6)}
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["verdict"], "insufficient")
        self.assertEqual(c["reason"], "few_replies")
        self.assertEqual(c["baseline"]["replies"], 0)
        self.assertEqual(c["baseline"]["sessions"], 0)
        self.assertIsNone(row(c, "median_bash_chars")["base"])
        self.assertIsNone(row(c, "multi_tool_share")["change"])

    def test_zero_baseline_metric_gives_none_change(self):
        base = [bucket(50, 0.0, 0.2) for _ in range(6)]
        ids = [bucket(50, 0.4, 0.2) for _ in range(6)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        r = row(c, "multi_tool_share")
        self.assertEqual(r["base"], 0.0)
        self.assertIsNone(r["change"])
        self.assertIsNone(r["lo"])
        # A move away from zero has no relative change: not judged.
        self.assertFalse(r["comparable"])

    def test_verdict_uses_rounded_row_values(self):
        c = card(build_experiment_summary(changed_corpus(), {}))
        moved = [r for r in c["rows"] if r["group"] == "behaviour"
                 and r["comparable"] and r["change"] is not None
                 and abs(r["change"]) >= 0.4 and r["p"] is not None
                 and r["p"] < 0.05]
        self.assertEqual(len(moved), 2)


class SupportFloorTest(unittest.TestCase):
    def sparse_corpus(self):
        # Rare events on both sides: multi-tool share doubles and Bash
        # commands are twice as long, but 10/8 and 4/3 events are noise.
        base = [mixed_bucket(200, 2, 2 if i < 4 else 0, bash_len=300)
                for i in range(5)]
        ids = [mixed_bucket(40, 1 if i < 4 else 0, 1 if i < 3 else 0,
                            bash_len=650) for i in range(5)]
        return corpus(ids, base)

    def test_sparse_events_are_not_comparable(self):
        c = card(build_experiment_summary(self.sparse_corpus(), {}))
        self.assertFalse(row(c, "multi_tool_share")["comparable"])
        self.assertFalse(row(c, "median_bash_chars")["comparable"])
        self.assertTrue(row(c, "text_before_share")["comparable"])
        self.assertTrue(row(c, "median_output_tokens")["comparable"])
        self.assertEqual(row(c, "multi_tool_share")["n"], 200)
        self.assertEqual(row(c, "median_bash_chars")["n"], 3)
        self.assertEqual(row(c, "median_bash_chars")["base_n"], 8)
        # Values are still reported.
        self.assertAlmostEqual(row(c, "multi_tool_share")["value"], 0.02, 4)
        self.assertIsNotNone(row(c, "median_bash_chars")["value"])
        self.assertEqual(c["verdict"], "no_effect")

    def test_context_and_quality_rows_need_events(self):
        # Rate rows need MIN_SUPPORT events in the larger numerator and in
        # the smaller denominator; cost rows only in the denominator.
        # Withheld rows keep their values but no change, CI or p.
        def qb(n, errors, calls, prompts, interrupts):
            b = bucket(n, 0.2, 0.2)
            b["tool_calls"], b["tool_errors"] = calls, errors
            b["prompts"], b["interrupts"] = prompts, interrupts
            return b
        base = [qb(40, i % 2, 40, 10, 1 + i % 2) for i in range(6)]
        ids = [qb(40, 2 + i % 2, 40, 4 + i % 2, 3) for i in range(6)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        err = row(c, "tool_error_rate")      # 3 vs 15 errors: too few
        self.assertEqual((err["n"], err["base_n"]), (240, 240))
        self.assertFalse(err["supported"])
        self.assertAlmostEqual(err["base"], 0.0125, 4)
        self.assertAlmostEqual(err["value"], 0.0625, 4)
        for k in ("change", "lo", "hi", "p"):
            self.assertIsNone(err[k], k)
        intr = row(c, "interrupt_rate")      # 9 vs 18 interrupts: too few
        self.assertFalse(intr["supported"])
        self.assertIsNone(intr["p"])
        cpp = row(c, "cost_per_prompt")      # 27 prompts on the ID side
        self.assertEqual((cpp["n"], cpp["base_n"]), (27, 60))
        self.assertFalse(cpp["supported"])
        self.assertIsNone(cpp["change"])
        self.assertIsNotNone(cpp["value"])
        cpr = row(c, "cost_per_reply")       # 240 replies each: enough
        self.assertTrue(cpr["supported"])
        self.assertIsNotNone(cpr["change"])
        self.assertFalse(cpr["comparable"])
        # Per-session medians have no event floor.
        self.assertTrue(row(c, "session_replies")["supported"])

    def test_rate_row_with_enough_events_keeps_change(self):
        def qb(n, errors, prompts):
            b = bucket(n, 0.2, 0.2)
            b["tool_calls"], b["tool_errors"] = n, errors
            b["prompts"] = prompts
            return b
        base = [qb(40, 1 + i % 2, 6) for i in range(6)]
        ids = [qb(40, 5 + i % 2, 5) for i in range(6)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        err = row(c, "tool_error_rate")      # 33 vs 9 errors, 240 calls
        self.assertTrue(err["supported"])
        self.assertIsNotNone(err["change"])
        self.assertIsNotNone(err["p"])
        cpp = row(c, "cost_per_prompt")      # 30 vs 36 prompts
        self.assertTrue(cpp["supported"])
        self.assertIsNotNone(cpp["p"])

    def test_behaviour_rows_report_support(self):
        c = card(build_experiment_summary(self.sparse_corpus(), {}))
        self.assertFalse(row(c, "median_bash_chars")["supported"])
        self.assertTrue(row(c, "median_output_tokens")["supported"])
        # Behaviour rows keep change and p; the UI hides them.
        self.assertIsNotNone(row(c, "median_bash_chars")["change"])

    def test_insufficient_when_too_few_metrics_can_be_judged(self):
        # Mostly text-only replies: only the output-token median can be
        # compared, one metric is fewer than MIN_CHANGED_METRICS.
        base = [mixed_bucket(200, 0, 1, plain=198) for _ in range(5)]
        ids = [mixed_bucket(60, 0, 1, plain=58, out=2000) for _ in range(5)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        judged = [r["key"] for r in c["rows"] if r["comparable"]]
        self.assertEqual(judged, ["median_output_tokens"])
        self.assertEqual(c["verdict"], "insufficient")
        self.assertEqual(c["reason"], "few_metrics")

    def test_text_before_needs_tool_replies_on_both_sides(self):
        base = [mixed_bucket(200, 20, 100) for _ in range(5)]
        ids = [mixed_bucket(60, 0, 6 if i < 4 else 5, plain=60)
               for i in range(5)]
        c = card(build_experiment_summary(corpus(ids, base), {}))
        r = row(c, "text_before_share")
        self.assertEqual(r["n"], 29)
        self.assertFalse(r["comparable"])


class EntrypointAndEffortTest(unittest.TestCase):
    def test_sdk_replies_excluded_from_both_sides(self):
        sess = corpus(
            alternating(10, 30, {"multi": 0.2}, {"multi": 0.3}),
            alternating(10, 30, {"multi": 0.1}, {"multi": 0.2}))
        for i in range(10):
            sess[f"sdk{i}"] = session(
                {(MODEL, "", day(-3), "sdk-py", "high"): bucket(50, 0.9)})
        sess["idsdk"] = session(
            {(MODEL, FULL, day(0), "sdk-ts", "high"): bucket(70, 0.9)})
        s = build_experiment_summary(sess, {})
        c = card(s)
        self.assertAlmostEqual(row(c, "multi_tool_share")["base"], 0.15, 4)
        self.assertAlmostEqual(row(c, "multi_tool_share")["value"], 0.25, 4)
        self.assertEqual(c["base_sdk_replies"], 500)
        self.assertEqual(c["baseline"]["replies"], 300)
        self.assertEqual(c["baseline"]["sessions"], 10)
        self.assertEqual(c["replies"], 300)
        self.assertEqual(c["sessions"], 10)
        self.assertEqual(c["entrypoints"], {"cli": 300})
        self.assertEqual(c["base_entrypoints"], {"cli": 300})
        # The per-ID timeline still counts every reply.
        self.assertEqual(s["ids"][0]["sessions"], 11)
        self.assertEqual(sum(s["ids"][0]["days"][day(0)].values()), 370)

    def test_sdk_only_id_gets_no_card(self):
        sess = {"a": session(
            {(MODEL, FULL, day(0), "sdk-py", "high"): bucket(10)})}
        e = build_experiment_summary(sess, {})["ids"][0]
        self.assertEqual(e["models"], [])
        self.assertEqual(e["sessions"], 1)

    def test_effort_standardization(self):
        sess = {}
        for i in range(10):
            sess[f"b{i}"] = session({
                (MODEL, "", day(-2), "cli", "high"): bucket(30, 0.4),
                (MODEL, "", day(-2), "cli", "medium"): bucket(30, 0.0)})
        for i in range(10):
            sess[f"i{i}"] = session({
                (MODEL, FULL, day(0), "cli", "high"): bucket(30, 0.4)})
        c = card(build_experiment_summary(sess, {}))
        r = row(c, "multi_tool_share")
        self.assertEqual(r["base"], 0.4)
        self.assertEqual(r["value"], 0.4)
        self.assertEqual(r["change"], 0.0)
        self.assertEqual(c["effort_mix"], {"high": 300})
        self.assertEqual(c["base_effort_mix"], {"high": 300, "medium": 300})
        self.assertEqual(c["unmatched_replies"], 0)
        self.assertEqual(c["baseline"]["replies"], 600)

    def test_effort_weights_follow_id_mix(self):
        # ID side 75% high / 25% medium, baseline 50/50: the baseline is
        # reweighted to 0.75 * 0.4 + 0.25 * 0.0 = 0.3 (pooled would be 0.2).
        sess = {}
        for i in range(10):
            sess[f"b{i}"] = session({
                (MODEL, "", day(-2), "cli", "high"): bucket(30, 0.4),
                (MODEL, "", day(-2), "cli", "medium"): bucket(30, 0.0)})
            sess[f"i{i}"] = session({
                (MODEL, FULL, day(0), "cli", "high"): bucket(30, 0.4),
                (MODEL, FULL, day(0), "cli", "medium"): bucket(10, 0.0)})
        c = card(build_experiment_summary(sess, {}))
        self.assertAlmostEqual(row(c, "multi_tool_share")["base"], 0.3, 4)
        self.assertAlmostEqual(row(c, "multi_tool_share")["value"], 0.3, 4)

    def test_unknown_effort_is_its_own_stratum(self):
        sess = {}
        for i in range(10):
            sess[f"b{i}"] = session({
                (MODEL, "", day(-2), "cli", ""): bucket(30, 0.0),
                (MODEL, "", day(-2), "cli", "high"): bucket(30, 0.6)})
            sess[f"i{i}"] = session({
                (MODEL, FULL, day(0), "cli", ""): bucket(30, 0.1)})
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["effort_mix"], {"unknown": 300})
        self.assertEqual(c["base_effort_mix"], {"high": 300, "unknown": 300})
        self.assertEqual(c["unmatched_replies"], 0)
        self.assertEqual(row(c, "multi_tool_share")["base"], 0.0)
        self.assertEqual(row(c, "multi_tool_share")["n"], 300)
        self.assertEqual(row(c, "multi_tool_share")["base_n"], 300)

    def test_no_common_effort_support(self):
        sess = corpus(alternating(10, 30, {"multi": 0.2}, {"multi": 0.3}),
                      [], effort="xhigh")
        sess.update({f"b{i}": session(
            {(MODEL, "", day(-2), "cli", "medium"): bucket(30, 0.1)})
            for i in range(10)})
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["verdict"], "insufficient")
        self.assertEqual(c["reason"], "few_replies")
        self.assertEqual(c["unmatched_replies"], 300)
        self.assertEqual(c["replies"], 300)
        for r in c["rows"]:
            if r["group"] in ("behaviour", "context", "quality"):
                self.assertIsNone(r["value"], r["key"])
                self.assertIsNone(r["base"], r["key"])
                self.assertFalse(r["comparable"])
        self.assertEqual(row(c, "session_replies")["value"], 30)

    def test_baseline_stratum_without_denominator_is_dropped_for_row(self):
        # A common stratum where the baseline has replies but no Bash
        # commands: the Bash median of both sides leaves that stratum out,
        # every other row keeps it.
        sess = {}
        for i in range(10):
            sess[f"b{i}"] = session({
                (MODEL, "", day(-2), "cli", "high"): bucket(30, 0.2),
                (MODEL, "", day(-2), "cli", "low"):
                    mixed_bucket(3, 0, 0)})
            sess[f"i{i}"] = session({
                (MODEL, FULL, day(0), "cli", "high"): bucket(30, 0.2),
                (MODEL, FULL, day(0), "cli", "low"): bucket(3, 0.0)})
        c = card(build_experiment_summary(sess, {}))
        r = row(c, "median_bash_chars")
        self.assertIsNotNone(r["base"])
        self.assertEqual(r["value"], r["base"])
        self.assertEqual(r["change"], 0.0)
        self.assertEqual((r["n"], r["base_n"]), (300, 300))
        self.assertTrue(r["comparable"])
        m = row(c, "multi_tool_share")
        self.assertEqual((m["n"], m["base_n"]), (330, 330))

    def test_identical_populations_show_no_change(self):
        # Two effort levels with very different tool-reply, text-first,
        # Bash-length and tool-error profiles, the same 50/50 mix and the
        # same generators on both sides: every row must read "no change".
        def bash(n):
            return {"type": "tool_use", "name": "Bash",
                    "input": {"command": "x" * n}}

        def high(j):
            b = new_bucket()
            for i in range(30):
                add_reply(b, ([TEXT] if i < 18 + j % 2 else []) + [bash(1000)]
                          + ([READ] if i % 3 == 0 else []), 450, 0.01)
            b["tool_errors"] = 10 + j % 2
            return b

        def medium(j):
            b = new_bucket()
            for i in range(30):
                add_reply(b, [bash(100)] if i < 6 + j % 2 else [TEXT], 450,
                          0.01)
            return b

        sess = {}
        for j in range(20):
            for side, atis, d in (("b", "", day(-5)), ("i", FULL, day(0))):
                sess[f"{side}{j}"] = session({
                    (MODEL, atis, d, "cli", "high"): high(j),
                    (MODEL, atis, d, "cli", "medium"): medium(j)})
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["effort_mix"], {"high": 600, "medium": 600})
        for k in ("multi_tool_share", "text_before_share",
                  "median_bash_chars", "median_output_tokens",
                  "cost_per_reply", "tool_error_rate"):
            r = row(c, k)
            self.assertIsNotNone(r["change"], k)
            self.assertLess(abs(r["change"]), 0.02, k)
            self.assertEqual(r["value"], r["base"], k)
            if r["p"] is not None:
                self.assertGreater(r["p"], 0.05, k)
        self.assertEqual(c["verdict"], "no_effect")
        self.assertIsNone(c["reason"])

    def test_row_weights_follow_id_denominator_mix(self):
        # Text-first share: ID side has its tool replies 75% in high (share
        # 0.6) and 25% in medium (share 0.0); the baseline is 50/50 in tool
        # replies. Reweighted per row: 0.75 * 0.6 = 0.45 on both sides.
        # The ID medium level also has 30 text-only replies, so reply-share
        # weights (3/7 high) would give a different baseline (0.257).
        def tb(n, share, plain=0):
            b = bucket(n, 0.0, share)
            for _ in range(plain):
                add_reply(b, [TEXT], 450, 0.01)
            return b
        sess = {}
        for i in range(10):
            sess[f"i{i}"] = session({
                (MODEL, FULL, day(0), "cli", "high"): tb(30, 0.6),
                (MODEL, FULL, day(0), "cli", "medium"): tb(10, 0.0, 30)})
            sess[f"b{i}"] = session({
                (MODEL, "", day(-2), "cli", "high"): tb(20, 0.6),
                (MODEL, "", day(-2), "cli", "medium"): tb(20, 0.0)})
        r = row(card(build_experiment_summary(sess, {})), "text_before_share")
        self.assertEqual(r["value"], 0.45)
        self.assertEqual(r["base"], 0.45)
        self.assertEqual(r["change"], 0.0)

    def test_id_side_uses_the_row_weights(self):
        # Effort-pure ID sessions with very different rates per level. The
        # ID side's own denominator shares are the row weights, so its
        # estimate equals the pooled one. Both sides are standardized to the
        # same realized weights, so the effort mix cancels in the contrast:
        # the ID side's error is the weighted one (weights held fixed),
        # not the pooled one, which would count the mix a second time.
        from claudestats_core.expstats import (compare, median_stat,
                                               ratio_stat)
        ids, base, sess = [], [], {}
        for i in range(12):
            eff = "high" if i < 6 else "medium"
            multi = (0.5 if i % 2 else 0.4) if eff == "high" else (
                0.1 if i % 2 else 0.0)
            out = (900 if i % 2 else 700) if eff == "high" else (
                300 if i % 2 else 200)
            b = bucket(30, multi, 0.2, out=out)
            ids.append((eff, b))
            sess[f"i{i}"] = session({(MODEL, FULL, day(0), "cli", eff): b})
        for i in range(8):
            hb = bucket(20, 0.3 + 0.1 * (i % 2), 0.2, out=600 + 100 * (i % 2))
            mb = bucket(20, 0.05 * (i % 2), 0.2, out=250)
            base.append({"high": hb, "medium": mb})
            sess[f"b{i}"] = session({
                (MODEL, "", day(-2), "cli", "high"): hb,
                (MODEL, "", day(-2), "cli", "medium"): mb})
        c = card(build_experiment_summary(sess, {}))
        w = {"high": 0.5, "medium": 0.5}  # ID replies 180 / 180

        pooled = ratio_stat([{e: (b["multi_tool"], b["replies"])}
                             for e, b in ids])
        a = ratio_stat([{e: (b["multi_tool"], b["replies"])}
                        for e, b in ids], w)
        bb = ratio_stat([{e: (b["multi_tool"], b["replies"])
                          for e, b in u.items()} for u in base], w)
        self.assertAlmostEqual(a["est"], pooled["est"], 12)
        self.assertLess(a["se"], pooled["se"])
        r = row(c, "multi_tool_share")
        self.assertAlmostEqual(r["value"], round(pooled["est"], 4), 9)
        cr = compare(a, bb, "ratio")
        self.assertNotEqual(float(f"{cr['p']:.3g}"),
                            float(f"{compare(pooled, bb, 'ratio')['p']:.3g}"))
        self.assertEqual(r["p"], float(f"{cr['p']:.3g}"))
        self.assertEqual((r["lo"], r["hi"]),
                         (round(cr["lo"], 4), round(cr["hi"], 4)))

        steps = experiments.HIST_STEPS
        pooled = median_stat([{e: b["out_hist"]} for e, b in ids],
                             steps=steps)
        a = median_stat([{e: b["out_hist"]} for e, b in ids], w, steps=steps)
        bb = median_stat([{e: b["out_hist"] for e, b in u.items()}
                          for u in base], w, steps=steps)
        r = row(c, "median_output_tokens")
        self.assertAlmostEqual(r["value"], round(pooled["est"], 1), 9)
        cm = compare(a, bb, "median")
        self.assertEqual(r["p"], float(f"{cm['p']:.3g}"))
        self.assertEqual((r["lo"], r["hi"]),
                         (round(cm["lo"], 4), round(cm["hi"], 4)))

    def test_standardized_row_holds_its_size_under_the_null(self):
        # Effort-pure sessions, rates 0.5 (high) and 0.05 (medium) on both
        # sides, ID mix 50/50, baseline mix 30/70: no effect. At alpha 0.05
        # the row must reject about 5% of the time (a pooled ID-side error
        # double-counts the effort mix and almost never rejects).
        import random
        rng = random.Random(20261109)
        rates = {"high": 0.5, "medium": 0.05}
        m = next(x for x in METRICS if x["key"] == "multi_tool_share")

        def side(n, p_high):
            units = []
            for _ in range(n):
                e = "high" if rng.random() < p_high else "medium"
                k = sum(rng.random() < rates[e] for _ in range(10))
                units.append({e: {"replies": 10, "multi_tool": k}})
            return {"all": units, "totals": []}

        reps, hits = 300, 0
        for _ in range(reps):
            r = experiments._metric_row(m, side(40, 0.5), side(80, 0.3))
            hits += r["p"] is not None and r["p"] < 0.05
        self.assertGreaterEqual(hits / reps, 0.01)
        self.assertLessEqual(hits / reps, 0.12)

    def test_identical_bins_are_not_shared_data(self):
        self.assertEqual(hist_bin(300), hist_bin(303))
        self.assertNotEqual(hist_bin(300), hist_bin(450))
        ids = [bucket(40, 0.2, 0.2, bash_len=300) for _ in range(5)]
        same = card(build_experiment_summary(corpus(
            ids, [bucket(40, 0.2, 0.2, bash_len=303) for _ in range(7)]),
            {}))
        diff = card(build_experiment_summary(corpus(
            ids, [bucket(40, 0.2, 0.2, bash_len=450) for _ in range(7)]),
            {}))
        self.assertEqual((same["sessions"], same["baseline"]["sessions"]),
                         (5, 7))
        self.assertEqual((diff["sessions"], diff["baseline"]["sessions"]),
                         (5, 7))
        s, d = row(same, "median_bash_chars"), row(diff, "median_bash_chars")
        self.assertEqual(s["value"], s["base"])
        self.assertEqual(s["value"], d["value"])
        self.assertNotEqual(d["value"], d["base"])
        self.assertGreater(d["base"], 400)
        self.assertLess(d["value"], 310)


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
        b = card(build_experiment_summary(sess, {}))["baseline"]
        self.assertEqual(b["replies"], 10 + 20 + 7)
        self.assertEqual(b["sessions"], 1)
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
        b = card(build_experiment_summary(sess, {}))["baseline"]
        self.assertEqual(b["from"], day(-3))
        self.assertEqual(b["to"], day(2))

    def test_baseline_window_clamp_uses_other_ids_of_same_model(self):
        sess = {"s1": session({
            (MODEL, FULL, day(0)): bucket(5),
            (MODEL, "aaaa000000000000", day(5)): bucket(5),
        })}
        s = build_experiment_summary(sess, {})
        c = next(e for e in s["ids"] if e["id"] == FULL)["models"][0]
        self.assertEqual(c["baseline"]["from"], day(0))
        self.assertEqual(c["baseline"]["to"], day(5))

    def test_baseline_is_same_model_only_and_merges_sources(self):
        sess = {
            "a": session({(MODEL, "", day(-2)): bucket(30),
                          ("other-model", "", day(-2)): bucket(500),
                          (MODEL, FULL, day(0)): bucket(5)}, source="desktop"),
            "b": session({(MODEL, "", day(-1)): bucket(40)}, source="laptop"),
        }
        b = card(build_experiment_summary(sess, {}))["baseline"]
        self.assertEqual(b["replies"], 70)
        self.assertEqual(b["sessions"], 2)

    def test_json_round_trip_buckets_still_work(self):
        sess = json.loads(json.dumps(changed_corpus()))
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["verdict"], "changed")
        json.dumps(build_experiment_summary(sess, {}))

    def test_legacy_two_part_keys(self):
        sess = {f"s{i}": {"experiments": {
            f"{MODEL}|{FULL}": {day(0): bucket(10)},
            f"{MODEL}|": {day(-1): bucket(10)}}} for i in range(3)}
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["effort_mix"], {"unknown": 30})
        self.assertEqual(c["entrypoints"], {"": 30})
        self.assertEqual(c["baseline"]["replies"], 30)


class SessionStartAndLateTest(unittest.TestCase):
    def test_session_start_range_and_late_counts(self):
        ikey = bucket_key(MODEL, FULL, "cli", "high")
        isdk = bucket_key(MODEL, FULL, "sdk-py", "high")
        bkey = bucket_key(MODEL, "", "cli", "high")
        sess = {
            "i0": session({(MODEL, FULL, day(0)): bucket(5)},
                          start=ms(-1), late={ikey: 4, isdk: 100}),
            "i1": session({(MODEL, FULL, day(2)): bucket(5)},
                          start=ms(2, 23)),
            "i2": session({(MODEL, FULL, day(3)): bucket(5),
                           (MODEL, FULL, day(4)): bucket(5)}),
            "b0": session({(MODEL, "", day(-1)): bucket(5)},
                          late={bkey: 3, ikey: 1}),
            "b1": session({(MODEL, "", day(-40)): bucket(5)},
                          late={bkey: 50}),
            "b2": session({(MODEL, "", day(30)): bucket(5)}),
        }
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["session_start_from"], day(-1))
        self.assertEqual(c["session_start_to"], day(3))
        self.assertEqual(c["late_replies"], 5)
        self.assertEqual(c["base_late_replies"], 3)
        self.assertEqual((c["first_day"], c["last_day"]), (day(0), day(4)))

    def test_bad_start_falls_back_to_first_day(self):
        sess = {"i0": session({(MODEL, FULL, day(1)): bucket(5),
                               (MODEL, FULL, day(2)): bucket(5)},
                              start="nope")}
        c = card(build_experiment_summary(sess, {}))
        self.assertEqual(c["session_start_from"], day(1))
        self.assertEqual(c["session_start_to"], day(1))
        self.assertEqual(c["late_replies"], 0)
        self.assertEqual(c["base_late_replies"], 0)


class IdEntryTest(unittest.TestCase):
    def test_id_entry_aggregates_sources_days_sessions(self):
        sess = {
            "a": session({(MODEL, FULL, day(0)): bucket(5),
                          ("m2", FULL, day(0)): bucket(2)}, source="desktop"),
            "b": session({(MODEL, FULL, day(2)): bucket(7)}, source="laptop"),
            "c": session({(MODEL, "", day(2)): bucket(7)}, source="laptop"),
        }
        s = build_experiment_summary(sess, {})
        e = s["ids"][0]
        self.assertEqual(e["first_day"], day(0))
        self.assertEqual(e["last_day"], day(2))
        self.assertEqual(e["sources"], ["desktop", "laptop"])
        self.assertEqual(e["sessions"], 2)
        self.assertEqual(e["days"], {day(0): {"desktop": 7},
                                     day(2): {"laptop": 7}})
        self.assertEqual([m["model"] for m in e["models"]], [MODEL, "m2"])
        self.assertEqual([m["replies"] for m in e["models"]], [12, 2])
        self.assertEqual([m["sessions"] for m in e["models"]], [2, 1])
        self.assertEqual((e["models"][0]["first_day"],
                          e["models"][0]["last_day"]), (day(0), day(2)))
        self.assertEqual((e["models"][1]["first_day"],
                          e["models"][1]["last_day"]), (day(0), day(0)))

    def test_ids_newest_first(self):
        sess = {"a": session({(MODEL, "aaaa000000000000", day(0)): bucket(1),
                               (MODEL, "bbbb000000000000", day(5)): bucket(1)})}
        s = build_experiment_summary(sess, {})
        self.assertEqual([e["short"] for e in s["ids"]], ["bbb", "aaa"])

    def test_short_prefix_unique(self):
        ids = ("abc1000000000000", "abc2000000000000", "fff0000000000000")
        sess = {"a": session({(MODEL, a, day(i)): bucket(1)
                              for i, a in enumerate(ids)})}
        s = build_experiment_summary(sess, {})
        self.assertEqual({e["id"]: e["short"] for e in s["ids"]},
                         {ids[0]: "abc1", ids[1]: "abc2", ids[2]: "fff"})

    def test_short_prefix_when_one_id_prefixes_another(self):
        ids = ("abcd", "abcdef")
        sess = {"a": session({(MODEL, a, day(i)): bucket(1)
                              for i, a in enumerate(ids)})}
        s = build_experiment_summary(sess, {})
        self.assertEqual({e["id"]: e["short"] for e in s["ids"]},
                         {"abcd": "abcd", "abcdef": "abcde"})

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


def think_bucket(values, plain=0):
    """Replies that reported thinking tokens (one per value) plus `plain`
    replies without the field."""
    b = new_bucket()
    for v in values:
        add_reply(b, [TEXT], 50, 0.01, thinking_tokens=v)
    for _ in range(plain):
        add_reply(b, [TEXT], 50, 0.01)
    return b


OTHER = "ffffeeee11112222"


class ThinkingTable(unittest.TestCase):
    def thinking(self, sess):
        return build_experiment_summary(sess, {})["thinking"]

    def test_thinking_table_cells(self):
        sess = {
            "a": session({(MODEL, "", day(0), "cli", "high"):
                          think_bucket([100] * 20),
                          (MODEL, "", day(0), "cli", "low"):
                          think_bucket([10, 30] * 10),
                          (MODEL, "", day(0), "cli", ""):
                          think_bucket([40] * 25)}),
            "b": session({(MODEL, FULL, day(1), "cli", "high"):
                          think_bucket([200] * 12),
                          (MODEL, FULL, day(2), "cli", "high"):
                          think_bucket([400] * 8)}),
            "c": session({(MODEL, OTHER, day(3), "cli", "max"):
                          think_bucket([1000] * 20)}),
        }
        t = self.thinking(sess)
        self.assertEqual([m["model"] for m in t], [MODEL])
        rows = t[0]["rows"]
        self.assertEqual([r["id"] for r in rows], ["", OTHER, FULL])
        self.assertEqual(rows[0]["short"], "")
        ids = {i["id"]: i["short"]
               for i in build_experiment_summary(sess, {})["ids"]}
        self.assertEqual(rows[1]["short"], ids[OTHER])
        self.assertEqual(rows[2]["short"], ids[FULL])
        # no ID: effort order low, high, unknown
        self.assertEqual(list(rows[0]["cells"]), ["low", "high", "unknown"])
        low = rows[0]["cells"]["low"]
        self.assertEqual(low["replies"], 20)
        self.assertEqual(low["mean"], 20.0)
        self.assertAlmostEqual(
            low["median"],
            round(experiments.hist_median(
                {hist_bin(10): 10, hist_bin(30): 10}), 1))
        self.assertEqual(rows[0]["cells"]["unknown"]["mean"], 40.0)
        # cells merge across sessions and days
        cell = rows[2]["cells"]["high"]
        self.assertEqual(cell["replies"], 20)
        self.assertEqual(cell["mean"], 280.0)
        self.assertEqual(list(rows[1]["cells"]), ["max"])

    def test_thinking_nonzero_share(self):
        sess = {"a": session({
            (MODEL, "", day(0), "cli", "high"):
                think_bucket([0] * 15 + [100] * 5),
            (MODEL, "", day(0), "cli", "low"): think_bucket([50] * 20),
            (MODEL, "", day(0), "cli", "max"): think_bucket([0] * 20)}),
            "b": session({(MODEL, FULL, day(1), "cli", "high"):
                          think_bucket([5] * 3)})}
        cells = self.thinking(sess)[0]["rows"][0]["cells"]
        self.assertEqual(cells["high"]["nonzero_share"], 0.25)
        self.assertEqual(cells["low"]["nonzero_share"], 1.0)
        self.assertEqual(cells["max"]["nonzero_share"], 0.0)
        self.assertEqual(cells["max"]["median"], 0.0)

    def test_thinking_nonzero_share_rounded(self):
        sess = {"a": session({
            (MODEL, "", day(0), "cli", "high"):
                think_bucket([0] * 20 + [7])}),
            "b": session({(MODEL, FULL, day(1), "cli", "high"):
                          think_bucket([5] * 3)})}
        cell = self.thinking(sess)[0]["rows"][0]["cells"]["high"]
        self.assertEqual(cell["nonzero_share"], round(1 / 21, 4))

    def test_thinking_skips_replies_without_field(self):
        sess = {
            "a": session({(MODEL, "", day(0)): think_bucket([100] * 20, 50)}),
            "b": session({(MODEL, FULL, day(0)): think_bucket([100], 5)}),
        }
        t = self.thinking(sess)
        cell = t[0]["rows"][0]["cells"]["high"]
        self.assertEqual(cell["replies"], 20)
        self.assertEqual(cell["mean"], 100.0)

    def test_thinking_cell_floor(self):
        sess = {
            "a": session({(MODEL, "", day(0), "cli", "high"):
                          think_bucket([100] * 19),
                          (MODEL, "", day(0), "cli", "low"):
                          think_bucket([100] * 20)}),
            "b": session({(MODEL, FULL, day(0), "cli", "high"):
                          think_bucket([100] * 19)}),
            "c": session({("claude-other", "", day(0), "cli", "high"):
                          think_bucket([100] * 40),
                          ("claude-other", OTHER, day(0), "sdk-cli", "high"):
                          think_bucket([100] * 40)}),
        }
        t = self.thinking(sess)
        # FULL row has no cell above the floor, claude-other has no card
        self.assertEqual([m["model"] for m in t], [MODEL])
        rows = t[0]["rows"]
        self.assertEqual([r["id"] for r in rows], [""])
        self.assertEqual(list(rows[0]["cells"]), ["low"])

    def test_thinking_interactive_only(self):
        sess = {
            "a": session({(MODEL, "", day(0), "sdk-cli", "high"):
                          think_bucket([100] * 30)}),
            "b": session({(MODEL, FULL, day(0), "cli", "high"):
                          think_bucket([100] * 30)}),
        }
        rows = self.thinking(sess)[0]["rows"]
        self.assertEqual([r["id"] for r in rows], [FULL])

    def test_thinking_empty(self):
        self.assertEqual(self.thinking({}), [])


if __name__ == "__main__":
    unittest.main()
