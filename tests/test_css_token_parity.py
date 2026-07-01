"""Parity guard for the VC-SHARED CSS blocks (see tools/check_css_tokens.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_css_tokens as cct  # noqa: E402


def fence(name, body):
    return f"/* VC-SHARED:{name}:START */\n{body}\n/* VC-SHARED:{name}:END */\n"


class ExtractBlocksTest(unittest.TestCase):
    def test_extracts_single_block(self):
        text = "before\n" + fence("tokens", ".vc { --x: 1; }") + "after\n"
        self.assertEqual(cct.extract_blocks(text, "f"), {"tokens": ".vc { --x: 1; }"})

    def test_extracts_multiple_blocks(self):
        text = fence("tokens", "a") + "mid\n" + fence("topbar", "b")
        self.assertEqual(cct.extract_blocks(text, "f"), {"tokens": "a", "topbar": "b"})

    def test_unclosed_block_raises(self):
        with self.assertRaises(ValueError):
            cct.extract_blocks("/* VC-SHARED:tokens:START */\nx\n", "f")

    def test_mismatched_end_raises(self):
        text = "/* VC-SHARED:tokens:START */\nx\n/* VC-SHARED:topbar:END */\n"
        with self.assertRaises(ValueError):
            cct.extract_blocks(text, "f")

    def test_nested_start_raises(self):
        text = (
            "/* VC-SHARED:tokens:START */\n"
            "/* VC-SHARED:topbar:START */\n"
            "/* VC-SHARED:topbar:END */\n"
            "/* VC-SHARED:tokens:END */\n"
        )
        with self.assertRaises(ValueError):
            cct.extract_blocks(text, "f")


class CompareTest(unittest.TestCase):
    def test_identical_blocks_pass(self):
        per_file = {"a.css": {"tokens": "x"}, "b.css": {"tokens": "x"}}
        self.assertEqual(cct.compare(per_file), [])

    def test_drifted_block_reported_with_diff(self):
        per_file = {"a.css": {"tokens": "x"}, "b.css": {"tokens": "y"}}
        problems = cct.compare(per_file)
        self.assertEqual(len(problems), 1)
        self.assertIn("drifted", problems[0])
        self.assertIn("-x", problems[0])
        self.assertIn("+y", problems[0])

    def test_missing_block_reported(self):
        per_file = {"a.css": {"tokens": "x"}, "b.css": {}}
        problems = cct.compare(per_file)
        self.assertTrue(any("missing in b.css" in p for p in problems))

    def test_no_blocks_anywhere_is_a_problem(self):
        per_file = {"a.css": {}, "b.css": {}}
        self.assertTrue(cct.compare(per_file))


class RealFilesParityTest(unittest.TestCase):
    # TODO(Task 2): expectedFailure entfernen, sobald der tokens-Block
    # in allen drei Dateien kanonisiert ist.
    @unittest.expectedFailure
    def test_shared_blocks_identical(self):
        per_file = {}
        for rel in cct.FILES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            per_file[rel] = cct.extract_blocks(text, rel)
        self.assertEqual(cct.compare(per_file), [])


if __name__ == "__main__":
    unittest.main()
