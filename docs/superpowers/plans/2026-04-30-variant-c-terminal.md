# Variant-C Terminal Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Claude Stats dashboard, plus project + session detail pages, from the current multi-color "AI dashboard" look to the Variant-C "Terminal" design (single-accent terracotta, monospace, light + dark mode, no border-radius), preserving all existing features.

**Architecture:** Three template files per page (HTML/CSS/JS) extracted from `extract_stats.py` inline strings into a `templates/` directory. Build pipeline reads templates, injects them into a single self-contained HTML output (no external file references in produced HTML). Visual changes happen tab-by-tab after extraction. Chart.js stays for complex charts, custom CSS components for heatmap, distribution bars, hourly histogram.

**Tech Stack:** Python 3 (`extract_stats.py`), self-contained HTML/CSS/JS output, Chart.js v4.4.7 (CDN), no test framework — verification via output diff + browser smoke tests.

**Source spec:** `docs/superpowers/specs/2026-04-30-variant-c-terminal-design.md`
**Source design:** `docs/design_handoff_claude_stats_terminal/` (component-level details)

---

## Phase 0 — Template Extraction (no UI change)

**Acceptance gate for entire phase:** `diff -w` between `public/index.html` (and 3 sample project + session HTMLs) before vs. after Phase 0 must be empty.

### Task 0.1: Create reference snapshot

**Files:**
- Create: `/tmp/variant-c-snapshot/` (working dir for diff verification)

- [ ] **Step 1: Run extract_stats.py to ensure it works in current state**

```bash
cd /home/andie/projects/claude-stats && python3 extract_stats.py
```

Expected: succeeds, produces `public/index.html`, `public/projects/*.html`, `public/sessions/*.html`.

- [ ] **Step 2: Snapshot current output**

```bash
mkdir -p /tmp/variant-c-snapshot
cp public/index.html /tmp/variant-c-snapshot/index.html.before
ls public/projects/*.html | head -3 | xargs -I{} cp {} /tmp/variant-c-snapshot/
ls public/sessions/*.html | head -3 | xargs -I{} cp {} /tmp/variant-c-snapshot/
ls /tmp/variant-c-snapshot/
```

Expected: 7 files (1 dashboard + 3 projects + 3 sessions).

### Task 0.2: Create templates/ directory structure

**Files:**
- Create: `templates/` directory
- Create: `templates/.gitkeep` (placeholder)

- [ ] **Step 1: Create directory**

```bash
cd /home/andie/projects/claude-stats && mkdir -p templates && touch templates/.gitkeep
```

- [ ] **Step 2: Commit empty structure**

```bash
git add templates/.gitkeep
git commit -m "chore: add templates/ directory for extracted HTML/CSS/JS"
```

### Task 0.3: Extract dashboard template (the core extraction)

**Files:**
- Read: `extract_stats.py:1943-3919` (`_get_html_template()`)
- Create: `templates/dashboard.html`, `templates/dashboard.css`, `templates/dashboard.js`
- Modify: `extract_stats.py` — `_get_html_template()` reads from files

- [ ] **Step 1: Read the entire `_get_html_template()` function body**

The function returns a single triple-quoted string from line 1945 (`return '''`) to its closing `'''`. Read the full content and split it into three sections:
1. HTML before `<style>` opening
2. CSS between `<style>` and `</style>`
3. HTML between `</style>` and `<script>` (the body markup)
4. JS between `<script>` (the inline one, NOT the CDN ones) and `</script>`
5. HTML after `</script>` (closing tags + footer divs)

- [ ] **Step 2: Write `templates/dashboard.html`**

Structure:
```html
<!DOCTYPE html>
<html lang="__L_html_lang__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code Dashboard</title>
<link rel="icon" type="image/png" href="favicon.png">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<!-- STYLES -->
</head>
<body>
[... entire body markup verbatim from current template ...]
<!-- SCRIPTS -->
[... closing footer divs verbatim ...]
</body>
</html>
```

- [ ] **Step 3: Write `templates/dashboard.css`**

Verbatim copy of everything between `<style>` and `</style>` from the current template.

- [ ] **Step 4: Write `templates/dashboard.js`**

Verbatim copy of everything between the inline `<script>` and matching `</script>` (NOT the CDN scripts in the head).

- [ ] **Step 5: Modify `_get_html_template()` to read files**

Replace `_get_html_template()` body with:
```python
def _get_html_template():
    """Return the HTML template string with placeholders for data, styles, scripts."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "dashboard.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "dashboard.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "dashboard.js").read_text(encoding="utf-8")
    html = html.replace("<!-- STYLES -->", f"<style>\n{css}\n</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>\n{js}\n</script>")
    return html
```

- [ ] **Step 6: Run extract_stats.py and diff**

```bash
cd /home/andie/projects/claude-stats && python3 extract_stats.py
diff -w /tmp/variant-c-snapshot/index.html.before public/index.html
```

Expected: empty diff (only whitespace tolerated).

- [ ] **Step 7: If diff is non-empty, fix and re-run**

Likely sources of diff:
- Extra/missing newlines around `<style>`/`<script>` markers — adjust the f-string.
- Triple-quote escaping differences in the original — preserve exactly.

- [ ] **Step 8: Commit**

```bash
git add templates/dashboard.html templates/dashboard.css templates/dashboard.js extract_stats.py
git commit -m "refactor: extract dashboard template HTML/CSS/JS to templates/"
```

### Task 0.4: Extract session detail template

**Files:**
- Read: `extract_stats.py:4110-5814` (`_get_session_html_template()`)
- Create: `templates/session_detail.html`, `templates/session_detail.css`, `templates/session_detail.js`
- Modify: `extract_stats.py:4110-5814`

- [ ] **Step 1: Apply the same extraction pattern as Task 0.3**

Read `_get_session_html_template()`, split into HTML/CSS/JS, write three template files, replace function body with the same read-and-replace pattern.

```python
def _get_session_html_template():
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "session_detail.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "session_detail.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "session_detail.js").read_text(encoding="utf-8")
    html = html.replace("<!-- STYLES -->", f"<style>\n{css}\n</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>\n{js}\n</script>")
    return html
```

- [ ] **Step 2: Run extract_stats.py and diff session HTMLs**

```bash
python3 extract_stats.py
for f in /tmp/variant-c-snapshot/*.html; do
  base=$(basename "$f" .before)
  current=$(find public/sessions -name "$base" | head -1)
  [ -n "$current" ] && diff -w "$f" "$current"
done
```

Expected: no output (= no diffs).

- [ ] **Step 3: Commit**

```bash
git add templates/session_detail.* extract_stats.py
git commit -m "refactor: extract session detail template to templates/"
```

### Task 0.5: Extract project detail template

**Files:**
- Read: `extract_stats.py:5937-6188` (`_get_project_html_template()`)
- Create: `templates/project_detail.html`, `templates/project_detail.css`, `templates/project_detail.js`
- Modify: `extract_stats.py:5937-6188`

- [ ] **Step 1: Apply same extraction pattern**

```python
def _get_project_html_template():
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "project_detail.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "project_detail.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "project_detail.js").read_text(encoding="utf-8")
    html = html.replace("<!-- STYLES -->", f"<style>\n{css}\n</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>\n{js}\n</script>")
    return html
```

Note: project template may have no inline JS (smaller file). If so, skip JS extraction and remove the `<!-- SCRIPTS -->` substitution.

- [ ] **Step 2: Diff project HTMLs**

```bash
python3 extract_stats.py
for f in /tmp/variant-c-snapshot/*.html; do
  base=$(basename "$f" .before)
  current=$(find public/projects -name "$base" | head -1)
  [ -n "$current" ] && diff -w "$f" "$current"
done
```

Expected: empty diffs.

- [ ] **Step 3: Commit**

```bash
git add templates/project_detail.* extract_stats.py
git commit -m "refactor: extract project detail template to templates/"
```

### Task 0.6: Phase 0 verification + browser smoke test

- [ ] **Step 1: Browser open and click through**

```bash
xdg-open /home/andie/projects/claude-stats/public/index.html &
```

Verify in browser:
- [ ] All tabs render (Cost / Activity / Projects / Sessions / Plan / Insights / Agents)
- [ ] Range filter buttons work
- [ ] Quick-filter input filters projects
- [ ] Click a project → project detail page opens
- [ ] Click a session → session detail page opens, chat replay starts
- [ ] Press F2 → anonymization toggles, project names become "Project N"

- [ ] **Step 2: Phase 0 done — tag commit**

```bash
git tag phase-0-complete
```

---

## Phase 1 — Persistent Shell + Design Tokens

**Acceptance gate:** Top-bar, primary nav, KPI strip render in Variant-C look in both light + dark mode. Theme toggle works. Old tab content remains functional inside a legacy wrapper.

### Task 1.1: Add Variant-C CSS tokens

**Files:**
- Modify: `templates/dashboard.css` (add to top of file)

- [ ] **Step 1: Prepend CSS variables for both modes**

Add at the very top of `templates/dashboard.css`:

```css
:root {
  --bg: #f4f1ec;
  --panel: #fbfaf6;
  --grid: #d8d2c4;
  --grid-2: #e8e3d6;
  --fg: #1c1a17;
  --fg-2: #4d4a42;
  --fg-3: #918a7a;
  --accent: #b04a2f;
  --accent-soft: #f1d9cd;
  --font-mono: 'Geist Mono', 'JetBrains Mono', ui-monospace, monospace;
  --font-sans: 'Geist', 'Inter', system-ui, sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e0d0b;
    --panel: #15140f;
    --grid: #2a2620;
    --grid-2: #1f1d18;
    --fg: #ece7da;
    --fg-2: #b3ad9b;
    --fg-3: #76705f;
    --accent: #d97757;
    --accent-soft: #2c1c14;
  }
}

html.theme-light {
  --bg: #f4f1ec;
  --panel: #fbfaf6;
  --grid: #d8d2c4;
  --grid-2: #e8e3d6;
  --fg: #1c1a17;
  --fg-2: #4d4a42;
  --fg-3: #918a7a;
  --accent: #b04a2f;
  --accent-soft: #f1d9cd;
}

html.theme-dark {
  --bg: #0e0d0b;
  --panel: #15140f;
  --grid: #2a2620;
  --grid-2: #1f1d18;
  --fg: #ece7da;
  --fg-2: #b3ad9b;
  --fg-3: #76705f;
  --accent: #d97757;
  --accent-soft: #2c1c14;
}

body {
  font-family: var(--font-mono);
  font-feature-settings: 'tnum' 1, 'zero' 1;
  background: var(--bg);
  color: var(--fg);
}

* { border-radius: 0 !important; }
```

The `* { border-radius: 0 !important; }` is a temporary nuclear option to enforce no-rounded-corners across the legacy components. It will be removed in Phase 2 once components are individually restyled.

- [ ] **Step 2: Build and visually verify**

```bash
cd /home/andie/projects/claude-stats && python3 extract_stats.py
xdg-open public/index.html
```

Expected: dashboard now uses warm-off-white (light) or near-black (dark) background, monospace font, no rounded corners. Old layout still works structurally — just looks raw/jarring with new colors. That's fine for now.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.css
git commit -m "feat: introduce Variant-C design tokens (light + dark)"
```

### Task 1.2: Replace top-bar markup

**Files:**
- Modify: `templates/dashboard.html` — locate the existing header/top bar markup and replace it
- Modify: `templates/dashboard.css` — add styles for `.vc-top`
- Modify: `templates/dashboard.js` — UTC time updater + theme toggle handler

- [ ] **Step 1: Find current top-bar markup**

In `templates/dashboard.html`, find the existing `.header` or `.top` div. It probably has the title, range filters, language selector, time. Note its exact DOM structure for replacing.

- [ ] **Step 2: Replace top-bar markup**

Replace with:
```html
<div class="vc-top">
  <div class="vc-top-left">
    <span class="vc-brand-mark"></span>
    <span class="vc-brand-name">CLAUDE.STATS</span>
    <span class="vc-version">v__VERSION__</span>
  </div>
  <div class="vc-top-center">
    <span class="vc-kv"><span class="vc-k">USER</span><span class="vc-v" id="topUser">-</span></span>
    <span class="vc-kv"><span class="vc-k">PLAN</span><span class="vc-v" id="topPlan">-</span></span>
    <span class="vc-kv"><span class="vc-k">RANGE</span><span class="vc-v" id="topRange">90d</span></span>
  </div>
  <div class="vc-top-right">
    <button class="vc-icon-btn" id="langToggle" title="Language">__L_top_lang_label__</button>
    <button class="vc-icon-btn" id="themeToggle" title="Theme">☼</button>
    <span class="vc-f2-hint">F2: ANON</span>
    <span class="vc-live"><span class="vc-live-dot">●</span> LIVE</span>
    <span class="vc-utc" id="utcTime">--:--:-- UTC</span>
  </div>
</div>
```

- [ ] **Step 3: Add CSS for top-bar**

Append to `templates/dashboard.css`:
```css
.vc-top {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  background: var(--panel);
  border-bottom: 1px solid var(--grid);
  font-family: var(--font-mono);
  font-size: 11px;
}
.vc-top-left { display: flex; align-items: center; gap: 10px; }
.vc-brand-mark { display: inline-block; width: 8px; height: 8px; background: var(--accent); }
.vc-brand-name { font-weight: 600; letter-spacing: 0.02em; }
.vc-version { color: var(--fg-3); }
.vc-top-center { display: flex; gap: 24px; justify-self: center; }
.vc-kv { display: inline-flex; gap: 6px; }
.vc-k { color: var(--fg-3); letter-spacing: 0.14em; }
.vc-v { color: var(--fg); font-weight: 500; }
.vc-top-right { display: flex; align-items: center; gap: 12px; }
.vc-icon-btn {
  background: transparent;
  border: 1px solid var(--grid);
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 4px 8px;
  cursor: pointer;
}
.vc-icon-btn:hover { background: var(--accent-soft); }
.vc-f2-hint { color: var(--fg-3); font-size: 10px; letter-spacing: 0.14em; }
.vc-live { color: var(--accent); }
.vc-live-dot { display: inline-block; }
.vc-utc { color: var(--fg-3); }
```

- [ ] **Step 4: Wire JS for theme toggle, language toggle, UTC time**

In `templates/dashboard.js`, add (after existing init code):
```js
// Theme handling
function applyTheme(theme) {
  document.documentElement.classList.remove('theme-light', 'theme-dark');
  if (theme === 'light' || theme === 'dark') {
    document.documentElement.classList.add('theme-' + theme);
  }
  const btn = document.getElementById('themeToggle');
  if (btn) {
    const isDark = theme === 'dark' || (theme !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    btn.textContent = isDark ? '☾' : '☼';
  }
  if (typeof setupChartDefaults === 'function') setupChartDefaults();
}
const savedTheme = localStorage.getItem('vc-theme') || 'system';
applyTheme(savedTheme);
document.getElementById('themeToggle')?.addEventListener('click', () => {
  const current = localStorage.getItem('vc-theme') || 'system';
  const next = current === 'system' ? 'light' : (current === 'light' ? 'dark' : 'system');
  localStorage.setItem('vc-theme', next);
  applyTheme(next);
});

// Language toggle (reload with ?lang=de or ?lang=en — server-side rendered, so no live switch)
document.getElementById('langToggle')?.addEventListener('click', () => {
  const url = new URL(window.location.href);
  const current = url.searchParams.get('lang') || (document.documentElement.lang || 'en');
  url.searchParams.set('lang', current === 'de' ? 'en' : 'de');
  window.location.href = url.toString();
});

// UTC time updater
function updateUtcTime() {
  const el = document.getElementById('utcTime');
  if (!el) return;
  const now = new Date();
  const t = now.toISOString().slice(11, 19);
  el.textContent = t + ' UTC';
}
updateUtcTime();
setInterval(updateUtcTime, 1000);

// Populate USER / PLAN / RANGE from data
if (typeof DASHBOARD_DATA !== 'undefined' && DASHBOARD_DATA) {
  const u = document.getElementById('topUser');
  const p = document.getElementById('topPlan');
  if (u && DASHBOARD_DATA.config && DASHBOARD_DATA.config.display_name) u.textContent = DASHBOARD_DATA.config.display_name;
  if (p && DASHBOARD_DATA.plan_summary && DASHBOARD_DATA.plan_summary.current_plan) p.textContent = DASHBOARD_DATA.plan_summary.current_plan;
}
```

Note: language toggle is implemented as a re-render (not live-switch), since strings are baked-in by `extract_stats.py`. This is a known limitation. Server-side rendering means the user sees a one-page-reload to switch. Acceptable for now.

**Subtle but important:** the page is statically generated, so `?lang=de` won't actually switch on the client. This needs `extract_stats.py` to also generate a `index_de.html` and `index_en.html` OR the language toggle just kicks the user back to the static file, which... won't change. Mark this as a known TODO and just make the toggle show a notification "Set `language` in config.json to switch — UI toggle currently informational only" instead of actually toggling.

Actually, simpler: the toggle reads the current `lang` attribute on `<html>`, and if user clicks it, it briefly highlights and shows a toast: "Language is set in config.json. Edit it and re-run extract_stats.py to switch."

Replace the language toggle handler with:
```js
document.getElementById('langToggle')?.addEventListener('click', () => {
  alert('Language is set in config.json — edit and re-run extract_stats.py to switch.');
});
```

This is honest about the constraint without misleading the user.

- [ ] **Step 5: Add new locale strings**

In `locales/en.json` add:
```json
{
  "top": {
    "lang_label": "DE/EN"
  }
}
```
In `locales/de.json` add:
```json
{
  "top": {
    "lang_label": "EN/DE"
  }
}
```

The placeholder `__L_top_lang_label__` will be substituted via existing `_inject_locale()`.

- [ ] **Step 6: Verify**

```bash
python3 extract_stats.py
xdg-open public/index.html
```

Expected: top-bar shows new Variant-C look, theme toggle cycles through system/light/dark, UTC time updates every second, language button shows toast.

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.html templates/dashboard.css templates/dashboard.js locales/
git commit -m "feat: replace top bar with Variant-C terminal design"
```

### Task 1.3: Replace primary nav (tabs + range + quick filter)

**Files:**
- Modify: `templates/dashboard.html` — find tabs/range/filter markup, replace
- Modify: `templates/dashboard.css` — add `.vc-nav` styles
- Modify: `templates/dashboard.js` — preserve existing tab-switching logic, hook up new buttons

- [ ] **Step 1: Find existing tab + range + filter markup**

Locate the current `.tabs`, `.time-filter`, and project filter input in the HTML. Note their IDs and JS handlers.

- [ ] **Step 2: Replace with Variant-C nav**

```html
<div class="vc-nav">
  <div class="vc-nav-tabs">
    <button class="vc-tab active" data-tab="cost">__L_tabs_cost__</button>
    <button class="vc-tab" data-tab="activity">__L_tabs_activity__</button>
    <button class="vc-tab" data-tab="projects">__L_tabs_projects__</button>
    <button class="vc-tab" data-tab="sessions">__L_tabs_sessions__</button>
    <button class="vc-tab" data-tab="plan">__L_tabs_plan__</button>
    <button class="vc-tab" data-tab="insights">__L_tabs_insights__</button>
    <button class="vc-tab" data-tab="agents">__L_tabs_agents__</button>
  </div>
  <div class="vc-nav-right">
    <div class="vc-filter">
      <span class="vc-filter-prompt">&gt;</span>
      <input type="text" id="quickFilter" class="vc-filter-input" placeholder="__L_filter_placeholder__">
    </div>
    <div class="vc-range">
      <button class="vc-range-btn" data-days="all">All</button>
      <button class="vc-range-btn" data-days="7">7D</button>
      <button class="vc-range-btn" data-days="30">30D</button>
      <button class="vc-range-btn active" data-days="90">90D</button>
      <button class="vc-range-btn" data-days="365">1Y</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add CSS**

```css
.vc-nav {
  display: flex;
  justify-content: space-between;
  align-items: stretch;
  padding: 0 20px;
  border-bottom: 1px solid var(--grid);
  background: var(--bg);
}
.vc-nav-tabs { display: flex; }
.vc-tab {
  padding: 14px 18px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-weight: 500;
  color: var(--fg-3);
  background: transparent;
  border: none;
  cursor: pointer;
  position: relative;
}
.vc-tab:hover { color: var(--fg-2); }
.vc-tab.active { color: var(--fg); }
.vc-tab.active::after {
  content: '';
  position: absolute;
  left: 12px; right: 12px; bottom: -1px;
  height: 2px;
  background: var(--accent);
}
.vc-nav-right { display: flex; align-items: center; gap: 12px; }
.vc-filter {
  display: flex;
  align-items: center;
  border: 1px solid var(--grid);
  padding: 0 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  height: 28px;
}
.vc-filter-prompt { color: var(--accent); margin-right: 6px; font-weight: 600; }
.vc-filter-input {
  background: transparent;
  border: none;
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 11px;
  outline: none;
  min-width: 140px;
}
.vc-filter-input::placeholder { color: var(--fg-3); }
.vc-range { display: flex; border: 1px solid var(--grid); }
.vc-range-btn {
  padding: 6px 12px;
  background: transparent;
  border: none;
  border-left: 1px solid var(--grid);
  color: var(--fg-3);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  cursor: pointer;
}
.vc-range-btn:first-child { border-left: none; }
.vc-range-btn:hover { color: var(--fg-2); }
.vc-range-btn.active { color: var(--accent); font-weight: 600; }
```

- [ ] **Step 4: Wire JS**

Preserve any existing tab-switching logic, but add new bindings:

```js
document.querySelectorAll('.vc-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.vc-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const tabName = tab.dataset.tab;
    // Trigger existing tab-switch logic — call into legacy showTab() if present
    if (typeof showTab === 'function') showTab(tabName);
  });
});

document.querySelectorAll('.vc-range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.vc-range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const days = btn.dataset.days;
    document.getElementById('topRange').textContent = days === 'all' ? 'all' : days + 'd';
    if (typeof applyFilter === 'function') applyFilter(days === 'all' ? 'all' : parseInt(days));
  });
});

document.getElementById('quickFilter')?.addEventListener('input', (e) => {
  const v = e.target.value.toLowerCase();
  if (typeof applyProjectFilter === 'function') applyProjectFilter(v);
  // Fallback: hide rows containing project name not matching
});
```

- [ ] **Step 5: Add locale strings**

In `locales/en.json`:
```json
{
  "tabs": {
    "cost": "Cost",
    "activity": "Activity",
    "projects": "Projects",
    "sessions": "Sessions",
    "plan": "Plan",
    "insights": "Insights",
    "agents": "Agents"
  },
  "filter": {
    "placeholder": "filter projects..."
  }
}
```

In `locales/de.json`:
```json
{
  "tabs": {
    "cost": "Kosten",
    "activity": "Aktivität",
    "projects": "Projekte",
    "sessions": "Sessions",
    "plan": "Plan",
    "insights": "Insights",
    "agents": "Agents"
  },
  "filter": {
    "placeholder": "Projekte filtern..."
  }
}
```

- [ ] **Step 6: Verify and commit**

```bash
python3 extract_stats.py && xdg-open public/index.html
```

Click each tab → content swaps. Click each range → KPIs/chart update. Type in filter → projects narrow.

```bash
git add templates/dashboard.html templates/dashboard.css templates/dashboard.js locales/
git commit -m "feat: replace primary nav with Variant-C tabs + range + filter"
```

### Task 1.4: Replace KPI strip

**Files:**
- Modify: `templates/dashboard.html` — replace existing `.kpi-grid` with Variant-C 5-cell strip
- Modify: `templates/dashboard.css` — add `.vc-kpis` styles
- Modify: `templates/dashboard.js` — KPI render with subs

- [ ] **Step 1: Replace markup**

```html
<div class="vc-kpis">
  <div class="vc-kpi vc-kpi-primary">
    <div class="vc-kpi-label">API EQUIVALENT<span class="vc-kpi-delta" id="kpiSavePct"></span></div>
    <div class="vc-kpi-value" id="kpiApiEq">$0.00</div>
    <div class="vc-kpi-sub" id="kpiApiEqSub">paid <b>$0.00</b> · save <b>0.0%</b></div>
  </div>
  <div class="vc-kpi">
    <div class="vc-kpi-label">SESSIONS</div>
    <div class="vc-kpi-value" id="kpiSessions">0</div>
    <div class="vc-kpi-sub" id="kpiSessionsSub">avg <b>0m</b></div>
  </div>
  <div class="vc-kpi">
    <div class="vc-kpi-label">MESSAGES</div>
    <div class="vc-kpi-value" id="kpiMessages">0</div>
    <div class="vc-kpi-sub" id="kpiMessagesSub"><b>0</b>/session</div>
  </div>
  <div class="vc-kpi">
    <div class="vc-kpi-label">OUTPUT TOKENS</div>
    <div class="vc-kpi-value" id="kpiOutput">0</div>
    <div class="vc-kpi-sub" id="kpiOutputSub">in <b>0</b></div>
  </div>
  <div class="vc-kpi">
    <div class="vc-kpi-label">CACHE HIT</div>
    <div class="vc-kpi-value" id="kpiCacheHit">0<span class="vc-kpi-pct">%</span></div>
    <div class="vc-kpi-sub" id="kpiCacheHitSub">read <b>0</b></div>
  </div>
</div>
```

- [ ] **Step 2: Add CSS**

```css
.vc-kpis {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr 1fr 1fr;
  border: 1px solid var(--grid);
  margin: 24px 20px;
  background: var(--panel);
}
.vc-kpi {
  padding: 14px 18px;
  border-right: 1px solid var(--grid);
}
.vc-kpi:last-child { border-right: none; }
.vc-kpi-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--fg-3);
  display: flex;
  justify-content: space-between;
}
.vc-kpi-delta { color: var(--accent); }
.vc-kpi-value {
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.02em;
  margin: 6px 0 4px;
  font-feature-settings: 'tnum' 1;
}
.vc-kpi-pct { font-size: 18px; color: var(--fg-3); }
.vc-kpi-primary .vc-kpi-value { color: var(--accent); }
.vc-kpi-sub {
  font-size: 11px;
  color: var(--fg-3);
}
.vc-kpi-sub b { font-weight: 500; color: var(--fg-2); }
```

- [ ] **Step 3: Add JS render function**

```js
function fmtTokens(n) {
  if (n >= 1e9) return (n/1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return String(n|0);
}
function fmtUsd(n) {
  return '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function renderVCKpis() {
  const d = DASHBOARD_DATA;
  if (!d) return;

  // API equivalent + save %
  const apiEq = d.totals?.cost ?? 0;
  const paid = d.plan_summary?.actual_paid_for_range ?? d.plan_summary?.total_paid ?? 0;
  const savePct = apiEq > 0 ? ((apiEq - paid) / apiEq * 100) : 0;
  document.getElementById('kpiApiEq').textContent = fmtUsd(apiEq);
  document.getElementById('kpiApiEqSub').innerHTML = `paid <b>${fmtUsd(paid)}</b> · save <b>${savePct.toFixed(1)}%</b>`;
  document.getElementById('kpiSavePct').textContent = savePct >= 0 ? `▲ ${savePct.toFixed(1)}%` : `▼ ${(-savePct).toFixed(1)}%`;

  // Sessions + avg duration
  const sessions = d.totals?.sessions ?? 0;
  const avgDuration = d.totals?.avg_session_duration_minutes ?? 0;
  document.getElementById('kpiSessions').textContent = sessions.toLocaleString('en-US');
  document.getElementById('kpiSessionsSub').innerHTML = `avg <b>${Math.round(avgDuration)}m</b>`;

  // Messages + per session
  const msgs = d.totals?.messages ?? 0;
  const perSession = sessions > 0 ? Math.round(msgs / sessions) : 0;
  document.getElementById('kpiMessages').textContent = msgs.toLocaleString('en-US');
  document.getElementById('kpiMessagesSub').innerHTML = `<b>${perSession}</b>/session`;

  // Output + input tokens
  const output = d.totals?.output_tokens ?? 0;
  const input = d.totals?.input_tokens ?? 0;
  document.getElementById('kpiOutput').textContent = fmtTokens(output);
  document.getElementById('kpiOutputSub').innerHTML = `in <b>${fmtTokens(input)}</b>`;

  // Cache hit + read total
  const cacheRead = d.totals?.cache_read_tokens ?? 0;
  const cacheWrite = d.totals?.cache_write_tokens ?? 0;
  const totalIn = input + cacheRead + cacheWrite;
  const cacheHit = totalIn > 0 ? (cacheRead / totalIn * 100) : 0;
  document.getElementById('kpiCacheHit').innerHTML = cacheHit.toFixed(1) + '<span class="vc-kpi-pct">%</span>';
  document.getElementById('kpiCacheHitSub').innerHTML = `read <b>${fmtTokens(cacheRead)}</b>`;
}
renderVCKpis();
```

Note: The exact field names in `DASHBOARD_DATA` may differ. The implementor should `console.log(DASHBOARD_DATA)` and adjust field paths to match actual structure. Common fields likely exist as `total_cost`, `total_messages`, etc. — adjust as needed.

- [ ] **Step 4: Verify and commit**

```bash
python3 extract_stats.py && xdg-open public/index.html
```

Expected: 5-cell KPI strip with correct values, primary cell terracotta.

```bash
git add templates/dashboard.html templates/dashboard.css templates/dashboard.js
git commit -m "feat: replace KPI grid with Variant-C 5-cell strip"
```

### Task 1.5: Add Chart.js theming defaults

**Files:**
- Modify: `templates/dashboard.js`

- [ ] **Step 1: Add setupChartDefaults function**

Add early in `dashboard.js` (before any chart instantiation):

```js
function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function setupChartDefaults() {
  if (typeof Chart === 'undefined') return;
  const fgC = getCSSVar('--fg');
  const fg2C = getCSSVar('--fg-2');
  const fg3C = getCSSVar('--fg-3');
  const gridC = getCSSVar('--grid');
  const grid2C = getCSSVar('--grid-2');
  const accentC = getCSSVar('--accent');
  const panelC = getCSSVar('--panel');

  Chart.defaults.font.family = "'Geist Mono', 'JetBrains Mono', ui-monospace, monospace";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = fg3C;
  Chart.defaults.borderColor = gridC;
  Chart.defaults.elements.line.borderWidth = 1.5;
  Chart.defaults.elements.line.borderColor = accentC;
  Chart.defaults.elements.point.radius = 0;
  Chart.defaults.elements.point.hoverRadius = 3;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = panelC;
  Chart.defaults.plugins.tooltip.titleColor = fgC;
  Chart.defaults.plugins.tooltip.bodyColor = fg2C;
  Chart.defaults.plugins.tooltip.borderColor = gridC;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 0;
  Chart.defaults.plugins.tooltip.titleFont = {family: "'Geist Mono', monospace", size: 11};
  Chart.defaults.plugins.tooltip.bodyFont = {family: "'Geist Mono', monospace", size: 11};

  if (Chart.defaults.scale) {
    Chart.defaults.scale.grid = Chart.defaults.scale.grid || {};
    Chart.defaults.scale.grid.color = grid2C;
    Chart.defaults.scale.grid.borderDash = [1, 3];
    Chart.defaults.scale.ticks = Chart.defaults.scale.ticks || {};
    Chart.defaults.scale.ticks.color = fg3C;
  }
  // Re-update existing charts
  if (Chart.instances) {
    for (const id in Chart.instances) {
      try { Chart.instances[id].update('none'); } catch {}
    }
  }
}
// Call once at startup
setupChartDefaults();
```

- [ ] **Step 2: Re-call on theme change**

Edit `applyTheme()` to also call `setupChartDefaults()` after applying the class.

- [ ] **Step 3: Verify and commit**

Existing charts should now render with Geist Mono, terracotta line color, dotted gridlines.

```bash
python3 extract_stats.py && xdg-open public/index.html
git add templates/dashboard.js
git commit -m "feat: theme Chart.js defaults to match Variant-C"
```

### Task 1.6: Phase 1 verification + tag

- [ ] **Step 1: Smoke test full dashboard**

In browser:
- [ ] Top bar shows brand, USER/PLAN/RANGE, theme/language toggles, F2 hint, UTC time
- [ ] Theme toggle cycles light → dark → system → light
- [ ] Tabs are visible and active state shows terracotta underline
- [ ] Range buttons activate (1 active at a time)
- [ ] Quick-filter input visible
- [ ] KPI strip shows 5 cells, primary cell terracotta
- [ ] Tab content below still renders (in legacy look)
- [ ] F2 still toggles anonymization

- [ ] **Step 2: Tag**

```bash
git tag phase-1-complete
```

---

## Phase 2 — Tab Redesigns (one subagent task per tab)

Each tab task replaces the legacy tab content with Variant-C components. Acceptance criteria for every task:
- Visual match to mockup (refer to `docs/design_handoff_claude_stats_terminal/README.md` and `preview.html`)
- Charts use new theming or are replaced with custom CSS components per design
- Range filter affects tab data
- Quick filter affects tab data where relevant
- F2 anonymization works (project names replaced via `anonName()`, unpredictable text wrapped in `<span class="anon-blur">`)
- Tooltips work
- Mobile layout reasonable at <960px

**Shared components for Phase 2** — implement once, reuse across tabs:

### Task 2.0: Implement shared Variant-C components

**Files:**
- Modify: `templates/dashboard.css` — add component classes
- Modify: `templates/dashboard.js` — helper render functions

- [ ] **Step 1: Add CSS for shared components**

Append to `templates/dashboard.css`:

```css
/* Tab section header */
.vc-tab-h {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 16px 20px 8px;
}
.vc-tab-h-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--fg-3);
}
.vc-tab-h-title b { color: var(--fg); font-weight: 500; }
.vc-tab-h-rule { height: 1px; background: var(--grid); }
.vc-tab-h-meta { font-size: 11px; color: var(--fg-3); }

/* Pane grid */
.vc-pane-grid {
  margin: 0 20px 24px;
  border: 1px solid var(--grid);
  display: grid;
}
.vc-pane-grid.cols-2 { grid-template-columns: 1.6fr 1fr; }
.vc-pane-grid.cols-2-eq { grid-template-columns: 1fr 1fr; }
.vc-pane-grid.cols-3 { grid-template-columns: 1fr 1fr 1fr; }
.vc-pane {
  padding: 16px 18px;
  border-right: 1px solid var(--grid);
}
.vc-pane:last-child { border-right: none; }
.vc-pane h3 {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin: 0 0 12px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.vc-pane h3 .meta { font-size: 10px; color: var(--fg-3); font-weight: normal; text-transform: none; letter-spacing: 0; }

/* Distribution bars */
.vc-distbar { display: flex; flex-direction: column; gap: 10px; }
.vc-distbar-row {
  display: grid;
  grid-template-columns: 90px 1fr 90px;
  gap: 10px;
  font-size: 11px;
  align-items: center;
}
.vc-distbar-name { color: var(--fg); }
.vc-distbar-track {
  height: 12px;
  border: 1px solid var(--grid);
  background: var(--bg);
  position: relative;
}
.vc-distbar-fill {
  height: 100%;
  background: var(--accent);
}
.vc-distbar-fill.s2 { background: var(--fg-2); }
.vc-distbar-fill.s3 { background: var(--fg-3); }
.vc-distbar-val { text-align: right; color: var(--fg-2); font-feature-settings: 'tnum' 1; }

/* Stat rows */
.vc-stat-row {
  display: grid;
  grid-template-columns: 1fr auto;
  padding: 8px 0;
  border-bottom: 1px dashed var(--grid);
  font-size: 12px;
}
.vc-stat-row:last-child { border-bottom: none; }
.vc-stat-row .k { color: var(--fg-3); }
.vc-stat-row .v { color: var(--fg); font-feature-settings: 'tnum' 1; }
.vc-stat-row .v.acc { color: var(--accent); }

/* Tables */
.vc-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
}
.vc-table th {
  font-size: 10px;
  text-transform: uppercase;
  font-weight: 500;
  letter-spacing: 0.1em;
  color: var(--fg-3);
  text-align: left;
  padding: 8px 14px;
  border-bottom: 1px solid var(--grid);
  background: var(--bg);
}
.vc-table th.num { text-align: right; }
.vc-table td {
  font-size: 11px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--grid-2);
}
.vc-table td.num { text-align: right; font-feature-settings: 'tnum' 1; }
.vc-table tr:last-child td { border-bottom: none; }
.vc-table tr:hover td { background: var(--accent-soft); }
.vc-table .idx { width: 32px; color: var(--fg-3); }
.vc-tag {
  display: inline-block;
  border: 1px solid var(--grid);
  padding: 1px 6px;
  font-family: var(--font-mono);
  font-size: 10px;
  margin-left: 6px;
}
.vc-tag.acc { color: var(--accent); border-color: var(--accent); }

/* Anonymization blur */
body.anon-mode .anon-blur {
  filter: blur(4px);
  user-select: none;
}

/* Misc grid (Insights tab) */
.vc-misc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
}
.vc-misc {
  padding: 16px 18px;
  border-right: 1px solid var(--grid);
  border-bottom: 1px solid var(--grid);
}
.vc-misc:nth-child(4n) { border-right: none; }
.vc-misc .v {
  font-size: 22px;
  font-weight: 500;
  font-feature-settings: 'tnum' 1;
}
.vc-misc .v.acc { color: var(--accent); }
.vc-misc .l {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--fg-3);
  margin-top: 4px;
}

/* Responsive */
@media (max-width: 960px) {
  .vc-pane-grid.cols-2, .vc-pane-grid.cols-2-eq, .vc-pane-grid.cols-3 { grid-template-columns: 1fr; }
  .vc-pane { border-right: none; border-bottom: 1px solid var(--grid); }
  .vc-pane:last-child { border-bottom: none; }
  .vc-kpis { grid-template-columns: 1fr 1fr; }
  .vc-kpi:nth-child(odd) { border-right: 1px solid var(--grid); }
  .vc-kpi { border-bottom: 1px solid var(--grid); }
}
```

- [ ] **Step 2: Add JS render helpers**

Append to `templates/dashboard.js`:

```js
function vcSection(title, meta) {
  return `<div class="vc-tab-h">
    <div class="vc-tab-h-title"><b>↳</b> ${title}</div>
    <div class="vc-tab-h-rule"></div>
    <div class="vc-tab-h-meta">${meta || ''}</div>
  </div>`;
}

function vcDistbar(rows, options = {}) {
  const max = Math.max(...rows.map(r => r.value), 1);
  const series = options.series || 1; // 1, 2, or 3
  const seriesClass = series === 2 ? 's2' : (series === 3 ? 's3' : '');
  return '<div class="vc-distbar">' + rows.map(r => `
    <div class="vc-distbar-row">
      <div class="vc-distbar-name">${r.name}</div>
      <div class="vc-distbar-track"><div class="vc-distbar-fill ${seriesClass}" style="width:${(r.value/max*100).toFixed(1)}%"></div></div>
      <div class="vc-distbar-val">${r.label || r.value.toLocaleString('en-US')}</div>
    </div>
  `).join('') + '</div>';
}

function vcStatRows(rows) {
  return rows.map(r => `
    <div class="vc-stat-row">
      <div class="k">${r.k}</div>
      <div class="v ${r.acc ? 'acc' : ''}">${r.v}</div>
    </div>
  `).join('');
}

function vcMisc(items) {
  return '<div class="vc-misc-grid">' + items.map(it => `
    <div class="vc-misc">
      <div class="v ${it.acc ? 'acc' : ''}">${it.v}</div>
      <div class="l">${it.l}</div>
    </div>
  `).join('') + '</div>';
}

// Anon-blur wrapper for unpredictable text
function anonBlur(text) {
  return `<span class="anon-blur">${text}</span>`;
}
```

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.css templates/dashboard.js
git commit -m "feat: add Variant-C shared components (panes, distbars, tables, stat rows)"
```

### Task 2.1 — 2.7: Per-tab redesigns

For each tab, the implementor:
1. Locates the existing tab content container in `templates/dashboard.html`.
2. Replaces its inner markup with Variant-C structure (refer to design handoff for exact components per tab — section "Tab content map").
3. Updates the corresponding render function in `templates/dashboard.js` to populate the new structure.
4. Removes legacy CSS that's no longer needed.
5. Verifies all acceptance criteria.
6. Commits.

Per-tab content references (from `docs/design_handoff_claude_stats_terminal/README.md`):

#### Task 2.1: Cost tab

Sections:
- (a) Cost line chart (Chart.js, restyled, with 7d-MA ghost dataset using `borderDash: [4,2]`)
- (b) Pane grid (cols-2): `by_model` distribution bars + `token_breakdown` stat rows (output, input, cache.read, cache.write, cache.efficiency)
- (c) `model_detail` table: model | API value | calls | output tokens | $/call | share + bar

Acceptance: existing daily cost data drives chart, model aggregation drives distribution bars + table. Stat rows show token totals.

Commit: `feat: redesign Cost tab in Variant-C`

#### Task 2.2: Activity tab

Sections:
- (a) Pane grid (cols-2): 18-week heatmap with legend + `weekday` distribution bars
- (b) Pane grid (cols-2): 24-bar hourly histogram + summary stat rows (peak hour, peak day, active days, avg/day, longest streak, current streak)

Heatmap: aggregate `daily_costs` into 7-row × 18-col matrix. Each cell: `aspect-ratio: 1`, terracotta with opacity = `0.08 + intensity * 0.92`.

Hourly: 24-bar CSS grid, height = `value/max * 100%`, opacity = `0.4 + (value/max) * 0.6`.

Commit: `feat: redesign Activity tab in Variant-C (heatmap + hourly + weekday)`

#### Task 2.3: Projects tab

Single full-width Variant-C table. Columns: idx | name | sessions | msgs | output tokens | size MB | API value (terracotta) | share % + 80×6px bar.

`anonName()` applied to project names when `body.anon-mode` active.

Quick filter narrows rows.

Commit: `feat: redesign Projects tab as Variant-C table`

#### Task 2.4: Sessions tab

Sessions list (`.vc-session`):
- 4-col grid: 90px (when) | 1fr (body) | auto (stats) | auto (cost)
- When: `2026-04-30 14:08`, `--fg-3`
- Body: project name + model tag (line 1), prompt preview (line 2, ellipsis, max-w 600px, sans-serif, `--fg-3`)
- Stats: `<duration>m` + `<count> msg`
- Cost: terracotta, right-aligned

Per-row MD download button (Terminal-style icon button).
Bulk download button preserved at top.
First-prompt wrapped in `<span class="anon-blur">` for anon-mode.

Commit: `feat: redesign Sessions tab as Variant-C list`

#### Task 2.5: Plan tab

Sections:
- (a) `.vc-plan-grid`: 4 cells (Plan, Paid, API equivalent, ROI), 1st and 4th in terracotta
- (b) Cycle progress bar (28px tall, terracotta fill, `data-label` text inside) + cycle stat rows
- (c) **List of all historical billing cycles** as Variant-C table (columns: cycle | start | end | API value | paid | savings | days)
- (d) `plan_comparison` distribution bars: user usage vs Free/Pro/Max5x/Max20x/Team thresholds

Commit: `feat: redesign Plan tab in Variant-C with cycle history`

#### Task 2.6: Insights tab

Sections:
- (a) `.vc-misc-grid` of 8 file/git/agent counts (file ops, git ops, files created, files edited, agents dispatched, etc.)
- (b) `top_tools` distribution bars
- (c) `config` stat rows (version, user, plan, mcp servers, hooks, custom skills, file snapshots, todos)
- (d) Plan-mode-plans table with `anon-blur` on titles
- (e) Storage breakdown (existing feature — preserve as Variant-C pane)
- (f) Telemetry / Performance metrics (existing — preserve as Variant-C pane)

Commit: `feat: redesign Insights tab in Variant-C with extended sections`

#### Task 2.7: Agents tab

Sections:
- (a) `by_type` distribution bars (verifier, general-purpose, output-style-setup, etc.)
- (b) `errors` distribution bars (tool_timeout, parse_error, rate_limit, network) + summary stat rows

Commit: `feat: redesign Agents tab in Variant-C`

### Task 2.8: Phase 2 verification + tag

- [ ] **Step 1: Full dashboard click-through**

For each tab:
- [ ] Visual match to mockup
- [ ] Range filter changes data correctly
- [ ] Quick filter narrows where applicable
- [ ] F2 anon: project names replaced, unpredictable text blurred

- [ ] **Step 2: Remove `* { border-radius: 0 !important; }` debug rule**

Now that all components are individually styled with `border-radius: 0`, the nuclear rule from Task 1.1 can be removed.

- [ ] **Step 3: Tag**

```bash
git tag phase-2-complete
```

---

## Phase 3 — Detail Pages

### Task 3.1: Project detail page redesign

**Files:**
- Modify: `templates/project_detail.html`, `.css`, `.js`

- [ ] **Step 1: Apply same persistent shell pattern (top-bar)**

Use the same `.vc-top` markup but with simpler content (no tabs, no range — those are dashboard-level). Top bar shows: brand, USER, project name, link back to dashboard, theme toggle, UTC time.

- [ ] **Step 2: Restructure content into pane grids**

- Header pane: project name (large), KPI mini-strip (sessions, messages, cost, output tokens)
- Memories pane: stat rows with `anon-blur` on memory content
- Workflow timeline pane: horizontal distribution bar (sessions per day, terracotta intensity)
- Sessions list pane: same as Sessions tab in dashboard

- [ ] **Step 3: Apply Terminal CSS tokens**

Reuse the same `--bg / --panel / --grid / --fg / --accent` tokens. Light + dark via same logic.

- [ ] **Step 4: Verify and commit**

```bash
python3 extract_stats.py
xdg-open public/projects/$(ls public/projects | head -1)
git add templates/project_detail.*
git commit -m "feat: redesign project detail page in Variant-C"
```

### Task 3.2: Session detail page redesign

**Files:**
- Modify: `templates/session_detail.html`, `.css`, `.js`

- [ ] **Step 1: Apply persistent shell**

Top bar with brand, project name, session ID, model tag, theme toggle, UTC time.

- [ ] **Step 2: Restructure**

- Header pane: session metadata (when, project, model, duration, messages, cost) as KPI mini-strip + stat rows
- Chat-replay canvas: container in 1px-grid frame, controls (play/pause/fullscreen) as Terminal buttons
- Messages list: each message as a pane with role tag + content. User content + assistant content + tool input/output wrapped in `<span class="anon-blur">`
- MD download button: Terminal-style at top right

- [ ] **Step 3: Reduce canvas-replay color palette**

Find the existing canvas-replay code (in `dashboard.js` or `session_detail.js` — likely uses many node colors). Reduce to: terracotta (`--accent`) for primary nodes, `--fg-2` for secondary, `--fg-3` for tertiary. Pulse + opacity variation kept for visual interest.

- [ ] **Step 4: Verify and commit**

```bash
python3 extract_stats.py
xdg-open public/sessions/$(ls public/sessions | head -1)
```

Verify: replay starts, scrubber works, MD download works, F2 blurs message content.

```bash
git add templates/session_detail.*
git commit -m "feat: redesign session detail page in Variant-C"
```

### Task 3.3: Phase 3 tag

```bash
git tag phase-3-complete
```

---

## Phase 4 — Polish

### Task 4.1: Anonymization audit

- [ ] **Step 1: Click through every page in anon-mode (F2 on)**

- [ ] All project names show as "Project N"
- [ ] All unpredictable text (memories, plan titles, session prompts, message content) blurred
- [ ] Toast notification looks Terminal-style

- [ ] **Step 2: Fix any unwrapped text**

Wrap any missed text in `<span class="anon-blur">`.

- [ ] **Step 3: Restyle toast notification**

Find the existing `anonNote` div creation in `dashboard.js`. Replace its `style.cssText` to:
```js
note.style.cssText = 'position:fixed;top:12px;right:12px;padding:8px 16px;border:1px solid var(--accent);background:var(--panel);color:var(--accent);font-family:var(--font-mono);font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;';
```

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.js templates/dashboard.css
git commit -m "polish: anonymization audit + Terminal-style toast"
```

### Task 4.2: Mobile breakpoint pass

- [ ] **Step 1: Resize browser to <960px and audit**

- [ ] KPI strip wraps to 2 columns
- [ ] Pane grids collapse to single column with bottom borders instead of right
- [ ] Tabs scroll horizontally if needed
- [ ] Range buttons + filter wrap to own row

- [ ] **Step 2: Fix breakpoint issues**

Add to `templates/dashboard.css` (refine the existing `@media (max-width: 960px)` block):
```css
@media (max-width: 960px) {
  .vc-nav { flex-direction: column; padding: 0; }
  .vc-nav-tabs { overflow-x: auto; padding: 0 12px; }
  .vc-nav-right { padding: 12px; border-top: 1px solid var(--grid); }
  .vc-top-center { display: none; }
}
@media (max-width: 600px) {
  .vc-kpis { grid-template-columns: 1fr; }
  .vc-kpi { border-right: none; border-bottom: 1px solid var(--grid); }
}
```

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.css
git commit -m "polish: mobile breakpoints for Variant-C layout"
```

### Task 4.3: Locale strings finalization (DE)

- [ ] **Step 1: Diff `locales/de.json` vs `locales/en.json`**

```bash
python3 -c "import json; e=json.load(open('locales/en.json')); d=json.load(open('locales/de.json')); from collections import deque; q=deque([('', e)]); paths=[]; missing=[]
while q:
    p,v = q.popleft()
    if isinstance(v, dict):
        for k,w in v.items(): q.append((p+'.'+k if p else k, w))
    else: paths.append(p)
for p in paths:
    cur=d
    for part in p.split('.'):
        if isinstance(cur, dict) and part in cur: cur=cur[part]
        else: missing.append(p); break
print('Missing in de.json:', missing)"
```

- [ ] **Step 2: Add missing DE translations**

For each missing key in `de.json`, add a German translation. Apply pragmatic-bilingual rule: KPI labels and code-tokens (`API EQUIVALENT`, `OUTPUT TOKENS`) stay English; tab names and prose translate.

- [ ] **Step 3: Verify build + commit**

```bash
python3 extract_stats.py
grep -o "__L_[a-z_]*__" public/index.html | head
```

Expected: no remaining `__L_*__` placeholders.

```bash
git add locales/de.json
git commit -m "polish: finalize German locale for Variant-C"
```

### Task 4.4: SESSION_LOG entry + final tag

- [ ] **Step 1: Add SESSION_LOG entry**

Prepend to `SESSION_LOG.md` after the title:
```markdown
## 2026-04-30 — Variant-C "Terminal" Dashboard Redesign
Komplette Umstellung des Dashboards auf den Variant-C-Look: monospace-forward, single-accent terracotta, hairline borders, light + dark mode mit System-Pref + Toggle. Templates aus extract_stats.py extrahiert in templates/, danach Tab-für-Tab redesigned (Cost, Activity, Projects, Sessions, Plan, Insights, Agents). Detail-Seiten (Projects + Sessions) ebenfalls umgestellt. Alle bestehenden Features erhalten: F2-Anonymization (jetzt mit Blur für unvorhersehbare Texte), Schnellfilter, Range-Buttons, MD-Export, Session-Replay (Canvas mit reduzierter Farbpalette).
```

- [ ] **Step 2: Final commit + tag**

```bash
git add SESSION_LOG.md
git commit -m "docs: log Variant-C Terminal redesign in SESSION_LOG"
git tag phase-4-complete
git tag variant-c-v1
```

- [ ] **Step 3: Final verification — build clean and visual smoke**

```bash
rm -rf public/index.html public/projects/*.html public/sessions/*.html
python3 extract_stats.py
xdg-open public/index.html
```

Click through: every tab, every detail page, theme toggle, anon mode, range buttons, quick filter. All must work.

---

## Self-review notes

**Spec coverage:** All 8 user-confirmed decisions covered (scope incl. detail pages, template extraction strategy, range values preserved, filter placement, hybrid charts, theme toggle, pragmatic bilingual, feature preservation). All risks from spec have mitigations referenced in the per-task acceptance criteria.

**Type consistency:** `anonBlur()` is referenced in shared components (Task 2.0) before being defined — but it's defined in the same task. `vcStatRows()`, `vcDistbar()`, `vcMisc()`, `vcSection()` all defined in 2.0 and consumed in 2.1-2.7.

**Placeholder scan:** Tab tasks 2.1-2.7 are intentionally less granular than 2.0 because the design handoff README is the spec for component-level details — referencing it avoids duplicating 300 lines of mockup specs into this plan. Each tab task has explicit acceptance criteria; the implementor refers to the handoff README for exact spacing/sizing.

**Known limitations documented in plan:**
- Language toggle is alert-based (not live-switch) due to static-generation constraint
- Phase 2 tab tasks use design-handoff README as spec for component details rather than re-specifying inline
