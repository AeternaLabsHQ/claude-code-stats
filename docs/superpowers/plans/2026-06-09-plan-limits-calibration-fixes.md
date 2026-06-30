# Plan-Limits Calibration & Recommendation Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Plan & Billing limit calibration so the per-tier 5h/weekly caps stop being implausibly low and the plan recommendation stops returning "None" as an artifact.

**Architecture:** All math lives in `extract_stats.py` (pure helper functions + the `build_plan_analysis` orchestrator); the UI is `templates/dashboard.js` (vanilla JS, string-built HTML) with locale strings in `locales/de.json` / `locales/en.json`. We extract the inline anchor-matching and hit-counting logic into module-level pure functions so they are unit-testable, fix their semantics, and add a dedup pass over limit events plus a plausibility floor on the cap estimate. The recommendation rule changes from "zero hits over all history" to "last 3 cycles, ≤5% of 5h-windows, ≤1 weekly hit" (user decision).

**Tech Stack:** Python 3 (stdlib only), pytest, vanilla JS, JSON locales.

---

## Context for the implementer (read first)

**The five confirmed defects:**

1. **Fingerprint events anchor the wrong window.** `_detect_5h_fingerprint_events` (extract_stats.py:1701) sets `timestamp` = `gap_end` = the *resume* time after the limit pause. The anchor-matching loop in `build_plan_analysis` (extract_stats.py:3002-3010) uses `ev.get("timestamp") or ev.get("gap_end")`, so it matches the fresh *post-limit* window, whose cost has nothing to do with the cap. The limited window is the one containing `gap_start`.
2. **Explicit banner events often anchor nothing.** A window's `end_ts` is its last assistant-turn timestamp. The "you've hit your limit" banner arrives *after* that turn, so `start_ts <= ev_ms <= end_ts` fails. Matching must use the full `[start_ts, start_ts + 5h)` span.
3. **Duplicate limit events.** Parallel sessions emit the same banner within seconds (2026-03-24: 2 events 0.4s apart; 2026-04-14: 4 events in 2 min), and one event exists twice verbatim (2026-03-27T14:54:04.081Z). No dedup exists; `limit_event_count` per cycle is inflated (March shows 12, real incidents ≈ 5-7).
4. **No plausibility floor.** The empirical Pro base came out at $5.77/window, yet the data contains a $10.55 Pro window and $115+ Max-5x windows *without* limit events — the data refutes its own calibration. The cap on tier T must be at least the cost of the most expensive limit-event-free window on T.
5. **Recommendation rule too brittle.** `SLACK = 0` over *all* cycles since Dec 2025: one over-cap window ever disqualifies a tier forever → "None". User chose: only last 3 cycles, tier holds at ≤5% 5h-window hit quota and ≤1 weekly hit.

**Additional consistency fix (Task 4):** with the floor in place, a window that contains a real limit event may have cost *below* the (raised) cap, so the active tier would show 0 hits despite real events. Therefore: an anchored window counts as a hit for the active tier *and every cheaper tier*, regardless of its USD cost.

**Environment cautions:**
- The cron job deploys from THIS working directory (`update_dashboard.sh` → `python3 extract_stats.py`, both local-only, never commit them). Stay on branch `feature/dashboard-rethink-v2`, do NOT create a worktree, do NOT switch branches.
- The user runs parallel Claude sessions on this repo: run `git status` fresh before each commit and stage ONLY the files named in the task. Never `git add -A`. Untracked junk (debug.log, screenshots) must not be committed.
- `weekly buckets` stay ISO-calendar-week based for now (rolling-7-day rework is out of scope); the weekly cap stays `7 × 5h-cap`. Both remain disclosed in the disclaimer.
- Tests import `extract_stats` directly (it reads `config.json` at import — that is fine, `tests/test_plan_optimizer.py` already does this).

**Run tests with:** `python3 -m pytest tests/test_plan_limits.py -v` (from repo root `/home/andie/projects/claude-stats`).

---

### Task 1: Limit-event dedup (`_iso_to_ms`, `_dedupe_limit_events`)

**Files:**
- Modify: `extract_stats.py` (new helpers after `_detect_5h_fingerprint_events`, ~line 1758; wire-in at ~line 3540)
- Create: `tests/test_plan_limits.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plan_limits.py`:

```python
"""Unit tests for plan-limit calibration & recommendation fixes."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _dedupe_limit_events


def _ev(ts, subtype="user_plan_limit", typ="explicit", sid="s1", **kw):
    e = {"type": typ, "subtype": subtype, "timestamp": ts, "session_id": sid}
    e.update(kw)
    return e


def test_dedupe_exact_duplicates_collapse():
    evs = [_ev("2026-03-27T14:54:04.081Z"), _ev("2026-03-27T14:54:04.081Z")]
    out = _dedupe_limit_events(evs)
    assert len(out) == 1
    assert out[0]["merged_count"] == 2


def test_dedupe_parallel_sessions_within_cluster_collapse():
    evs = [_ev("2026-03-24T14:33:09.089Z", sid="a"),
           _ev("2026-03-24T14:33:09.510Z", sid="b")]
    assert len(_dedupe_limit_events(evs)) == 1


def test_dedupe_retry_chain_collapses_but_distant_event_stays():
    evs = [_ev("2026-04-14T13:14:48Z"), _ev("2026-04-14T13:15:21Z"),
           _ev("2026-04-14T13:16:24Z"), _ev("2026-04-14T16:00:00Z")]
    out = _dedupe_limit_events(evs)
    assert len(out) == 2
    assert out[0]["merged_count"] == 3
    assert out[1]["merged_count"] == 1


def test_dedupe_input_order_does_not_matter():
    evs = [_ev("2026-04-14T16:00:00Z"), _ev("2026-04-14T13:14:48Z"),
           _ev("2026-04-14T13:15:21Z")]
    out = _dedupe_limit_events(evs)
    assert len(out) == 2
    assert out[0]["timestamp"] == "2026-04-14T13:14:48Z"


def test_dedupe_keeps_unparseable_timestamp_events():
    evs = [_ev(""), _ev("2026-04-14T13:14:48Z")]
    assert len(_dedupe_limit_events(evs)) == 2


def test_dedupe_does_not_mutate_input():
    evs = [_ev("2026-04-14T13:14:48Z")]
    _dedupe_limit_events(evs)
    assert "merged_count" not in evs[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: FAIL at import — `ImportError: cannot import name '_dedupe_limit_events'`

- [ ] **Step 3: Implement the helpers**

In `extract_stats.py`, directly AFTER the `_detect_5h_fingerprint_events` function body (after its `return events`, ~line 1758), insert:

```python
LIMIT_EVENT_CLUSTER_SEC = 15 * 60  # events closer than this describe one limit hit


def _iso_to_ms(s):
    """ISO-8601 string → epoch ms, or None if unparseable."""
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OSError, AttributeError, TypeError):
        return None


def _dedupe_limit_events(events):
    """Collapse limit events that describe the same underlying limit hit.

    Parallel sessions surface the same banner within seconds of each other,
    and retries repeat it minutes later. Sorted by time, an event merges
    into the current cluster when it is within LIMIT_EVENT_CLUSTER_SEC of
    the cluster's last event; the earliest event represents the cluster and
    `merged_count` records how many raw events it absorbed. Events without
    a parseable timestamp are kept unmerged at the end.
    """
    parsed, rest = [], []
    for ev in events:
        ms = _iso_to_ms(ev.get("timestamp"))
        if ms is None:
            rest.append(ev)
        else:
            parsed.append((ms, ev))
    parsed.sort(key=lambda x: x[0])
    deduped = []
    last_ms = None
    for ms, ev in parsed:
        if last_ms is not None and ms - last_ms <= LIMIT_EVENT_CLUSTER_SEC * 1000:
            deduped[-1]["merged_count"] += 1
        else:
            ev = dict(ev)
            ev["merged_count"] = 1
            deduped.append(ev)
        last_ms = ms
    return deduped + rest
```

- [ ] **Step 4: Wire the dedup into the aggregation**

In `extract_stats.py` (~line 3540), replace:

```python
    all_limit_events = explicit_events + fingerprint_events
    all_limit_events.sort(key=lambda e: e.get("timestamp", ""))
```

with:

```python
    all_limit_events = _dedupe_limit_events(explicit_events + fingerprint_events)
    all_limit_events.sort(key=lambda e: e.get("timestamp", ""))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git status   # fresh check — parallel sessions may have touched the repo
git add tests/test_plan_limits.py extract_stats.py
git commit -m "fix(limits): dedupe limit events from parallel sessions and retries"
```

---

### Task 2: Correct anchor matching (`_match_limit_events_to_windows`)

**Files:**
- Modify: `extract_stats.py` (new helper after `_dedupe_limit_events`; replace inline loop + local `_ts_to_ms` at ~lines 2993-3010)
- Test: `tests/test_plan_limits.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_limits.py`:

```python
from extract_stats import _match_limit_events_to_windows

T0 = 1_750_000_000_000  # arbitrary fixed epoch ms
H = 3600 * 1000


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _win(start_ms, last_turn_ms, cost=10.0):
    return {"start_ts": start_ms, "end_ts": last_turn_ms, "cost": cost}


def test_fingerprint_event_anchors_pre_gap_window():
    # Window A active [T0, T0+2h]; limit pause; resume at T0+7h opens window B.
    # The limited window is A (contains gap_start), NOT B (contains timestamp).
    wins = [_win(T0, T0 + 2 * H), _win(T0 + 7 * H, T0 + 8 * H)]
    ev = {"type": "heuristic", "subtype": "5h_fingerprint",
          "timestamp": _iso(T0 + 7 * H), "gap_start": _iso(T0 + 2 * H),
          "gap_end": _iso(T0 + 7 * H)}
    assert _match_limit_events_to_windows([ev], wins) == {0}


def test_explicit_banner_after_last_turn_still_anchors_window():
    # Banner arrives 10 min after the window's last assistant turn but
    # within the window's 5h span — must match.
    wins = [_win(T0, T0 + 2 * H)]
    ev = _ev(_iso(T0 + 2 * H + 10 * 60 * 1000))
    assert _match_limit_events_to_windows([ev], wins) == {0}


def test_event_in_dead_gap_between_windows_matches_nothing():
    wins = [_win(T0, T0 + 2 * H), _win(T0 + 9 * H, T0 + 10 * H)]
    ev = _ev(_iso(T0 + 6 * H))  # after A's 5h span, before B starts
    assert _match_limit_events_to_windows([ev], wins) == set()


def test_event_with_unparseable_timestamp_is_skipped():
    wins = [_win(T0, T0 + 2 * H)]
    assert _match_limit_events_to_windows([_ev("")], wins) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: new tests FAIL at import — `ImportError: cannot import name '_match_limit_events_to_windows'`

- [ ] **Step 3: Implement the helper**

In `extract_stats.py`, directly after `_dedupe_limit_events`, insert (note: `FIVE_HOUR_MS` is already defined at line 221):

```python
def _match_limit_events_to_windows(events, windows):
    """Map limit events to the 5h-window that actually hit the cap.

    Fingerprint events carry the resume time in `timestamp`/`gap_end`; the
    limited window is the one containing the last activity BEFORE the gap
    (`gap_start`). Explicit banner events fire inside the limited window
    but AFTER its last assistant turn, so match against the full
    [start, start+5h) span rather than [start, last-turn]. Returns the set
    of matched window indices.
    """
    matched = set()
    for ev in events:
        if ev.get("subtype") == "5h_fingerprint":
            ev_ms = _iso_to_ms(ev.get("gap_start"))
        else:
            ev_ms = _iso_to_ms(ev.get("timestamp"))
        if ev_ms is None:
            continue
        for i, w in enumerate(windows):
            if w["start_ts"] <= ev_ms < w["start_ts"] + FIVE_HOUR_MS:
                matched.add(i)
                break
    return matched
```

- [ ] **Step 4: Replace the inline matching in `build_plan_analysis`**

In `extract_stats.py` (~lines 2993-3010), replace this entire block:

```python
    # Match limit events to windows by timestamp (event.timestamp falls in
    # [window.start_ts, window.end_ts]). These windows are the calibration
    # anchors — their cost ≈ 100% of that-tier's 5h cap.
    def _ts_to_ms(s):
        try:
            return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
        except (ValueError, OSError, AttributeError):
            return None

    limit_event_window_ids = set()
    for ev in all_limit_events:
        ev_ms = _ts_to_ms(ev.get("timestamp") or ev.get("gap_end"))
        if ev_ms is None:
            continue
        for i, w in enumerate(windows_5h):
            if w["start_ts"] <= ev_ms <= w["end_ts"]:
                limit_event_window_ids.add(i)
                break
```

with:

```python
    # Match limit events to their calibration-anchor windows — the windows
    # whose cost ≈ 100% of the active tier's 5h cap.
    limit_event_window_ids = _match_limit_events_to_windows(all_limit_events, windows_5h)
```

Check first whether the removed local `_ts_to_ms` has other call sites inside `build_plan_analysis` (`grep -n "_ts_to_ms" extract_stats.py`); if yes, replace those calls with `_iso_to_ms`.

- [ ] **Step 5: Run the full test file**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: 10 PASS

- [ ] **Step 6: Commit**

```bash
git status
git add tests/test_plan_limits.py extract_stats.py
git commit -m "fix(limits): anchor fingerprint events to the pre-gap window, match banners in the full 5h span"
```

---

### Task 3: Plausibility floor in `_estimate_5h_window_cap_usd`

**Files:**
- Modify: `extract_stats.py:303-344` (`_estimate_5h_window_cap_usd`)
- Test: `tests/test_plan_limits.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_limits.py`:

```python
from extract_stats import _estimate_5h_window_cap_usd


def test_floor_raises_implausibly_low_empirical_base():
    # Anchor on Max 5x cost $10 → base $2. But an event-free Max 5x window
    # cost $115 — the cap must be at least that, so base floors to 115/5.
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 10.0},
            {"start_ts": 2, "end_ts": 3, "cost": 115.0}]
    tiers = {0: "Max 5x", 1: "Max 5x"}
    info = _estimate_5h_window_cap_usd(wins, {0}, tiers, None)
    assert info["floor_applied"] is True
    assert info["base_pro_per_window_usd"] == 23.0
    assert info["caps_per_window"]["Max 5x"] == 115.0
    assert info["source"] == "empirical"


def test_floor_not_applied_when_anchor_median_is_higher():
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 100.0},
            {"start_ts": 2, "end_ts": 3, "cost": 50.0}]
    tiers = {0: "Max 5x", 1: "Max 5x"}
    info = _estimate_5h_window_cap_usd(wins, {0}, tiers, None)
    assert info["floor_applied"] is False
    assert info["base_pro_per_window_usd"] == 20.0


def test_floor_also_lifts_default_fallback():
    # No anchors → default base 100; event-free Pro window of $150 lifts it.
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 150.0}]
    tiers = {0: "Pro"}
    info = _estimate_5h_window_cap_usd(wins, set(), tiers, None)
    assert info["source"] == "default"
    assert info["floor_applied"] is True
    assert info["base_pro_per_window_usd"] == 150.0


def test_config_override_is_never_floored():
    wins = [{"start_ts": 0, "end_ts": 1, "cost": 500.0}]
    tiers = {0: "Pro"}
    info = _estimate_5h_window_cap_usd(wins, set(), tiers, 30.0)
    assert info["source"] == "config_override"
    assert info["floor_applied"] is False
    assert info["base_pro_per_window_usd"] == 30.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: the 4 new tests FAIL — `KeyError: 'floor_applied'` (and wrong base values)

- [ ] **Step 3: Implement the floor**

In `extract_stats.py`, inside `_estimate_5h_window_cap_usd`, replace the tail of the function:

```python
    caps = {t: round(base * f, 2) for t, f in PLAN_TIER_FACTORS.items()}
    return {
        "caps_per_window": caps,
        "base_pro_per_window_usd": round(base, 2),
        "anchor_window_count": len(anchors),
        "source": source,
    }
```

with:

```python
    # Plausibility floor: the true cap on tier T is at least the cost of
    # the most expensive window on T that did NOT contain a limit event —
    # had it been over the cap, it would have been cut off. Anchors biased
    # low (resume-side windows, misaligned window starts) would otherwise
    # produce caps the observed data already refutes. A config override is
    # authoritative and never floored.
    floor_pro = 0.0
    for i, w in enumerate(windows):
        if i in limit_event_window_ids:
            continue
        tier = cycle_tier_by_window_id.get(i)
        factor = PLAN_TIER_FACTORS.get(tier)
        if not factor or w["cost"] <= 0:
            continue
        floor_pro = max(floor_pro, w["cost"] / factor)
    floor_applied = False
    if source != "config_override" and floor_pro > base:
        base = floor_pro
        floor_applied = True

    caps = {t: round(base * f, 2) for t, f in PLAN_TIER_FACTORS.items()}
    return {
        "caps_per_window": caps,
        "base_pro_per_window_usd": round(base, 2),
        "anchor_window_count": len(anchors),
        "source": source,
        "floor_pro_per_window_usd": round(floor_pro, 2),
        "floor_applied": floor_applied,
    }
```

Also extend the docstring's first paragraph with one sentence: `The result is floored at the most expensive limit-event-free window per tier (normalised to Pro), since the true cap cannot be below a cost that was actually reached without a cutoff.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: 14 PASS

- [ ] **Step 5: Commit**

```bash
git status
git add tests/test_plan_limits.py extract_stats.py
git commit -m "fix(limits): floor cap estimate at the most expensive limit-free window"
```

---

### Task 4: Hit counting with anchor propagation (`_count_5h_hits`)

**Files:**
- Modify: `extract_stats.py` (new helper after `_match_limit_events_to_windows`; wire-in inside `build_plan_analysis`, ~lines 3034-3044)
- Test: `tests/test_plan_limits.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_limits.py`:

```python
from extract_stats import _count_5h_hits

CAPS = {"Pro": 23.0, "Max 5x": 115.0, "Max 20x": 460.0}


def test_anchor_window_counts_as_hit_on_active_and_cheaper_tiers():
    # Real limit hit on Max 5x with (proxy) cost below every cap: still a
    # hit for Max 5x and Pro, but says nothing about Max 20x.
    wins = [(0, {"cost": 30.0})]
    hits = _count_5h_hits(wins, CAPS, {0: "Max 5x"}, {0})
    assert hits == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}


def test_cost_above_cap_counts_without_anchor():
    wins = [(0, {"cost": 120.0})]
    hits = _count_5h_hits(wins, CAPS, {0: "Max 5x"}, set())
    assert hits == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}


def test_anchor_window_not_double_counted():
    wins = [(0, {"cost": 120.0})]
    hits = _count_5h_hits(wins, CAPS, {0: "Max 5x"}, {0})
    assert hits == {"Pro": 1, "Max 5x": 1, "Max 20x": 0}


def test_anchor_on_unknown_tier_falls_back_to_cost_comparison():
    wins = [(0, {"cost": 30.0})]
    hits = _count_5h_hits(wins, CAPS, {0: None}, {0})
    assert hits == {"Pro": 1, "Max 5x": 0, "Max 20x": 0}


def test_zero_cap_yields_no_cost_hits():
    wins = [(0, {"cost": 30.0})]
    hits = _count_5h_hits(wins, {"Pro": 0.0, "Max 5x": 0.0, "Max 20x": 0.0},
                          {0: "Max 5x"}, set())
    assert hits == {"Pro": 0, "Max 5x": 0, "Max 20x": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: FAIL at import — `ImportError: cannot import name '_count_5h_hits'`

- [ ] **Step 3: Implement the helper**

In `extract_stats.py`, directly after `_match_limit_events_to_windows`, insert:

```python
def _count_5h_hits(indexed_windows, caps, tier_by_idx, anchor_ids):
    """Per-tier hit counts for a list of (window_index, window) pairs.

    A window counts as a hit for tier U when its cost exceeds U's cap, OR
    when it contains a detected limit event and U is not above the tier
    that was active — a real hit on the active tier is by definition also
    a hit on every cheaper tier, regardless of what the USD proxy says.
    """
    hits = {}
    for tier, cap in caps.items():
        n = 0
        for i, w in indexed_windows:
            active = tier_by_idx.get(i)
            anchored = (i in anchor_ids and active in PLAN_TIER_FACTORS
                        and PLAN_TIER_FACTORS[tier] <= PLAN_TIER_FACTORS[active])
            if anchored or (cap > 0 and w["cost"] > cap):
                n += 1
        hits[tier] = n
    return hits
```

- [ ] **Step 4: Wire it into the cycle loop**

In `extract_stats.py` (~lines 3034-3055), replace:

```python
    rec_cycles = []
    for p in periods:
        api = p.get("api_cost", 0)
        cycle_windows = [w for w in windows_5h if _cycle_contains_ts(p, w["start_ts"])]
        cycle_weeks   = [b for b in weekly_buckets if _cycle_contains_ts(p, b["week_start_ts"])]
        hits_5h = {}
        for tier, cap in cap_info_5h["caps_per_window"].items():
            hits_5h[tier] = sum(1 for w in cycle_windows if w["cost"] > cap) if cap > 0 else 0
```

with:

```python
    rec_cycles = []
    for p in periods:
        api = p.get("api_cost", 0)
        cycle_windows = [(i, w) for i, w in enumerate(windows_5h)
                         if _cycle_contains_ts(p, w["start_ts"])]
        cycle_weeks   = [b for b in weekly_buckets if _cycle_contains_ts(p, b["week_start_ts"])]
        hits_5h = _count_5h_hits(cycle_windows, cap_info_5h["caps_per_window"],
                                 cycle_tier_by_window_idx, limit_event_window_ids)
```

The weekly hit loop below stays unchanged. `"total_5h_windows": len(cycle_windows)` further down also stays correct (the list now holds pairs, length is the same).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: 19 PASS

- [ ] **Step 6: Commit**

```bash
git status
git add tests/test_plan_limits.py extract_stats.py
git commit -m "fix(limits): anchored windows always count as hits on the active and cheaper tiers"
```

---

### Task 5: Recency + quota recommendation rule (`_recommend_tier`)

**Files:**
- Modify: `extract_stats.py` (constants near `WEEKLY_VS_5H_RATIO` ~line 2748; new helper; replace SLACK block ~lines 3057-3081)
- Test: `tests/test_plan_limits.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_limits.py`:

```python
from extract_stats import _recommend_tier

ZERO = {"Pro": 0, "Max 5x": 0, "Max 20x": 0}


def _cycle(windows, hits5, hitsw):
    return {"total_5h_windows": windows,
            "tier_5h_hits": hits5, "tier_weekly_hits": hitsw}


def test_recommendation_uses_only_recent_cycles():
    old = _cycle(50, {"Pro": 50, "Max 5x": 50, "Max 20x": 50}, ZERO)
    new = _cycle(40, ZERO, ZERO)
    rec, basis = _recommend_tier([old, new, new, new])
    assert rec == "Pro"
    assert basis["recent_cycles"] == 3
    assert basis["recent_window_total"] == 120


def test_recommendation_tolerates_hits_within_quota():
    # 5 Pro hits of 120 windows = 4.2% <= 5%
    c = _cycle(40, {"Pro": 5, "Max 5x": 0, "Max 20x": 0}, ZERO)
    z = _cycle(40, ZERO, ZERO)
    rec, _ = _recommend_tier([c, z, z])
    assert rec == "Pro"


def test_recommendation_escalates_above_quota():
    # 30 Pro hits of 120 windows = 25% > 5% → Pro out, Max 5x holds (1 hit)
    c = _cycle(40, {"Pro": 30, "Max 5x": 1, "Max 20x": 0}, ZERO)
    z = _cycle(40, ZERO, ZERO)
    rec, _ = _recommend_tier([c, z, z])
    assert rec == "Max 5x"


def test_recommendation_weekly_allowance():
    # Pro: 2 weekly hits > allowance of 1 → Max 5x (1 weekly hit) holds
    c = _cycle(40, ZERO, {"Pro": 2, "Max 5x": 1, "Max 20x": 0})
    z = _cycle(40, ZERO, ZERO)
    rec, _ = _recommend_tier([c, z, z])
    assert rec == "Max 5x"


def test_recommendation_none_when_even_top_tier_overruns():
    c = _cycle(40, {"Pro": 40, "Max 5x": 40, "Max 20x": 40}, ZERO)
    rec, _ = _recommend_tier([c])
    assert rec is None


def test_recommendation_basis_fields():
    z = _cycle(40, ZERO, ZERO)
    _, basis = _recommend_tier([z])
    assert basis["hit_quota"] == 0.05
    assert basis["weekly_allowance"] == 1
    assert basis["tier_recent_5h_hits"]["Pro"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_plan_limits.py -v`
Expected: FAIL at import — `ImportError: cannot import name '_recommend_tier'`

- [ ] **Step 3: Implement constants + helper**

In `extract_stats.py`, directly below the `WEEKLY_VS_5H_RATIO = 7` line (~2748), insert:

```python
REC_RECENT_CYCLES = 3         # recommendation looks at the last N billing cycles
REC_5H_HIT_QUOTA = 0.05       # tier holds if it hits in <=5% of recent 5h-windows
REC_WEEKLY_HIT_ALLOWANCE = 1  # ...and in at most this many recent weeks


def _recommend_tier(rec_cycles):
    """Cheapest tier whose recent hit rate stays inside the tolerance.

    Only the last REC_RECENT_CYCLES cycles count — usage from months ago,
    shaped by a different plan, should not disqualify a tier forever. A
    tier holds when its 5h hits are <= REC_5H_HIT_QUOTA of the recent
    window count and its weekly hits are <= REC_WEEKLY_HIT_ALLOWANCE.
    Returns (recommended_tier_or_None, basis_dict).
    """
    recent = rec_cycles[-REC_RECENT_CYCLES:]
    window_total = sum(c.get("total_5h_windows", 0) for c in recent)
    tier_5h = {t: sum(c.get("tier_5h_hits", {}).get(t, 0) for c in recent)
               for t in PLAN_TIER_FACTORS}
    tier_weekly = {t: sum(c.get("tier_weekly_hits", {}).get(t, 0) for c in recent)
                   for t in PLAN_TIER_FACTORS}
    recommended = None
    for tier in ("Pro", "Max 5x", "Max 20x"):
        if (tier_5h[tier] <= REC_5H_HIT_QUOTA * window_total
                and tier_weekly[tier] <= REC_WEEKLY_HIT_ALLOWANCE):
            recommended = tier
            break
    basis = {
        "recent_cycles": len(recent),
        "recent_window_total": window_total,
        "hit_quota": REC_5H_HIT_QUOTA,
        "weekly_allowance": REC_WEEKLY_HIT_ALLOWANCE,
        "tier_recent_5h_hits": tier_5h,
        "tier_recent_weekly_hits": tier_weekly,
    }
    return recommended, basis
```

- [ ] **Step 4: Replace the SLACK block in `build_plan_analysis`**

In `extract_stats.py` (~lines 3057-3071), replace:

```python
    # Recommendation: cheapest tier whose total 5h-hits across all cycles
    # is 0 (or below a small slack). Weekly hits factor in as a tiebreaker:
    # if multiple tiers have 0 5h-hits, pick the cheapest that also has 0
    # weekly-hits.
    SLACK = 0  # zero tolerance — any hit means the tier was insufficient
    tier_total_5h     = {t: sum(c["tier_5h_hits"].get(t, 0) for c in rec_cycles)
                          for t in PLAN_TIER_FACTORS}
    tier_total_weekly = {t: sum(c["tier_weekly_hits"].get(t, 0) for c in rec_cycles)
                          for t in PLAN_TIER_FACTORS}
    recommended_tier = None
    for tier in ("Pro", "Max 5x", "Max 20x"):
        if tier_total_5h[tier] <= SLACK and tier_total_weekly[tier] <= SLACK:
            recommended_tier = tier
            break
```

with:

```python
    # Totals over all cycles feed the per-cycle tables; the recommendation
    # itself only looks at recent cycles with a hit-quota tolerance.
    tier_total_5h     = {t: sum(c["tier_5h_hits"].get(t, 0) for c in rec_cycles)
                          for t in PLAN_TIER_FACTORS}
    tier_total_weekly = {t: sum(c["tier_weekly_hits"].get(t, 0) for c in rec_cycles)
                          for t in PLAN_TIER_FACTORS}
    recommended_tier, rec_basis = _recommend_tier(rec_cycles)
```

Then in the `plan_recommendation = {...}` dict right below, add the new field after `"recommended_tier"`:

```python
    plan_recommendation = {
        "current_tier":     normalized_current,
        "recommended_tier": recommended_tier,
        "rec_basis":        rec_basis,
        "total_cycles":     len(rec_cycles),
        "tier_total_5h_hits":     tier_total_5h,
        "tier_total_weekly_hits": tier_total_weekly,
        "calibration_5h":      cap_info_5h,
        "calibration_weekly":  cap_info_weekly,
        "cycles": rec_cycles,
    }
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests PASS (25 in test_plan_limits.py plus the pre-existing files)

- [ ] **Step 6: Commit**

```bash
git status
git add tests/test_plan_limits.py extract_stats.py
git commit -m "feat(limits): recommend by recent-cycle hit quota instead of all-history zero tolerance"
```

---

### Task 6: UI + locales (basis line, floor display, merged-event badge, disclaimers)

**Files:**
- Modify: `templates/dashboard.js:2054-2143` (`renderPlanRecommendation`), `templates/dashboard.js:2012-2021` (`renderLimitsEventTimeline` tooltip)
- Modify: `locales/de.json:257`, `locales/en.json:257` (`planRec` block)

No JS test infra exists; verification is `node --check` (Step 5).

- [ ] **Step 1: Extend `renderPlanRecommendation` T-keys**

In `templates/dashboard.js`, inside the `const T = {...}` of `renderPlanRecommendation`, after the `anchors:` line, add:

```js
    recBasis:     L.recBasis     || 'Basis: last {n} cycles ({w} 5h-windows) — tolerance: ≤{q}% of 5h-windows, ≤{a} weeks over cap',
    calFloor:     L.calFloor     || 'floored at the most expensive limit-free window',
```

and replace the `disclaimer:` fallback line with:

```js
    disclaimer:   L.disclaimer   || "Hit counts use empirical caps derived from windows that contained a limit event, floored at the most expensive limit-free window (USD is a rough proxy for Anthropic's limit units). Duplicate events from parallel sessions are merged. Anthropic does not publish exact token limits — the 1:5:20 tier ratio is approximate. Weekly cap is estimated as 7 × the 5h cap until a dedicated weekly-limit detector is added.",
```

- [ ] **Step 2: Render floor info and basis line**

In the same function, replace:

```js
  const cal5Line = T.cal + ' (5h): ' + calSrc5 + ' — Pro $' + (caps5.Pro || 0).toFixed(2) +
    ' / Max 5x $' + (caps5['Max 5x'] || 0).toFixed(2) +
    ' / Max 20x $' + (caps5['Max 20x'] || 0).toFixed(2) + ' ' + T.capPerWindow +
    ' (n=' + (cal5.anchor_window_count || 0) + ' ' + T.anchors + ')';
```

with:

```js
  const cal5Line = T.cal + ' (5h): ' + calSrc5 + ' — Pro $' + (caps5.Pro || 0).toFixed(2) +
    ' / Max 5x $' + (caps5['Max 5x'] || 0).toFixed(2) +
    ' / Max 20x $' + (caps5['Max 20x'] || 0).toFixed(2) + ' ' + T.capPerWindow +
    ' (n=' + (cal5.anchor_window_count || 0) + ' ' + T.anchors + ')' +
    (cal5.floor_applied ? ' · ' + T.calFloor : '');
```

Then replace:

```js
  const recLine = pr.recommended_tier
    ? T.rec + ': ' + pr.recommended_tier
    : T.rec + ': ' + T.none;
```

with:

```js
  const recLine = pr.recommended_tier
    ? T.rec + ': ' + pr.recommended_tier
    : T.rec + ': ' + T.none;

  const basis = pr.rec_basis || null;
  const basisLine = basis
    ? T.recBasis.replace('{n}', basis.recent_cycles)
                .replace('{w}', basis.recent_window_total)
                .replace('{q}', Math.round((basis.hit_quota || 0) * 100))
                .replace('{a}', basis.weekly_allowance)
    : '';
```

and in the `el.innerHTML = ...` block, replace:

```js
      '<div>' + recLine + '</div>' +
```

with:

```js
      '<div>' + recLine + '</div>' +
      (basisLine ? '<div class="plan-rec-cal">' + basisLine + '</div>' : '') +
```

- [ ] **Step 3: Show merged-event count in the timeline tooltip**

In `renderLimitsEventTimeline`, replace:

```js
      const tooltip = (ev.type === 'explicit' ? T.explicit : T.heuristic) +
                      ' · ' + (ev.subtype || '') +
                      ' · ' + (ev.timestamp || ev.gap_end || '');
```

with:

```js
      const tooltip = (ev.type === 'explicit' ? T.explicit : T.heuristic) +
                      ' · ' + (ev.subtype || '') +
                      ' · ' + (ev.timestamp || ev.gap_end || '') +
                      (ev.merged_count > 1 ? ' · ×' + ev.merged_count : '');
```

- [ ] **Step 4: Update locales**

In `locales/de.json`, inside the `"planRec"` object, replace:

```json
  "disclaimer": "Schätzung basierend auf Anthropic-Faktoren (1:5:20). Anthropic publiziert keine exakten Token-Limits. Tatsächliche Limits können abweichen."
```

with:

```json
  "recBasis": "Basis: letzte {n} Zyklen ({w} 5h-Fenster) — Toleranz: ≤{q}% der 5h-Fenster, ≤{a} Wochen über Cap",
  "calFloor": "Floor: teuerstes limit-freies Fenster",
  "disclaimer": "Hit-Zählung nutzt empirische Caps aus Fenstern mit Limit-Event, mindestens aber das teuerste limit-freie Fenster (USD ist ein grober Proxy für Anthropics Limit-Einheiten). Doppelte Events paralleler Sessions werden zusammengeführt. Anthropic publiziert keine exakten Limits — der 1:5:20-Faktor ist eine Näherung. Wochen-Cap ≈ 7 × 5h-Cap."
```

In `locales/en.json`, inside the `"planRec"` object, replace:

```json
  "disclaimer": "Estimate based on Anthropic's 1:5:20 factor. Anthropic does not publish exact token limits. Actual limits may differ."
```

with:

```json
  "recBasis": "Basis: last {n} cycles ({w} 5h-windows) — tolerance: ≤{q}% of 5h-windows, ≤{a} weeks over cap",
  "calFloor": "floored at the most expensive limit-free window",
  "disclaimer": "Hit counts use empirical caps from windows that contained a limit event, floored at the most expensive limit-free window (USD is a rough proxy for Anthropic's limit units). Duplicate events from parallel sessions are merged. Anthropic does not publish exact token limits — the 1:5:20 ratio is approximate. Weekly cap ≈ 7 × the 5h cap."
```

Mind the JSON commas: the replaced `disclaimer` line is the LAST entry in both `planRec` objects, so the two new lines added before it need trailing commas (as shown) and `disclaimer` stays last without one.

- [ ] **Step 5: Syntax preflight**

Run: `node --check templates/dashboard.js && python3 -c "import json; json.load(open('locales/de.json')); json.load(open('locales/en.json')); print('OK')"`
Expected: no node output (success) and `OK`

- [ ] **Step 6: Commit**

```bash
git status
git add templates/dashboard.js locales/de.json locales/en.json
git commit -m "feat(limits-ui): show recommendation basis, calibration floor and merged-event count"
```

---

### Task 7: End-to-end verification against real data

**Files:**
- No source changes expected; regenerates `public/dashboard_data.json` (untracked output — do not commit) and writes nothing else.

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 2: Regenerate dashboard data**

Run from repo root: `python3 extract_stats.py`
Expected: completes without traceback (same invocation the cron uses; the live dashboard will pick this up — that is intended, the user reviews in the browser).

- [ ] **Step 3: Sanity-check the new numbers**

Run:

```bash
python3 -c "
import json
d = json.load(open('public/dashboard_data.json'))
pr = d['plan_recommendation']
print('current:', pr['current_tier'], '| recommended:', pr['recommended_tier'])
print('basis:', pr['rec_basis'])
print('cal 5h:', pr['calibration_5h'])
print('totals 5h:', pr['tier_total_5h_hits'])
print('totals weekly:', pr['tier_total_weekly_hits'])
for c in pr['cycles']:
    print(c['label'], '| win', c['total_5h_windows'], '| 5h', c['tier_5h_hits'], '| wk', c['tier_weekly_hits'], '| ev', c['limit_event_count'])
print('events:', len(d['limit_events_all']))
"
```

Expected properties (report the actual numbers, do not force them):
- `base_pro_per_window_usd` clearly above the old $5.77; `anchor_window_count` plausibly larger than 5 (explicit banners now match).
- No internal contradiction: in each cycle, the active tier's 5h hits should be ≥ 0 and roughly consistent with `limit_event_count` (anchored windows count as hits); cycles on Max 20x with 0 events should show ~0 Max-20x hits.
- `len(limit_events_all)` noticeably below the previous 19 (duplicates merged) and the 2026-03-27 duplicate is gone.
- `recommended_tier` is no longer the artifact "None" — most plausibly "Max 20x" (or "Max 5x" if recent hits are rare). If it IS still None, investigate before finishing and report why.

- [ ] **Step 4: Report**

Summarize old vs. new calibration and recommendation for the user (German), including the per-cycle table, and remind them the live dashboard now shows the new numbers for browser review. Do not push, do not tag — the v2 release flow is handled separately.
