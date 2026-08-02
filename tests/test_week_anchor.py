"""Weekly buckets must honor the configurable week anchor."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _compute_weekly_buckets


def _wt(ts, cost):
    return {"ts": ts, "cost": cost, "session_id": "s1"}


def _ms(y, m, d, h=12):
    return int(datetime.datetime(
        y, m, d, h, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def test_monday_anchor_week_key_is_week_start_date():
    b = _compute_weekly_buckets([_wt(_ms(2026, 1, 5), 1.0)], anchor_weekday=0)
    assert b[0]["week_key"] == "2026-01-05"  # 2026-01-05 is a Monday


def test_tuesday_anchor_groups_monday_into_previous_week():
    turns = [
        _wt(_ms(2026, 1, 5), 1.0),   # Monday
        _wt(_ms(2026, 1, 6), 2.0),   # Tuesday -> new week
    ]
    b = _compute_weekly_buckets(turns, anchor_weekday=1)
    assert len(b) == 2
    assert b[0]["week_key"] == "2025-12-30"  # Tuesday of the previous week
    assert b[1]["week_key"] == "2026-01-06"
    assert b[0]["cost"] == 1.0
    assert b[1]["cost"] == 2.0


def test_week_end_is_seven_days_after_start():
    b = _compute_weekly_buckets([_wt(_ms(2026, 1, 5), 1.0)], anchor_weekday=0)
    assert b[0]["week_end_ts"] - b[0]["week_start_ts"] == 7 * 24 * 3600 * 1000 - 1
