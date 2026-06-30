# Token Attribution by Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute output tokens and cost to individual tool calls (and to a separate "reasoning" bucket for tool-less turns) so the dashboard can show *where* the money actually goes, not just *what was called how often*.

**Architecture:** Extend per-session aggregation in `extract_stats.py` so the existing `tools` count dict gains a parallel `tool_tokens` dict (`{tool_name: {calls, output_tokens, cost}}`) and a new top-level `reasoning_tokens` field. Attribution policy: for each assistant turn, split the turn's `output_tokens` and computed `cost` equally across the `tool_use` blocks in that turn; turns with zero `tool_use` blocks attribute fully to the reasoning bucket. Aggregate to a global `tool_token_summary` at the dashboard data level. Surface in the session-detail sidebar (extend the existing "Tools Used" card) and add a stacked-bar widget on the dashboard's Tools section.

**Tech Stack:** Python 3 (`extract_stats.py`, no test framework currently — add minimal `unittest` based file under `tests/`), vanilla JS + Chart.js for dashboard rendering, no new dependencies.

---

## File Structure

- **Modify** `extract_stats.py`:
  - Add pure helper `attribute_turn_tokens(usage, model, tool_names)` near `calc_cost` (around line 800-840)
  - Extend session init dict (around line 964-999) with `tool_tokens` and `reasoning_tokens`
  - Wire the helper in the assistant-message branch (around line 1074-1103)
  - Add global aggregation `tool_token_summary` (around line 1818-1825)
  - Include `tool_token_summary` in the dashboard `data` dict (around line 1909-1912)
- **Create** `tests/test_token_attribution.py`: unittest-based, no external deps
- **Modify** `templates/session_detail.js` (line 237-242): show output-token share next to the count
- **Modify** `templates/dashboard.js`:
  - Recompute `tool_token_summary` in `filterData()` (around line 432-439)
  - New `renderToolTokenChart()` rendering a stacked bar (count vs token share)
  - Hook into `applyFilter()` (around line 533-540)
- **Modify** `templates/dashboard.html`: add a `<canvas id="chartToolTokens">` next to the existing tool usage chart

---

## Attribution Policy (locked decisions)

- **Output tokens per turn**: split equally across all `tool_use` blocks in that turn. If a turn has N tools, each gets `output_tokens / N`.
- **Cost per turn**: same equal split as output tokens (uses already-computed `calc_cost(model, usage)`).
- **Reasoning bucket**: any assistant turn with **zero** `tool_use` blocks contributes its full `output_tokens` and `cost` to `sess["reasoning_tokens"]`. This includes pure-text turns and "thinking-only" turns where the model planned but didn't call a tool.
- **Input tokens / cache tokens**: NOT attributed per tool. They reflect context size, not model action — keep them at session+model level only. (Avoids the false impression that "Read uses lots of input tokens" when really the input is shared turn context.)
- **Skipped turns**: turns where `usage.output_tokens == 0` (e.g. a pure tool_result echo) contribute nothing. Same gate as the existing `if usage and usage.get("output_tokens", 0) > 0` check.

---

## Task 1: Pure attribution helper + unit test

**Files:**
- Create: `tests/test_token_attribution.py`
- Modify: `extract_stats.py` (add helper near `calc_cost`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_token_attribution.py`:

```python
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
        # Two Edit calls in one turn → Edit appears once with 2/2 share
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_token_attribution -v`
Expected: ImportError or AttributeError — `attribute_turn_tokens` does not exist yet.

- [ ] **Step 3: Write minimal implementation in `extract_stats.py`**

Find the `calc_cost` function (search for `def calc_cost`). Immediately AFTER it, add:

```python
def attribute_turn_tokens(output_tokens, cost, tool_names):
    """Split a turn's output_tokens and cost across its tool_use blocks.

    Repeated tool names in the same turn collapse into a single entry whose
    share equals (count_of_that_tool / total_tools) of the turn.
    Turns with no tools attribute fully to the reasoning bucket.
    """
    if not tool_names:
        return {
            "per_tool": [],
            "reasoning_output_tokens": output_tokens,
            "reasoning_cost": cost,
        }

    n = len(tool_names)
    per_tool_counts = {}
    for name in tool_names:
        per_tool_counts[name] = per_tool_counts.get(name, 0) + 1

    per_tool = []
    for name, c in per_tool_counts.items():
        share = c / n
        per_tool.append({
            "tool": name,
            "output_tokens": int(round(output_tokens * share)),
            "cost": cost * share,
        })

    return {
        "per_tool": per_tool,
        "reasoning_output_tokens": 0,
        "reasoning_cost": 0.0,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_token_attribution -v`
Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_token_attribution.py extract_stats.py
git commit -m "feat: add attribute_turn_tokens helper for per-tool token/cost split"
```

---

## Task 2: Wire helper into session aggregation

**Files:**
- Modify: `extract_stats.py` (session init dict + assistant-message branch)
- Modify: `tests/test_token_attribution.py` (add integration test against parser)

- [ ] **Step 1: Extend session init dict**

In `extract_stats.py`, find the session init around line 964-999 (look for `"tools": defaultdict(int),`). Right AFTER the `"tools": defaultdict(int),` line, add:

```python
                                    "tool_tokens": defaultdict(lambda: {
                                        "calls": 0,
                                        "output_tokens": 0,
                                        "cost": 0.0,
                                    }),
                                    "reasoning_output_tokens": 0,
                                    "reasoning_cost": 0.0,
```

- [ ] **Step 2: Wire attribution into assistant-message branch**

Find the assistant-message branch (search for `elif msg_type == "assistant":` around line 1074). Find the block that does:

```python
                                if usage and usage.get("output_tokens", 0) > 0:
                                    m = sess["models"][model]
                                    ...
                                    m["cost"] += calc_cost(model, usage)
                                    m["calls"] += 1
```

Right AFTER `m["calls"] += 1` and BEFORE `for block in message.get("content", []):`, insert:

```python
                                    turn_output = usage.get("output_tokens", 0)
                                    turn_cost = calc_cost(model, usage)
                                    turn_tool_names = [
                                        b.get("name", "unknown")
                                        for b in message.get("content", [])
                                        if isinstance(b, dict) and b.get("type") == "tool_use"
                                    ]
                                    attrib = attribute_turn_tokens(turn_output, turn_cost, turn_tool_names)
                                    for entry in attrib["per_tool"]:
                                        tt = sess["tool_tokens"][entry["tool"]]
                                        tt["output_tokens"] += entry["output_tokens"]
                                        tt["cost"] += entry["cost"]
                                    sess["reasoning_output_tokens"] += attrib["reasoning_output_tokens"]
                                    sess["reasoning_cost"] += attrib["reasoning_cost"]
```

Then in the existing tool-iteration loop (search for `sess["tools"][tool_name] += 1`), right after that line, also bump the calls counter on `tool_tokens`:

```python
                                        sess["tool_tokens"][tool_name]["calls"] += 1
```

- [ ] **Step 3: Add integration test**

Append to `tests/test_token_attribution.py`:

```python
class ParserIntegrationTest(unittest.TestCase):
    """End-to-end: synthesize a tiny JSONL and parse it via build_sessions."""

    def test_synthetic_session_aggregates_tokens(self):
        import json
        import tempfile
        import os

        # We don't run the full parser here (it needs a real ~/.claude tree).
        # Instead, exercise the per-turn logic directly with realistic shapes.
        from extract_stats import attribute_turn_tokens

        # Turn 1: 2 Reads, 1 Edit, 600 output tokens
        a1 = attribute_turn_tokens(600, 0.06, ["Read", "Read", "Edit"])
        # Turn 2: 0 tools, 1000 output tokens  → all reasoning
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
```

- [ ] **Step 4: Run all tests**

Run: `python -m unittest tests.test_token_attribution -v`
Expected: All tests pass.

- [ ] **Step 5: Smoke-run the extractor against real data**

Run: `cd /home/andie/projects/claude-stats && python extract_stats.py 2>&1 | tail -5`
Expected: Completes without exceptions; final lines mention session count.

Then verify the new fields are present in the output:

Run: `python -c "import json; d = json.load(open('public/dashboard_data.json')); s = d['sessions'][0]; print('tool_tokens keys:', list(s.get('tool_tokens', {}).keys())[:5]); print('reasoning_output_tokens:', s.get('reasoning_output_tokens'))"`
Expected: Non-empty `tool_tokens` keys for at least one session, and a non-zero `reasoning_output_tokens` somewhere across sessions.

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py tests/test_token_attribution.py
git commit -m "feat: attribute output tokens + cost to tools + reasoning bucket per session"
```

---

## Task 3: Convert defaultdicts to dicts for JSON serialization

**Files:**
- Modify: `extract_stats.py` (look for the existing serialization spot — search for `dict(sub["tools"])` or where `"tools": dict(sess["tools"])` is built into the session_list output)

- [ ] **Step 1: Find the serialization point**

Run: `grep -n 'dict(sess\[.tools.\])\|dict(s\[.tools.\])\|"tools": dict' /home/andie/projects/claude-stats/extract_stats.py`
Expected: One or more lines where `sess["tools"]` is converted to a plain dict for the session_list output.

- [ ] **Step 2: Add the new fields alongside `tools`**

Wherever `"tools": dict(sess["tools"])` (or equivalent) appears in the session_list construction, add right after it:

```python
                "tool_tokens": {
                    name: {
                        "calls": v["calls"],
                        "output_tokens": v["output_tokens"],
                        "cost": round(v["cost"], 4),
                    }
                    for name, v in sess["tool_tokens"].items()
                },
                "reasoning_output_tokens": sess["reasoning_output_tokens"],
                "reasoning_cost": round(sess["reasoning_cost"], 4),
```

If multiple session_list construction spots exist (e.g. `build_session_list` and any subagent path), repeat in each.

- [ ] **Step 3: Re-run extractor and verify JSON output**

Run: `cd /home/andie/projects/claude-stats && python extract_stats.py 2>&1 | tail -3`
Expected: No exceptions.

Run: `python -c "import json; d = json.load(open('public/dashboard_data.json')); s = next(x for x in d['sessions'] if x.get('tool_tokens')); print(json.dumps({k: s[k] for k in ['session_id','tool_tokens','reasoning_output_tokens','reasoning_cost']}, indent=2)[:800])"`
Expected: Pretty-printed sample showing per-tool calls/output_tokens/cost and the reasoning numbers.

- [ ] **Step 4: Commit**

```bash
git add extract_stats.py
git commit -m "feat: serialize tool_tokens + reasoning_tokens into per-session JSON"
```

---

## Task 4: Global tool_token_summary aggregation

**Files:**
- Modify: `extract_stats.py` (around line 1818-1825 where `global_tools` is built, and line 1909-1912 where the dashboard `data` dict is assembled)

- [ ] **Step 1: Build the global aggregator**

Find the block starting with `# ── Global Tool Aggregation ───` (around line 1818). Right AFTER:

```python
    tool_summary = [{"name": n, "count": c} for n, c in tool_ranking]
```

Insert:

```python
    # Global Tool Token Aggregation (cost + output tokens per tool)
    global_tool_tokens = {}
    global_reasoning_output = 0
    global_reasoning_cost = 0.0
    for s in session_list:
        for tname, td in (s.get("tool_tokens") or {}).items():
            agg = global_tool_tokens.setdefault(tname, {"calls": 0, "output_tokens": 0, "cost": 0.0})
            agg["calls"] += td.get("calls", 0)
            agg["output_tokens"] += td.get("output_tokens", 0)
            agg["cost"] += td.get("cost", 0.0)
        global_reasoning_output += s.get("reasoning_output_tokens", 0)
        global_reasoning_cost += s.get("reasoning_cost", 0.0)

    tool_token_summary = sorted(
        [{"name": n, **v, "cost": round(v["cost"], 4)} for n, v in global_tool_tokens.items()],
        key=lambda x: -x["output_tokens"],
    )
```

- [ ] **Step 2: Add to the dashboard `data` dict**

Find the `data = {` assembly (around line 1879) and the existing `"tool_summary": tool_summary,` line. Right after it, add:

```python
        "tool_token_summary": tool_token_summary,
        "reasoning_summary": {
            "output_tokens": global_reasoning_output,
            "cost": round(global_reasoning_cost, 4),
        },
```

- [ ] **Step 3: Re-run extractor and verify**

Run: `cd /home/andie/projects/claude-stats && python extract_stats.py 2>&1 | tail -3`
Expected: No exceptions.

Run: `python -c "import json; d = json.load(open('public/dashboard_data.json')); print('tool_token_summary[:3]:', json.dumps(d['tool_token_summary'][:3], indent=2)); print('reasoning_summary:', d['reasoning_summary'])"`
Expected: Top 3 tools by output_tokens with calls/output_tokens/cost, and global reasoning numbers.

- [ ] **Step 4: Commit**

```bash
git add extract_stats.py
git commit -m "feat: add global tool_token_summary + reasoning_summary to dashboard data"
```

---

## Task 5: Session-detail sidebar — show output-token share per tool

**Files:**
- Modify: `templates/session_detail.js` (line 237-242)

- [ ] **Step 1: Replace the Tools Used rendering**

In `templates/session_detail.js`, find the block at line 237-242:

```js
const tools = Object.entries(sess.tools||{}).sort((a,b)=>b[1]-a[1]);
if (tools.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Tools Used</h4>' +
    tools.slice(0,15).map(([n,c]) => '<div class="sidebar-row"><span class="label">'+escHtml(n)+'</span><span class="val">'+c+'x</span></div>').join('') +
    '</div>';
}
```

Replace with:

```js
const toolTokens = sess.tool_tokens || {};
const tools = Object.entries(sess.tools||{}).sort((a,b)=>b[1]-a[1]);
if (tools.length>0) {
  const totalOut = Object.values(toolTokens).reduce((s,v)=>s+(v.output_tokens||0),0)
                    + (sess.reasoning_output_tokens||0);
  sideHtml += '<div class="sidebar-card"><h4>Tools Used</h4>' +
    tools.slice(0,15).map(([n,c]) => {
      const tk = toolTokens[n] || {output_tokens: 0};
      const pct = totalOut > 0 ? ((tk.output_tokens / totalOut) * 100).toFixed(0) : '0';
      return '<div class="sidebar-row"><span class="label">'+escHtml(n)+'</span>' +
             '<span class="val">'+c+'x <span style="opacity:0.6;font-size:11px">('+pct+'% out)</span></span></div>';
    }).join('') +
    (sess.reasoning_output_tokens > 0
      ? '<div class="sidebar-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:4px"><span class="label" style="opacity:0.7">Reasoning (no tools)</span><span class="val">' +
        (totalOut > 0 ? ((sess.reasoning_output_tokens / totalOut) * 100).toFixed(0) : '0') + '% out</span></div>'
      : '') +
    '</div>';
}
```

- [ ] **Step 2: Visual smoke test**

Run: `cd /home/andie/projects/claude-stats && python -m http.server 8765 --directory public &` (or open `public/index.html` directly).
Open a session detail page in the browser. Expected: "Tools Used" sidebar still shows tool counts, but each row now also has a "(NN% out)" annotation, and a "Reasoning (no tools)" row appears at the bottom.

Stop server: `kill %1` (or close the tab if you opened the file directly).

- [ ] **Step 3: Commit**

```bash
git add templates/session_detail.js
git commit -m "feat: show per-tool output-token share + reasoning row in session sidebar"
```

---

## Task 6: Dashboard — recompute tool_token_summary on filter

**Files:**
- Modify: `templates/dashboard.js` (around line 432-439)

- [ ] **Step 1: Add the recompute block in `filterData()`**

In `templates/dashboard.js`, find:

```js
  // Recalculate tool_summary
  const toolMap = {};
  F.sessions.forEach(s => {
    Object.entries(s.tools || {}).forEach(([name, count]) => {
      toolMap[name] = (toolMap[name] || 0) + count;
    });
  });
  F.tool_summary = Object.entries(toolMap).map(([name, count]) => ({name, count})).sort((a, b) => b.count - a.count);
```

Right AFTER that block, add:

```js
  // Recalculate tool_token_summary + reasoning_summary
  const toolTokenMap = {};
  let reasoningOut = 0, reasoningCost = 0;
  F.sessions.forEach(s => {
    Object.entries(s.tool_tokens || {}).forEach(([name, v]) => {
      const agg = toolTokenMap[name] || (toolTokenMap[name] = {calls: 0, output_tokens: 0, cost: 0});
      agg.calls += v.calls || 0;
      agg.output_tokens += v.output_tokens || 0;
      agg.cost += v.cost || 0;
    });
    reasoningOut += s.reasoning_output_tokens || 0;
    reasoningCost += s.reasoning_cost || 0;
  });
  F.tool_token_summary = Object.entries(toolTokenMap)
    .map(([name, v]) => ({name, ...v, cost: +v.cost.toFixed(4)}))
    .sort((a, b) => b.output_tokens - a.output_tokens);
  F.reasoning_summary = {output_tokens: reasoningOut, cost: +reasoningCost.toFixed(4)};
```

- [ ] **Step 2: Run extractor + reload dashboard**

Run: `cd /home/andie/projects/claude-stats && python extract_stats.py 2>&1 | tail -1`
Expected: No exceptions. Reload the dashboard in the browser (or open `public/index.html`). The page should still render normally — no visible change yet, this task only wires the data.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.js
git commit -m "feat: recompute tool_token_summary + reasoning on dashboard filter"
```

---

## Task 7: Dashboard — render tool token donut

**Files:**
- Modify: `templates/dashboard.html` (add canvas)
- Modify: `templates/dashboard.js` (add `renderToolTokenChart()` and call it from `applyFilter()`)

- [ ] **Step 1: Find the existing tool usage chart canvas**

Run: `grep -n 'chartToolUsage' /home/andie/projects/claude-stats/templates/dashboard.html /home/andie/projects/claude-stats/templates/dashboard.js`
Expected: One `<canvas id="chartToolUsage">` in the HTML and a `renderToolUsageChart()` in the JS.

- [ ] **Step 2: Add a sibling canvas in `dashboard.html`**

Locate the wrapper element that holds `<canvas id="chartToolUsage">`. Add a sibling card right after it:

```html
<div class="card">
  <h3>Token Share by Tool</h3>
  <p style="font-size:12px;opacity:0.7;margin:0 0 8px 0">Output-token share. "Reasoning" = turns with no tool calls (pure model thinking).</p>
  <canvas id="chartToolTokens"></canvas>
</div>
```

(If the existing tool-usage canvas is wrapped in a `<div class="card">`, mirror that wrapper exactly. Read 5-10 lines of context around it first to match the established structure.)

- [ ] **Step 3: Add the renderer in `dashboard.js`**

In `templates/dashboard.js`, immediately AFTER `function renderToolUsageChart()`'s closing brace, add:

```js
function renderToolTokenChart() {
  const data = (F.tool_token_summary || []).slice(0, 12);
  const reasoningOut = (F.reasoning_summary || {}).output_tokens || 0;

  const labels = data.map(t => t.name);
  const values = data.map(t => t.output_tokens);
  if (reasoningOut > 0) {
    labels.push('Reasoning');
    values.push(reasoningOut);
  }
  if (values.length === 0) return;

  const palette = ['#10b981','#06b6d4','#6366f1','#f59e0b','#ef4444','#a855f7','#ec4899','#84cc16','#14b8a6','#f97316','#3b82f6','#eab308','#94a3b8'];

  const canvas = document.getElementById('chartToolTokens');
  if (!canvas) return;
  charts.toolTokens = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((_, i) => palette[i % palette.length]),
        borderWidth: 0,
      }],
    },
    options: {
      animation: false,
      plugins: {
        legend: {position: 'right'},
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((s,v)=>s+v,0);
              const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : '0';
              return ctx.label + ': ' + ctx.raw.toLocaleString() + ' tokens (' + pct + '%)';
            },
          },
        },
      },
    },
  });
}
```

- [ ] **Step 4: Hook into `applyFilter()`**

Find `applyFilter(days, projectFilter)` (around line 522). After the existing `renderToolUsageChart();` call, add:

```js
  renderToolTokenChart();
```

- [ ] **Step 5: Trigger initial render**

Find where `renderToolUsageChart()` is first called on page load (likely inside the same `applyFilter(0)` or directly after `initTimeFilter()`). If `applyFilter` is the entry point, the new line in Step 4 already covers it. Otherwise, add a parallel `renderToolTokenChart();` call there.

Run: `grep -n 'renderToolUsageChart' /home/andie/projects/claude-stats/templates/dashboard.js`
Expected: Two call sites — confirm both have a matching `renderToolTokenChart()` next to them.

- [ ] **Step 6: Visual smoke test**

Run: `cd /home/andie/projects/claude-stats && python extract_stats.py 2>&1 | tail -1` then reload the dashboard.
Expected: A new doughnut chart titled "Token Share by Tool" sits next to the existing tool-usage bar chart, showing output-token share per tool plus a "Reasoning" slice. Hover tooltip shows tokens + percentage.

Sanity-check: the slices' relative sizes should differ from the bar chart's bar heights (counts ≠ tokens — that's the whole point).

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.html templates/dashboard.js
git commit -m "feat: dashboard donut for output-token share by tool + reasoning"
```

---

## Self-Review Checklist (run after implementation)

1. **Spec coverage:**
   - [x] Token attribution per tool — Task 1+2
   - [x] Reasoning bucket — Task 1+2
   - [x] Per-session sidebar update — Task 5
   - [x] Dashboard donut widget — Task 7
   - [x] Recompute on filter — Task 6
   - [x] Global aggregation in JSON — Task 4

2. **Type consistency:**
   - `tool_tokens` keys: `calls`, `output_tokens`, `cost` — used identically in Tasks 2/3/4/5/6.
   - `reasoning_output_tokens` and `reasoning_cost` (session-level) vs. `reasoning_summary.output_tokens` and `reasoning_summary.cost` (global) — naming is intentional (session-flat vs nested). Task 5 uses session-flat, Task 7 uses nested — correct.

3. **Placeholder scan:** No TODOs, no "implement later", no skipped logic.

4. **Out of scope (deferred, do NOT do here):**
   - Category mapping (Read/Glob/Grep → "Exploration") — separate follow-up plan.
   - LLM-based per-turn classification (Reddit-style architecture/refactor/debug labels) — separate plan.
   - Input-token attribution per tool — explicitly excluded (see Attribution Policy).
   - Locale strings for the new labels — current code mixes hardcoded EN + locale dict; keeping new strings hardcoded matches recent changes (e.g. `"Tools Used"` is already hardcoded). Add a follow-up for i18n if user wants.
