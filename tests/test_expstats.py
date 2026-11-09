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
        self.assertIsNotNone(b["lo"])
        if a["lo"] is not None:
            self.assertGreater(a["hi"] / a["lo"], b["hi"] / b["lo"])

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
