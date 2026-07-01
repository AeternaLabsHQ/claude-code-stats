# Teilplan A: Backend-Python-Fixes (v2-Release) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behebt die im Pre-Release-Review bestaetigten Backend-Bugs in extract_stats.py und tools/calibrate_write_categories.py (Findings 1, 2, 3, 7, 8, 9, 11, 12, 13, 37, 41b) inklusive Regressionstests.

**Architecture:** Reine Python-Stdlib-Aenderungen an einem monolithischen Extractor (extract_stats.py, ~4500 Zeilen) plus einem Kalibrier-Tool. Jeder Bugfix beginnt mit einem fehlschlagenden Test gegen die ECHTE Funktion (kein Nachbau im Test). Fuer Parser-nahe Bugs gibt es ein neues Fixture-Modul (tests/fixture_utils.py), das Mini-JSONLs in Temp-Verzeichnisse schreibt und die Modul-Globals von extract_stats monkeypatcht - dieser Ansatz ist vorab empirisch verifiziert worden (Probe-Skripte reproduzierten F1, F2, F3, F9 exakt).

**Tech Stack:** Python 3 (stdlib: calendar, datetime, json, tempfile, unittest), pytest als Runner.

## Global Constraints

- Testsuite muss nach JEDEM Task gruen sein: `python3 -m pytest tests/ -q` (Baseline vor diesem Plan: 195 passed, 20 subtests).
- KEINE Em-Dashes in neuen Strings, Kommentaren oder Prints (User-Styleguide); Code und Kommentare auf Englisch.
- extract_stats.py NIEMALS als Skript gegen die echte Config laufen lassen (der Cron deployt aus diesem Working Dir). Nur pytest und die hier definierten Fixture-Tests ausfuehren.
- update_dashboard.sh und jegliche Deploy-Infrastruktur nicht anfassen, config.json (lokal) nicht committen.
- Vor jedem Commit frisches `git status` und nur die eigenen Task-Dateien stagen (am Repo laufen parallele Sessions).
- Frontend-Kontrakte fuer Teilplan B (exakt so benennen): Config-Feld `week_anchor` (String `"mon"`..`"sun"`, Default `"mon"`), JSON top-level `data["week_anchor"]`; `error_summary.total_tool_calls` = Summe aller `s["tools"]`-Values ueber session_list; Boxplot-Trivialfilter `CACHE_EFF_MIN_MESSAGES = 3` (Slice zaehlt nur bei >= 3 Messages an dem Tag); `data["plan"]` kann `null` sein; `plan_recommendation` existiert NUR noch top-level.

---

### Task 1: Billing-Zyklen mit billing_day >= 29 (Finding 1)

`_expand_billing_cycles` ueberspringt bei billing_day >= 29 ganze Monate (der ValueError-Fallback springt per `- timedelta(days=0)` auf den 1. des uebernaechsten Monats). Zusaetzlich crasht der Current-Billing-Block in `build_plan_analysis` (Zeilen ~3161-3174) mit ValueError, wenn billing_day 29-31 in einem kurzen Monat landet. Fix: zentraler Clamping-Helper, Anker bleibt ueber Kurzmonate hinweg erhalten (Jan 31 -> Feb 28 -> Mar 31).

**Files:**
- Modify: `extract_stats.py` (Imports ~Zeile 11; `_expand_billing_cycles` ~Zeile 2928-2958; Current-Billing-Block ~Zeile 3159-3174)
- Test: `tests/test_billing_cycles.py` (neu)

**Interfaces:**
- Produces: `_month_day_clamped(year: int, month: int, day: int) -> datetime` (naiv, Tag auf Monatsende geklemmt). Wird von Task-1-Code an zwei Stellen genutzt; spaetere Tasks brauchen sie nicht.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

Neue Datei `tests/test_billing_cycles.py`:

```python
"""Regression tests for billing-cycle expansion with high billing_day anchors."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _expand_billing_cycles, _month_day_clamped


def _ph(billing_day, cost=100.0):
    return {"plan": "Max 5x", "cost_usd": cost, "billing_day": billing_day,
            "billing_cycle": "monthly"}


def _parse(d):
    return datetime.strptime(d, "%Y-%m-%d")


def test_billing_day_31_produces_five_monthly_cycles():
    cycles = _expand_billing_cycles(_ph(31), "2026-01-31", "2026-06-29")
    starts = [c["start"] for c in cycles]
    assert starts == ["2026-01-31", "2026-02-28", "2026-03-31",
                      "2026-04-30", "2026-05-31"]
    assert cycles[-1]["end"] == "2026-06-29"


def test_billing_day_31_cycles_are_gap_free_and_month_sized():
    cycles = _expand_billing_cycles(_ph(31), "2026-01-31", "2026-06-29")
    for prev, nxt in zip(cycles, cycles[1:]):
        gap = (_parse(nxt["start"]) - _parse(prev["end"])).days
        assert gap == 1, (prev, nxt)
    for c in cycles:
        length = (_parse(c["end"]) - _parse(c["start"])).days + 1
        assert 28 <= length <= 31, c


def test_anchor_day_recovers_after_short_month():
    # Feb clamps to 28, but March must return to the day-31 anchor.
    cycles = _expand_billing_cycles(_ph(31), "2026-01-31", "2026-04-15")
    assert cycles[1]["start"] == "2026-02-28"
    assert cycles[2]["start"] == "2026-03-31"


def test_unclamped_days_unchanged():
    cycles = _expand_billing_cycles(_ph(2), "2026-01-02", "2026-03-01")
    assert [c["start"] for c in cycles] == ["2026-01-02", "2026-02-02"]
    assert [c["end"] for c in cycles] == ["2026-02-01", "2026-03-01"]


def test_december_rollover():
    cycles = _expand_billing_cycles(_ph(31), "2025-11-30", "2026-01-30")
    assert [c["start"] for c in cycles] == ["2025-11-30", "2025-12-31"]
    assert cycles[1]["end"] == "2026-01-30"


def test_month_day_clamped():
    assert _month_day_clamped(2026, 2, 31) == datetime(2026, 2, 28)
    assert _month_day_clamped(2028, 2, 31) == datetime(2028, 2, 29)  # leap year
    assert _month_day_clamped(2026, 4, 31) == datetime(2026, 4, 30)
    assert _month_day_clamped(2026, 1, 15) == datetime(2026, 1, 15)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_billing_cycles.py -v`
Expected: FAIL - `ImportError: cannot import name '_month_day_clamped'` (und nach Helper-Stub: 3 Zyklen statt 5).

- [ ] **Step 3: Implementierung**

(a) In den Imports (nach `import sys`... Block, vor `import json` einsortieren):

```python
import calendar
```

(b) Direkt VOR der Funktion `_expand_billing_cycles` einfuegen:

```python
def _month_day_clamped(year, month, day):
    """Naive datetime for (year, month, day) with the day clamped to the
    month's last day. Billing anchors like 31 survive short months this
    way: callers pass the anchor day each time (never the clamped result),
    so Jan 31 -> Feb 28 -> Mar 31."""
    return datetime(year, month, min(day, calendar.monthrange(year, month)[1]))
```

(c) In `_expand_billing_cycles` den kompletten While-Loop-Kopf ersetzen. ALT (ab `while cycle_start <= end_dt:` bis einschliesslich der Zeile `cycle_end = min(next_billing - timedelta(days=1), end_dt)`):

```python
    while cycle_start <= end_dt:
        if cycle_start.month == 12:
            next_billing = cycle_start.replace(
                year=cycle_start.year + 1, month=1, day=billing_day
            )
        else:
            try:
                next_billing = cycle_start.replace(
                    month=cycle_start.month + 1, day=billing_day
                )
            except ValueError:
                # billing_day doesn't exist in target month (e.g. day 31 in Feb)
                m = cycle_start.month + 1
                first_of_next = cycle_start.replace(month=m, day=1)
                if m == 12:
                    next_billing = first_of_next.replace(year=first_of_next.year + 1, month=1, day=1) - timedelta(days=0)
                else:
                    next_billing = first_of_next.replace(month=m + 1, day=1) - timedelta(days=0)
        cycle_end = min(next_billing - timedelta(days=1), end_dt)
```

NEU:

```python
    while cycle_start <= end_dt:
        ny = cycle_start.year + (1 if cycle_start.month == 12 else 0)
        nm = 1 if cycle_start.month == 12 else cycle_start.month + 1
        # Clamp to the target month's length so day 29-31 anchors neither
        # raise ValueError nor skip whole months; passing billing_day (not
        # the clamped previous start) keeps the anchor across short months.
        next_billing = _month_day_clamped(ny, nm, billing_day)
        cycle_end = min(next_billing - timedelta(days=1), end_dt)
```

(d) Im Current-Billing-Block von `build_plan_analysis` den monatlichen Zweig ersetzen. ALT (der komplette `else:`-Zweig nach dem `annual`-Block, beginnend mit `# Find current monthly billing period start` bis einschliesslich `billing_end = billing_start.replace(month=billing_start.month + 1)`):

```python
    else:
        # Find current monthly billing period start
        if today_dt.day >= billing_day:
            billing_start = today_dt.replace(day=billing_day)
        else:
            # Previous month
            if today_dt.month == 1:
                billing_start = today_dt.replace(year=today_dt.year - 1, month=12, day=billing_day)
            else:
                billing_start = today_dt.replace(month=today_dt.month - 1, day=billing_day)

        # Find next billing date
        if today_dt.month == 12:
            billing_end = billing_start.replace(year=billing_start.year + 1, month=1)
        else:
            billing_end = billing_start.replace(month=billing_start.month + 1)
```

NEU:

```python
    else:
        # Find current monthly billing period start. billing_day is clamped
        # to each month's length so day 29-31 anchors cannot raise ValueError
        # in short months.
        candidate = _month_day_clamped(
            today_dt.year, today_dt.month, billing_day
        ).replace(tzinfo=timezone.utc)
        if candidate <= today_dt:
            billing_start = candidate
        else:
            py = today_dt.year - 1 if today_dt.month == 1 else today_dt.year
            pm = 12 if today_dt.month == 1 else today_dt.month - 1
            billing_start = _month_day_clamped(py, pm, billing_day).replace(
                tzinfo=timezone.utc)

        # Find next billing date (same clamped anchor logic)
        ny = billing_start.year + (1 if billing_start.month == 12 else 0)
        nm = 1 if billing_start.month == 12 else billing_start.month + 1
        billing_end = _month_day_clamped(ny, nm, billing_day).replace(
            tzinfo=timezone.utc)
```

Hinweis: `billing_start` ist damit auf Mitternacht UTC statt auf die aktuelle Uhrzeit gesetzt; `days_elapsed = (today_dt - billing_start).days + 1` liefert fuer den heutigen Tag weiterhin 1 (Bruchteil < 1 Tag -> .days == 0).

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_billing_cycles.py -v`
Expected: 6 passed.

- [ ] **Step 5: Volle Suite**

Run: `python3 -m pytest tests/ -q`
Expected: alle Tests gruen (201 passed, 20 subtests).

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py tests/test_billing_cycles.py
git commit -m "fix(plan): clamp billing_day anchors to month length (day >= 29 skipped whole cycles)"
```

---

### Task 2: Guard fuer leere plan_history + plan_recommendation nur einmal serialisieren (Findings 3, 37c)

`build_plan_analysis` crasht bei `plan_history: []` an `PLAN_HISTORY[-1]` (empirisch reproduziert: IndexError). Ausserdem wird `plan_recommendation` doppelt serialisiert (in `data["plan"]` und top-level); dashboard.js konsumiert ausschliesslich `D.plan_recommendation` (top-level, Zeilen 2094/2207) - die Kopie in `data["plan"]` entfernen wir per `pop`.

**Files:**
- Modify: `extract_stats.py` (Anfang von `build_plan_analysis` ~Zeile 3051; Aufrufer-Block ~Zeile 3894-3926)
- Test: `tests/test_plan_empty_history.py` (neu)

**Interfaces:**
- Produces: `build_plan_analysis(...)` liefert `None`, wenn keine plan_history konfiguriert ist. `data["plan"]` ist dann `null`, `data["plan_recommendation"]` `null`, `kpi.actual_plan_cost` 0. `plan_recommendation` ist NIE mehr in `data["plan"]` enthalten (Frontend-Kontrakt).

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Neue Datei `tests/test_plan_empty_history.py`:

```python
"""build_plan_analysis must not crash for API-only users without a plan."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es


def test_empty_plan_history_returns_none():
    saved = es.PLAN_HISTORY
    es.PLAN_HISTORY = []
    try:
        assert es.build_plan_analysis([], []) is None
    finally:
        es.PLAN_HISTORY = saved
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_plan_empty_history.py -v`
Expected: FAIL mit `IndexError: list index out of range`.

- [ ] **Step 3: Implementierung**

(a) In `build_plan_analysis` direkt nach `all_limit_events = all_limit_events or []` einfuegen:

```python
    if not PLAN_HISTORY:
        # No subscription configured (API-only user): nothing to compare
        # against, and the current-billing block below would crash on
        # PLAN_HISTORY[-1]. The caller treats None as "no plan section".
        return None
```

(b) Im Aufrufer (`build_dashboard_data`) den Block ersetzen. ALT:

```python
    # ── Actual plan cost for KPI ─────────────────────────────────────────
    actual_plan_cost = plan_analysis.get("total_plan_cost", 0)
```

NEU:

```python
    # ── Actual plan cost for KPI ─────────────────────────────────────────
    actual_plan_cost = plan_analysis.get("total_plan_cost", 0) if plan_analysis else 0
    # plan_recommendation is consumed by the frontend at the top level only;
    # pop it out of the nested plan dict so it is serialized exactly once.
    plan_recommendation = (
        plan_analysis.pop("plan_recommendation", None) if plan_analysis else None
    )
```

(c) In der `data = {...}`-Zuweisung die Zeile ersetzen. ALT:

```python
        "plan_recommendation": plan_analysis.get("plan_recommendation"),
```

NEU:

```python
        "plan_recommendation": plan_recommendation,
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_plan_empty_history.py tests/ -q`
Expected: alle gruen (202 passed).

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py tests/test_plan_empty_history.py
git commit -m "fix(plan): survive empty plan_history; serialize plan_recommendation once"
```

---

### Task 3: Subagent-Linking extrahieren, Orphans behalten (Findings 2, 41b)

`del sessions[sub_id]` steht ausserhalb des Parent-Checks: Subagents ohne auffindbaren Parent werden samt Kosten geloescht (empirisch reproduziert). Gleichzeitig re-implementiert `tests/test_daily_split.py::SubagentDailyMergeTest` die Absorb-Schleife inline statt die echte Verdrahtung zu testen. Fix: Logik in `_absorb_subagent` + `_link_subagents` extrahieren, Orphans behalten (mit Warnung), Tests gegen die echten Funktionen.

**Files:**
- Modify: `extract_stats.py` (Neue Funktionen nach `_merge_model_buckets` ~Zeile 1397; Inline-Block ~Zeile 2503-2559 ersetzen)
- Modify: `tests/test_daily_split.py` (SubagentDailyMergeTest ersetzen)
- Create: `tests/fixture_utils.py` (Parser-Fixture-Helfer, von Tasks 4, 6, 7 wiederverwendet)
- Test: `tests/test_source_integration.py` (neu)

**Interfaces:**
- Produces: `_absorb_subagent(parent: dict, sub: dict, sub_type: str = "", sub_desc: str = "") -> None`; `_link_subagents(sessions: dict) -> int` (Rueckgabe: Orphan-Anzahl).
- Produces (fixture_utils): `user_line(session_id="S1", ts="2026-06-10T10:00:00Z", text="hello world") -> dict`; `assistant_line(session_id="S1", ts="2026-06-10T10:00:05Z", msg_id="m1", model="claude-opus-4-8", output_tokens=100, content=None, usage_extra=None) -> dict`; `write_jsonl(path, objs) -> None`; Contextmanager `patched_sources(primary_dir, additional=None, plan_history=None)` (None -> Standard-Plan "Max 5x"; patcht PROJECTS_DIR, MIGRATION_ENABLED=False, ADDITIONAL_SOURCES, SOURCE_LABEL="current", PLAN_HISTORY und stellt alles wieder her).

- [ ] **Step 1: Fixture-Modul anlegen**

Neue Datei `tests/fixture_utils.py`:

```python
"""Shared helpers for parser-level integration tests: write minimal JSONL
fixtures into temp dirs and point extract_stats' module globals at them.
This pattern is validated against the real parser (see plan probes)."""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es

STD_PLAN = {"plan": "Max 5x", "start": "2026-01-01", "end": None,
            "cost_usd": 100.0, "billing_day": 2, "billing_cycle": "monthly"}


def user_line(session_id="S1", ts="2026-06-10T10:00:00Z", text="hello world"):
    return {"type": "user", "sessionId": session_id, "timestamp": ts,
            "message": {"role": "user", "content": text}}


def assistant_line(session_id="S1", ts="2026-06-10T10:00:05Z", msg_id="m1",
                   model="claude-opus-4-8", output_tokens=100, content=None,
                   usage_extra=None):
    usage = {"input_tokens": 10, "output_tokens": output_tokens,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    if usage_extra:
        usage.update(usage_extra)
    return {"type": "assistant", "sessionId": session_id, "timestamp": ts,
            "uuid": "u-" + msg_id,
            "message": {"id": msg_id, "model": model,
                        "content": (content if content is not None
                                    else [{"type": "text", "text": "hi"}]),
                        "usage": usage}}


def write_jsonl(path, objs):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(o) for o in objs) + "\n",
                    encoding="utf-8")


@contextmanager
def patched_sources(primary_dir, additional=None, plan_history=None):
    """Point extract_stats' module globals at temp fixture dirs (hermetic:
    the user's real config.json values are saved and restored)."""
    saved = (es.PROJECTS_DIR, es.MIGRATION_ENABLED, es.ADDITIONAL_SOURCES,
             es.SOURCE_LABEL, es.PLAN_HISTORY)
    es.PROJECTS_DIR = Path(primary_dir)
    es.MIGRATION_ENABLED = False
    es.ADDITIONAL_SOURCES = additional or []
    es.SOURCE_LABEL = "current"
    es.PLAN_HISTORY = [dict(STD_PLAN)] if plan_history is None else plan_history
    try:
        yield es
    finally:
        (es.PROJECTS_DIR, es.MIGRATION_ENABLED, es.ADDITIONAL_SOURCES,
         es.SOURCE_LABEL, es.PLAN_HISTORY) = saved
```

- [ ] **Step 2: Fehlschlagende Tests schreiben**

(a) In `tests/test_daily_split.py` die Klasse `SubagentDailyMergeTest` (komplett, inklusive ihres `from collections import defaultdict`-Inline-Imports) ersetzen durch:

```python
class SubagentAbsorbTest(unittest.TestCase):
    """Exercises the REAL absorb/link functions instead of re-implementing
    the merge loop inline (the old test stayed green even when the real
    wiring regressed)."""

    def _parent(self):
        return {
            "session_id": "parent",
            "models": defaultdict(lambda: _bucket()),
            "daily_models": defaultdict(lambda: defaultdict(lambda: _bucket())),
            "subagents": [],
            "agent_dispatches": [],
            "message_count": 5,
            "tools": {},
            "is_subagent": False,
            "parent_session_id": "",
        }

    def _sub(self, parent_id="parent"):
        return {
            "session_id": "agent-a1",
            "models": {"opus": _bucket(input_tokens=10, output_tokens=40,
                                       cost=0.5, calls=1)},
            "daily_models": {
                "2026-06-12": {"opus": _bucket(cost=0.5, calls=1)},
                "2026-06-11": {"haiku": _bucket(cost=0.2, calls=1)},
            },
            "subagents": [],
            "agent_dispatches": [],
            "message_count": 3,
            "tools": {"Read": 2},
            "is_subagent": True,
            "parent_session_id": parent_id,
            "agent_id": "a1",
            "agent_type": "explore",
            "agent_description": "look around",
        }

    def test_absorb_merges_totals_and_daily(self):
        from extract_stats import _absorb_subagent
        parent = self._parent()
        parent["models"]["opus"] = _bucket(cost=1.0, calls=1)
        parent["daily_models"]["2026-06-12"]["opus"] = _bucket(cost=1.0, calls=1)
        _absorb_subagent(parent, self._sub(), "explore", "look around")
        self.assertAlmostEqual(parent["models"]["opus"]["cost"], 1.5)
        self.assertAlmostEqual(
            parent["daily_models"]["2026-06-12"]["opus"]["cost"], 1.5)
        self.assertAlmostEqual(
            parent["daily_models"]["2026-06-11"]["haiku"]["cost"], 0.2)
        self.assertEqual(parent["subagents"][0]["tokens"], 50)

    def test_link_subagents_absorbs_and_removes(self):
        from extract_stats import _link_subagents
        sessions = {"parent": self._parent(), "agent-a1": self._sub()}
        orphans = _link_subagents(sessions)
        self.assertEqual(orphans, 0)
        self.assertNotIn("agent-a1", sessions)
        self.assertAlmostEqual(sessions["parent"]["models"]["opus"]["cost"], 0.5)

    def test_link_subagents_keeps_orphans(self):
        from extract_stats import _link_subagents
        sessions = {"agent-a1": self._sub(parent_id="GONE")}
        orphans = _link_subagents(sessions)
        self.assertEqual(orphans, 1)
        self.assertIn("agent-a1", sessions)
```

(b) Neue Datei `tests/test_source_integration.py`:

```python
"""Parser-level integration tests: orphan subagents and duplicate sources."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixture_utils import (assistant_line, patched_sources, user_line,
                                 write_jsonl)


class OrphanSubagentTest(unittest.TestCase):
    def test_orphan_subagent_survives_parsing(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-orphan-"))
        pd = tmp / "projects"
        write_jsonl(
            pd / "proj1" / "PARENT-GONE" / "subagents" / "agent-a1.jsonl",
            [user_line(session_id="agent-a1"),
             assistant_line(session_id="agent-a1", output_tokens=77)])
        with patched_sources(pd) as es:
            sessions = es.parse_session_transcripts()
        self.assertIn("agent-a1", sessions)
        total_out = sum(m["output_tokens"]
                        for m in sessions["agent-a1"]["models"].values())
        self.assertEqual(total_out, 77)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_daily_split.py tests/test_source_integration.py -v`
Expected: FAIL - `ImportError: cannot import name '_absorb_subagent'` bzw. `AssertionError: 'agent-a1' not found in {}`.

- [ ] **Step 4: Implementierung**

(a) In `extract_stats.py` direkt NACH `_merge_model_buckets` (nach dessen letzter Zeile `db[key] = db.get(key, 0) + val`) einfuegen:

```python
def _absorb_subagent(parent, sub, sub_type="", sub_desc=""):
    """Fold a subagent session's API usage into its parent session.

    Appends a per-subagent summary entry to parent["subagents"] and merges
    the subagent's model buckets (session totals and per-day) into the
    parent. The subagent's turns live only in its own transcript file, so
    this counts each turn exactly once. The caller removes the subagent
    from the top-level sessions dict afterwards."""
    sub_tokens = sum(m["input_tokens"] + m["output_tokens"]
                     for m in sub["models"].values())
    sub_cost = sum(m["cost"] for m in sub["models"].values())
    parent["subagents"].append({
        "agent_id": sub["session_id"],
        "type": sub_type,
        "description": sub_desc,
        "tokens": sub_tokens,
        "cost": round(sub_cost, 4),
        "messages": sub["message_count"],
        "tools": dict(sub["tools"]),
    })
    _merge_model_buckets(parent["models"], sub["models"])
    for day, mdict in sub.get("daily_models", {}).items():
        _merge_model_buckets(parent["daily_models"][day], mdict)


def _link_subagents(sessions):
    """Attach every subagent session to its parent and absorb its usage.

    Subagents whose parent transcript is missing (cleaned up by
    cleanupPeriodDays or never parsed) are KEPT as standalone sessions:
    deleting them would silently drop their tokens and cost from every
    total. Returns the orphan count."""
    subagent_ids = [sid for sid, s in sessions.items() if s.get("is_subagent")]
    orphan_count = 0
    for sub_id in subagent_ids:
        sub = sessions[sub_id]
        parent_id = sub.get("parent_session_id", "")
        if not (parent_id and parent_id in sessions):
            orphan_count += 1
            continue
        parent = sessions[parent_id]
        sub_agent_id = sub.get("agent_id", "")
        # Resolve subagent type: primary = meta.json on disk, secondary =
        # matching dispatch in parent
        sub_type = sub.get("agent_type", "")
        sub_desc = sub.get("agent_description", "")
        if not sub_type and sub_agent_id:
            for ad in parent.get("agent_dispatches", []):
                if ad.get("agent_id") == sub_agent_id:
                    sub_type = ad.get("type", "")
                    if not sub_desc:
                        sub_desc = ad.get("description", "")
                    break
        # Still no type? Insert synthetic dispatch so aggregation counts
        # the spawn once.
        if not sub_type:
            sub_type = "<unlinked>"
            parent.setdefault("agent_dispatches", []).append({
                "type": "<unlinked>",
                "description": sub_desc,
                "tool_use_id": "",
                "agent_id": sub_agent_id,
            })
        elif sub_agent_id:
            # We have a type but did the parent dispatch get linked? If not,
            # backfill agent_id on the first matching dispatch by type that's
            # still unlinked.
            for ad in parent.get("agent_dispatches", []):
                if ad.get("agent_id"):
                    continue
                if ad.get("type") == sub_type:
                    ad["agent_id"] = sub_agent_id
                    break
        _absorb_subagent(parent, sub, sub_type, sub_desc)
        del sessions[sub_id]
    if orphan_count:
        print(f"  WARNING: {orphan_count} subagent session(s) have no reachable "
              f"parent transcript; keeping them as standalone sessions so "
              f"their tokens and cost still count.")
    return orphan_count
```

(b) Den kompletten Inline-Block in `parse_session_transcripts` ersetzen. ALT: alles von `# Link subagents to parent sessions and remove from top-level` (Zeile ~2503) ueber `subagent_ids = [...]` und die gesamte For-Schleife bis einschliesslich `del sessions[sub_id]` (Zeile ~2559). NEU:

```python
    # Link subagents to parent sessions and remove them from the top level;
    # orphans (parent transcript missing) stay so their spend is not lost.
    _link_subagents(sessions)
```

WICHTIG: Der Kommentar- und Codeblock DANACH (`# Compute gap-based cache-flush count ...`) bleibt unveraendert.

- [ ] **Step 5: Tests laufen lassen**

Run: `python3 -m pytest tests/test_daily_split.py tests/test_source_integration.py -v`
Expected: alle gruen (Orphan-Test besteht jetzt).

- [ ] **Step 6: Volle Suite**

Run: `python3 -m pytest tests/ -q`
Expected: alle gruen.

- [ ] **Step 7: Commit**

```bash
git add extract_stats.py tests/test_daily_split.py tests/fixture_utils.py tests/test_source_integration.py
git commit -m "fix(parser): keep orphan subagent sessions; extract _link_subagents/_absorb_subagent"
```

---

### Task 4: Duplikat-Guard fuer alle Quellkombinationen (Finding 9)

Der Guard `if file_session_id in sessions and source_label == SOURCE_LABEL` dedupliziert nur die Kombination "primaere Quelle nach Migration". Dieselbe Session in zwei additional_sources (oder migration + additional) wird doppelt geparst und summiert (empirisch reproduziert: 200 statt 100 Output-Tokens). Fix: first-seen-wins ueber ALLE Quellen, mit Log-Hinweis.

**Files:**
- Modify: `extract_stats.py` (~Zeile 2025-2028)
- Test: `tests/test_source_integration.py` (erweitern)

**Interfaces:**
- Consumes: `tests/fixture_utils.py` aus Task 3.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

In `tests/test_source_integration.py` vor dem `if __name__ ...`-Block ergaenzen:

```python
class DuplicateSourceTest(unittest.TestCase):
    def test_same_session_in_two_additional_sources_counts_once(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-dup-"))
        prim = tmp / "primary" / "projects"
        prim.mkdir(parents=True)
        b = tmp / "b" / "projects"
        c = tmp / "c" / "projects"
        lines = [user_line(), assistant_line(output_tokens=100)]
        write_jsonl(b / "proj1" / "S1.jsonl", lines)
        write_jsonl(c / "proj1" / "S1.jsonl", lines)
        with patched_sources(prim, additional=[
            {"label": "x1", "projects_dir": b, "sudo_user": None},
            {"label": "x2", "projects_dir": c, "sudo_user": None},
        ]) as es:
            sessions = es.parse_session_transcripts()
        s1 = sessions["S1"]
        self.assertEqual(
            sum(m["output_tokens"] for m in s1["models"].values()), 100)
        self.assertEqual(s1["message_count"], 2)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_source_integration.py -v`
Expected: FAIL - output_tokens 200 statt 100.

- [ ] **Step 3: Implementierung**

In `parse_session_transcripts` den Guard ersetzen. ALT:

```python
                # Skip if this session was already fully parsed from migration
                if file_session_id in sessions and source_label == SOURCE_LABEL:
                    # Same session file in both sources — skip duplicate
                    continue
```

NEU:

```python
                # Skip if this session was already parsed from an earlier
                # source pass (migration, another additional source, or the
                # primary dir). First seen wins: parsing the same transcript
                # again would double count every token and cost.
                if file_session_id in sessions:
                    _prev_src = sessions[file_session_id].get("source", SOURCE_LABEL)
                    if _prev_src != source_label:
                        print(f"      NOTE: {file_session_id} already parsed from "
                              f"source '{_prev_src}'; skipping duplicate in "
                              f"'{source_label}'")
                    continue
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_source_integration.py tests/ -q`
Expected: alle gruen.

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py tests/test_source_integration.py
git commit -m "fix(parser): dedupe sessions across ALL source combinations (first seen wins)"
```

---

### Task 5: 1h-Cache-Writes exakt bepreisen (Finding 7)

`calc_cost` und `cost_by_type` bepreisen alle Cache-Writes mit dem 5m-Satz (1.25x Input); die `cache_write_1h`-Spalten (2x Input) aller 15 PRICING-Eintraege sind toter Code, obwohl die 1h-Tokens pro Modell bereits getrennt gezaehlt werden (`cache_1h_tokens`). User-Entscheidung: exakt bepreisen.

**Files:**
- Modify: `extract_stats.py` (`calc_cost` ~Zeile 601-620; `model_totals`-Factory ~Zeile 3397; Aggregationsschleife ~Zeile 3443-3449; `cost_by_type` ~Zeile 3726-3733)
- Test: `tests/test_cache_pricing.py` (neu)

**Interfaces:**
- Consumes: Session-Model-Buckets tragen bereits `cache_5m_tokens`/`cache_1h_tokens` (Parser-Zeilen ~2362-2364); `_merge_model_buckets` summiert generisch alle numerischen Keys, Subagent-Merges bleiben also korrekt.
- Produces: `model_totals[display]["cache_1h_tokens"]` (int) als neue Aggregatspalte.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

Neue Datei `tests/test_cache_pricing.py`:

```python
"""Cache-write pricing: 5m writes at 1.25x input, 1h writes at 2x input."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import calc_cost, resolve_pricing


def _usage(creation=1_000_000, one_hour=0):
    u = {"input_tokens": 0, "output_tokens": 0,
         "cache_read_input_tokens": 0,
         "cache_creation_input_tokens": creation}
    if one_hour:
        u["cache_creation"] = {
            "ephemeral_5m_input_tokens": creation - one_hour,
            "ephemeral_1h_input_tokens": one_hour,
        }
    return u


def test_pure_5m_writes_priced_at_5m_rate():
    p = resolve_pricing("claude-opus-4-8")
    assert calc_cost("claude-opus-4-8", _usage()) == p["cache_write_5m"]


def test_1h_writes_priced_at_1h_rate():
    p = resolve_pricing("claude-opus-4-8")
    cost = calc_cost("claude-opus-4-8",
                     _usage(creation=1_000_000, one_hour=1_000_000))
    assert cost == p["cache_write_1h"]


def test_mixed_ttl_split():
    p = resolve_pricing("claude-opus-4-8")
    cost = calc_cost("claude-opus-4-8",
                     _usage(creation=1_000_000, one_hour=400_000))
    expected = 0.6 * p["cache_write_5m"] + 0.4 * p["cache_write_1h"]
    assert abs(cost - expected) < 1e-9


def test_missing_breakdown_falls_back_to_5m_rate():
    # Old transcripts without usage.cache_creation keep the old behavior.
    p = resolve_pricing("claude-opus-4-8")
    assert calc_cost("claude-opus-4-8", _usage()) == p["cache_write_5m"]


def test_malformed_1h_exceeding_creation_is_clamped():
    u = _usage(creation=100)
    u["cache_creation"] = {"ephemeral_1h_input_tokens": 500}
    p = resolve_pricing("claude-opus-4-8")
    expected = 100 * p["cache_write_1h"] / 1_000_000
    assert abs(calc_cost("claude-opus-4-8", u) - expected) < 1e-12
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_cache_pricing.py -v`
Expected: FAIL bei `test_1h_writes_priced_at_1h_rate`, `test_mixed_ttl_split`, `test_malformed_...` (alles wird mit 5m-Satz bepreist).

- [ ] **Step 3: Implementierung**

(a) `calc_cost` komplett ersetzen:

```python
def calc_cost(model_id, usage):
    """Calculate cost for a single API call based on usage tokens.

    Cache writes are priced per TTL: 5m writes at 1.25x input
    (cache_write_5m), 1h writes at 2x input (cache_write_1h). Transcripts
    without the usage.cache_creation breakdown fall back to pricing all
    cache creation tokens at the 5m rate, matching Claude Code's own cost
    calculation."""
    p = resolve_pricing(model_id)

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    cache_info = usage.get("cache_creation") or {}
    # 1h tokens are a subset of cache_creation; clamp defensively so a
    # malformed transcript can never yield negative 5m tokens.
    cache_1h = min(cache_info.get("ephemeral_1h_input_tokens", 0), cache_creation)
    cache_5m = cache_creation - cache_1h

    cost = (
        input_tokens * p["input"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
        + cache_read * p["cache_read"] / 1_000_000
        + cache_5m * p["cache_write_5m"] / 1_000_000
        + cache_1h * p["cache_write_1h"] / 1_000_000
    )
    return cost
```

(b) `model_totals`-Factory in `build_dashboard_data` ersetzen. ALT:

```python
    model_totals = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "cost": 0.0, "calls": 0
    })
```

NEU:

```python
    model_totals = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "cache_1h_tokens": 0,
        "cost": 0.0, "calls": 0
    })
```

(c) In der Session-Schleife nach der Zeile `mt["cache_write_tokens"] += mdata["cache_creation_input_tokens"]` ergaenzen:

```python
            mt["cache_1h_tokens"] += mdata.get("cache_1h_tokens", 0)
```

(d) `cost_by_type`-Schleife: die `cache_write`-Zeile ersetzen. ALT:

```python
        cost_by_type["cache_write"] += mdata["cache_write_tokens"] * p["cache_write_5m"] / 1_000_000
```

NEU:

```python
        # Split cache writes by TTL: 1h writes cost 2x input, 5m writes 1.25x.
        _w1h = min(mdata.get("cache_1h_tokens", 0), mdata["cache_write_tokens"])
        _w5m = mdata["cache_write_tokens"] - _w1h
        cost_by_type["cache_write"] += (
            _w5m * p["cache_write_5m"] + _w1h * p["cache_write_1h"]
        ) / 1_000_000
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_cache_pricing.py tests/ -q`
Expected: alle gruen (die bestehenden calc_cost-Tests in test_model_naming.py nutzen Usage ohne cache_creation-Breakdown und bleiben unveraendert gruen).

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py tests/test_cache_pricing.py
git commit -m "fix(cost): price 1h cache writes at their real 2x rate (was 5m rate for all)"
```

---

### Task 6: total_tool_calls zaehlt echte Tool-Calls (Finding 8)

`total_tool_calls = sum(api_calls)` zaehlt Assistant-API-Calls, das UI beschriftet die Zahl aber als "tool calls" (ein API-Call kann mehrere parallele tool_use-Bloecke tragen). Fix laut Kontrakt: Summe aller `s["tools"]`-Values. Die bereits berechnete Aggregation `global_tools` liefert exakt das.

**Files:**
- Modify: `extract_stats.py` (~Zeile 3835)
- Test: `tests/test_dashboard_data_integration.py` (neu; nimmt auch die Daten-Ebene von Task 2 mit auf)

**Interfaces:**
- Consumes: `tests/fixture_utils.py` (Task 3); `global_tools` (existiert bereits weiter oben in `build_dashboard_data`).
- Produces: `error_summary.total_tool_calls` = Summe aller tool_use-Zaehler; `error_rate` nutzt denselben Nenner (Frontend-Kontrakt fuer Teilplan B).

- [ ] **Step 1: Fehlschlagende Tests schreiben**

Neue Datei `tests/test_dashboard_data_integration.py`:

```python
"""End-to-end checks on build_dashboard_data using minimal JSONL fixtures."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixture_utils import (assistant_line, patched_sources, user_line,
                                 write_jsonl)

TOOLS3 = [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
          {"type": "tool_use", "id": "t2", "name": "Read", "input": {}},
          {"type": "tool_use", "id": "t3", "name": "Bash",
           "input": {"command": "ls"}}]


def _build(tmp, session_lines, plan_history=None):
    pd = tmp / "projects"
    write_jsonl(pd / "proj1" / "S1.jsonl", session_lines)
    with patched_sources(pd, plan_history=plan_history) as es:
        sessions = es.parse_session_transcripts()
        return es.build_dashboard_data(sessions, {}, {}, [])


class ToolCallCountTest(unittest.TestCase):
    def test_total_tool_calls_counts_tool_uses_not_api_calls(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-tools-"))
        data = _build(tmp, [
            user_line(),
            assistant_line(msg_id="m1", content=TOOLS3),
            assistant_line(msg_id="m2", ts="2026-06-10T10:01:00Z"),
        ])
        # 3 tool_use blocks in 2 api calls: the label says "tool calls".
        self.assertEqual(data["error_summary"]["total_tool_calls"], 3)


class EmptyPlanHistoryDataTest(unittest.TestCase):
    def test_dashboard_builds_without_plan_history(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-noplan-"))
        data = _build(tmp, [user_line(), assistant_line()], plan_history=[])
        self.assertIsNone(data["plan"])
        self.assertIsNone(data["plan_recommendation"])
        self.assertEqual(data["kpi"]["actual_plan_cost"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_dashboard_data_integration.py -v`
Expected: `ToolCallCountTest` FAIL (2 statt 3, weil api_calls gezaehlt werden). `EmptyPlanHistoryDataTest` PASS (Task 2 hat den Guard schon eingebaut) - das ist okay, er sichert Task 2 auf Datenebene ab.

- [ ] **Step 3: Implementierung**

In `build_dashboard_data` die Zeile ersetzen. ALT:

```python
    total_tool_calls = sum(s.get("api_calls", 0) for s in session_list)
```

NEU:

```python
    # True tool-call count (every tool_use across all sessions), NOT the
    # number of assistant API calls: one API call can carry several parallel
    # tool_use blocks, and the UI labels this number "tool calls".
    total_tool_calls = sum(global_tools.values())
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_dashboard_data_integration.py tests/ -q`
Expected: alle gruen.

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py tests/test_dashboard_data_integration.py
git commit -m "fix(errors): total_tool_calls counts tool_use blocks, not API calls"
```

---

### Task 7: Trivial-Filter fuer die Server-Cache-Efficiency-Serie (Finding 12)

Die server-seitige Boxplot-Serie (`daily_cache_eff`) nimmt jeden Tages-Slice mit `_day_in > 0` auf; der Client-Rebuild filtert Sessions mit weniger als 3 Messages. Beim Umschalten von "Hide empty sessions" springen dadurch Median/IQR. Fix: derselbe Filter serverseitig, pro Tages-Slice.

**Files:**
- Modify: `extract_stats.py` (Konstante nach `SOURCE_LABEL`-Zeile ~59; Slice-Filter ~Zeile 3478)
- Test: `tests/test_dashboard_data_integration.py` (erweitern)

**Interfaces:**
- Produces: Modul-Konstante `CACHE_EFF_MIN_MESSAGES = 3` (Kontrakt mit Teilplan B: Frontend nutzt dieselbe Regel pro Slice).

- [ ] **Step 1: Fehlschlagende Tests schreiben**

In `tests/test_dashboard_data_integration.py` ergaenzen (vor `if __name__ ...`):

```python
class CacheEffTrivialFilterTest(unittest.TestCase):
    def test_one_message_session_excluded_from_cache_eff_series(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-eff1-"))
        data = _build(tmp, [
            assistant_line(msg_id="m1",
                           usage_extra={"cache_read_input_tokens": 500}),
        ])
        days = [d["date"] for d in data["daily_cache_efficiency"]]
        self.assertEqual(days, [])

    def test_three_message_session_included(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-eff3-"))
        data = _build(tmp, [
            user_line(),
            assistant_line(msg_id="m1",
                           usage_extra={"cache_read_input_tokens": 500}),
            assistant_line(msg_id="m2", ts="2026-06-10T10:01:00Z",
                           usage_extra={"cache_read_input_tokens": 500}),
        ])
        days = [d["date"] for d in data["daily_cache_efficiency"]]
        self.assertEqual(days, ["2026-06-10"])
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_dashboard_data_integration.py -v`
Expected: `test_one_message_session_excluded...` FAIL (Tag erscheint in der Serie).

- [ ] **Step 3: Implementierung**

(a) Nach der Zeile `SOURCE_LABEL = CONFIG.get("source_label", "current")` einfuegen:

```python
# Minimum messages a session-day slice needs before it enters the daily
# cache-efficiency box-plot series. 1-2 message sessions have no realistic
# cache-hit opportunity and only drag the distribution down. MUST match the
# client-side rebuild filter in templates/dashboard.js (plan B contract).
CACHE_EFF_MIN_MESSAGES = 3
```

(b) Den Slice-Append in `build_dashboard_data` ersetzen. ALT:

```python
            if _day_in > 0:
                daily_cache_eff[_day].append(_day_cr / _day_in * 100)
```

NEU:

```python
            # Skip structurally trivial slices; mirrors the frontend filter
            # (CACHE_EFF_MIN_MESSAGES) so server series == client rebuild.
            if _day_in > 0 and per_day_messages.get(_day, 0) >= CACHE_EFF_MIN_MESSAGES:
                daily_cache_eff[_day].append(_day_cr / _day_in * 100)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_dashboard_data_integration.py tests/ -q`
Expected: alle gruen.

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py tests/test_dashboard_data_integration.py
git commit -m "fix(cache-eff): apply the >=3-messages trivial filter to the server series"
```

---

### Task 8: Konfigurierbarer Wochen-Anker (Finding 13)

Chart-Marker (Frontend) nutzen hart Dienstag, die Backend-Weekly-Analyse ISO-Wochen Mo-So. Fix laut User-Entscheidung: neues Config-Feld `week_anchor` ("mon".."sun", Default "mon"), `_compute_weekly_buckets` bucketiert danach, `data["week_anchor"]` geht ans Frontend (Teilplan B stellt die Marker darauf um). `week_key` wechselt von "YYYY-Www" auf das ISO-Datum des Wochenstarts (anchor-unabhaengig eindeutig).

**Files:**
- Modify: `extract_stats.py` (Config-Global nach `CACHE_EFF_MIN_MESSAGES`; `_compute_weekly_buckets` ~Zeile 265-302; `data`-Dict: neuer Key nach `"locale"`)
- Modify: `tests/test_plan_optimizer.py` (zwei Weekly-Tests: Anker explizit + neues Key-Format)
- Modify: `config.example.json` (Feld dokumentieren)
- Test: `tests/test_week_anchor.py` (neu)

**Interfaces:**
- Produces: `WEEK_ANCHOR` (Modul-Global, validierter String); `_compute_weekly_buckets(turns, anchor_weekday=None)` (None -> Config-Anker; 0=Mo..6=So); `data["week_anchor"]` (Frontend-Kontrakt); `week_key` = "YYYY-MM-DD" des Wochenstarts (UTC).

- [ ] **Step 1: Fehlschlagende Tests schreiben**

Neue Datei `tests/test_week_anchor.py`:

```python
"""Weekly buckets must honor the configurable week anchor."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _compute_weekly_buckets


def _wt(ts, cost):
    return {"ts": ts, "cost": cost, "session_id": "s1"}


def _ms(y, m, d, h=12):
    return int(datetime.datetime(
        y, m, d, h, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def test_monday_anchor_week_key_is_week_start_date():
    b = _compute_weekly_buckets([_wt(_ms(2026, 1, 5), 1.0)], anchor_weekday=0)
    assert b[0]["week_key"] == "2026-01-05"  # 2026-01-05 is a Monday


def test_tuesday_anchor_groups_monday_into_previous_week():
    turns = [
        _wt(_ms(2026, 1, 5), 1.0),   # Monday
        _wt(_ms(2026, 1, 6), 2.0),   # Tuesday -> new week
    ]
    b = _compute_weekly_buckets(turns, anchor_weekday=1)
    assert len(b) == 2
    assert b[0]["week_key"] == "2025-12-30"  # Tuesday of the previous week
    assert b[1]["week_key"] == "2026-01-06"
    assert b[0]["cost"] == 1.0
    assert b[1]["cost"] == 2.0


def test_week_end_is_seven_days_after_start():
    b = _compute_weekly_buckets([_wt(_ms(2026, 1, 5), 1.0)], anchor_weekday=0)
    assert b[0]["week_end_ts"] - b[0]["week_start_ts"] == 7 * 24 * 3600 * 1000 - 1
```

- [ ] **Step 2: Bestehende Weekly-Tests auf neues Key-Format und expliziten Anker umstellen**

In `tests/test_plan_optimizer.py`:

(a) Im Test `test_weekly_buckets_...` (der mit den drei Turns Dez 30, Dez 31, Jan 3): die Zeilen

```python
    b = _compute_weekly_buckets(turns)
    assert len(b) == 1
    assert b[0]["week_key"] == "2026-W01"
```

ersetzen durch:

```python
    b = _compute_weekly_buckets(turns, anchor_weekday=0)
    assert len(b) == 1
    assert b[0]["week_key"] == "2025-12-29"  # Monday of that week
```

(b) In `test_weekly_buckets_splits_across_weeks` die Zeilen

```python
    b = _compute_weekly_buckets(turns)
    assert len(b) == 2
    assert b[0]["week_key"] == "2026-W01"
    assert b[1]["week_key"] == "2026-W02"
```

ersetzen durch:

```python
    b = _compute_weekly_buckets(turns, anchor_weekday=0)
    assert len(b) == 2
    assert b[0]["week_key"] == "2025-12-29"
    assert b[1]["week_key"] == "2026-01-05"
```

(Der explizite `anchor_weekday=0` macht die Tests unabhaengig vom week_anchor in der lokalen config.json des Users.)

- [ ] **Step 3: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_week_anchor.py tests/test_plan_optimizer.py -v`
Expected: FAIL - `_compute_weekly_buckets() got an unexpected keyword argument 'anchor_weekday'`.

- [ ] **Step 4: Implementierung**

(a) Nach dem `CACHE_EFF_MIN_MESSAGES`-Block (Task 7) einfuegen:

```python
# Anthropic weekly limits reset on a per-user weekday, not on ISO weeks.
# config.json "week_anchor" ("mon".."sun") sets that weekday for the weekly
# bucketing AND the frontend chart markers (exported as data["week_anchor"]).
_WEEKDAY_BY_ANCHOR = {"mon": 0, "tue": 1, "wed": 2, "thu": 3,
                      "fri": 4, "sat": 5, "sun": 6}
WEEK_ANCHOR = str(CONFIG.get("week_anchor", "mon")).strip().lower()[:3]
if WEEK_ANCHOR not in _WEEKDAY_BY_ANCHOR:
    print(f"  WARNING: invalid week_anchor {CONFIG.get('week_anchor')!r} "
          f"in config.json; falling back to 'mon'")
    WEEK_ANCHOR = "mon"
```

(b) `_compute_weekly_buckets` komplett ersetzen:

```python
def _compute_weekly_buckets(turns, anchor_weekday=None):
    """Group chronological per-turn data into calendar weeks starting on
    the configured anchor weekday (config.json "week_anchor", default
    Monday).

    Returns a list of {week_key, week_start_ts, week_end_ts, cost,
    turn_count, session_ids} dicts sorted by week_start_ts. week_key is
    the ISO date (YYYY-MM-DD, UTC) of the week's first day."""
    if anchor_weekday is None:
        anchor_weekday = _WEEKDAY_BY_ANCHOR[WEEK_ANCHOR]
    if not turns:
        return []
    buckets = {}
    for t in turns:
        ts = t.get("ts")
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        week_start = (dt - timedelta(days=(dt.weekday() - anchor_weekday) % 7)
                      ).replace(hour=0, minute=0, second=0, microsecond=0)
        key = week_start.strftime("%Y-%m-%d")
        if key not in buckets:
            buckets[key] = {
                "week_key": key,
                "week_start_ts": int(week_start.timestamp() * 1000),
                "week_end_ts": int(week_start.timestamp() * 1000)
                               + 7 * 24 * 3600 * 1000 - 1,
                "cost": 0.0,
                "turn_count": 0,
                "session_ids": set(),
            }
        b = buckets[key]
        b["cost"] += t.get("cost", 0.0)
        b["turn_count"] += 1
        sid = t.get("session_id")
        if sid:
            b["session_ids"].add(sid)
    for b in buckets.values():
        b["session_ids"] = sorted(b["session_ids"])
    return sorted(buckets.values(), key=lambda b: b["week_start_ts"])
```

(c) Im `data = {...}`-Dict direkt nach `"locale": LOCALE,` einfuegen:

```python
        "week_anchor": WEEK_ANCHOR,
```

(d) In `config.example.json` nach der Zeile `"source_label": "current",` einfuegen:

```json
  "week_anchor": "mon",
```

- [ ] **Step 5: Tests laufen lassen**

Run: `python3 -m pytest tests/test_week_anchor.py tests/test_plan_optimizer.py tests/ -q`
Expected: alle gruen.

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py tests/test_week_anchor.py tests/test_plan_optimizer.py config.example.json
git commit -m "feat(limits): configurable week_anchor for weekly buckets + frontend export"
```

Hinweis fuer den Orchestrator (nicht Teil des Commits): Der User muss `"week_anchor": "tue"` selbst in seine lokale config.json eintragen; die Datei ist nicht im Repo.

---

### Task 9: Toter Code raus (Findings 37a, 37b)

Der `msg_type == "summary"`-Zweig ist tot (eigener Code-Kommentar plus empirische Pruefung: 0 Treffer in allen realen Transcripts unter ~/.claude/projects). `_is_real_user_prompt` wird nur von Tests referenziert; die Tests werden auf die echte Produktionsfunktion `_classify_user_entry` umgestellt.

**Files:**
- Modify: `extract_stats.py` (Summary-Zweig ~Zeile 2487-2498; Kommentar ~Zeile 2220-2223; `_is_real_user_prompt` ~Zeile 1382-1384)
- Modify: `tests/test_user_message_count.py` (komplett ersetzen)

**Interfaces:**
- Consumes: `_classify_user_entry` (bleibt unveraendert).

- [ ] **Step 1: Test-Datei umstellen**

`tests/test_user_message_count.py` KOMPLETT ersetzen durch:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _classify_user_entry


def _user(content, **extra):
    obj = {"type": "user", "message": {"role": "user", "content": content}}
    obj.update(extra)
    return obj


class ClassifyUserEntryTest(unittest.TestCase):
    def test_plain_string_prompt_is_prompt(self):
        self.assertEqual(_classify_user_entry(_user("Fix the bug please")),
                         "prompt")

    def test_text_block_prompt_is_prompt(self):
        self.assertEqual(
            _classify_user_entry(_user([{"type": "text",
                                         "text": "do the thing"}])),
            "prompt")

    def test_tool_result_is_not_a_prompt(self):
        # Claude Code records tool results on the user channel.
        self.assertEqual(
            _classify_user_entry(_user([{"type": "tool_result",
                                         "tool_use_id": "abc",
                                         "content": "file contents"}])),
            "tool_result")

    def test_tool_result_mixed_with_text_is_tool_result(self):
        self.assertEqual(
            _classify_user_entry(_user([
                {"type": "tool_result", "tool_use_id": "x", "content": "y"},
                {"type": "text", "text": "trailing"}])),
            "tool_result")

    def test_slash_command_wrapper_is_command(self):
        self.assertEqual(
            _classify_user_entry(_user("<command-name>close</command-name>")),
            "command")

    def test_local_command_wrapper_is_command(self):
        self.assertEqual(
            _classify_user_entry(
                _user("<local-command-stdout>output</local-command-stdout>")),
            "command")

    def test_interrupt_marker_is_interrupt(self):
        self.assertEqual(
            _classify_user_entry(_user("[Request interrupted by user]")),
            "interrupt")

    def test_meta_entry_is_meta(self):
        self.assertEqual(
            _classify_user_entry(_user("some system note", isMeta=True)),
            "meta")

    def test_empty_content_is_meta(self):
        self.assertEqual(_classify_user_entry(_user("")), "meta")
        self.assertEqual(_classify_user_entry(_user([])), "meta")

    def test_precedence_tool_result_over_meta(self):
        obj = _user([{"type": "tool_result", "tool_use_id": "a",
                      "content": "x"}], isMeta=True)
        self.assertEqual(_classify_user_entry(obj), "tool_result")

    def test_compact_summary_is_meta_not_prompt(self):
        # Compaction is recorded as type:"user" + isCompactSummary:true with
        # a plain-string content; it must not count as a typed prompt.
        obj = _user("This session is being continued from a previous "
                    "conversation that ran out of context...",
                    isCompactSummary=True)
        self.assertEqual(_classify_user_entry(obj), "meta")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Tests laufen lassen (muessen schon VOR der Code-Aenderung gruen sein)**

Run: `python3 -m pytest tests/test_user_message_count.py -v`
Expected: 11 passed (testet nur noch die Produktionsfunktion).

- [ ] **Step 3: Toten Code entfernen**

(a) `_is_real_user_prompt` samt Docstring loeschen (die drei Zeilen ab `def _is_real_user_prompt(obj: dict) -> bool:`).

(b) Den kompletten `elif msg_type == "summary":`-Block loeschen (von `elif msg_type == "summary":` bis einschliesslich `sess["compaction_events"].append({"timestamp": ts_str})`).

(c) Den Kommentar im User-Zweig anpassen. ALT:

```python
                                # Compaction: Claude Code records it as a
                                # type:"user" entry flagged isCompactSummary
                                # (there is no type:"summary" entry — that path
                                # below is dead for current transcripts).
```

NEU:

```python
                                # Compaction: Claude Code records it as a
                                # type:"user" entry flagged isCompactSummary.
```

(d) Verifizieren, dass nichts mehr auf die geloeschten Symbole zeigt:

Run: `grep -n "_is_real_user_prompt" extract_stats.py tests/ -r; grep -n 'msg_type == "summary"' extract_stats.py`
Expected: keine Treffer.

- [ ] **Step 4: Volle Suite**

Run: `python3 -m pytest tests/ -q`
Expected: alle gruen.

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py tests/test_user_message_count.py
git commit -m "refactor: drop dead summary branch and _is_real_user_prompt wrapper"
```

---

### Task 10: Kalibrier-Tool robust machen (Finding 11)

`make_anthropic_counter` behandelt JEDE Exception als "Modell tot": ein einzelner transienter 429 degradiert ein gesundes Modell dauerhaft auf den Fallback-Tokenizer, waehrend `calibrate()` die Werte weiter unter dem Original-Modell verbucht - das korrumpiert genau die Per-Model-Tabelle, fuer die das Feature gebaut wurde. Zusaetzlich unterzaehlt die Baseline-Subtraktion jeden Block um das 1 Token des Baseline-Inhalts ".". Fix: Fehlertyp-Unterscheidung per status_code, Retry mit Backoff fuer transiente Fehler auf JEDEM Modell, degradierte Bloecke aus der Per-Model-Tabelle ausschliessen (mit sichtbarem Hinweis), +1-Korrektur, injizierbarer Client fuer Tests.

**Files:**
- Modify: `tools/calibrate_write_categories.py` (Docstring Zeile 14; `make_anthropic_counter` komplett; `make_tiktoken_counter` Rueckgabeformat; `calibrate()`; `print_table()`)
- Test: `tests/test_calibrate_tool.py` (neu)

**Interfaces:**
- Produces: Counter-Protokoll `count(text, model) -> (tokens: int, degraded: bool)` fuer BEIDE Backends; `make_anthropic_counter(default_model, client=None, sleep=time.sleep)`; `_is_model_rejection(exc) -> bool`; `calibrate()`-Ergebnis erhaelt Key `"degraded_blocks": int`.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

Neue Datei `tests/test_calibrate_tool.py`:

```python
"""Tests for tools/calibrate_write_categories.py using a fake API client."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from calibrate_write_categories import calibrate, make_anthropic_counter


class _Resp:
    def __init__(self, n):
        self.input_tokens = n


class _ApiError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _FakeMessages:
    """count_tokens fake: 7 tokens fixed overhead + one token per word.
    `failures` is a list of (model, status_code) entries, each consumed by
    the FIRST matching call (so retries succeed afterwards)."""

    def __init__(self, failures=None):
        self.failures = list(failures or [])
        self.calls = []

    def count_tokens(self, model, messages):
        self.calls.append(model)
        for i, (match, status) in enumerate(self.failures):
            if match == model:
                self.failures.pop(i)
                raise _ApiError(status)
        text = messages[0]["content"]
        return _Resp(7 + len(text.split()))


class _FakeClient:
    def __init__(self, **kw):
        self.messages = _FakeMessages(**kw)


def _counter(**kw):
    return make_anthropic_counter("claude-haiku-4-5",
                                  client=_FakeClient(**kw),
                                  sleep=lambda s: None)


class CounterTest(unittest.TestCase):
    def test_exact_token_count_no_off_by_one(self):
        count = _counter()
        toks, degraded = count("alpha beta gamma", "claude-opus-4-7")
        self.assertEqual(toks, 3)  # not 2: the "." baseline token is added back
        self.assertFalse(degraded)

    def test_transient_429_does_not_poison_model(self):
        count = _counter(failures=[("claude-opus-4-7", 429)])
        toks, degraded = count("alpha beta", "claude-opus-4-7")
        self.assertEqual((toks, degraded), (2, False))
        toks2, degraded2 = count("alpha beta gamma", "claude-opus-4-7")
        self.assertEqual((toks2, degraded2), (3, False))

    def test_model_rejection_degrades_and_flags(self):
        count = _counter(failures=[("claude-opus-4-1", 404)])
        toks, degraded = count("alpha beta", "claude-opus-4-1")
        self.assertEqual(toks, 2)
        self.assertTrue(degraded)


class CalibrateTest(unittest.TestCase):
    def test_degraded_blocks_excluded_from_per_model_table(self):
        count = _counter(failures=[("claude-opus-4-1", 404)])
        samples = {"screen_text": [
            {"payload": "alpha beta gamma delta", "model": "claude-opus-4-1"},
            {"payload": "alpha beta", "model": "claude-opus-4-8"},
        ]}
        calib = calibrate(samples, count, "fake")
        models = [pm["model"] for pm in calib["per_model"]]
        self.assertEqual(models, ["claude-opus-4-8"])
        self.assertEqual(calib["degraded_blocks"], 1)
        # Degraded blocks still count toward the category stats.
        self.assertEqual(calib["categories"]["screen_text"]["n"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_calibrate_tool.py -v`
Expected: FAIL - `TypeError: make_anthropic_counter() got an unexpected keyword argument 'client'`.

- [ ] **Step 3: Implementierung**

(a) Docstring Zeile 14: `Two backends:` ersetzen durch `Backends:`.

(b) `make_tiktoken_counter` innere Funktion ersetzen. ALT:

```python
    def count(text: str, model: str = "") -> int:  # model ignored
        return len(enc.encode(text or ""))
```

NEU:

```python
    def count(text: str, model: str = ""):  # model ignored, never degraded
        return len(enc.encode(text or "")), False
```

(c) `make_anthropic_counter` KOMPLETT ersetzen (inklusive neuer Helper davor):

```python
def _is_model_rejection(exc) -> bool:
    """True for permanent per-model API failures (unknown/retired model id,
    no access): only these justify degrading a model to the fallback
    tokenizer. Transient failures (429 rate limit, 5xx overload, network)
    must be retried on the SAME model - a single hiccup must never
    permanently poison a healthy model's calibration. Checks status_code
    instead of anthropic exception classes so test fakes work too."""
    return getattr(exc, "status_code", None) in (400, 403, 404)


def make_anthropic_counter(default_model: str, client=None, sleep=time.sleep):
    """Build a counter that tokenises with each block's own model when present.

    Protocol: count(text, model) -> (tokens, degraded). degraded is True
    when the requested model was permanently rejected by the API and the
    fallback default_model tokenizer was used instead; calibrate() excludes
    those blocks from the per-model table (a fallback ratio says nothing
    about the requested model's tokenizer).

    Caches per-model baselines (the fixed message overhead measured with a
    one-token "." message) and remembers permanently rejected models.
    `client` and `sleep` are injectable for tests."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    baselines: dict = {}
    bad_models: set = set()

    def _count_via_api(model: str, content: str) -> int:
        """count_tokens with retry + exponential backoff for transient
        errors. Raises immediately on permanent model rejection (caller
        degrades) and after exhausting retries."""
        last = None
        for attempt in range(4):
            try:
                return client.messages.count_tokens(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                ).input_tokens
            except Exception as e:
                if _is_model_rejection(e):
                    raise
                last = e
                if attempt < 3:
                    sleep(2 ** attempt)
        raise last

    def _resolve(model: str) -> str:
        """Map a requested model to the model actually used, learning
        permanent rejections exactly once (with a warning). Guarantees a
        baseline exists for the returned model."""
        m = model or default_model
        if m in bad_models:
            m = default_model
        if m not in baselines:
            try:
                baselines[m] = _count_via_api(m, ".")
            except Exception as e:
                if not _is_model_rejection(e) or m == default_model:
                    # transient failure after retries, or the fallback model
                    # itself is unusable: abort loudly instead of measuring
                    # garbage.
                    raise
                bad_models.add(m)
                print(f"  warn: count_tokens rejected model={m!r} "
                      f"({e.__class__.__name__}); falling back to "
                      f"{default_model}", file=sys.stderr)
                return _resolve(default_model)
        return m

    def count(text: str, model: str = ""):
        if not text:
            return 0, False
        requested = model or default_model
        m = _resolve(requested)
        toks = _count_via_api(m, text)
        # The baseline message content "." itself tokenises to 1 token on
        # top of the fixed per-message overhead; add it back so the
        # subtraction removes only the overhead (otherwise every block is
        # undercounted by exactly 1 token).
        return max(0, toks - baselines[m] + 1), (m != requested)

    return count
```

(Das unerreichbare `return 0` am Ende der alten Retry-Schleife entfaellt durch die Neustrukturierung.)

(d) In `calibrate()`: vor der Kategorie-Schleife `total_degraded = 0` initialisieren; die Block-Schleife anpassen. ALT:

```python
            chars = len(payload)
            toks = counter(payload, model)
            if toks <= 0:
                continue
            per_block.append((chars, toks))
            agg = per_model_totals.setdefault(model or "(unknown)",
                                              {"chars": 0, "tokens": 0, "n": 0})
            agg["chars"] += chars
            agg["tokens"] += toks
            agg["n"] += 1
```

NEU:

```python
            chars = len(payload)
            toks, degraded = counter(payload, model)
            if toks <= 0:
                continue
            per_block.append((chars, toks))
            if degraded:
                # Counted with the fallback tokenizer: fine for the category
                # stats, meaningless for the per-model table.
                total_degraded += 1
                continue
            agg = per_model_totals.setdefault(model or "(unknown)",
                                              {"chars": 0, "tokens": 0, "n": 0})
            agg["chars"] += chars
            agg["tokens"] += toks
            agg["n"] += 1
```

Und die Return-Zeile ersetzen. ALT:

```python
    return {"backend": label, "categories": results, "per_model": per_model}
```

NEU:

```python
    return {"backend": label, "categories": results, "per_model": per_model,
            "degraded_blocks": total_degraded}
```

(e) In `print_table()` am Ende (nach dem per_model-Block) ergaenzen:

```python
    if calib.get("degraded_blocks"):
        print(f"\n  note: {calib['degraded_blocks']} block(s) tokenised with "
              f"the fallback model (their model was rejected by the API); "
              f"included in category stats, excluded from the per-model table.")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/test_calibrate_tool.py tests/ -q`
Expected: alle gruen.

- [ ] **Step 5: Commit**

```bash
git add tools/calibrate_write_categories.py tests/test_calibrate_tool.py
git commit -m "fix(calibrate): retry transient API errors, exclude degraded blocks, fix 1-token baseline bias"
```

---

### Task 11: Abschlussverifikation

**Files:**
- Read-only; keine Aenderungen ausser evtl. Fixes aus gefundenen Problemen.

- [ ] **Step 1: Volle Suite mit Zaehlung**

Run: `python3 -m pytest tests/ -q`
Expected: 0 failed; erwartete Groessenordnung ~220 passed (Baseline 195 + ~26 neue, minus 9 entfernte Wrapper-Tests aus test_user_message_count.py, plus Umbauten).

- [ ] **Step 2: Keine Em-Dashes in neuen Strings**

Run: `git diff <erster-Task-1-Commit>^..HEAD -- extract_stats.py tools/calibrate_write_categories.py tests/ | grep '^+' | grep -c $'—'`
Expected: `0` (die von diesem Plan hinzugefuegten Zeilen enthalten keine Em-Dashes; Alt-Bestand auf dem Branch zaehlt nicht). Den Commit-Hash des Task-1-Commits per `git log --oneline | grep "clamp billing_day"` ermitteln.

- [ ] **Step 3: Tote Symbole wirklich weg**

Run: `grep -rn "_is_real_user_prompt" extract_stats.py tests/; grep -n 'cache_write_tokens"\] \* p\["cache_write_5m"\]' extract_stats.py`
Expected: beide Greps liefern keine Treffer (Wrapper geloescht; cache_write nutzt ueberall den TTL-Split).

- [ ] **Step 4: Orchestrator informieren**

Kein Commit. Ergebnis an den Orchestrator melden: Task-Status, finale Testzahl, Abweichungen vom Plan. Erinnerung an den User-Handgriff: `"week_anchor": "tue"` in der lokalen config.json setzen (Datei ist nicht im Repo).

---

## Self-Review (durchgefuehrt beim Planschreiben)

- **Spec-Abdeckung:** F1 -> Task 1 (inkl. Current-Billing-Crash als gleiche Fehlerklasse, im Review-Finding implizit), F2 -> Task 3, F3 -> Task 2, F7 -> Task 5, F8 -> Task 6, F9 -> Task 4, F11 -> Task 10, F12 -> Task 7, F13 -> Task 8, F37 -> Tasks 2 (c) und 9 (a, b), F41b -> Task 3. Kein Finding offen.
- **Empirische Absicherung:** F1 (3 statt 5 Zyklen), F2 (Orphan verschwindet), F3 (IndexError), F9 (200 statt 100 Tokens) wurden vor Planerstellung mit Probe-Skripten gegen den echten Parser reproduziert; die Fixture-Zeilenformate in fixture_utils.py sind exakt die getesteten. build_dashboard_data(sessions, {}, {}, []) mit Minimal-Fixture verifiziert (tools: {'Read': 2, 'Bash': 1}, daily_cache_efficiency-Shape [{date, ...}]).
- **Platzhalter-Scan:** keine TBD/TODO; jeder Code-Step enthaelt vollstaendigen Code; Kommandos mit erwartetem Output.
- **Typ-/Namens-Konsistenz:** `_month_day_clamped` (Task 1) nur in Task 1 genutzt; `patched_sources`/`assistant_line`/`user_line`/`write_jsonl` (Task 3) konsistent in Tasks 4, 6, 7; Counter-Protokoll `(tokens, degraded)` konsistent zwischen make_anthropic_counter, make_tiktoken_counter und calibrate() (Task 10); `CACHE_EFF_MIN_MESSAGES`, `WEEK_ANCHOR`, `data["week_anchor"]`, `total_tool_calls` entsprechen woertlich den Global-Constraints-Kontrakten fuer Teilplan B.
- **Risiken (bewusst akzeptiert):** (1) week_key-Formatwechsel ist backend-intern plus zwei angepasste Tests; dashboard.js liest week_key/week_start_ts nicht (per Grep verifiziert). (2) Der Summary-Zweig koennte in fremden, sehr alten Transcripts theoretisch noch vorkommen; dann zaehlte er Session-Titel faelschlich als Compactions, sein Wegfall ist also auch dort eher Korrektur als Regression. (3) error_rate sinkt sichtbar durch den neuen Nenner; das ist die gewollte Korrektur (Teilplan B passt Label/Anzeige an).
