# Dashboard "Modern SaaS" Reskin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the claude.stats dashboard (5 tabs + session-detail + project-detail pages) from the current "Variant-C Terminal" look to the approved "Modern SaaS" design from Claude Design — soft shadowed cards, rounded corners, Manrope sans type, a switchable accent color, the Insights mega-tab restructured into a numbered sub-nav, and dense tables that collapse to stacked cards on mobile.

**Architecture:** The design is purely a re-skin: the data layer (`extract_stats.py`) and all DOM ids / render functions stay intact. We rewrite the CSS token layer and component styles, swap fonts, fix chart theming to read the new tokens, add one behavioral change (Insights sub-nav), and add mobile table-to-card behavior. The dashboard's design tokens live in a `.vc`-scoped block that is **duplicated** across three CSS files (`dashboard.css`, `session_detail.css`, `project_detail.css`); each is inlined into its page by `extract_stats.py`. We keep that pattern and update all three token blocks identically.

**Tech Stack:** Vanilla HTML/CSS/JS, Chart.js 4.4.7, Python build step (`extract_stats.py`), pytest (154 tests), Google Fonts (Manrope + JetBrains Mono).

**Design source of truth (read before implementing):** The exported Claude Design bundle is staged in the repo at `docs/design-handoff/`. The two files that define the look are:
- `docs/design-handoff/css/base.css` — structure/layout + the component class contract (KPI, panel, table, subnav, heatmap, etc.) driven entirely by CSS custom props.
- `docs/design-handoff/css/saas.css` — the "Modern SaaS" skin: the **exact token values**, accent/density variants, and the new components (progress bar, limit timeline, session badges, mobile table-to-card).
The mock markup is `docs/design-handoff/claude.stats-SaaS.html`. Note the mock uses its own class names (`.appwrap`, `.panel`, `.kpi`, `.mainnav .tab`); our job is to port the **visual output** onto the real dashboard's existing classes (`.vc`, `.chart-box`, `.vc-kpi`, `.vc-tab`, …), NOT to adopt the mock's DOM.

---

## Verification model (this is a visual reskin, not TDD)

There are no unit tests for visuals. Each task is verified by the combination below; a task's final steps spell out which apply.

- **JS syntax preflight:** `node -c templates/dashboard.js` (and `session_detail.js` / `project_detail.js` when touched). Must print nothing (exit 0).
- **Data tests stay green:** `python3 -m pytest tests/ -q` → `154 passed`. (We never touch extraction logic; this is a regression guard.)
- **Rebuild:** `python3 extract_stats.py` must complete without traceback and regenerate `public/index.html`.
- **Headless smoke test:** Task 1 creates `tools/smoke_shot.mjs` (Playwright/Chromium from the local cache) that loads a built page and screenshots each tab in light + dark + one mobile width. Re-run it after visual tasks and view the PNGs.

**Build/preview commands (memorize):**
```bash
python3 extract_stats.py                 # rebuild public/ from templates/
node tools/smoke_shot.mjs                 # screenshot tabs → /tmp/smoke/*.png (after Task 1)
python3 -m pytest tests/ -q               # 154 passed
```

**Do NOT edit `public/index.html`, `public/sessions/*.html`, or `public/projects/*.html` directly — they are generated.** Edit only `templates/*` and `locales/*`, then rebuild.

---

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `templates/dashboard.html` | Main dashboard markup, `<head>` font links, Insights sub-nav markup, table `data-label`s | Modify |
| `templates/dashboard.css` | Token block + all dashboard component styles | Heavy modify |
| `templates/dashboard.js` | Chart theming, Insights sub-nav behavior, `data-label`s in JS-rendered rows | Modify |
| `templates/session_detail.{html,css,js}` | Session chat-detail page | Modify (tokens + components) |
| `templates/project_detail.{html,css,js}` | Project detail page | Modify (tokens + components) |
| `templates/custom.css.example` | Documented accent presets (indigo/emerald) | Modify |
| `locales/en.json`, `locales/de.json` | New `__L_*__` strings for the Insights sub-nav labels | Modify |
| `tools/smoke_shot.mjs` | Headless screenshot smoke-test helper | Create |
| `docs/design-handoff/**` | Design reference bundle | Already staged (read-only) |

---

## SHARED REFERENCE — the new token values (used by Tasks 2, 19, 20)

These come verbatim from `docs/design-handoff/css/saas.css` lines 8-65, re-expressed against our `--vc-*` names. The mapping from SaaS token → our token:

| SaaS (`--*`) | Our (`--vc-*`) | Light | Dark |
|---|---|---|---|
| `--bg` | `--vc-bg` | `#f5f6f8` | `#0e1014` |
| `--panel` | `--vc-panel` | `#ffffff` | `#181b21` |
| `--fg` | `--vc-fg` | `#14161c` | `#eef0f4` |
| `--muted` | `--vc-fg-2` | `#5b6473` | `#a8afbb` |
| `--faint` | `--vc-fg-3` | `#99a1af` | `#6b7380` |
| `--line` | `--vc-grid` / `--vc-grid-2` | `#e7e9ee` | `#262b33` |
| `--accent` | `--vc-accent` | `#c2562f` | `#e27a51` |
| `--accent-soft` | `--vc-accent-soft` | `rgba(194,86,47,.10)` | `rgba(226,122,81,.16)` |
| `--pos` | `--vc-pos` (new) | `#1f9d63` | `#34c77f` |
| `--pos-soft` | `--vc-pos-soft` (new) | `rgba(31,157,99,.12)` | `rgba(52,199,127,.16)` |
| `--neg` | `--vc-neg` (new) | `#d24b3e` | `#f0786b` |
| `--neg-soft` | `--vc-neg-soft` (new) | `rgba(210,75,62,.12)` | `rgba(240,120,107,.16)` |

New non-color tokens (theme-independent):
```css
--vc-radius: 14px; --vc-radius-sm: 10px; --vc-radius-pill: 999px; --vc-radius-ctl: 9px;
--vc-shadow: 0 1px 2px rgba(20,22,28,.04), 0 8px 20px -12px rgba(20,22,28,.14);
--vc-font-sans: 'Manrope', system-ui, sans-serif;
--vc-font-mono: 'JetBrains Mono', ui-monospace, monospace;
```
Dark shadow override: `--vc-shadow: 0 1px 2px rgba(0,0,0,.30), 0 10px 26px -14px rgba(0,0,0,.55);`

**Accent is a single source:** keep `--vc-accent` (+ `--vc-accent-soft`) as the only accent definition so `custom.css` can recolor with one rule (Task 18). The categorical chart palette stays earth-toned per `docs/design-handoff/js/charts.js:20` (`CAT_PALETTE`) so it does not clash when accent is swapped.

---

## Task 1: Headless smoke-test helper + baseline capture

**Files:**
- Create: `tools/smoke_shot.mjs`

- [ ] **Step 1: Write the smoke-test script**

```js
// tools/smoke_shot.mjs — screenshot each dashboard tab in light/dark + mobile.
// Uses the Chromium already cached by Playwright. Run: node tools/smoke_shot.mjs
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const OUT = '/tmp/smoke';
mkdirSync(OUT, { recursive: true });
const url = pathToFileURL(resolve('public/index.html')).href;
const tabs = ['costs', 'plan', 'activity', 'sessions', 'insights'];

const browser = await chromium.launch();
for (const [theme, w, h, tag] of [['light', 1440, 1000, 'desk'], ['dark', 1440, 1000, 'desk'], ['light', 420, 900, 'mob']]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.evaluate(t => {
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    document.documentElement.classList.add('theme-' + t);
  }, theme);
  for (const tab of tabs) {
    await page.evaluate(name => window.activateTabByName && window.activateTabByName(name, false), tab);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/${tag}-${theme}-${tab}.png`, fullPage: tag !== 'mob' });
  }
  await page.close();
}
await browser.close();
console.log('screenshots in', OUT);
```

- [ ] **Step 2: Confirm Playwright Chromium is available**

Run: `node -e "import('playwright').then(p=>p.chromium.launch()).then(b=>{console.log('ok');return b.close()}).catch(e=>{console.error('NO CHROMIUM',e.message);process.exit(1)})"`
Expected: `ok`. If it fails with a missing-browser error, run `npx playwright install chromium` first (note it in the task output; do not add a package.json).

- [ ] **Step 3: Build current templates and capture the BEFORE baseline**

Run: `python3 extract_stats.py && node tools/smoke_shot.mjs && cp -r /tmp/smoke /tmp/smoke_before`
Expected: `screenshots in /tmp/smoke`. Keep `/tmp/smoke_before` to compare against after the reskin.

- [ ] **Step 4: Commit**

```bash
git add tools/smoke_shot.mjs
git commit -m "tools: headless screenshot smoke-test for dashboard tabs"
```

---

## Task 2: New token system + fonts (dashboard.css + dashboard.html head)

**Files:**
- Modify: `templates/dashboard.css:1-157` (the `.vc` token block, dark overrides, legacy remap, and the `border-radius:0` rule at line 68)
- Modify: `templates/dashboard.html:12-15` (add font `<link>`s in `<head>`)

- [ ] **Step 1: Add the Google Fonts links** in `templates/dashboard.html` `<head>` (right after the Chart.js adapter script on line 13, before `<!-- STYLES -->`):

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Replace the `.vc` light token block** (`templates/dashboard.css:9-32`) using the SHARED REFERENCE values above. Add the new radius/shadow/pos/neg tokens. Set `--vc-font-sans: 'Manrope',…` and `--vc-font-mono: 'JetBrains Mono',…`, and set the base `.vc { font-family: var(--vc-font-sans); }` (the design is sans-first; mono is only for tabular figures where already applied). Keep the 8-step `--vc-fs-*` scale.

- [ ] **Step 3: Replace the dark token values** in both the `@media (prefers-color-scheme: dark) html:not(.theme-light) .vc` block (`:33-45`) and the `html.theme-dark .vc` block (`:46-56`) with the dark column from the SHARED REFERENCE (including the dark `--vc-shadow`). Update `html.theme-light .vc` (`:57-67`) to the light values.

- [ ] **Step 4: Remove the hard-rectangle rule.** Change `templates/dashboard.css:68` from `.vc *, .vc *::before, .vc *::after { border-radius: 0 !important; box-sizing: border-box; }` to keep `box-sizing` only: `.vc *, .vc *::before, .vc *::after { box-sizing: border-box; }`. (Rounded corners are core to the SaaS look; the `!important` blanket must go.)

- [ ] **Step 5: Update the legacy var remap** (`body.vc-page` blocks at `:87-156`) so `--accent`/`--bg`/`--bg2`/`--border`/`--text`/`--text2` track the new palette (light + dark + prefers-dark). Map: `--bg`→`#f5f6f8`/`#0e1014`, `--bg2`→`#ffffff`/`#181b21`, `--border`→`#e7e9ee`/`#262b33`, `--text`→`#14161c`/`#eef0f4`, `--text2`→`#5b6473`/`#a8afbb`, `--accent`→`var(--vc-accent)`, `--green`→`var(--vc-pos)`, `--red`→`var(--vc-neg)`. This keeps innerHTML-inlined colors and Chart.js legacy lookups coherent.

- [ ] **Step 6: Verify syntax + build + render**

```bash
node -c templates/dashboard.js   # untouched, sanity
python3 extract_stats.py
node tools/smoke_shot.mjs
```
Expected: build OK; screenshots show the new background/panel colors and that corners are no longer force-squared. (Components are not yet restyled — this step only proves tokens flow.)

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.css templates/dashboard.html
git commit -m "feat(dashboard): SaaS token system + Manrope/JetBrains Mono fonts"
```

---

## Task 3: Cards, panels & section headers

**Files:**
- Modify: `templates/dashboard.css` — `.chart-box`, `.chart-grid`, `.masonry-section` (in the `:327-644` legacy-override range), `.vc-tab-h*` and `.vc-sect-h*` (`:647-856`).

Port these from `docs/design-handoff/css/base.css` `.panel` (`:175-189`) and `.subsection-title` (`:247-252`), plus `saas.css` panel tokens (`:28-35`).

- [ ] **Step 1: Restyle panels.** Give `.vc .chart-box`, `.vc .vc-pane`, and `.vc .stat-card` (and `.masonry-section > *` cards): `background: var(--vc-panel); border: 1px solid var(--vc-grid); border-radius: var(--vc-radius); box-shadow: var(--vc-shadow); padding: 20px 22px 22px;`. Remove any prior `border-radius:0`/hard-edge declarations in these blocks.

- [ ] **Step 2: Panel titles (`h3` inside cards) + `.vc-tab-h` + `.vc-sect-h`.** Use `--vc-font-sans`, weight 700, sentence case (drop forced `text-transform:uppercase` on the big titles; keep uppercase only for small label/meta text). `.vc-tab-h-title` → 19px/700/-0.01em; `.vc-sect-h-title` → 17px/700. Hairlines (`.vc-tab-h-rule`, `.vc-sect-h-rule`) become `1px solid var(--vc-grid)`.

- [ ] **Step 3: Grid gaps.** `.chart-grid`/`.masonry-section` gap → 18px to match `--panel-gap`.

- [ ] **Step 4: Verify + commit**

```bash
python3 extract_stats.py && node tools/smoke_shot.mjs
git add templates/dashboard.css && git commit -m "feat(dashboard): SaaS cards, panels, section headers"
```
Expected: panels render as white rounded cards with soft shadow in light, dark equivalents in dark.

---

## Task 4: Top bar

**Files:**
- Modify: `templates/dashboard.css:164-225` (`.vc-top*` blocks)
- Modify: `templates/dashboard.html:42-50` (theme-toggle button markup → pill)

Reference: `docs/design-handoff/css/base.css:49-71` (`.topbar`) + `saas.css:91-99` (`.theme-toggle` pill).

- [ ] **Step 1: Top bar container.** `.vc-top-inner` becomes a flex row, `border-bottom: 1px solid var(--vc-grid)`, sans font, 11.5px muted text. Brand mark `.vc-brand-mark` → `width:9px;height:9px;background:var(--vc-accent);border-radius:var(--vc-radius-pill)`. Brand name weight 700, letter-spacing .08em. `.vc-k` uppercase 10px faint; `.vc-v` `--vc-fg` with `font-variant-numeric: tabular-nums`.

- [ ] **Step 2: Theme toggle pill.** Restyle `#vcThemeToggle` (`.vc-icon-btn`) as the SaaS pill: `background:var(--vc-panel);border:1px solid var(--vc-grid);border-radius:var(--vc-radius-pill);padding:5px 11px;color:var(--vc-fg-2)`. Keep the existing `&#9737;`/emoji swap logic in JS (`applyVcTheme`) untouched.

- [ ] **Step 3: Hide-empty checkbox + F2 hint** styled with `--vc-accent` box border (port `.chk .box` from base.css:69-71, but with `border-radius: var(--vc-radius-sm)`).

- [ ] **Step 4: Verify + commit** (`python3 extract_stats.py && node tools/smoke_shot.mjs`; commit `templates/dashboard.css templates/dashboard.html` → `feat(dashboard): SaaS top bar`).

---

## Task 5: Primary nav (pill tabs + range + filter)

**Files:**
- Modify: `templates/dashboard.css:857-939` (`.vc-nav*`, `.vc-tab`, `.vc-range*`, `.vc-filter*`)

Reference: `base.css:73-111` (`.mainnav .tab`, `.rangesel`, `.filterbox`) + `saas.css:37-44`, `:82`.

- [ ] **Step 1: Tabs as pills.** `.vc-tab`: sans, 12px, letter-spacing .06em, padding 14px 22px, `border-radius: var(--vc-radius-ctl)`, `color: var(--vc-fg-2)`; hover `background: var(--vc-accent-soft); color: var(--vc-fg)`. `.vc-tab.active` → `background: var(--vc-accent); color:#fff`.

- [ ] **Step 2: Range selector + filter box.** `.vc-range` and `.vc-filter` get `1px solid var(--vc-grid)` borders, `border-radius: var(--vc-radius-ctl)`, `background: var(--vc-panel)`. `.vc-range-btn.active` → accent bg, white text. `.vc-filter .vc-filter-prompt`/`.chev` → `color: var(--vc-accent)`.

- [ ] **Step 3: Nav container** `.vc-nav-inner` → `border-bottom: 1px solid var(--vc-grid)`; remove old hard underline-tab styling.

- [ ] **Step 4: Verify + commit** (build + smoke; commit → `feat(dashboard): SaaS pill nav, range + filter controls`).

---

## Task 6: KPI strip

**Files:**
- Modify: `templates/dashboard.css:227-296` (`.vc-kpis*`, `.vc-kpi*`)

Reference: `base.css:128-157` (`.kpis`, `.kpi`, `.kpi.hero`) + `saas.css:23-27`.

- [ ] **Step 1: Strip layout.** `.vc-kpis` → `display:grid; grid-template-columns: 1.25fr 1fr 1fr 1fr 1fr; gap:14px`. Drop the band border/`overflow` that made it a single ruled strip.

- [ ] **Step 2: KPI cards.** `.vc-kpi` → `background:var(--vc-panel); border:1px solid var(--vc-grid); border-radius:var(--vc-radius); box-shadow:var(--vc-shadow); padding:18px 20px 20px; display:flex; flex-direction:column; gap:8px`. `.vc-kpi-label` uppercase 10.5px muted. `.vc-kpi-value` → 30px/700/-0.02em tabular. `.vc-kpi-primary .vc-kpi-value` → 36px, `color: var(--vc-accent)`. `.vc-kpi-delta` → pill chip: `background:var(--vc-pos-soft); color:var(--vc-pos); border-radius:var(--vc-radius-pill); padding:2px 7px`.

- [ ] **Step 3: Verify + commit** (build + smoke; commit → `feat(dashboard): SaaS KPI cards`).

---

## Task 7: Data tables (+ sortable affordance)

**Files:**
- Modify: `templates/dashboard.css` — `.data-table` rules within `:327-644` and the legacy `.data-table` at `:941-1169`.

Reference: `base.css:195-209` (`table.data`) + `saas.css:172-185` (badges), `:211-214` (sortable).

- [ ] **Step 1: Base table.** `.vc table.data-table` / `.vc .data-table`: sans, tabular-nums, 12.5px; `th` uppercase 10px muted, `border-bottom:1px solid var(--vc-grid)`, sticky top with `background:var(--vc-panel)`; `td` `padding:10px 14px`, `border-bottom:1px solid var(--vc-grid)`; first column left-aligned, numeric columns right-aligned (the `.num` class already marks them). Row hover → `background: var(--vc-accent-soft)`.

- [ ] **Step 2: Badges/affordances.** Add `.badge-model` / `.tag-source` / `.badge-ctx` / `.cell-link` / `.chat-btn` styles from `saas.css:172-185` (model badge = accent-soft pill, source tag = muted pill, ctx badge = violet pill for the 1M-context marker). Add `th.sortable{cursor:pointer}` + `.arr` opacity per `saas.css:211-214`. The existing 1M-context flag and sortable headers keep their JS; this only restyles them.

- [ ] **Step 3: Verify + commit** (build + smoke on costs/activity/sessions tabs which have the densest tables; commit → `feat(dashboard): SaaS data tables + badges`).

---

## Task 8: Costs tab specifics (idle banner, token-type, model table notice)

**Files:**
- Modify: `templates/dashboard.css` (add `.vc-idle-aggregate` banner styling near `:941-1169`)
- Modify: `templates/dashboard.js:862-881` (`renderIdleGapAggregateCard`) only if inline styles hardcode old colors

Reference: `base.css:159-168` (`.banner`).

- [ ] **Step 1: Idle-gap banner.** Style `#idleGapAggregateCard.vc-idle-aggregate` as the SaaS banner: `padding:12px 16px; border:1px solid var(--vc-grid); border-radius:var(--vc-radius-sm); background:var(--vc-accent-soft); font:var(--vc-font-mono)`-numerics; the `.vc-k` tag uppercase faint. If `renderIdleGapAggregateCard` inlines `var(--accent)`/hex, leave the var() refs (they now resolve to the new palette via the remap) — only replace any literal hex.

- [ ] **Step 2: Verify + commit** (build + smoke costs tab; commit → `feat(dashboard): SaaS idle-gap banner`).

---

## Task 9: Plan & Billing specifics (progress bar, period stats, limit timeline, plan rec)

**Files:**
- Modify: `templates/dashboard.css` (`.plan-highlight`, `.billing-progress`, `.vc-limits-section`, `.lim-row`, `.plan-rec-table` in `:327-644` and `:941-1169`)
- Modify: `templates/dashboard.js:1532-1874` (`renderPlan`, `renderLimitsEventTimeline`, `renderPlanRecommendation`) — replace literal hex in inlined HTML with token vars; structural HTML unchanged.

Reference: `saas.css:104-151` (progress bar, period-stats, currency toggle, limit timeline, rec note, beta-tag).

- [ ] **Step 1: Billing progress bar.** `.billing-progress` / `#billingProgress .fill`: rounded pill track `background: color-mix(in srgb, var(--vc-fg-2) 12%, transparent)`, `.fill` accent bg, white 700 label, `border-radius: var(--vc-radius-pill)`, height 26px.

- [ ] **Step 2: Limit events timeline.** Port `.le-row`/`.le-track`/`.le-ev.explicit`(neg)/`.le-ev.fp`(muted)/`.le-legend`/`.le-count` from `saas.css:127-141`. Map onto the markup `renderLimitsEventTimeline` produces (check the existing class names it emits; if they differ, add equivalent rules keyed to the emitted classes rather than renaming in JS).

- [ ] **Step 3: Plan recommendation + currency toggle + beta tag.** `.rec-note` accent-soft callout; `.beta-tag` accent-soft pill; currency toggle (`#vcPlanMeta` buttons) as a bordered segmented control with accent `.on`.

- [ ] **Step 4: Replace literal hex** in `renderPlan`/`renderLimitsEventTimeline`/`renderPlanRecommendation` inlined styles with `var(--vc-*)` equivalents (e.g. status greens/reds → `var(--vc-pos)`/`var(--vc-neg)`).

- [ ] **Step 5: Verify + commit** (`node -c templates/dashboard.js && python3 extract_stats.py && node tools/smoke_shot.mjs`; smoke the plan tab; commit → `feat(dashboard): SaaS plan & billing, limit timeline`).

---

## Task 10: Activity tab — heatmap reskin

**Files:**
- Modify: `templates/dashboard.css:298-325` (heatmap polish block) + heatmap rules in `:941-1169`
- Modify: `templates/dashboard.js:1144-1198` (`renderHeatmap`) — cells currently use `rgba(accent, opacity)` inline; switch to rounded cells with discrete accent levels OR keep opacity gradient but add `border-radius`.

Reference: `saas.css:153-170` (`.hm-cell`, levels `l0..l4` via `color-mix`).

- [ ] **Step 1: Rounded cells.** Add `border-radius:3px` to heatmap cells. The current renderer computes a continuous `rgba(accentRgb, opacity)`; keep that (it already tracks accent) but ensure the cell element gets `border-radius:3px` and the empty level uses `color-mix(in srgb, var(--vc-fg-2) 9%, transparent)` instead of a hard grey. Legend swatches (`.vc-heatmap-legend .cell`) get matching radius.

- [ ] **Step 2: Verify + commit** (build + smoke activity tab; commit → `feat(dashboard): SaaS activity heatmap`).

---

## Task 11: Sessions tab — toolbar, filter chips, pagination

**Files:**
- Modify: `templates/dashboard.css` (add `.toolbar`, `.btn`, `.select`, `.searchbox`, `.fchip`, `.list-meta`, `.pager`) — these classes may be emitted by `templates/components/session_filters.*` and `session_table.*`; check those component files and key the styles to the actual emitted classes.
- Read first: `templates/components/session_filters.css`, `session_table.css`, and their `.js` to learn the real class names; restyle in `dashboard.css` (which is inlined alongside the components) or in the component CSS files.

Reference: `saas.css:187-225`.

- [ ] **Step 1: Read the session components** to identify the real toolbar/filter/pagination classes (`.session-filters`, export buttons `.bulk-download-btn`, the mounted table, any pager).

- [ ] **Step 2: Restyle controls.** Buttons → `.btn` style (38px tall, bordered, `--vc-radius-ctl`, hover accent-soft; `.primary` = accent bg). Selects/search → bordered control. Filter chips → accent-soft pills (`.fchip`). Pagination buttons → bordered, `.on` accent.

- [ ] **Step 3: Verify + commit** (`node -c` any touched component JS + build + smoke sessions tab; commit → `feat(dashboard): SaaS sessions toolbar & filters`).

---

## Task 12: Insights tab — numbered sub-nav restructure

**Files:**
- Modify: `templates/dashboard.html:266-392` (Insights tab: insert a `.vc-subnav` before the first `.vc-sect-h`; wrap each existing `.vc-sect-h`+`.masonry-section` pair in a `<div class="vc-subsection" data-sub="…">`)
- Modify: `templates/dashboard.css` (add `.vc-subnav`/`.vc-subsection` styles)
- Modify: `templates/dashboard.js` (add sub-nav switching behavior + ensure charts in a newly-shown subsection get built/resized)
- Modify: `locales/en.json`, `locales/de.json` (sub-nav button labels)

Reference: `base.css:225-252` (`.subnav`, `.subsection`) + `saas.css:84-89` + mock markup `claude.stats-SaaS.html:215-329`.

The 7 sections (in current DOM order) and their `data-sub` keys: `cache` (Cache & Tokens), `tools` (Tools & Plugins), `workflows` (Workflows), `storage` (Storage & Files), `environment` (Environment), `agents` (Agents), `errors` (Errors & Reliability).

- [ ] **Step 1: Add sub-nav markup.** Immediately after the `#tab-insights` `.vc-tab-h` (there is none today — the tab starts directly with the first `.vc-sect-h` at `:267`), insert:

```html
<nav class="vc-subnav" id="insightsSubnav">
  <button data-sub="cache" class="on"><span class="ic">01</span>__L_insights_sect_cache_tokens__</button>
  <button data-sub="tools"><span class="ic">02</span>__L_insights_sect_tools_plugins__</button>
  <button data-sub="workflows"><span class="ic">03</span>__L_insights_sect_workflows__</button>
  <button data-sub="storage"><span class="ic">04</span>__L_insights_sect_storage_files__</button>
  <button data-sub="environment"><span class="ic">05</span>__L_insights_sect_environment__</button>
  <button data-sub="agents"><span class="ic">06</span>__L_insights_subnav_agents__</button>
  <button data-sub="errors"><span class="ic">07</span>__L_insights_subnav_errors__</button>
</nav>
```

- [ ] **Step 2: Wrap each section.** Wrap each existing `.vc-sect-h` + following content block(s) in `<div class="vc-subsection" data-sub="KEY">…</div>` with the matching key, `hidden` on all except `cache`. Keep all inner ids/markup byte-for-byte so render functions still find their targets. (The Agents and Errors sections currently use literal English titles in the HTML — replace those two `.vc-sect-h-title` texts with `__L_insights_subnav_agents__` / `__L_insights_subnav_errors__` too, for parity.)

- [ ] **Step 3: Add the two new locale keys** to `locales/en.json` and `locales/de.json` under `insights`: `subnav_agents` ("Agents" / "Agenten") and `subnav_errors` ("Errors & Reliability" / "Fehler & Zuverlässigkeit"). Verify both files stay valid JSON (`python3 -c "import json;json.load(open('locales/en.json'));json.load(open('locales/de.json'))"`).

- [ ] **Step 4: Sub-nav behavior in dashboard.js.** Add an initializer (call it from the existing DOM-ready/IIFE near the tab wiring at `:2388-2409`):

```js
function initInsightsSubnav() {
  const nav = document.getElementById('insightsSubnav');
  if (!nav) return;
  const sections = Array.from(document.querySelectorAll('#tab-insights .vc-subsection'));
  nav.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-sub]');
    if (!btn) return;
    const key = btn.dataset.sub;
    nav.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === btn));
    sections.forEach(s => { s.hidden = s.dataset.sub !== key; });
    // charts inside a previously-hidden section measured 0px; resize them now.
    if (window.Chart) Object.values(Chart.instances || {}).forEach(c => { try { c.resize(); } catch (_) {} });
  });
}
```

Call `initInsightsSubnav()` once after charts are built. Confirm `activateTabByName` is exposed on `window` (the smoke test calls it); if it is not already global, add `window.activateTabByName = activateTabByName;` near its definition (`:832`).

- [ ] **Step 5: Sub-nav styling.** `.vc-subnav` → bordered, shadowed pill group (`background:var(--vc-panel); border:1px solid var(--vc-grid); border-radius:var(--vc-radius); box-shadow:var(--vc-shadow); padding:5px; display:flex; gap:6px; flex-wrap:wrap; width:fit-content; max-width:100%`). Buttons: sans 11.5px uppercase, `border-radius:var(--vc-radius-ctl-sm,8px)`, muted; `.on` → accent bg white; `.ic` numeric faint. `.vc-subsection[hidden]{display:none}`.

- [ ] **Step 6: Verify.**

```bash
node -c templates/dashboard.js
python3 -c "import json;json.load(open('locales/en.json'));json.load(open('locales/de.json'))"
python3 extract_stats.py && node tools/smoke_shot.mjs
```
Expected: Insights tab shows one section at a time; clicking sub-nav buttons swaps sections and charts render at full width (not 0px). Smoke `insights` screenshot shows the Cache section only.

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.html templates/dashboard.css templates/dashboard.js locales/en.json locales/de.json
git commit -m "feat(dashboard): restructure Insights into numbered sub-nav"
```

---

## Task 13: Chart theming — read new tokens, kill hardcoded slate/hex

**Files:**
- Modify: `templates/dashboard.js:175-281` (`setupVcChartDefaults`) and the chart builders that hardcode colors: `renderWriteCategoriesChart` (`:666-702`), `renderToolTokenChart` (`:704-747`), `renderToolUsageChart` (`:633-647`), `chartStorage` (`:1889`), `errorRateChart` (`:2064`), agent/error charts in `renderAgentsTab` (`:2077-2197`).

Goal: charts must re-theme on light/dark + accent change and stop using the legacy slate palette (`#94a3b8`, `#10b981`, `#6366f1`, …) that clashes with the SaaS look.

- [ ] **Step 1: Confirm `setupVcChartDefaults` reads the (now updated) `--vc-*` tokens** for font, `--vc-fg-3` (ticks), `--vc-grid`/`--vc-grid-2` (gridlines), `--vc-panel` (arc borders). Update `Chart.defaults.font.family` to `'Manrope'` (read from `--vc-font-sans`, first family, quotes stripped — mirror `fam()` in `docs/design-handoff/js/charts.js:59`). Keep `window.__vcFg2/__vcFg3/__vcGrid2` exposure.

- [ ] **Step 2: Introduce a single categorical palette** matching the design (`docs/design-handoff/js/charts.js:20`): add near the existing palette maps (`:71`):

```js
const _VC_CAT = ['#c4623f', '#7aa589', '#cda43f', '#a8442a', '#6f8f9e',
  '#9b7bb0', '#4f7a5f', '#d98b6a', '#8a8175', '#b8966a'];
```

- [ ] **Step 3: Replace hardcoded doughnut/bar palettes** in `renderWriteCategoriesChart`, `renderToolTokenChart`, `chartStorage`, `errorByCategoryChart`, `errorByToolChart` with `_VC_CAT` (cycled) or `vcModelColor`/accent where semantically appropriate. Replace literal `#ef4444` error reds with `var(--vc-neg)` read via `getComputedStyle` (use the existing `_vcAccentRgb`-style helper or `cvar`-equivalent; if none exists, add a small `vcVar(name, fallback)` reader). Tool-usage `hsl(...)` loop (`:636`) → `_VC_CAT`.

- [ ] **Step 4: Verify re-theme.** Build, then in the smoke run confirm dark-mode chart screenshots have readable ticks/legends (no invisible mid-slate on dark) and category colors are earth-toned. `node -c templates/dashboard.js` first.

- [ ] **Step 5: Commit** (`feat(dashboard): chart theming reads SaaS tokens, drop hardcoded slate palette`).

---

## Task 14: Mobile — dense tables collapse to stacked cards

**Files:**
- Modify: `templates/dashboard.css` (add the `@media (max-width:760px)` responsive-table block + general mobile grid rules)
- Modify: `templates/dashboard.html` — add `class="responsive"` to the static tables (`#modelTable`, `#projectTable`, `#planTable`, `#pluginTable`, `#plansTable`) and `data-label` is added per-cell in JS (next step)
- Modify: `templates/dashboard.js` — in the row-builder render functions (`renderProjectTable` `:1251-1291`, model table in `renderCosts`, plan table in `renderPlan`, plugin/plans tables in `renderInsights`) add `data-label="<column>"` to each `<td>`, and mark the first/identifying cell `class="primary"`.

Reference: `saas.css:227-249` (the responsive table-to-card block) + `base.css:283-297` (kpi/grid breakpoints).

- [ ] **Step 1: Add the responsive CSS** (port `saas.css:227-249` verbatim, keying `table.responsive` and `--vc-*` tokens): under 760px, `thead{display:none}`, rows become bordered shadowed cards, each `td` becomes a flex row showing `td::before{content:attr(data-label)}` as the label. `.primary` cell gets accent-tinted emphasis.

- [ ] **Step 2: Add general mobile rules** (port `base.css:283-297`): `≤1100px` collapse 2-col grids to 1 and make `.vc-kpi-primary` span full width; `≤720px` kpis 2-col, tabs flex; `≤480px` kpis 1-col. Apply to `.chart-grid`, `.masonry-section .grid`, `.vc-kpis`.

- [ ] **Step 3: Add `class="responsive"` to the static tables** in `dashboard.html` and add `data-label`/`class="primary"` in the JS row builders. Each `data-label` must match its column header text (English from the locale is fine; the label is cosmetic).

- [ ] **Step 4: Verify.** `node -c templates/dashboard.js && python3 extract_stats.py && node tools/smoke_shot.mjs`. The `mob-light-*` screenshots must show tables as stacked labelled cards, KPIs single/double column, no horizontal overflow.

- [ ] **Step 5: Commit** (`feat(dashboard): mobile table-to-card + responsive grids`).

---

## Task 15: Accent color via custom.css

**Files:**
- Modify: `templates/custom.css.example`
- (No JS — accent is a pure CSS var swap; `--vc-accent`/`--vc-accent-soft` are the single source set in Task 2.)

- [ ] **Step 1: Document accent presets.** Append to `custom.css.example` two commented presets that recolor light + dark in one block each, per the documented theme-scoped pattern:

```css
/* === Accent: Indigo (uncomment to apply) ===
html.theme-light .vc, html.theme-light body.vc-page { --vc-accent:#4f46e5; --vc-accent-soft:rgba(79,70,229,.10); --accent:#4f46e5; }
html.theme-dark  .vc, html.theme-dark  body.vc-page { --vc-accent:#818cf8; --vc-accent-soft:rgba(129,140,248,.18); --accent:#818cf8; }
*/
/* === Accent: Emerald ===
html.theme-light .vc, html.theme-light body.vc-page { --vc-accent:#0e9f6e; --vc-accent-soft:rgba(14,159,110,.10); --accent:#0e9f6e; }
html.theme-dark  .vc, html.theme-dark  body.vc-page { --vc-accent:#34d399; --vc-accent-soft:rgba(52,211,153,.18); --accent:#34d399; }
*/
```

- [ ] **Step 2: Verify** by temporarily pasting the Indigo block into `public/custom.css`, rebuild not required (custom.css is loaded live), re-run smoke → accent turns indigo across nav/KPIs/charts; then revert `public/custom.css`.

- [ ] **Step 3: Commit** (`docs(theming): document indigo/emerald accent presets`).

---

## Task 16: Session-detail page reskin

**Files:**
- Modify: `templates/session_detail.css` — token block (`:1-89`, identical structure to dashboard) + components (`:91-213`): header, stats-bar, model-badge, flow viz, chat transcript (`.message`, `.message-role`), sidebar, markers.
- Modify: `templates/session_detail.html` `<head>` — add the same Google Fonts links.
- Modify: `templates/session_detail.js` only to replace literal hex with token vars if any.

- [ ] **Step 1: Sync the token block.** Replace `session_detail.css:1-89` `.vc` light/dark/legacy-remap with the SHARED REFERENCE values (same as dashboard Task 2), including radius/shadow/pos/neg tokens and removing the `border-radius:0 !important` rule (`:44`). Keep the session-only extra tokens (`--vc-flow-bg`, `--vc-btn-flow-bg`, `--vc-node-icon`, `--vc-grid-line`) but retune them to the new palette (flow bg ≈ `--vc-bg`, node icon ≈ `--vc-fg-2`).

- [ ] **Step 2: Restyle components.** Cards/panels (`.sidebar-card`, `.chat-panel`, `.flow-container`) → rounded shadowed surfaces. `.message` bubbles, `.message-role`, `.model-badge`, `.filter-btn`, `.flow-toolbar button` → SaaS controls (bordered, `--vc-radius-ctl`, accent active). Markers keep their semantic colors but route through `--vc-pos`/`--vc-neg`/`--vc-accent`.

- [ ] **Step 3: Add fonts to head** (same 3 `<link>`s).

- [ ] **Step 4: Verify.** `node -c templates/session_detail.js && python3 extract_stats.py`, then screenshot one generated page:

```bash
node -e "import('playwright').then(async p=>{const b=await p.chromium.launch();const pg=await b.newPage({viewport:{width:1440,height:1000}});const f=require('fs').readdirSync('public/sessions').find(x=>x.endsWith('.html'));await pg.goto('file://'+process.cwd()+'/public/sessions/'+f,{waitUntil:'networkidle'});await pg.screenshot({path:'/tmp/smoke/session-detail.png',fullPage:true});await b.close();console.log('shot',f)})"
```

- [ ] **Step 5: Commit** (`feat(session-detail): SaaS reskin`).

---

## Task 17: Project-detail page reskin

**Files:**
- Modify: `templates/project_detail.css` — token block (`:1-82`) + components (`:84-257`): header, kpi-grid/kpi-card, tools-section/tool-pill, proj-tabs/proj-tab, info-grid/info-card, memory-card.
- Modify: `templates/project_detail.html` `<head>` — add fonts.
- Modify: `templates/project_detail.js` — literal hex → tokens if any.

- [ ] **Step 1: Sync the token block** (`:1-82`) with the SHARED REFERENCE + remove the `border-radius:0` rule (`:37`).

- [ ] **Step 2: Restyle components.** `.kpi-card` → SaaS KPI card; `.tool-pill` → accent-soft pill (`--vc-radius-pill`); `.proj-tab` → pill tab; `.info-card`/`.memory-card` → rounded shadowed cards.

- [ ] **Step 3: Add fonts to head.**

- [ ] **Step 4: Verify.** `node -c templates/project_detail.js && python3 extract_stats.py`, screenshot one `public/projects/*.html` (same one-liner as Task 16, swapping the dir).

- [ ] **Step 5: Commit** (`feat(project-detail): SaaS reskin`).

---

## Task 18: Full regression + final verification

**Files:** none (verification only)

- [ ] **Step 1: Data tests green.** Run: `python3 -m pytest tests/ -q` → Expected: `154 passed`.

- [ ] **Step 2: JS syntax across all touched files.** Run: `for f in dashboard session_detail project_detail; do node -c templates/$f.js || echo FAIL $f; done` plus any touched `templates/components/*.js`. Expected: no `FAIL`.

- [ ] **Step 3: Locale validity.** Run: `python3 -c "import json;[json.load(open(f)) for f in ('locales/en.json','locales/de.json')]"`. Expected: no error.

- [ ] **Step 4: Full rebuild + smoke.** Run: `python3 extract_stats.py && node tools/smoke_shot.mjs`. View every PNG in `/tmp/smoke/` (5 tabs × {desk-light, desk-dark, mob-light}) + the two detail-page shots. Compare against `/tmp/smoke_before`.

- [ ] **Step 5: Visual acceptance checklist** (eyeball each screenshot against `docs/design-handoff/`): (a) rounded shadowed cards everywhere, no force-squared corners; (b) Manrope type; (c) KPI hero value in accent; (d) pill nav with accent active tab; (e) Insights shows one section at a time via sub-nav; (f) dark mode legible incl. chart ticks/legends; (g) mobile tables are stacked labelled cards; (h) detail pages match. Note any gaps for follow-up.

- [ ] **Step 6: Final commit if any cleanup** (`chore(dashboard): SaaS reskin verification pass`).

---

## Self-review notes (spec coverage)

- Modern SaaS look (cards/shadows/radius/sans) → Tasks 2,3,6,7. Pill nav → Task 5. Top bar → Task 4.
- Keep ALL data/features → no render function loses content; only styling + the Insights wrapper change (Task 12) touches structure, and it preserves every inner id.
- Light + dark → token block carries both (Task 2); chart re-theme (Task 13); verified per-task via smoke.
- Responsive/mobile → Task 14 (+ detail pages inherit grid rules).
- Accent switch via custom.css (no React) → Task 15, single-source `--vc-accent` from Task 2.
- Insights numbered sub-nav → Task 12.
- Detail pages → Tasks 16, 17.
- Model colors stay family-distinct/earth-toned → Task 13 keeps `vcModelColor` + `_VC_CAT`.
- Charts stay Chart.js standard types → unchanged; only colors/fonts retuned.

**Known risk flags for the executor:**
- Session/sessions-table and filter classes live in `templates/components/*` — Task 11 must read them first; don't assume class names.
- `renderLimitsEventTimeline` / `renderPlanRecommendation` emit their own class names — Task 9 keys styles to the emitted names, not the mock's.
- The user runs parallel Claude Code sessions on this repo; `git status` showed `extract_stats.py` and `dashboard.js` already modified by another session at plan time. Re-check `git status` before each commit and avoid clobbering unrelated changes (consider executing in a worktree).
