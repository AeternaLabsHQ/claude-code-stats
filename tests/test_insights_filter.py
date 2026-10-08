"""Skills, hooks and git ops follow the date/project filter (issue #27).

These cards used to read the all-time server summaries (D.skill_summary etc.)
and were rendered once at load, so changing the date range had no effect.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_JS = (ROOT / "templates" / "dashboard.js").read_text(encoding="utf-8")


def function_body(name):
    m = re.search(r"function " + name + r"\([^)]*\) \{(.*?)\n\}", DASHBOARD_JS, re.S)
    assert m, f"{name} not found in dashboard.js"
    return m.group(1)


# Runs filterData() in Node against two sessions: one 60 days old in project
# "alpha", one from today in project "beta".
NODE_HARNESS = r"""
const document = { getElementById: id => id === 'hideEmptySessions' ? { checked: true } : null };
function recomputeIdleGapAggregate() {}
const day = n => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };
const D = {
  sessions: [
    { date: day(60), end: day(60) + 'T10:00:00', project: 'alpha', messages: 5, output_tokens: 10,
      skills: { 'old-skill': 3, shared: 1 }, hooks: { 'PostToolUse:Read': 4 },
      git_ops: [{ type: 'commit' }, { type: 'push' }] },
    { date: day(0), end: day(0) + 'T10:00:00', project: 'beta', messages: 5, output_tokens: 10,
      skills: { shared: 2, 'new-skill': 1 }, hooks: { 'SessionStart:startup': 1 },
      git_ops: [{ type: 'commit' }, { type: 'pr' }] },
  ],
  insights: {}, kpi: { total_cost: 0 }, plan: null,
  cost_by_token_type: { input: 0, output: 0, cache_read: 0, cache_write: 0 },
  hourly_distribution: [], weekday_distribution: [],
  daily_costs: [], daily_tokens: [], daily_messages: [], daily_cache_efficiency: [],
};
__SLICE__
const out = {};
const snap = () => ({ skills: F.skill_summary, hooks: F.hook_summary, git: F.git_summary });
filterData(0, ''); out.all = snap();
filterData(7, ''); out.week = snap();
filterData(0, 'alpha'); out.alpha = snap();
console.log(JSON.stringify(out));
"""


class InsightsFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start = DASHBOARD_JS.index("let F = {};")
        end = DASHBOARD_JS.index("function initTimeFilter()")
        cls.slice = DASHBOARD_JS[start:end]

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_filter_data_recomputes_skills_hooks_git(self):
        script = NODE_HARNESS.replace("__SLICE__", self.slice)
        res = subprocess.run(["node", "-"], input=script, capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)

        def counts(rows):
            self.assertIsNotNone(rows)
            self.assertEqual([r["count"] for r in rows],
                             sorted((r["count"] for r in rows), reverse=True))
            return {r["name"]: r["count"] for r in rows}

        self.assertEqual(counts(out["all"]["skills"]),
                         {"old-skill": 3, "shared": 3, "new-skill": 1})
        self.assertEqual(counts(out["all"]["hooks"]),
                         {"PostToolUse:Read": 4, "SessionStart:startup": 1})
        self.assertEqual(out["all"]["git"], {"commits": 2, "pushes": 1, "prs": 1})

        self.assertEqual(counts(out["week"]["skills"]), {"shared": 2, "new-skill": 1})
        self.assertEqual(counts(out["week"]["hooks"]), {"SessionStart:startup": 1})
        self.assertEqual(out["week"]["git"], {"commits": 1, "pushes": 0, "prs": 1})

        self.assertEqual(counts(out["alpha"]["skills"]), {"old-skill": 3, "shared": 1})
        self.assertEqual(counts(out["alpha"]["hooks"]), {"PostToolUse:Read": 4})
        self.assertEqual(out["alpha"]["git"], {"commits": 1, "pushes": 1, "prs": 0})

    def test_cards_never_read_all_time_summaries(self):
        for key in ("skill_summary", "hook_summary", "git_summary"):
            self.assertFalse("D." + key in DASHBOARD_JS, f"dashboard.js reads D.{key}")

    def test_cards_rerender_on_filter_change(self):
        self.assertIn("renderSkillsHooksGit();", function_body("applyFilter"))
        body = function_body("renderSkillsHooksGit")
        for key in ("skill_summary", "hook_summary", "git_summary"):
            self.assertIn("F." + key, body)


if __name__ == "__main__":
    unittest.main()
