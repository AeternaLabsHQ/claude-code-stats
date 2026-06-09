"""Unit tests for plan-limit calibration & recommendation fixes."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _dedupe_limit_events


def _ev(ts, subtype="user_plan_limit", typ="explicit", sid="s1", **kw):
    e = {"type": typ, "subtype": subtype, "timestamp": ts, "session_id": sid}
    e.update(kw)
    return e


def test_dedupe_exact_duplicates_collapse():
    evs = [_ev("2026-03-27T14:54:04.081Z"), _ev("2026-03-27T14:54:04.081Z")]
    out = _dedupe_limit_events(evs)
    assert len(out) == 1
    assert out[0]["merged_count"] == 2


def test_dedupe_parallel_sessions_within_cluster_collapse():
    evs = [_ev("2026-03-24T14:33:09.089Z", sid="a"),
           _ev("2026-03-24T14:33:09.510Z", sid="b")]
    assert len(_dedupe_limit_events(evs)) == 1


def test_dedupe_retry_chain_collapses_but_distant_event_stays():
    evs = [_ev("2026-04-14T13:14:48Z"), _ev("2026-04-14T13:15:21Z"),
           _ev("2026-04-14T13:16:24Z"), _ev("2026-04-14T16:00:00Z")]
    out = _dedupe_limit_events(evs)
    assert len(out) == 2
    assert out[0]["merged_count"] == 3
    assert out[1]["merged_count"] == 1


def test_dedupe_input_order_does_not_matter():
    evs = [_ev("2026-04-14T16:00:00Z"), _ev("2026-04-14T13:14:48Z"),
           _ev("2026-04-14T13:15:21Z")]
    out = _dedupe_limit_events(evs)
    assert len(out) == 2
    assert out[0]["timestamp"] == "2026-04-14T13:14:48Z"


def test_dedupe_keeps_unparseable_timestamp_events():
    evs = [_ev(""), _ev("2026-04-14T13:14:48Z")]
    assert len(_dedupe_limit_events(evs)) == 2


def test_dedupe_does_not_mutate_input():
    evs = [_ev("2026-04-14T13:14:48Z")]
    _dedupe_limit_events(evs)
    assert "merged_count" not in evs[0]
