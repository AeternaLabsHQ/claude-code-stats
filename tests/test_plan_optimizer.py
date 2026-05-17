"""Unit tests for plan-optimizer heuristics (Tasks 1-4)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _detect_cache_flushes


def _turn(ts_min, cc=0, cr=0):
    """Build a turn dict; ts is given as minutes since session start."""
    return {"ts": int(ts_min * 60 * 1000), "cache_creation": cc, "cache_read": cr}


def test_cache_flush_trivial_session_returns_zero():
    turns = [_turn(0, cc=1000, cr=0), _turn(1, cc=200, cr=800)]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_buildup_only_session_returns_zero():
    turns = [_turn(i, cc=1000, cr=0) for i in range(6)]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_warm_session_no_gaps_returns_zero():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),   # buildup-over signal here
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=100, cr=2800),
        _turn(5, cc=100, cr=3000),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_single_real_pause_returns_one():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(15, cc=2000, cr=500),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 1


def test_cache_flush_gap_below_threshold_ignored():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(7, cc=2000, cr=500),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_creation_within_2x_median_ignored():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(15, cc=180, cr=2500),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_1h_cache_uses_60min_threshold():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(35, cc=2000, cr=500),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=True) == 0


def test_cache_flush_multiple_real_pauses_counted():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(20, cc=2500, cr=1000),
        _turn(21, cc=100, cr=2800),
        _turn(22, cc=100, cr=2900),
        _turn(40, cc=3000, cr=1500),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 2


# ── Task 2: idle-gap summary ───────────────────────────────────────

from extract_stats import _compute_idle_gap_summary


def test_idle_gap_empty_session_returns_none():
    assert _compute_idle_gap_summary([]) is None


def test_idle_gap_single_turn_returns_none():
    assert _compute_idle_gap_summary([_turn(0, cc=100)]) is None


def test_idle_gap_all_short_gaps_summary():
    turns = [_turn(i, cc=100) for i in range(5)]
    s = _compute_idle_gap_summary(turns)
    assert s["short"]["count"] == 4
    assert s["mid"]["count"] == 0
    assert s["long"]["count"] == 0
    assert s["estimated_overspend_tokens"] == 0


def test_idle_gap_mixed_buckets_classified_correctly():
    turns = [
        _turn(0,   cc=100),
        _turn(1,   cc=100),    # 1min → short
        _turn(2,   cc=100),    # 1min → short
        _turn(10,  cc=500),    # 8min → mid
        _turn(80,  cc=2000),   # 70min → long
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["short"]["count"] == 2
    assert s["mid"]["count"] == 1
    assert s["long"]["count"] == 1


def test_idle_gap_overspend_uses_short_bucket_median_as_baseline():
    turns = [
        _turn(0,   cc=100),
        _turn(1,   cc=100),
        _turn(2,   cc=100),
        _turn(10,  cc=500),     # mid
        _turn(80,  cc=2000),    # long
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["baseline_per_turn_tokens"] == 100
    assert s["estimated_overspend_tokens"] == 2300


def test_idle_gap_overspend_falls_back_to_session_median_if_no_short_bucket():
    turns = [
        _turn(0,   cc=100),
        _turn(10,  cc=500),
        _turn(80,  cc=2000),
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["baseline_per_turn_tokens"] == 500
    assert s["estimated_overspend_tokens"] == 1500


def test_idle_gap_overspend_pct_of_session_total():
    turns = [
        _turn(0, cc=100),
        _turn(1, cc=100),
        _turn(2, cc=100),
        _turn(10, cc=500),
        _turn(80, cc=2000),
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["estimated_overspend_pct_of_session"] == 82


# ── Task 3: rate-limit error categorization ─────────────────────────

from extract_stats import _categorize_error


def test_categorize_rate_limit_error_string():
    assert _categorize_error("rate_limit_error", "API") == "rate_limit"


def test_categorize_429_status():
    assert _categorize_error("HTTP 429 Too Many Requests", "API") == "rate_limit"


def test_categorize_over_capacity():
    assert _categorize_error("API is over capacity", "API") == "rate_limit"


def test_categorize_usage_limit_reached():
    assert _categorize_error("Usage limit reached. Reset at 17:00 UTC.", "API") == "rate_limit"


def test_categorize_overloaded():
    assert _categorize_error("Anthropic overloaded right now", "API") == "rate_limit"


def test_categorize_non_rate_limit_unchanged():
    # Existing category 'permission_denied' still works.
    assert _categorize_error("Permission denied", "Bash") == "permission_denied"


def test_categorize_other_unchanged():
    assert _categorize_error("random unexpected text", "Unknown") == "other"


# ── Task 3: 5h-fingerprint heuristic ────────────────────────────────

from extract_stats import _detect_5h_fingerprint_events
from datetime import datetime, timezone, timedelta


def _prompt(ts_iso, session_id="s1"):
    return {"timestamp": ts_iso, "session_id": session_id}


def test_5h_fingerprint_clean_5h_gap_with_active_prefix_detected():
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt((base + timedelta(minutes=-90)).isoformat()),
        _prompt((base + timedelta(minutes=-30)).isoformat()),
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=5, minutes=2)).isoformat(), "s2"),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert len(events) == 1
    assert events[0]["confidence"] in ("high", "medium")
    assert events[0]["session_id"] == "s2"


def test_5h_fingerprint_isolated_gap_without_activity_rejected():
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=5, minutes=2)).isoformat()),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert events == []


def test_5h_fingerprint_short_gap_ignored():
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt((base + timedelta(minutes=-30)).isoformat()),
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=4)).isoformat()),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert events == []


def test_5h_fingerprint_long_gap_ignored():
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt((base + timedelta(minutes=-30)).isoformat()),
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=6)).isoformat()),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert events == []


# ── Task 4: plan-recommendation ────────────────────────────────────

from extract_stats import (
    _normalize_tier_name,
    _estimate_tier_capacity_usd,
    _summarize_recommendation,
    PLAN_TIER_FACTORS,
)


def test_normalize_pro_variants():
    assert _normalize_tier_name("Pro") == "Pro"
    assert _normalize_tier_name("pro plan") == "Pro"
    assert _normalize_tier_name("Pro (annual)") == "Pro"


def test_normalize_max5x_variants():
    assert _normalize_tier_name("Max 5x") == "Max 5x"
    assert _normalize_tier_name("max5x") == "Max 5x"
    assert _normalize_tier_name("5x") == "Max 5x"


def test_normalize_max20x_variants():
    assert _normalize_tier_name("Max 20x") == "Max 20x"
    assert _normalize_tier_name("max20x") == "Max 20x"
    assert _normalize_tier_name("20x") == "Max 20x"


def test_normalize_unknown_returns_none():
    assert _normalize_tier_name("Enterprise") is None
    assert _normalize_tier_name("") is None


def test_estimate_capacity_override_takes_precedence():
    r = _estimate_tier_capacity_usd("Max 5x", {}, {}, override_pro=200.0)
    assert r["source"] == "config_override"
    assert r["base_pro_usd"] == 200.0
    assert r["capacities"]["Pro"] == 200.0
    assert r["capacities"]["Max 5x"] == 1000.0
    assert r["capacities"]["Max 20x"] == 4000.0


def test_estimate_capacity_empirical_from_limit_events():
    events_by_cycle = {"c1": [{"x": 1}], "c2": [{"x": 1}], "c3": [{"x": 1}]}
    cost_by_cycle = {"c1": 480.0, "c2": 510.0, "c3": 540.0}
    r = _estimate_tier_capacity_usd("Max 5x", events_by_cycle, cost_by_cycle, None)
    assert r["source"] == "empirical"
    assert r["base_pro_usd"] == 102.0


def test_estimate_capacity_fallback_to_default_without_events():
    r = _estimate_tier_capacity_usd("Max 5x", {}, {}, None)
    assert r["source"] == "default"
    assert r["base_pro_usd"] == 100.0


def test_estimate_capacity_ignores_cycles_without_events():
    # Only cycles WITH events count toward calibration.
    events_by_cycle = {"c1": [{"x": 1}], "c2": []}
    cost_by_cycle = {"c1": 500.0, "c2": 200.0}
    r = _estimate_tier_capacity_usd("Max 5x", events_by_cycle, cost_by_cycle, None)
    assert r["source"] == "empirical"
    assert r["base_pro_usd"] == 100.0  # 500 / 5


def test_recommendation_recommends_cheapest_holding_tier():
    cycles = [
        {"tier_utilization": {"Pro": 50,  "Max 5x": 10, "Max 20x": 3}},
        {"tier_utilization": {"Pro": 150, "Max 5x": 30, "Max 20x": 8}},
        {"tier_utilization": {"Pro": 200, "Max 5x": 40, "Max 20x": 10}},
    ]
    r = _summarize_recommendation(cycles, current_tier="Max 5x")
    assert r["recommended_tier"] == "Max 5x"
    assert r["held_count"]["Pro"] == 1
    assert r["held_count"]["Max 5x"] == 3
    assert r["total_cycles"] == 3


def test_recommendation_recommends_pro_if_always_held():
    cycles = [
        {"tier_utilization": {"Pro": 50, "Max 5x": 10, "Max 20x": 3}},
        {"tier_utilization": {"Pro": 80, "Max 5x": 16, "Max 20x": 4}},
    ]
    r = _summarize_recommendation(cycles, current_tier="Max 5x")
    assert r["recommended_tier"] == "Pro"


def test_recommendation_none_if_nothing_holds():
    cycles = [
        {"tier_utilization": {"Pro": 150, "Max 5x": 150, "Max 20x": 150}},
    ]
    r = _summarize_recommendation(cycles, current_tier="Max 20x")
    assert r["recommended_tier"] is None


def test_recommendation_empty_cycles_returns_none():
    r = _summarize_recommendation([], current_tier="Pro")
    assert r["recommended_tier"] is None
    assert r["total_cycles"] == 0
    assert r["held_count"] == {"Pro": 0, "Max 5x": 0, "Max 20x": 0}


def test_estimate_capacity_unknown_current_tier_uses_5x_fallback_factor():
    # Unknown tier name → falls back to factor 5.0 for the calibration math.
    # 500 / 5 = 100.
    events_by_cycle = {"c1": [{"x": 1}]}
    cost_by_cycle = {"c1": 500.0}
    r = _estimate_tier_capacity_usd("Enterprise", events_by_cycle, cost_by_cycle, None)
    assert r["source"] == "empirical"
    assert r["base_pro_usd"] == 100.0


def test_estimate_capacity_negative_override_ignored():
    # Negative override is rejected; falls through to default.
    r = _estimate_tier_capacity_usd("Max 5x", {}, {}, override_pro=-50.0)
    assert r["source"] == "default"
    assert r["base_pro_usd"] == 100.0
