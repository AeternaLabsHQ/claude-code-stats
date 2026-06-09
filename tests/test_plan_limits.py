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


from extract_stats import _match_limit_events_to_windows

T0 = 1_750_000_000_000  # arbitrary fixed epoch ms
H = 3600 * 1000


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _win(start_ms, last_turn_ms, cost=10.0):
    return {"start_ts": start_ms, "end_ts": last_turn_ms, "cost": cost}


def test_fingerprint_event_anchors_pre_gap_window():
    # Window A active [T0, T0+2h]; limit pause; resume at T0+7h opens window B.
    # The limited window is A (contains gap_start), NOT B (contains timestamp).
    wins = [_win(T0, T0 + 2 * H), _win(T0 + 7 * H, T0 + 8 * H)]
    ev = {"type": "heuristic", "subtype": "5h_fingerprint",
          "timestamp": _iso(T0 + 7 * H), "gap_start": _iso(T0 + 2 * H),
          "gap_end": _iso(T0 + 7 * H)}
    assert _match_limit_events_to_windows([ev], wins) == {0}


def test_explicit_banner_after_last_turn_still_anchors_window():
    # Banner arrives 10 min after the window's last assistant turn but
    # within the window's 5h span -- must match.
    wins = [_win(T0, T0 + 2 * H)]
    ev = _ev(_iso(T0 + 2 * H + 10 * 60 * 1000))
    assert _match_limit_events_to_windows([ev], wins) == {0}


def test_event_in_dead_gap_between_windows_matches_nothing():
    wins = [_win(T0, T0 + 2 * H), _win(T0 + 9 * H, T0 + 10 * H)]
    ev = _ev(_iso(T0 + 6 * H))  # after A's 5h span, before B starts
    assert _match_limit_events_to_windows([ev], wins) == set()


def test_event_with_unparseable_timestamp_is_skipped():
    wins = [_win(T0, T0 + 2 * H)]
    assert _match_limit_events_to_windows([_ev("")], wins) == set()


from extract_stats import _estimate_5h_window_cap_usd


def test_floor_raises_implausibly_low_empirical_base():
    # Anchor on Max 5x cost $10 -> base $2. But an event-free Max 5x window
    # cost $115 -- the cap must be at least that, so base floors to 115/5.
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 10.0},
            {"start_ts": 2, "end_ts": 3, "cost": 115.0}]
    tiers = {0: "Max 5x", 1: "Max 5x"}
    info = _estimate_5h_window_cap_usd(wins, {0}, tiers, None)
    assert info["floor_applied"] is True
    assert info["base_pro_per_window_usd"] == 23.0
    assert info["caps_per_window"]["Max 5x"] == 115.0
    assert info["source"] == "empirical"


def test_floor_not_applied_when_anchor_median_is_higher():
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 100.0},
            {"start_ts": 2, "end_ts": 3, "cost": 50.0}]
    tiers = {0: "Max 5x", 1: "Max 5x"}
    info = _estimate_5h_window_cap_usd(wins, {0}, tiers, None)
    assert info["floor_applied"] is False
    assert info["base_pro_per_window_usd"] == 20.0


def test_floor_also_lifts_default_fallback():
    # No anchors -> default base 100; event-free Pro window of $150 lifts it.
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 150.0}]
    tiers = {0: "Pro"}
    info = _estimate_5h_window_cap_usd(wins, set(), tiers, None)
    assert info["source"] == "default"
    assert info["floor_applied"] is True
    assert info["base_pro_per_window_usd"] == 150.0


def test_config_override_is_never_floored():
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 500.0}]
    tiers = {0: "Pro"}
    info = _estimate_5h_window_cap_usd(wins, set(), tiers, 30.0)
    assert info["source"] == "config_override"
    assert info["floor_applied"] is False
    assert info["base_pro_per_window_usd"] == 30.0


from extract_stats import _count_5h_hits

CAPS = {"Pro": 23.0, "Max 5x": 115.0, "Max 20x": 460.0}


def test_anchor_window_counts_as_hit_on_active_and_cheaper_tiers():
    # Real limit hit on Max 5x with (proxy) cost below every cap: still a
    # hit for Max 5x and Pro, but says nothing about Max 20x.
    wins = [(0, {"cost": 30.0})]
    hits = _count_5h_hits(wins, CAPS, {0: "Max 5x"}, {0})
    assert hits == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}


def test_cost_above_cap_counts_without_anchor():
    wins = [(0, {"cost": 120.0})]
    hits = _count_5h_hits(wins, CAPS, {0: "Max 5x"}, set())
    assert hits == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}


def test_anchor_window_not_double_counted():
    wins = [(0, {"cost": 120.0})]
    hits = _count_5h_hits(wins, CAPS, {0: "Max 5x"}, {0})
    assert hits == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}


def test_anchor_on_unknown_tier_falls_back_to_cost_comparison():
    wins = [(0, {"cost": 30.0})]
    hits = _count_5h_hits(wins, CAPS, {0: None}, {0})
    assert hits == {"Pro": 1, "Max 5x": 0, "Max 20x": 0}


def test_zero_cap_yields_no_cost_hits():
    wins = [(0, {"cost": 30.0})]
    hits = _count_5h_hits(wins, {"Pro": 0.0, "Max 5x": 0.0, "Max 20x": 0.0},
                          {0: "Max 5x"}, set())
    assert hits == {"Pro": 0, "Max 5x": 0, "Max 20x": 0}
