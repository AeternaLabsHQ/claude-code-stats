"""Cache-write pricing: 5m writes at 1.25x input, 1h writes at 2x input."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import calc_cost, resolve_pricing


def _usage(creation=1_000_000, one_hour=0):
    u = {"input_tokens": 0, "output_tokens": 0,
         "cache_read_input_tokens": 0,
         "cache_creation_input_tokens": creation}
    if one_hour:
        u["cache_creation"] = {
            "ephemeral_5m_input_tokens": creation - one_hour,
            "ephemeral_1h_input_tokens": one_hour,
        }
    return u


def test_pure_5m_writes_priced_at_5m_rate():
    p = resolve_pricing("claude-opus-4-8")
    assert calc_cost("claude-opus-4-8", _usage()) == p["cache_write_5m"]


def test_1h_writes_priced_at_1h_rate():
    p = resolve_pricing("claude-opus-4-8")
    cost = calc_cost("claude-opus-4-8",
                     _usage(creation=1_000_000, one_hour=1_000_000))
    assert cost == p["cache_write_1h"]


def test_mixed_ttl_split():
    p = resolve_pricing("claude-opus-4-8")
    cost = calc_cost("claude-opus-4-8",
                     _usage(creation=1_000_000, one_hour=400_000))
    expected = 0.6 * p["cache_write_5m"] + 0.4 * p["cache_write_1h"]
    assert abs(cost - expected) < 1e-9


def test_missing_breakdown_falls_back_to_5m_rate():
    # Old transcripts without usage.cache_creation keep the old behavior.
    p = resolve_pricing("claude-opus-4-8")
    assert calc_cost("claude-opus-4-8", _usage()) == p["cache_write_5m"]


def test_malformed_1h_exceeding_creation_is_clamped():
    u = _usage(creation=100)
    u["cache_creation"] = {"ephemeral_1h_input_tokens": 500}
    p = resolve_pricing("claude-opus-4-8")
    expected = 100 * p["cache_write_1h"] / 1_000_000
    assert abs(calc_cost("claude-opus-4-8", u) - expected) < 1e-12
