# Handoff: Claude Stats Dashboard — Variant C "Terminal"

## Overview
Redesign of the Claude Code usage-stats dashboard. The brief was to move away from the existing multi-color "AI dashboard" look (parallel purple / cyan / orange / green / red / blue accents) toward something **structured, calm, and information-dense**. Variant C — "Terminal" — is the chosen direction: monospace-forward, Bloomberg-row KPIs, dotted/hairline grids, single accent hue, light + dark mode driven by system preference.

The dashboard surfaces:
- Plan economics (subscription paid vs. API-equivalent value, ROI)
- Token & cost trends over a configurable range
- Activity patterns (heatmap, hour-of-day, weekday, streaks)
- Project-level breakdown
- Recent session list
- Tool / file-op / git insights
- Subagent activity

## About the Design Files
The files in this bundle are **design references created in HTML** — a React + JSX prototype showing intended look, layout, typography, and behavior. They are **not production code to copy directly**.

The task is to **recreate this design in the target codebase's existing environment** (likely React/Next.js for the Claude Code stats app — but use whatever stack the repo already uses) following its established patterns, design tokens, charting library, and component conventions. If no environment exists yet, pick the most appropriate stack for the project.

In particular:
- Replace the inline `<style>` CSS string with the codebase's styling system (Tailwind, CSS modules, styled-components, etc.).
- Replace the hand-rolled SVG cost chart with the codebase's existing chart library (Recharts, Visx, etc.) if one is already in use — but match the visual treatment described below (hairline gridlines, no axis labels beyond what's shown, 7-day moving-average ghost line).
- Wire the data shapes shown in `data.js` to real API responses; treat that file as a schema reference.

## Fidelity
**High-fidelity.** Final colors, type, spacing, component structure, and tab navigation are intended as shown. Pixel-perfect implementation expected, with the caveat that fonts/charts/icons should map to whatever the codebase already provides (don't introduce new font dependencies if Geist isn't already loaded — use the existing UI font + a monospace).

## Files in this bundle
| File | What it is |
|---|---|
| `variant-c.jsx` | The full React component tree for the dashboard (`VariantC` + `CostTab`, `ActivityTab`, `ProjectsTab`, `SessionsTab`, `PlanTab`, `InsightsTab`, `AgentsTab`, `CostChart`). All CSS lives in a single `terminalCSS` template string at the top. |
| `data.js` | Mock data shape. Use as a schema reference for the API response. |
| `preview.html` | Standalone preview — open this in a browser to see Variant C exactly as designed (no canvas wrapper, no tweaks panel). Auto-respects `prefers-color-scheme`. |

---

## Design tokens

All tokens are CSS custom properties defined on `.vc` (light) and `.vc.dark`.

### Colors — light mode
| Token | Value | Use |
|---|---|---|
| `--bg` | `#f4f1ec` | Page background — warm off-white, not pure white |
| `--panel` | `#fbfaf6` | Card / panel background |
| `--grid` | `#d8d2c4` | Borders, table-row separators |
| `--grid-2` | `#e8e3d6` | Lighter dotted gridlines, secondary separators |
| `--fg` | `#1c1a17` | Primary text |
| `--fg-2` | `#4d4a42` | Secondary text |
| `--fg-3` | `#918a7a` | Tertiary / labels / muted |
| `--accent` | `#b04a2f` | Terracotta — single accent color |
| `--accent-soft` | `#f1d9cd` | Hover backgrounds, soft accent fills |

### Colors — dark mode
| Token | Value |
|---|---|
| `--bg` | `#0e0d0b` |
| `--panel` | `#15140f` |
| `--grid` | `#2a2620` |
| `--grid-2` | `#1f1d18` |
| `--fg` | `#ece7da` |
| `--fg-2` | `#b3ad9b` |
| `--fg-3` | `#76705f` |
| `--accent` | `#d97757` |
| `--accent-soft` | `#2c1c14` |

**Single-accent rule.** Charts, KPIs, hover states, status indicators, and progress bars all use the same `--accent`. Do **not** introduce per-category coloring (no different color per model, project, or tool). Categorical differentiation comes from monospace tags + ordering, not hue. Where multiple bars stack (e.g. distribution lists), use `--accent` for the primary series, `--fg-2` for secondary, `--fg-3` for tertiary.

### Typography
- **UI / labels / data**: Geist Mono (or fallback `'JetBrains Mono', ui-monospace, monospace`). Font-feature-settings: `'tnum' 1, 'zero' 1` for tabular numerals.
- **Body / longer prose / session-prompt previews**: Geist (or fallback `'Inter', system-ui, sans-serif`).
- **Letter-spacing**: `-0.005em` on body, `0.14em` to `0.18em` uppercase on labels and section headers.
- **Sizes** — see exact px values per component below; the dashboard does not have a single rigid type scale, but it consistently uses 10–11px for labels/uppercase, 11–12px for body data, 22–26px for KPI values.

### Spacing
- Page padding: `20px 20px 40px` on `.vc-main`, `max-width: 1400px`, centered.
- Component padding inside panes: `14px 18px` to `16px 18px`.
- Gaps between major sections: `16px` to `24px`.
- Borders: always `1px solid var(--grid)`. **No border-radius anywhere** — this is a deliberate flat-rectangle aesthetic. Do not soften corners.

### Borders & dividers
- Solid `1px` borders on panels, KPI cells, tables.
- Dashed `1px` separators inside stat rows (`border-bottom: 1px dashed var(--grid)`).
- Chart gridlines: `stroke-dasharray: 1 3` (dotted), `var(--grid-2)`.
- Moving-average ghost line: `stroke-dasharray: 4 2`, `var(--fg-2)`, `opacity: 0.6`.

---

## Layout — top-level structure

The dashboard is a single vertical stack:

```
┌────────────────────────────────────────────────────────────┐
│ TOP BAR (persistent)                                       │  height ~38px
├────────────────────────────────────────────────────────────┤
│ PRIMARY NAV TABS · · · · · · · · · · ·   RANGE FILTER      │  height ~44px
├────────────────────────────────────────────────────────────┤
│                                                            │
│ KPI STRIP (persistent — 5 cells)                           │  height ~96px
│                                                            │
├────────────────────────────────────────────────────────────┤
│ TAB CONTENT (swaps based on active tab)                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

The **top bar**, **primary nav**, and **KPI strip** are persistent across all tabs. Only the area below the KPI strip swaps when the user changes tabs.

---

## Components

### 1. Top bar (`.vc-top`)
- 3-column grid: `auto 1fr auto`, gap 16px, padding `10px 20px`.
- Background: `--panel`, bottom border: `1px solid --grid`.
- Font: Geist Mono, 11px.
- **Left**: brand mark (8×8 terracotta square — *not* a circle, `border-radius: 1px`), product name `CLAUDE.STATS` in 600 weight with `letter-spacing: 0.02em`, version tag `v2.4.0` in `--fg-3`.
- **Center**: `USER`, `PLAN`, `RANGE` label/value pairs. Labels in `--fg-3`, values in `--fg`, weight 500.
- **Right**: `● LIVE` indicator (in `--accent`) + UTC time in `--fg-3`.

### 2. Primary navigation (`.vc-nav`)
- Horizontal flex row, padding `0 20px`, bottom border.
- Tabs: `Cost`, `Activity`, `Projects`, `Sessions`, `Plan`, `Insights`, `Agents`.
- Each tab: `padding: 14px 18px`, font 11px Geist Mono, `letter-spacing: 0.14em`, `text-transform: uppercase`, weight 500.
- Inactive: color `--fg-3`. Hover: `--fg-2`. Active: `--fg` + 2px terracotta underline (positioned `bottom: -1px` to overlap the nav border, inset 12px from the tab edges).
- Right side: `RANGE` segmented control with options `7d / 30d / 90d / YTD / ALL`. Each segment is a button with a left border (no left border on the first). Active segment colored `--accent`. **No underline on the active range button** (the nav underline only applies to top-level tabs).

### 3. KPI strip (`.vc-kpis`)
- 5-column grid: `1.4fr 1fr 1fr 1fr 1fr`, full width, single 1px border around the whole strip, 1px right-border between cells.
- Background `--panel`. Margin-bottom 24px.
- Each cell (`.vc-kpi`): padding `14px 18px`.
  - **Label row**: 10px uppercase `letter-spacing: 0.14em`, color `--fg-3`. May contain a delta indicator on the right (e.g. `▲ 12.4%` in `--accent` for positive, or a contextual count like `12 prj`).
  - **Value row**: 26px, weight 500, `letter-spacing: -0.02em`, tabular numerals. Primary KPI (first cell, "API EQUIVALENT") uses `--accent`; others use `--fg`.
  - **Sub row**: 11px `--fg-3`, with key terms wrapped in `<b>` styled as weight 500 `--fg-2`.

The five cells, in order:
1. **API EQUIVALENT** (primary) — large dollar amount, sub: `paid <b>$200.00</b> · save <b>95.3%</b>`
2. **SESSIONS** — count, sub: `avg <b>38m</b>`
3. **MESSAGES** — count, sub: `<msgs/session>/session`
4. **OUTPUT TOKENS** — formatted (e.g. `8.42M`), sub: `in <b>412.0K</b>`
5. **CACHE HIT** — percentage with smaller `%` glyph, sub: `read <b>184.2M</b>`

### 4. Tab section header (`.vc-tab-h`)
Appears at the top of every tab's content area:
- 3-column grid: `auto 1fr auto`, gap 12px.
- Left: `↳` glyph (in `--fg`) + section name (e.g. "Token & API Value"). Format: `<b>↳</b> <name>`. 11px uppercase, `letter-spacing: 0.16em`, color `--fg-3` with `<b>` overrides to `--fg`.
- Center: 1px horizontal rule in `--grid`.
- Right: meta string (e.g. `90d · daily · USD`) in 11px `--fg-3`.

### 5. Pane grid (`.vc-pane-grid`)
- Container with 1px border, no internal gaps (panes share edges).
- Variants: `.cols-2` = `1.6fr 1fr`, `.cols-2-eq` = `1fr 1fr`, `.cols-3` = `1fr 1fr 1fr`.
- Each `.vc-pane`: padding `16px 18px`, right-border between panes.
- Pane heading (`h3`): 11px weight 600, uppercase, `letter-spacing: 0.14em`. Optional `.meta` span on the right in 10px `--fg-3`, normal case.

### 6. Cost chart (`CostChart` component)
- 800×280 SVG, `preserveAspectRatio="none"` (stretches to container width).
- Padding inside SVG: `{l: 44, r: 16, t: 20, b: 28}`.
- 5 horizontal gridlines at 0/25/50/75/100% of max, dotted (`stroke-dasharray: 1 3`), color `--grid-2`.
- Y-axis labels: 10px Geist Mono, right-aligned, color `--fg-3`.
- X-axis: every 12th day labeled (e.g. "Apr 30", "Apr 18", "Apr 6"). Format: `toLocaleDateString('en-US', {month: 'short', day: 'numeric'})`.
- **Data line**: solid `--accent`, 1.5px stroke.
- **Area fill**: `--accent` at `fill-opacity: 0.1`.
- **7-day moving-average ghost line**: `--fg-2`, 0.75px stroke, `stroke-dasharray: 4 2`, opacity 0.6.

### 7. Distribution bars (`.vc-distbar`)
Used for "by_model", "weekday", "top_tools", "plan_comparison", etc.
- Vertical flex stack, gap 10px.
- Each row: 3-col grid `90px 1fr 90px`, gap 10px, font 11px.
- Name on left in `--fg`.
- Bar: 12px tall, 1px `--grid` border, `--bg` background. Inner fill `--accent`. Series 2 uses `--fg-2`, series 3 uses `--fg-3`.
- Value on right, right-aligned, tabular numerals, `--fg-2`.

### 8. Stat rows (`.vc-stat-row`)
Key/value pairs inside panes:
- 2-col grid `1fr auto`, padding `8px 0`, dashed bottom border (`1px dashed --grid`), no border on last child.
- Key: 12px `--fg-3`. Value: 12px `--fg`, tabular numerals. Use class `.acc` on value for terracotta highlight.

### 9. Heatmap (`.vc-heatmap`)
Activity heatmap (last 18 weeks):
- 7 rows (Mon–Sun) × 18 cols (weeks).
- Each row: grid `28px repeat(18, 1fr)`, gap 2px.
- Day label: 10px `--fg-3`.
- Cells: aspect-ratio 1, terracotta fill, opacity = `0.08 + intensity * 0.92` where intensity is `value / max`.
- Below the grid: legend row with "less / more" + 5 swatches at opacities `0.1, 0.3, 0.5, 0.7, 0.95`.

### 10. Hourly histogram (`.vc-hourly`)
24-bar bar chart of messages by hour:
- Grid `repeat(24, 1fr)`, gap 2px, height 80px, align-items end.
- Each bar: terracotta, `min-height: 1px`, height = `value/max * 100%`, opacity `0.4 + (value/max) * 0.6` (taller = more opaque).
- Bottom border under bars: 1px `--grid`.
- X-axis labels (`.vc-hourly-x`): every 4th hour (`00`, `04`, `08`, `12`, `16`, `20`), 10px `--fg-3`, centered.

### 11. Plan tab specifics
- **Plan grid** (`.vc-plan-grid`): 4 equal-width cells in a single bordered strip. Each cell: uppercase 10px label in `--fg-3`, then 20px value (weight 500), then 11px sub in `--fg-3`. The first ("PLAN") and fourth ("EFFECTIVE ROI") values use `--accent`.
- **Cycle progress bar** (`.vc-progress-track`): 28px tall, 1px `--grid` border, terracotta fill. The fill has a `data-label` attribute that renders as text inside the bar (right-aligned, 10px, color `--bg` for contrast against terracotta).

### 12. Tables (`.vc-table`)
- Full-width, no cell-padding gaps.
- `th`: 10px uppercase, weight 500, `letter-spacing: 0.1em`, color `--fg-3`, padding `8px 14px`, bottom border `1px --grid`, `--bg` background. Right-align numeric columns (`.num`).
- `td`: 11px, padding `8px 14px`, bottom border `1px --grid-2`. Last row no border.
- Hover: row background swaps to `--accent-soft`.
- **Index column**: width 32px, `--fg-3`, zero-padded (`01`, `02`, ...).
- **Bar cell**: appears in projects/models tables as a small inline distribution bar. Right-aligned flex with percentage label + 80×6px bar.
- Model names are wrapped in `.vc-tag.model` (1px border, 1px×6px padding, monospace, 10px).

### 13. Sessions list (`.vc-session`)
Used in the Sessions tab — denser than a generic table:
- 4-col grid `90px 1fr auto auto`, padding `11px 16px`, bottom border `1px --grid-2`.
- Hover: `--accent-soft` background.
- **Col 1** (when): timestamp like `2026-04-30 14:08`, color `--fg-3`.
- **Col 2** (body): two stacked lines — line 1: project name (weight 500, `--fg`) + model tag inline. Line 2: prompt preview, ellipsis-truncated, max-width 600px, 10px Geist (sans), color `--fg-3`. Opus tag uses `.acc` modifier (terracotta border + text).
- **Col 3** (stats): `<duration>m` and `<count> msg`, gap 12px, units (m, msg) styled as `<b>` weight 500 `--fg`.
- **Col 4** (cost): right-aligned, weight 500, `--accent`, min-width 60px.

### 14. Insights tab — misc grid (`.vc-misc-grid`)
4×N grid of stat tiles for git/file-ops counts:
- Each `.vc-misc`: padding `16px 18px`, right + bottom `1px --grid` border.
- 22px value (weight 500, tabular). Some tiles use `.v.acc` for terracotta.
- Below value: 10px uppercase label, `letter-spacing: 0.12em`, `--fg-3`.

---

## Tab content map

| Tab | Sections |
|---|---|
| **Cost** | (a) `cost.daily` chart with 7d-MA ghost line · (b) `by_model` distribution bars + `token_breakdown` stat rows (output, input, cache.read, cache.write, cache.efficiency) · (c) `model_detail` table (model, API value, calls, output tokens, $/call, share+bar) |
| **Activity** | (a) 18-week heatmap with legend + `weekday` distribution bars · (b) `hour_of_day` 24-bar histogram + `summary` stat rows (peak hour, peak day, active days, avg/day, longest streak, current streak) |
| **Projects** | Single full-width table: index, name, sessions, msgs, output tokens, size MB, API value (terracotta), share % + bar |
| **Sessions** | Single full-width list of recent sessions (see component #13) |
| **Plan** | (a) 4-cell plan grid (Plan, Paid, API equivalent, ROI) · (b) cycle progress bar + cycle stat rows · (c) plan_comparison distribution bars showing user usage against Free/Pro/Max5×/Max20×/Team thresholds |
| **Insights** | (a) `vc-misc-grid` of 8 file/git/agent counts · (b) `top_tools` distribution bars · (c) `config` stat rows (version, user, plan, mcp servers, hooks, custom skills, file snapshots, todos) |
| **Agents** | (a) `by_type` distribution bars (verifier, general-purpose, output-style-setup, repo-explorer, design-reviewer) · (b) `errors` distribution bars (tool_timeout, parse_error, rate_limit, network) + `summary` stat rows |

---

## Interactions & behavior

- **Tab switching**: clicking a tab in the primary nav (`Cost`, `Activity`, etc.) replaces the content area below the KPI strip. Top bar, nav, and KPI strip stay mounted (no re-render flicker). Implemented in the prototype with `useState`; in production, prefer URL-based routing (`/stats/cost`, `/stats/activity`, ...) so tabs are linkable and back/forward works.
- **Range filter**: the segmented control on the right of the nav (`7d / 30d / 90d / YTD / ALL`) is global — it scopes data for the active tab. Default: `90d`. In the prototype this is visual-only; wire it to actual data fetching.
- **Hover**: table rows and session list rows swap background to `--accent-soft`. Tab buttons darken from `--fg-3` to `--fg-2`.
- **Theme**: light/dark via `.vc.dark` class on the root. In production, follow `prefers-color-scheme: dark` by default, with an explicit user override stored in app preferences.
- **No animations** beyond default browser hover transitions. This is a deliberately static / utilitarian aesthetic — no fade-ins, no number-tickers, no chart entrance animations.
- **Click affordances** (build these as the codebase supports them):
  - Project row → drill into project detail (out of scope for this handoff).
  - Session row → drill into session detail (out of scope).
  - Model tag → filter activity to that model.

---

## State

| State | Source | Notes |
|---|---|---|
| `activeTab` | local UI state | one of: `cost`, `activity`, `projects`, `sessions`, `plan`, `insights`, `agents`. URL-driven in production. |
| `range` | local UI state | one of: `7d`, `30d`, `90d`, `YTD`, `ALL`. Global to dashboard. |
| `theme` | user preference / system | `light`, `dark`, or `system`. |
| dashboard data | API fetch | shape per `data.js`. Re-fetch on `range` change. |

---

## Data shape

See `data.js`. Top-level keys:
- `account`: `{ name, plan, first_session, last_session }`
- `generated_at`: ISO timestamp
- `kpi`: `{ api_equivalent, actual_paid, messages, sessions, output_tokens, input_tokens, cache_read, cache_write }`
- `daily_cost`: number[] (one entry per day in the active range)
- `models`: `[{ name, cost, calls, share, output }]`
- `projects`: `[{ name, sessions, messages, cost, output, sizeMb }]`
- `hourly`: number[24] (messages by hour 0–23, local time)
- `weekday`: number[7] (Mon–Sun)
- `heatmap`: number[7][18] (rows = weekday Mon–Sun, cols = weeks ago, last 18 weeks)
- `recent_sessions`: `[{ date, project, model, duration, messages, cost, prompt }]`
- `top_tools`: `[{ name, count }]`

---

## Number formatting

All numeric values use US locale + tabular numerals:
- USD: `$1,234.56` — `toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})` with leading `$`.
- Token counts: humanize — `8.42M`, `412.0K`, `184.2M`. See `fmtTok_C` in `variant-c.jsx`.
- Plain integers: `toLocaleString('en-US')`.
- Indexes: zero-padded to 2 digits (`01`, `02`, ...).
- Always enable `font-feature-settings: 'tnum' 1, 'zero' 1` on any element rendering numbers.

---

## Responsive behavior

The prototype is designed at 1400px content width. Below that:
- KPI strip: at <1100px wrap to 2 rows of cells (3+2 or 5+0 with horizontal scroll).
- Pane grids: `cols-2` collapse to single column at <960px.
- Tables: horizontal scroll inside the pane.
- Nav: keep tabs in a single row; allow horizontal scroll if needed. Range filter wraps below tabs at narrow widths.

The prototype does not implement these breakpoints — it assumes desktop. The implementor should add them per the codebase's responsive conventions.

---

## Assets

No images, icons, or external assets used. Brand mark is a simple 8×8 terracotta square. Status indicator is a `●` Unicode character. The `↳` glyph in section headers is also Unicode. All UI is text + CSS rectangles + inline SVG charts.

---

## Brand

If the target codebase already has an Anthropic / Claude brand system, use those tokens for the accent color (terracotta is intentionally aligned with the Claude brand orange — `#d97757` in dark mode is exactly Claude's orange). Use the codebase's existing fonts if Geist isn't already loaded; the design works with any clean monospace + UI sans pair.

---

## Out of scope for this handoff

- Project detail screen
- Session detail screen
- Settings / account management
- Onboarding / empty states
- Loading / error states (designs not yet specified — implementor should follow codebase patterns)
- Mobile-first layouts (desktop hi-fi only at this stage)
