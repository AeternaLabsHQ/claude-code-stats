"""Insights "Experiments" section: VCExperiments.html() rendered in Node
(skipped without node), plus locale and template wiring checks."""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COMPONENTS = ROOT / "templates" / "components"
EXPERIMENTS_JS = COMPONENTS / "experiments.js"

# Loads shared_helpers.js + experiments.js with stubbed DOM globals, then
# renders every case from the JSON on stdin and prints {name: html}.
NODE_HARNESS = r"""
const fs = require('fs');
global.window = { __LOCALE__: { locale_code: 'en-US' } };
global.document = {
  getElementById: () => null,
  querySelector: () => null,
  createElement: () => ({ style: {}, getContext: () => null }),
  body: { appendChild() {} },
  documentElement: { classList: { contains: () => false, add() {}, remove() {} } },
};
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
global.localStorage = { getItem: () => null, setItem() {} };
eval(fs.readFileSync(process.argv[1], 'utf8'));
eval(fs.readFileSync(process.argv[2], 'utf8'));
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = {};
for (const [name, c] of Object.entries(cases)) {
  const opts = c.anon ? { anon: true, anonSource: n => 'Source ' + (n.length) } : undefined;
  out[name] = window.VCExperiments.html(c.exp, c.L, opts);
}
console.log(JSON.stringify(out));
"""

FULL = "21e0afd842ce5836"


def metrics(multi, text, bash, out, cost):
    return {"multi_tool_share": multi, "text_before_share": text,
            "median_bash_chars": bash, "median_output_tokens": out,
            "cost_per_reply": cost}


def summary(verdict="changed", model="claude-opus-5", sources=("desktop",),
            current=None, text_change=-0.55):
    return {
        "has_data": True,
        "thresholds": {"min_replies": 200, "rel_change": 0.4,
                       "min_changed_metrics": 2, "baseline_pad_days": 14,
                       "min_support": 30},
        "current": current or [],
        "ids": [{
            "id": FULL, "short": "21e",
            "first_day": "2026-06-20", "last_day": "2026-06-22",
            "sources": list(sources), "sessions": 3,
            "days": {"2026-06-20": {s: 100 for s in sources},
                     "2026-06-22": {s: 200 for s in sources}},
            "models": [{
                "model": model, "replies": 300,
                # Narrower than the ID-wide range: the card shows these.
                "first_day": "2026-06-21", "last_day": "2026-06-22",
                "metrics": metrics(0.4, 0.09, 650.0, 940.0, 0.0123),
                "baseline": {"replies": 400, "from": "2026-06-06",
                             "to": "2026-07-06",
                             "metrics": metrics(0.2, 0.2, 300.0, 450.0, 0.01)},
                "changes": {"multi_tool_share": 1.0,
                            "text_before_share": text_change,
                            "median_bash_chars": 1.1667,
                            "median_output_tokens": 0.1},
                "verdict": verdict,
            }, {
                "model": "tiny-model", "replies": 5,
                "first_day": "2026-06-20", "last_day": "2026-06-20",
                "metrics": metrics(0.0, None, None, 10.0, 0.0),
                "baseline": {"replies": 0, "from": "2026-06-06",
                             "to": "2026-07-06",
                             "metrics": metrics(0.0, None, None, None, 0.0)},
                "changes": {"multi_tool_share": None,
                            "text_before_share": None,
                            "median_bash_chars": None,
                            "median_output_tokens": None},
                "verdict": "insufficient",
            }],
        }],
    }


def load_locale(name):
    return json.loads((ROOT / "locales" / f"{name}.json")
                      .read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExperimentsHtmlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = load_locale("en").get("experiments", {})
        cur = [{"model": "claude-opus-5", "entrypoint": "cli",
                "id": FULL, "at": "2026-11-08T10:00:00+00:00"},
               {"model": "claude-sonnet-5", "entrypoint": "cli",
                "id": "", "at": "2026-11-08T10:00:00+00:00"}]
        # One judged card plus one "too little data" card (tiny-model
        # raised above the 20-reply card cutoff).
        mixed = summary("changed")
        mixed["ids"][0]["models"][1]["replies"] = 50
        cases = {
            "null": {"exp": None, "L": cls.L},
            "nodata": {"exp": {"has_data": False, "ids": [], "current": []},
                       "L": cls.L},
            "nodata_current": {"exp": {"has_data": False, "ids": [],
                                       "current": cur}, "L": cls.L},
            "changed": {"exp": summary("changed", current=cur), "L": cls.L},
            "no_effect": {"exp": summary("no_effect"), "L": cls.L},
            "insufficient": {"exp": summary("insufficient"), "L": cls.L},
            "escaped": {"exp": summary(model="<b>x</b>"), "L": cls.L},
            "plain": {"exp": summary(sources=("desktop", "laptop")),
                      "L": cls.L},
            "anon": {"exp": summary(sources=("desktop", "laptop")),
                     "L": cls.L, "anon": True},
            "no_locale": {"exp": summary(), "L": {}},
            "null_change": {"exp": summary(text_change=None), "L": cls.L},
            "null_change_no_locale": {"exp": summary(text_change=None),
                                      "L": {}},
            "mixed": {"exp": mixed, "L": cls.L},
        }
        res = subprocess.run(
            ["node", "-e", NODE_HARNESS, str(COMPONENTS / "shared_helpers.js"),
             str(EXPERIMENTS_JS)],
            input=json.dumps(cases), capture_output=True, text=True,
            timeout=60)
        if res.returncode != 0:
            raise AssertionError(res.stdout + res.stderr)
        cls.out = json.loads(res.stdout)

    def test_empty_state(self):
        for name in ("null", "nodata"):
            h = self.out[name]
            self.assertIn(self.L["empty"], h, name)
            self.assertNotIn("exp-card", h, name)
            self.assertNotIn("exp-current", h, name)

    def test_empty_state_keeps_current_assignment(self):
        h = self.out["nodata_current"]
        self.assertIn(self.L["empty"], h)
        self.assertIn("exp-current", h)
        self.assertIn("21e", h)

    def test_card_and_badge(self):
        h = self.out["changed"]
        self.assertIn("exp-card", h)
        self.assertIn("21e", h)
        self.assertIn(self.L["verdict_changed"], h)
        self.assertIn("exp-badge changed", h)
        for k in ("m_multi_tool_share", "m_text_before_share",
                  "m_median_bash_chars", "m_median_output_tokens",
                  "m_cost_per_reply"):
            self.assertIn(self.L[k], h, k)
        self.assertIn("exp-timeline", h)
        self.assertIn(self.L["intro"].split(".")[0], h)

    def test_small_models_get_no_card(self):
        h = self.out["changed"]
        self.assertEqual(h.count('exp-card"'), 1)
        self.assertNotIn("tiny-model", h)

    def test_change_colored_only_above_threshold(self):
        h = self.out["changed"]
        self.assertIn("+100%", h)
        self.assertIn("+10%", h)
        self.assertEqual(h.count("exp-chg sig"), 3)  # 1.0, -0.55, 1.1667

    def test_insufficient_card_does_not_highlight_changes(self):
        h = self.out["insufficient"]
        self.assertIn(self.L["verdict_insufficient"], h)
        self.assertIn("+100%", h)
        self.assertNotIn("exp-chg sig", h)

    def test_hide_switch_with_mixed_cards(self):
        h = self.out["mixed"]
        self.assertIn("data-exp-hide-insufficient", h)
        self.assertIn(self.L["hide_insufficient"].replace("{n}", "1"), h)
        self.assertEqual(h.count("exp-card--insufficient"), 1)
        self.assertEqual(h.count('<article class="chart-box exp-card"'), 1)

    def test_no_hide_switch_without_both_kinds(self):
        # Only judged cards, or only "too little data" cards: hiding would
        # either do nothing or leave the section empty.
        self.assertNotIn("data-exp-hide-insufficient", self.out["changed"])
        self.assertNotIn("data-exp-hide-insufficient", self.out["insufficient"])

    def test_no_effect_badge(self):
        h = self.out["no_effect"]
        self.assertIn(self.L["verdict_no_effect"], h)
        self.assertIn("exp-badge muted", h)
        self.assertNotIn("exp-badge changed", h)

    def test_current_chips(self):
        h = self.out["changed"]
        self.assertIn("exp-current", h)
        self.assertIn(FULL, h)            # full ID in the chip title
        self.assertIn(self.L["current_none"], h)

    def test_thresholds_footnote(self):
        h = self.out["changed"]
        self.assertIn("200", h)
        self.assertIn("40%", h)
        self.assertNotIn("{min}", h)
        self.assertNotIn("{pct}", h)
        self.assertNotIn("{support}", h)

    def test_footnote_mentions_support_floor(self):
        h = self.out["changed"]
        method = h[h.index('class="exp-method"'):]
        self.assertIn("30", method)
        self.assertIn("10%", method)   # medians are approximate

    def test_unsupported_change_shows_too_few_events(self):
        h = self.out["null_change"]
        self.assertEqual(h.count("exp-chg na"), 1)
        self.assertIn(self.L["change_na"], h)
        self.assertEqual(h.count("exp-chg sig"), 2)   # 1.0 and 1.1667
        # The values themselves are still shown.
        self.assertIn("9.0%", h)
        self.assertIn("20.0%", h)
        self.assertIn("too few events",
                      self.out["null_change_no_locale"])

    def test_cost_row_keeps_dash(self):
        h = self.out["null_change"]
        cost = h[h.index("exp-cost"):]
        self.assertNotIn("exp-chg na", cost)

    def test_card_meta_uses_model_days(self):
        h = self.out["changed"]
        meta = h[h.index('class="exp-card-meta"'):]
        meta = meta[:meta.index("</div>")]
        self.assertIn("Jun 21, 2026 - Jun 22, 2026", meta)
        self.assertNotIn("Jun 20", meta)

    def test_escapes_model_name(self):
        h = self.out["escaped"]
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", h)
        self.assertNotIn("<b>x</b>", h)

    def test_sources_shown_without_anon(self):
        h = self.out["plain"]
        self.assertIn("desktop", h)
        self.assertIn("laptop", h)

    def test_sources_masked_in_anon_mode(self):
        h = self.out["anon"]
        self.assertNotIn("desktop", h)
        self.assertNotIn("laptop", h)
        self.assertIn("Source 6", h)   # anonSource stub: 'Source ' + len
        self.assertIn("Source 7", h)

    def test_english_fallbacks_without_locale(self):
        h = self.out["no_locale"]
        self.assertIn("exp-card", h)
        self.assertNotIn("undefined", h)


class ExperimentsLocaleTest(unittest.TestCase):
    def test_locale_keys_present(self):
        src = EXPERIMENTS_JS.read_text(encoding="utf-8")
        keys = set(re.findall(r"\bL\.([a-z_]+)", src))
        self.assertTrue(keys)
        for name in ("en", "de"):
            sec = load_locale(name).get("experiments", {})
            missing = sorted(keys - set(sec))
            self.assertFalse(missing, f"{name}: missing {missing}")


class ExperimentsTemplateTest(unittest.TestCase):
    def test_dashboard_template_wires_section(self):
        import extract_stats
        html = extract_stats._get_html_template()
        self.assertIn('data-sub="experiments"', html)
        self.assertIn('id="experimentsRoot"', html)
        self.assertIn("VCExperiments", html)
        self.assertIn(".exp-card", html)

    def test_f2_path_rerenders_with_anon(self):
        js = (ROOT / "templates" / "dashboard.js").read_text(encoding="utf-8")
        m = re.search(r"function applyFilter\([^)]*\) \{(.*?)\n\}", js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("renderExperiments();", m.group(1))
        m = re.search(r"function renderExperiments\(\) \{(.*?)\n\}", js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("anon: anonMode", m.group(1))
        self.assertIn("anonSource: anonSource", m.group(1))

    def test_project_page_has_no_experiments_component(self):
        import extract_stats
        html = extract_stats._build_project_html_template()
        self.assertNotIn("VCExperiments", html)


if __name__ == "__main__":
    unittest.main()
