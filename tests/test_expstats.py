"""expstats: cluster-robust ratio and median statistics for experiment IDs."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core.expstats import (Z95, compare, median_stat, ratio_stat,
                                       values_median_stat)

STEPS = 32


def bin_of(v, steps=STEPS):
    """Same bin formula as experiments.hist_bin, with explicit steps."""
    return str(math.floor(math.log2(v) * steps) + 1)


class RatioStatTests(unittest.TestCase):
    def test_pooled_ratio_matches_simple_share(self):
        r = ratio_stat([{"a": (1, 10)}, {"a": (3, 10)}])
        self.assertAlmostEqual(r["est"], 0.2, places=6)
        self.assertAlmostEqual(r["se"], 0.1, places=6)
        self.assertEqual(r["n_units"], 2)
        self.assertEqual(r["x"], 20)

    def test_standardized_ratio_uses_weights(self):
        units = [{"a": (1, 10), "b": (5, 10)}, {"a": (1, 10), "b": (5, 10)}]
        r = ratio_stat(units, {"a": 0.75, "b": 0.25})
        self.assertAlmostEqual(r["est"], 0.2, places=6)

    def test_weighted_missing_stratum_gives_no_estimate(self):
        r = ratio_stat([{"a": (1, 10)}], {"a": 0.5, "b": 0.5})
        self.assertIsNone(r["est"])

    def test_single_unit_has_no_se(self):
        r = ratio_stat([{"a": (1, 10)}])
        self.assertIsNone(r["se"])
        self.assertAlmostEqual(r["est"], 0.1)

    def test_empty_units(self):
        r = ratio_stat([])
        self.assertIsNone(r["est"])
        self.assertIsNone(r["se"])
        self.assertEqual(r["n_units"], 0)

    def test_empty_or_zero_weights_give_no_estimate(self):
        for w in ({}, {"a": 0}, {"a": 0.0, "b": 0}):
            r = ratio_stat([{"a": (1, 10)}, {"a": (3, 10)}], w)
            self.assertIsNone(r["est"])
            self.assertIsNone(r["se"])

    def test_centre_overrides_linearisation_point(self):
        units = [{"a": (10, 10)}, {"a": (10, 10)}]
        self.assertEqual(ratio_stat(units)["se"], 0.0)
        r = ratio_stat(units, centre=0.5)
        self.assertEqual(r["est"], 1.0)
        # z = (10 - 5)/20 = 0.25 each, Σz² = 0.125, factor 2
        self.assertAlmostEqual(r["se"], 0.5, places=6)

    def test_weighted_se_matches_hand_value(self):
        # a: Y=4, X=20, r=0.2; b: Y=10, X=20, r=0.5; est = 0.35.
        # z = 0.5*(1-2)/20, 0.5*(3-2)/20, 0, 0 = -0.025, 0.025, 0, 0;
        # se = sqrt(4/3 * 0.00125).
        units = [{"a": (1, 10)}, {"a": (3, 10)}, {"b": (5, 10)},
                 {"b": (5, 10)}]
        r = ratio_stat(units, {"a": 0.5, "b": 0.5})
        self.assertAlmostEqual(r["est"], 0.35, places=9)
        self.assertAlmostEqual(r["se"], math.sqrt(4 / 3 * 0.00125), places=9)
        self.assertEqual(r["y"], 14)
        self.assertEqual(r["x"], 40)

    def test_centre_per_stratum(self):
        # Same units, centred at 0.3 in a and 0.4 in b:
        # z = 0.5*(1-3)/20, 0.5*(3-3)/20, 0.5*(5-4)/20, 0.5*(5-4)/20
        #   = -0.05, 0, 0.025, 0.025; se = sqrt(4/3 * 0.00375).
        units = [{"a": (1, 10)}, {"a": (3, 10)}, {"b": (5, 10)},
                 {"b": (5, 10)}]
        r = ratio_stat(units, {"a": 0.5, "b": 0.5},
                       centre={"a": 0.3, "b": 0.4})
        self.assertAlmostEqual(r["est"], 0.35, places=9)
        self.assertAlmostEqual(r["se"], math.sqrt(4 / 3 * 0.00375), places=9)
        # Unweighted: z = (y - c_s * x) / X summed over the unit's strata,
        # here the same values (each stratum holds half of X).
        r = ratio_stat(units, centre={"a": 0.3, "b": 0.4})
        self.assertAlmostEqual(r["se"], math.sqrt(4 / 3 * 0.00375), places=9)

    def test_units_without_x_do_not_count(self):
        r = ratio_stat([{"a": (1, 10)}, {"a": (0, 0)}, {"a": (3, 10)}])
        self.assertEqual(r["n_units"], 2)
        self.assertAlmostEqual(r["se"], 0.1, places=6)


class MedianStatTests(unittest.TestCase):
    def test_median_ci_contains_median_and_spans_a_bin(self):
        b = bin_of(300)
        r = median_stat([{"a": {b: 50}} for _ in range(20)], steps=STEPS)
        self.assertLess(r["lo"], r["est"])
        self.assertLess(r["est"], r["hi"])
        self.assertGreaterEqual(r["hi"] / r["lo"], 2 ** (1 / STEPS) - 1e-12)
        self.assertEqual(r["n"], 1000)
        self.assertEqual(r["n_units"], 20)

    def test_clustered_median_ci_is_wider(self):
        low, high = bin_of(10), bin_of(1000)
        # Same pooled histogram (200 low, 200 high), different clustering:
        # two homogeneous units vs 40 identical mixed units.
        few = [{"a": {low: 200}}, {"a": {high: 200}}]
        many = [{"a": {low: 5, high: 5}} for _ in range(40)]
        a = median_stat(few, steps=STEPS)
        b = median_stat(many, steps=STEPS)
        self.assertEqual(a["est"], b["est"])
        self.assertIsNotNone(a["lo"])
        self.assertIsNotNone(b["lo"])
        self.assertGreater(a["hi"] / a["lo"], b["hi"] / b["lo"])

    def test_ci_spans_both_bins_when_cdf_straddles_half(self):
        low, high = bin_of(10), bin_of(1000)
        # 13 all-low and 12 all-high sessions: F(low) = 0.52, median in low.
        units = ([{"a": {low: 50}} for _ in range(13)]
                 + [{"a": {high: 50}} for _ in range(12)])
        r = median_stat(units, steps=STEPS)
        self.assertLess(r["est"], 20)
        self.assertGreater(r["hi"], 900)
        self.assertLess(r["lo"], 10)

    def test_median_in_top_bin_does_not_collapse_ci(self):
        low, high = bin_of(10), bin_of(1000)
        # F(low) = 0.48 so the median is the top occupied bin (F = 1.0).
        units = ([{"a": {low: 50}} for _ in range(12)]
                 + [{"a": {high: 50}} for _ in range(13)])
        r = median_stat(units, steps=STEPS)
        self.assertGreater(r["est"], 500)
        self.assertGreater(r["hi"] / r["lo"], 50)  # reaches down into low bin

    def test_single_unit_has_no_ci(self):
        r = median_stat([{"a": {bin_of(300): 10}}], steps=STEPS)
        self.assertIsNotNone(r["est"])
        self.assertIsNone(r["lo"])
        self.assertIsNone(r["hi"])

    def test_empty(self):
        r = median_stat([], steps=STEPS)
        self.assertIsNone(r["est"])
        self.assertEqual(r["n"], 0)

    def test_zero_bin_median_is_zero(self):
        r = median_stat([{"a": {"0": 9, bin_of(5): 1}}, {"a": {"0": 8}}],
                        steps=STEPS)
        self.assertEqual(r["est"], 0.0)

    def test_weighted_median_centres_each_stratum(self):
        # Effort-pure sessions whose strata sit on opposite sides of the
        # median: F_a(low) = 0.8, F_b(low) = 0.2, standardized F(low) = 0.5.
        # Centred per stratum (c_a = 0.8, c_b = 0.2) every influence value
        # is 0, so the CI is the median bin alone. Centring every stratum at
        # 0.5 gave se = 0.069 and a CI over both bins.
        low, high = bin_of(10), bin_of(1000)
        units = ([{"a": {low: 8, high: 2}} for _ in range(10)]
                 + [{"b": {low: 2, high: 8}} for _ in range(10)])
        r = median_stat(units, {"a": 0.5, "b": 0.5}, steps=STEPS)
        self.assertLess(r["est"], 20)
        self.assertAlmostEqual(r["se"], 0.0, places=12)
        self.assertAlmostEqual(r["hi"] / r["lo"], 2 ** (1 / STEPS), places=9)

    def test_weighted_median_se_hand_value(self):
        # a (weight 0.9): 4 sessions over bins A1 < A2 < A3 with totals
        # 12/12/16; b (weight 0.1): 4 sessions in two high bins. Standardized
        # F(A1) = 0.27, F(A2) = 0.54, so m = A2 with F_a = 0.6, F_b = 0.
        # Centres: c_a = 0.6 - 0.04 = 0.56, c_b = 0 - 0.04 = -0.04.
        # z_a = 0.9*(y - 5.6)/40 for y = 6, 8, 4, 6; z_b = 0.1*0.4/40.
        # The old 0.5 centring gave 0.0875 here.
        a1, a2, a3 = bin_of(10), bin_of(20), bin_of(40)
        b1, b2 = bin_of(1000), bin_of(2000)
        units = [{"a": {a1: 3, a2: 3, a3: 4}}, {"a": {a1: 4, a2: 4, a3: 2}},
                 {"a": {a1: 2, a2: 2, a3: 6}}, {"a": {a1: 3, a2: 3, a3: 4}}]
        units += [{"b": {b1: 5, b2: 5}} for _ in range(4)]
        r = median_stat(units, {"a": 0.9, "b": 0.1}, steps=STEPS)
        self.assertGreater(r["est"], 19)
        self.assertLess(r["est"], 21)
        zs = [0.009, 0.054, -0.036, 0.009] + [0.001] * 4
        expected = math.sqrt(8 / 7 * sum(z * z for z in zs))
        self.assertAlmostEqual(r["se"], expected, places=9)

    def test_single_stratum_weight_matches_pooled(self):
        low, high = bin_of(10), bin_of(1000)
        units = ([{"a": {low: 7, high: 3}} for _ in range(6)]
                 + [{"a": {low: 2, high: 8}} for _ in range(5)])
        pooled = median_stat(units, steps=STEPS)
        std = median_stat(units, {"a": 1.0}, steps=STEPS)
        for k in ("est", "lo", "hi", "n", "n_units"):
            self.assertEqual(pooled[k], std[k], k)
        self.assertAlmostEqual(pooled["se"], std["se"], places=12)

    def test_standardized_median_uses_weights(self):
        low, high = bin_of(10), bin_of(1000)
        # Stratum a (all low) is rare in the data but dominant in the weights.
        units = [{"a": {low: 10}, "b": {high: 90}} for _ in range(10)]
        pooled = median_stat(units, steps=STEPS)
        std = median_stat(units, {"a": 0.9, "b": 0.1}, steps=STEPS)
        self.assertGreater(pooled["est"], 500)
        self.assertLess(std["est"], 20)


class ValuesMedianTests(unittest.TestCase):
    def test_values_median_stat(self):
        r = values_median_stat([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        self.assertEqual(r["est"], 6)
        self.assertLessEqual(r["lo"], 6)
        self.assertGreaterEqual(r["hi"], 6)
        self.assertEqual(r["n"], 11)

    def test_even_count_averages_middle_pair(self):
        self.assertEqual(values_median_stat([1, 2, 3, 10])["est"], 2.5)

    def test_tiny_samples(self):
        self.assertIsNone(values_median_stat([])["est"])
        one = values_median_stat([7])
        self.assertEqual(one["est"], 7)
        self.assertIsNone(one["lo"])
        self.assertIsNone(one["hi"])

    def test_rank_ci_is_clamped(self):
        r = values_median_stat([1, 2])
        self.assertGreaterEqual(r["lo"], 1)
        self.assertLessEqual(r["hi"], 2)


class CompareTests(unittest.TestCase):
    def test_compare_ratio_p_and_ci(self):
        c = compare({"est": 0.4, "se": 0.02}, {"est": 0.2, "se": 0.02}, "ratio")
        self.assertAlmostEqual(c["change"], 1.0)
        self.assertLess(c["p"], 0.001)
        self.assertLess(c["lo"], 1.0)
        self.assertGreater(c["hi"], 1.0)

    def test_p_matches_normal_tail(self):
        # z = 1.959964 -> two-sided p = 0.05
        se = 0.01 / math.sqrt(2)
        c = compare({"est": 0.2 + 0.01 * Z95, "se": se},
                    {"est": 0.2, "se": se}, "ratio")
        self.assertAlmostEqual(c["p"], 0.05, places=4)

    def test_zero_estimate_gives_p_but_no_ci(self):
        c = compare({"est": 0.0, "se": 0.01}, {"est": 0.2, "se": 0.02}, "ratio")
        self.assertIsNotNone(c["p"])
        self.assertIsNone(c["lo"])
        self.assertIsNone(c["hi"])
        self.assertAlmostEqual(c["change"], -1.0)

    def test_compare_missing_se(self):
        c = compare({"est": 0.4, "se": 0.02}, {"est": 0.2, "se": None}, "ratio")
        self.assertIsNone(c["p"])
        self.assertIsNone(c["lo"])
        self.assertAlmostEqual(c["change"], 1.0)

    def test_compare_missing_estimate(self):
        c = compare({"est": None, "se": None}, {"est": 0.2, "se": 0.02}, "ratio")
        self.assertIsNone(c["change"])
        self.assertIsNone(c["p"])
        c = compare({"est": 0.2, "se": 0.02}, {"est": 0, "se": 0.02}, "ratio")
        self.assertIsNone(c["change"])

    def test_compare_median_uses_log_scale(self):
        a = {"est": 400.0, "lo": 300.0, "hi": 533.0}
        b = {"est": 200.0, "lo": 150.0, "hi": 267.0}
        c = compare(a, b, "median")
        self.assertAlmostEqual(c["change"], 1.0)
        self.assertLess(c["p"], 0.001)
        self.assertLess(c["lo"], 1.0)
        self.assertGreater(c["hi"], 1.0)

    def test_compare_median_without_ci_gives_nothing(self):
        a = {"est": 400.0, "lo": None, "hi": None}
        b = {"est": 200.0, "lo": 150.0, "hi": 267.0}
        c = compare(a, b, "median")
        self.assertIsNone(c["p"])
        self.assertIsNone(c["lo"])
        self.assertAlmostEqual(c["change"], 1.0)

    def test_compare_median_zero_lower_edge(self):
        a = {"est": 400.0, "lo": 0.0, "hi": 533.0}
        b = {"est": 200.0, "lo": 150.0, "hi": 267.0}
        self.assertIsNone(compare(a, b, "median")["p"])


if __name__ == "__main__":
    unittest.main()
