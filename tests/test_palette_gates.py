"""Palette gate checks against the real CSS tokens (see tools/palette_check.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import palette_check as pc  # noqa: E402


class MathTest(unittest.TestCase):
    def test_contrast_black_on_white_is_21(self):
        self.assertAlmostEqual(pc.contrast("#000000", "#ffffff"), 21.0, places=1)

    def test_identical_colors_have_zero_delta(self):
        self.assertEqual(pc.delta_e("#c2562f", "#c2562f"), 0.0)

    def test_red_green_collapse_under_deutan(self):
        # The old status pair: clearly apart for normal vision, not for deutan.
        self.assertGreater(pc.delta_e("#1f9d63", "#d24b3e"), 25)
        self.assertLess(pc.cvd_delta("#1f9d63", "#d24b3e"), 8)


class ParserTest(unittest.TestCase):
    def test_marked_blocks_are_parsed(self):
        css = ("/* PALETTE:base:light */\n.vc { --vc-panel: #ffffff; --vc-x: 1px; }\n"
               "/* PALETTE:default:light */\n.vc { --vc-cat-1: #c2562f; }\n")
        blocks = pc.load_blocks(css)
        self.assertEqual(blocks[("base", "light")]["--vc-panel"], "#ffffff")
        self.assertEqual(blocks[("default", "light")]["--vc-cat-1"], "#c2562f")

    def test_nested_media_block_is_parsed(self):
        css = ("@media (prefers-color-scheme: dark) {\n"
               "  /* PALETTE:base:dark-media */\n"
               "  html:not(.theme-light) .vc { --vc-panel: #181b21; }\n}\n")
        self.assertEqual(pc.load_blocks(css)[("base", "dark-media")]["--vc-panel"], "#181b21")


class RealCssGatesTest(unittest.TestCase):
    def test_all_gates_pass_on_dashboard_css(self):
        palettes = pc.load_palettes(pc.CSS.read_text(encoding="utf-8"))
        self.assertEqual(pc.run_gates(palettes), [])

    def test_every_chart_token_defined_in_every_variant(self):
        blocks = pc.load_blocks(pc.CSS.read_text(encoding="utf-8"))
        expected = ({f"--vc-cat-{i}" for i in range(1, 9)} | {"--vc-cat-n1", "--vc-cat-n2"}
                    | {f"--vc-model-{f}-{s}" for f in pc.FAMILIES for s in range(1, 5)}
                    | {"--vc-model-unknown", "--vc-series-1", "--vc-series-2", "--vc-series-soft"})
        for pal in ("default", "cvd"):
            for var in ("light", "dark", "dark-media", "light-forced"):
                missing = expected - set(blocks[(pal, var)])
                self.assertEqual(missing, set(), f"{pal}/{var}")


if __name__ == "__main__":
    unittest.main()
