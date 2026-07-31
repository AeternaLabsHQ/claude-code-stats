"""A config written before the cost_local rename must keep its currency view."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _plan_currency_symbol


def test_legacy_cost_eur_implies_euro_symbol():
    # cost_eur was euro by definition, so the symbol is recoverable.
    ph = {"plan": "Max", "cost_usd": 93.00, "cost_eur": 87.61}
    assert _plan_currency_symbol(ph) == "€"


def test_explicit_symbol_always_wins():
    ph = {"plan": "Max", "cost_usd": 100.0, "cost_local": 92.0,
          "currency_symbol": "CHF"}
    assert _plan_currency_symbol(ph) == "CHF"


def test_explicit_symbol_wins_even_next_to_legacy_key():
    ph = {"plan": "Max", "cost_usd": 93.0, "cost_eur": 87.61,
          "currency_symbol": "£"}
    assert _plan_currency_symbol(ph) == "£"


def test_modern_config_without_symbol_stays_none():
    # cost_local carries no currency information, so nothing may be guessed.
    ph = {"plan": "Max", "cost_usd": 100.0, "cost_local": 92.0}
    assert _plan_currency_symbol(ph) is None


def test_plan_without_any_local_cost_stays_none():
    ph = {"plan": "Pro", "cost_usd": 20.0}
    assert _plan_currency_symbol(ph) is None
