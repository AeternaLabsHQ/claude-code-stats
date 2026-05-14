# Session Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an expandable "Weitere Filter" module above the session table on the dashboard Sessions tab and on the project detail page, with 9 numeric range filters, two quick-presets ("Nur echte Sessions", "Nur teure Sessions"), and a live chip row.

**Architecture:** New standalone JS/CSS component in `templates/components/` (analogous to `session_table.js`), mounted on both dashboard and project detail. The component owns its UI, state and persistence; the consumers query the active filters via `getActiveFiltersList()` and feed them into their existing `getFilteredSessions()` pipeline.

**Tech Stack:** Vanilla JS IIFE exposing `window.mountSessionFilters`. CSS uses the project's terminal-aesthetic vars (`--vc-bg`, `--vc-border`, `--vc-text`, `--vc-accent`). Persistence via `localStorage`, keyed by context. Build is the existing `extract_stats.py` template concatenation (no new build tooling).

**Spec:** `docs/superpowers/specs/2026-05-14-session-filters-design.md`

**Testing convention:** This project has no JS unit test framework. Every task ends with (a) `node --check` syntax preflight and (b) manual headless-Chromium smoke per `reference_local_ui_smoketest.md`. Per task: write code, syntax-check, regenerate the dashboard once via `python3 extract_stats.py`, eyeball the rendered HTML, then commit.

---

## File Structure

**New files:**

- `templates/components/session_filters.js` — single IIFE, exposes `window.mountSessionFilters(host, options)`. ~ 400 LoC.
- `templates/components/session_filters.css` — module styling. ~ 150 LoC.

**Modified files:**

- `extract_stats.py` — `_get_html_template()` and `_get_project_html_template()` each gain two extra `read_text` calls to inline the new component.
- `templates/dashboard.html` — adds presets row, panel host div and chip-row host div inside `.session-filters`.
- `templates/dashboard.js` — mounts the filter module, extends `getFilteredSessions()`, and re-pokes the module whenever the upstream pool (`F.sessions`) changes.
- `templates/project_detail.html` — adds host divs above the existing `#sessionList`.
- `templates/project_detail.js` — mounts the filter module with `context: 'projectDetail'` and intercepts the sessions list passed to `mountSessionTable`.

No changes to `extract_stats.py` analytics, no `tests/` additions.

---

## Pre-flight

- [ ] **Step 0.1: Create a working branch off `main`**

```bash
git checkout -b feature/session-filters
git status --short
```

Expected: clean tree (apart from already-existing untracked files unrelated to this work).

- [ ] **Step 0.2: Verify Python build still passes baseline**

```bash
python3 extract_stats.py >/dev/null 2>&1 && echo OK
```

Expected: `OK`. If it fails, stop and surface the existing breakage.

---

## Task 1: Component skeleton + build pipeline integration

**Goal:** Ship an empty `mountSessionFilters` function that is included in both built HTML templates but does nothing yet. This unblocks every later task.

**Files:**
- Create: `templates/components/session_filters.js`
- Create: `templates/components/session_filters.css`
- Modify: `extract_stats.py:2280-2294` (dashboard build), `extract_stats.py:2622-2634` (project detail build)

- [ ] **Step 1.1: Write the skeleton JS file**

Create `templates/components/session_filters.js` with:

```javascript
// ── Session Filters Component ───────────────────────────────────
// Reusable filter module mounted above the session table. Owns its
// own UI, state and localStorage persistence. Consumers call
// getActiveFiltersList() and feed the predicates into their
// existing session-filtering pipeline.
(function() {
  'use strict';

  // ── Storage helpers ─────────────────────────────────────────
  function storageKey(context) {
    return 'sessionFilters.' + context;
  }
  function loadState(context) {
    try {
      const raw = localStorage.getItem(storageKey(context));
      if (raw == null) return null;
      return JSON.parse(raw);
    } catch (e) { return null; }
  }
  function saveState(context, value) {
    try { localStorage.setItem(storageKey(context), JSON.stringify(value)); }
    catch (e) {}
  }

  // ── Mount ──────────────────────────────────────────────────
  function mountSessionFilters(container, options) {
    options = options || {};
    const ctx = { context: options.context || 'dashboard' };
    const getPool = options.getPool || function() { return []; };
    const onChange = options.onChange || function() {};

    // Placeholder DOM so consumers see *something* and verify
    // the file is loaded. Subsequent tasks replace this.
    const wrapper = document.createElement('div');
    wrapper.className = 'sf-wrapper';
    wrapper.setAttribute('data-context', ctx.context);
    container.appendChild(wrapper);

    return {
      getActiveFiltersList: function() { return []; },
      onPoolChanged: function() {},
      destroy: function() { wrapper.remove(); },
    };
  }

  window.mountSessionFilters = mountSessionFilters;
})();
```

- [ ] **Step 1.2: Write the skeleton CSS file**

Create `templates/components/session_filters.css` with:

```css
/* ── Session Filters Component ──────────────────────────────── */
.sf-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
```

- [ ] **Step 1.3: Wire into `extract_stats.py` for the dashboard build**

Open `extract_stats.py`. Locate `_get_html_template()` near line 2280. Replace the function body with:

```python
def _get_html_template():
    """Return the HTML template string with placeholders for data, styles, scripts."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "dashboard.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "dashboard.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "dashboard.js").read_text(encoding="utf-8")
    table_css = (base_dir / "templates" / "components" / "session_table.css").read_text(encoding="utf-8")
    table_js = (base_dir / "templates" / "components" / "session_table.js").read_text(encoding="utf-8")
    filters_css = (base_dir / "templates" / "components" / "session_filters.css").read_text(encoding="utf-8")
    filters_js = (base_dir / "templates" / "components" / "session_filters.js").read_text(encoding="utf-8")
    css = filters_css + "\n" + table_css + "\n" + css
    js = filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html
```

- [ ] **Step 1.4: Wire into `extract_stats.py` for the project detail build**

Locate `_get_project_html_template()` near line 2622. Replace its body with:

```python
def _get_project_html_template():
    """Return the project detail HTML template string."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "project_detail.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "project_detail.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "project_detail.js").read_text(encoding="utf-8")
    table_css = (base_dir / "templates" / "components" / "session_table.css").read_text(encoding="utf-8")
    table_js = (base_dir / "templates" / "components" / "session_table.js").read_text(encoding="utf-8")
    filters_css = (base_dir / "templates" / "components" / "session_filters.css").read_text(encoding="utf-8")
    filters_js = (base_dir / "templates" / "components" / "session_filters.js").read_text(encoding="utf-8")
    css = filters_css + "\n" + table_css + "\n" + css
    js = filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html
```

- [ ] **Step 1.5: JS syntax preflight**

Run:

```bash
node --check templates/components/session_filters.js && echo OK
```

Expected: `OK`.

- [ ] **Step 1.6: Regenerate dashboard and verify the new code is inlined**

Run:

```bash
python3 extract_stats.py >/dev/null && grep -c "window.mountSessionFilters" public/index.html
```

Expected: `1` (the function is in the inlined `<script>`).

- [ ] **Step 1.7: Commit**

```bash
git add templates/components/session_filters.js templates/components/session_filters.css extract_stats.py
git commit -m "feat(filters): scaffold session_filters component + wire into build"
```

---

## Task 2: Filter spec table (attribute definitions)

**Goal:** Define every filterable attribute (label, getter, group, scale, step) as data in the component so later tasks consume one source of truth.

**Files:**
- Modify: `templates/components/session_filters.js`

- [ ] **Step 2.1: Add `ATTRIBUTES` array and helpers**

Inside the IIFE, **above** the `// ── Storage helpers` block, insert:

```javascript
  // ── Attribute spec ─────────────────────────────────────────
  // scale: 'linear' | 'log'
  // get(s): returns a finite number, never null
  const ATTRIBUTES = [
    { id: 'user_messages',  group: 'volume',   label: 'User Msgs',
      get: (s) => s.user_messages || 0,
      scale: 'linear', step: 1, unit: '' },
    { id: 'messages',       group: 'volume',   label: 'Messages',
      get: (s) => s.messages || 0,
      scale: 'linear', step: 1, unit: '' },
    { id: 'duration_min',   group: 'volume',   label: 'Duration',
      get: (s) => s.duration_min || 0,
      scale: 'linear', step: 1, unit: 'min' },
    { id: 'total_tokens',   group: 'tokens',   label: 'Total Tokens',
      get: (s) => (s.input_tokens||0) + (s.output_tokens||0)
                  + (s.cache_read_tokens||0) + (s.cache_write_tokens||0),
      scale: 'log', step: 1, unit: '' },
    { id: 'cost',           group: 'cost',     label: 'Cost',
      get: (s) => Number(s.cost) || 0,
      scale: 'log', step: 0.01, unit: 'USD' },
    { id: 'cache_eff',      group: 'cache',    label: 'Cache Eff.',
      get: (s) => {
        const sum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
        if (sum === 0) return 0;
        return Math.round((s.cache_read_tokens||0) / sum * 100);
      },
      scale: 'linear', step: 1, unit: '%' },
    { id: 'tool_calls',     group: 'activity', label: 'Tool Calls',
      get: (s) => {
        if (!s.tools) return 0;
        let n = 0;
        for (const k in s.tools) n += s.tools[k] || 0;
        return n;
      },
      scale: 'log', step: 1, unit: '' },
    { id: 'agent_dispatches', group: 'activity', label: 'Agent Dispatches',
      get: (s) => Array.isArray(s.agent_dispatches) ? s.agent_dispatches.length : 0,
      scale: 'log', step: 1, unit: '' },
    { id: 'errors',         group: 'errors',   label: 'Error Count',
      get: (s) => s.error_count || 0,
      scale: 'linear', step: 1, unit: '' },
  ];
  const ATTRIBUTES_BY_ID = {};
  ATTRIBUTES.forEach(a => { ATTRIBUTES_BY_ID[a.id] = a; });

  const GROUP_ORDER = ['volume','tokens','cost','cache','activity','errors'];
  const GROUP_LABELS = {
    volume: 'Volume', tokens: 'Tokens', cost: 'Cost',
    cache: 'Cache Health', activity: 'Activity', errors: 'Errors',
  };
```

- [ ] **Step 2.2: Syntax preflight + commit**

```bash
node --check templates/components/session_filters.js && echo OK
python3 extract_stats.py >/dev/null && grep -c "ATTRIBUTES_BY_ID" public/index.html
```

Expected: `OK` and `1`.

```bash
git add templates/components/session_filters.js
git commit -m "feat(filters): define filterable attribute spec"
```

---

## Task 3: State management & persistence

**Goal:** Add a state object with per-attribute `{min, max}` plus a `panelOpen` flag, load from localStorage on mount, save on every mutation.

**Files:**
- Modify: `templates/components/session_filters.js`

- [ ] **Step 3.1: Replace the `mountSessionFilters` body to manage state**

Find `function mountSessionFilters(container, options)` (added in Task 1). Replace its entire body with:

```javascript
  function mountSessionFilters(container, options) {
    options = options || {};
    const ctx = { context: options.context || 'dashboard' };
    const getPool = options.getPool || function() { return []; };
    const onChange = options.onChange || function() {};

    // ── State ────────────────────────────────────────────────
    // Shape: { user_messages: {min, max}, ..., panelOpen: bool }
    // null on min/max means "unbounded on that side"
    let state = loadState(ctx.context) || {};
    state.panelOpen = !!state.panelOpen;
    ATTRIBUTES.forEach(a => {
      if (!state[a.id] || typeof state[a.id] !== 'object') {
        state[a.id] = { min: null, max: null };
      } else {
        if (typeof state[a.id].min !== 'number') state[a.id].min = null;
        if (typeof state[a.id].max !== 'number') state[a.id].max = null;
      }
    });
    // Drop unknown attribute keys from older releases
    Object.keys(state).forEach(k => {
      if (k === 'panelOpen') return;
      if (!ATTRIBUTES_BY_ID[k]) delete state[k];
    });

    function persist() { saveState(ctx.context, state); }

    function setBound(attrId, side, value) {
      const cur = state[attrId];
      if (!cur) return;
      cur[side] = (value == null || isNaN(value)) ? null : Number(value);
      persist();
    }

    function clearAttr(attrId) {
      if (!state[attrId]) return;
      state[attrId].min = null;
      state[attrId].max = null;
      persist();
    }

    function clearAll() {
      ATTRIBUTES.forEach(a => { state[a.id].min = null; state[a.id].max = null; });
      persist();
    }

    function activeCount() {
      let n = 0;
      ATTRIBUTES.forEach(a => {
        const v = state[a.id];
        if (v && (v.min != null || v.max != null)) n++;
      });
      return n;
    }

    // ── DOM scaffold ────────────────────────────────────────
    const wrapper = document.createElement('div');
    wrapper.className = 'sf-wrapper';
    wrapper.setAttribute('data-context', ctx.context);
    container.appendChild(wrapper);

    return {
      getActiveFiltersList: function() {
        const list = [];
        ATTRIBUTES.forEach(a => {
          const v = state[a.id];
          if (!v) return;
          if (v.min == null && v.max == null) return;
          list.push({
            id: a.id,
            label: a.label,
            min: v.min,
            max: v.max,
            predicate: (s) => {
              const n = a.get(s);
              if (v.min != null && n < v.min) return false;
              if (v.max != null && n > v.max) return false;
              return true;
            },
          });
        });
        return list;
      },
      onPoolChanged: function() {},
      destroy: function() { wrapper.remove(); },
      _state: state,           // for test/debug only
      _activeCount: activeCount,
      _clearAll: clearAll,
      _setBound: setBound,
    };
  }
```

- [ ] **Step 3.2: Syntax preflight**

```bash
node --check templates/components/session_filters.js && echo OK
```

Expected: `OK`.

- [ ] **Step 3.3: Manual state smoke (via headless Chromium console)**

After regenerating with `python3 extract_stats.py`, open `public/index.html` headless and run in the dev console:

```javascript
const h = window.mountSessionFilters(document.body, {context:'smoke'});
h._setBound('user_messages','min',2);
h._setBound('cost','max',5);
console.log('active:', h._activeCount());
console.log('preds match:', h.getActiveFiltersList().map(f => f.predicate({user_messages:3, cost:1.0})));
h._clearAll();
console.log('after clear:', h._activeCount());
```

Expected: `active: 2`, `preds match: [true, true]`, `after clear: 0`. Also verify `localStorage.getItem('sessionFilters.smoke')` round-trips between reloads (set values, reload, re-mount, check state). If automation is not available, defer this verification to Task 12 — but still mark this step done after the syntax preflight passes.

- [ ] **Step 3.4: Commit**

```bash
git add templates/components/session_filters.js
git commit -m "feat(filters): state, persistence, getActiveFiltersList()"
```

---

## Task 4: Pool-range computation

**Goal:** Compute slider min/max bounds for each attribute from the current sessions pool, with P99-snap to "nice" numbers. Re-runs whenever the upstream pool changes.

**Files:**
- Modify: `templates/components/session_filters.js`

- [ ] **Step 4.1: Insert a `computeRanges` helper near the attribute spec**

Right after the `GROUP_LABELS = { ... };` block, insert:

```javascript
  // ── Range computation ──────────────────────────────────────
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500,
                      1000, 2000, 5000, 10000, 20000, 50000,
                      100000, 200000, 500000, 1000000, 2000000,
                      5000000, 10000000];

  function niceCeil(value) {
    if (!isFinite(value) || value <= 0) return 1;
    for (const s of NICE_STEPS) {
      if (s >= value) return s;
    }
    // Beyond the predefined table: snap up to the next power of 10
    // so very heavy sessions still get a sensible slider max.
    return Math.pow(10, Math.ceil(Math.log10(value)));
  }

  function percentile(sorted, p) {
    if (sorted.length === 0) return 0;
    if (sorted.length === 1) return sorted[0];
    const idx = (sorted.length - 1) * p;
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }

  function computeRanges(sessions) {
    const out = {};
    ATTRIBUTES.forEach(a => {
      const vals = sessions.map(a.get).filter(v => Number.isFinite(v));
      if (vals.length === 0) { out[a.id] = { min: 0, max: 0 }; return; }
      vals.sort((x, y) => x - y);
      const p99 = percentile(vals, 0.99);
      let hi;
      if (a.unit === 'USD') {
        // Cents-precise nice ceil so cost sliders don't snap to $1.
        hi = Math.max(1, Math.ceil(p99 * 100) / 100);
        if (hi > 1) hi = niceCeil(hi);
      } else if (a.unit === '%') {
        hi = 100;
      } else {
        hi = niceCeil(p99 || 1);
      }
      out[a.id] = { min: 0, max: hi };
    });
    return out;
  }
```

- [ ] **Step 4.2: Wire `computeRanges` into the mount**

Inside `mountSessionFilters`, after the state-init block but before the DOM scaffold, add:

```javascript
    let ranges = computeRanges(getPool());

    function refreshRanges() {
      ranges = computeRanges(getPool());
      // Clamp current bounds into the new range
      ATTRIBUTES.forEach(a => {
        const v = state[a.id];
        const r = ranges[a.id];
        if (v.min != null) v.min = Math.min(Math.max(v.min, r.min), r.max);
        if (v.max != null) v.max = Math.min(Math.max(v.max, r.min), r.max);
      });
      persist();
    }
```

In the handle object, replace the no-op `onPoolChanged` with:

```javascript
      onPoolChanged: function() { refreshRanges(); /* rerender hooked in Task 6 */ },
```

- [ ] **Step 4.3: Syntax preflight + commit**

```bash
node --check templates/components/session_filters.js && echo OK
git add templates/components/session_filters.js
git commit -m "feat(filters): compute slider ranges from session pool"
```

---

## Task 5: Collapsed toolbar (presets + toggle with badge)

**Goal:** Render the always-visible row inside `.sf-wrapper`: two preset buttons and a toggle button. Toggle text reflects active filter count.

**Files:**
- Modify: `templates/components/session_filters.js`

- [ ] **Step 5.1: Add `buildToolbar()` and call it from the mount**

Inside `mountSessionFilters`, after the wrapper is appended to `container`, add:

```javascript
    const toolbar = document.createElement('div');
    toolbar.className = 'sf-toolbar';
    wrapper.appendChild(toolbar);

    const chipsRow = document.createElement('div');
    chipsRow.className = 'sf-chips';
    wrapper.appendChild(chipsRow);

    const panelHost = document.createElement('div');
    panelHost.className = 'sf-panel-host';
    wrapper.appendChild(panelHost);

    // Preset configs.
    const PRESETS = [
      { id: 'real',     label: 'Nur echte Sessions',
        apply:  () => { state.user_messages.min = 2; persist(); },
        clear:  () => { state.user_messages.min = null; persist(); },
        isOn:   () => state.user_messages.min === 2 },
      { id: 'expensive', label: 'Nur teure Sessions',
        apply:  () => { state.cost.min = 1.00; persist(); },
        clear:  () => { state.cost.min = null; persist(); },
        isOn:   () => state.cost.min === 1.00 },
    ];

    function renderToolbar() {
      toolbar.innerHTML = '';
      PRESETS.forEach(p => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'sf-preset' + (p.isOn() ? ' is-on' : '');
        b.textContent = p.label;
        b.addEventListener('click', () => {
          if (p.isOn()) p.clear(); else p.apply();
          renderAll();
          notifyChange();
        });
        toolbar.appendChild(b);
      });

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'sf-toggle' + (state.panelOpen ? ' is-open' : '');
      const n = activeCount();
      toggle.innerHTML = '&#9881; Weitere Filter'
        + (n > 0 ? ' (' + n + ')' : '')
        + ' <span class="sf-caret">' + (state.panelOpen ? '▴' : '▾') + '</span>';
      toggle.addEventListener('click', () => {
        state.panelOpen = !state.panelOpen;
        persist();
        renderAll();
      });
      toolbar.appendChild(toggle);
    }

    function renderChips() { /* Task 7 fills this in */ }
    function renderPanel() { /* Task 6 fills this in */ }

    function renderAll() {
      renderToolbar();
      renderChips();
      renderPanel();
    }

    function notifyChange() { onChange(); }

    renderAll();
```

Also update `onPoolChanged` and the public handle to re-render:

```javascript
      onPoolChanged: function() { refreshRanges(); renderAll(); },
```

- [ ] **Step 5.2: Syntax preflight + commit**

```bash
node --check templates/components/session_filters.js && echo OK
python3 extract_stats.py >/dev/null && grep -c "sf-toolbar" public/index.html
```

Expected: `OK` and at least `1`.

```bash
git add templates/components/session_filters.js
git commit -m "feat(filters): toolbar with preset buttons and panel toggle"
```

---

## Task 6: Expandable filter panel (sliders + min/max inputs)

**Goal:** When `state.panelOpen`, render a panel under the toolbar with the 9 attribute rows, each showing a range slider plus min and max number inputs. Group rows by `GROUP_ORDER`.

**Files:**
- Modify: `templates/components/session_filters.js`

- [ ] **Step 6.1: Add log-scale helpers**

Below `computeRanges`, add:

```javascript
  // Slider position is always integer 0–1000. We convert to/from the
  // attribute's domain using either linear or log10(value + 1).
  const SLIDER_RES = 1000;

  function valueToPos(attr, range, value) {
    if (range.max <= range.min) return 0;
    let v = Math.max(range.min, Math.min(range.max, value));
    if (attr.scale === 'log') {
      const a = Math.log10(range.min + 1);
      const b = Math.log10(range.max + 1);
      if (b <= a) return 0;
      return Math.round((Math.log10(v + 1) - a) / (b - a) * SLIDER_RES);
    }
    return Math.round((v - range.min) / (range.max - range.min) * SLIDER_RES);
  }

  function posToValue(attr, range, pos) {
    if (range.max <= range.min) return range.min;
    const t = Math.max(0, Math.min(SLIDER_RES, pos)) / SLIDER_RES;
    if (attr.scale === 'log') {
      const a = Math.log10(range.min + 1);
      const b = Math.log10(range.max + 1);
      const raw = Math.pow(10, a + (b - a) * t) - 1;
      return snap(attr, raw);
    }
    return snap(attr, range.min + (range.max - range.min) * t);
  }

  function snap(attr, v) {
    if (attr.step >= 1) return Math.round(v / attr.step) * attr.step;
    const inv = 1 / attr.step;
    return Math.round(v * inv) / inv;
  }
```

- [ ] **Step 6.2: Replace the `renderPanel()` placeholder**

Replace:

```javascript
    function renderPanel() { /* Task 6 fills this in */ }
```

with:

```javascript
    function renderPanel() {
      panelHost.innerHTML = '';
      if (!state.panelOpen) return;

      const panel = document.createElement('div');
      panel.className = 'sf-panel';

      GROUP_ORDER.forEach(g => {
        const attrs = ATTRIBUTES.filter(a => a.group === g);
        if (attrs.length === 0) return;
        const grp = document.createElement('div');
        grp.className = 'sf-group';
        const h = document.createElement('div');
        h.className = 'sf-group-h';
        h.textContent = GROUP_LABELS[g];
        grp.appendChild(h);
        attrs.forEach(a => grp.appendChild(buildRow(a)));
        panel.appendChild(grp);
      });

      const actions = document.createElement('div');
      actions.className = 'sf-panel-actions';
      const reset = document.createElement('button');
      reset.type = 'button';
      reset.className = 'sf-action';
      reset.textContent = 'Reset';
      reset.addEventListener('click', () => {
        clearAll();
        renderAll();
        notifyChange();
      });
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'sf-action';
      closeBtn.textContent = 'Schließen';
      closeBtn.addEventListener('click', () => {
        state.panelOpen = false;
        persist();
        renderAll();
      });
      actions.appendChild(reset);
      actions.appendChild(closeBtn);
      panel.appendChild(actions);

      panelHost.appendChild(panel);
    }

    function buildRow(attr) {
      const r = ranges[attr.id];
      const v = state[attr.id];
      const row = document.createElement('div');
      row.className = 'sf-row';

      const lbl = document.createElement('label');
      lbl.className = 'sf-row-label';
      lbl.textContent = attr.label + (attr.unit ? ' (' + attr.unit + ')' : '');
      row.appendChild(lbl);

      // Two-handle slider as two <input type=range> stacked.
      const track = document.createElement('div');
      track.className = 'sf-track';
      const sMin = document.createElement('input');
      sMin.type = 'range';
      sMin.min = 0; sMin.max = SLIDER_RES; sMin.step = 1;
      sMin.className = 'sf-slider sf-slider-min';
      sMin.value = valueToPos(attr, r, v.min != null ? v.min : r.min);
      sMin.setAttribute('aria-label', attr.label + ' minimum');
      const sMax = document.createElement('input');
      sMax.type = 'range';
      sMax.min = 0; sMax.max = SLIDER_RES; sMax.step = 1;
      sMax.className = 'sf-slider sf-slider-max';
      sMax.value = valueToPos(attr, r, v.max != null ? v.max : r.max);
      sMax.setAttribute('aria-label', attr.label + ' maximum');
      track.appendChild(sMin);
      track.appendChild(sMax);
      row.appendChild(track);

      const iMin = document.createElement('input');
      iMin.type = 'number';
      iMin.className = 'sf-num sf-num-min';
      iMin.placeholder = 'min';
      iMin.step = attr.step;
      if (v.min != null) iMin.value = v.min;
      const iMax = document.createElement('input');
      iMax.type = 'number';
      iMax.className = 'sf-num sf-num-max';
      iMax.placeholder = 'max';
      iMax.step = attr.step;
      if (v.max != null) iMax.value = v.max;
      row.appendChild(iMin);
      row.appendChild(iMax);

      function commit(side, raw) {
        const num = (raw === '' || raw == null) ? null : Number(raw);
        if (num == null || isNaN(num)) { setBound(attr.id, side, null); }
        else { setBound(attr.id, side, Math.min(Math.max(num, r.min), r.max)); }
        // Keep slider thumbs in sync with input values
        sMin.value = valueToPos(attr, r, state[attr.id].min != null ? state[attr.id].min : r.min);
        sMax.value = valueToPos(attr, r, state[attr.id].max != null ? state[attr.id].max : r.max);
        scheduleNotify();
        renderToolbar();
        renderChips();
      }

      sMin.addEventListener('input', () => {
        const val = posToValue(attr, r, Number(sMin.value));
        let other = state[attr.id].max != null ? state[attr.id].max : r.max;
        const minVal = Math.min(val, other);
        setBound(attr.id, 'min', minVal);
        iMin.value = minVal;
        sMin.value = valueToPos(attr, r, minVal);
        scheduleNotify();
        renderToolbar();
        renderChips();
      });
      sMax.addEventListener('input', () => {
        const val = posToValue(attr, r, Number(sMax.value));
        let other = state[attr.id].min != null ? state[attr.id].min : r.min;
        const maxVal = Math.max(val, other);
        setBound(attr.id, 'max', maxVal);
        iMax.value = maxVal;
        sMax.value = valueToPos(attr, r, maxVal);
        scheduleNotify();
        renderToolbar();
        renderChips();
      });
      iMin.addEventListener('change', () => commit('min', iMin.value));
      iMax.addEventListener('change', () => commit('max', iMax.value));

      return row;
    }
```

Also add at the start of the mount body (just below `let state = ...` block):

```javascript
    let notifyTimer = null;
    function scheduleNotify() {
      if (notifyTimer) clearTimeout(notifyTimer);
      notifyTimer = setTimeout(() => { notifyTimer = null; notifyChange(); }, 200);
    }
```

- [ ] **Step 6.3: Add Escape-closes-panel listener**

After `renderAll()` in `mountSessionFilters`, add:

```javascript
    function onDocKey(e) {
      if (e.key === 'Escape' && state.panelOpen) {
        state.panelOpen = false;
        persist();
        renderAll();
      }
    }
    document.addEventListener('keydown', onDocKey);
```

And in the destroy method:

```javascript
      destroy: function() {
        document.removeEventListener('keydown', onDocKey);
        wrapper.remove();
      },
```

- [ ] **Step 6.4: Syntax preflight + commit**

```bash
node --check templates/components/session_filters.js && echo OK
git add templates/components/session_filters.js
git commit -m "feat(filters): expandable panel with range sliders + inputs"
```

---

## Task 7: Chip row (active filters)

**Goal:** Render a chip per active filter under the toolbar with text describing the bounds and an `×` to clear. Also a trailing `Clear all` link.

**Files:**
- Modify: `templates/components/session_filters.js`

- [ ] **Step 7.1: Replace the `renderChips()` placeholder**

Replace:

```javascript
    function renderChips() { /* Task 7 fills this in */ }
```

with:

```javascript
    function chipText(attr, v) {
      const fmt = (n) => attr.unit === 'USD' ? n.toFixed(2) : String(n);
      if (v.min != null && v.max != null) return attr.label + ' ' + fmt(v.min) + '–' + fmt(v.max);
      if (v.min != null) return attr.label + ' ≥' + fmt(v.min);
      if (v.max != null) return attr.label + ' ≤' + fmt(v.max);
      return attr.label;
    }

    function renderChips() {
      chipsRow.innerHTML = '';
      const active = ATTRIBUTES.filter(a => {
        const v = state[a.id];
        return v && (v.min != null || v.max != null);
      });
      if (active.length === 0) return;
      active.forEach(a => {
        const c = document.createElement('span');
        c.className = 'sf-chip';
        const txt = document.createElement('span');
        txt.textContent = chipText(a, state[a.id]);
        c.appendChild(txt);
        const x = document.createElement('button');
        x.type = 'button';
        x.className = 'sf-chip-x';
        x.innerHTML = '&times;';
        x.setAttribute('aria-label', 'Clear ' + a.label);
        x.addEventListener('click', () => {
          clearAttr(a.id);
          renderAll();
          notifyChange();
        });
        c.appendChild(x);
        chipsRow.appendChild(c);
      });
      const ca = document.createElement('button');
      ca.type = 'button';
      ca.className = 'sf-clear-all';
      ca.textContent = 'Clear all';
      ca.addEventListener('click', () => {
        clearAll();
        renderAll();
        notifyChange();
      });
      chipsRow.appendChild(ca);
    }
```

- [ ] **Step 7.2: Syntax preflight + commit**

```bash
node --check templates/components/session_filters.js && echo OK
git add templates/components/session_filters.js
git commit -m "feat(filters): active-filter chip row with per-chip clear"
```

---

## Task 8: CSS styling

**Goal:** Apply the terminal aesthetic, lay the toolbar and panel out responsively, style sliders / chips / inputs.

**Files:**
- Modify: `templates/components/session_filters.css`

- [ ] **Step 8.1: Replace the CSS file with the full stylesheet**

Replace the contents of `templates/components/session_filters.css` with:

```css
/* ── Session Filters Component ──────────────────────────────── */
.sf-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
  font-family: var(--vc-font, inherit);
}

.sf-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.sf-preset,
.sf-toggle {
  background: var(--bg3, #2a2a2a);
  color: var(--text, #e6e6e6);
  border: 1px solid var(--border, #3a3a3a);
  padding: 6px 12px;
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.sf-preset:hover,
.sf-toggle:hover { background: var(--bg4, #333); }
.sf-preset.is-on {
  background: var(--vc-accent, #2c8); color: #000;
  border-color: var(--vc-accent, #2c8);
}
.sf-toggle.is-open { border-color: var(--vc-accent, #2c8); }
.sf-caret { opacity: 0.7; }

.sf-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.sf-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px 3px 10px;
  background: var(--bg2, #1d1d1d);
  border: 1px solid var(--border, #3a3a3a);
  border-radius: 12px;
  font-size: 12px;
  color: var(--text, #e6e6e6);
}
.sf-chip-x {
  background: transparent;
  border: 0;
  color: var(--text2, #999);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 6px;
}
.sf-chip-x:hover { color: var(--red, #e55); }
.sf-clear-all {
  background: transparent;
  border: 0;
  color: var(--text2, #999);
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}
.sf-clear-all:hover { color: var(--text, #e6e6e6); }

.sf-panel-host {}
.sf-panel {
  background: var(--bg2, #1d1d1d);
  border: 1px solid var(--border, #3a3a3a);
  border-radius: 10px;
  padding: 12px 16px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
@media (min-width: 1100px) {
  .sf-panel { grid-template-columns: 1fr 1fr; }
}

.sf-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sf-group-h {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text2, #999);
  margin-bottom: 4px;
}
.sf-row {
  display: grid;
  grid-template-columns: 130px 1fr 70px 70px;
  align-items: center;
  gap: 8px;
}
.sf-row-label {
  font-size: 12px;
  color: var(--text, #e6e6e6);
}
.sf-track {
  position: relative;
  height: 22px;
  display: grid;
  align-items: center;
}
.sf-track .sf-slider {
  grid-column: 1;
  grid-row: 1;
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  background: transparent;
  height: 22px;
  margin: 0;
  pointer-events: none;
}
.sf-track .sf-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  pointer-events: auto;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--vc-accent, #2c8);
  border: 1px solid var(--bg, #111);
  cursor: pointer;
}
.sf-track .sf-slider::-moz-range-thumb {
  pointer-events: auto;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--vc-accent, #2c8);
  border: 1px solid var(--bg, #111);
  cursor: pointer;
}
.sf-track::before {
  content: '';
  position: absolute;
  left: 0; right: 0; top: 50%;
  transform: translateY(-50%);
  height: 3px;
  background: var(--border, #3a3a3a);
  border-radius: 2px;
}
.sf-num {
  width: 100%;
  background: var(--bg3, #2a2a2a);
  border: 1px solid var(--border, #3a3a3a);
  border-radius: 6px;
  padding: 4px 6px;
  font: inherit;
  font-size: 12px;
  color: var(--text, #e6e6e6);
  text-align: right;
}

.sf-panel-actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.sf-action {
  background: var(--bg3, #2a2a2a);
  color: var(--text, #e6e6e6);
  border: 1px solid var(--border, #3a3a3a);
  padding: 6px 12px;
  border-radius: 6px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.sf-action:hover { background: var(--bg4, #333); }

@media (max-width: 699px) {
  .sf-row { grid-template-columns: 1fr; }
  .sf-row-label { font-weight: bold; }
}
```

- [ ] **Step 8.2: Rebuild dashboard, eyeball, commit**

```bash
python3 extract_stats.py >/dev/null && grep -c "sf-panel" public/index.html
```

Expected: at least `1`.

```bash
git add templates/components/session_filters.css
git commit -m "feat(filters): terminal-aesthetic styling for the filter panel"
```

---

## Task 9: Dashboard integration

**Goal:** Mount the filter module above the dashboard session table and extend `getFilteredSessions()` to apply the active filters. Recompute the module's ranges whenever the upstream pool changes.

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `templates/dashboard.js`

- [ ] **Step 9.1: Add the host divs to `dashboard.html`**

Open `templates/dashboard.html`. Locate the `<div class="session-filters">` block (around line 217) and the `<div id="sessionTableMount">` line below it (around line 225). Replace the block from the closing `</div>` of `.session-filters` down to (but not including) `<div id="sessionTableMount">` with:

```html
    </div>
    <div id="sessionFiltersMount"></div>
```

After edit, the section reads:

```html
    <div class="session-filters">
      <select id="filterProject"><option value="">__L_sessions_tab_all_projects__</option></select>
      <select id="filterSource"><option value="">All Sources</option></select>
      <input type="text" id="filterSearch" placeholder="__L_sessions_tab_search_placeholder__">
      <button id="exportXlsxBtn" class="bulk-download-btn" style="margin-left:auto" title="Export all currently filtered sessions as XLSX (Excel)">&#11015; XLSX</button>
      <button id="exportCsvBtn" class="bulk-download-btn" title="Export all currently filtered sessions as CSV">&#11015; CSV</button>
      <button id="bulkDownloadBtn" class="bulk-download-btn" title="Download all currently filtered sessions as a ZIP of Markdown files">&#11015; Download all (0)</button>
    </div>
    <div id="sessionFiltersMount"></div>
    <div id="sessionTableMount"></div>
```

- [ ] **Step 9.2: Declare and mount the filter module in `dashboard.js`**

Open `templates/dashboard.js`. Locate the `sessionTable` declaration (search for `let sessionTable`). Just above it, add:

```javascript
let sessionFilters = null;
```

Find `renderSessions()` (around line 1200). Insert immediately above the line `// Mount table on first call, update on subsequent calls.` (i.e. before `const filtered = getFilteredSessions();`):

```javascript
  if (!sessionFilters) {
    const fm = document.getElementById('sessionFiltersMount');
    sessionFilters = mountSessionFilters(fm, {
      context: 'dashboard',
      getPool: () => F.sessions,
      onChange: () => {
        const next = getFilteredSessions();
        if (sessionTable) sessionTable.update(next);
        updateBulkBtnLabel();
      },
    });
  } else {
    sessionFilters.onPoolChanged();
  }
```

- [ ] **Step 9.3: Extend `getFilteredSessions()` to apply numeric predicates**

Find `function getFilteredSessions()` (around line 1185). Replace it with:

```javascript
function getFilteredSessions() {
  let list = [...F.sessions];
  const proj = document.getElementById('filterProject').value;
  const src = document.getElementById('filterSource').value;
  const search = document.getElementById('filterSearch').value.toLowerCase();

  if (proj) list = list.filter(s => s.project === proj);
  if (src) list = list.filter(s => s.source === src);
  if (search) list = list.filter(s =>
    (s.first_prompt || '').toLowerCase().includes(search) ||
    s.project.toLowerCase().includes(search));

  if (sessionFilters) {
    const active = sessionFilters.getActiveFiltersList();
    for (const f of active) list = list.filter(f.predicate);
  }

  return list;
}
```

- [ ] **Step 9.4: Rebuild and smoke**

```bash
python3 extract_stats.py >/dev/null && grep -c "sessionFiltersMount" public/index.html
```

Expected: `1` in HTML container plus `1` in the script (so `>= 2`).

Open `public/index.html` in a headless browser (per `reference_local_ui_smoketest.md`); switch to Sessions tab; verify preset row and chip row render; click "Nur echte Sessions" and verify the table shrinks (single-user-message sessions disappear).

- [ ] **Step 9.5: Commit**

```bash
git add templates/dashboard.html templates/dashboard.js
git commit -m "feat(filters): mount filter module on dashboard sessions tab"
```

---

## Task 10: Project detail integration

**Goal:** Mount the filter module above the existing session table on the project detail page.

**Files:**
- Modify: `templates/project_detail.html`
- Modify: `templates/project_detail.js`

- [ ] **Step 10.1: Add the host div to `project_detail.html`**

Open `templates/project_detail.html`. Find `<div id="sessionList"></div>` (around line 46). Replace it with:

```html
    <div id="sessionFiltersMount"></div>
    <div id="sessionList"></div>
```

- [ ] **Step 10.2: Mount the filter module and re-feed the table**

Open `templates/project_detail.js`. Find the `mountSessionTable(...)` call (around line 83). Replace that block with:

```javascript
let pdSessionTable = null;
let pdSessionFilters = null;
const pdAllSessions = Array.isArray(P.sessions) ? P.sessions.slice() : [];

function pdApplyFilters() {
  let list = pdAllSessions.slice();
  if (pdSessionFilters) {
    const active = pdSessionFilters.getActiveFiltersList();
    for (const f of active) list = list.filter(f.predicate);
  }
  return list;
}

function pdRender() {
  const next = pdApplyFilters();
  if (!pdSessionTable) {
    pdSessionTable = mountSessionTable(
      document.getElementById('sessionList'),
      next,
      { context: 'projectDetail', hideChatInAnon: false }
    );
  } else {
    pdSessionTable.update(next);
  }
}

pdSessionFilters = mountSessionFilters(
  document.getElementById('sessionFiltersMount'),
  {
    context: 'projectDetail',
    getPool: () => pdAllSessions,
    onChange: pdRender,
  }
);

pdRender();
```

- [ ] **Step 10.3: Rebuild, smoke, commit**

```bash
python3 extract_stats.py >/dev/null && \
  ls public/projects | head -1 | xargs -I {} grep -c "sessionFiltersMount" public/projects/{}/index.html
```

Expected: a positive number (the host div made it into the rendered project page).

```bash
git add templates/project_detail.html templates/project_detail.js
git commit -m "feat(filters): mount filter module on project detail page"
```

---

## Task 11: End-to-end smoke verification

**Goal:** Spend ten minutes clicking through the feature in a real browser to catch what static checks miss. Capture findings; if anything breaks, file as a follow-up task or fix inline (per the project's conventions).

**Files:** none modified unless a fix is needed.

- [ ] **Step 11.1: Regenerate the dashboard against real data**

```bash
python3 extract_stats.py >/dev/null && echo OK
```

Expected: `OK`.

- [ ] **Step 11.2: Smoke checklist**

Open `public/index.html` in a regular browser (Chromium or Firefox). Confirm each:

- [ ] Sessions tab: preset buttons + "Weitere Filter" toggle render below the existing filter row.
- [ ] No chips visible on first load.
- [ ] Click "Nur echte Sessions" → button highlights, `User Msgs ≥2` chip appears, badge reads `(1)`, table loses single-user-message sessions.
- [ ] Open the panel → 9 sliders grouped in 6 sections; User Msgs slider min handle sits at `2`.
- [ ] Drag the Cost min slider → ~ 200 ms later, table re-renders, chip appears, badge increments.
- [ ] Type `5` into the Cost max number input → chip becomes `Cost 0.50–5.00`, table re-renders.
- [ ] Type a huge number (e.g. `1e9`) into Cost max → silently clamps to slider max; chip reflects clamped value.
- [ ] Click the `×` on a chip → that filter clears, slider thumb returns to range bound, badge decrements.
- [ ] Click `Clear all` → all chips disappear, presets de-highlight, badge gone.
- [ ] Press Escape while the panel is open → panel closes; state persists.
- [ ] Reload the page → panel-open state and any active filter values persist.
- [ ] Switch time filter to "7 days" → panel ranges shrink; current bounds clamp into the new range.
- [ ] Open a project detail page → filter module appears above the session table, its localStorage state is independent of dashboard's.
- [ ] At < 700 px viewport: rows stack vertically, chip row wraps.

- [ ] **Step 11.3: Mark plan complete**

If every box is checked, write `Smoke verified <ISO date>` to the bottom of this plan file and commit. If any box failed, file a follow-up commit fixing it before claiming done.

```bash
git add docs/superpowers/plans/2026-05-14-session-filters.md
git commit -m "chore(filters): smoke verification complete"
```

---

## Out-of-scope / follow-ups

- i18n of filter labels (currently English, matching `session_table.js` column labels)
- URL-param sharing of filter state
- Saved named filter presets
- Filter-driven CSV/XLSX export header line ("filter applied: X ≥ 2 …")
