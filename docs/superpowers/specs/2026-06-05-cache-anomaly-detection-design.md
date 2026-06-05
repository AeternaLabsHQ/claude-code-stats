# Cache Anomaly Detection (No-Gap Flushes)

**Date:** 2026-06-05
**Status:** Approved by user (follow-up to the March cost analysis)

## Problem

Claude Code has had a series of cache regressions (TTL cuts, billing-word
invalidation "Bug A", resume invalidation - see the May 2026 Medium timeline).
The dashboard already surfaces TTL/idle-gap damage (`cache_flush_count`,
idle-gap overhead card), but **mid-work cache invalidations with no idle gap**
(the Bug-A pattern) are invisible: `_detect_cache_flushes` only counts turns
whose gap exceeds the cache TTL.

Analysis on real data (2026-06-05, /tmp/inspect_nogap_flushes.py) found this
pattern at 3.5-8.4 events per 1000 turns (~$107 over six months) - small
today, but the user wants a **permanent early-warning signal** in case a
future regression spikes it (like gap flushes jumped 2 -> 135 from Feb to
March when the TTL was cut).

## Solution Overview

1. **Backend**: extend the existing gap-based flush detector to also classify
   **no-gap flushes** in the same pass: a post-buildup turn where the cache
   was rebuilt although there was no TTL-relevant pause. Two new per-session
   fields, exported to the dashboard JSON.
2. **Frontend (Insights > Cache & Tokens)**:
   - extend the relocated idle-gap bar into a two-line **cache anomalies
     card** (idle-gap overhead + no-gap flush events),
   - add a **"Cache Flushes per Day"** stacked bar chart (TTL/gap flushes vs
     no-gap anomalies) so future regressions are visible as a spike, fully
     range-filter aware.

## Detection (backend)

`_detect_cache_flushes(turns, has_1h_cache)` becomes a single pass returning
`{"gap_flushes": int, "nogap_flushes": int, "nogap_rewrite_tokens": int}`.

- **Gap flush** (UNCHANGED semantics - existing numbers must not shift):
  post-buildup, `gap >= TTL`, `cache_creation > 2 x rolling median`
  (`len(history) >= 3`, median over `history[:-1]`, floor 100).
- **No-gap flush** (new): same buildup/median/history conditions, but
  `gap < TTL` AND `cache_read < 50% of previous turn's cache_read`
  (read collapse - distinguishes true invalidation from legitimately large
  incremental writes). `nogap_rewrite_tokens` sums the `cache_creation` of
  those turns (the re-billed context).
- Validated against real logs: Mar 18 / Apr 39 / May 60 events; no false
  explosion.

Call site (extract_stats.py ~2342) sets:
- `sess["cache_flush_count"]` = gap_flushes (unchanged name/meaning)
- `sess["cache_nogap_flush_count"]`
- `sess["cache_nogap_rewrite_tokens"]`

Export whitelist (~3223) gains the two new fields.

Unit tests (new `tests/test_cache_flush_detection.py`): gap flush still
counted, no-gap flush counted on read-collapse, buildup turns never count,
large write WITHOUT read collapse does not count, <3 turns returns zeros.

## Frontend

- `recomputeIdleGapAggregate()` additionally sums
  `cache_nogap_flush_count` / `cache_nogap_rewrite_tokens` into
  `F.idle_gap_aggregate` (fields `nogap_flush_count`, `nogap_rewrite_tokens`).
- `renderIdleGapAggregateCard()` renders a second line:
  `CACHE-FLUSH ANOMALIES (NO GAP) ≈ N events · ≈ X Tokens · ≈ $Y` using the
  same `IDLE_GAP_OVERSPEND_USD_PER_M` rate constant (conservative Sonnet
  rate, consistent with the idle-gap line). Line hidden when count is 0.
  Card visibility: shown when idle-gap overspend OR no-gap count is > 0
  (previously: idle-gap only).
- New chart `chartCacheFlushDaily` (canvas in the cache subsection, below the
  daily cache-efficiency box plot): stacked bars per day,
  dataset 1 = gap flushes (TTL victims, muted color),
  dataset 2 = no-gap flushes (anomalies, accent/warning color),
  aggregated from `F.sessions` by session date (same attribution as all daily
  charts), so range/quick filters apply automatically.
  Per [[feedback_ui_visual_hierarchy]]: the actionable series (no-gap
  anomalies) gets the loud color, the expected/structural one (gap) muted.
- Locale keys (en/de) under a new `cacheFlush` section: card line label,
  chart title, two legend labels.

## Out of Scope

- Resume/Bug-B detection (hides in the buildup phase, needs different logic).
- Per-1000-turns normalization (absolute daily counts suffice; the gap series
  provides context).
- Session-detail view markers for no-gap flushes.
- Live alerting/notifications - the dashboard chart IS the alert.

## Testing

- `python3 -m pytest tests/` (new unit tests + 154 existing green).
- Rebuild + headless check: card shows two lines, chart exists with data,
  no console errors; screenshot for user review.
