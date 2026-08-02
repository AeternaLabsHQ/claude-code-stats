"""Unit tests for the 1M-context-window detection heuristic.

The standard context window caps the prompt at ~200k tokens, so any assistant
turn whose prompt context (input + cache_read + cache_creation) exceeds the
threshold provably ran with the 1M-context window enabled.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import CONTEXT_1M_THRESHOLD, summarize_context_window


def _turn(timestamp, input=0, cache_read=0, cache_creation=0):
    return {
        "timestamp": timestamp,
        "input": input,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
    }


def test_threshold_is_200k():
    assert CONTEXT_1M_THRESHOLD == 200_000


def test_empty_session_has_no_1m():
    summary = summarize_context_window([])
    assert summary["peak_context_tokens"] == 0
    assert summary["used_1m_context"] is False
    assert summary["first_1m_at"] is None


def test_all_turns_below_threshold_not_flagged():
    turns = [
        _turn("2026-05-30T10:00:00Z", input=2, cache_read=50_000, cache_creation=10_000),
        _turn("2026-05-30T10:05:00Z", input=2, cache_read=120_000, cache_creation=5_000),
    ]
    summary = summarize_context_window(turns)
    assert summary["peak_context_tokens"] == 125_002
    assert summary["used_1m_context"] is False
    assert summary["first_1m_at"] is None


def test_turn_over_threshold_is_flagged():
    turns = [
        _turn("2026-05-30T10:00:00Z", input=2, cache_read=100_000, cache_creation=5_000),
        _turn("2026-05-30T10:05:00Z", input=2, cache_read=300_000, cache_creation=20_000),
    ]
    summary = summarize_context_window(turns)
    assert summary["peak_context_tokens"] == 320_002
    assert summary["used_1m_context"] is True
    assert summary["first_1m_at"] == "2026-05-30T10:05:00Z"


def test_context_is_summed_across_token_fields():
    # No single field exceeds 200k, but their sum does.
    turns = [_turn("2026-05-30T10:00:00Z", input=10_000, cache_read=150_000, cache_creation=60_000)]
    summary = summarize_context_window(turns)
    assert summary["peak_context_tokens"] == 220_000
    assert summary["used_1m_context"] is True
    assert summary["first_1m_at"] == "2026-05-30T10:00:00Z"


def test_first_1m_at_is_earliest_crossing_regardless_of_order():
    # A later-timestamp over-threshold turn appears before an earlier one in the
    # list; first_1m_at must still be the chronologically earliest crossing.
    turns = [
        _turn("2026-05-30T12:00:00Z", cache_read=400_000),
        _turn("2026-05-30T10:30:00Z", cache_read=250_000),
        _turn("2026-05-30T11:00:00Z", cache_read=80_000),
    ]
    summary = summarize_context_window(turns)
    assert summary["used_1m_context"] is True
    assert summary["first_1m_at"] == "2026-05-30T10:30:00Z"


def test_exactly_at_threshold_is_not_flagged():
    # Strictly greater than the cap is required; a prompt at exactly 200k could
    # still be a standard-window session at its limit.
    turns = [_turn("2026-05-30T10:00:00Z", cache_read=200_000)]
    summary = summarize_context_window(turns)
    assert summary["peak_context_tokens"] == 200_000
    assert summary["used_1m_context"] is False
    assert summary["first_1m_at"] is None
