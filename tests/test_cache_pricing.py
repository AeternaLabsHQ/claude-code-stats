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


# ── Haiku 5.5: prompt-length tiers ────────────────────────────────────────
# A request whose prompt (input + cache reads + cache writes) is over 100k
# tokens pays the long-context rates on every token type, output included.

def _haiku_usage(input_tokens=0, cache_read=0, creation=0, output=1_000_000):
    return {"input_tokens": input_tokens, "output_tokens": output,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": creation}


def test_haiku_5_5_short_prompt_uses_base_rates():
    # 100k exactly is not "over 100k".
    u = _haiku_usage(input_tokens=10_000, cache_read=80_000, creation=10_000)
    expected = (10_000 * 0.10 + 1_000_000 * 0.50 + 80_000 * 0.01
                + 10_000 * 0.125) / 1_000_000
    assert abs(calc_cost("claude-haiku-5-5", u) - expected) < 1e-12


def test_haiku_5_5_long_prompt_uses_long_context_rates():
    # Cache reads count towards the prompt length: 100_001 tips it over.
    u = _haiku_usage(input_tokens=10_000, cache_read=80_001, creation=10_000)
    expected = (10_000 * 0.50 + 1_000_000 * 2.50 + 80_001 * 0.05
                + 10_000 * 0.625) / 1_000_000
    assert abs(calc_cost("claude-haiku-5-5", u) - expected) < 1e-12


def test_haiku_5_5_long_prompt_1h_writes():
    u = _haiku_usage(creation=200_000, output=0)
    u["cache_creation"] = {"ephemeral_1h_input_tokens": 200_000}
    assert abs(calc_cost("claude-haiku-5-5", u) - 200_000 * 1.00 / 1e6) < 1e-12


def test_output_tokens_do_not_count_towards_prompt_length():
    u = _haiku_usage(input_tokens=50_000, output=200_000)
    expected = (50_000 * 0.10 + 200_000 * 0.50) / 1_000_000
    assert abs(calc_cost("claude-haiku-5-5", u) - expected) < 1e-12


def test_long_prompt_does_not_change_flat_models():
    u = _haiku_usage(cache_read=500_000, output=0)
    p = resolve_pricing("claude-sonnet-5-5")
    assert abs(calc_cost("claude-sonnet-5-5", u)
               - 500_000 * p["cache_read"] / 1e6) < 1e-12
