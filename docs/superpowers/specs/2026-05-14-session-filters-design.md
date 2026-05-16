# Session Filters — Design

**Date:** 2026-05-14
**Branch:** to be created from `main` before implementation
**Status:** Approved (Ansatz A); user waived per-section approval

## Goal

Add an expandable "Weitere Filter" module above the session table so that
users can narrow the list by numeric session attributes (e.g. only
sessions with **more than 1 user message**, filtering out trivial
sub-agent / boilerplate sessions). The same module is mounted on both
the dashboard Sessions tab and the project detail page bottom table.

Motivating use case: many sub-agent / hook-driven sessions have exactly
one user message and bloat the list. The user wants a slider-driven
panel and one-click presets to remove this noise, plus broader
exploration over Cost, Duration, Tool Calls, etc.

## Non-Goals

- Filter persistence across browsers / accounts (localStorage only)
- Filter sharing via URL params (room to add later)
- Boolean / categorical filters beyond what the existing
  `filterProject` / `filterSource` selects already cover
- Saved-filter presets that the user can name and store
- Filtering on the table inside `templates/components/session_table.js`
  itself — the table stays "render what you're handed"

## User-Visible Behavior

### Toolbar layout (dashboard tab "Sessions")

The existing `.session-filters` bar gains two new controls and a chip
row underneath:

```
[ Project ▾ ]  [ Source ▾ ]  [ search… ]
[ Nur echte Sessions ]  [ Nur teure Sessions ]  [ ⚙ Weitere Filter ▾ ]      [⬇ XLSX] [⬇ CSV] [⬇ Download all]
[ User Msgs ≥2 × ] [ Cost 0.50–5.00 × ] [ Tool Calls ≥10 × ]   Clear all
```

- The two **preset buttons** are toggles (active state highlights them).
- **Weitere Filter** is the panel toggle. It shows a badge with the
  count of currently-active filters, e.g. `Weitere Filter (3) ▾`.
- The **chip row** appears only when at least one numeric filter (or a
  preset) is active. Each chip shows attribute and bounds, with an `×`
  to clear that filter. A trailing `Clear all` link clears every chip
  (presets included).

On the project detail page the same module appears between the page
KPIs and the session table, with the project filter implicitly fixed
(no Project select needed).

### Filter panel (expanded)

```
┌──────────────────────────────────────────────────────────────┐
│ Volume                                                       │
│   User Msgs       [◀─●─────────●▶]    min[ 2 ] max[    ]     │
│   Messages        [◀●──────────▶]     min[   ] max[    ]     │
│   Duration (min)  [◀●──────────▶]     min[   ] max[    ]     │
│                                                              │
│ Tokens                                                       │
│   Total Tokens    [◀●──────────▶]     min[   ] max[    ]     │
│                                                              │
│ Cost                                                         │
│   Cost (USD)      [◀─●─────●────▶]    min[0.50] max[5.00]    │
│                                                              │
│ Cache Health                                                 │
│   Cache Eff. (%)  [◀●──────────▶]     min[   ] max[    ]     │
│                                                              │
│ Activity                                                     │
│   Tool Calls      [◀●──────────▶]     min[10 ] max[    ]     │
│   Agent Dispatch. [◀●──────────▶]     min[   ] max[    ]     │
│                                                              │
│ Errors                                                       │
│   Error Count     [◀●──────────▶]     min[   ] max[    ]     │
│                                                              │
│                                       [Reset]  [Schließen]   │
└──────────────────────────────────────────────────────────────┘
```

Group headers mirror the column groups in `session_table.js`. The
panel uses the existing terminal-aesthetic CSS vars (`--vc-bg`,
`--vc-border`, `--vc-text`, monospace headings).

### Filterable attributes (curated set, 9 entries)

| Group | Label | Field | Unit | Scale | Step |
|---|---|---|---|---|---|
| Volume | User Msgs | `user_messages` | count | linear | 1 |
| Volume | Messages (total) | `messages` | count | linear | 1 |
| Volume | Duration | `s.duration_min` directly | min | linear | 1 |
| Tokens | Total Tokens | sum of input + output + cache\_read + cache\_write | tokens | log | (snap) |
| Cost | Cost | `cost` | USD | log | 0.01 |
| Cache Health | Cache Eff. | derived (cache_read / inputSum × 100) | % | linear | 1 |
| Activity | Tool Calls | `api_calls` (or sumTools) — see below | count | log | 1 |
| Activity | Agent Dispatches | `agent_dispatches.length` | count | log | 1 |
| Errors | Error Count | `error_count` | count | linear | 1 |

Open implementation detail: **Tool Calls** maps to whatever the
`tool_calls` column in `session_table.js` already shows. Verify during
implementation and reuse the same getter so the slider matches the
column the user sees (`sumTools(s)` per line 252-258 of
`session_table.js`).

### Slider scale per attribute

- **Linear** sliders for bounded counts (User Msgs, Messages, Duration
  in minutes, Cache Eff %, Error Count): min = 0,
  max = ceil of P99 of currently-loaded sessions, snapped to a "nice"
  value (1, 2, 5, 10, 20, 50, 100, …).
- **Log** sliders for heavy-tail attributes (Total Tokens, Cost,
  Tool Calls, Agent Dispatches): position is mapped through `log10(value + 1)`. The
  Min/Max text inputs display the linear value the user expects;
  internally the slider track is log-scaled. Both rails meet at
  P99-snap.
- Ranges are **recomputed whenever the upstream pool changes** (i.e.
  whenever `F.sessions` changes because of the time filter, project
  filter, source filter, or search). When recomputed, the user's
  current min/max values are clamped into the new range (never
  silently moved otherwise).

### Quick-Presets

Two preset buttons, both toggles:

- **Nur echte Sessions** — sets `user_messages.min = 2`. Toggling off
  clears the User-Msgs min back to its unbounded state.
- **Nur teure Sessions** — sets `cost.min = 1.00`. Toggling off clears
  the Cost min.

A preset is "active" iff the corresponding filter is set to *exactly*
the preset's value. Editing the slider away from the preset's value
deactivates the highlight but does not toggle the preset off.

### Live updates

All slider / input changes apply with a **200 ms debounce**, after
which `applyFilter(...)` is re-run and the table re-renders. The
"Reset" button clears all numeric filters and presets, then triggers
an immediate apply.

### Chip row

- Rendered above the table, only when at least one numeric filter is
  active.
- Chip text format depends on bounds:
  - Both min and max: `User Msgs 2–50`
  - Only min: `User Msgs ≥2`
  - Only max: `User Msgs ≤50`
- Clicking the `×` clears that single attribute's min and max.
- Clicking `Clear all` clears every numeric filter and deactivates
  both presets.

## Architecture

### Approach A — standalone component

New files in `templates/components/`:

- `session_filters.js` — `mountSessionFilters(host, options)` returns
  `{ getActiveFiltersList(), onPoolChanged(), destroy() }` and calls
  `options.onChange()` whenever the user state changes.
- `session_filters.css` — terminal-aesthetic styling matching
  `session_table.css`.

Both files are loaded by `dashboard.html` and `project_detail.html`
the same way the table component is loaded today (script + stylesheet
tags in `<head>`).

### Integration with existing filter pipeline

In `dashboard.js`:

1. On init, mount filters above the table mount:
   ```js
   sessionFilters = mountSessionFilters(filtersHost, {
     context: 'dashboard',
     getPool: () => F.sessions,        // upstream filtered set
     onChange: () => renderSessions(),  // re-run getFilteredSessions
   });
   ```
2. Extend `getFilteredSessions()` (line 1185 of dashboard.js) to call
   `sessionFilters.getActiveFiltersList()` and apply each predicate
   after the existing project / source / search filters.
3. The filter component recomputes its slider ranges from `getPool()`
   when it receives an `onPoolChanged()` call from `renderSessions`.

`project_detail.js` follows the identical pattern with
`context: 'projectDetail'`.

### Filter state shape

Stored per context in `localStorage` under
`sessionFilters.<context>` (matching the existing
`sessionTable.<context>.<suffix>` convention).

```json
{
  "user_messages":      { "min": 2, "max": null },
  "messages":           { "min": null, "max": null },
  "duration_min":       { "min": null, "max": null },
  "total_tokens":       { "min": null, "max": null },
  "cost":               { "min": 0.5, "max": 5.0 },
  "cache_eff":          { "min": null, "max": null },
  "tool_calls":         { "min": null, "max": null },
  "agent_dispatches":   { "min": null, "max": null },
  "errors":             { "min": null, "max": null },
  "panelOpen":          false
}
```

`null` means "unbounded on this side". Missing keys are treated as
unbounded.

Presets are not stored separately — they're "shortcuts" that mutate
this state and read back from it to determine active highlight.

### Active filter count (panel badge)

A filter is "active" iff at least one of its `min` / `max` is not
`null`. Total count is rendered in the toggle: `Weitere Filter (3) ▾`.

## Files Touched

**New:**

- `templates/components/session_filters.js` (~ 400 lines)
- `templates/components/session_filters.css` (~ 120 lines)

**Modified:**

- `templates/dashboard.html` — script + stylesheet include, new mount
  point, presets row, chip row.
- `templates/dashboard.js` — mount the component, extend
  `getFilteredSessions()`, hook `onChange`, recompute pool on filter
  changes.
- `templates/project_detail.html` — same script/style include, new
  mount point above the existing session table block.
- `templates/project_detail.js` — same mount pattern as dashboard,
  with `context: 'projectDetail'`.

No `extract_stats.py` changes — the filter operates entirely on the
client-side session list.

## Accessibility

- Each slider has an aria-label matching its visible label.
- The Min/Max inputs are real `<input type="number">` with min/max/step.
- Tab order: presets → toggle → (when open) sliders top-to-bottom →
  Reset → Schließen → chip × buttons → Clear all.
- `Escape` while the panel is open closes the panel (same pattern as
  the column picker in `session_table.js`).

## Responsive layout

- ≥ 1100 px: two-column slider grid inside the panel.
- 700–1099 px: single-column slider grid.
- < 700 px: presets and toggle wrap to multiple lines; sliders
  collapse to single-column; chip row wraps to additional lines as
  needed.

## Edge Cases

- **Empty pool** (no sessions match upstream filters): the panel still
  renders, sliders show range `0–0` and are disabled. Chip row hidden.
- **Single-value pool** (e.g. only one session with cost = $0.42):
  slider range becomes `0–1` (next nice value above 0.42), no special
  state.
- **User pastes an out-of-range number** into a Min/Max input: clamp
  silently to the current slider's range.
- **User types Min > Max**: the lower bound is reduced to the new
  value; the upper bound is unchanged. (Symmetric for Max < Min.)
- **localStorage stores a key for an attribute that no longer exists**
  (release removed it): silently dropped on load.
- **Time filter changes while panel is open**: ranges recompute, user
  bounds clamp into the new range, chip text updates if a bound
  changed due to the clamp.

## Test Plan

Manual smoke test in headless Chromium (per
`reference_local_ui_smoketest.md` pattern):

1. Load dashboard. Confirm Sessions tab shows two new preset buttons,
   the "Weitere Filter" toggle, no chip row.
2. Click "Nur echte Sessions". Confirm preset highlights, chip
   `User Msgs ≥2` appears, table loses single-message sessions, badge
   reads `(1)`.
3. Open the panel. Confirm slider for User Msgs has its min handle
   at 2 and the min input reads `2`.
4. Drag the Cost min slider; confirm 200 ms debounce, chip appears,
   badge increments.
5. Type `100000` into Total Tokens min input; confirm clamp to range
   max if exceeded.
6. Reload page. Confirm state persists (panel open/closed, slider
   values, presets).
7. Switch to project detail page of a project with sessions. Confirm
   filter module appears above the table with `context: 'projectDetail'`
   storage key (independent of dashboard state).
8. Time filter to "7 days" with very few sessions. Confirm slider
   ranges shrink, current bounds clamp.
9. JS syntax preflight: `node -c session_filters.js`.

No new automated tests — UI smoke is sufficient and matches the
project's testing conventions for table components.

## Open implementation details (decide during build)

1. Whether **Tool Calls** maps to `api_calls` or `sumTools(s)`. Use
   the same getter the visible table column uses.
2. Exact "nice number" snap table for slider max ranges.
3. Whether the chip row scrolls inline or wraps to a second line on
   narrow viewports (decide visually).
