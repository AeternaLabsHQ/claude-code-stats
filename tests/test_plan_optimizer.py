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
