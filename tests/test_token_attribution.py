import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import attribute_turn_tokens


class AttributeTurnTokensTest(unittest.TestCase):
    def test_no_tools_returns_reasoning_only(self):
        result = attribute_turn_tokens(
            output_tokens=1000,
            cost=0.05,
            tool_names=[],
        )
        self.assertEqual(result, {
            "per_tool": [],
            "reasoning_output_tokens": 1000,
            "reasoning_cost": 0.05,
        })

    def test_single_tool_gets_full_share(self):
        result = attribute_turn_tokens(
            output_tokens=800,
            cost=0.04,
            tool_names=["Read"],
        )
        self.assertEqual(result["reasoning_output_tokens"], 0)
        self.assertEqual(result["reasoning_cost"], 0.0)
        self.assertEqual(len(result["per_tool"]), 1)
        self.assertEqual(result["per_tool"][0]["tool"], "Read")
        self.assertEqual(result["per_tool"][0]["output_tokens"], 800)
        self.assertAlmostEqual(result["per_tool"][0]["cost"], 0.04)

    def test_multiple_tools_split_equally(self):
        result = attribute_turn_tokens(
            output_tokens=900,
            cost=0.09,
            tool_names=["Read", "Edit", "Bash"],
        )
        self.assertEqual(len(result["per_tool"]), 3)
        for entry in result["per_tool"]:
            self.assertEqual(entry["output_tokens"], 300)
            self.assertAlmostEqual(entry["cost"], 0.03)

    def test_repeated_tool_in_same_turn_aggregates(self):
        # Two Edit calls in one turn -> Edit appears once with 2/2 share
        result = attribute_turn_tokens(
            output_tokens=400,
            cost=0.02,
            tool_names=["Edit", "Edit"],
        )
        self.assertEqual(len(result["per_tool"]), 1)
        self.assertEqual(result["per_tool"][0]["tool"], "Edit")
        self.assertEqual(result["per_tool"][0]["output_tokens"], 400)
        self.assertAlmostEqual(result["per_tool"][0]["cost"], 0.02)

    def test_zero_output_tokens_returns_zeros(self):
        result = attribute_turn_tokens(
            output_tokens=0,
            cost=0.0,
            tool_names=["Read"],
        )
        self.assertEqual(result["per_tool"][0]["output_tokens"], 0)
        self.assertAlmostEqual(result["per_tool"][0]["cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
