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


def row(key, group, kind, base, value, change, lo, hi, p, comparable=False,
        n=120, base_n=150):
    return {"key": key, "group": group, "kind": kind, "base": base,
            "value": value, "change": change, "lo": lo, "hi": hi, "p": p,
            "n": n, "base_n": base_n, "comparable": comparable}


def rows(text_change=-0.55):
    """All METRICS rows in backend order (claudestats_core.experiments)."""
    t = text_change is not None
    return [
        row("multi_tool_share", "behaviour", "share", 0.2, 0.4, 1.0,
            0.5, 1.6, 0.001, True),
        row("text_before_share", "behaviour", "share", 0.2, 0.09,
            text_change, -0.8 if t else None, -0.2 if t else None,
            0.002 if t else None, t),
        row("median_bash_chars", "behaviour", "int", 300.0, 650.0, 1.1667,
            0.2, 2.1, 0.03, True),
        row("median_output_tokens", "behaviour", "int", 450.0, 940.0, 0.1,
            -0.05, 0.25, 0.3, True),
        row("cost_per_reply", "context", "usd", 0.01, 0.0123, 0.23,
            0.1, 0.4, 0.004),
        row("session_cost", "session", "usd", 1.5, 4.2, 1.8, 0.6, 3.1,
            0.0004),
        row("session_replies", "session", "int", 40.0, 90.0, 1.25, 0.5,
            2.0, 0.01),
        row("session_prompts", "session", "int", 6.0, 6.5, 0.08, -0.3, 0.5,
            0.6),
        row("session_tool_calls", "session", "int", 70.0, 160.0, 1.28, 0.4,
            2.2, 0.02),
        row("session_active_min", "session", "int", 25.0, 31.0, 0.24,
            -0.1, 0.6, 0.2),
        row("cost_per_prompt", "session", "usd", 0.3, 0.7, 1.33, 0.5, 2.0,
            0.003),
        row("tool_error_rate", "quality", "rate", 0.02, 0.05, 1.5, 0.4,
            2.9, 0.01),
        row("repeat_call_rate", "quality", "rate", 0.1, 0.1, 0.0, -0.2,
            0.2, 0.9),
        row("rejected_rate", "quality", "rate", 0.01, 0.0, -1.0, None,
            None, None),
        row("interrupt_rate", "quality", "rate", 0.04, 0.06, 0.5, -0.1,
            1.2, 0.2),
        row("correction_rate", "quality", "rate", 0.03, 0.03, 0.0, -0.5,
            0.5, 0.95),
        row("re_edit_rate", "quality", "rate", 0.2, 0.1, -0.5, -0.9, -0.1,
            0.0002),
    ]


def card(model, replies, verdict, reason=None, text_change=-0.55, **kw):
    c = {
        "model": model, "replies": replies, "sessions": 12,
        # Narrower than the ID-wide range: the card shows these.
        "first_day": "2026-06-21", "last_day": "2026-06-22",
        "session_start_from": "2026-06-20", "session_start_to": "2026-06-22",
        "entrypoints": {"cli": 250, "vscode": 50},
        "base_entrypoints": {"cli": 380, "vscode": 20},
        "base_sdk_replies": 77,
        "effort_mix": {"high": 200, "xhigh": 100},
        "base_effort_mix": {"high": 300, "xhigh": 100},
        "unmatched_replies": 0,
        "late_replies": 0, "base_late_replies": 0,
        "baseline": {"replies": 400, "sessions": 30, "from": "2026-06-06",
                     "to": "2026-07-06"},
        "rows": rows(text_change), "verdict": verdict, "reason": reason,
    }
    c.update(kw)
    return c


def summary(verdict="changed", model="claude-opus-5", sources=("desktop",),
            current=None, text_change=-0.55, reason=None, **card_kw):
    return {
        "has_data": True,
        "thresholds": {"min_replies": 200, "rel_change": 0.4,
                       "min_changed_metrics": 2, "baseline_pad_days": 14,
                       "min_support": 30, "min_sessions": 5, "alpha": 0.05,
                       "late_cutoff_days": 7, "active_gap_min": 30,
                       "correction_max_chars": 160},
        "current": current or [],
        "ids": [{
            "id": FULL, "short": "21e",
            "first_day": "2026-06-20", "last_day": "2026-06-22",
            "sources": list(sources), "sessions": 3,
            "days": {"2026-06-20": {s: 100 for s in sources},
                     "2026-06-22": {s: 200 for s in sources}},
            "models": [
                card(model, 300, verdict, reason, text_change, **card_kw),
                card("tiny-model", 5, "insufficient", "few_replies"),
            ],
        }, {
            # Only SDK replies: on the timeline, but no card.
            "id": "9ab5555555555555", "short": "9ab",
            "first_day": "2026-06-21", "last_day": "2026-06-21",
            "sources": list(sources), "sessions": 1,
            "days": {"2026-06-21": {s: 10 for s in sources}}, "models": [],
        }],
        "thinking": [{
            "model": model,
            "rows": [
                {"id": "", "short": "",
                 "cells": {"high": {"replies": 500, "median": 812.0,
                                    "mean": 900.5},
                           "xhigh": {"replies": 120, "median": 1500.0,
                                     "mean": 1650.2}}},
                {"id": FULL, "short": "21e",
                 "cells": {"high": {"replies": 80, "median": 401.0,
                                    "mean": 450.1}}},
            ],
        }],
    }


def load_locale(name):
    return json.loads((ROOT / "locales" / f"{name}.json")
                      .read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExperimentsHtmlTest(unittest.TestCase):
    METRIC_KEYS = (
        "multi_tool_share", "text_before_share", "median_bash_chars",
        "median_output_tokens", "cost_per_reply", "session_cost",
        "session_replies", "session_prompts", "session_tool_calls",
        "session_active_min", "cost_per_prompt", "tool_error_rate",
        "repeat_call_rate", "rejected_rate", "interrupt_rate",
        "correction_rate", "re_edit_rate")

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
            "insufficient": {"exp": summary("insufficient",
                                           reason="few_sessions"),
                             "L": cls.L},
            "escaped": {"exp": summary(model="<b>x</b>"), "L": cls.L},
            "plain": {"exp": summary(sources=("desktop", "laptop")),
                      "L": cls.L},
            "anon": {"exp": summary(sources=("desktop", "laptop"),
                                    current=cur),
                     "L": cls.L, "anon": True},
            "late": {"exp": summary(late_replies=4, base_late_replies=6,
                                    unmatched_replies=9),
                     "L": cls.L},
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
        for k in self.METRIC_KEYS:
            self.assertIn(self.L["m_" + k], h, k)
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
        # 1.0, -0.55, 1.1667 (behaviour rows only; session and quality
        # rows move a lot too but never get the loud colour)
        self.assertEqual(h.count("exp-chg sig"), 3)

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
        # The non-comparable row shows no CI or p either.
        na_row = h[h.rindex("<tr", 0, h.index("exp-chg na")):]
        na_row = na_row[:na_row.index("</tr>")]
        self.assertEqual(na_row.count("<td"), 6)
        self.assertEqual(na_row.count(">-<"), 2)
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
        self.assertNotIn("exp-chg sig", cost)

    def test_card_meta_uses_model_days(self):
        h = self.out["changed"]
        meta = h[h.index('class="exp-card-meta"'):]
        meta = meta[:meta.index("</div>")]
        self.assertIn('">Jun 21, 2026 - Jun 22, 2026 \u00b7', meta)

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

    def test_anon_hides_full_id(self):
        h = self.out["anon"]
        self.assertNotIn(FULL, h)
        self.assertNotIn(FULL[:8], h)
        self.assertIn(FULL[:3], h)
        # Chips carry model and short ID only, no entrypoint or date.
        chips = h[h.index('class="exp-chips"'):]
        chips = chips[:chips.index("</div>")]
        self.assertNotIn("title=", chips)
        self.assertNotIn("2026-11-08", chips)
        self.assertNotIn(">cli<", chips)
        # Without anon the full ID is still reachable as a tooltip.
        self.assertIn(FULL, self.out["plain"])

    def test_id_without_cards_stays_on_timeline(self):
        h = self.out["changed"]
        self.assertIn(">9ab<", h)
        self.assertEqual(h.count('exp-card"'), 1)

    def test_rule_visible_in_card_and_badge_title(self):
        h = self.out["changed"]
        rule = self.L["rule"]
        for k, v in (("{n}", "2"), ("{pct}", "40"), ("{alpha}", "0.05"),
                     ("{min}", "200"), ("{sessions}", "5")):
            rule = rule.replace(k, v)
        self.assertNotIn("{", rule)
        from html import escape
        rule = escape(rule)
        badge = h[h.index('<span class="exp-badge'):]
        badge = badge[:badge.index("</span>")]
        self.assertIn('title="' + rule, badge)
        foot = h[h.index('class="exp-card-foot'):]
        self.assertIn(">" + rule + "<", foot)
        self.assertIn("exp-rule", foot)

    def test_insufficient_shows_reason(self):
        h = self.out["insufficient"]
        badge = h[h.index('<span class="exp-badge'):]
        badge = badge[:badge.index("</span>")]
        reason = self.L["reason_few_sessions"].replace("{sessions}", "5")
        self.assertNotIn("{", reason)
        self.assertIn(reason, badge)
        self.assertIn("= at least 2 of the 4", badge)
        # A judged card carries no reason in its badge.
        ok = self.out["changed"]
        ok_badge = ok[ok.index('<span class="exp-badge'):]
        ok_badge = ok_badge[:ok_badge.index("</span>")]
        self.assertNotIn(reason, ok_badge)

    def test_three_groups_rendered(self):
        h = self.out["changed"]
        card = h[h.index('<article'):h.index("</article>")]
        self.assertEqual(card.count("<tbody"), 3)
        order = [card.index(self.L[k]) for k in
                 ("group_behaviour", "group_session", "group_quality")]
        self.assertEqual(order, sorted(order))
        # cost per reply is a context row inside the behaviour group
        beh_end = card.index(self.L["group_session"])
        self.assertLess(card.index("exp-cost"), beh_end)
        self.assertLess(card.index(self.L["m_median_output_tokens"]),
                        card.index("exp-cost"))
        self.assertEqual(card.count("exp-group-h"), 3)

    def test_ci_and_p_columns(self):
        h = self.out["changed"]
        for k in ("col_ci", "col_p"):
            self.assertIn(self.L[k], h, k)
        self.assertIn("+50% .. +160%", h)     # multi_tool CI
        self.assertIn("-80% .. -20%", h)      # text_before CI
        self.assertIn("&lt;0.001", h)         # p 0.0004
        self.assertIn("0.030", h)             # p 0.03, three decimals
        self.assertIn("0.300", h)

    def test_sig_only_for_behaviour_rows(self):
        h = self.out["changed"]
        card = h[h.index('<article'):h.index("</article>")]
        # session_cost (+180%, p 0.0004) and re_edit_rate are large and
        # significant, but only behaviour rows get the loud colour.
        sess = card[card.index(self.L["group_session"]):]
        self.assertNotIn("exp-chg sig", sess)
        beh = card[:card.index(self.L["group_session"])]
        self.assertEqual(beh.count("exp-chg sig"), 3)
        # median_output_tokens: 10%, p 0.3 -> plain
        row = beh[beh.index(self.L["m_median_output_tokens"]):]
        self.assertNotIn("exp-chg sig", row[:row.index("</tr>")])

    def test_sig_needs_p_below_alpha(self):
        # Large move but p >= alpha: not highlighted.
        exp = summary("changed")
        for r in exp["ids"][0]["models"][0]["rows"]:
            if r["key"] == "median_output_tokens":
                r["change"], r["p"] = 0.9, 0.2
        out = self.render({"x": {"exp": exp, "L": self.L}})["x"]
        self.assertEqual(out.count("exp-chg sig"), 3)

    def test_value_formats(self):
        h = self.out["changed"]
        self.assertIn("40.0%", h)       # share
        self.assertIn("$0.0123", h)     # usd
        self.assertIn("5.00%", h)       # rate
        self.assertIn("650", h)         # int

    def test_card_foot_lines(self):
        h = self.out["changed"]
        foot = h[h.index('class="exp-card-foot'):h.index("</article>")]
        self.assertIn("cli 250", foot)
        self.assertIn("vscode 20", foot)
        self.assertIn(self.L["sdk_excluded"].replace("{n}", "77"), foot)
        self.assertIn("xhigh 33%", foot)        # ID mix share
        self.assertIn("high 67%", foot)
        self.assertNotIn("{", foot)
        # no late / unmatched lines when zero
        self.assertNotIn("exp-late", foot)
        self.assertNotIn("exp-unmatched", foot)

    def test_late_and_unmatched_lines(self):
        h = self.out["late"]
        self.assertIn("exp-late", h)
        self.assertIn("exp-unmatched", h)
        late = h[h.index("exp-late"):]
        late = late[:late.index("</p>")]
        self.assertIn("4", late)
        self.assertIn("6", late)
        self.assertIn("7", late)         # cutoff days

    def test_meta_has_session_starts(self):
        h = self.out["changed"]
        meta = h[h.index('class="exp-card-meta"'):]
        meta = meta[:meta.index("</div>")]
        self.assertIn(self.L["session_starts"].split("{")[0].strip(), meta)
        self.assertIn("Jun 20, 2026 - Jun 22, 2026", meta)
        self.assertIn("12 " + self.L["sessions"], meta)

    def test_thinking_table(self):
        h = self.out["changed"]
        self.assertIn(self.L["thinking_title"], h)
        self.assertIn(self.L["thinking_hint"], h)
        box = h[h.index("exp-think"):]
        self.assertIn(self.L["thinking_no_id"], box)
        self.assertIn("xhigh", box)
        self.assertIn("812 (500)", box)
        self.assertIn("1,500 (120)", box)
        self.assertIn("401 (80)", box)
        self.assertIn("claude-opus-5", box)
        self.assertGreater(box.index("812 (500)"), box.index("thinking"))
        # after the cards
        self.assertGreater(h.index("exp-think"), h.index("</article>"))

    def test_no_thinking_box_without_data(self):
        exp = summary("changed")
        exp["thinking"] = []
        out = self.render({"x": {"exp": exp, "L": self.L}})["x"]
        self.assertNotIn(self.L["thinking_title"], out)

    def test_caveats_rendered(self):
        h = self.out["changed"]
        self.assertIn('<ul class="exp-caveats">', h)
        self.assertIn(self.L["caveats_title"], h)
        items = self.L["caveats"]
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 8)
        for c in items:
            self.assertIn(c.replace("{late}", "7"), h)
        self.assertEqual(h.count("<li>"), 8)

    def test_table_wrapped_for_scroll(self):
        h = self.out["changed"]
        self.assertIn('<div class="exp-table-wrap"><table class="exp-table"', h)
        css = (COMPONENTS / "experiments.css").read_text(encoding="utf-8")
        m = re.search(r"\.exp-table-wrap\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        self.assertIn("overflow-x: auto", m.group(1))

    def test_no_dashes_in_texts(self):
        for name in ("en", "de"):
            sec = load_locale(name)["experiments"]
            blob = json.dumps(sec, ensure_ascii=False)
            self.assertNotIn("\u2014", blob, name)
            self.assertNotIn("\u2013", blob, name)

    def render(self, cases):
        res = subprocess.run(
            ["node", "-e", NODE_HARNESS, str(COMPONENTS / "shared_helpers.js"),
             str(EXPERIMENTS_JS)],
            input=json.dumps(cases), capture_output=True, text=True,
            timeout=60)
        if res.returncode != 0:
            raise AssertionError(res.stdout + res.stderr)
        return json.loads(res.stdout)

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
