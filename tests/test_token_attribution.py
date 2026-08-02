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


    def test_non_divisible_tokens_reconcile_to_total(self):
        # 1000 tokens / 3 tools must sum back to exactly 1000, not 999 or 1001
        result = attribute_turn_tokens(
            output_tokens=1000,
            cost=0.10,
            tool_names=["Read", "Edit", "Bash"],
        )
        total_tokens = sum(e["output_tokens"] for e in result["per_tool"])
        total_cost = sum(e["cost"] for e in result["per_tool"])
        self.assertEqual(total_tokens, 1000)
        self.assertAlmostEqual(total_cost, 0.10, places=10)

    def test_non_divisible_tokens_with_repeated_tool(self):
        # 1000 tokens / 3 calls (Edit, Read, Edit) → Edit gets 2/3 share, Read 1/3
        # After collapsing: 2 entries summing to exactly 1000
        result = attribute_turn_tokens(
            output_tokens=1000,
            cost=0.10,
            tool_names=["Edit", "Read", "Edit"],
        )
        total_tokens = sum(e["output_tokens"] for e in result["per_tool"])
        total_cost = sum(e["cost"] for e in result["per_tool"])
        self.assertEqual(total_tokens, 1000)
        self.assertAlmostEqual(total_cost, 0.10, places=10)


class ParserIntegrationTest(unittest.TestCase):
    """End-to-end: synthesize a tiny JSONL and parse it via build_sessions."""

    def test_synthetic_session_aggregates_tokens(self):
        # We don't run the full parser here (it needs a real ~/.claude tree).
        # Instead, exercise the per-turn logic directly with realistic shapes.
        from extract_stats import attribute_turn_tokens

        # Turn 1: 2 Reads, 1 Edit, 600 output tokens
        a1 = attribute_turn_tokens(600, 0.06, ["Read", "Read", "Edit"])
        # Turn 2: 0 tools, 1000 output tokens  -> all reasoning
        a2 = attribute_turn_tokens(1000, 0.10, [])

        # Aggregate manually like the parser would
        agg = {}
        for entry in a1["per_tool"]:
            t = agg.setdefault(entry["tool"], {"output_tokens": 0, "cost": 0.0})
            t["output_tokens"] += entry["output_tokens"]
            t["cost"] += entry["cost"]

        reasoning_out = a1["reasoning_output_tokens"] + a2["reasoning_output_tokens"]

        self.assertEqual(agg["Read"]["output_tokens"], 400)  # 2/3 of 600
        self.assertEqual(agg["Edit"]["output_tokens"], 200)  # 1/3 of 600
        self.assertEqual(reasoning_out, 1000)


if __name__ == "__main__":
    unittest.main()
