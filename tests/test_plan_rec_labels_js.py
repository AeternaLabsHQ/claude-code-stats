"""Plan recommendation section: Max/Ultra display names and the Ultra note.

Extracts the two renderers from templates/dashboard.js and runs them in Node
(skipped without node) against a stub document and a fixture D."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_JS = ROOT / "templates" / "dashboard.js"

NODE_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
function grab(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing ' + name);
  const end = src.indexOf('\n}\n', start);
  return src.slice(start, end + 3);
}
const helpers = src.match(/function tierLabel\([^\n]*\n/)[0];
const tierMap = src.match(/const TIER_LABEL = [^\n]*\n/)[0];
const els = {};
global.document = { getElementById: (id) => (els[id] = els[id] || { innerHTML: '' }) };
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = {};
for (const [name, c] of Object.entries(cases)) {
  for (const k of Object.keys(els)) delete els[k];
  global.D = c.D;
  const run = new Function('document', 'D',
    tierMap + helpers + grab('renderRecommendationCard') + grab('renderPlanRecommendation') +
    'renderRecommendationCard(); renderPlanRecommendation();');
  run(global.document, c.D);
  out[name] = { card: els.limitsRecCard.innerHTML, plan: els.limitsPlanRec.innerHTML };
}
console.log(JSON.stringify(out));
"""

LOCALE_EN = json.loads((ROOT / "locales" / "en.json").read_text(encoding="utf-8"))["planRec"]


def _pr(ultra_from, current="Max 20x", rec="Max 20x"):
    hits = {"Pro": 3, "Max 5x": 1, "Max 20x": 0}
    return {
        "current_tier": current,
        "recommended_tier": rec,
        "ultra_no_5h_from": ultra_from,
        "ultra_launch_date": "2026-10-30",
        "cycles": [{
            "cycle_start": "2026-11-01", "label": "Nov 2026",
            "active_tier": "Max 20x", "switch_arrow": None,
            "tier_5h_hits": hits, "tier_weekly_hits": hits,
        }],
        "tier_total_5h_hits": hits,
        "tier_total_weekly_hits": hits,
        "calibration_5h": {"source": "empirical", "anchor_window_count": 4,
                           "caps_per_window": {"Pro": 5.0, "Max 5x": 25.0, "Max 20x": 100.0}},
        "calibration_weekly": {"ratio_vs_5h": 7,
                               "caps_per_week": {"Pro": 35.0, "Max 5x": 175.0, "Max 20x": 350.0}},
    }


def _render(cases, with_locale=False):
    payload = {}
    for name, pr in cases.items():
        D = {"plan_recommendation": pr}
        if with_locale:
            D["locale"] = {"planRec": LOCALE_EN}
        payload[name] = {"D": D}
    res = subprocess.run(["node", "-e", NODE_HARNESS.replace("process.argv[1]", json.dumps(str(DASHBOARD_JS)))],
                         input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlanRecLabelsJsTest(unittest.TestCase):
    def _check(self, with_locale):
        out = _render({"verified": _pr("2026-10-30"), "unverified": _pr(None),
                       "pro_rec": _pr("2026-10-30", current="Pro", rec="Max 5x")},
                      with_locale)
        v = out["verified"]
        # display names replace the internal tier keys everywhere
        heads = re.findall(r'<th class="ph-th[^"]*">([^<]*)', v["plan"])
        self.assertEqual(heads, ["Pro", "Max", "Ultra"] * 2)
        body = v["plan"].split('<div class="plan-rec-disclaimer">')[0]
        self.assertNotIn("Max 20x", body)
        self.assertNotIn("Max 5x", body)
        self.assertIn("Pro $5.00 / Max $25.00 / Ultra $100.00", v["plan"])
        self.assertIn("Pro $35 / Max $175 / Ultra $350", v["plan"])
        self.assertIn('class="rec-card-value">Ultra<', v["card"])
        self.assertNotIn("Max 20x", v["card"])
        # notes
        self.assertIn("Max was called Max 5x and Ultra was called Max 20x until 2026-10-30.", v["plan"])
        self.assertIn("Since 2026-10-30, Ultra has no 5-hour limit for verified accounts", v["plan"])
        self.assertEqual(v["plan"].count("Ultra's weekly allowance is 10x Pro since then."), 1)
        self.assertIn("weekly 1:5:10 since Ultra", v["plan"])
        self.assertNotIn("—", v["plan"])
        # unverified: rename note stays, ultra note goes
        u = out["unverified"]
        self.assertIn("until 2026-10-30.", u["plan"])
        self.assertIn("Ultra's weekly allowance is 10x Pro since then.", u["plan"])
        self.assertNotIn("has no 5-hour limit", u["plan"])
        # recommendation card for a switch shows the new names
        p = out["pro_rec"]
        self.assertIn('class="rec-card-value">Max<', p["card"])
        self.assertIn("Current tier: Pro", p["card"])

    def test_with_locale(self):
        self._check(True)

    def test_js_fallback_strings(self):
        self._check(False)

    def test_locales_have_new_keys(self):
        for lang in ("en", "de"):
            L = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))["planRec"]
            self.assertIn("{date}", L["renameNote"])
            self.assertIn("{date}", L["ultraNote"])
            self.assertIn("10x", L["renameNote"])
            self.assertNotIn("10x", L["ultraNote"])
            self.assertIn("1:5:10", L["disclaimer"])
            for k in ("renameNote", "ultraNote"):
                self.assertNotIn("—", L[k])


if __name__ == "__main__":
    unittest.main()
