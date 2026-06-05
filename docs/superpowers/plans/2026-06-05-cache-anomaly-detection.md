# Cache Anomaly Detection (No-Gap Flushes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect mid-work cache invalidations ("no-gap flushes", the Bug-A pattern from the Claude Code cache regressions) per session, and surface them in Insights > Cache & Tokens as a card line plus a per-day stacked chart - a permanent early-warning signal for future cache bugs.

**Architecture:** The existing gap-based detector `_detect_cache_flushes()` in `extract_stats.py` is extended to classify both flush kinds in one pass (gap semantics MUST stay byte-identical). Two new per-session fields flow through the explicit export whitelist into the dashboard JSON. The frontend aggregates them in the existing `recomputeIdleGapAggregate()` (range-filter aware for free), renders a second line in the relocated idle-gap card, and adds a stacked daily bar chart in the cache subsection.

**Tech Stack:** Python 3 + pytest (`tests/`), vanilla JS + Chart.js 4 (`templates/dashboard.js`), locale JSON. Build: `python3 extract_stats.py` (~75s) writes `public/index.html`.

**Spec:** `docs/superpowers/specs/2026-06-05-cache-anomaly-detection-design.md`

**Context for workers with zero codebase knowledge:**

- `_assistant_turns` per session: list of `{"ts", "cache_creation", "cache_read", "model"}` dicts, **ts in MILLISECONDS**.
- `_detect_cache_flushes(turns, has_1h_cache)` currently returns an int (gap flushes only); call site `extract_stats.py:~2337-2343`; export whitelist entry `"cache_flush_count"` at `:~3223`.
- Locale placeholders `__L_<section>_<key>__` are replaced generically from the locale JSON (any new section works automatically). Frontend access: `D.locale.<section>.<key>`.
- Frontend: `F` = filtered data, rebuilt by `applyFilter()`; `charts` registry is bulk-destroyed on every filter change, so any `charts.<name>` chart re-renders cleanly. `recomputeIdleGapAggregate(F.sessions)` is already called inside `applyFilter()` (dashboard.js:~436).
- The idle-gap card `#idleGapAggregateCard` lives in the Insights cache subsection (dashboard.html:~286), rendered by `renderIdleGapAggregateCard()` (dashboard.js:~964), styled by `.vc .vc-idle-aggregate` rules (dashboard.css:~1416).
- The cache render function ends with `renderIdleGapAggregateCard();` at dashboard.js:~1314 - the new chart render goes directly before that call.
- Run everything from `/home/andie/projects/claude-stats`. NEVER `git add -A` (repo has unrelated untracked files); add files explicitly.

---

## File Structure

- **Create** `tests/test_cache_flush_detection.py` - unit tests for both flush kinds
- **Modify** `extract_stats.py` - detector returns dict; call site sets 3 fields; export whitelist +2
- **Modify** `templates/dashboard.js` - aggregate fields, card second line, daily chart
- **Modify** `templates/dashboard.css` - card becomes two-row capable
- **Modify** `templates/dashboard.html` - chart canvas in cache subsection
- **Modify** `locales/en.json`, `locales/de.json` - new `cacheFlush` section

---

### Task 1: Backend - detector returns both flush kinds (TDD)

**Files:**
- Create: `tests/test_cache_flush_detection.py`
- Modify: `extract_stats.py:1571-1617` (detector), `:~2342` (call site), `:~3223` (export whitelist)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cache_flush_detection.py`:

```python
"""Tests for _detect_cache_flushes: gap (TTL) and no-gap (anomaly) flushes."""
import unittest

from extract_stats import _detect_cache_flushes


def turn(ts_s, cache_creation, cache_read):
    """Build a turn dict; ts is given in seconds for readability."""
    return {"ts": ts_s * 1000, "cache_creation": cache_creation,
            "cache_read": cache_read, "model": "claude-opus-4-8"}


def steady_session():
    """Buildup + 3 steady post-buildup turns (history filled, 60s apart)."""
    return [
        turn(0, 10_000, 0),         # buildup: write-only
        turn(10, 500, 10_000),      # buildup over (read > creation)
        turn(70, 200, 10_500),
        turn(130, 200, 10_700),
        turn(190, 200, 10_900),
    ]


class TestDetectCacheFlushes(unittest.TestCase):
    def test_short_sessions_return_zeros(self):
        result = _detect_cache_flushes([turn(0, 100, 0), turn(10, 50, 200)], False)
        self.assertEqual(result, {"gap_flushes": 0, "nogap_flushes": 0,
                                  "nogap_rewrite_tokens": 0})

    def test_steady_session_has_no_flushes(self):
        result = _detect_cache_flushes(steady_session(), False)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 0)

    def test_gap_flush_counted(self):
        # 400s pause (> 300s TTL) followed by a big rewrite
        turns = steady_session() + [turn(590, 50_000, 11_000)]
        result = _detect_cache_flushes(turns, False)
        self.assertEqual(result["gap_flushes"], 1)
        self.assertEqual(result["nogap_flushes"], 0)

    def test_nogap_flush_counted_on_read_collapse(self):
        # 60s gap (< TTL), big rewrite AND cache_read collapses -> anomaly
        turns = steady_session() + [turn(250, 50_000, 500)]
        result = _detect_cache_flushes(turns, False)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 1)
        self.assertEqual(result["nogap_rewrite_tokens"], 50_000)

    def test_big_write_without_read_collapse_not_counted(self):
        # Big incremental write but cache still read fine -> legitimate work
        turns = steady_session() + [turn(250, 50_000, 11_200)]
        result = _detect_cache_flushes(turns, False)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 0)

    def test_1h_cache_classifies_400s_pause_as_nogap(self):
        # With a 1h TTL a 400s pause cannot expire the cache -> a rewrite
        # with read collapse there is an anomaly, not a TTL victim
        turns = steady_session() + [turn(590, 50_000, 500)]
        result = _detect_cache_flushes(turns, True)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests, verify they FAIL**

```bash
cd /home/andie/projects/claude-stats
python3 -m pytest tests/test_cache_flush_detection.py -v
```

Expected: FAIL - the current function returns an `int`, so the dict comparisons/subscripts fail. If they pass, stop and investigate.

- [ ] **Step 3: Rewrite the detector**

In `extract_stats.py`, replace the whole `_detect_cache_flushes` function (lines 1571-1617) with:

```python
def _detect_cache_flushes(turns: list[dict], has_1h_cache: bool) -> dict:
    """Gap-based + no-gap cache-flush detection in one pass.

    Gap flush (TTL victim) - unchanged semantics:
      1. Cache was previously established (post-buildup phase)
      2. Gap since previous turn exceeds the active cache TTL
      3. Turn's cache_creation > 2x rolling median of post-buildup
         cache_creation values (floor: 100 tokens)

    No-gap flush (anomaly; e.g. the 2026 Claude Code mid-work
    invalidation bugs): conditions 1+3, but the gap is BELOW the TTL
    and the turn's cache_read collapses to under 50% of the previous
    turn's - the cache was rebuilt although it cannot have expired.
    nogap_rewrite_tokens sums the cache_creation of those turns.
    """
    result = {"gap_flushes": 0, "nogap_flushes": 0, "nogap_rewrite_tokens": 0}
    if len(turns) < 3:
        return result

    gap_threshold_ms = (3600 if has_1h_cache else 300) * 1000
    sorted_turns = sorted(turns, key=lambda t: t["ts"])

    buildup_over = False
    creation_history: list[int] = []

    for i, t in enumerate(sorted_turns):
        prev = sorted_turns[i - 1] if i > 0 else None

        if (not buildup_over
                and t["cache_read"] > t["cache_creation"]
                and t["cache_read"] > 0):
            buildup_over = True
            continue

        if not buildup_over:
            continue

        if t["cache_creation"] > 0:
            creation_history.append(t["cache_creation"])

        if not prev:
            continue
        if len(creation_history) < 3:
            continue
        median = statistics.median(creation_history[:-1])
        if t["cache_creation"] <= 2 * max(median, 100):
            continue

        gap_ms = t["ts"] - prev["ts"]
        if gap_ms >= gap_threshold_ms:
            result["gap_flushes"] += 1
        elif prev["cache_read"] > 0 and t["cache_read"] < 0.5 * prev["cache_read"]:
            result["nogap_flushes"] += 1
            result["nogap_rewrite_tokens"] += t["cache_creation"]

    return result
```

(Gap semantics are preserved: the original checked `gap >= threshold AND len(history) >= 3 AND creation > 2x median` - the same conjunction, only evaluated in a different order with no state changes in between.)

- [ ] **Step 4: Update the call site**

At `extract_stats.py:~2342`, replace:

```python
        sess["cache_flush_count"] = _detect_cache_flushes(turns, has_1h)
```

with:

```python
        flushes = _detect_cache_flushes(turns, has_1h)
        sess["cache_flush_count"] = flushes["gap_flushes"]
        sess["cache_nogap_flush_count"] = flushes["nogap_flushes"]
        sess["cache_nogap_rewrite_tokens"] = flushes["nogap_rewrite_tokens"]
```

- [ ] **Step 5: Extend the export whitelist**

At `extract_stats.py:~3223`, replace:

```python
            "cache_flush_count": sess.get("cache_flush_count", 0),
```

with:

```python
            "cache_flush_count": sess.get("cache_flush_count", 0),
            "cache_nogap_flush_count": sess.get("cache_nogap_flush_count", 0),
            "cache_nogap_rewrite_tokens": sess.get("cache_nogap_rewrite_tokens", 0),
```

- [ ] **Step 6: Run the new tests, then the full suite**

```bash
python3 -m pytest tests/test_cache_flush_detection.py -v
python3 -m pytest tests/ -q
```

Expected: new tests PASS; full suite stays green (154 passed + the new ones).

- [ ] **Step 7: Commit**

```bash
git add tests/test_cache_flush_detection.py extract_stats.py
git commit -m "feat(stats): detect no-gap cache flushes (mid-work invalidation anomalies)"
```

---

### Task 2: Frontend - aggregate + two-line anomaly card

**Files:**
- Modify: `templates/dashboard.js` (`recomputeIdleGapAggregate` ~line 989, `renderIdleGapAggregateCard` ~line 964)
- Modify: `templates/dashboard.css` (`.vc-idle-aggregate` rules ~line 1416)
- Modify: `locales/en.json`, `locales/de.json` (new `cacheFlush` section)

- [ ] **Step 1: Add the locale section**

In `locales/en.json`, add a top-level section (alphabetical placement near the existing `idleGap` section is fine):

```json
"cacheFlush": {
  "cardTitle": "Cache-flush anomalies (no gap)",
  "events": "events",
  "chart_title": "Cache Flushes per Day",
  "legend_gap": "TTL/idle-gap flushes",
  "legend_nogap": "No-gap anomalies"
}
```

In `locales/de.json`:

```json
"cacheFlush": {
  "cardTitle": "Cache-Flush-Anomalien (ohne Pause)",
  "events": "Events",
  "chart_title": "Cache-Flushes pro Tag",
  "legend_gap": "TTL/Idle-Gap-Flushes",
  "legend_nogap": "No-Gap-Anomalien"
}
```

Verify: `python3 -c "import json; [json.load(open(f))['cacheFlush'] for f in ('locales/en.json','locales/de.json')]; print('OK')"`

- [ ] **Step 2: Extend `recomputeIdleGapAggregate`**

In `templates/dashboard.js` (~line 989), replace the function with:

```js
function recomputeIdleGapAggregate(filteredSessions) {
  let totalOversp = 0;
  let withOversp = 0;
  let nogapFlushes = 0;
  let nogapRewrite = 0;
  for (const s of (filteredSessions || [])) {
    const igs = s.idle_gap_summary;
    if (igs && igs.estimated_overspend_tokens > 0) {
      totalOversp += igs.estimated_overspend_tokens;
      withOversp += 1;
    }
    nogapFlushes += s.cache_nogap_flush_count || 0;
    nogapRewrite += s.cache_nogap_rewrite_tokens || 0;
  }
  F.idle_gap_aggregate = {
    total_overspend_tokens: totalOversp,
    total_overspend_usd: Math.round(totalOversp * IDLE_GAP_OVERSPEND_USD_PER_M / 1_000_000 * 100) / 100,
    session_count_with_overspend: withOversp,
    nogap_flush_count: nogapFlushes,
    nogap_rewrite_tokens: nogapRewrite,
    nogap_rewrite_usd: Math.round(nogapRewrite * IDLE_GAP_OVERSPEND_USD_PER_M / 1_000_000 * 100) / 100,
  };
}
```

- [ ] **Step 3: Two-line card render**

Replace `renderIdleGapAggregateCard` (~line 964) with:

```js
function renderIdleGapAggregateCard() {
  const el = document.getElementById('idleGapAggregateCard');
  if (!el) return;
  const agg = (F && F.idle_gap_aggregate) || null;
  if (!agg || (!agg.total_overspend_tokens && !agg.nogap_flush_count)) {
    el.style.display = 'none';
    return;
  }
  const L = (D && D.locale && D.locale.idleGap) || {};
  const LF = (D && D.locale && D.locale.cacheFlush) || {};
  const T = {
    dashTitle: L.dashTitle || 'Idle-gap overhead (full range)',
    sessions:  L.sessions  || 'Sessions',
    nogapTitle: LF.cardTitle || 'Cache-flush anomalies (no gap)',
    events: LF.events || 'events',
  };
  const fmtTokensAgg = (n) => n >= 1_000_000 ? (n/1_000_000).toFixed(1) + 'M' : (n >= 1000 ? (n/1000).toFixed(0) + 'k' : String(n));
  let html = '';
  if (agg.total_overspend_tokens > 0) {
    html +=
      '<div class="vc-idle-row"><span class="vc-k">' + T.dashTitle + '</span> ' +
      '<span class="vc-v">≈ ' + fmtTokensAgg(agg.total_overspend_tokens) + ' Tokens · ≈ $' + (agg.total_overspend_usd || 0).toFixed(2) + ' · ' +
      (agg.session_count_with_overspend || 0) + ' ' + T.sessions + '</span></div>';
  }
  if (agg.nogap_flush_count > 0) {
    html +=
      '<div class="vc-idle-row"><span class="vc-k">' + T.nogapTitle + '</span> ' +
      '<span class="vc-v">' + agg.nogap_flush_count + ' ' + T.events + ' · ≈ ' + fmtTokensAgg(agg.nogap_rewrite_tokens) + ' Tokens · ≈ $' + (agg.nogap_rewrite_usd || 0).toFixed(2) + '</span></div>';
  }
  el.innerHTML = html;
  el.style.display = '';
}
```

- [ ] **Step 4: CSS - column layout with row children**

In `templates/dashboard.css`, directly AFTER the existing block that ends with `.vc .vc-idle-aggregate b { color: var(--vc-fg); }` (~line 1429), add:

```css
.vc .vc-idle-aggregate { flex-direction: column; align-items: flex-start; gap: 6px; }
.vc .vc-idle-aggregate .vc-idle-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
```

(Later rules win at equal specificity; a single-row card looks identical to before.)

- [ ] **Step 5: Syntax check + commit**

```bash
node --check templates/dashboard.js
git add templates/dashboard.js templates/dashboard.css locales/en.json locales/de.json
git commit -m "feat(insights): cache anomaly card - no-gap flush line next to idle-gap overhead"
```

---

### Task 3: Frontend - "Cache Flushes per Day" chart

**Files:**
- Modify: `templates/dashboard.html` (cache subsection, after the `chartCacheEffDaily` row ~line 303)
- Modify: `templates/dashboard.js` (cache render function, directly before the `renderIdleGapAggregateCard();` call ~line 1314)

- [ ] **Step 1: Add the canvas**

In `templates/dashboard.html`, directly after the line

```html
      <div class="chart-box"><h3>__L_costs_cache_efficiency_daily__</h3><canvas id="chartCacheEffDaily"></canvas></div>
```

and its closing `</div>` of that `chart-grid full`, insert a new row:

```html
    <div class="chart-grid full">
      <div class="chart-box"><h3>__L_cacheFlush_chart_title__</h3><canvas id="chartCacheFlushDaily"></canvas></div>
    </div>
```

- [ ] **Step 2: Render the chart**

In `templates/dashboard.js`, directly BEFORE the line `  renderIdleGapAggregateCard();` (~line 1314), insert:

```js
  // Cache flushes per day: gap = TTL victims (structural), no-gap = anomalies
  // (e.g. invalidation bugs) - loud color on the actionable series.
  const cfCanvas = document.getElementById('chartCacheFlushDaily');
  if (cfCanvas) {
    const flushByDate = {};
    F.sessions.forEach(s => {
      if (!s.date) return;
      if (!flushByDate[s.date]) flushByDate[s.date] = { gap: 0, nogap: 0 };
      flushByDate[s.date].gap += s.cache_flush_count || 0;
      flushByDate[s.date].nogap += s.cache_nogap_flush_count || 0;
    });
    const flushDates = Object.keys(flushByDate).sort();
    const LF = (D.locale && D.locale.cacheFlush) || {};
    charts.cacheFlushDaily = new Chart(cfCanvas, {
      type: 'bar',
      data: {
        labels: flushDates,
        datasets: [
          { label: LF.legend_gap || 'TTL/idle-gap flushes', data: flushDates.map(d => flushByDate[d].gap), backgroundColor: vcRgba(2, 0.45), borderRadius: 0 },
          { label: LF.legend_nogap || 'No-gap anomalies', data: flushDates.map(d => flushByDate[d].nogap), backgroundColor: vcColor(0), borderRadius: 0 },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: window.__vcFg2 || '#4d4a42' } }, tooltip: { mode: 'index', intersect: false } },
        scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, stacked: true, ticks: { ...scaleDefaults.y.ticks, precision: 0 } } }
      }
    });
  }
```

- [ ] **Step 3: Syntax check + commit**

```bash
node --check templates/dashboard.js
git add templates/dashboard.html templates/dashboard.js
git commit -m "feat(insights): cache flushes per day chart (gap vs no-gap anomalies)"
```

---

### Task 4: Build, verify, screenshot

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

```bash
python3 -m pytest tests/ -q
```

Expected: all green (154 + 6 new).

- [ ] **Step 2: Rebuild (~75s)**

```bash
python3 extract_stats.py
```

Expected: exit 0.

- [ ] **Step 3: Headless verification**

```bash
node -e "
const { chromium } = require('playwright');
const { pathToFileURL } = require('node:url');
const { resolve } = require('node:path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(pathToFileURL(resolve('public/index.html')).href, { waitUntil: 'networkidle' });
  const checks = await page.evaluate(() => {
    const card = document.getElementById('idleGapAggregateCard');
    const rows = card ? card.querySelectorAll('.vc-idle-row').length : 0;
    const agg = F.idle_gap_aggregate || {};
    const chart = charts.cacheFlushDaily;
    const nogapSum = chart ? chart.data.datasets[1].data.reduce((a, v) => a + v, 0) : -1;
    const gapSum = chart ? chart.data.datasets[0].data.reduce((a, v) => a + v, 0) : -1;
    return { rows, nogapAgg: agg.nogap_flush_count, gapSum, nogapSum, cardVisible: card && card.style.display !== 'none' };
  });
  console.log(JSON.stringify(checks));
  if (!checks.cardVisible || checks.rows !== 2) throw new Error('card does not show two rows');
  if (!(checks.nogapAgg > 0)) throw new Error('no-gap aggregate empty');
  if (checks.nogapSum !== checks.nogapAgg) throw new Error('chart no-gap sum != aggregate (' + checks.nogapSum + ' vs ' + checks.nogapAgg + ')');
  if (!(checks.gapSum > 0)) throw new Error('gap series empty');
  // range filter sanity: 7D should not exceed All
  const allNogap = checks.nogapAgg;
  await page.click('.vc-range-btn[data-days=\"7\"]');
  await page.waitForTimeout(600);
  const nogap7 = await page.evaluate(() => (F.idle_gap_aggregate || {}).nogap_flush_count);
  console.log('nogap 7D:', nogap7, '/ All:', allNogap);
  if (nogap7 > allNogap) throw new Error('7D filter exceeds All');
  if (errors.length) throw new Error('browser errors: ' + errors.join(' | '));
  console.log('OK — cache anomaly detection verified');
  await browser.close();
})();
"
```

Expected: final line `OK — cache anomaly detection verified`. Plausibility anchor from the raw-log analysis (2026-06-05): the pre-guard estimate was ≈130 no-gap events across all months (Mar 18 / Apr 39 / May 60 / Jun 12, Feb 2). The shipped detector additionally excludes compaction-adjacent rebuilds, so the aggregate should land NOTICEABLY BELOW ≈130 but ABOVE zero (zero would suggest the guard is over-suppressing; >200 would suggest it is not applied).

- [ ] **Step 4: Screenshot the cache section**

```bash
node -e "
const { chromium } = require('playwright');
const { pathToFileURL } = require('node:url');
const { resolve } = require('node:path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1400 } });
  await page.goto(pathToFileURL(resolve('public/index.html')).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => window.activateTabByName && window.activateTabByName('insights', false));
  await page.waitForTimeout(700);
  await page.screenshot({ path: '/tmp/smoke/cache-anomalies.png', fullPage: true });
  await browser.close();
  console.log('screenshot done');
})();
"
```

Inspect `/tmp/smoke/cache-anomalies.png` (Read tool): the card must show both lines, the new chart must render below the daily cache-efficiency box plot with mostly-muted bars and occasional accent-colored anomaly segments.

- [ ] **Step 5: Repo hygiene**

```bash
git status --short
```

Expected: no modified tracked files beyond what was committed.

---

## Self-Review Notes

- Spec coverage: detection + unchanged gap semantics (Task 1 Steps 3+tests), export (Task 1 Step 5), card two-liner + visibility rule (Task 2 Step 3), daily chart with color hierarchy (Task 3), locale en/de (Task 2 Step 1), range-awareness verified (Task 4 Step 3). Out-of-scope items untouched.
- Type consistency: detector returns `{"gap_flushes", "nogap_flushes", "nogap_rewrite_tokens"}` (Task 1 Steps 1+3 match); session fields `cache_nogap_flush_count`/`cache_nogap_rewrite_tokens` consistent across call site, whitelist, JS aggregate, and chart.
- ts unit: tests build ms via `ts_s * 1000`, matching `_assistant_turns`.
