"""Retired tab anchors must still resolve to a tab that exists."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DASHBOARD_JS = (ROOT / "templates" / "dashboard.js").read_text(encoding="utf-8")

# Anchors that shipped in 0.8.x and no longer have a tab of their own.
RETIRED_ANCHORS = {"projects", "agents"}


def tab_ids():
    block = re.search(r"const TAB_NAMES = \[(.*?)\];", DASHBOARD_JS, re.S)
    assert block, "TAB_NAMES array not found in dashboard.js"
    return set(re.findall(r"id:\s*'([a-z]+)'", block.group(1)))


def aliases():
    block = re.search(r"const TAB_ALIASES = \{(.*?)\};", DASHBOARD_JS, re.S)
    assert block, "TAB_ALIASES map not found in dashboard.js"
    return dict(re.findall(r"(\w+):\s*'([a-z]+)'", block.group(1)))


class TabAliasTest(unittest.TestCase):
    def test_every_retired_anchor_has_an_alias(self):
        self.assertEqual(set(aliases()) & RETIRED_ANCHORS, RETIRED_ANCHORS)

    def test_every_alias_points_at_a_real_tab(self):
        ids = tab_ids()
        for old, new in aliases().items():
            self.assertIn(new, ids, f"alias {old} points at unknown tab {new}")

    def test_aliases_do_not_shadow_live_tabs(self):
        # An alias for a tab that still exists would hijack a working link.
        self.assertEqual(set(aliases()) & tab_ids(), set())

    def test_hash_router_consults_the_alias_map(self):
        router = re.search(r"function tabFromHash\(\) \{(.*?)\n\}",
                           DASHBOARD_JS, re.S)
        self.assertIsNotNone(router, "tabFromHash not found")
        self.assertIn("TAB_ALIASES", router.group(1))
