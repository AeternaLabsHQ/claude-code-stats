"""Ultra (ex Max 20x) has no rolling 5h limit from 2026-10-30."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core import settings
from claudestats_core.limits import (
    ULTRA_LAUNCH_DATE, WEEKLY_TIER_FACTORS_ULTRA, _count_5h_hits,
    _drop_impossible_5h_fingerprints, _normalize_tier_name, _tier_on_date,
    _ultra_5h_free, _utc_date)
from claudestats_core.plan_analysis import build_plan_analysis

CAPS = {"Pro": 100.0, "Max 5x": 500.0, "Max 20x": 900.0}


def D(s):
    dt = datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ph(plan, start, end=None):
    return {"plan": plan, "start": start, "end": end, "cost_usd": 200,
            "cost_local": 200, "billing_day": 1, "billing_cycle": "monthly"}


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (settings.PLAN_HISTORY, settings.ULTRA_NO_5H_FROM,
             settings.PLAN_CAPACITY_OVERRIDE_PRO_USD)
    yield
    (settings.PLAN_HISTORY, settings.ULTRA_NO_5H_FROM,
     settings.PLAN_CAPACITY_OVERRIDE_PRO_USD) = saved


def test_normalize_new_names():
    assert _normalize_tier_name("Ultra") == "Max 20x"
    assert _normalize_tier_name("ultra (annual)") == "Max 20x"
    assert _normalize_tier_name("Max") == "Max 5x"
    assert _normalize_tier_name("max") == "Max 5x"
    assert _normalize_tier_name("Pro") == "Pro"
    assert _normalize_tier_name("Max 5x") == "Max 5x"
    assert _normalize_tier_name("Max 20x") == "Max 20x"


def test_constants():
    assert ULTRA_LAUNCH_DATE == "2026-10-30"
    assert WEEKLY_TIER_FACTORS_ULTRA == {"Pro": 1.0, "Max 5x": 5.0, "Max 20x": 10.0}


def test_utc_date_and_ultra_5h_free():
    settings.configure(ultra_no_5h_from="2026-10-30")
    assert _utc_date(D("2026-10-30T00:00")) == "2026-10-30"
    assert _utc_date(None) is None
    assert _ultra_5h_free(D("2026-10-30T00:00")) is True
    assert _ultra_5h_free(D("2026-10-29T23:59")) is False
    assert _ultra_5h_free(None) is False
    settings.configure(ultra_no_5h_from=None)
    assert _ultra_5h_free(D("2026-11-05T00:00")) is False


def test_tier_on_date_first_match():
    settings.configure(plan_history=[_ph("Pro", "2026-01-01", "2026-03-31"),
                                     _ph("Ultra", "2026-04-01")])
    assert _tier_on_date("2026-02-01") == "Pro"
    assert _tier_on_date("2026-11-01") == "Max 20x"
    assert _tier_on_date("2025-12-31") is None


def test_count_hits_ultra_free_window_never_counts_for_max20x():
    w = [(0, {"cost": 1000.0})]
    free = _count_5h_hits(w, CAPS, {0: "Max 20x"}, set(), ultra_free_ids={0})
    assert free == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}
    old = _count_5h_hits(w, CAPS, {0: "Max 20x"}, set())
    assert old == {"Pro": 1, "Max 5x": 1, "Max 20x": 1}


def test_count_hits_anchored_ultra_free_window_not_counted():
    w = [(0, {"cost": 10.0})]
    assert _count_5h_hits(w, CAPS, {0: "Max 20x"}, {0})["Max 20x"] == 1
    assert _count_5h_hits(w, CAPS, {0: "Max 20x"}, {0},
                          ultra_free_ids={0})["Max 20x"] == 0


def _fp(gap_start):
    return {"type": "heuristic", "subtype": "5h_fingerprint",
            "timestamp": gap_start, "gap_start": gap_start}


def test_drop_impossible_fingerprints():
    settings.configure(plan_history=[_ph("Max 20x", "2026-04-27")],
                       ultra_no_5h_from="2026-10-30")
    late, early = _fp("2026-11-07T23:21:00+00:00"), _fp("2026-10-27T10:00:00+00:00")
    explicit = {"type": "explicit", "subtype": "user_plan_limit",
                "timestamp": "2026-11-08T10:00:00Z"}
    broken = {"type": "heuristic", "subtype": "5h_fingerprint",
              "timestamp": "x", "gap_start": "garbage"}
    evs = [late, early, explicit, broken]
    assert _drop_impossible_5h_fingerprints(evs) == [early, explicit, broken]

    settings.configure(ultra_no_5h_from=None)
    assert _drop_impossible_5h_fingerprints(evs) == evs

    settings.configure(plan_history=[_ph("Max 5x", "2026-04-27")],
                       ultra_no_5h_from="2026-10-30")
    assert _drop_impossible_5h_fingerprints(evs) == evs


def _analysis(windows, events, weeks=()):
    settings.configure(plan_history=[_ph("Max 20x", "2026-10-01")])
    wins = [{"start_ts": D(t), "end_ts": D(t), "cost": c, "turn_count": 1,
             "session_ids": []} for t, c in windows]
    return build_plan_analysis(
        [], [], first_session="2026-10-01", all_limit_events=events,
        windows_5h=wins,
        weekly_buckets=[{"week_key": k, "week_start_ts": D(k + "T00:00"),
                         "cost": c} for k, c in weeks])["plan_recommendation"]


WINS = [("2026-10-10T10:00", 5000.0), ("2026-11-05T10:00", 5000.0)]
EVS = [{"type": "explicit", "subtype": "user_plan_limit",
        "timestamp": "2026-11-05T12:00:00Z", "session_id": "s"}]


def _cycle(rec, start):
    return next(c for c in rec["cycles"] if c["cycle_start"] == start)


def test_calibration_ignores_post_cutoff_anchor():
    settings.configure(ultra_no_5h_from="2026-10-30")
    rec = _analysis(WINS, EVS)
    cal = rec["calibration_5h"]
    assert cal["anchor_window_count"] == 0
    assert cal["floor_pro_per_window_usd"] == 250.0
    assert _cycle(rec, "2026-11-01")["tier_5h_hits"]["Max 20x"] == 0
    assert rec["ultra_no_5h_from"] == "2026-10-30"
    assert rec["ultra_launch_date"] == "2026-10-30"


def test_calibration_without_cutoff_keeps_anchor():
    settings.configure(ultra_no_5h_from=None)
    rec = _analysis(WINS, EVS)
    assert rec["calibration_5h"]["anchor_window_count"] == 1
    assert rec["ultra_no_5h_from"] is None


def test_weekly_caps_and_cutoff_by_week_start():
    settings.configure(ultra_no_5h_from="2026-10-30")
    probe = _analysis(WINS, EVS)
    base = probe["calibration_5h"]["base_pro_per_window_usd"]
    wk = probe["calibration_weekly"]
    assert wk["caps_per_week"]["Max 20x"] == round(base * 10 * 7, 2)
    assert wk["caps_per_week_before_ultra"]["Max 20x"] == round(base * 20 * 7, 2)
    assert wk["caps_per_week"]["Pro"] == wk["caps_per_week_before_ultra"]["Pro"]
    assert wk["ratio_vs_5h"] == 7 and wk["source"] == "derived_from_5h"
    mid = (wk["caps_per_week"]["Max 20x"] + wk["caps_per_week_before_ultra"]["Max 20x"]) / 2
    rec = _analysis(WINS, EVS, weeks=[("2026-11-02", mid), ("2026-10-05", mid)])
    assert _cycle(rec, "2026-11-01")["tier_weekly_hits"]["Max 20x"] == 1
    assert _cycle(rec, "2026-10-01")["tier_weekly_hits"]["Max 20x"] == 0


def test_weekly_caps_exact_for_non_round_base():
    settings.configure(ultra_no_5h_from="2026-10-30",
                       plan_capacity_override_pro_usd=12.3456)
    wk = _analysis(WINS, EVS)["calibration_weekly"]
    new, old = wk["caps_per_week"], wk["caps_per_week_before_ultra"]
    assert new["Pro"] == old["Pro"]
    assert new["Max 5x"] == old["Max 5x"]
    assert old["Max 5x"] == 432.11
    assert abs(new["Max 20x"] - old["Max 20x"] / 2) <= 0.01


def test_parse_ultra_cutoff(capsys):
    assert settings.parse_ultra_cutoff() == "2026-10-30"
    assert settings.parse_ultra_cutoff(settings.MISSING, default="x") == "x"
    assert settings.parse_ultra_cutoff(None) is None
    assert settings.parse_ultra_cutoff("2026-11-05") == "2026-11-05"
    assert settings.parse_ultra_cutoff("2026-11-3") == "2026-11-03"
    assert capsys.readouterr().out == ""
    assert settings.parse_ultra_cutoff("2026-10-30") == "2026-10-30"
    assert capsys.readouterr().out == ""
    assert settings.parse_ultra_cutoff("garbage") == "2026-10-30"
    assert "WARNING" in capsys.readouterr().out
    # Ultra did not exist earlier: clamp with a warning
    assert settings.parse_ultra_cutoff("2026-01-01") == "2026-10-30"
    assert "WARNING" in capsys.readouterr().out
