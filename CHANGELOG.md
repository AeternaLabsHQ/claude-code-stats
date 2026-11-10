# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The Experiments comparison is stricter and fairer: it compares like with like (interactive use, same effort level) and tells you how sure it is. The pricing table also knows Fable 5.2 and the Mythos models.

### Changed
- **The baseline is interactive use only.** SDK-driven runs (entrypoints starting with `sdk`) no longer enter the baseline, because they behave very differently from a person working in a terminal, an app or an editor. The card shows how many SDK replies were left out. Verdicts can change, see [MIGRATION.md](MIGRATION.md).
- **The baseline is matched to the ID side's effort level.** Each row reweights the baseline to the ID side's mix of that row's own base (for example tool replies, Bash commands or prompts) over the effort levels both sides have. The per-session rows are not reweighted. Replies at an effort level the baseline lacks are not compared; the card says how many.
- **Significance counts sessions, not replies.** Every row shows a 95% interval and a p-value that treat the session as the unit. The verdict "Behaviour changed" now needs at least 2 of the 4 behaviour measures with a change of 40% or more and p < 0.05, plus at least 200 replies and at least 5 sessions on each side (fewer sessions, or fewer than 2 behaviour measures with enough events to compare, read "Too little data").
- **Replies more than 7 days after the session start are dropped.** A session carries the ID it started with, which can change on the server later. The card shows how many replies this removed.
- **Medians of single replies are now within about 2%** (the histogram is finer than before).

### Added
- **"Per session" rows** on the comparison card: median cost, replies, prompts, tool calls and active minutes per session, plus cost per prompt.
- **"Quality proxies" rows:** tool calls ending in an error, repeated identical tool calls, tool calls you rejected, prompts that interrupted a reply, prompts that look like corrections, and edits of a file already edited. They are hints, not a quality verdict, and do not enter the verdict. Like cost per reply and cost per prompt, they show a change only with a base of at least 30 on each side (for example 30 tool calls) and, for a rate, at least 30 counted events on one side (for example 30 tool errors); otherwise the change reads "too few events".
- **`experiments.correction_words` in `config.json`** sets the words that mark a short prompt as a correction (default: a short list of English and German words, an empty list switches correction counting off).
- **Thinking tokens per effort level** as a table under the cards, per ID and model.
- **Caveats and the verdict rule on the card.** Every card prints its rule, the entrypoints and effort mix of both sides, and the caveats of the method.
- In the F2 screenshot mode the Experiments section shows only shortened IDs, without tooltips that carry the full ID.
- **Fable 5.2 and Mythos 5.2** in the pricing table: $8 / $40, cache reads $0.20 / MTok, cache writes $10 (5m) and $16 (1h).
- **Mythos 5.1 and Mythos 5** in the pricing table, at the same rates as Fable 5.1 and Fable 5. Mythos models have limited availability. Until now they fell through to the default estimate ($3 / $15). In the charts they show in the neutral colour for now, as Mythos has no colour family of its own yet.

### Fixed
- **Sonnet 5.5 cache reads cost $0.10 / MTok, not $0.20.** Like Opus 5.5, Sonnet 5.5 bills cache hits at 0.05x the base input price. Costs for Sonnet 5.5 sessions with a lot of cache reads go down accordingly.
- **Experiments comparison cards no longer cut off their table.** On wide screens three cards sat side by side and the 95% interval and p columns were hidden behind a scrollbar. Desktop screens now show two cards per row, wide enough for all six columns.
- **Steadier number columns in the Experiments section.** The two bounds of the 95% interval sit in fixed slots, so the ".." lines up from row to row. The thinking-token table is now one table for all models with the same effort columns throughout, and shows the mean on top with the reply count small below it.

## [1.4.2] - 2026-11-09

A switch for cleaner experiment screenshots, and an up-to-date README.

### Added
- **"Hide cards with too little data" switch in the Experiments section.** It sits above the comparison cards, shows how many cards it hides, and is remembered in your browser. Handy for a screenshot that only shows the IDs with a verdict. The switch only appears when there are cards of both kinds.

### Fixed
- **README brought up to date.** It now states the real minimum Python version (3.10, as `pyproject.toml` already required; it said 3.8), the cron example logs errors to the log file (the redirects were in the wrong order), and the feature list covers experiment IDs, the session totals row and column chooser, and the Pro / Max / Ultra plan names.

## [1.4.1] - 2026-11-09

The experiments timeline fits the screen.

### Fixed
- **Experiments timeline fits the screen.** The day cells shrink to fit the box, so on normal screens there is no horizontal scrollbar any more. Only on narrow screens does the timeline scroll, with a slim scrollbar in the theme colours, and it now opens at the newest days instead of the oldest.

## [1.4.0] - 2026-11-09

The Insights tab can now show whether a server-side experiment changed how Claude works for you, and the plan recommendation follows Anthropic's 2026-10-30 plan change (Ultra without a 5-hour limit).

### Added
- **Experiments section in Insights & System.** Anthropic runs server-side experiments on part of its users, and Claude Code writes the assigned experiment ID into the session logs. The new section "07 Experiments" shows a timeline (one row per ID, one cell per day), your current assignment per model, and a comparison card per ID and model (a model with very few replies under an ID, under 20, gets no card). Each card compares your replies under the ID with replies of the same model without a recorded experiment ID, using the baseline from within 14 days before and after the experiment's dates. Four measures are compared: replies with 2 or more tool calls, median Bash command length, median output tokens per reply, and the share of tool-using replies that start with text before the first tool call. Cost per reply is shown alongside for context and does not count towards the verdict. The verdict is "Behaviour changed" when at least 2 of the 4 measures differ by 40% or more and there are at least 200 replies on each side; otherwise it reads "No clear effect", or "Too little data" when either side has fewer than 200 replies. A measure only counts when at least 30 events back it (for example 30 Bash commands on each side, otherwise its change reads "too few events"), and when fewer than 2 measures can be compared the verdict is "Too little data" as well. Medians are approximate (histogram-based, within about 10%). The section always covers the full period and ignores the date and project filters.
- **Experiment column in the session table.** It shows the first three characters of each experiment ID a session ran under (the full ID is in the tooltip), or a dash for none, and is on by default. If you saved your own column selection earlier, turn the column on in the gear menu.
- IDs in both log formats (plain 16-character IDs and the longer `v1.` form) are recognized as the same experiment.
- Only main-thread replies count. Subagent replies are left out, so a long agent run does not skew the comparison.

### Changed
- **The plan recommendation knows Anthropic's 2026-10-30 plan change.** Max 20x is now called Ultra and has no 5-hour limit for verified accounts, Max 5x is now called Max. The dashboard shows the new names (your data and config keep working with the old ones), and from 2026-10-30 on, 5-hour windows no longer count as Ultra limit hits or feed the Ultra calibration. Ultra's weekly allowance is now 10x Pro instead of 20x, applied to weeks starting on or after that date. Everything before 2026-10-30 is calculated as before. New config key `ultra_no_5h_limit_from` (default `"2026-10-30"`, set `null` if your Ultra account is not verified and still has a 5-hour limit), and the plan names `"Max"` and `"Ultra"` are accepted in `plan_history`.

## [1.3.0] - 2026-10-14

The session table gets a totals row and stays usable on any screen width.

### Added
- **Totals row in the session table**, on the Sessions tab and on every project page. It sums up all sessions in the current filter (period, project, source and session filters), not just the visible page: duration, messages, all token columns, cost, tool calls and so on. Cache efficiency is recomputed from the summed tokens instead of adding percentages, the project column shows how many distinct projects are included, and text columns stay empty. The row follows your column selection, so turn on "Total Tokens" for the overall token count. No more exporting to a spreadsheet just to add up a column.

### Changed
- **The horizontal scrollbar is always in view.** The table now scrolls inside a box that fits the screen, so the scrollbar no longer sits below row 50 where you never saw it. The header row and the totals row stay in place while you scroll. Phones keep the plain page scroll.
- **Wider pages.** Dashboard, project and session pages now grow up to 1680px instead of 1400px, so on wide screens the default table columns fit without scrolling.

## [1.2.4] - 2026-10-09

A pricing update for the new Haiku 5.5, the first model priced by prompt length.

### Added
- **Haiku 5.5** in the pricing table: $0.10 / $0.50, cache reads $0.01 / MTok, cache writes $0.125 (5m) and $0.20 (1h). Haiku 5.5 is the first model priced by prompt length: a request whose prompt is over 100,000 tokens (cache reads and writes included) pays 5x on every token type, output included. The dashboard picks the rate for each request on its own. Without an entry it fell through to the default estimate ($3 / $15).

### Fixed
- The cost breakdown by token type (input, output, cache reads, cache writes) and the cache savings are now summed per request instead of recomputed from token totals, so they add up to the total cost exactly. Before, they could drift by a few cents.

## [1.2.3] - 2026-10-08

A bugfix release for the Insights tab: Skills, Hooks and Git Ops now follow the date range, and hooks from newer Claude Code versions are counted again.

### Fixed
- **Skills Used, Hooks and Git Ops** now follow the date range and project filter. They always showed all-time totals, no matter which range was selected. (#27)
- **Hooks** are counted again for sessions from Claude Code 2.1.9x (April 2026) on. Newer versions log hooks in a different format, which the dashboard did not read, so the card stopped counting in April. Hooks that finish without output are no longer logged by Claude Code at all and cannot be counted; the card now says so. Stop and async hooks are counted in full. (#28)
- Hooks without a matcher, such as Stop or UserPromptSubmit, no longer show their name twice ("STOP Stop") in the Hooks card.

## [1.2.2] - 2026-10-04

A pricing update for the new Sonnet 5.5.

### Added
- **Sonnet 5.5** in the pricing table: $2 / $10, cache reads $0.20 / MTok, cache writes $2.50 (5m) and $4 (1h), the same rates as Sonnet 5. Without an entry it fell through to the default estimate ($3 / $15). In the charts it takes the strongest Sonnet shade automatically; Sonnet 5 moves one step lighter.

## [1.2.1] - 2026-09-22

A pricing update. Two new models get their own rates, and Sonnet 5 goes back to its launch price.

### Added
- **Opus 5.5** in the pricing table: $4 / $20, cache reads $0.20 / MTok, cache writes $5 (5m) and $8 (1h). Without an entry it fell through to the default estimate ($3 / $15). In the charts it takes the strongest Opus shade automatically; Opus 5 moves one step lighter.
- **Fable 5.1** in the pricing table. Same base rates as Fable 5 ($10 / $50), but cache reads are priced at 0.025x base input ($0.25 / MTok) instead of the usual 0.1x. Previously the model fell through to the default estimate and was undercounted by roughly 70%. (#24)

### Fixed
- Sonnet 5 is back at $2 / $10. The increase to $3 / $15 scheduled for 2026-09-01 was cancelled by Anthropic; the launch rate is now the standard price. (#25)

## [1.2.0] - 2026-08-27

A performance release. Nothing about the dashboard itself changes; runs simply stop repeating work they have already done.

### Added
- Incremental scans. The merged session state is cached in `.cache/`, so a repeat run only re-reads the transcripts whose size or timestamp moved, and only re-renders the detail pages whose content changed. On a large history a repeat run costs roughly a quarter of a full one. The cache is keyed on a hash over the source tree and your `config.json`, so editing the parser, adding a model to the pricing table or changing your plan history discards it automatically. (#22, #23)
- `--verify-cache` parses the corpus warm and cold and reports any session where the two disagree. Sessions that are still being written while it runs are detected and excluded, so it can be used on a machine that is in use.
- `--no-cache` forces a full scan and leaves the cache untouched. Deleting `.cache/` is always safe; the next run rebuilds it.

### Changed
- The session and project page templates are built once per run instead of once per page. Thanks to @jkopczyn. (#21, #22)
- Session transcripts are located from an index built during the parse pass instead of searched for once per detail page. With a `sudo_user` source configured, that search cost two subprocess round trips per session, paid even by sessions living in the primary directory. (#23)
- Unchanged detail pages keep their timestamp along with their contents, so an `rsync`-based deploy skips them as well and the upload shrinks with the run.
- The transcript parse loop no longer catches bare `Exception`. Only I/O errors are swallowed, so a bug in the parsing code surfaces as a crash instead of as a silently empty or partial data set.

## [1.1.0] - 2026-08-25

### Added
- A dedicated colorblind chart palette (validated for protanopia and deuteranopia, with wide lightness steps between versions of one model family), enabled with `"palette": "colorblind"` in `config.json`. (#19)
- The favicon now ships with the repo (SVG plus PNG fallback) and is written to `public/` on every build; `"favicon": "indigo"` in `config.json` selects the previous indigo look.
- All chart colors are CSS tokens (`--vc-cat-*`, `--vc-model-*`, `--vc-series-*`), so `custom.css` can recolor every chart; see `custom.css.example`.
- A legacy palette preset in `custom.css.example` that restores the pre-1.1.0 chart colors, and a palette guide with a comparison image in the README.

### Changed
- The default chart palette is more distinguishable: eight categorical hues in a validated order, one hue per model family with four lightness steps per version, and a status pair that no longer collides with the accent. Per-model colors are now derived automatically, so new model releases need no color table entry. (#19)
- Doughnut segments and stacked bars are separated by a thin panel-colored gap.

### Fixed
- Switching the theme now repaints the charts on the dashboard and the session pages instead of leaving them in the previous theme's colors until the next filter change.
- `Opus 5` and `Sonnet 5` no longer share a color with older versions of their family. (#19)

## [1.0.0] - 2026-07-31

First stable release. Consolidates the dashboard into five focused tabs with a light and dark theme, adds a currency and token metric toggle, cache anomaly detection, and a calibrated plan recommendation, and re-bases every time series on the day the work actually happened. It also corrects several cost and rate calculations that were wrong in 0.8.x.

### Breaking changes

- The seven dashboard tabs are consolidated into five. The `#projects` and `#agents` deep links now resolve to `#activity` and `#insights`; existing bookmarks keep working.
- `extract_stats.py` no longer contains the HTML, CSS and JavaScript, which moved to `templates/`, and the computation logic moved to the `claudestats_core` package. Anyone maintaining a patched fork should re-apply their changes rather than merge. See [MIGRATION.md](MIGRATION.md).
- Existing `config.json` files keep working unchanged, including the older `cost_eur` key.

### Added

#### Tab consolidation (7 to 5)
- Consolidated into five tabs: **Token & API Value**, **Plan & Billing**, **Activity & Projects**, **Sessions**, **Insights & System**; Projects merged into Activity, and Agents became a numbered sub-section under Insights & System
- A modern visual reskin across the dashboard and the project / session detail pages, with light / dark themes
- KPI-strip polish, a billing bar, and week markers on the time-series charts

#### Metric toggle (USD / billing currency / Tokens)
- The daily by-model chart and the cumulative chart switch between USD, your billing currency, and consumed tokens (input + output, cache excluded); the money KPI follows the selected currency
- Currency view converts with your per-billing-cycle exchange rate

#### Cache anomaly detection
- Separates TTL / idle-gap cache flushes from no-gap invalidations (the cache was rebuilt although it cannot have expired - the pattern behind the 2026 Claude Code cache bugs); compaction rebuilds are excluded to avoid false alarms
- Per-session `cache_nogap_flush_count` / `cache_nogap_rewrite_tokens`, a cache-anomaly card, and a "Cache Flushes per Day" early-warning chart on Insights & System

#### Activity-time and per-day attribution
- Daily costs, tokens, and messages are bucketed by the day work actually happened; a session spanning midnight is split across the real calendar days (`split_session_by_day` with a reconciliation invariant)
- Per-session `per_day` breakdown serialized; subagent per-day spend folded into the parent session
- New `daily_tokens` and `daily_cache_efficiency` series in `dashboard_data.json`
- Hour-of-day and weekday distributions are attributed to each message's actual local timestamp (per-session `hour_hist` / `weekday_hist`) instead of the session start
- Activity-based session date filter, so a multi-day session matches every day it was active
- Multi-day sessions badged in the session-table date column
- Chat replay inserts day-divider rows, and the date carries into the copy-to-clipboard and Markdown exports

#### Limits and recommendation redesign
- Plan-tier recommendation now uses a recent-cycle hit quota instead of all-history zero tolerance, with a calibration floor and an explicit "recommendation basis" line (shows the merged-event count)
- 5-hour-window hit counting anchored to the pre-gap window; anchored windows always count as hits on the active and cheaper tiers; cap estimate floored at the most expensive limit-free window
- Limit events from parallel sessions and retries are deduplicated

#### Pricing and model naming
- Added **Fable 5** and **Opus 4.8** to the pricing table and chart palette
- Display names are derived from the raw model id (`derive_model_display`), so unseen `claude-*` ids render a sensible label and surface the estimated-pricing notice

#### Refreshed dashboard design
- Unified monospace aesthetic across all surfaces (dashboard, project detail, session detail) with a single restrained accent color
- New top bar with brand mark, user / plan / range readout, and a 2-state theme toggle (light / dark) plus system-preference fallback
- 5-cell KPI strip pinned to the top of the dashboard
- Wider 1400 px shell with consistent alignment between top bar, KPI strip, tabs, and content panels
- Hash-based tab routing: deep links like `index.html#sessions` are bookmarkable and survive a full page reload
- Theme-aware Chart.js defaults: grid colors, fonts, and animations match the surrounding panel in both themes
- Single-accent palette on charts, heatmap, and distribution bars to replace the older multi-color scheme
- Section sub-headers added on the Insights tab; charts on single-metric panels no longer render redundant legends
- Project and session detail pages re-skinned to match the dashboard

#### Limits and plan recommendation (Plan & Billing section, beta)
- Detects rate-limit events from session transcripts using both explicit API error markers and heuristic signals; the legend distinguishes the two
- Server-overload events are separated from user rate-limit hits so 529s do not inflate your usage stats
- 5-hour rolling window tracker (matches how Anthropic actually enforces the cap) with a weekly hit-count summary, replacing the previous monthly percent-of-limit readout
- Idle-gap correlation panel: shows how often sessions stalled and groups gaps into short / medium / long buckets to make blocked sessions visible
- Gap-based cache-flush detection: separates real cache misses from natural idle gaps
- Plan-tier recommendation with empirical calibration: per-day tier capacity (no longer per-cycle, which previously produced misleading 400%+ readouts)
- Marked beta in the UI to signal the heuristics may still drift

#### Session filtering
- New filter module mounted on both the dashboard Sessions tab and the per-project detail page
- Expandable filter panel with range sliders and number inputs for: tokens (input / output / cache), cost, duration, message count, cache efficiency, tool calls, agent dispatches, and error count
- One-click presets (e.g. "long sessions", "high-cost sessions") and a free-text search across project / session id
- Active-filter chip row with per-chip clear; full filter state is persisted across reloads
- Slider ranges auto-fit to the actual session pool, with log scaling for skewed attributes
- All translation strings ship in English and German

#### Session table
- Replaces the older session card list everywhere (dashboard + project detail)
- Column resize, multi-column sort, lightbox details, and CSV / XLSX export
- Per-session detail page link, chat replay link, and bulk-Markdown-ZIP download

#### Per-tool token attribution
- Each session attributes output tokens and cost across the tools that produced them, plus a separate reasoning bucket
- Per-session sidebar shows the per-tool absolute + percentage split, including reasoning-only sessions
- Dashboard donut chart for output-token share by tool + reasoning, recomputed live when the time / project filter changes
- Largest-remainder allocation in the attribution helper prevents fractional drift across many small turns

#### User theming via `custom.css`
- The dashboard, project detail, and session detail pages now load an optional `public/custom.css` after the inlined styles
- `public/custom.css.example` is shipped on every build with the full set of overridable design tokens (both the new design and the legacy chart variables) for light, dark, and `prefers-color-scheme`
- A user-edited `public/custom.css` is preserved across rebuilds; the builder only creates it when missing
- See "Custom Styling" in the README

#### Other additions
- Cache-efficiency per-day box plot on the Token & API Value tab to surface day-over-day variance
- Per-session cache-efficiency badge and flush counter
- Theme-aware session-flow canvas: container, node fill, grid, and icons all switch with the theme
- Footer now reads consistently at 13 px across the site
- `config.json` accepts `cost_local` + `currency_symbol` for any currency (the legacy `cost_eur` key keeps working)

### Changed
- refactor: Domain logic extracted as stdlib-only package `claudestats_core` (pricing, attribution, classify, anomalies, limits, sessions, plan_analysis, aggregate). `extract_stats.py` remains CLI driver and re-exports all names; behavior is byte-identical to the pre-refactor implementation, confirmed via regression testing.
- In-progress billing period is framed with its real end date plus a projected end-of-cycle API value and ROI
- Configurable `plan_capacity_override_pro_usd` to override the empirical Pro-tier capacity used by the recommendation
- Plan-cost math is now filter-aware: switching the time range or project filter scales the plan-cost reference accordingly
- Session-flow visualization no longer auto-plays; toolbar buttons are unified and theme-aware
- The Insights tab uses a masonry layout to fill grid gaps
- Generated dashboard now shows the report generation timestamp instead of a live clock
- Anonymization (F2) extended to source labels, plan titles, skills, hooks, and project memories; the toast lives in the new design system

### Fixed
- Dashboard pages no longer break when served behind a SPA catch-all that produces nested `/sessions/` paths
- Inline `<script>` JSON payloads escape `</` to prevent premature script termination
- Subagent types resolve correctly via the new `agent-<id>.meta.json` sidecar in addition to the parent `toolUseResult`
- Light-mode regressions in the Limits & Recommendation section, Idle-Gap panels, and several legacy components
- Dark-mode doughnut chart borders and chart grid colors persist across theme toggles
- Multi-byte hex grid in the session-flow canvas now renders correctly under both themes

### Internal
- HTML, CSS, and JS for all three page types extracted into `templates/` and assembled at build time
- New session-filters and session-table components live under `templates/components/`

## [0.8.1] - 2026 (hotfix)

- Guarded against a feedback loop where a SPA catch-all could serve the dashboard at a path with repeated `/sessions/` segments, causing relative "Chat" links to keep extending the URL
- Switched per-session JSON extraction from regex to `indexOf` to tolerate edge cases in the embedded payload

## [0.8.0]

- Bulk session Markdown export (ZIP) plus per-session Markdown download button
- Skip empty assistant turns in the Markdown export
- Hide "Chat" link for sessions that have no transcript
- Added Claude Opus 4.7 to the pricing table and chart palette
- Configurable per-source labels and an optional `sudo_user` field for cross-user reads
- Hardened sudo helpers (added `-n`, error logging, `cwd=/` to avoid find cwd-restore errors)
- Documented the 30-day session-cleanup risk and the required `cleanupPeriodDays` setting

## [0.7.0]

- Filter-aware plan costs and KPI tooltips: changing the time-range filter rescales plan-cost reference values proportionally
- Mobile-responsive dashboard layout
- Major Session Flow upgrade: User node + bidirectional message flow, Chat node with wait-time indicator, response edges, live message and tool-call counters during auto-play, fullscreen toggle, two-line node labels, auto-scrolling chat panel during playback

## [0.6.1]

- Plan cost is now sliced into monthly billing cycles so annual plans no longer dominate a single chart bar
- Documented the multi-user `additional_sources` configuration

## [0.6.0]

- `additional_sources` support: merge multiple `~/.claude` directories (multi-user) with automatic session deduplication
- Full token breakdown (input / output / cache-read / cache-write) surfaced in the dashboard

## [0.5.0]

- Error breakdown by category and tool on a new Agents tab
- Subagent prompt extraction
- Empty-session filter

## [0.4.0]

- Agents tab with subagent type distribution, error breakdown, and task management
- Telemetry, project-memory, and task loaders
- Per-project pages extended with memories and a workflow timeline

## [0.3.0]

- Per-session chat replay pages with role filter and copy-to-clipboard
- Per-project detail pages with session lists
- GitHub-style activity heatmap on the Activity tab
- Cache-efficiency display on the Token & API Value tab
- Skills and hooks display on the Insights tab
- Global project-name filter next to the time-range buttons

## [0.2.1]

- Complete model pricing table for all Claude generations

## [0.2.0]

- Global time-range filter (All / 7D / 30D / 90D / 1Y) with version embedded in the generated HTML

## [0.1.0]

- Initial public release: KPI dashboard, daily / cumulative cost charts, model distribution, basic activity and project breakdowns
