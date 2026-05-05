# Session Table — Design

**Date:** 2026-05-05
**Branch:** to be created from `main` before implementation
**Status:** Draft, awaiting user review

## Goal

Replace the existing expandable session-card list with a dense, sortable
data table that exposes all available session metrics. The same component
is used in two places:

1. The **Sessions** tab on the dashboard (`templates/dashboard.html`)
2. The session list at the bottom of each **project detail** page
   (`templates/project_detail.html`)

Users should be able to compare sessions across many KPIs at a glance,
sort by any numeric column, and pick which columns are visible. Column
choices, sort, and page size persist across reloads, separately per
context.

## Non-Goals

- Drag & drop column reorder
- CSV / JSON export of the table
- Multi-column sort
- Column-level filters in the table header
- Sticky table header on scroll (room to add later without breaking
  changes)
- Card / table view toggle — the cards are removed entirely

## User-Visible Behavior

### Default view

A table with 8 columns, sorted by date descending:

`Date · Project · First Prompt · Model · Duration · Messages · Cost · Chat`

On project detail pages, the `Project` column is statically suppressed
(it would be the same value in every row) — default visible columns
are otherwise the same.

### All available columns (25)

Grouped for the column picker:

| Group | Columns |
|---|---|
| Identity | Date, Project, First Prompt, Source, Primary Model |
| Volume | Duration, Messages, User Msgs, Assistant Msgs, API Calls |
| Tokens | Input, Output, Cache Read, Cache Write, Reasoning, Total |
| Cost | Cost, Reasoning Cost |
| Cache Health | Cache Efficiency, Compactions, Flushes |
| Activity | Tool Calls (sum), File Ops, Agent Dispatches, File Size (MB) |
| Errors | Error Count |
| Action | Chat |

### Interaction

- **Sort:** click a column header to toggle ascending / descending.
  The active sort column shows the existing `▲` / `▼` indicator from
  `.vc .data-table` styles. Stable secondary sort by `start` desc on
  ties. Sort persists per context.
- **Pagination:** existing footer with `«‹ page X / Y ›»`, plus a new
  page-size picker (25 / 50 / 100). Default 50. Page size persists
  per context.
- **Column picker:** gear icon (⚙) to the right of the filter bar
  (dashboard) or above the table (project detail). Clicking opens a
  dropdown listing all 25 columns under their group headings, each
  with a checkbox. Footer buttons: **Reset to default** and **Hide all
  optional**. Click-outside or ESC closes the dropdown. Selection
  applies immediately and persists per context.
- **Clickable cells:**
  - Project cell links to `projects/<slug>.html` (or
    `../projects/<slug>.html` from project detail — but the column is
    suppressed there anyway).
  - Chat column renders as an icon-button linking to
    `sessions/<session_id>.html` (or `../sessions/<session_id>.html`
    from project detail).
- **First prompt:** truncated to ~80 characters; full text shown in a
  `title` tooltip on hover. Hidden in anonymized mode.
- **Anonymization (F2):** project name shown via `anonName()`, first
  prompt hidden, chat link hidden — matches current card behavior.
- **Narrow viewports (<800px):** the table is wrapped in an
  `overflow-x: auto` container so it scrolls horizontally without
  breaking layout. No automatic column hiding.

### Filters (dashboard only)

The existing filter bar (project select, source select, search input)
remains above the table. The `filterSort` select is **removed** —
column-header sort replaces it. Bulk-download button continues to
operate on the current filter result.

## Architecture

### New files

- `templates/components/session_table.js`
- `templates/components/session_table.css`

### Modified files

- `extract_stats.py` — extend `_get_html_template()` (and the
  equivalent for `project_detail`) to prepend the component CSS / JS
  before the page CSS / JS, in both dashboard and project detail
  builders. The session detail page is unchanged.
- `templates/dashboard.html` — remove the `filterSort` select; add a
  gear icon placeholder slot inside the existing filter bar.
- `templates/dashboard.js` — replace `buildSessionCard` and
  `renderSessionList` with a single call to `mountSessionTable`. Wire
  the existing filter handlers to `tableHandle.update(filtered)`. The
  `getFilteredSessions()` helper used by bulk download keeps its
  current responsibility (it filters source / project / search), and
  the table's internal sort + pagination apply on top.
- `templates/dashboard.css` — remove `.session-card` and descendant
  rules.
- `templates/project_detail.html` — replace the inline session card
  list with a single mount container.
- `templates/project_detail.js` — replace the `innerHTML` card builder
  with `mountSessionTable(container, P.sessions, {context: 'projectDetail'})`.
- `templates/project_detail.css` — remove `.session-card` and
  descendant rules.

### Public API

```js
mountSessionTable(container, sessions, {
  context: 'dashboard' | 'projectDetail',
  defaultColumns?: string[],       // override the per-context defaults
  defaultPageSize?: number,        // default 50
  filteredCountEl?: HTMLElement,   // updated with current filtered count
  onChange?: () => void            // fired after sort / page / column changes
}) → {
  update(sessions),                // re-render with a new sessions list
  getFiltered(),                   // current sessions in current sort order
  destroy()                        // clean up listeners + DOM
}
```

The component owns its own state (sort, page, page size, visible
columns). It does not own the project / source / search filters —
those stay in the page and feed the component via `update()`.

### State persistence

`localStorage` keys, scoped by context:

- `sessionTable.<context>.columns` — array of visible column IDs
- `sessionTable.<context>.sort` — `{col: string, dir: 'asc' | 'desc'}`
- `sessionTable.<context>.pageSize` — number

`<context>` is one of `dashboard`, `projectDetail`.

### Column definition shape

```js
{
  id: 'cost',
  label: 'Cost',
  group: 'cost',
  align: 'right',                  // 'left' | 'right' | 'center'
  sortable: true,
  defaultIn: ['dashboard', 'projectDetail'],
  hideWhen?: { context: 'projectDetail' },   // suppress entirely
  get: (s) => s.cost,                        // value for sorting
  render: (s, ctx) => fmtUSD(s.cost)         // returns HTML string or DOM node
}
```

Special columns:

- `chat_link` — `sortable: false`, renders an icon button. URL prefix
  depends on `ctx.context` (dashboard: `sessions/...`; projectDetail:
  `../sessions/...`).
- `project` — links to `projects/<slug>.html`; renders `anonName(s.project)`
  in anon mode.
- `model` — uses existing `.model-badge.opus|.sonnet|.haiku` classes.
- `cache_eff` — uses existing `sessionCacheEff()` and `effStyle()` helpers.
- `compactions`, `flushes` — render empty string when value is 0.
- `first_prompt` — truncated to 80 chars; full text in `title`; empty
  in anon mode.

### Anon mode

The component reads the global `anonMode` flag at render time (set by
the F2 toggle) and re-renders when it changes. Existing F2 handler in
the page calls `tableHandle.update(currentSessions)` after toggling.

## Build pipeline change

`extract_stats.py` currently reads page-specific HTML/CSS/JS and inlines
them via `<!-- STYLES -->` and `<!-- SCRIPTS -->` placeholders. The
extension:

```python
comp_dir = base_dir / "templates" / "components"
comp_css = (comp_dir / "session_table.css").read_text(encoding="utf-8")
comp_js  = (comp_dir / "session_table.js").read_text(encoding="utf-8")
css = comp_css + "\n" + css
js  = comp_js  + "\n" + js
```

Applied in both `_get_html_template()` (dashboard) and the project
detail equivalent. Session detail page is not touched.

## Acceptance criteria

1. Default dashboard view shows 8 columns, sorted by date desc.
2. Clicking a column header sorts; reload preserves the sort.
3. Column picker lists all 25 columns under 8 group headers; checkbox
   toggles visibility immediately; reload preserves visibility.
4. Project cell click navigates to `projects/<slug>.html`; chat icon
   click navigates to `sessions/<id>.html`.
5. On a project detail page, the same table renders without the
   project column and with its own localStorage state independent of
   the dashboard.
6. F2 anonymization: project blurred / anonymized, first prompt empty,
   chat link hidden — same behavior as before.
7. Page-size picker (25 / 50 / 100) and pagination buttons work and
   persist per context.
8. Bulk-download button continues to download the currently filtered
   set in current sort order.
9. On viewports under 800px, the table scrolls horizontally without
   breaking the surrounding layout.

## Testing

Manual verification in local browser is sufficient for v1; no JS
unit-test infrastructure exists in the repo. Walk through each
acceptance criterion above. The extended Python build is verified by
running `extract_stats.py` and confirming dashboard + project pages
render without errors.

## Open risks

- Dashboard.js is large (~2400 lines). Removing the card path and
  rewiring filters through the new component will touch existing
  helpers (`getFilteredSessions`, `updateBulkBtnLabel`,
  `renderSessions`). The component takes over `renderSessionList`'s
  job; the wiring change must keep the bulk-download counter in
  sync via `onChange`.
- Anon mode toggling is currently driven from outside the card render
  path. The page must call `tableHandle.update(...)` from the F2
  handler — there is one F2 handler per page that needs updating.
- The project detail page does not currently have a filter bar. The
  column picker is still useful there, so the gear icon goes above
  the table on its own.
