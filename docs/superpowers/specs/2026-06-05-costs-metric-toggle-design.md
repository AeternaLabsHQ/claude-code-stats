# Costs Tab Metric Toggle (USD | Local Currency | Tokens)

**Date:** 2026-06-05
**Status:** Approved by user (brainstorming session)

## Problem

The "Token & API Value" tab shows API value per day by model and a cumulative
API value curve, both USD-only. Two things are missing:

1. **Daily token consumption** - there is no per-day view of tokens consumed,
   even though the data exists per session in `model_breakdown`.
2. **Local currency** - the Plan & Billing tab can switch between USD and the
   user's configured billing currency, but the Costs tab cannot.

## Solution Overview

A three-state metric toggle **`USD | <symbol> | Tokens`** in the Costs tab
header, replacing the static `daily · USD` text in `#vcCostMeta`
(`templates/dashboard.html:95`). It switches the two main charts:

- **chartDailyCost** (stacked bar by model, `templates/dashboard.js:961`)
- **chartCumCost** (cumulative line, `templates/dashboard.js:979`)

Frontend-only change. No backend export changes; all data needed is already
in the frontend (`s.model_breakdown` per session, `D.plan` periods for FX).

## Decisions Made

| Question | Decision |
|---|---|
| Which tokens count? | **Input + output only**, no cache reads. Cache reads dominate raw volume (>95%) and would flatten the chart. |
| Toggle scope | Both `chartDailyCost` and `chartCumCost` switch together. |
| Local currency in Costs tab? | Yes - three-way toggle, despite the API value being USD-denominated list pricing. |
| FX rate | **Same mechanism as Plan & Billing**: per-cycle rate `plan_cost_local / plan_cost_usd` from the period matching the date; current cycle's rate as fallback for dates outside known periods. Nothing new invented. |
| "API Value by Token Type" chart + model table | **Stay USD.** Per-date FX on range aggregates would be imprecise, and the table already has token columns. Possible later extension. |
| Persistence | None - mode resets on reload, consistent with `planCurrencyMode`. |
| KPI strip (added 2026-06-05 after browser review) | **API EQUIVALENT card follows the currency mode**: value converts per-day (matches the daily chart sum), "paid" uses actual local plan costs per period (`calcFilteredPlanCost(dates, true)`). Tokens mode keeps the USD display (money metric; tokens have their own card). Toggle onclick re-renders the KPI strip. |

## Design

### State

```js
let costMetricMode = 'usd'; // 'usd' | 'local' | 'tokens'
```

Module-level, next to `planCurrencyMode` (`templates/dashboard.js:7`).

### Toggle UI

Built into `#vcCostMeta` following the `mkBtn` pattern from `renderPlan()`
(`templates/dashboard.js:1594-1611`): inline-flex button group, active button
filled with `var(--accent)`.

- Buttons: `USD`, `<currency_symbol>`, `Tokens` (label localized).
- The currency button renders **only if** `D.plan && D.plan.currency_symbol`
  and at least one FX rate is derivable (some period or current billing has
  both `plan_cost_local` and `plan_cost_usd`). Otherwise the toggle is just
  `USD | Tokens`.
- `onclick`: set `costMetricMode`, destroy `charts.dailyCost` +
  `charts.cumCost`, re-render only those two charts (factored into a helper,
  see below).

### Data: daily token aggregation

In `applyFilter()` next to the existing `dailyCostMap` loop
(`templates/dashboard.js:413-429`):

```js
dailyTokenMap[s.date][model] += (d.input_tokens || 0) + (d.output_tokens || 0);
dailyTokenMap[s.date].total  += same;
```

Produces `F.daily_tokens` with the same shape as `F.daily_costs`
(`{date, total, [modelName]: n}`), aligned on the same `allDates` axis.
`F.cumulative_tokens` is built next to `F.cumulative_costs`
(`templates/dashboard.js:480`), shape `{date, tokens}`.

Token mode therefore respects every existing filter (range buttons, quick
filter) for free, because it aggregates from `F.sessions`.

### FX conversion (local currency mode)

Render-time conversion, no duplicated data structures:

```js
function fxForDate(dateStr) {
  // find p in D.plan.periods where p.start <= dateStr <= p.end
  //   and p.plan_cost_local && p.plan_cost_usd -> local/usd
  // fallback 1: current_billing.plan_cost_local / plan_cost_usd
  // fallback 2: most recent period with a derivable rate
  // (button visibility guarantees at least one of these exists)
}
```

Dataset values become `(d[m] || 0) * fxForDate(d.date)` in local mode.
This mirrors how `extract_stats.py:2774` derives per-cycle FX
(`fx = plan_cost_local / plan_cost_usd`), so daily numbers stay consistent
with the Plan & Billing per-period figures.

### Rendering

Extract the two charts from `renderCosts()` into `renderCostCharts()` so the
toggle can rebuild them without re-running the token-type chart, pricing
notice, and model table (re-running the table append loop would duplicate
rows). `renderCosts()` calls `renderCostCharts()` plus the rest, unchanged
in behavior.

Per mode, `renderCostCharts()` selects:

| | usd | local | tokens |
|---|---|---|---|
| Daily data | `F.daily_costs` | `F.daily_costs` × fx | `F.daily_tokens` |
| Cumulative data | `F.cumulative_costs` | × fx | `F.cumulative_tokens` |
| Y-axis title | `USD` | `currency_symbol` | `Tokens` |
| Value format (tooltips + y ticks) | `fmtUSD` | number + symbol (like `fmtPlanMoney`) | `fmtTokens` |
| Daily chart `<h3>` | `costs.daily_cost` | `costs.daily_cost` | `costs.daily_tokens` (new) |
| Cumulative `<h3>` / dataset label | `costs.cumulative` / `costs.cumulative_label` | same | `costs.cumulative_tokens` / `costs.cumulative_tokens_label` (new) |

The two `<h3>` titles get ids (`chartDailyCostTitle`, `chartCumCostTitle`) in
`dashboard.html` so JS can swap their text; the build-time `__L_*__`
placeholder text remains as the initial (usd) state.

Tooltip and y-tick callbacks are added to both charts so token mode shows
`1.2M`-style values and currency mode shows formatted money instead of raw
floats.

### Locale additions (`locales/en.json`, `locales/de.json`)

New keys under `costs`:

- `daily_tokens` - "Tokens per Day by Model" / "Tokens pro Tag nach Modell"
- `cumulative_tokens` - "Cumulative Tokens" / "Kumulierte Tokens"
- `cumulative_tokens_label` - "Cumulative (tokens)" / "Kumuliert (Tokens)"
- `toggle_tokens` - "Tokens" / "Tokens" (button label)

`USD` and the currency symbol need no locale entries (symbols, not words).

### Edge cases

- **No plan configured / no currency**: currency button hidden; `USD | Tokens`.
- **Date outside all known periods** (before first plan, gaps): current
  cycle's FX as fallback - explicitly accepted by user ("like Plan & Billing,
  nothing new").
- **Period without local cost** (`plan_cost_local` null): that period yields
  no rate; fall through to the fallback chain (current billing rate, then
  most recent period with a rate).
- **Sessions without `model_breakdown`**: contribute 0 tokens, same as they
  contribute 0 to per-model cost today.
- **Mode = 'local' but FX becomes unavailable after filter change**: cannot
  happen - FX availability depends on `D.plan` (unfiltered), checked once at
  toggle build time.

## Testing

- `node --check` syntax preflight on `templates/dashboard.js` (existing local
  smoke-test pattern).
- Headless Chromium smoke test (Playwright-cache Chromium): build dashboard,
  open it, click through all three toggle states, assert no console errors
  and that the y-axis title changes.
- Visual check by user in browser (per project convention before merge).

## Out of Scope

- Currency/token conversion of "API Value by Token Type" chart and the model
  detail table.
- Persisting the toggle mode.
- Backend changes (`extract_stats.py` daily token export stays unexported).
- Cache-read token visualization (covered elsewhere by cache-efficiency
  charts).
