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

from extract_stats import _categorize_error, _is_user_plan_limit_text


def test_categorize_rate_limit_error_string():
    assert _categorize_error("rate_limit_error", "API") == "rate_limit"


def test_categorize_429_status():
    assert _categorize_error("HTTP 429 Too Many Requests", "API") == "rate_limit"


def test_categorize_over_capacity():
    assert _categorize_error("API is over capacity", "API") == "rate_limit"


def test_categorize_usage_limit_reached():
    assert _categorize_error("Usage limit reached. Reset at 17:00 UTC.", "API") == "rate_limit"


def test_categorize_overloaded_is_server_overload_not_rate_limit():
    # 'overloaded' / 'overloaded_error' / HTTP 529 are Anthropic-side capacity
    # issues, NOT user plan-limits. They must categorize separately so they
    # do not pollute Limit-Event detection on the Limits tab.
    assert _categorize_error("Anthropic overloaded right now", "API") == "server_overload"
    assert _categorize_error('{"type":"overloaded_error"}', "API") == "server_overload"
    assert _categorize_error("HTTP 529 Overloaded", "API") == "server_overload"


def test_categorize_429_requires_word_boundary():
    # Bare digit sequences inside unrelated numbers must not trigger.
    assert _categorize_error("queue had 1429 items", "API") != "rate_limit"
    assert _categorize_error("processed 42900 tokens", "API") != "rate_limit"


def test_categorize_non_rate_limit_unchanged():
    # Existing category 'permission_denied' still works.
    assert _categorize_error("Permission denied", "Bash") == "permission_denied"


def test_categorize_other_unchanged():
    assert _categorize_error("random unexpected text", "Unknown") == "other"


# ── User-plan-limit text detection (isApiErrorMessage path) ────────

def test_user_plan_limit_text_matches_session_cap():
    # Claude Code's 5h-session limit banner.
    assert _is_user_plan_limit_text("You've hit your limit · resets 6pm (Europe/Berlin)")
    assert _is_user_plan_limit_text("You've hit your limit · resets 6:30pm (Europe/Berlin)")


def test_user_plan_limit_text_matches_monthly_cap():
    assert _is_user_plan_limit_text("You've hit your org's monthly usage limit")


def test_user_plan_limit_text_matches_api_phrases():
    assert _is_user_plan_limit_text("API Error: Rate limit reached")


def test_user_plan_limit_text_rejects_sibling_api_errors():
    # These ALL come through isApiErrorMessage too but are NOT plan limits.
    assert not _is_user_plan_limit_text(
        'API Error: 529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'
    )
    assert not _is_user_plan_limit_text(
        'Please run /login · API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"}}'
    )
    assert not _is_user_plan_limit_text(
        'API Error: 500 Internal server error. This is a server-side issue, usually temporary.'
    )
    assert not _is_user_plan_limit_text("API Error: Stream idle timeout - partial response received")
    assert not _is_user_plan_limit_text(
        'API Error: 400 {"type":"error","error":{"type":"invalid_request_error","message":"Could not process image"}}'
    )


def test_user_plan_limit_text_rejects_incidental_text():
    # Function is only fed isApiErrorMessage text, but sanity-check that
    # nearby phrases that share words don't pattern-match accidentally.
    assert not _is_user_plan_limit_text("Subtest: throws on 429 rate limit · ok 4")
    assert not _is_user_plan_limit_text("")
    assert not _is_user_plan_limit_text("Prompt is too long")  # context overflow != plan limit


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
    _estimate_tier_capacity_per_day_usd,
    _summarize_recommendation,
    PLAN_TIER_FACTORS,
)


def _pi(plan, api_cost, total_days, limit_event_count):
    """Shorthand: build a periods_info entry for the calibration tests."""
    return {
        "plan_normalized": plan,
        "api_cost": api_cost,
        "total_days": total_days,
        "limit_event_count": limit_event_count,
    }


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
    # Override is interpreted as USD-per-day for Pro tier.
    r = _estimate_tier_capacity_per_day_usd([], override_pro_per_day=5.0)
    assert r["source"] == "config_override"
    assert r["base_pro_per_day_usd"] == 5.0
    assert r["capacities_per_day"]["Pro"] == 5.0
    assert r["capacities_per_day"]["Max 5x"] == 25.0
    assert r["capacities_per_day"]["Max 20x"] == 100.0


def test_estimate_capacity_empirical_normalises_by_tier_and_duration():
    # Each limit-hit cycle anchored to its own tier; per-day rate is taken
    # before mixing across tiers.
    #   Max5x cycle, 30d, $1500 → $50/d → $10/d Pro
    #   Max5x cycle, 30d, $1800 → $60/d → $12/d Pro
    #   Max20x cycle, 30d, $7200 → $240/d → $12/d Pro
    # Median of [$10, $12, $12] = $12/d Pro.
    info = [
        _pi("Max 5x",  1500.0, 30, 1),
        _pi("Max 5x",  1800.0, 30, 2),
        _pi("Max 20x", 7200.0, 30, 1),
    ]
    r = _estimate_tier_capacity_per_day_usd(info, None)
    assert r["source"] == "empirical"
    assert r["base_pro_per_day_usd"] == 12.0
    assert r["capacities_per_day"]["Max 5x"] == 60.0
    assert r["capacities_per_day"]["Max 20x"] == 240.0
    assert r["anchor_cycle_count"] == 3


def test_estimate_capacity_ignores_short_cycle_distortion():
    # A short limit-hit cycle (4 days at $1400) and a long limit-hit cycle
    # (30 days at $1500) on the same tier — the per-day normalisation
    # should make the short cycle stand out as a real high-rate anchor,
    # not be smeared with the long-cycle data. Per-day rates:
    #   $1400/4d = $350/d → $70/d Pro
    #   $1500/30d = $50/d → $10/d Pro
    # Median of [$10, $70] = $40/d Pro.
    info = [
        _pi("Max 5x", 1400.0,  4, 2),
        _pi("Max 5x", 1500.0, 30, 1),
    ]
    r = _estimate_tier_capacity_per_day_usd(info, None)
    assert r["source"] == "empirical"
    assert r["base_pro_per_day_usd"] == 40.0


def test_estimate_capacity_fallback_to_default_without_events():
    # No limit-hit cycles at all → fall back to PRO_CAPACITY_USD_DEFAULT/30.
    info = [_pi("Max 5x", 500.0, 30, 0)]
    r = _estimate_tier_capacity_per_day_usd(info, None)
    assert r["source"] == "default"
    # PRO_CAPACITY_USD_DEFAULT is 100/cycle → ~3.33/day with the 30-day spread.
    assert round(r["base_pro_per_day_usd"], 2) == round(100.0 / 30.0, 2)
    assert r["anchor_cycle_count"] == 0


def test_estimate_capacity_ignores_cycles_without_events():
    info = [
        _pi("Max 5x", 1500.0, 30, 1),  # used
        _pi("Max 5x",  200.0, 30, 0),  # ignored — no limit hit
    ]
    r = _estimate_tier_capacity_per_day_usd(info, None)
    assert r["source"] == "empirical"
    # Only the first cycle contributes: $1500/30d = $50/d → $10/d Pro.
    assert r["base_pro_per_day_usd"] == 10.0
    assert r["anchor_cycle_count"] == 1


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


def test_estimate_capacity_skips_unknown_tier_anchors():
    # An unknown tier name on a limit-hit cycle is skipped (no factor),
    # not forcibly normalised against a guessed factor.
    info = [
        _pi(None,      500.0, 30, 1),   # "Enterprise" → unknown, ignored
        _pi("Max 5x", 1500.0, 30, 1),
    ]
    r = _estimate_tier_capacity_per_day_usd(info, None)
    assert r["source"] == "empirical"
    # Only Max 5x contributes: $1500/30d = $50/d → $10/d Pro
    assert r["base_pro_per_day_usd"] == 10.0


def test_estimate_capacity_negative_override_ignored():
    info = [_pi("Max 5x", 1500.0, 30, 1)]
    r = _estimate_tier_capacity_per_day_usd(info, override_pro_per_day=-50.0)
    # Negative override is rejected; falls through to empirical.
    assert r["source"] == "empirical"
    assert r["base_pro_per_day_usd"] == 10.0
