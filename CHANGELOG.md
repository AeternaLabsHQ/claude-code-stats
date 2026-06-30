# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - v2 (Dashboard Rethink)

Builds on the 1.0.0 feature set below. A full dashboard rethink that consolidates the eight v1 tabs into five focused surfaces with a "Modern SaaS" reskin, adds a currency/token metric toggle, no-gap cache-anomaly detection, and a calibrated plan-tier recommendation, and re-bases all time-series on the day work actually happened. Not yet tagged.

### Added

#### Dashboard rethink (8 tabs to 5)
- Consolidated into five tabs: **Token & API Value**, **Plan & Billing**, **Activity & Projects**, **Sessions**, **Insights & System**; the former standalone Agents, Errors, Tools, Storage, and Workflows surfaces became numbered sub-sections under Insights & System
- "Modern SaaS" visual reskin across the dashboard and the project / session detail pages, with light / dark themes
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

### Changed
- In-progress billing period is framed with its real end date plus a projected end-of-cycle API value and ROI
- Configurable `plan_capacity_override_pro_usd` to override the empirical Pro-tier capacity used by the recommendation

---

## [1.0.0] - Unreleased

First stable release. Brings a complete visual refresh, a new Limits / Plan-recommendation tab driven by gap analysis of session transcripts, multi-attribute session filtering, a unified session table, per-tool token attribution, and user theming via `custom.css`.

> **License change:** The project relicensed from MIT to **AGPL-3.0** with this release. If you fork and run a modified version on a network server, you must make the source of your modifications available to users interacting with it. See [`LICENSE`](LICENSE).

### Added

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

#### Limits and plan recommendation (new tab, beta)
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
- Cache-efficiency per-day box plot on the Costs tab to surface day-over-day variance
- Per-session cache-efficiency badge and flush counter
- Theme-aware session-flow canvas: container, node fill, grid, and icons all switch with the theme
- Footer now reads consistently at 13 px across the site
- `config.json` accepts `cost_local` + `currency_symbol` for any currency (the legacy `cost_eur` key keeps working)

### Changed
- Plan-cost math is now filter-aware: switching the time range or project filter scales the plan-cost reference accordingly
- Session-flow visualization no longer auto-plays; toolbar buttons are unified and theme-aware
- The Insights tab uses a masonry layout to fill grid gaps
- Generated dashboard now shows the report generation timestamp instead of a live clock
- Anonymization (F2) extended to source labels, plan titles, skills, hooks, and project memories; the toast lives in the new design system

### Fixed
- Dashboard pages no longer break when served behind a SPA catch-all that produces nested `/sessions/` paths
- Inline `<script>` JSON payloads escape `</` to prevent premature script termination
- Subagent types resolve correctly via the new `agent-<id>.meta.json` sidecar in addition to the parent `toolUseResult`
- Light-mode regressions on the Limits tab, Idle-Gap panels, and several legacy components
- Dark-mode doughnut chart borders and chart grid colors persist across theme toggles
- Multi-byte hex grid in the session-flow canvas now renders correctly under both themes

### Internal
- HTML, CSS, and JS for all three page types extracted into `templates/` and assembled at build time
- New session-filters and session-table components live under `templates/components/`
- `VERSION` should be bumped to `1.0.0` before tagging

---

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
- Cache-efficiency display on the Costs tab
- Skills and hooks display on the Insights tab
- Global project-name filter next to the time-range buttons

## [0.2.1]

- Complete model pricing table for all Claude generations

## [0.2.0]

- Global time-range filter (All / 7D / 30D / 90D / 1Y) with version embedded in the generated HTML

## [0.1.0]

- Initial public release: KPI dashboard, daily / cumulative cost charts, model distribution, basic activity and project breakdowns
