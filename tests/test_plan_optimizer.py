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
    assert _detect_cache_flushes(turns, has_1h_cache=False)["gap_flushes"] == 0


def test_cache_flush_buildup_only_session_returns_zero():
    turns = [_turn(i, cc=1000, cr=0) for i in range(6)]
    assert _detect_cache_flushes(turns, has_1h_cache=False)["gap_flushes"] == 0


def test_cache_flush_warm_session_no_gaps_returns_zero():
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),   # buildup-over signal here
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=100, cr=2800),
        _turn(5, cc=100, cr=3000),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False)["gap_flushes"] == 0


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
    assert _detect_cache_flushes(turns, has_1h_cache=False)["gap_flushes"] == 1


def test_cache_flush_gap_below_threshold_ignored():
    # 7-min gap < 5-min TTL threshold: not a gap flush.
    # The read collapse makes it a no-gap anomaly (new behavior).
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(7, cc=2000, cr=500),
    ]
    result = _detect_cache_flushes(turns, has_1h_cache=False)
    assert result["gap_flushes"] == 0
    assert result["nogap_flushes"] == 1


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
    result = _detect_cache_flushes(turns, has_1h_cache=False)
    assert result["gap_flushes"] == 0
    assert result["nogap_flushes"] == 0


def test_cache_flush_1h_cache_uses_60min_threshold():
    # 35-min gap < 60-min TTL: not a gap flush.
    # The read collapse makes it a no-gap anomaly (new behavior).
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(35, cc=2000, cr=500),
    ]
    result = _detect_cache_flushes(turns, has_1h_cache=True)
    assert result["gap_flushes"] == 0
    assert result["nogap_flushes"] == 1


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
    assert _detect_cache_flushes(turns, has_1h_cache=False)["gap_flushes"] == 2


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


# ── Error classification: backend (isApiErrorMessage) vs tool ───────
# Backend categories (rate_limit / overload) are matched ONLY on the
# isApiErrorMessage channel via _classify_api_error. Tool-result errors go
# through _classify_tool_error and must NEVER be tagged as backend, because
# tool stdout/stderr mentions those keywords incidentally.

from extract_stats import _classify_tool_error, _classify_api_error, _is_user_plan_limit_text


def test_api_rate_limit_error_string():
    assert _classify_api_error("rate_limit_error") == "rate_limit"


def test_api_429_status():
    assert _classify_api_error("HTTP 429 Too Many Requests") == "rate_limit"


def test_api_usage_limit_reached():
    assert _classify_api_error("Usage limit reached. Reset at 17:00 UTC.") == "rate_limit"


def test_api_overloaded_is_server_overload_not_rate_limit():
    assert _classify_api_error('{"type":"overloaded_error"}') == "server_overload"
    assert _classify_api_error("HTTP 529 Overloaded") == "server_overload"


def test_api_429_requires_word_boundary():
    # Bare digit sequences inside unrelated numbers must not trigger.
    assert _classify_api_error("queue had 1429 items") != "rate_limit"
    assert _classify_api_error("processed 42900 tokens") != "rate_limit"


def test_tool_permission_denied():
    assert _classify_tool_error("Permission denied", "Bash") == ("tool", "permission_denied")


def test_tool_other_unchanged():
    assert _classify_tool_error("random unexpected text", "Unknown") == ("tool", "other")


def test_tool_error_never_tagged_backend():
    # The bug the user spotted: tool output that mentions rate_limit_error / 429
    # must stay source=tool, not be miscategorised as a backend rate-limit.
    src, cat = _classify_tool_error(
        "Exit code 1\n# test covers rate_limit_error and HTTP 429 paths\nnot ok 2", "Bash")
    assert src == "tool"
    assert cat != "rate_limit"


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
    _compute_5h_windows,
    _compute_weekly_buckets,
    _estimate_5h_window_cap_usd,
    PLAN_TIER_FACTORS,
    FIVE_HOUR_MS,
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


# ── 5h-window aggregation ───────────────────────────────────────────

def _wt(ts_ms, cost, session_id="s1"):
    """Helper for window/weekly tests — distinct from _turn() above."""
    return {"ts": ts_ms, "cost": cost, "session_id": session_id}


def test_5h_windows_empty_input():
    assert _compute_5h_windows([]) == []


def test_5h_windows_single_window():
    # Three turns within 5h → single window.
    turns = [
        _wt(0,                     1.0),
        _wt(60 * 60 * 1000,        2.0),  # +1h
        _wt(4 * 60 * 60 * 1000,    3.0),  # +4h
    ]
    w = _compute_5h_windows(turns)
    assert len(w) == 1
    assert w[0]["cost"] == 6.0
    assert w[0]["turn_count"] == 3


def test_5h_windows_split_at_5h_boundary():
    # Turn exactly at +5h opens a new window.
    turns = [
        _wt(0, 1.0),
        _wt(FIVE_HOUR_MS - 1, 2.0),   # still in first window
        _wt(FIVE_HOUR_MS,     3.0),    # opens window 2
        _wt(FIVE_HOUR_MS + 3600 * 1000, 4.0),  # in window 2
    ]
    w = _compute_5h_windows(turns)
    assert len(w) == 2
    assert w[0]["cost"] == 3.0
    assert w[1]["cost"] == 7.0


def test_5h_windows_session_ids_aggregated():
    turns = [
        _wt(0, 1.0, "A"),
        _wt(60 * 1000, 1.0, "B"),
        _wt(60 * 60 * 1000, 1.0, "A"),
    ]
    w = _compute_5h_windows(turns)
    assert w[0]["session_ids"] == ["A", "B"]


# ── Weekly bucket aggregation ───────────────────────────────────────

def test_weekly_buckets_groups_same_iso_week():
    # All three timestamps are in ISO week 2026-W01 (Mon 2025-12-29 → Sun 2026-01-04).
    import datetime
    def ms(y, m, d, h=12):
        return int(datetime.datetime(y, m, d, h, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    turns = [
        _wt(ms(2025, 12, 30), 1.0),  # Tue W01
        _wt(ms(2025, 12, 31), 2.0),  # Wed W01
        _wt(ms(2026,  1,  3), 4.0),  # Sat W01
    ]
    b = _compute_weekly_buckets(turns, anchor_weekday=0)
    assert len(b) == 1
    assert b[0]["week_key"] == "2025-12-29"  # Monday of that week
    assert b[0]["cost"] == 7.0


def test_weekly_buckets_splits_across_weeks():
    import datetime
    def ms(y, m, d):
        return int(datetime.datetime(y, m, d, 12, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    turns = [
        _wt(ms(2026, 1, 4),  1.0),  # Sun W01
        _wt(ms(2026, 1, 5),  2.0),  # Mon W02
    ]
    b = _compute_weekly_buckets(turns, anchor_weekday=0)
    assert len(b) == 2
    assert b[0]["week_key"] == "2025-12-29"
    assert b[1]["week_key"] == "2026-01-05"


# ── Per-tier 5h-window cap estimation ───────────────────────────────

def test_5h_cap_empirical_from_anchor_windows():
    # Two anchor windows on different tiers should normalise to a
    # consistent Pro baseline per the 1:5:20 ratio:
    #   Max5x window cost $30 → Pro per-window = $30 / 5 = $6
    #   Max20x window cost $120 → Pro per-window = $120 / 20 = $6
    # Median = $6.
    windows = [
        {"cost": 30.0, "start_ts": 0, "end_ts": 1, "turn_count": 1, "session_ids": ["s1"]},
        {"cost": 120.0, "start_ts": 2, "end_ts": 3, "turn_count": 1, "session_ids": ["s2"]},
    ]
    tier_by_idx = {0: "Max 5x", 1: "Max 20x"}
    r = _estimate_5h_window_cap_usd(windows, {0, 1}, tier_by_idx, None)
    assert r["source"] == "empirical"
    assert r["base_pro_per_window_usd"] == 6.0
    assert r["caps_per_window"]["Pro"] == 6.0
    assert r["caps_per_window"]["Max 5x"] == 30.0
    assert r["caps_per_window"]["Max 20x"] == 120.0
    assert r["anchor_window_count"] == 2


def test_5h_cap_config_override_takes_precedence():
    r = _estimate_5h_window_cap_usd([], set(), {}, override_pro=5.0)
    assert r["source"] == "config_override"
    assert r["base_pro_per_window_usd"] == 5.0
    assert r["caps_per_window"]["Max 5x"] == 25.0
    assert r["caps_per_window"]["Max 20x"] == 100.0


def test_5h_cap_default_fallback_without_anchors():
    r = _estimate_5h_window_cap_usd([], set(), {}, None)
    assert r["source"] == "default"
    # PRO_CAPACITY_USD_DEFAULT is 100 → Pro cap = $100 per window.
    assert r["base_pro_per_window_usd"] == 100.0


def test_5h_cap_skips_unknown_tier_anchors():
    windows = [
        {"cost": 50.0, "start_ts": 0, "end_ts": 1, "turn_count": 1, "session_ids": []},
        {"cost": 30.0, "start_ts": 2, "end_ts": 3, "turn_count": 1, "session_ids": []},
    ]
    tier_by_idx = {0: None, 1: "Max 5x"}  # idx 0 is unknown tier → skipped
    r = _estimate_5h_window_cap_usd(windows, {0, 1}, tier_by_idx, None)
    assert r["source"] == "empirical"
    # Only the Max 5x window contributes: $30 / 5 = $6.
    assert r["base_pro_per_window_usd"] == 6.0
    assert r["anchor_window_count"] == 1


def test_5h_cap_negative_override_ignored():
    windows = [{"cost": 30.0, "start_ts": 0, "end_ts": 1, "turn_count": 1, "session_ids": []}]
    r = _estimate_5h_window_cap_usd(windows, {0}, {0: "Max 5x"}, override_pro=-50.0)
    assert r["source"] == "empirical"
    assert r["base_pro_per_window_usd"] == 6.0
