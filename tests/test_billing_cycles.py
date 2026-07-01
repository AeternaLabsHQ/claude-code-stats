"""Regression tests for billing-cycle expansion with high billing_day anchors."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _expand_billing_cycles, _month_day_clamped


def _ph(billing_day, cost=100.0):
    return {"plan": "Max 5x", "cost_usd": cost, "billing_day": billing_day,
            "billing_cycle": "monthly"}


def _parse(d):
    return datetime.strptime(d, "%Y-%m-%d")


def test_billing_day_31_produces_five_monthly_cycles():
    cycles = _expand_billing_cycles(_ph(31), "2026-01-31", "2026-06-29")
    starts = [c["start"] for c in cycles]
    assert starts == ["2026-01-31", "2026-02-28", "2026-03-31",
                      "2026-04-30", "2026-05-31"]
    assert cycles[-1]["end"] == "2026-06-29"


def test_billing_day_31_cycles_are_gap_free_and_month_sized():
    cycles = _expand_billing_cycles(_ph(31), "2026-01-31", "2026-06-29")
    for prev, nxt in zip(cycles, cycles[1:]):
        gap = (_parse(nxt["start"]) - _parse(prev["end"])).days
        assert gap == 1, (prev, nxt)
    for c in cycles:
        length = (_parse(c["end"]) - _parse(c["start"])).days + 1
        assert 28 <= length <= 31, c


def test_anchor_day_recovers_after_short_month():
    # Feb clamps to 28, but March must return to the day-31 anchor.
    cycles = _expand_billing_cycles(_ph(31), "2026-01-31", "2026-04-15")
    assert cycles[1]["start"] == "2026-02-28"
    assert cycles[2]["start"] == "2026-03-31"


def test_unclamped_days_unchanged():
    cycles = _expand_billing_cycles(_ph(2), "2026-01-02", "2026-03-01")
    assert [c["start"] for c in cycles] == ["2026-01-02", "2026-02-02"]
    assert [c["end"] for c in cycles] == ["2026-02-01", "2026-03-01"]


def test_december_rollover():
    cycles = _expand_billing_cycles(_ph(31), "2025-11-30", "2026-01-30")
    assert [c["start"] for c in cycles] == ["2025-11-30", "2025-12-31"]
    assert cycles[1]["end"] == "2026-01-30"


def test_month_day_clamped():
    assert _month_day_clamped(2026, 2, 31) == datetime(2026, 2, 28)
    assert _month_day_clamped(2028, 2, 31) == datetime(2028, 2, 29)  # leap year
    assert _month_day_clamped(2026, 4, 31) == datetime(2026, 4, 30)
    assert _month_day_clamped(2026, 1, 15) == datetime(2026, 1, 15)
