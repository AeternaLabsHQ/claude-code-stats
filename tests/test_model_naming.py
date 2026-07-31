import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import (
    DEFAULT_PRICING,
    PRICING,
    build_pricing_warnings,
    calc_cost,
    derive_model_display,
    get_model_display,
    pricing_for_display,
    resolve_pricing,
)


class DeriveModelDisplayTest(unittest.TestCase):
    """The parser must reproduce every curated PRICING display name from the
    raw id alone, so a brand-new model is named correctly with no code change."""

    def test_reproduces_every_curated_display_name(self):
        # Ground truth: the parser must derive exactly what the PRICING table
        # hardcodes, for every known model id.
        for model_id, entry in PRICING.items():
            with self.subTest(model_id=model_id):
                self.assertEqual(derive_model_display(model_id), entry["display"])

    def test_family_first_with_minor(self):
        self.assertEqual(derive_model_display("claude-opus-4-8"), "Opus 4.8")

    def test_family_first_with_date_stamp(self):
        self.assertEqual(derive_model_display("claude-haiku-4-5-20251001"), "Haiku 4.5")

    def test_family_first_no_minor(self):
        self.assertEqual(derive_model_display("claude-opus-4-20250514"), "Opus 4")

    def test_version_first_legacy_format(self):
        self.assertEqual(derive_model_display("claude-3-opus-20240229"), "Opus 3")

    def test_version_first_legacy_with_minor(self):
        self.assertEqual(derive_model_display("claude-3-5-haiku-20241022"), "Haiku 3.5")

    def test_future_model_needs_no_code_change(self):
        # A ".0" model is named bare-major ("Opus 9"), matching how Anthropic
        # names models (there is no "Opus 4.0", only "Opus 4"). Non-zero minors
        # keep the dotted form.
        self.assertEqual(derive_model_display("claude-opus-9-0"), "Opus 9")
        self.assertEqual(derive_model_display("claude-sonnet-5-2-20270101"), "Sonnet 5.2")

    def test_zero_minor_renders_bare_major(self):
        # The '-0' alias forms (claude-opus-4-0, claude-sonnet-4-0) name the same
        # model as the bare/dated entry, so they must NOT render as "Opus 4.0".
        self.assertEqual(derive_model_display("claude-opus-4-0"), "Opus 4")
        self.assertEqual(derive_model_display("claude-sonnet-4-0"), "Sonnet 4")

    def test_stacked_variant_markers_are_stripped(self):
        self.assertEqual(derive_model_display("claude-opus-4-8[1m][beta]"), "Opus 4.8")

    def test_case_insensitive(self):
        self.assertEqual(derive_model_display("CLAUDE-OPUS-4-8"), "Opus 4.8")

    def test_synthetic_marker(self):
        self.assertEqual(derive_model_display("<synthetic>"), "Synthetic")

    def test_no_model_defaults_to_unknown(self):
        # message.get("model", "unknown") feeds the literal "unknown" through.
        self.assertEqual(derive_model_display("unknown"), "Unknown")

    def test_never_crashes_on_odd_input(self):
        # Must degrade gracefully, never raise.
        for bad in ["", "claude-", "gpt-4o", None, 42]:
            with self.subTest(bad=bad):
                self.assertIsInstance(derive_model_display(bad), str)


class ModelVariantNormalizationTest(unittest.TestCase):
    """Real ids carry a trailing variant marker like '[1m]' (1M-context
    enablement). It must collapse onto the base model, not split off."""

    def test_1m_context_variant_derives_to_base_display(self):
        # claude-opus-4-8[1m] is the live 1M-context Opus 4.8 id.
        self.assertEqual(derive_model_display("claude-opus-4-8[1m]"), "Opus 4.8")
        self.assertEqual(derive_model_display("claude-sonnet-4-5[1m]"), "Sonnet 4.5")

    def test_get_model_display_collapses_variant_to_base(self):
        self.assertEqual(get_model_display("claude-opus-4-8[1m]"), "Opus 4.8")


class ResolvePricingTest(unittest.TestCase):
    def test_exact_id_resolves_to_its_entry(self):
        self.assertIs(resolve_pricing("claude-opus-4-8"), PRICING["claude-opus-4-8"])

    def test_1m_variant_resolves_to_base_entry(self):
        self.assertIs(resolve_pricing("claude-opus-4-8[1m]"), PRICING["claude-opus-4-8"])

    def test_dated_variant_of_undated_entry_resolves_to_it(self):
        # API may emit a date-stamped form of a dateless table entry.
        self.assertIs(
            resolve_pricing("claude-opus-4-8-20260601"), PRICING["claude-opus-4-8"]
        )

    def test_undated_variant_of_dated_entry_resolves_to_it(self):
        self.assertIs(
            resolve_pricing("claude-opus-4-5"), PRICING["claude-opus-4-5-20251101"]
        )

    def test_zero_minor_alias_resolves_to_curated_base(self):
        # claude-opus-4-0 is an alias for the dated "Opus 4" entry; must not
        # drop to DEFAULT (a 5x underpricing).
        self.assertIs(
            resolve_pricing("claude-opus-4-0"), PRICING["claude-opus-4-20250514"]
        )
        self.assertIs(
            resolve_pricing("claude-sonnet-4-0"), PRICING["claude-sonnet-4-20250514"]
        )

    def test_genuinely_unknown_model_falls_back_to_default(self):
        self.assertIs(resolve_pricing("claude-opus-9-0"), DEFAULT_PRICING)


class CalcCostConsistencyTest(unittest.TestCase):
    USAGE = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }

    def test_1m_variant_costs_the_same_as_base_model(self):
        # Regression: variant must not silently drop to DEFAULT_PRICING.
        self.assertAlmostEqual(
            calc_cost("claude-opus-4-8[1m]", self.USAGE),
            calc_cost("claude-opus-4-8", self.USAGE),
        )

    def test_1m_variant_is_priced_at_opus_rates_not_default(self):
        opus = calc_cost("claude-opus-4-8[1m]", self.USAGE)
        default = (
            self.USAGE["input_tokens"] * DEFAULT_PRICING["input"] / 1_000_000
            + self.USAGE["output_tokens"] * DEFAULT_PRICING["output"] / 1_000_000
        )
        self.assertNotAlmostEqual(opus, default)


class GetModelDisplayTest(unittest.TestCase):
    def test_known_model_uses_curated_name(self):
        self.assertEqual(get_model_display("claude-opus-4-8"), "Opus 4.8")

    def test_unknown_claude_model_is_derived_not_unknown(self):
        # Regression: previously collapsed to "Unknown"; now named from the id.
        self.assertEqual(get_model_display("claude-opus-9-0"), "Opus 9")

    def test_unparseable_model_still_returns_string(self):
        self.assertIsInstance(get_model_display("gpt-4o"), str)


class PricingForDisplayTest(unittest.TestCase):
    def test_matched_display_returns_its_pricing_entry(self):
        self.assertIs(pricing_for_display("Opus 4.8"), PRICING["claude-opus-4-8"])

    def test_unmatched_display_falls_back_to_default_not_first_entry(self):
        # Bugfix: an unknown/derived display must use DEFAULT_PRICING, NOT
        # list(PRICING.keys())[0] (which would misprice it at Fable rates).
        self.assertIs(pricing_for_display("Opus 9"), DEFAULT_PRICING)
        self.assertIs(pricing_for_display("Unknown"), DEFAULT_PRICING)

    def test_opus_5_is_priced_not_defaulted(self):
        # Regression: claude-opus-5 sat in the Unknown bucket and was costed
        # at DEFAULT_PRICING ($3/$15) instead of $5/$25, a 40% undercount.
        self.assertIsNot(pricing_for_display("Opus 5"), DEFAULT_PRICING)
        self.assertEqual(PRICING["claude-opus-5"]["input"], 5.00)
        self.assertEqual(PRICING["claude-opus-5"]["output"], 25.00)


class BuildPricingWarningsTest(unittest.TestCase):
    def test_unknown_claude_model_is_flagged_with_derived_name(self):
        warnings = build_pricing_warnings(["claude-opus-9-0"])
        self.assertEqual(warnings, [{"model_id": "claude-opus-9-0", "display": "Opus 9"}])

    def test_known_model_is_not_flagged(self):
        self.assertEqual(build_pricing_warnings(["claude-opus-4-8"]), [])

    def test_non_claude_markers_are_not_flagged(self):
        # <synthetic>, gpt-4o, "unknown", empties are not billable Claude models.
        self.assertEqual(
            build_pricing_warnings(["<synthetic>", "gpt-4o", "unknown", "", None]),
            [],
        )

    def test_priced_variants_are_not_false_flagged(self):
        # These all resolve to a known PRICING entry, so the user should NOT be
        # nagged to add them: the 1M-context variant, a dated form of a dateless
        # entry, and an undated form of a date-stamped entry.
        self.assertEqual(build_pricing_warnings(["claude-opus-4-8[1m]"]), [])
        self.assertEqual(build_pricing_warnings(["claude-opus-4-8-20260601"]), [])
        self.assertEqual(build_pricing_warnings(["claude-opus-4-5"]), [])

    def test_dedupes_variants_to_deterministic_base_id(self):
        # Several id forms of one unknown model collapse to a single warning, and
        # the surfaced model_id is the canonical base regardless of input order
        # (callers pass a set, so iteration order is otherwise nondeterministic).
        warnings = build_pricing_warnings(
            ["claude-opus-9-0[1m]", "claude-opus-9-0-20990101", "claude-opus-9-0"]
        )
        self.assertEqual(warnings, [{"model_id": "claude-opus-9-0", "display": "Opus 9"}])

    def test_deduplicates_and_sorts_by_display(self):
        warnings = build_pricing_warnings(
            ["claude-sonnet-9-0", "claude-opus-9-0", "claude-sonnet-9-0"]
        )
        self.assertEqual(
            warnings,
            [
                {"model_id": "claude-opus-9-0", "display": "Opus 9"},
                {"model_id": "claude-sonnet-9-0", "display": "Sonnet 9"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
