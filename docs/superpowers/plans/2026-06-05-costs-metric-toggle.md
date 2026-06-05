# Costs Tab Metric Toggle (USD | Local Currency | Tokens) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-state toggle (USD | local currency | Tokens) to the "Token & API Value" tab that switches the daily-by-model chart and the cumulative chart between API value in USD, API value in the user's billing currency, and consumed tokens (input + output, no cache).

**Architecture:** Frontend-only. `applyFilter()` in `templates/dashboard.js` already rebuilds `F.daily_costs` per model per day from `s.model_breakdown`; we add a parallel `F.daily_tokens` + `F.cumulative_tokens`. Currency conversion happens at render time via a per-date FX lookup that mirrors Plan & Billing's per-cycle rate (`plan_cost_local / plan_cost_usd`). The two affected charts are extracted from `renderCosts()` into `renderCostCharts()` so the toggle can rebuild them alone. Toggle UI follows the existing `mkBtn` pattern from `renderPlan()` (`templates/dashboard.js:1594-1611`).

**Tech Stack:** Vanilla JS + Chart.js 4 (`templates/dashboard.js`), locale JSON (`locales/en.json`, `locales/de.json`), `python3 extract_stats.py` builds `public/index.html`. No JS unit-test harness exists in this repo; frontend changes are verified with `node --check` plus a headless-Chromium assertion script (Playwright-cached Chromium, same pattern as `tools/smoke_shot.mjs`). That verification script is written in Task 1 (before any production code) and must FAIL until the feature is complete.

**Spec:** `docs/superpowers/specs/2026-06-05-costs-metric-toggle-design.md`

**Important context for workers with zero codebase knowledge:**

- `D` is the embedded data object (`const D = "__DATA_PLACEHOLDER__"` gets replaced at build time). `F` holds the *filtered* mirror of that data, rebuilt by `applyFilter()`.
- `D.plan.periods[]` entries use `start`/`end` date strings; `D.plan.current_billing` uses `period_start`/`period_end`. Both carry `plan_cost_local` + `plan_cost_usd`. The existing `calcFilteredPlanCost()` (`templates/dashboard.js:349`) shows the `p.start || p.period_start` dual-field pattern.
- `charts` is a module-level object holding Chart.js instances; `applyFilter()` destroys all of them and re-runs every render function, so a module-level mode variable survives filter changes automatically.
- `updateVcTabMetas()` (`templates/dashboard.js:2818`) currently overwrites `#vcCostMeta` on every filter change - Task 6 removes that line, otherwise it would clobber the toggle.
- The dashboard JS is a classic (non-module) script, so top-level `let`/`const` like `F` and `charts` ARE reachable from Playwright `page.evaluate()`.
- `python3 extract_stats.py` regenerates `public/index.html` from the real local session logs (the cron job runs the same command). Run it from the repo root.
- Range buttons set their `.active` class *before* calling `applyFilter()`, so reading `.vc-range-btn.active` inside render functions is safe.

---

## File Structure

- **Modify** `locales/en.json`, `locales/de.json` - four new keys under `costs`
- **Modify** `templates/dashboard.html:133,136` - ids on the two chart `<h3>` titles
- **Modify** `templates/dashboard.js`:
  - line ~7: add `costMetricMode` state
  - lines ~413-429: token aggregation in `applyFilter()`
  - line ~480: cumulative tokens
  - after `calcFilteredPlanCost()` (~line 375): FX helpers
  - `renderCosts()` (~line 957): extract `renderCostCharts()`, add `renderCostMetricToggle()`
  - `updateVcTabMetas()` (~line 2824): release ownership of `#vcCostMeta`
- **Create** `/tmp/verify_toggle.mjs` - headless verification script (NOT committed; `/tmp` keeps it out of the repo on purpose - deploy/infra scripts stay local per project convention)

---

### Task 1: Headless verification script (the "failing test")

**Files:**
- Create: `/tmp/verify_toggle.mjs`

- [ ] **Step 1: Write the verification script**

```js
// /tmp/verify_toggle.mjs — asserts the costs metric toggle works end-to-end.
// Run from repo root: node /tmp/verify_toggle.mjs
import { chromium } from 'playwright';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const url = pathToFileURL(resolve('public/index.html')).href;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
await page.goto(url, { waitUntil: 'networkidle' });

// 1. Toggle buttons exist (USD first, Tokens last; local currency optional in between)
const btnLabels = await page.$$eval('#vcCostMeta button', bs => bs.map(b => b.textContent));
console.log('toggle buttons:', btnLabels);
if (btnLabels[0] !== 'USD') throw new Error('first toggle button is not USD: ' + btnLabels);
if (!btnLabels.includes('Tokens')) throw new Error('Tokens button missing: ' + btnLabels);

// 2. Token data is aggregated
const tokTotal = await page.evaluate(() => F.daily_tokens.reduce((a, r) => a + (r.total || 0), 0));
console.log('aggregated token total:', tokTotal);
if (!(tokTotal > 0)) throw new Error('F.daily_tokens empty or zero');

// 3. Clicking Tokens switches title, y-axis, and data source
const titleBefore = await page.textContent('#costsDailyTitle');
await page.click('#vcCostMeta button:has-text("Tokens")');
await page.waitForTimeout(300);
const titleAfter = await page.textContent('#costsDailyTitle');
console.log('daily title:', JSON.stringify(titleBefore), '->', JSON.stringify(titleAfter));
if (titleAfter === titleBefore) throw new Error('daily <h3> did not switch in tokens mode');
const yTitle = await page.evaluate(() => charts.dailyCost.options.scales.y.title.text);
if (yTitle !== 'Tokens') throw new Error('y-axis title not "Tokens": ' + yTitle);
const cumLast = await page.evaluate(() => {
  const ds = charts.cumCost.data.datasets[0].data;
  return ds[ds.length - 1];
});
console.log('cumulative last point (tokens mode):', cumLast);
if (!(cumLast > 1000)) throw new Error('cumulative chart not showing token-scale values: ' + cumLast);

// 4. Local-currency mode (only if a currency button is present)
if (btnLabels.length === 3) {
  await page.click('#vcCostMeta button >> nth=1');
  await page.waitForTimeout(300);
  const y2 = await page.evaluate(() => charts.dailyCost.options.scales.y.title.text);
  console.log('local-mode y-axis title:', y2);
  if (y2 === 'Tokens' || y2 === 'USD') throw new Error('local mode y-axis wrong: ' + y2);
  const sums = await page.evaluate(() => {
    const usd = F.daily_costs.reduce((a, r) => a + (r.total || 0), 0);
    const chart = charts.dailyCost.data.datasets
      .flatMap(d => d.data).reduce((a, v) => a + (v || 0), 0);
    return { usd, chart };
  });
  console.log('usd total:', sums.usd, '/ chart total in local mode:', sums.chart);
  if (Math.abs(sums.chart - sums.usd) < 1e-9) throw new Error('local mode did not convert values');
} else {
  console.log('no currency button (no FX configured) — skipping local-mode checks');
}

// 5. Switching back to USD restores the original title
await page.click('#vcCostMeta button:has-text("USD")');
await page.waitForTimeout(300);
const titleRestored = await page.textContent('#costsDailyTitle');
if (titleRestored !== titleBefore) throw new Error('USD mode did not restore title');

if (errors.length) throw new Error('browser errors:\n' + errors.join('\n'));
console.log('OK — toggle verified');
await browser.close();
```

- [ ] **Step 2: Build the dashboard and run the script to verify it FAILS**

```bash
cd /home/andie/projects/claude-stats
python3 extract_stats.py
node /tmp/verify_toggle.mjs
```

Expected: FAIL - `#vcCostMeta button` matches nothing (the element currently contains only static text), so step 1 of the script throws. If it passes, something is wrong - stop and investigate.

(No commit - `/tmp` file.)

---

### Task 2: Locale keys

**Files:**
- Modify: `locales/en.json` (costs section, after `"cumulative_label"`)
- Modify: `locales/de.json` (costs section, after `"cumulative_label"`)

- [ ] **Step 1: Add the English keys**

In `locales/en.json`, inside the `"costs"` object, directly after the `"cumulative_label"` line:

```json
 "cumulative_label": "Cumulative (API $)",
 "daily_tokens": "Tokens per Day by Model",
 "cumulative_tokens": "Cumulative Tokens",
 "cumulative_tokens_label": "Cumulative (tokens)",
 "toggle_tokens": "Tokens",
```

- [ ] **Step 2: Add the German keys**

In `locales/de.json`, inside the `"costs"` object, directly after the `"cumulative_label"` line:

```json
 "cumulative_label": "Kumulativ (API-$)",
 "daily_tokens": "Tokens pro Tag nach Modell",
 "cumulative_tokens": "Kumulierte Tokens",
 "cumulative_tokens_label": "Kumuliert (Tokens)",
 "toggle_tokens": "Tokens",
```

- [ ] **Step 3: Verify both files parse and contain the keys**

```bash
cd /home/andie/projects/claude-stats
python3 -c "
import json
for f in ('locales/en.json', 'locales/de.json'):
    c = json.load(open(f))['costs']
    for k in ('daily_tokens', 'cumulative_tokens', 'cumulative_tokens_label', 'toggle_tokens'):
        assert k in c, f'{f} missing {k}'
print('locales OK')
"
```

Expected: `locales OK`

- [ ] **Step 4: Commit**

```bash
git add locales/en.json locales/de.json
git commit -m "feat(costs): locale keys for metric toggle token mode"
```

---

### Task 3: HTML ids on the two chart titles

**Files:**
- Modify: `templates/dashboard.html:133,136`

- [ ] **Step 1: Add ids to the `<h3>` elements**

Line 133, change:

```html
<div class="chart-box"><h3>__L_costs_daily_cost__</h3><canvas id="chartDailyCost"></canvas></div>
```

to:

```html
<div class="chart-box"><h3 id="costsDailyTitle">__L_costs_daily_cost__</h3><canvas id="chartDailyCost"></canvas></div>
```

Line 136, change:

```html
<div class="chart-box"><h3>__L_costs_cumulative__</h3><canvas id="chartCumCost"></canvas></div>
```

to:

```html
<div class="chart-box"><h3 id="costsCumTitle">__L_costs_cumulative__</h3><canvas id="chartCumCost"></canvas></div>
```

- [ ] **Step 2: Verify**

```bash
grep -c 'costsDailyTitle\|costsCumTitle' templates/dashboard.html
```

Expected: `2`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat(costs): ids on daily/cumulative chart titles for mode switching"
```

---

### Task 4: Token aggregation in `applyFilter()`

**Files:**
- Modify: `templates/dashboard.js:413-429` (daily maps) and `:478-481` (cumulative)

- [ ] **Step 1: Add `dailyTokenMap` to the daily aggregation loop**

In `applyFilter()`, replace this block (currently lines 413-429):

```js
  // Rebuild daily aggregates from filtered sessions
  const dailyCostMap = {};
  const dailyMsgMap = {};
  F.sessions.forEach(s => {
    if (!s.date) return;
    if (!dailyMsgMap[s.date]) dailyMsgMap[s.date] = {date: s.date, messages: 0, sessions: 0};
    dailyMsgMap[s.date].messages += s.messages || 0;
    dailyMsgMap[s.date].sessions += 1;
    if (!dailyCostMap[s.date]) dailyCostMap[s.date] = {date: s.date, total: 0};
    dailyCostMap[s.date].total += s.cost || 0;
    Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
      dailyCostMap[s.date][model] = (dailyCostMap[s.date][model] || 0) + (d.cost || 0);
    });
  });
  const allDates = [...new Set([...Object.keys(dailyCostMap), ...Object.keys(dailyMsgMap)])].sort();
  F.daily_costs = allDates.map(d => dailyCostMap[d] || {date: d, total: 0});
  F.daily_messages = allDates.map(d => dailyMsgMap[d] || {date: d, messages: 0, sessions: 0});
```

with:

```js
  // Rebuild daily aggregates from filtered sessions
  const dailyCostMap = {};
  const dailyTokenMap = {};   // input + output tokens (no cache), per model per day
  const dailyMsgMap = {};
  F.sessions.forEach(s => {
    if (!s.date) return;
    if (!dailyMsgMap[s.date]) dailyMsgMap[s.date] = {date: s.date, messages: 0, sessions: 0};
    dailyMsgMap[s.date].messages += s.messages || 0;
    dailyMsgMap[s.date].sessions += 1;
    if (!dailyCostMap[s.date]) dailyCostMap[s.date] = {date: s.date, total: 0};
    if (!dailyTokenMap[s.date]) dailyTokenMap[s.date] = {date: s.date, total: 0};
    dailyCostMap[s.date].total += s.cost || 0;
    Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
      dailyCostMap[s.date][model] = (dailyCostMap[s.date][model] || 0) + (d.cost || 0);
      const tok = (d.input_tokens || 0) + (d.output_tokens || 0);
      dailyTokenMap[s.date][model] = (dailyTokenMap[s.date][model] || 0) + tok;
      dailyTokenMap[s.date].total += tok;
    });
  });
  const allDates = [...new Set([...Object.keys(dailyCostMap), ...Object.keys(dailyMsgMap)])].sort();
  F.daily_costs = allDates.map(d => dailyCostMap[d] || {date: d, total: 0});
  F.daily_tokens = allDates.map(d => dailyTokenMap[d] || {date: d, total: 0});
  F.daily_messages = allDates.map(d => dailyMsgMap[d] || {date: d, messages: 0, sessions: 0});
```

- [ ] **Step 2: Add cumulative tokens**

Still in `applyFilter()`, around line 478-481, replace:

```js
  // Recalculate cumulative costs from filtered daily costs
  let cum = 0;
  F.cumulative_costs = F.daily_costs.map(r => { cum += r.total; return {date: r.date, cost: cum}; });
```

with:

```js
  // Recalculate cumulative costs from filtered daily costs
  let cum = 0;
  F.cumulative_costs = F.daily_costs.map(r => { cum += r.total; return {date: r.date, cost: cum}; });
  let cumTok = 0;
  F.cumulative_tokens = F.daily_tokens.map(r => { cumTok += r.total; return {date: r.date, tokens: cumTok}; });
```

- [ ] **Step 3: Syntax check**

```bash
node --check templates/dashboard.js
```

Expected: no output (exit 0).

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.js
git commit -m "feat(costs): aggregate daily + cumulative input/output tokens per model"
```

---

### Task 5: Mode state and FX helpers

**Files:**
- Modify: `templates/dashboard.js:7` (state) and after `calcFilteredPlanCost()` (~line 375)

- [ ] **Step 1: Add the mode variable**

Directly after line 7 (`let planCurrencyMode = ...`):

```js
let costMetricMode = 'usd'; // 'usd' | 'local' | 'tokens' — Costs tab metric toggle
```

- [ ] **Step 2: Add FX helpers**

After the closing brace of `calcFilteredPlanCost()` (the function starting at ~line 349 - find its end with the matching `}` before the next `function`), insert:

```js
// ── Costs tab metric toggle: FX helpers ────────────────────────────────
// Mirrors Plan & Billing per-cycle FX (extract_stats.py: plan_cost_local / plan_cost_usd).
function periodFx(p) {
  return (p && p.plan_cost_local && p.plan_cost_usd) ? p.plan_cost_local / p.plan_cost_usd : null;
}
function currentFx() {
  if (!D.plan) return null;
  let fx = periodFx(D.plan.current_billing);
  if (fx) return fx;
  const ps = D.plan.periods || [];
  for (let i = ps.length - 1; i >= 0; i--) {
    fx = periodFx(ps[i]);
    if (fx) return fx;
  }
  return null;
}
function fxForDate(dateStr) {
  if (!D.plan) return null;
  // periods use start/end, current_billing uses period_start/period_end
  const all = (D.plan.periods || []).concat(D.plan.current_billing ? [D.plan.current_billing] : []);
  for (const p of all) {
    const start = p.start || p.period_start;
    const end = p.end || p.period_end;
    if (start && end && start <= dateStr && dateStr <= end) {
      const fx = periodFx(p);
      if (fx) return fx;
      break; // matching period without a rate -> fallback chain
    }
  }
  return currentFx();
}
```

- [ ] **Step 3: Syntax check**

```bash
node --check templates/dashboard.js
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.js
git commit -m "feat(costs): metric mode state + per-date FX lookup (plan-cycle rates)"
```

---

### Task 6: `renderCostCharts()` - mode-aware chart rendering

**Files:**
- Modify: `templates/dashboard.js:957-989` (`renderCosts()` head)

- [ ] **Step 1: Extract and rewrite the two charts**

In `renderCosts()` (line 957), the current code begins:

```js
function renderCosts() {
  const dates = F.daily_costs.map(d => d.date);
  const models = D.models;

  charts.dailyCost = new Chart(document.getElementById('chartDailyCost'), {
    type: 'bar',
    data: {
      labels: dates,
      datasets: models.map(m => ({
        label: m,
        data: F.daily_costs.map(d => d[m] || 0),
        backgroundColor: vcModelColor(m),
        borderRadius: 0,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: window.__vcFg2 || '#4d4a42' } }, tooltip: { mode: 'index', intersect: false } },
      scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, stacked: true, title: { display: true, text: 'USD', color: window.__vcFg2 || '#5b6473' } } }
    }
  });

  charts.cumCost = new Chart(document.getElementById('chartCumCost'), {
    type: 'line',
    data: {
      labels: F.cumulative_costs.map(d => d.date),
      datasets: [{ label: D.locale.costs.cumulative_label, data: F.cumulative_costs.map(d => d.cost),
        borderColor: vcColor(1), backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: 'USD', color: window.__vcFg2 || '#5b6473' } } } }
  });

  const cbt = F.cost_by_token_type;
```

Replace everything from `function renderCosts() {` down to (but NOT including) `  const cbt = F.cost_by_token_type;` with:

```js
// Format a value according to the active costs metric mode.
function costModeFmt(v) {
  if (costMetricMode === 'tokens') return fmtTokens(v);
  if (costMetricMode === 'local') {
    return v.toLocaleString(D.locale.locale_code, {minimumFractionDigits: 2, maximumFractionDigits: 2})
      + ' ' + ((D.plan && D.plan.currency_symbol) || '');
  }
  return fmtUSD(v);
}

// The two metric-switchable charts (daily by model + cumulative).
// Separate from renderCosts() so the toggle can rebuild just these two.
function renderCostCharts() {
  const mode = costMetricMode;
  const L = D.locale.costs;
  const models = D.models;
  const dates = F.daily_costs.map(d => d.date);
  const dailySrc = mode === 'tokens' ? F.daily_tokens : F.daily_costs;
  const cumSrc = mode === 'tokens' ? F.cumulative_tokens : F.cumulative_costs;
  const yTitle = mode === 'tokens' ? 'Tokens'
    : (mode === 'local' ? ((D.plan && D.plan.currency_symbol) || 'USD') : 'USD');
  const conv = (v, date) => mode === 'local' ? v * (fxForDate(date) || 0) : v;
  const yTicks = mode === 'tokens'
    ? { ...scaleDefaults.y.ticks, callback: v => fmtTokens(v) }
    : scaleDefaults.y.ticks;

  const dailyTitle = document.getElementById('costsDailyTitle');
  if (dailyTitle) dailyTitle.textContent = mode === 'tokens' ? L.daily_tokens : L.daily_cost;
  const cumTitle = document.getElementById('costsCumTitle');
  if (cumTitle) cumTitle.textContent = mode === 'tokens' ? L.cumulative_tokens : L.cumulative;

  charts.dailyCost = new Chart(document.getElementById('chartDailyCost'), {
    type: 'bar',
    data: {
      labels: dates,
      datasets: models.map(m => ({
        label: m,
        data: dailySrc.map(d => conv(d[m] || 0, d.date)),
        backgroundColor: vcModelColor(m),
        borderRadius: 0,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: window.__vcFg2 || '#4d4a42' } },
        tooltip: { mode: 'index', intersect: false,
          callbacks: { label: ctx => ctx.dataset.label + ': ' + costModeFmt(ctx.parsed.y) } }
      },
      scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, ticks: yTicks, stacked: true, title: { display: true, text: yTitle, color: window.__vcFg2 || '#5b6473' } } }
    }
  });

  charts.cumCost = new Chart(document.getElementById('chartCumCost'), {
    type: 'line',
    data: {
      labels: cumSrc.map(d => d.date),
      datasets: [{ label: mode === 'tokens' ? L.cumulative_tokens_label : L.cumulative_label,
        data: cumSrc.map(d => conv(mode === 'tokens' ? d.tokens : d.cost, d.date)),
        borderColor: vcColor(1), backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => costModeFmt(ctx.parsed.y) } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, ticks: yTicks, title: { display: true, text: yTitle, color: window.__vcFg2 || '#5b6473' } } } }
  });
}

function renderCosts() {
  renderCostCharts();

  const cbt = F.cost_by_token_type;
```

Note: the toggle UI itself comes in Task 7 - this task's commit leaves the dashboard fully working (charts render in default `usd` mode; the cron job deploys from this working dir every 10 minutes, so every commit must be runnable).

- [ ] **Step 2: Syntax check**

```bash
node --check templates/dashboard.js
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.js
git commit -m "refactor(costs): extract mode-aware renderCostCharts() from renderCosts()"
```

---

### Task 7: Toggle UI + meta ownership

**Files:**
- Modify: `templates/dashboard.js` (new function before `renderCostCharts()`; `updateVcTabMetas()` at ~line 2824)

- [ ] **Step 1: Add `renderCostMetricToggle()`**

Directly above the `// Format a value according to the active costs metric mode.` comment from Task 6, insert:

```js
// ── Costs tab metric toggle (USD | local currency | Tokens) ───────────
// Owns #vcCostMeta (updateVcTabMetas leaves it alone). Pattern follows the
// Plan & Billing currency toggle in renderPlan().
function renderCostMetricToggle() {
  const meta = document.getElementById('vcCostMeta');
  if (!meta) return;
  meta.innerHTML = '';
  const activeRange = document.querySelector('.vc-range-btn.active');
  const range = activeRange ? (activeRange.dataset.days === '0' ? 'all' : activeRange.dataset.days + 'd') : 'all';
  meta.appendChild(document.createTextNode(range + ' · daily · '));
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:inline-flex;gap:4px;align-items:center;';
  const mkBtn = (mode, label) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    const on = costMetricMode === mode;
    b.style.cssText = 'padding:2px 8px;border:1px solid var(--border);background:' + (on ? 'var(--accent)' : 'transparent') + ';color:' + (on ? '#fff' : 'inherit') + ';cursor:pointer;font:inherit;border-radius:0;';
    b.onclick = () => {
      if (costMetricMode === mode) return;
      costMetricMode = mode;
      if (charts.dailyCost) { charts.dailyCost.destroy(); delete charts.dailyCost; }
      if (charts.cumCost) { charts.cumCost.destroy(); delete charts.cumCost; }
      renderCostMetricToggle();
      renderCostCharts();
    };
    return b;
  };
  wrap.appendChild(mkBtn('usd', 'USD'));
  if (D.plan && D.plan.currency_symbol && currentFx()) {
    wrap.appendChild(mkBtn('local', D.plan.currency_symbol));
  }
  wrap.appendChild(mkBtn('tokens', (D.locale.costs && D.locale.costs.toggle_tokens) || 'Tokens'));
  meta.appendChild(wrap);
}
```

- [ ] **Step 2: Wire the toggle into `renderCosts()`**

In `renderCosts()` (created in Task 6), add the toggle call as the first line of the body:

```js
function renderCosts() {
  renderCostMetricToggle();
  renderCostCharts();

  const cbt = F.cost_by_token_type;
```

- [ ] **Step 3: Release `#vcCostMeta` from `updateVcTabMetas()`**

At ~line 2824, replace:

```js
  _vcMeta('vcCostMeta', range + ' · daily · USD');
```

with:

```js
  // vcCostMeta is owned by renderCostMetricToggle (metric toggle)
```

(The range prefix text is preserved inside `renderCostMetricToggle()`, which re-runs on every `applyFilter()` via `renderCosts()`.)

- [ ] **Step 4: Syntax check**

```bash
node --check templates/dashboard.js
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.js
git commit -m "feat(costs): USD | local currency | Tokens toggle in tab header"
```

---

### Task 8: Build, verify, screenshots

**Files:**
- No source changes. Builds `public/index.html`, runs `/tmp/verify_toggle.mjs` and `tools/smoke_shot.mjs`.

- [ ] **Step 1: Rebuild the dashboard**

```bash
cd /home/andie/projects/claude-stats
python3 extract_stats.py
```

Expected: exits 0 (writes `public/index.html`).

- [ ] **Step 2: Run the verification script from Task 1**

```bash
node /tmp/verify_toggle.mjs
```

Expected output ends with `OK — toggle verified`. The button list should be `[ 'USD', '€', 'Tokens' ]` (the user has a EUR plan configured; if it shows only 2 buttons, `currentFx()` found no rate - investigate before continuing, do not shrug it off).

- [ ] **Step 3: Run the existing smoke screenshots**

```bash
node tools/smoke_shot.mjs
```

Expected: `screenshots in /tmp/smoke`. Check `/tmp/smoke/desk-light-costs.png` and `desk-dark-costs.png`: the toggle must be visible in the tab header and the charts intact.

- [ ] **Step 4: Regression check - other tabs unaffected**

The verify script already fails on any console error. Additionally confirm in the screenshots that `plan`, `activity`, `sessions`, `insights` tabs render (smoke_shot captures all of them).

- [ ] **Step 5: Final commit if anything is dirty**

```bash
git status --short
```

Expected: no modified tracked files (public/ is gitignored or untracked output). If `git status` shows source changes you have not committed, commit them with an appropriate message before finishing.

---

## Self-Review Notes

- Spec coverage: token aggregation (Task 4), FX per cycle (Task 5), three-way toggle + currency-button guard (Task 7), mode-aware rendering incl. titles/ticks/tooltips (Task 6), locale keys (Task 2), h3 ids (Task 3), edge cases (guard in Task 7 Step 1, fallback chain in Task 5 Step 2), testing (Tasks 1 + 8). Out-of-scope items untouched.
- Type consistency: `F.daily_tokens` rows `{date, total, [model]}` (Task 4) match `dailySrc.map(d => conv(d[m] || 0, d.date))` (Task 6). `F.cumulative_tokens` rows `{date, tokens}` match `d.tokens` access (Task 6). `renderCostMetricToggle` defined Task 7, referenced Task 6 - ordering documented in Task 6 note.
