# Per-Day Token Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute daily costs, tokens and messages to the day each API call/message actually occurred, instead of bucketing a whole session onto its start date.

**Architecture:** At parse time we already accumulate per-session, per-model token/cost buckets in `sess["models"]`. We add a parallel `sess["daily_models"]` (keyed `[day][model]`) and `sess["daily_message_count"]` (keyed `[day]`), populated from each message's own timestamp. Subagent spend is folded into the parent's `daily_models` exactly as it already is for `models` (reusing `_merge_model_buckets`), so daily sums reconcile with headline totals. A pure helper `split_session_by_day` distributes a session across its active days and dumps any timestamp-less remainder on the start day, guaranteeing `sum(per-day) == session total`. The build loop in `build_dashboard_data` is rewired to feed `daily_costs` / `daily_tokens` / `daily_messages` / `daily_sessions` / `daily_cache_eff` from this helper.

**Tech Stack:** Python 3, stdlib only (`datetime`, `collections.defaultdict`), `unittest` (mirrors existing `tests/` conventions).

**Out of scope (intentional, documented):**
- `hourly_distribution` / `weekday_distribution` stay keyed on session **start** hour/weekday. They are date-less aggregate distributions, so "today/yesterday" does not apply. Noted as a possible follow-up.
- The per-session `sessions[].date` field stays the session **start** date (the session table is per-session, not per-day).
- `daily_sessions` semantics change deliberately: a session spanning N days now counts on **each active day** (so `sum(daily_sessions)` may exceed total session count). This is the correct meaning for a daily view ("sessions active that day").

---

## File Structure

- `extract_stats.py` — all production changes:
  - new module-level helpers `_day_from_ms` and `split_session_by_day`
  - session-init block (~line 2002): add `daily_models` + `daily_message_count`
  - assistant parse block (~line 2272): populate `daily_models`
  - user-typed + assistant message blocks (~lines 2170, 2265): populate `daily_message_count`
  - subagent merge block (~line 2465): fold subagent `daily_models` into parent
  - `build_dashboard_data` session loop (~lines 3341-3400): rewire daily series via helper
  - cleanup/pop block (~line 3720): drop the two temp fields before serialization
- `tests/test_daily_split.py` — new unit tests for `split_session_by_day` and `_day_from_ms`.

---

## Task 1: Pure day-split helper (`_day_from_ms`, `split_session_by_day`)

**Files:**
- Modify: `extract_stats.py` (add two module-level functions next to `_merge_model_buckets`, after line 1397)
- Test: `tests/test_daily_split.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_daily_split.py`:

```python
import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _day_from_ms, split_session_by_day

# 2026-06-10T12:00:00Z and 2026-06-12T08:00:00Z in ms
TS_10 = 1781438400000
TS_12 = 1781596800000


def _bucket(**kw):
    base = {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        "cost": 0.0, "calls": 0,
    }
    base.update(kw)
    return base


class DayFromMsTest(unittest.TestCase):
    def test_utc_day_string(self):
        self.assertEqual(_day_from_ms(TS_10), "2026-06-10")
        self.assertEqual(_day_from_ms(TS_12), "2026-06-12")


class SplitSessionByDayTest(unittest.TestCase):
    def test_distributes_across_days(self):
        daily_models = {
            "2026-06-10": {"opus": _bucket(output_tokens=100, cost=2.0, calls=1)},
            "2026-06-12": {"opus": _bucket(output_tokens=50, cost=1.0, calls=1)},
        }
        model_totals = {"opus": _bucket(output_tokens=150, cost=3.0, calls=2)}
        per_day_models, per_day_messages = split_session_by_day(
            daily_models, model_totals, {}, 0, start_day="2026-06-10")
        self.assertEqual(per_day_models["2026-06-10"]["opus"]["cost"], 2.0)
        self.assertEqual(per_day_models["2026-06-12"]["opus"]["cost"], 1.0)

    def test_untimestamped_remainder_goes_to_start_day(self):
        # daily_models only saw 100 output / 2.0 cost; model total is larger,
        # so the 50/1.0 remainder (a turn without a parseable timestamp) must
        # land on the start day so per-day sums reconcile with the total.
        daily_models = {
            "2026-06-12": {"opus": _bucket(output_tokens=100, cost=2.0, calls=1)},
        }
        model_totals = {"opus": _bucket(output_tokens=150, cost=3.0, calls=2)}
        per_day_models, _ = split_session_by_day(
            daily_models, model_totals, {}, 0, start_day="2026-06-10")
        self.assertEqual(per_day_models["2026-06-10"]["opus"]["cost"], 1.0)
        self.assertEqual(per_day_models["2026-06-10"]["opus"]["output_tokens"], 50)
        self.assertEqual(per_day_models["2026-06-12"]["opus"]["cost"], 2.0)
        # reconciliation: per-day sum == total
        total = sum(d["opus"]["cost"] for d in per_day_models.values())
        self.assertAlmostEqual(total, 3.0)

    def test_empty_daily_models_all_on_start_day(self):
        # Backwards-compat: a session that recorded no per-day data behaves
        # exactly like the old start-date bucketing.
        model_totals = {"opus": _bucket(output_tokens=80, cost=1.6, calls=1)}
        per_day_models, _ = split_session_by_day(
            {}, model_totals, {}, 0, start_day="2026-05-11")
        self.assertEqual(per_day_models["2026-05-11"]["opus"]["cost"], 1.6)
        self.assertEqual(list(per_day_models.keys()), ["2026-05-11"])

    def test_messages_distributed_with_remainder_on_start(self):
        per_day_messages_in = {"2026-06-11": 5, "2026-06-12": 3}
        _, per_day_messages = split_session_by_day(
            {}, {}, per_day_messages_in, total_message_count=10,
            start_day="2026-06-10")
        self.assertEqual(per_day_messages["2026-06-11"], 5)
        self.assertEqual(per_day_messages["2026-06-12"], 3)
        self.assertEqual(per_day_messages["2026-06-10"], 2)  # remainder
        self.assertEqual(sum(per_day_messages.values()), 10)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_split.py -v`
Expected: FAIL with `ImportError: cannot import name '_day_from_ms'`

- [ ] **Step 3: Write minimal implementation**

In `extract_stats.py`, immediately after `_merge_model_buckets` (after line 1397), add:

```python
_DAILY_FIELDS = (
    "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens",
    "cost", "calls",
)


def _day_from_ms(ms: int) -> str:
    """UTC calendar day (YYYY-MM-DD) for an epoch-millisecond timestamp."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def split_session_by_day(daily_models, model_totals,
                         daily_message_count, total_message_count,
                         start_day):
    """Distribute one session's per-model spend and message count across the
    days they actually occurred.

    `daily_models[day][model]` and `daily_message_count[day]` hold the share
    that carried a parseable per-message timestamp. Any remainder (turns/
    messages whose timestamp could not be parsed) is dumped on `start_day`, so
    the returned per-day values reconcile EXACTLY with the session totals
    (`model_totals`, `total_message_count`).

    Returns `(per_day_models, per_day_messages)` where
    `per_day_models[day][model]` is a fresh bucket dict (raw model keys; the
    caller maps to display names) and `per_day_messages[day]` is an int.
    """
    per_day_models = {}
    attributed = defaultdict(lambda: {k: 0 for k in _DAILY_FIELDS})
    for day, mdict in daily_models.items():
        day_out = per_day_models.setdefault(day, {})
        for model, b in mdict.items():
            dst = day_out.setdefault(model, {k: 0 for k in _DAILY_FIELDS})
            for k in _DAILY_FIELDS:
                v = b.get(k, 0)
                dst[k] += v
                attributed[model][k] += v

    for model, tb in model_totals.items():
        remainder = {k: tb.get(k, 0) - attributed[model].get(k, 0)
                     for k in _DAILY_FIELDS}
        if any(remainder[k] for k in _DAILY_FIELDS):
            dst = per_day_models.setdefault(start_day, {}).setdefault(
                model, {k: 0 for k in _DAILY_FIELDS})
            for k in _DAILY_FIELDS:
                dst[k] += remainder[k]

    per_day_messages = dict(daily_message_count)
    remainder_msgs = total_message_count - sum(per_day_messages.values())
    if remainder_msgs:
        per_day_messages[start_day] = per_day_messages.get(start_day, 0) + remainder_msgs

    return per_day_models, per_day_messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_daily_split.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_daily_split.py extract_stats.py
git commit -m "feat(daily): add split_session_by_day helper with reconciliation invariant"
```

---

## Task 2: Populate `daily_models` + `daily_message_count` at parse time

**Files:**
- Modify: `extract_stats.py` session-init (~line 2016), assistant block (~line 2285), user-typed block (~line 2170), assistant message-count (~line 2265)

- [ ] **Step 1: Add the two fields to the session-init dict**

In `extract_stats.py`, in the `sessions[session_id] = { ... }` literal, directly after the `"models": defaultdict(...)` block closes (after line 2016, before `"tools":`), add:

```python
                                    "daily_models": defaultdict(lambda: defaultdict(lambda: {
                                        "input_tokens": 0,
                                        "output_tokens": 0,
                                        "cache_read_input_tokens": 0,
                                        "cache_creation_input_tokens": 0,
                                        "cost": 0.0,
                                        "calls": 0,
                                    })),
                                    "daily_message_count": defaultdict(int),
```

- [ ] **Step 2: Populate `daily_models` in the assistant usage block**

In the assistant block, inside `if usage and usage.get("output_tokens", 0) > 0:`, locate where `turn_ts_ms` is computed (the block ending around line 2308 that appends to `_assistant_turns`). Immediately **after** that `if turn_ts_ms is not None:` append-to-`_assistant_turns` block, add:

```python
                                    if turn_ts_ms is not None:
                                        _dm = sess["daily_models"][_day_from_ms(turn_ts_ms)][model]
                                        _dm["input_tokens"] += usage.get("input_tokens", 0)
                                        _dm["output_tokens"] += usage.get("output_tokens", 0)
                                        _dm["cache_read_input_tokens"] += usage.get("cache_read_input_tokens", 0)
                                        _dm["cache_creation_input_tokens"] += usage.get("cache_creation_input_tokens", 0)
                                        _dm["cost"] += turn_cost
                                        _dm["calls"] += 1
```

- [ ] **Step 3: Populate `daily_message_count` for assistant messages**

In the assistant block, right after `sess["assistant_message_count"] += 1` (line ~2266), add:

```python
                                if ts_ms_for_msg is not None:
                                    sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
```

(`ts_ms_for_msg` is computed earlier at ~line 2087 for every message and is in scope here.)

- [ ] **Step 4: Populate `daily_message_count` for user-typed messages**

In the user block, find the branch that does `sess["message_count"] += 1` / `sess["user_message_count"] += 1` (line ~2170, the typed-prompt branch — NOT tool_results / slash-commands / meta). Right after `sess["user_message_count"] += 1`, add:

```python
                                    if ts_ms_for_msg is not None:
                                        sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
```

- [ ] **Step 5: Sanity-run the existing suite (no behavior asserted yet, just no crash)**

Run: `python -m pytest tests/ -q`
Expected: PASS (existing tests unaffected; new fields are populated but not yet consumed)

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py
git commit -m "feat(daily): record per-day model spend and message counts at parse time"
```

---

## Task 3: Fold subagent `daily_models` into the parent

**Files:**
- Modify: `extract_stats.py` subagent merge block (~line 2465)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_daily_split.py` a test proving a parent's `daily_models` absorbs a subagent's per-day spend via `_merge_model_buckets` (the mechanism the production merge will use):

```python
from extract_stats import _merge_model_buckets


class SubagentDailyMergeTest(unittest.TestCase):
    def test_parent_daily_absorbs_subagent_day(self):
        parent_daily = defaultdict(lambda: defaultdict(lambda: _bucket()))
        parent_daily["2026-06-12"]["opus"] = _bucket(cost=1.0, calls=1)
        sub_daily = {"2026-06-12": {"opus": _bucket(cost=0.5, calls=1)},
                     "2026-06-11": {"haiku": _bucket(cost=0.2, calls=1)}}
        for day, mdict in sub_daily.items():
            _merge_model_buckets(parent_daily[day], mdict)
        self.assertAlmostEqual(parent_daily["2026-06-12"]["opus"]["cost"], 1.5)
        self.assertAlmostEqual(parent_daily["2026-06-11"]["haiku"]["cost"], 0.2)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_daily_split.py::SubagentDailyMergeTest -v`
Expected: PASS (this validates the helper composition; it documents the contract the production code must use). If it fails, fix the test before touching production code.

- [ ] **Step 3: Add the production merge**

In `extract_stats.py`, in the subagent merge block, directly after the existing `_merge_model_buckets(parent["models"], sub["models"])` (line ~2465), add:

```python
            for _day, _mdict in sub.get("daily_models", {}).items():
                _merge_model_buckets(parent["daily_models"][_day], _mdict)
```

(`parent["daily_models"]` is a `defaultdict`, so `parent["daily_models"][_day]` auto-creates the inner per-model `defaultdict`, on which `_merge_model_buckets` operates. Subagent message counts are deliberately NOT merged — they are already excluded from `parent["message_count"]`, so `daily_message_count` stays symmetric.)

- [ ] **Step 4: Run the suite**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_daily_split.py extract_stats.py
git commit -m "feat(daily): fold subagent per-day spend into parent daily_models"
```

---

## Task 4: Rewire `build_dashboard_data` daily series to use the split

**Files:**
- Modify: `extract_stats.py` session loop in `build_dashboard_data` (~lines 3341-3400)

- [ ] **Step 1: Remove the per-session start-date daily writes**

In the `for model, mdata in sess["models"].items():` loop (starts ~line 3341), DELETE these lines (daily writes only — keep `seen_model_ids`, `session_*` accumulation, `display_model`, `model_totals`/`mt` updates, and `model_breakdown`):

```python
            daily_costs[date_str][display_model] += mdata["cost"]

            daily_tokens[date_str][display_model]["input"] += mdata["input_tokens"]
            daily_tokens[date_str][display_model]["output"] += mdata["output_tokens"]
            daily_tokens[date_str][display_model]["cache_read"] += mdata["cache_read_input_tokens"]
            daily_tokens[date_str][display_model]["cache_write"] += mdata["cache_creation_input_tokens"]
```

- [ ] **Step 2: Remove the old daily message / session / cache-eff writes**

Further down in the same session loop, DELETE:

```python
        daily_messages[date_str] += sess["message_count"]
        daily_sessions[date_str] += 1
```

and DELETE the cache-eff block:

```python
        sess_total_in = session_input + session_cache_read + session_cache_write
        if sess_total_in > 0 and sess["message_count"] >= 3:
            daily_cache_eff[date_str].append(session_cache_read / sess_total_in * 100)
```

(Keep `hourly_messages[hour] += ...` and `weekday_messages[weekday] += ...` — those stay start-based.)

- [ ] **Step 3: Add the per-day distribution after the model loop**

Immediately after the `for model, mdata in sess["models"].items():` loop ends (right after `model_breakdown[display_model] = {...}` closes, before `total_cost += session_cost`), insert:

```python
        per_day_models, per_day_messages = split_session_by_day(
            sess.get("daily_models", {}),
            sess["models"],
            sess.get("daily_message_count", {}),
            sess["message_count"],
            start_day=date_str,
        )
        for _day, _mdict in per_day_models.items():
            _day_in = 0
            _day_cr = 0
            for _model, _b in _mdict.items():
                _dm = get_model_display(_model)
                daily_costs[_day][_dm] += _b["cost"]
                daily_tokens[_day][_dm]["input"] += _b["input_tokens"]
                daily_tokens[_day][_dm]["output"] += _b["output_tokens"]
                daily_tokens[_day][_dm]["cache_read"] += _b["cache_read_input_tokens"]
                daily_tokens[_day][_dm]["cache_write"] += _b["cache_creation_input_tokens"]
                _day_in += _b["input_tokens"] + _b["cache_read_input_tokens"] + _b["cache_creation_input_tokens"]
                _day_cr += _b["cache_read_input_tokens"]
            if _day_in > 0:
                daily_cache_eff[_day].append(_day_cr / _day_in * 100)
        for _day, _n in per_day_messages.items():
            daily_messages[_day] += _n
        for _day in set(per_day_models) | set(per_day_messages):
            daily_sessions[_day] += 1
```

- [ ] **Step 4: Drop the temp fields before serialization**

In the cleanup loop near line 3720 (where `sess.pop("user_timestamps", None)` etc. live), add:

```python
        sess.pop("daily_models", None)
        sess.pop("daily_message_count", None)
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py
git commit -m "feat(daily): bucket daily costs/tokens/messages by actual activity day"
```

---

## Task 5: Real-data verification + reconciliation check

**Files:**
- No production changes unless a discrepancy is found.

- [ ] **Step 1: Rebuild the dashboard data**

Run the project's normal extract entrypoint (same one the cron/`update_dashboard.sh` uses; do NOT run the deploy script). Inspect:

Run:
```bash
python3 -c "
import json
d=json.load(open('public/dashboard_data.json'))
for row in d['daily_costs'][-4:]: print(row['date'], 'total', round(row['total'],2))
print('--- messages ---')
for row in d['daily_messages'][-4:]: print(row)
"
```
Expected: `2026-06-11` and `2026-06-12` now carry dori's Opus 4.8 spend (5bc2bc3b runs to 06-12; previously $0 there), not only andie's Fable 5.

- [ ] **Step 2: Verify headline totals are unchanged (reconciliation invariant)**

The grand total cost must be identical before/after — only the *distribution across days* moved.

Run:
```bash
python3 -c "
import json
d=json.load(open('public/dashboard_data.json'))
day_sum=sum(r['total'] for r in d['daily_costs'])
model_sum=sum(m.get('cost',0) for m in d['model_summary'])
print('sum(daily_costs.total)=', round(day_sum,2))
print('sum(model_summary.cost)=', round(model_sum,2))
print('match:', abs(day_sum-model_sum) < 1.0)
"
```
Expected: the two sums match within rounding (`match: True`). If they diverge, STOP — the reconciliation remainder logic is wrong; return to Task 1.

- [ ] **Step 3: Spot-check the previously mis-bucketed dori session**

Confirm `5cf2f346` (start 05-11, active to 06-11) no longer dumps its full ~$193 on 05-11.

Run:
```bash
python3 -c "
import json
d=json.load(open('public/dashboard_data.json'))
m={r['date']:r['total'] for r in d['daily_costs']}
print('2026-05-11 total now:', round(m.get('2026-05-11',0),2))
"
```
Expected: substantially lower than the pre-change 05-11 total (its later-day spend has moved to the days it happened).

- [ ] **Step 4: Commit (only if a fix was needed in Steps 1-3)**

```bash
git add extract_stats.py
git commit -m "fix(daily): <describe reconciliation fix>"
```

---

## Self-Review Notes

- **Spec coverage:** daily_costs (Task 4), daily_tokens (Task 4), daily_messages (Task 4), daily_sessions (Task 4, semantics documented), daily_cache_eff (Task 4), subagent consistency (Task 3), reconciliation/no-total-change (Task 1 + Task 5 Step 2). hourly/weekday/session.date explicitly out of scope.
- **Type consistency:** `split_session_by_day(daily_models, model_totals, daily_message_count, total_message_count, start_day)` — same signature in Task 1 definition and Task 4 call site. Bucket field names match `_DAILY_FIELDS` and the existing `sess["models"]` bucket keys.
- **Invariant:** `sum_over_days(per_day_models) == model_totals` and `sum_over_days(per_day_messages) == total_message_count`, enforced by the remainder-to-start_day logic and checked on real data in Task 5 Step 2.

---

# Phase 2: Frontend consumes the per-day data

> Added after a final review found the frontend (`templates/dashboard.js` `filterData()`) rebuilds all daily series client-side keyed on session START day (`s.date`), ignoring the backend per-day series. So Phase 1 fixed the backend but the rendered charts were unchanged. Phase 2 makes the frontend USE the server-prepared per-day data: the unfiltered default view (`filterData(0,'')`) assigns the backend series directly (offload), and filtered views redistribute each multi-day session via a new per-session `per_day` field.

**Goal:** The daily cost/token/message/cache-efficiency charts attribute activity to the day it happened, both in the default (unfiltered) view and in filtered views.

**Architecture decision:** Default view = no `currentDays` cutoff, no project filter, no hideEmpty → use `D.daily_costs/daily_tokens/daily_messages/daily_cache_efficiency` directly. Filtered view → rebuild from `F.sessions`, distributing a session via `s.per_day` (when present) or its `s.date` (single-day sessions). Backend emits a compact `per_day` ONLY for multi-day sessions to keep JSON size down.

**Known follow-up (out of scope):** the session-level date cutoff (`filterData` line 436) still filters whole sessions by `s.date`, so a session that STARTED before the selected range but is active within it is excluded entirely from filtered views. The default (no-cutoff) view — which is the reported bug — is fully correct. Documented, not fixed here.

---

## Task 6: Backend - emit `daily_tokens` series + per-session `per_day`

**Files:** Modify `extract_stats.py`.

- [ ] **Step 1: Serialize a `daily_tokens` series**

After the `daily_message_series = [...]` list comprehension (anchor: the line `daily_message_series = [` and its closing `]`), insert:

```python
    daily_token_series = []
    for d in all_dates:
        entry = {"date": d}
        day_total = 0
        day_tok = daily_tokens.get(d, {})
        for m in all_models:
            tb = day_tok.get(m)
            val = (tb["input"] + tb["output"]) if tb else 0
            entry[m] = val
            day_total += val
        entry["total"] = day_total
        daily_token_series.append(entry)
```
(`daily_tokens` is a defaultdict; use `.get(d, {})` / `.get(m)` so we never mutate it while reading. `all_dates` and `all_models` are already defined just above.)

- [ ] **Step 2: Add it to the output dict**

In the `data = {...}` dict, right after the line `"daily_costs": daily_cost_series,` (anchor), add:
```python
        "daily_tokens": daily_token_series,
```

- [ ] **Step 3: Build per-session `per_day` for multi-day sessions**

In the session loop, the split block already computes `per_day_models, per_day_messages = split_session_by_day(...)`. Immediately AFTER that call (and after the existing per-day aggregation loops that consume them), and BEFORE `total_cost += session_cost`, add:

```python
        _active_days = set(per_day_models) | set(per_day_messages)
        session_per_day = None
        if len(_active_days) > 1:
            session_per_day = {}
            for _day in sorted(_active_days):
                _models_out = {}
                for _model, _b in per_day_models.get(_day, {}).items():
                    _dm = get_model_display(_model)
                    e = _models_out.setdefault(_dm, {
                        "cost": 0.0, "input_tokens": 0, "output_tokens": 0,
                        "cache_read_tokens": 0, "cache_write_tokens": 0,
                    })
                    e["cost"] += _b["cost"]
                    e["input_tokens"] += _b["input_tokens"]
                    e["output_tokens"] += _b["output_tokens"]
                    e["cache_read_tokens"] += _b["cache_read_input_tokens"]
                    e["cache_write_tokens"] += _b["cache_creation_input_tokens"]
                for e in _models_out.values():
                    e["cost"] = round(e["cost"], 4)
                session_per_day[_day] = {
                    "messages": per_day_messages.get(_day, 0),
                    "models": _models_out,
                }
```

- [ ] **Step 4: Attach `per_day` to the session record**

In the `session_list.append({ ... })` dict, right after the line `"model_breakdown": model_breakdown,` (anchor), add:
```python
            "per_day": session_per_day,
```
(It is `None` for single-day sessions; the frontend treats a falsy `per_day` as "use `s.date`".)

- [ ] **Step 5: Verify + rebuild**

Run `python3 -m pytest tests/ -q` (still 195 passed). Then regenerate and confirm shape:
```bash
python3 extract_stats.py
python3 -c "
import json; d=json.load(open('public/dashboard_data.json'))
print('daily_tokens last:', d['daily_tokens'][-1])
md=[s for s in d['sessions'] if s.get('per_day')]
print('sessions with per_day:', len(md))
ex=next(s for s in md if s['session_id'][:8]=='5bc2bc3b')
print('5bc2bc3b per_day days:', sorted(ex['per_day']))
"
```
Expected: `daily_tokens` last entry has per-model token columns + total; some sessions carry `per_day`; `5bc2bc3b` spans 2026-06-10..2026-06-12.

- [ ] **Step 6: Commit**
```bash
git add extract_stats.py
git commit -m "feat(daily): serialize daily_tokens series and per-session per_day breakdown"
```

---

## Task 7: Frontend - `filterData` uses server series unfiltered, per_day when filtered

**Files:** Modify `templates/dashboard.js`, function `filterData` (the block currently spanning roughly lines 458-527: from the comment `// Rebuild daily aggregates from filtered sessions` through the end of the `F.daily_cache_efficiency = ...` assignment).

- [ ] **Step 1: Replace the daily-aggregation block**

REPLACE the entire block starting at the comment `// Rebuild daily aggregates from filtered sessions` and ending at the close of the `F.daily_cache_efficiency = Object.keys(cacheEffByDate).sort().map(...)` assignment (i.e. everything that builds `F.daily_costs`, `F.daily_tokens`, `F.daily_messages`, `F.daily_cache_efficiency`) with:

```javascript
  // Daily aggregates. Unfiltered default view: use the server-prepared
  // per-day series directly (no client recompute). Filtered view: rebuild
  // from sessions, distributing each multi-day session across its actual
  // activity days via s.per_day (single-day sessions fall back to s.date).
  const noFilter = currentDays === 0 && !pf && !hideEmpty;
  const _q = (sv, q) => {
    const n = sv.length;
    if (n === 0) return 0;
    if (n === 1) return sv[0];
    const pos = (n - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.min(lo + 1, n - 1);
    return sv[lo] * (1 - (pos - lo)) + sv[hi] * (pos - lo);
  };
  const _boxplot = (cacheEffByDate) => Object.keys(cacheEffByDate).sort().map(d => {
    const sv = cacheEffByDate[d].slice().sort((a, b) => a - b);
    const n = sv.length;
    const median = _q(sv, 0.5);
    const q1 = _q(sv, 0.25);
    const q3 = _q(sv, 0.75);
    const iqr = q3 - q1;
    const loFence = q1 - 1.5 * iqr;
    const hiFence = q3 + 1.5 * iqr;
    const inRange = sv.filter(v => v >= loFence && v <= hiFence);
    const whiskerLow = inRange.length ? inRange[0] : sv[0];
    const whiskerHigh = inRange.length ? inRange[inRange.length - 1] : sv[n - 1];
    const outliers = sv.filter(v => v < loFence || v > hiFence).map(v => +v.toFixed(2));
    const sum = sv.reduce((a, b) => a + b, 0);
    return {
      date: d, sessions: n,
      mean: +(sum / n).toFixed(2), median: +median.toFixed(2),
      q1: +q1.toFixed(2), q3: +q3.toFixed(2),
      whisker_low: +whiskerLow.toFixed(2), whisker_high: +whiskerHigh.toFixed(2),
      min: +sv[0].toFixed(2), max: +sv[n - 1].toFixed(2), outliers,
    };
  });

  if (noFilter) {
    F.daily_costs = D.daily_costs;
    F.daily_tokens = D.daily_tokens;
    F.daily_messages = D.daily_messages;
    F.daily_cache_efficiency = D.daily_cache_efficiency;
  } else {
    const dailyCostMap = {};
    const dailyTokenMap = {};
    const dailyMsgMap = {};
    const cacheEffByDate = {};
    F.sessions.forEach(s => {
      if (s.per_day) {
        Object.entries(s.per_day).forEach(([day, slice]) => {
          if (cutoff && day < cutoff) return;
          if (!dailyMsgMap[day]) dailyMsgMap[day] = {date: day, messages: 0, sessions: 0};
          dailyMsgMap[day].messages += slice.messages || 0;
          dailyMsgMap[day].sessions += 1;
          if (!dailyCostMap[day]) dailyCostMap[day] = {date: day, total: 0};
          if (!dailyTokenMap[day]) dailyTokenMap[day] = {date: day, total: 0};
          let dIn = 0, dCr = 0, dCw = 0;
          Object.entries(slice.models || {}).forEach(([model, d]) => {
            dailyCostMap[day].total += d.cost || 0;
            dailyCostMap[day][model] = (dailyCostMap[day][model] || 0) + (d.cost || 0);
            const tok = (d.input_tokens || 0) + (d.output_tokens || 0);
            dailyTokenMap[day][model] = (dailyTokenMap[day][model] || 0) + tok;
            dailyTokenMap[day].total += tok;
            dIn += d.input_tokens || 0; dCr += d.cache_read_tokens || 0; dCw += d.cache_write_tokens || 0;
          });
          const tot = dIn + dCr + dCw;
          if ((slice.messages || 0) >= 3 && tot > 0) {
            (cacheEffByDate[day] = cacheEffByDate[day] || []).push(dCr / tot * 100);
          }
        });
      } else {
        if (!s.date) return;
        if (!dailyMsgMap[s.date]) dailyMsgMap[s.date] = {date: s.date, messages: 0, sessions: 0};
        dailyMsgMap[s.date].messages += s.messages || 0;
        dailyMsgMap[s.date].sessions += 1;
        if (!dailyCostMap[s.date]) dailyCostMap[s.date] = {date: s.date, total: 0};
        if (!dailyTokenMap[s.date]) dailyTokenMap[s.date] = {date: s.date, total: 0};
        dailyCostMap[s.date].total += s.cost || 0;
        Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
          dailyCostMap[s.date][model] = (dailyCostMap[s.date][model] || 0) + (d.cost || 0);
          const tok = (d.input_tokens || 0) + (d.output_tokens || 0);
          dailyTokenMap[s.date][model] = (dailyTokenMap[s.date][model] || 0) + tok;
          dailyTokenMap[s.date].total += tok;
        });
        if ((s.messages || 0) >= 3) {
          const tot = (s.input_tokens || 0) + (s.cache_read_tokens || 0) + (s.cache_write_tokens || 0);
          if (tot > 0) (cacheEffByDate[s.date] = cacheEffByDate[s.date] || []).push((s.cache_read_tokens || 0) / tot * 100);
        }
      }
    });
    const allDates = [...new Set([...Object.keys(dailyCostMap), ...Object.keys(dailyMsgMap)])].sort();
    F.daily_costs = allDates.map(d => dailyCostMap[d] || {date: d, total: 0});
    F.daily_tokens = allDates.map(d => dailyTokenMap[d] || {date: d, total: 0});
    F.daily_messages = allDates.map(d => dailyMsgMap[d] || {date: d, messages: 0, sessions: 0});
    F.daily_cache_efficiency = _boxplot(cacheEffByDate);
  }
```

NOTE: `cutoff` and `pf` are computed earlier in `filterData`; `hideEmpty` too. `D.daily_tokens` now exists (Task 6). The `_q`/`_boxplot` helpers replace the old inline `_q` and box-plot map; make sure no duplicate `const _q` remains elsewhere in the function (the old one was inside the deleted block).

- [ ] **Step 2: Syntax preflight**

Run: `node -c templates/dashboard.js` (or the project's JS check). Expected: no syntax errors. If `node -c` doesn't accept it because the file is a browser script with top-level statements, instead extract-check by running the project's existing JS lint/preflight if present; otherwise wrap with `node --check`. Report what you used.

- [ ] **Step 3: Commit**
```bash
git add templates/dashboard.js
git commit -m "feat(dashboard): consume per-day series unfiltered, redistribute via per_day when filtered"
```

---

## Task 8: End-to-end smoke verification

- [ ] **Step 1: Rebuild data** (`python3 extract_stats.py`) so `public/dashboard_data.json` has `daily_tokens` + `per_day`.

- [ ] **Step 2: Headless render smoke test**

Use the project's local UI smoke-test pattern (headless chromium from the playwright cache) to load the generated dashboard HTML and assert: no console errors, the daily cost chart has a non-zero bar on 2026-06-12 and 2026-06-11, and toggling a project filter does not throw. If a ready-made smoke script exists in `tools/` or `tests/`, use it; otherwise load `public/index.html`/the rendered dashboard and check `window` for thrown errors. Report exactly what was run and the observed result. Do NOT run any deploy script.

- [ ] **Step 3: Data assertion (no browser needed as backstop)**
```bash
python3 -c "
import json; d=json.load(open('public/dashboard_data.json'))
m={r['date']:r for r in d['daily_costs']}
print('06-11 Opus 4.8:', m['2026-06-11'].get('Opus 4.8'))
print('06-12 Opus 4.8:', m['2026-06-12'].get('Opus 4.8'))
print('daily_tokens 06-12 total:', {r['date']:r['total'] for r in d['daily_tokens']}.get('2026-06-12'))
"
```
Expected: 06-11 and 06-12 carry nonzero Opus 4.8; daily_tokens has a 06-12 total. (These are what the unfiltered view now renders directly.)

- [ ] **Step 4: Final commit if anything was tweaked during smoke.**
