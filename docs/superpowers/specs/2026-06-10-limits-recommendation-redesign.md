# Design: "Limits & Recommendation" Redesign

Date: 2026-06-10
Branch: feature/dashboard-rethink-v2
Status: Approved (brainstorm, visual companion). User AFK → implement to completion.

## Problem

The "Limits & Recommendation" section on the Plan & Billing tab has three issues:

1. The actual recommendation (current tier + recommended tier) sits at the **bottom**
   of the section, inside a brown box. It should be the **first** thing seen.
2. The brown box (`.plan-rec-summary`, tinted with `--vc-accent-soft` = terracotta)
   reads as muddy. It should stand out using the theme's **green** (`--vc-pos`) accent.
3. The two per-cycle hit tables ("5h-limit hits" / "weekly-limit hits") are plain
   number grids that look unappealing and are hard to scan.

## Goals

- Promote the recommendation to a prominent card at the top of the section.
- Re-skin it with the green positive accent (whole-panel tint, green left border) — variant A.
- Replace the plain tables with a **heatmap matrix** that is scannable at a glance,
  keeps the numbers, and tells the story "which tier holds / where you over- or
  under-provisioned".

## Out of scope

- No change to how hits/caps/recommendation are *computed* (calibration, tolerance,
  cap estimation). Only one small additive backend field set (per-cycle `active_tier`
  + `switch_arrow`) reusing the existing tolerance constants. No new thresholds.
- Limit-Events timeline (`renderLimitsEventTimeline`) stays as is.

## New section order

Inside the `#tab-plan` "Limits & Recommendation" section:

1. **Recommendation card** (new, top) — `#limitsRecCard`
2. **Limit Events** timeline — `#limitsEventTimeline` (unchanged)
3. **Per-cycle hit heatmaps** (5h + weekly) — `#limitsPlanRec`
4. **Fine print** — calibration (5h + weekly) + disclaimer, muted, under the heatmaps

## Component 1 — Recommendation card (variant A)

Green-tinted panel, green left border (`3px`), at the top of the section.

- Label "Empfehlung" + recommended tier as large green text.
- If `recommended_tier == current_tier`: show an "optimal" state (e.g. "Du bist
  optimal — Max 20x") instead of a switch, no alarm.
- If `recommended_tier == null` ("no tier holds without hits"): show that message,
  neutral (not green).
- Sub-line: "Aktueller Tarif: {current_tier} · Basis: {rec_basis}".
- Colors: `--vc-pos` / `--vc-pos-soft` (light `#1f9d63` / dark `#34c77f`).
  Green sits on the actionable value; the panel tint is soft.

## Component 2 — Hit heatmap (5h + weekly)

A matrix per metric. Rows = billing cycles (+ totals row). Columns =
`Pro · [gutter] · Max 5x · [gutter] · Max 20x`. The gutter columns are narrow
(~20px), normally empty, and exist so the directional arrow has a clean place to
live (keeps value cells uncluttered).

Per cell:
- value `0` → dim dot `·` (recedes).
- value `>0` → number on a severity-tinted background:
  - `1–2` faint amber, `3–9` amber/orange, `10+` red (theme accent/neg ramp).
- **Recommended column** (`recommended_tier`): inset green frame on every cell of
  that column; header labelled "empfohlen" (green). Data-driven — moves with the
  recommendation.
- **Current column** (`current_tier`): header labelled "aktuell".
- **Active cell** per row (column = that cycle's `active_tier`): subtle neutral
  inset ring — **except** when it coincides with the recommended column (then the
  green frame already marks it; no double border).
- **Switch arrow** in the gutter adjacent to the active cell, pointing toward the
  recommended column (see rule below):
  - downgrade → green `←`
  - upgrade → amber `→`
- Vertical rhythm: `border-spacing: 0 4px` (rows breathe; gutters stay tight).
- Totals row: bold, no arrows/rings.

### Switch-arrow rule (the one domain decision — reuses existing tolerance)

For each cycle, with `A = active_tier`, `R = recommended_tier` (global), tier order
`Pro < Max 5x < Max 20x`, and a cycle-local "holds" test that reuses the existing
constants:

```
holds(cycle, tier) :=
    tier_5h_hits[tier]     <= REC_5H_HIT_QUOTA * total_5h_windows   (0.05)
AND tier_weekly_hits[tier] <= REC_WEEKLY_HIT_ALLOWANCE              (1)
```

Arrow:
- `R is None` or `A == R` → **no arrow**.
- `price(R) < price(A)` (recommended cheaper = **downgrade**) AND `holds(cycle, R)`
  → green `←` toward R.
- `price(R) > price(A)` (recommended pricier = **upgrade**) AND **not** `holds(cycle, A)`
  → amber `→` toward R.
- else → no arrow.

Validated against real data (current=Max 20x, recommended=Max 5x): arrows land on
exactly the two `Max 20x` cycles (2026-04, 2026-05) and nowhere else — matching the
user's stated expectation. No new threshold invented; only the existing
`REC_5H_HIT_QUOTA` / `REC_WEEKLY_HIT_ALLOWANCE` are reused per-cycle.

## Data changes (`extract_stats.py`)

Per `rec_cycles` entry, add:
- `active_tier`: `_normalize_tier_name(p["plan"])`.
- `switch_arrow`: `null | "down" | "up"`, computed in a pass after `recommended_tier`
  is known, via a new helper `_tier_holds_in_cycle(cycle, tier)` (reuses the two
  tolerance constants). Purely additive; nothing existing changes.

## Frontend changes

- `templates/dashboard.html`: add `<div id="limitsRecCard" class="vc-limits-section">`
  as the first child of the section (before `#limitsEventTimeline`).
- `templates/dashboard.js`:
  - `renderLimits()` also calls `renderRecommendationCard()` first.
  - new `renderRecommendationCard()` → builds variant-A card into `#limitsRecCard`.
  - rewrite the table builder in `renderPlanRecommendation()` into the heatmap
    (severity colors, gutters, recommended-column frame, active ring, arrows).
    Keep calibration + disclaimer as the muted fine print; drop the tier/recommendation
    lines from here (moved to the card). Remove the brown `.plan-rec-summary` box.
- `templates/dashboard.css`: styles for `.rec-card`, the heatmap table + cells +
  severity classes + gutter/arrow/active-ring/recommended-frame, fine print. Reuse
  `--vc-pos*` / `--vc-accent*` / `--vc-neg*`; no hard-coded one-off colors where a
  token exists.

## Verification

- `python3 -c "import ast; ast.parse(...)"` on extract_stats.py; small script asserting
  the arrow lands on the two Max 20x cycles on real data.
- `node -c templates/dashboard.js`.
- `python3 extract_stats.py` to rebuild `public/`, then `node tools/smoke_shot.mjs`;
  inspect the `plan` tab screenshot (light + dark).

## Notes / risk

- The arrow rule is the single domain assumption. It is isolated to one helper +
  one pass and clearly documented; trivial to adjust if the user wants different
  semantics.
- `dashboard.{html,css,js}` already carry unrelated WIP from the dashboard-rethink-v2
  branch; the implementation does not commit those. Only this spec is committed here.
