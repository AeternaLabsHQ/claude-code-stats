# Plan 1: Kern-Extraktion `claudestats_core` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die kalibrierte Domänenlogik aus `extract_stats.py` (4617 Zeilen) in ein
importierbares, stdlib-reines Package `claudestats_core` extrahieren, ohne das
Verhalten des CLI-Tools um ein Byte zu ändern - bewiesen per Golden-Master.

**Architecture:** `extract_stats.py` bleibt der CLI-Driver (Config, Datei-Discovery,
sudo-Quellen, `load_*`-Loader, HTML-Generierung) und re-exportiert alle bewegten
Namen, damit die ~25 bestehenden Testmodule unverändert grün bleiben. Der Kern
bekommt ein `settings`-Modul für die 7 Laufzeit-Einstellungen, die heute
Modul-Globals sind. Die Session-State-Machine wird an der Naht
Datei-Discovery/Zeilen-Verarbeitung getrennt: der Driver liefert geparste
JSONL-Objekte + Datei-Metadaten, der Kern baut daraus Sessions
(`absorb_file`/`finalize_sessions`). Später füttert der Collector-Server-Driver
(Plan 4) denselben Kern aus Postgres.

**Tech Stack:** Python >= 3.10 (Code nutzt `dict | None`), nur stdlib im Kern,
setuptools-`pyproject.toml` für die Git-Dependency des Collector-Repos, pytest.

## Global Constraints

- **Kein Verhaltens-Delta:** Nach JEDEM Task müssen `python3 -m pytest tests/ -q`
  UND `python3 tools/golden_master.py check` grün sein. Ein Golden-Master-Diff ist
  ein Task-Abbruch, kein "kleiner Unterschied".
- **Kern ist stdlib-rein:** kein Import außerhalb der Python-Standardbibliothek in
  `claudestats_core/` (Spec §2 Dependency-Grenze).
- **Kern importiert nie `extract_stats`:** Abhängigkeitsrichtung ist ausschließlich
  `extract_stats.py -> claudestats_core`, nie umgekehrt.
- **Verbatim-Moves:** Funktionskörper werden unverändert verschoben. Einzige
  erlaubte Text-Änderung im Körper: die in den Tasks EXAKT aufgelisteten
  Ersetzungen `<GLOBAL>` -> `settings.<GLOBAL>`. Nichts "nebenbei aufräumen",
  keine Umbenennungen, keine Format-Fixes (feedback_refactor_with_tradeoff).
- **Re-Export-Pflicht:** Jeder aus `extract_stats.py` entfernte Name wird dort
  durch einen expliziten Import aus dem Kern ersetzt (`from claudestats_core.X
  import a, b, c`) - Tests und verbleibender Code importieren/nutzen weiter
  `extract_stats.<name>`.
- **Branch:** `feature/core-extraction`, abgezweigt von
  `feature/dashboard-rethink-v2`. Ausführung in einem git worktree
  (superpowers:using-git-worktrees) - WICHTIG: der Deploy-Cron dieses Repos läuft
  aus dem Haupt-Working-Dir, dort NICHT den Branch wechseln
  (project_claude_stats_deploy).
- **Golden-Master-Daten sind sensibel** (echte Prompts, Pfade): `.golden/` ist
  gitignored und wird NIE committet.
- **Zeilennummern** in den Tasks beziehen sich auf `extract_stats.py` im
  Ausgangszustand (Commit-Stand von `feature/dashboard-rethink-v2`,
  `wc -l` = 4617). Nach Task 3 verschieben sie sich; Tasks 4-5 lokalisieren
  deshalb über Funktionsnamen, nicht über Zeilennummern.

### Move-Mechanik M (von Tasks 3-5 referenziert, hier einmal definiert)

Für jeden Modul-Move gilt exakt diese Abfolge:

1. Neue Datei `claudestats_core/<modul>.py` anlegen: Docstring (eine Zeile,
   was das Modul verantwortet), benötigte stdlib-Imports (nur die, die die
   bewegten Funktionen wirklich nutzen), benötigte Kern-Imports
   (`from . import settings`, `from .<anderes_modul> import ...` - im Task
   aufgelistet), dann die Funktionen/Konstanten in Original-Reihenfolge
   per Cut-and-Paste aus `extract_stats.py` einfügen.
2. Die im Task aufgelisteten `settings.`-Ersetzungen im bewegten Code anwenden
   (und NUR diese).
3. In `extract_stats.py` die bewegten Definitionen löschen und im
   Re-Export-Block (direkt nach den stdlib-Imports, Zeile ~22) die Import-Zeile
   aus dem Task einfügen.
4. `python3 -m pytest tests/ -q` -> alle Tests PASS.
5. `python3 tools/golden_master.py check` -> `GOLDEN MASTER: OK`.
6. Commit mit der im Task angegebenen Message.

---

### Task 1: Golden-Master-Harness

**Files:**
- Create: `tools/golden_master.py`
- Modify: `.gitignore` (Zeile ans Ende: `.golden/`)
- Test: der Harness ist selbst das Testwerkzeug; Verifikation siehe Steps

**Interfaces:**
- Produces: `python3 tools/golden_master.py baseline` (Referenz einfrieren) und
  `python3 tools/golden_master.py check` (Exit 0 = byte-identisch, Exit 1 = Diff,
  Exit 2 = Baseline von anderem UTC-Tag). Alle späteren Tasks rufen `check` auf.

- [ ] **Step 1: `.gitignore` erweitern**

Ans Ende von `.gitignore` anfügen:

```
.golden/
```

- [ ] **Step 2: Harness schreiben**

`tools/golden_master.py`:

```python
#!/usr/bin/env python3
"""Golden-Master-Harness fuer die Kern-Extraktion.

Friert das normalisierte public/dashboard_data.json als Referenz ein und
vergleicht spaetere Laeufe byte-genau dagegen. Das ist der
Nicht-Regressions-Beweis fuer jeden Refactor-Schritt.

ACHTUNG: .golden/ enthaelt echte Session-Daten (Prompts, Pfade) und ist
gitignored. Nie committen.

build_plan_analysis() haengt von datetime.now() ab (Billing-Zyklen bis
"heute"). Baseline und Check muessen deshalb am selben UTC-Tag laufen;
bei Tageswechsel Baseline von einem gruenen Commit-Stand neu erzeugen.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / ".golden"
BASELINE = GOLDEN_DIR / "baseline.json"
BASELINE_META = GOLDEN_DIR / "baseline_meta.json"
CURRENT = GOLDEN_DIR / "current.json"
DATA = ROOT / "public" / "dashboard_data.json"

VOLATILE_TOP_LEVEL_KEYS = ("generated_at",)


def _run_pipeline():
    r = subprocess.run([sys.executable, str(ROOT / "extract_stats.py")], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"extract_stats.py failed (rc={r.returncode})")


def _normalized() -> str:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for key in VOLATILE_TOP_LEVEL_KEYS:
        data.pop(key, None)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cmd_baseline():
    GOLDEN_DIR.mkdir(exist_ok=True)
    _run_pipeline()
    BASELINE.write_text(_normalized(), encoding="utf-8")
    BASELINE_META.write_text(
        json.dumps({"utc_day": _today()}), encoding="utf-8"
    )
    print(f"Baseline geschrieben: {BASELINE}")


def cmd_check():
    if not BASELINE.exists():
        sys.exit("Keine Baseline. Erst: python3 tools/golden_master.py baseline")
    meta = json.loads(BASELINE_META.read_text(encoding="utf-8"))
    if meta.get("utc_day") != _today():
        sys.exit(2)
    _run_pipeline()
    current = _normalized()
    if current == BASELINE.read_text(encoding="utf-8"):
        print("GOLDEN MASTER: OK (byte-identisch)")
        return
    CURRENT.write_text(current, encoding="utf-8")
    print("GOLDEN MASTER: DIFF!")
    print(f"  diff {BASELINE} {CURRENT} | head -50")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("baseline", "check"):
        sys.exit("Usage: golden_master.py baseline|check")
    {"baseline": cmd_baseline, "check": cmd_check}[sys.argv[1]]()
```

Hinweis zu Exit 2 (Tageswechsel): Baseline nur von einem Stand neu erzeugen, bei
dem `check` zuletzt grün war (nach jedem Task-Commit gegeben) - also committen,
dann `baseline` neu, dann weiterarbeiten.

- [ ] **Step 3: Baseline erzeugen und Harness verifizieren**

```bash
python3 tools/golden_master.py baseline
python3 tools/golden_master.py check
```

Expected: erster Aufruf schreibt `.golden/baseline.json`, zweiter endet mit
`GOLDEN MASTER: OK (byte-identisch)` und Exit 0. (Läuft die volle Pipeline
zweimal; je nach Datenmenge ca. 1-3 Minuten pro Lauf.)

- [ ] **Step 4: Negativ-Probe (Harness erkennt Diffs wirklich)**

Wichtig: NICHT `public/dashboard_data.json` manipulieren und `check` aufrufen -
`check` läuft die Pipeline neu und überschriebe die Manipulation. Stattdessen
die Vergleichslogik direkt prüfen:

```bash
python3 - <<'EOF'
import sys
sys.path.insert(0, "tools")
import golden_master as gm
base = gm.BASELINE.read_text(encoding="utf-8")
assert gm._normalized() == base, "sollte nach Pipeline-Lauf identisch sein"
mutated = base.replace('"total_cost":', '"total_cost_x":', 1)
assert mutated != base
print("Negativ-Probe: Vergleichslogik unterscheidet Abweichungen. OK")
EOF
```

Expected: `Negativ-Probe: ... OK`

- [ ] **Step 5: Commit (inkl. der beiden Architektur-Dokumente)**

```bash
git add tools/golden_master.py .gitignore \
  docs/superpowers/plans/audit-collector-v0.md \
  docs/superpowers/plans/audit-collector-v0-architektur.md \
  docs/superpowers/plans/2026-07-06-plan1-core-extraction.md
git commit -m "chore(core): golden-master harness + audit-collector v0 spec/architektur"
```

---

### Task 2: Package-Skelett `claudestats_core` + settings

**Files:**
- Create: `pyproject.toml`
- Create: `claudestats_core/__init__.py`
- Create: `claudestats_core/settings.py`
- Modify: `extract_stats.py` (configure-Aufruf nach Zeile 209)
- Test: `tests/test_core_settings.py`

**Interfaces:**
- Produces: `claudestats_core.settings` mit den Modul-Attributen `WEEK_ANCHOR`
  (str, default `"mon"`), `PLAN_HISTORY` (list, default `[]`),
  `PLAN_CAPACITY_OVERRIDE_PRO_USD` (float | None, default `None`),
  `CACHE_EFF_MIN_MESSAGES` (int, default `3`), `SOURCE_LABEL` (str, default
  `"current"`), `LOCALE` (dict, default `{}`), `DISPLAY_NAME` (str | None,
  default `None`) sowie `configure(**kwargs)` (lowercase-Keys, unbekannter Key
  -> `AttributeError`). Tasks 3-5 ersetzen Global-Reads durch `settings.<NAME>`;
  der Collector-Server-Driver (Plan 4) ruft `configure()` pro Tenant.

- [ ] **Step 1: Failing Test schreiben**

`tests/test_core_settings.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_configure_sets_known_setting():
    from claudestats_core import settings
    saved = settings.WEEK_ANCHOR
    try:
        settings.configure(week_anchor="wed")
        assert settings.WEEK_ANCHOR == "wed"
    finally:
        settings.WEEK_ANCHOR = saved


def test_configure_rejects_unknown_setting():
    from claudestats_core import settings
    with pytest.raises(AttributeError):
        settings.configure(does_not_exist=1)


def test_core_imports_without_config_json(tmp_path):
    """Der Kern muss ohne config.json und ohne extract_stats importierbar
    sein - sonst ist er als Library (Collector-Repo!) unbrauchbar."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    r = subprocess.run(
        [sys.executable, "-c",
         "import claudestats_core, sys;"
         "assert 'extract_stats' not in sys.modules"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag verifizieren**

Run: `python3 -m pytest tests/test_core_settings.py -v`
Expected: FAIL / ERROR mit `ModuleNotFoundError: No module named 'claudestats_core'`

- [ ] **Step 3: Package anlegen**

`claudestats_core/settings.py`:

```python
"""Laufzeit-Einstellungen des Kerns.

extract_stats.py (CLI) befuellt sie aus config.json; der Collector-Server
(anderes Repo) pro Tenant. Defaults sind so gewaehlt, dass der Kern ohne
configure()-Aufruf lauffaehig ist.
"""

WEEK_ANCHOR = "mon"
PLAN_HISTORY = []
PLAN_CAPACITY_OVERRIDE_PRO_USD = None
CACHE_EFF_MIN_MESSAGES = 3
SOURCE_LABEL = "current"
LOCALE = {}
DISPLAY_NAME = None

_KNOWN = {
    "WEEK_ANCHOR", "PLAN_HISTORY", "PLAN_CAPACITY_OVERRIDE_PRO_USD",
    "CACHE_EFF_MIN_MESSAGES", "SOURCE_LABEL", "LOCALE", "DISPLAY_NAME",
}


def configure(**kwargs):
    """Setzt Einstellungen per lowercase-Keyword; unbekannte Namen -> Fehler."""
    import sys
    mod = sys.modules[__name__]
    for key, value in kwargs.items():
        name = key.upper()
        if name not in _KNOWN:
            raise AttributeError(f"unknown setting: {key}")
        setattr(mod, name, value)
```

`claudestats_core/__init__.py`:

```python
"""claudestats_core - kalibrierte Domaenenlogik von claude-stats.

Stdlib-rein. Public API waechst mit den Extraktions-Tasks; finale
Re-Exports in __init__ kommen im letzten Task.
"""
from . import settings  # noqa: F401
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "claudestats-core"
version = "0.1.0"
description = "Kalibrierte claude-stats Domaenenlogik (Kosten, Cache, Limits, Attribution) als Library"
requires-python = ">=3.10"

[tool.setuptools]
packages = ["claudestats_core"]
```

- [ ] **Step 4: configure-Aufruf in `extract_stats.py` verdrahten**

Direkt nach der Zeile `PLAN_CAPACITY_OVERRIDE_PRO_USD = CONFIG.get("plan_capacity_override_pro_usd")`
(Zeile 209) einfügen:

```python
import claudestats_core.settings as _core_settings
_core_settings.configure(
    week_anchor=WEEK_ANCHOR,
    plan_history=PLAN_HISTORY,
    plan_capacity_override_pro_usd=PLAN_CAPACITY_OVERRIDE_PRO_USD,
    cache_eff_min_messages=CACHE_EFF_MIN_MESSAGES,
    source_label=SOURCE_LABEL,
    locale=LOCALE,
    display_name=CONFIG.get("display_name"),
)
```

(`WEEK_ANCHOR`, `CACHE_EFF_MIN_MESSAGES`, `SOURCE_LABEL`, `LOCALE` sind an
Zeile 209 bereits definiert - Zeilen 51-77.)

- [ ] **Step 5: Tests laufen lassen**

Run: `python3 -m pytest tests/test_core_settings.py -v && python3 -m pytest tests/ -q`
Expected: alle PASS

- [ ] **Step 6: Golden-Master prüfen**

Run: `python3 tools/golden_master.py check`
Expected: `GOLDEN MASTER: OK (byte-identisch)`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml claudestats_core/ tests/test_core_settings.py extract_stats.py
git commit -m "feat(core): claudestats_core package skeleton + settings module"
```

---

### Task 3: Leaf-Module verschieben (pricing, attribution, classify, anomalies, limits)

Fünf mechanische Moves nach Move-Mechanik M (siehe Global Constraints), je ein
Commit. Reihenfolge exakt wie unten (spätere Module importieren frühere nicht;
alle fünf sind Blätter ohne Kern-interne Abhängigkeiten untereinander - einzige
Ausnahme: keine).

**Files:**
- Create: `claudestats_core/pricing.py`, `claudestats_core/attribution.py`,
  `claudestats_core/classify.py`, `claudestats_core/anomalies.py`,
  `claudestats_core/limits.py`
- Modify: `extract_stats.py` (Definitionen raus, Re-Export-Imports rein)
- Test: bestehende Suite + Golden-Master (Moves sind verhaltensneutral;
  neue Unit-Tests sind hier explizit NICHT das Werkzeug - das Netz sind die
  vorhandenen ~25 Testmodule plus Golden-Master)

**Interfaces:**
- Consumes: `claudestats_core.settings` (Task 2)
- Produces (von Tasks 4-5 und extract_stats konsumiert):
  - `pricing`: `PRICING: dict`, `DEFAULT_PRICING: dict`, `_version(maj, minor)`,
    `derive_model_display(model_id) -> str`, `get_model_display(model_id) -> str`,
    `pricing_for_display(display_name) -> dict`, `resolve_pricing(model_id) -> dict`,
    `build_pricing_warnings(model_ids) -> list`, `calc_cost(model_id, usage) -> float`
  - `attribution`: `attribute_turn_tokens(output_tokens, cost, tool_names) -> dict`,
    `WRITE_CATEGORIES: tuple`, `_block_weight(block)`, `_block_category(block,
    turn_has_tools)`, `attribute_write_categories(content_blocks, output_tokens) -> dict`
  - `classify`: `_is_user_plan_limit_text(text) -> bool`,
    `_classify_user_entry(obj) -> str`, `_merge_streamed_assistant_entries(entries) -> list`,
    `_classify_tool_error(msg, tool_name) -> tuple`, `_clean_error_text(s) -> str`,
    `_route_tool_error(source, category)`, `_extract_command_label(text) -> str`,
    `_classify_api_error(text) -> str`
  - `anomalies`: `CONTEXT_1M_THRESHOLD: int`, `summarize_context_window(turns,
    threshold=CONTEXT_1M_THRESHOLD) -> dict`, `_detect_cache_flushes(turns,
    has_1h_cache, compaction_ts_ms) -> dict`, `_compute_idle_gap_summary(turns) -> dict | None`
  - `limits`: `_WEEKDAY_BY_ANCHOR: dict`, `PLAN_TIER_FACTORS: dict`,
    `PRO_CAPACITY_USD_DEFAULT: float`, `_normalize_tier_name(raw)`,
    `_compute_5h_windows(turns)`, `_compute_weekly_buckets(turns, anchor_weekday=None)`,
    `_estimate_5h_window_cap_usd(windows, limit_event_window_ids, ...)`,
    `_detect_5h_fingerprint_events(prompts) -> list`, `_iso_to_ms(s)`,
    `_dedupe_limit_events(events)`, `_match_limit_events_to_windows(events, windows)`,
    `_count_5h_hits(indexed_windows, caps, tier_by_idx, anchor_ids)`

- [ ] **Step 1: Move `pricing.py`** (Mechanik M)

Zu verschieben (Original-Zeilen): `PRICING` (395-490), `DEFAULT_PRICING`
(491-497), `_version` (498-507), `derive_model_display` (508-563),
`get_model_display` (564-571), `pricing_for_display` (572-584),
`resolve_pricing` (585-599), `build_pricing_warnings` (600-629),
`calc_cost` (630-659).
settings-Ersetzungen: keine. Kern-Imports: keine.
Re-Export-Zeile in `extract_stats.py`:

```python
from claudestats_core.pricing import (
    PRICING, DEFAULT_PRICING, _version, derive_model_display,
    get_model_display, pricing_for_display, resolve_pricing,
    build_pricing_warnings, calc_cost,
)
```

Verify: `python3 -m pytest tests/ -q` PASS, `python3 tools/golden_master.py check` OK.
Commit: `refactor(core): move pricing tables and cost calc to claudestats_core.pricing`

- [ ] **Step 2: Move `attribution.py`** (Mechanik M)

Zu verschieben: `attribute_turn_tokens` (660-706), `WRITE_CATEGORIES` (707-717),
`_block_weight` (718-742), `_block_category` (743-766),
`attribute_write_categories` (767-813).
settings-Ersetzungen: keine. Kern-Imports: keine.
Re-Export-Zeile:

```python
from claudestats_core.attribution import (
    attribute_turn_tokens, WRITE_CATEGORIES, _block_weight,
    _block_category, attribute_write_categories,
)
```

Verify wie oben.
Commit: `refactor(core): move token/write-category attribution to claudestats_core.attribution`

- [ ] **Step 3: Move `classify.py`** (Mechanik M)

Zu verschieben: `_is_user_plan_limit_text` (1368-1381), `_classify_user_entry`
(1382-1418), `_merge_streamed_assistant_entries` (1575-1619),
`_classify_tool_error` (1620-1674), `_clean_error_text` (1675-1685),
`_route_tool_error` (1686-1700), `_extract_command_label` (1701-1717),
`_classify_api_error` (1718-1745).
settings-Ersetzungen: keine. Kern-Imports: keine.
Re-Export-Zeile:

```python
from claudestats_core.classify import (
    _is_user_plan_limit_text, _classify_user_entry,
    _merge_streamed_assistant_entries, _classify_tool_error,
    _clean_error_text, _route_tool_error, _extract_command_label,
    _classify_api_error,
)
```

Verify wie oben.
Commit: `refactor(core): move entry/error classification and stream merge to claudestats_core.classify`

- [ ] **Step 4: Move `anomalies.py`** (Mechanik M)

Zu verschieben: `CONTEXT_1M_THRESHOLD` (1746-1748), `summarize_context_window`
(1749-1777), `_detect_cache_flushes` (1778-1842), `_compute_idle_gap_summary`
(1843-1907).
settings-Ersetzungen: keine. Kern-Imports: keine.
Re-Export-Zeile:

```python
from claudestats_core.anomalies import (
    CONTEXT_1M_THRESHOLD, summarize_context_window,
    _detect_cache_flushes, _compute_idle_gap_summary,
)
```

Verify wie oben.
Commit: `refactor(core): move cache-flush/idle-gap/context-window detection to claudestats_core.anomalies`

- [ ] **Step 5: Move `limits.py`** (Mechanik M)

Zu verschieben: `_WEEKDAY_BY_ANCHOR` (71-72), `PLAN_TIER_FACTORS` (215),
`PRO_CAPACITY_USD_DEFAULT` (220), `_normalize_tier_name` (223-241),
`_compute_5h_windows` (242-282), `_compute_weekly_buckets` (283-324),
`_estimate_5h_window_cap_usd` (325-394), `_detect_5h_fingerprint_events`
(1908-1970), `_iso_to_ms` (1971-1978), `_dedupe_limit_events` (1979-2009),
`_match_limit_events_to_windows` (2010-2034), `_count_5h_hits` (2035-2056).
settings-Ersetzung (genau 1 Stelle, in `_compute_weekly_buckets`):

```python
# vorher (Zeile 292):
        anchor_weekday = _WEEKDAY_BY_ANCHOR[WEEK_ANCHOR]
# nachher:
        anchor_weekday = _WEEKDAY_BY_ANCHOR[settings.WEEK_ANCHOR]
```

Kern-Imports: `from . import settings`.
Re-Export-Zeile:

```python
from claudestats_core.limits import (
    _WEEKDAY_BY_ANCHOR, PLAN_TIER_FACTORS, PRO_CAPACITY_USD_DEFAULT,
    _normalize_tier_name, _compute_5h_windows, _compute_weekly_buckets,
    _estimate_5h_window_cap_usd, _detect_5h_fingerprint_events,
    _iso_to_ms, _dedupe_limit_events, _match_limit_events_to_windows,
    _count_5h_hits,
)
```

Achtung: die WEEK_ANCHOR-Validierung in `extract_stats.py` (Zeilen 73-77) nutzt
`_WEEKDAY_BY_ANCHOR` - sie funktioniert über den Re-Export weiter, der
Import-Block muss also VOR Zeile 73 stehen (tut er: Zeile ~22).
Verify wie oben.
Commit: `refactor(core): move 5h-window/weekly/limit-event math to claudestats_core.limits`

---

### Task 4: Session-Builder-Schnitt (`sessions.py`) + Driver-Umbau

Der inhaltliche Kern des Plans: `parse_session_transcripts()` wird an der Naht
Datei-Discovery/Zeilen-Verarbeitung getrennt. Alles ab hier lokalisiert über
Funktionsnamen (Zeilennummern haben sich durch Task 3 verschoben).

**Files:**
- Create: `claudestats_core/sessions.py`
- Modify: `extract_stats.py` (`parse_session_transcripts` wird Driver;
  Definitionen `_merge_model_buckets`, `_absorb_subagent`, `_link_subagents`,
  `_day_from_ms`, `split_session_by_day` raus + Re-Export)
- Test: bestehende Suite (u.a. `test_source_integration.py`,
  `test_user_message_count.py`, `test_daily_split.py` decken genau diese
  State-Machine über `parse_session_transcripts` ab) + Golden-Master

**Interfaces:**
- Consumes: `settings` (Task 2); `calc_cost` (pricing); `attribute_turn_tokens`,
  `attribute_write_categories`, `WRITE_CATEGORIES` (attribution);
  `_classify_user_entry`, `_is_user_plan_limit_text`, `_classify_api_error`,
  `_classify_tool_error`, `_route_tool_error`, `_merge_streamed_assistant_entries`
  (classify); `_detect_cache_flushes`, `_compute_idle_gap_summary`,
  `summarize_context_window` (anomalies)
- Produces (Server-Driver in Plan 4 nutzt exakt diese drei):
  - `SessionFileMeta` (dataclass): `source_label: str`, `file_session_id: str`,
    `project_name: str`, `file_size: int = 0`, `is_subagent: bool = False`,
    `parent_session_id: str = ""`, `agent_id: str = ""`, `agent_type: str = ""`,
    `agent_description: str = ""`
  - `absorb_file(sessions: dict, meta: SessionFileMeta, parsed_objs: list[dict]) -> None`
    (mutiert `sessions`; Duplikat-Session wird übersprungen wie bisher)
  - `finalize_sessions(sessions: dict) -> dict` (Subagent-Linking +
    per-Session-Ableitungen; gibt `sessions` zurück)
  - außerdem verschoben: `_merge_model_buckets(dst, src)`, `_absorb_subagent(parent,
    sub, sub_type="", sub_desc="")`, `_link_subagents(sessions)`,
    `_day_from_ms(ms) -> str`, `split_session_by_day(daily_models, model_totals, ...)`

- [ ] **Step 1: Helferfunktionen verschieben** (Mechanik M)

Zu verschieben nach `claudestats_core/sessions.py`: `_merge_model_buckets`,
`_absorb_subagent`, `_link_subagents`, `_day_from_ms`, `split_session_by_day`
(Originalzeilen 1419-1574). settings-Ersetzungen: keine.
Re-Export-Zeile:

```python
from claudestats_core.sessions import (
    _merge_model_buckets, _absorb_subagent, _link_subagents,
    _day_from_ms, split_session_by_day,
)
```

Verify: pytest + golden check.
Commit: `refactor(core): move session merge/link/day-split helpers to claudestats_core.sessions`

- [ ] **Step 2: `SessionFileMeta` + `absorb_file` + `finalize_sessions` in `sessions.py` anlegen**

Kopf von `sessions.py` erweitern:

```python
from dataclasses import dataclass


@dataclass
class SessionFileMeta:
    """Datei-/Herkunfts-Metadaten eines Transcripts, vom Driver geliefert."""
    source_label: str
    file_session_id: str      # Datei-Stem (bei Subagents die agent-Datei)
    project_name: str         # Name des Projekt-Verzeichnisses
    file_size: int = 0
    is_subagent: bool = False
    parent_session_id: str = ""
    agent_id: str = ""
    agent_type: str = ""
    agent_description: str = ""
```

Dann `absorb_file`: Rumpf ist der VERBATIM übernommene Datei-Verarbeitungsteil
aus `parse_session_transcripts` - beginnend bei der Duplikat-Prüfung
(`if file_session_id in sessions:` ... "First seen wins"-Kommentarblock,
Original 2139-2149, `continue` wird `return`) gefolgt von der kompletten
Schleife `for obj in _merge_streamed_assistant_entries(_parsed_objs):`
(Original 2177-2604) mit `_parsed_objs` -> Parameter `parsed_objs`.
Die lokalen Namen, die der Rumpf nutzt, kommen aus einem Unpacking-Prolog,
damit KEIN Zeichen des Rumpfs angefasst werden muss:

```python
def absorb_file(sessions, meta, parsed_objs):
    """Faltet die geparsten JSONL-Objekte EINER Transcript-Datei in sessions.

    Herkunftsneutral: der CLI-Driver liefert parsed_objs aus Dateien, der
    Collector-Server aus dem DB-Export. Duplikate (session bereits aus
    anderer Quelle geparst) werden wie bisher uebersprungen - first seen wins.
    """
    source_label = meta.source_label
    file_session_id = meta.file_session_id
    project_name = meta.project_name
    file_size = meta.file_size
    is_subagent = meta.is_subagent
    parent_id = meta.parent_session_id
    sub_agent_id = meta.agent_id
    sub_agent_type = meta.agent_type
    sub_agent_desc = meta.agent_description

    # --- ab hier verbatim Original 2139-2149 (continue -> return) ---
    if file_session_id in sessions:
        _prev_src = sessions[file_session_id].get("source", settings.SOURCE_LABEL)
        if _prev_src != source_label:
            print(f"      NOTE: {file_session_id} already parsed from "
                  f"source '{_prev_src}'; skipping duplicate in "
                  f"'{source_label}'")
        return

    # --- ab hier verbatim Original 2172-2604 ---
    for obj in _merge_streamed_assistant_entries(parsed_objs):
        ...
```

Einzige settings-Ersetzung im übernommenen Code (genau 1 Stelle, oben schon
gezeigt): `SOURCE_LABEL` -> `settings.SOURCE_LABEL` in der Duplikat-Prüfung
(Original 2144). Einrückung des Schleifenrumpfs um die weggefallenen
Verschachtelungsebenen reduzieren (rein mechanisch, z.B. per Editor-Dedent -
keine inhaltliche Änderung).

`finalize_sessions` ist der VERBATIM übernommene Abschluss (Original 2609-2642:
`_link_subagents(sessions)` + die `for sess in sessions.values():`-Schleife mit
`_detect_cache_flushes`/`_compute_idle_gap_summary`/`summarize_context_window`):

```python
def finalize_sessions(sessions):
    """Subagent-Linking + per-Session-Ableitungen nach dem letzten absorb_file."""
    # --- verbatim Original 2609-2642 ---
    _link_subagents(sessions)
    for sess in sessions.values():
        ...
    return sessions
```

Benötigte Imports am Modulkopf von `sessions.py` (zusätzlich zu Step 1):

```python
from collections import defaultdict
from datetime import datetime, timezone

from . import settings
from .anomalies import (_compute_idle_gap_summary, _detect_cache_flushes,
                        summarize_context_window)
from .attribution import (WRITE_CATEGORIES, attribute_turn_tokens,
                          attribute_write_categories)
from .classify import (_classify_api_error, _classify_tool_error,
                       _classify_user_entry, _is_user_plan_limit_text,
                       _merge_streamed_assistant_entries, _route_tool_error)
from .pricing import calc_cost
```

- [ ] **Step 3: `parse_session_transcripts` in `extract_stats.py` zum Driver umbauen**

Die Funktion behält Signatur, Discovery, sudo-Handling und Konsolen-Ausgaben;
Zeilen-Verarbeitung geht an den Kern. Vollständiger neuer Körper (ersetzt
Original 2057-2648; die Quell-Listen-Konstruktion 2063-2079 und die
Verzeichnis-Schleifen 2081-2137 bleiben verbatim erhalten, hier mit
`<verbatim ...>` markiert wo unverändert):

```python
def parse_session_transcripts():
    """Parse all session JSONL transcripts from all sources."""
    sessions = {}
    total_files = 0
    total_lines = 0

    <verbatim: sources-Aufbau, Original 2062-2079>

    for source_label, projects_dir, sudo_user in sources:
        <verbatim: print + project_dirs-Listing + Schleifenkopf, Original 2080-2103>

            for jsonl_file in jsonl_files:
                total_files += 1
                file_session_id = jsonl_file.stem
                if sudo_user:
                    file_size = sudo_file_size(jsonl_file, sudo_user)
                else:
                    file_size = jsonl_file.stat().st_size

                meta = SessionFileMeta(
                    source_label=source_label,
                    file_session_id=file_session_id,
                    project_name=project_name,
                    file_size=file_size,
                )
                if "/subagents/" in str(jsonl_file):
                    meta.is_subagent = True
                    meta.parent_session_id = jsonl_file.parent.parent.name
                    if file_session_id.startswith("agent-"):
                        meta.agent_id = file_session_id[len("agent-"):]
                    meta_path = jsonl_file.with_suffix(".meta.json")
                    try:
                        if sudo_user:
                            _mc = sudo_read_text(meta_path, sudo_user)
                            if _mc:
                                _mj = json.loads(_mc)
                                meta.agent_type = _mj.get("agentType", "") or ""
                                meta.agent_description = _mj.get("description", "") or ""
                        elif meta_path.exists():
                            with open(meta_path, "r", encoding="utf-8", errors="replace") as _mf:
                                _mj = json.load(_mf)
                            meta.agent_type = _mj.get("agentType", "") or ""
                            meta.agent_description = _mj.get("description", "") or ""
                    except (OSError, json.JSONDecodeError):
                        pass

                try:
                    if sudo_user:
                        _content = sudo_read_text(jsonl_file, sudo_user)
                        if _content is None:
                            continue
                        _line_iter = _content.split("\n")
                    else:
                        _line_iter = open(jsonl_file, "r", encoding="utf-8", errors="replace").readlines()

                    _parsed_objs = []
                    for line in _line_iter:
                        total_lines += 1
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        _parsed_objs.append(obj)

                    absorb_file(sessions, meta, _parsed_objs)

                except Exception as e:
                    print(f"      ERROR reading {jsonl_file.name}: {e}")

    finalize_sessions(sessions)

    migration_count = sum(1 for s in sessions.values() if s.get("source") == MIGRATION_LABEL)
    current_count = sum(1 for s in sessions.values() if s.get("source") == SOURCE_LABEL)
    print(f"  Parsed {total_files} files, {total_lines} lines, {len(sessions)} sessions"
          f" (migration: {migration_count}, current: {current_count})")
    return sessions
```

Re-Export-Zeile ergänzen:

```python
from claudestats_core.sessions import SessionFileMeta, absorb_file, finalize_sessions
```

Bewusste, dokumentierte Mini-Abweichung (nur Konsolen-Statistik, nicht im
Golden-Master-Output): Duplikat-Dateien werden jetzt gelesen bevor `absorb_file`
sie verwirft; `total_lines` im Print kann dadurch höher ausfallen als vorher.
`dashboard_data.json` ist davon unberührt.

- [ ] **Step 4: Tests laufen lassen**

Run: `python3 -m pytest tests/ -q`
Expected: alle PASS (insbesondere `test_source_integration.py`,
`test_user_message_count.py`, `test_daily_split.py`,
`test_streamed_assistant_merge.py`)

- [ ] **Step 5: Golden-Master prüfen**

Run: `python3 tools/golden_master.py check`
Expected: `GOLDEN MASTER: OK (byte-identisch)`

- [ ] **Step 6: Commit**

```bash
git add claudestats_core/sessions.py extract_stats.py
git commit -m "refactor(core): split session state machine into absorb_file/finalize_sessions"
```

---

### Task 5: `plan_analysis.py` + `aggregate.py` verschieben (inkl. Test-Fixture-Umstellung)

**Files:**
- Create: `claudestats_core/plan_analysis.py`, `claudestats_core/aggregate.py`
- Modify: `extract_stats.py` (Definitionen raus, Re-Exports rein)
- Modify: `tests/fixture_utils.py:50-54`, `tests/test_plan_empty_history.py`
- Test: bestehende Suite (v.a. `test_plan_optimizer.py`, `test_plan_limits.py`,
  `test_billing_cycles.py`, `test_plan_empty_history.py`,
  `test_dashboard_data_integration.py`) + Golden-Master

**Interfaces:**
- Consumes: alles aus Tasks 2-4
- Produces:
  - `plan_analysis`: `_month_day_clamped(year, month, day)`,
    `_expand_billing_cycles(ph, start_str, end_str)`, `_recommend_tier(rec_cycles)`,
    `_tier_holds_in_cycle(cycle, tier)`, `_switch_arrow_for_cycle(cycle,
    recommended_tier)`, `build_plan_analysis(daily_cost_series, session_list,
    first_session=None, ...)` (liest `settings.PLAN_HISTORY` und
    `settings.PLAN_CAPACITY_OVERRIDE_PRO_USD`)
  - `aggregate`: `project_display_name(project_path) -> str`,
    `build_dashboard_data(sessions, stats_cache, dot_claude, history, plans=None,
    plugins=None, todos=None, file_history=None, storage=None, telemetry=None,
    tasks=None, memories=None) -> dict` - der Aggregations-Einstieg, den auch der
    Server-Driver (Plan 4) aufruft; die lokalen Extra-Quellen sind bereits
    optionale Parameter mit None-Default

**KRITISCH - Monkeypatch-Falle:** `tests/fixture_utils.py:54` und
`tests/test_plan_empty_history.py` patchen `es.PLAN_HISTORY`. Nach dem Move
liest `build_plan_analysis` aber `settings.PLAN_HISTORY` - der Patch auf
`extract_stats` griffe ins Leere und die Tests würden stillschweigend etwas
anderes testen (bzw. rot werden). Die Fixture-Umstellung ist deshalb Teil
DIESES Tasks, nicht optional.

- [ ] **Step 1: Move `plan_analysis.py`** (Mechanik M)

Zu verschieben: `_month_day_clamped`, `_expand_billing_cycles`,
`_recommend_tier`, `_tier_holds_in_cycle`, `_switch_arrow_for_cycle`,
`build_plan_analysis` (Original 2953-3433).
settings-Ersetzungen in `build_plan_analysis` (genau 7 Stellen, Original-Zeilen
3101, 3109, 3190, 3306, 3334 für `PLAN_HISTORY`; 3349 für
`PLAN_CAPACITY_OVERRIDE_PRO_USD`; der Kommentar 3104/3329 bleibt unverändert):
jedes Code-Vorkommen `PLAN_HISTORY` -> `settings.PLAN_HISTORY`,
`PLAN_CAPACITY_OVERRIDE_PRO_USD` -> `settings.PLAN_CAPACITY_OVERRIDE_PRO_USD`.
Kern-Imports:

```python
from . import settings
from .limits import (PLAN_TIER_FACTORS, PRO_CAPACITY_USD_DEFAULT,
                     _normalize_tier_name)
```

(Falls beim Move weitere Namen aus `limits`/`pricing` referenziert werden -
sichtbar als NameError beim Testlauf - in den Import aufnehmen; KEINE
Duplikat-Definitionen.)
Re-Export-Zeile:

```python
from claudestats_core.plan_analysis import (
    _month_day_clamped, _expand_billing_cycles, _recommend_tier,
    _tier_holds_in_cycle, _switch_arrow_for_cycle, build_plan_analysis,
)
```

Noch NICHT committen - erst Step 2 (Fixtures), sonst ist der Zwischenstand rot.

- [ ] **Step 2: Test-Fixtures auf settings umstellen**

`tests/fixture_utils.py`: nach `import extract_stats as es` ergänzen:

```python
import claudestats_core.settings as core_settings
```

und die Patch-Zeilen 50-54 erweitern - `es.`-Zuweisungen bleiben (Driver liest
sie weiter), die settings-Zuweisungen kommen dazu:

```python
    es.PROJECTS_DIR = Path(primary_dir)
    es.MIGRATION_ENABLED = False
    es.ADDITIONAL_SOURCES = additional or []
    es.SOURCE_LABEL = "current"
    core_settings.SOURCE_LABEL = "current"
    es.PLAN_HISTORY = [dict(STD_PLAN)] if plan_history is None else plan_history
    core_settings.PLAN_HISTORY = es.PLAN_HISTORY
```

`tests/test_plan_empty_history.py`: analog - `import claudestats_core.settings
as core_settings` ergänzen und im Test das Setzen/Zurücksetzen doppeln:

```python
    saved = core_settings.PLAN_HISTORY
    es.PLAN_HISTORY = []
    core_settings.PLAN_HISTORY = []
    try:
        ...bestehender Testkörper...
    finally:
        es.PLAN_HISTORY = saved
        core_settings.PLAN_HISTORY = saved
```

(Exakte bestehende try/finally-Struktur der Datei beibehalten - nur die
core_settings-Zeilen symmetrisch ergänzen.)

Run: `python3 -m pytest tests/ -q` -> alle PASS.
Run: `python3 tools/golden_master.py check` -> OK.
Commit: `refactor(core): move plan analysis to claudestats_core.plan_analysis; tests patch core settings`

- [ ] **Step 3: Move `aggregate.py`** (Mechanik M)

Zu verschieben: `project_display_name` (Original 814-824) und
`build_dashboard_data` (Original 3434-4063).
settings-Ersetzungen (genau 5 Stellen, Original-Zeilen):

- 3540: `CACHE_EFF_MIN_MESSAGES` -> `settings.CACHE_EFF_MIN_MESSAGES`
- 3588: `sess.get("source", SOURCE_LABEL)` -> `sess.get("source", settings.SOURCE_LABEL)`
- 3756: `LOCALE.get("weekdays", ...)` -> `settings.LOCALE.get("weekdays", ...)`
- 3983: `"locale": LOCALE,` -> `"locale": settings.LOCALE,`
- 3984: `"week_anchor": WEEK_ANCHOR,` -> `"week_anchor": settings.WEEK_ANCHOR,`
- 3986: `CONFIG.get("display_name")` -> `settings.DISPLAY_NAME`

(Das sind 6 Zeilen - die Zählung "5 Stellen" oben meint 5 verschiedene
Settings; alle 6 Zeilen ersetzen.)
Kern-Imports:

```python
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from . import settings
from .limits import (_compute_5h_windows, _compute_weekly_buckets,
                     _count_5h_hits, _dedupe_limit_events,
                     _detect_5h_fingerprint_events,
                     _estimate_5h_window_cap_usd, _iso_to_ms,
                     _match_limit_events_to_windows)
from .plan_analysis import build_plan_analysis
from .pricing import build_pricing_warnings, get_model_display
from .sessions import _day_from_ms, split_session_by_day
```

(Gleiches Vorgehen wie Step 1: fehlende Namen zeigen sich als NameError im
Testlauf und werden in die Imports aufgenommen, nie dupliziert.)
Re-Export-Zeile:

```python
from claudestats_core.aggregate import project_display_name, build_dashboard_data
```

Run: `python3 -m pytest tests/ -q` -> PASS.
Run: `python3 tools/golden_master.py check` -> OK.
Commit: `refactor(core): move build_dashboard_data aggregation to claudestats_core.aggregate`

---

### Task 6: Public API, Doku, End-Verifikation

**Files:**
- Modify: `claudestats_core/__init__.py` (Public API)
- Modify: `README.md` (neuer Abschnitt "Library-Nutzung / claudestats_core")
- Modify: `CHANGELOG.md` (Unreleased-Eintrag)
- Test: `tests/test_core_settings.py` erweitert um Public-API-Test

**Interfaces:**
- Produces: `claudestats_core` Top-Level-API - der Name-Vertrag für das
  Collector-Repo (Pläne 2-4): `settings`, `SessionFileMeta`, `absorb_file`,
  `finalize_sessions`, `build_dashboard_data`, `calc_cost`, `get_model_display`,
  `PRICING`, `build_pricing_warnings`

- [ ] **Step 1: Failing Test für die Public API**

An `tests/test_core_settings.py` anfügen:

```python
def test_public_api_surface():
    """Der Name-Vertrag, gegen den das Collector-Repo programmiert."""
    import claudestats_core as core
    for name in ("settings", "SessionFileMeta", "absorb_file",
                 "finalize_sessions", "build_dashboard_data", "calc_cost",
                 "get_model_display", "PRICING", "build_pricing_warnings"):
        assert hasattr(core, name), f"public API missing: {name}"
```

Run: `python3 -m pytest tests/test_core_settings.py::test_public_api_surface -v`
Expected: FAIL (`public API missing: SessionFileMeta`)

- [ ] **Step 2: `__init__.py` finalisieren**

```python
"""claudestats_core - kalibrierte Domaenenlogik von claude-stats.

Stdlib-rein. Zwei Driver konsumieren dieses Package:
- extract_stats.py (CLI): Datei-Discovery -> absorb_file/finalize_sessions
  -> build_dashboard_data -> statisches HTML
- Collector-Server (eigenes Repo): DB-Export -> dieselbe Kette -> Tenant-JSON
"""
from . import settings  # noqa: F401
from .aggregate import build_dashboard_data, project_display_name  # noqa: F401
from .pricing import (PRICING, build_pricing_warnings, calc_cost,  # noqa: F401
                      get_model_display)
from .sessions import (SessionFileMeta, absorb_file,  # noqa: F401
                       finalize_sessions)
```

Run: `python3 -m pytest tests/test_core_settings.py -v`
Expected: alle PASS

- [ ] **Step 3: README-Abschnitt**

In `README.md` nach dem bestehenden Architektur-/Usage-Teil einfügen (Wortlaut
darf an den README-Stil angepasst werden, Inhalt fix):

```markdown
## Library-Nutzung (`claudestats_core`)

Die kalibrierte Domänenlogik (Kosten, Cache-Anomalien, Limits, Attribution)
liegt als stdlib-reines Package `claudestats_core` vor. `extract_stats.py`
ist der CLI-Driver darüber; andere Consumer installieren das Package direkt:

    pip install "claudestats-core @ git+https://github.com/<owner>/claude-stats@<tag>"

Einstellungen (Woche-Anker, Plan-Historie, Locale) werden per
`claudestats_core.settings.configure(...)` gesetzt; ohne Aufruf gelten
lauffähige Defaults.
```

- [ ] **Step 4: CHANGELOG-Eintrag**

Unter der obersten (Unreleased-)Sektion von `CHANGELOG.md`:

```markdown
- refactor: Domänenlogik als stdlib-reines Package `claudestats_core`
  extrahiert (pricing, attribution, classify, anomalies, limits, sessions,
  plan_analysis, aggregate). `extract_stats.py` bleibt CLI-Driver und
  re-exportiert alle Namen; Verhalten byte-identisch (Golden-Master-verifiziert).
```

- [ ] **Step 5: End-Verifikation**

```bash
python3 -m pytest tests/ -q
python3 tools/golden_master.py check
python3 - <<'EOF'
import subprocess, sys, os, tempfile
from pathlib import Path
# Kern importierbar aus fremdem CWD ohne config.json
with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, PYTHONPATH=str(Path.cwd()))
    r = subprocess.run([sys.executable, "-c", "import claudestats_core"],
                       cwd=td, env=env)
    assert r.returncode == 0
print("Import-Check: OK")
EOF
grep -c "^def \|^class " extract_stats.py
```

Expected: pytest PASS, `GOLDEN MASTER: OK`, `Import-Check: OK`; der grep zeigt
die deutlich geschrumpfte Definitionszahl (Richtwert: ~55 vorher, ~20-25 nachher
- reine Plausibilität, kein hartes Kriterium).

Optionaler Packaging-Check (braucht Netz für setuptools-Build-Deps; bei
Offline-Fehlschlag NICHT blockierend, dann in Plan 2 beim ersten echten
Consumer verifizieren):

```bash
python3 -m venv /tmp/claude-1000/-home-andie-projects-claude-stats/gm-venv \
  && /tmp/claude-1000/-home-andie-projects-claude-stats/gm-venv/bin/pip install -e . --quiet \
  && /tmp/claude-1000/-home-andie-projects-claude-stats/gm-venv/bin/python -c "import claudestats_core; print('editable install: OK')"
```

- [ ] **Step 6: Commit**

```bash
git add claudestats_core/__init__.py tests/test_core_settings.py README.md CHANGELOG.md
git commit -m "feat(core): finalize claudestats_core public API + docs"
```

---

## Self-Review-Protokoll (beim Planschreiben durchgeführt)

1. **Spec-Abdeckung:** Plan 1 deckt aus der v0-Spec die Vorbedingung "Kern gemäß
   §10-Analyse strukturiert" ab (Architektur-Empfehlung Abschnitte 1-5). Agent,
   Collector, Verifier, Compute-Driver sind bewusst Pläne 2-4 (Repo-Split,
   Entscheidung 4). Keine Lücke innerhalb des Plan-1-Scopes.
2. **Platzhalter-Scan:** Die `<verbatim Original X-Y>`-Marker sind keine
   Platzhalter, sondern präzise Move-Anweisungen auf im Repo vorhandenen Code
   mit exakten Zeilengrenzen; alle NEUEN Artefakte (Harness, settings,
   pyproject, Meta/absorb/finalize-Gerüst, Driver-Körper, Fixture-Änderungen,
   Tests) stehen vollständig im Plan.
3. **Typ-/Namens-Konsistenz:** `SessionFileMeta`-Feldnamen in Task 4 Step 2 und
   Step 3 identisch; `absorb_file(sessions, meta, parsed_objs)` und
   `finalize_sessions(sessions)` konsistent zwischen Task 4 und Task 6-API;
   settings-Namen zwischen Task 2 (`_KNOWN`) und allen Ersetzungsstellen in
   Tasks 3-5 abgeglichen (7 Namen, 11 Ersetzungszeilen: 1 limits, 1 sessions,
   6+... plan_analysis 6 Zeilen, aggregate 6 Zeilen).
