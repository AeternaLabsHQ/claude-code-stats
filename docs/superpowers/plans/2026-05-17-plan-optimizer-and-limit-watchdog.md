# Plan-Optimizer & Limit-Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vier zusammenhängende Änderungen am claude-code-stats Dashboard, strikt in Reihenfolge 1 → 2 → 3 → 4: (1) Gap-basierte Cache-Flush-Detection ersetzt die heutige rate-basierte Heuristik; (2) Idle-Gap-Korrelations-Analyse zeigt Mehrverbrauch durch Pausen; (3) Limit-Events aus expliziten rate-limit-Errors + 5h-Fingerprint-Heuristik in neuem "Limits"-Tab; (4) Plan-Recommendation mit empirisch+default+config-override-Kalibrierung.

**Architecture:** Backend-Berechnungen in Python (`extract_stats.py`); pre-computed Felder in `dashboard_data.json` und per-Session-JSON; Frontend rein für Rendering (vanilla JS). Keine neuen Komponenten-Files - alle neuen UI-Teile inline in bestehenden Render-Funktionen. Existierende Build-Pipeline (Template-Concat in `extract_stats.py`) reicht.

**Tech Stack:** Python 3 (`statistics`, `datetime`, `zoneinfo`), pytest für Heuristik-Unit-Tests, vanilla JS für UI, CSS-Variablen aus dem Variant-C-Theme (`--vc-bg`, `--vc-border`, `--vc-text`, `--vc-accent`, `--vc-accent-red`).

**Spec:** `docs/superpowers/specs/2026-05-17-plan-optimizer-and-limit-watchdog-design.md`

**Testing convention:** Python-Heuristiken bekommen pytest-Unit-Tests in `tests/test_plan_optimizer.py`. UI nur Smoke-Tested per headless Chromium (siehe `reference_local_ui_smoketest.md`). Pro Task: Tests grün → `node --check` für JS → `python3 extract_stats.py` Smoke → manueller Browser-Spot-Check auf Dev-Server → eigener Commit → Deploy → Live-Cron-Validierung → nächste Task.

---

## File Structure

**Modified:**
- `extract_stats.py` — neue Konstanten am Top (`PLAN_TIER_FACTORS`, `PRO_CAPACITY_USD_DEFAULT`, `LIMIT_5H_*`), neue Helper (`_detect_cache_flushes`, `_compute_idle_gap_summary`, `_normalize_tier_name`, `_estimate_tier_capacity_usd`, `_summarize_recommendation`, `_detect_5h_fingerprint_events`), Erweiterung `_categorize_error`, erweiterte Session-Datenstruktur, neue JSON-Felder unter `plan_analysis`, `idle_gap_aggregate`, `plan_recommendation`, `limit_events_all`.
- `templates/dashboard.html` — neuer `<div class="tab-content" id="tab-limits">`-Container, neue Aggregat-Karte im Costs-Tab.
- `templates/dashboard.js` — `renderLimits()` Funktion, Tab-Renderer-Registrierung, `renderIdleGapAggregateCard()`.
- `templates/dashboard.css` — Styling für Limits-Tab (Timeline-Bars, Recommendation-Tabelle, Disclaimer-Box) + Aggregat-Karte.
- `templates/session_detail.js` — `renderIdleGapPanel()` Sektion zwischen "Tools" und "Errors".
- `templates/session_detail.css` — Styling für Idle-Gap-Panel (Bars, Text).
- `locales/de.json`, `locales/en.json` — neue Strings unter `idleGap`, `limits`, `planRec`.
- `config.example.json` — neues optionales `plan_capacity_override_pro_usd: null`.
- `docs/DOCUMENTATION_de.md` — vier neue Sektionen mit Erklärungen + Heuristik-Begründungen + Konstanten-Quellen.

**Created:**
- `tests/test_plan_optimizer.py` — pytest-Unit-Tests für alle Heuristiken.
- `docs/TODO_v2.md` — Sammelbecken für Out-of-Scope-Ideen während der Umsetzung.
- `docs/CHANGELOG.md` (oder Erweiterung wenn schon vorhanden) — Eintrag für die vier Änderungen.

**Not changed:** keine Refactorings außerhalb des Spec-Scopes; keine Änderungen an `templates/components/`, `templates/project_detail.*`, `update_dashboard.sh`, `public/`.

---

## Pre-flight

- [ ] **Step 0.1: Working branch erstellen**

```bash
git status --short
git checkout -b feature/plan-optimizer-and-limit-watchdog
git status --short
```

Expected: erst sauberer Tree (außer existierende untracked-Files wie `Bildschirmfoto*`, `debug.log` — die bleiben unangetastet), dann neuer Branch aktiv.

- [ ] **Step 0.2: Baseline-Build verifizieren**

```bash
python3 extract_stats.py >/tmp/ext_baseline.log 2>&1 && echo OK
```

Expected: `OK`. Wenn nicht: existierende Breakage stoppen und melden, **nicht** mit Plan starten.

- [ ] **Step 0.3: Pytest-Setup prüfen**

```bash
ls tests/
python3 -m pytest tests/ --collect-only -q 2>&1 | tail -5
```

Expected: bestehende Tests werden gefunden (`test_*.py` Dateien existieren). Wenn pytest nicht installiert: `pip install pytest` oder Hinweis ans User-Setup.

- [ ] **Step 0.4: TODO_v2.md anlegen**

```bash
cat > docs/TODO_v2.md <<'EOF'
# v2 TODO-Sammelbecken

Ideen, die während der Umsetzung des Plan-Optimizer-Features außerhalb
des v1.x-Scopes aufkamen. Vor v2-Release durchgehen und entscheiden,
was implementiert wird.

## Limit-Detection

- Weekly-Pause-Heuristik (mehrtägige Pausen nach hohem Verbrauch,
  Wiederaufnahme am vermuteten Weekly-Reset-Tag).
- Anthropic-Web-UI-Limits Drift-Detection (verworfen für v1, evtl.
  reaktivieren wenn UI-%-Daten verfügbar werden).

## Plan-Recommendation

- API pay-per-use als vierte Vergleichs-Tier in der Recommendation.
- Predictive: "wann läufst du wahrscheinlich ins Limit".

## Allgemein

(Während der Implementierung hier ergänzen.)
EOF
git add docs/TODO_v2.md
```

- [ ] **Step 0.5: Pre-flight-Commit**

```bash
git commit -m "chore: scaffold v1.x plan-optimizer feature branch (TODO_v2 sink)"
```

---

## Task 1: Gap-basierte Cache-Flush-Detection

**Files:**
- Modify: `extract_stats.py` (Session-Ingest-Loop, neue Funktion `_detect_cache_flushes`)
- Create: `tests/test_plan_optimizer.py`
- Modify: `docs/DOCUMENTATION_de.md`

### Task 1.1: Per-Turn Daten capturen

- [ ] **Step 1.1.1: Sess-Init erweitern**

In `extract_stats.py` rund um Zeile 1040–1080 (Session-Init-Dict), neues Private-Field hinzufügen direkt nach `"cache_flush_count": 0,`:

```python
"_assistant_turns": [],  # private: (ts_ms, cache_creation, cache_read) per turn — dropped before serialization
```

- [ ] **Step 1.1.2: Assistant-Turn-Capture im Loop**

In `extract_stats.py` ab Zeile 1178 (`if usage and usage.get("output_tokens", 0) > 0:` im `elif msg_type == "assistant":` Block) folgenden Block VOR der bestehenden Cache-Flush-Berechnung (Zeile 1192–1199) einfügen:

```python
                                    # Per-turn capture for gap-based cache-flush + idle-gap analysis (Tasks 1+2).
                                    turn_ts_ms = None
                                    if timestamp:
                                        if isinstance(timestamp, str):
                                            try:
                                                _dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                                turn_ts_ms = int(_dt.timestamp() * 1000)
                                            except (ValueError, OSError):
                                                pass
                                        elif isinstance(timestamp, (int, float)):
                                            turn_ts_ms = int(timestamp)
                                    if turn_ts_ms is not None:
                                        sess["_assistant_turns"].append({
                                            "ts": turn_ts_ms,
                                            "cache_creation": usage.get("cache_creation_input_tokens", 0),
                                            "cache_read": usage.get("cache_read_input_tokens", 0),
                                        })
```

- [ ] **Step 1.1.3: Smoke baseline run**

```bash
python3 extract_stats.py >/tmp/ext_step1_1.log 2>&1 && echo OK
```

Expected: `OK`, keine neuen Errors im Log. (Wir haben noch keine Verwendung des neuen Feldes, aber die Datenstruktur soll sauber laufen.)

### Task 1.2: `_detect_cache_flushes()` mit TDD

- [ ] **Step 1.2.1: Test-File anlegen mit failing test**

`tests/test_plan_optimizer.py`:

```python
"""Unit tests for plan-optimizer heuristics (Tasks 1-4)."""
import sys
from pathlib import Path

# Allow importing extract_stats from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _detect_cache_flushes


# ── Task 1: cache-flush detection ──────────────────────────────────

def _turn(ts_min, cc=0, cr=0):
    """Build a turn dict; ts is given as minutes since session start."""
    return {"ts": int(ts_min * 60 * 1000), "cache_creation": cc, "cache_read": cr}


def test_cache_flush_trivial_session_returns_zero():
    # Fewer than 3 turns → no classification possible.
    turns = [_turn(0, cc=1000, cr=0), _turn(1, cc=200, cr=800)]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_buildup_only_session_returns_zero():
    # 6 turns, all in buildup (cache_creation >= cache_read each turn).
    # Without a buildup-over signal nothing should be flagged.
    turns = [_turn(i, cc=1000, cr=0) for i in range(6)]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_warm_session_no_gaps_returns_zero():
    # Buildup ends turn 2, then dense activity (1min gaps), no creation spikes.
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),   # buildup-over signal here
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=100, cr=2800),
        _turn(5, cc=100, cr=3000),
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_single_real_pause_returns_one():
    # Warm session, then 10min pause, then a turn with huge cache_creation
    # (5× the post-buildup median).
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),   # buildup ends
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(15, cc=2000, cr=500),  # 10min gap, big creation
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 1


def test_cache_flush_gap_below_threshold_ignored():
    # Same as previous but only 2min gap → below 5min TTL.
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(7, cc=2000, cr=500),   # 2min gap
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_creation_within_2x_median_ignored():
    # 10min gap but creation only 1.5× median → below significance threshold.
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(15, cc=180, cr=2500),  # 10min gap, 1.5× median 120
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 0


def test_cache_flush_1h_cache_uses_60min_threshold():
    # 30min gap with extended caching → NOT a flush (below 60min threshold).
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(35, cc=2000, cr=500),   # 30min gap — below 60min cache TTL
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=True) == 0


def test_cache_flush_multiple_real_pauses_counted():
    # Two pause events, both qualify.
    turns = [
        _turn(0, cc=1000, cr=0),
        _turn(1, cc=500, cr=500),
        _turn(2, cc=200, cr=2000),    # buildup ends
        _turn(3, cc=100, cr=2500),
        _turn(4, cc=120, cr=2700),
        _turn(5, cc=110, cr=2800),
        _turn(20, cc=2500, cr=1000),  # 15min gap, big creation → flush 1
        _turn(21, cc=100, cr=2800),
        _turn(22, cc=100, cr=2900),
        _turn(40, cc=3000, cr=1500),  # 18min gap → flush 2
    ]
    assert _detect_cache_flushes(turns, has_1h_cache=False) == 2
```

- [ ] **Step 1.2.2: Run tests, expect ImportError**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '_detect_cache_flushes'` (oder ähnlich). Funktion existiert noch nicht.

- [ ] **Step 1.2.3: Implementation hinzufügen**

In `extract_stats.py` direkt nach den Imports (Top) `statistics` importieren (falls noch nicht da):

```python
import statistics
```

Dann (nach den existierenden Helpers, vor `def parse_session_transcripts`, also direkt vor Zeile 920) folgende Funktion einfügen:

```python
def _detect_cache_flushes(turns: list[dict], has_1h_cache: bool) -> int:
    """Gap-based flush detection.

    A turn counts as a cache-flush only if all three conditions hold:
      1. Cache was previously established (post-buildup phase)
      2. Gap since previous turn exceeds the active cache TTL
      3. Turn's cache_creation > 2× rolling median of post-buildup
         cache_creation values (floor: 100 tokens)
    """
    if len(turns) < 3:
        return 0

    gap_threshold_ms = (3600 if has_1h_cache else 300) * 1000
    sorted_turns = sorted(turns, key=lambda t: t["ts"])

    flushes = 0
    buildup_over = False
    creation_history: list[int] = []  # post-buildup cache_creation values

    for i, t in enumerate(sorted_turns):
        prev = sorted_turns[i - 1] if i > 0 else None

        if (not buildup_over
                and t["cache_read"] > t["cache_creation"]
                and t["cache_read"] > 0):
            buildup_over = True
            continue

        if not buildup_over:
            continue

        if t["cache_creation"] > 0:
            creation_history.append(t["cache_creation"])

        if not prev:
            continue
        gap_ms = t["ts"] - prev["ts"]
        if gap_ms < gap_threshold_ms:
            continue

        if len(creation_history) < 3:
            continue
        median = statistics.median(creation_history[:-1])
        if t["cache_creation"] > 2 * max(median, 100):
            flushes += 1

    return flushes
```

- [ ] **Step 1.2.4: Run tests, expect PASS**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -20
```

Expected: alle 8 Tests passen.

### Task 1.3: Bestehende Cache-Flush-Berechnung ersetzen

- [ ] **Step 1.3.1: Alte rate-basierte Logik entfernen**

In `extract_stats.py`, Zeile 1192–1199 löschen (den Block `# Cache flush = turn whose cache-hit-rate is < 50%.` und die folgenden Zeilen bis inklusive `sess["cache_flush_count"] += 1`).

- [ ] **Step 1.3.2: Post-Session Gap-Detection hinzufügen**

In `extract_stats.py` müssen wir die finale `cache_flush_count` aus `_assistant_turns` berechnen, **nachdem** die Session-Iteration vollständig durch ist. Finde die Stelle (rund um Zeile 1300–1350) wo der Loop über eine Session-JSONL endet und vor der Aggregation der Session ins finale Output passiert. Konkret: such nach dem Punkt, wo `sess["_tool_id_map"]` weggeworfen wird, oder vor der nächsten outer-loop-Iteration.

Nach dem inneren Per-Line-Loop (also außerhalb des `for obj in ...`-Loops aber innerhalb des `for jsonl_file in ...`-Loops) folgenden Block einfügen:

```python
                    # Compute gap-based cache-flush count from per-turn data (Task 1).
                    turns = sess.get("_assistant_turns", [])
                    has_1h = any(
                        m.get("cache_1h_tokens", 0) > 0
                        for m in sess.get("models", {}).values()
                    )
                    sess["cache_flush_count"] = _detect_cache_flushes(turns, has_1h)
```

Wenn die genaue Stelle unklar ist, mit `grep -n "_tool_id_map" extract_stats.py` orientieren und unmittelbar danach platzieren.

- [ ] **Step 1.3.3: Privates Feld vor JSON-Serialisierung droppen**

Dort, wo die finale Session-JSON für `public/sessions/<id>.json` geschrieben wird, oder dort wo `_tool_id_map` schon gedroppt wird (analoge Pattern), `_assistant_turns` ebenfalls droppen:

```python
                    sess.pop("_assistant_turns", None)
                    sess.pop("_tool_id_map", None)  # already there, keep
```

Konkret: `grep -n "_tool_id_map" extract_stats.py | head -10` lokalisiert beide Drop-Stellen, dort `_assistant_turns` daneben.

- [ ] **Step 1.3.4: Vollbuild + Sanity-Check**

```bash
python3 extract_stats.py 2>&1 | tail -20
ls public/sessions/ | head -5
```

Expected: Build OK, sessions/ noch da. Pick eine zufällige Session-JSON und prüfe:

```bash
SESS=$(ls public/sessions/ | head -1)
python3 -c "import json; d = json.load(open('public/sessions/$SESS')); print('cache_flush_count:', d.get('cache_flush_count')); print('_assistant_turns in?', '_assistant_turns' in d)"
```

Expected: `cache_flush_count` ist eine Zahl (oft 0), `_assistant_turns in? False`.

### Task 1.4: Validierung gegen reale Sessions

- [ ] **Step 1.4.1: Validierungs-Script**

Lege folgendes Validierungs-Snippet als `tests/validate_cache_flushes.py` ab (nicht committen — nur lokales Werkzeug):

```python
"""Local validation tool: print cache-flush summaries for a sample of sessions."""
import json
import sys
from pathlib import Path

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "public" / "sessions"

def main():
    sessions = sorted(SESSIONS_DIR.glob("*.json"))
    sample_size = min(20, len(sessions))
    print(f"Found {len(sessions)} sessions, sampling {sample_size}.\n")
    for sf in sessions[-sample_size:]:
        d = json.loads(sf.read_text())
        msgs = d.get("message_count", 0)
        cfc = d.get("cache_flush_count", 0)
        dur = d.get("duration_minutes", 0)
        print(f"  {sf.stem[:8]}  msgs={msgs:4d}  dur={dur:5.1f}min  flushes={cfc}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 1.4.2: Validation laufen lassen**

```bash
python3 tests/validate_cache_flushes.py
```

Erwartetes Bild: triviale Sessions (msgs<5) → 0 Flushes; lange Sessions (msgs>50, dur>120min) → 0 bis wenige Flushes (nur echte Pausen).

Wenn lange Sessions plötzlich Dutzende Flushes haben: Threshold falsch — kehre zu Task 1.2 zurück, justiere Multiplikator oder Median-Floor, und re-validate.

- [ ] **Step 1.4.3: Validierungs-Script aufräumen**

```bash
rm tests/validate_cache_flushes.py
```

(Das Tool war lokal, nicht für Commit gedacht.)

### Task 1.5: DOCUMENTATION + Commit

- [ ] **Step 1.5.1: DOCUMENTATION_de.md erweitern**

In `docs/DOCUMENTATION_de.md` nach der Sektion über "Cache Efficiency" (oder, falls keine existiert, am sinnvollen thematischen Punkt) folgenden Block einfügen:

```markdown
## Cache-Flush-Detection (Gap-basiert)

Der `cache_flush_count` einer Session zählt Turns, bei denen alle drei
folgenden Bedingungen erfüllt sind:

1. **Post-Buildup-Phase:** Die Session hat bereits einen Turn gehabt,
   in dem `cache_read > cache_creation` war (der Punkt, an dem der
   Prompt-Cache vom Kostenposten zum Asset wird).
2. **Gap überschreitet TTL:** Der zeitliche Abstand zum vorigen
   Assistant-Turn liegt über der erwarteten Cache-Lebenszeit:
   5 Minuten Default, 60 Minuten wenn die Session extended caching
   (1h-TTL) nutzt.
3. **Signifikante Creation-Spitze:** Die `cache_creation`-Tokens dieses
   Turns liegen über dem 2-fachen des Rolling-Medians der post-buildup
   `cache_creation`-Werte (Floor: 100 Tokens, um Mini-Sessions vor
   false positives zu schützen).

**Begründung der Konstanten:**

| Konstante | Wert | Begründung |
|---|---|---|
| Gap-Threshold (5min cache) | 5 min | Anthropic-dokumentierte ephemere Cache-TTL |
| Gap-Threshold (1h cache) | 60 min | Wenn die Session 1h-extended-caching nutzte, ist die TTL höher; Auto-Detection vermeidet falsche Flush-Klassifizierung |
| Buildup-Ende-Signal | `cache_read > cache_creation AND cache_read > 0` | Erster Turn, in dem der Cache mehr beigetragen hat als er kostete |
| Signifikanz-Multiplikator | 2× | Konservativ; nur deutlich überdurchschnittliche Creation-Kosten gelten als Flush |
| Median-Floor | 100 Tokens | Division-by-zero und false positives in Mini-Sessions vermeiden |
| Minimum-Turns | 3 total + 3 post-buildup | Triviale Sub-Agent-Sessions liefern keine Klassifizierung |

**Migrationshinweis:** Bis v1.0 wurde `cache_flush_count` über eine
rate-basierte Heuristik (`cache_hit_rate < 50%`) berechnet, die am
Session-Anfang falsch positive Treffer lieferte. Ab dieser Version
wird die obige gap-basierte Logik verwendet — historische
Vergleichsdaten fallen entsprechend niedriger aus.
```

- [ ] **Step 1.5.2: Syntax/Lint-Check**

```bash
python3 -c "import extract_stats; print('import ok')"
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -5
python3 extract_stats.py >/tmp/ext_task1.log 2>&1 && echo OK
```

Expected: alle drei OK.

- [ ] **Step 1.5.3: UI-Smoke-Check (kein neuer UI-Code, aber Regression-Check)**

Starte temporären HTTP-Server und prüfe headless dass keine JS-Errors:

```bash
cd public && python3 -m http.server 8765 >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
# Headless Chromium aus playwright cache
PWC=$(find ~/.cache/ms-playwright -name 'chrome' -path '*chrome-linux*' 2>/dev/null | head -1)
if [ -n "$PWC" ]; then
  "$PWC" --headless --disable-gpu --dump-dom http://localhost:8765/ 2>&1 | grep -i "uncaught\|error" | head -5 || echo "no JS errors detected"
fi
kill $SERVER_PID
```

Expected: `no JS errors detected` (oder leerer Output für die grep).

- [ ] **Step 1.5.4: Commit**

```bash
git add extract_stats.py tests/test_plan_optimizer.py docs/DOCUMENTATION_de.md
git status
git commit -m "feat: gap-based cache-flush detection (Task 1)

Replaces rate-based heuristic (cache_hit_rate < 50%) that fired falsely
during session buildup. New detection requires three concurrent signals:
post-buildup phase reached, gap exceeds cache TTL, creation tokens
significantly above session median.

Constants and rationale documented in DOCUMENTATION_de.md."
```

- [ ] **Step 1.5.5: Deploy + Live-Validierung**

```bash
./update_dashboard.sh 2>&1 | tail -10
```

Warte eine Cron-Runde (10min) oder lass den Script-Output durchgehen. Dann manuell im Browser auf `claude-stats.hive.dammert.net` (oder lokalem Dev-Server) eine bekannt-lange Session öffnen und prüfen ob `Cache Flushes`-Stat-Card jetzt 0 (oder nahe 0) statt z.B. 8 anzeigt.

Wenn UI nicht passt: Bug einkreisen, fixen, **nicht** mit Task 2 starten.

---

## Task 2: Idle-Gap-Korrelation

**Files:**
- Modify: `extract_stats.py` (neuer Helper `_compute_idle_gap_summary`, Session-Output erweitern, dashboard_data-Aggregat)
- Modify: `tests/test_plan_optimizer.py` (neue Tests)
- Modify: `templates/session_detail.js`, `templates/session_detail.css`, `templates/dashboard.js`, `templates/dashboard.html`, `templates/dashboard.css`
- Modify: `locales/de.json`, `locales/en.json`
- Modify: `docs/DOCUMENTATION_de.md`

### Task 2.1: `_compute_idle_gap_summary()` mit TDD

- [ ] **Step 2.1.1: Failing tests anhängen**

An `tests/test_plan_optimizer.py` anhängen:

```python


# ── Task 2: idle-gap summary ───────────────────────────────────────

from extract_stats import _compute_idle_gap_summary


def test_idle_gap_empty_session_returns_none():
    assert _compute_idle_gap_summary([]) is None


def test_idle_gap_single_turn_returns_none():
    # No gap possible with 1 turn.
    assert _compute_idle_gap_summary([_turn(0, cc=100)]) is None


def test_idle_gap_all_short_gaps_summary():
    # 5 turns, all <5min gaps, all cc=100.
    turns = [_turn(i, cc=100) for i in range(5)]
    s = _compute_idle_gap_summary(turns)
    assert s["short"]["count"] == 4  # 4 gaps from 5 turns
    assert s["mid"]["count"] == 0
    assert s["long"]["count"] == 0
    assert s["estimated_overspend_tokens"] == 0


def test_idle_gap_mixed_buckets_classified_correctly():
    turns = [
        _turn(0,   cc=100),
        _turn(1,   cc=100),    # 1min → short
        _turn(2,   cc=100),    # 1min → short
        _turn(10,  cc=500),    # 8min → mid
        _turn(80,  cc=2000),   # 70min → long
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["short"]["count"] == 2
    assert s["mid"]["count"] == 1
    assert s["long"]["count"] == 1


def test_idle_gap_overspend_uses_short_bucket_median_as_baseline():
    # Short-bucket median cc=100, mid+long turns spiked to 500 and 2000.
    # Overspend = (500-100) + (2000-100) = 400 + 1900 = 2300.
    turns = [
        _turn(0,   cc=100),
        _turn(1,   cc=100),
        _turn(2,   cc=100),
        _turn(10,  cc=500),     # mid
        _turn(80,  cc=2000),    # long
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["baseline_per_turn_tokens"] == 100
    assert s["estimated_overspend_tokens"] == 2300


def test_idle_gap_overspend_falls_back_to_session_median_if_no_short_bucket():
    # No short-bucket turns; baseline = session-overall median.
    turns = [
        _turn(0,   cc=100),
        _turn(10,  cc=500),     # mid
        _turn(80,  cc=2000),    # long
    ]
    s = _compute_idle_gap_summary(turns)
    # median of [100, 500, 2000] = 500.
    assert s["baseline_per_turn_tokens"] == 500
    # overspend = max(0, 500-500) + max(0, 2000-500) = 0 + 1500.
    assert s["estimated_overspend_tokens"] == 1500


def test_idle_gap_overspend_pct_of_session_total():
    # total_cc = 100+100+100+500+2000 = 2800; overspend = 2300; pct = 82.
    turns = [
        _turn(0, cc=100),
        _turn(1, cc=100),
        _turn(2, cc=100),
        _turn(10, cc=500),
        _turn(80, cc=2000),
    ]
    s = _compute_idle_gap_summary(turns)
    assert s["estimated_overspend_pct_of_session"] == 82
```

- [ ] **Step 2.1.2: Tests laufen, ImportError erwartet**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '_compute_idle_gap_summary'`.

- [ ] **Step 2.1.3: Implementation**

In `extract_stats.py` direkt nach `_detect_cache_flushes` einfügen:

```python
def _compute_idle_gap_summary(turns: list[dict]) -> dict | None:
    """Classify per-turn gaps into short/mid/long buckets and estimate
    overspend from lost cache-warmth.

    Returns None for sessions with <2 turns (no gap possible).
    """
    if len(turns) < 2:
        return None

    sorted_turns = sorted(turns, key=lambda t: t["ts"])
    buckets = {
        "short": {"count": 0, "cache_creation_tokens": 0, "values": []},
        "mid":   {"count": 0, "cache_creation_tokens": 0, "values": []},
        "long":  {"count": 0, "cache_creation_tokens": 0, "values": []},
    }

    for i in range(1, len(sorted_turns)):
        gap_sec = (sorted_turns[i]["ts"] - sorted_turns[i - 1]["ts"]) / 1000
        cc = sorted_turns[i]["cache_creation"]
        if gap_sec < 300:
            bucket = "short"
        elif gap_sec < 3600:
            bucket = "mid"
        else:
            bucket = "long"
        buckets[bucket]["count"] += 1
        buckets[bucket]["cache_creation_tokens"] += cc
        buckets[bucket]["values"].append(cc)

    # Baseline: median of short bucket, fallback to session-overall median.
    if buckets["short"]["values"]:
        baseline = int(statistics.median(buckets["short"]["values"]))
    else:
        all_ccs = [t["cache_creation"] for t in sorted_turns if t["cache_creation"] > 0]
        baseline = int(statistics.median(all_ccs)) if all_ccs else 0

    # Overspend: sum of max(0, cc - baseline) over mid + long turns.
    overspend = 0
    for bucket_name in ("mid", "long"):
        for cc in buckets[bucket_name]["values"]:
            overspend += max(0, cc - baseline)

    total_cc = sum(t["cache_creation"] for t in sorted_turns)
    overspend_pct = round(100 * overspend / total_cc) if total_cc > 0 else 0

    # Strip internal 'values' before returning.
    for b in buckets.values():
        b.pop("values", None)

    return {
        "short": buckets["short"],
        "mid": buckets["mid"],
        "long": buckets["long"],
        "estimated_overspend_tokens": overspend,
        "estimated_overspend_pct_of_session": overspend_pct,
        "baseline_per_turn_tokens": baseline,
    }
```

- [ ] **Step 2.1.4: Tests grün**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -20
```

Expected: alle Tests passen.

### Task 2.2: `idle_gap_summary` per Session ausgeben

- [ ] **Step 2.2.1: Im Session-Postprocessing-Block einbauen**

Direkt nach dem `_detect_cache_flushes`-Aufruf (Step 1.3.2) folgenden Block einfügen:

```python
                    sess["idle_gap_summary"] = _compute_idle_gap_summary(turns)
```

- [ ] **Step 2.2.2: Sanity-Check JSON**

```bash
python3 extract_stats.py 2>&1 | tail -5
SESS=$(ls -t public/sessions/*.json | head -1 | xargs basename)
python3 -c "import json; d = json.load(open('public/sessions/$SESS')); print(json.dumps(d.get('idle_gap_summary'), indent=2))"
```

Expected: entweder `null` (Mini-Session) oder ein Dict mit den erwarteten Feldern.

### Task 2.3: Dashboard-Aggregat

- [ ] **Step 2.3.1: Aggregate-Computation im Dashboard-Bau**

Such die Stelle in `extract_stats.py` wo `dashboard_data` final assembliert wird (search via `grep -n "dashboard_data" extract_stats.py | tail -20`). Pro-Session-`idle_gap_summary` muss bereits assembled sein bevor das Dashboard-Aggregat berechnet wird.

Direkt vor dem `json.dump(dashboard_data, ...)` Aufruf folgende Aggregation einfügen:

```python
    # Idle-gap aggregate over all sessions (Task 2 dashboard).
    total_overspend = 0
    sessions_with_overspend = 0
    for s in session_list:
        igs = s.get("idle_gap_summary")
        if igs and igs.get("estimated_overspend_tokens", 0) > 0:
            total_overspend += igs["estimated_overspend_tokens"]
            sessions_with_overspend += 1

    # USD estimate: tokens × default cache_write_5m rate (Sonnet 4.6 baseline).
    # Conservative: cheapest non-Haiku rate to avoid over-stating costs.
    OVERSPEND_USD_PER_MILLION = 3.75  # Sonnet 4.x cache_write_5m
    dashboard_data["idle_gap_aggregate"] = {
        "total_overspend_tokens": total_overspend,
        "total_overspend_usd": round(total_overspend * OVERSPEND_USD_PER_MILLION / 1_000_000, 2),
        "session_count_with_overspend": sessions_with_overspend,
    }
```

Anmerkung: `session_list` und das `dashboard_data`-Dict sollten an der Stelle vorhanden sein. Wenn das Variable-Naming anders ist (z.B. `sessions_summary`), an die lokalen Namen anpassen.

- [ ] **Step 2.3.2: Verify**

```bash
python3 extract_stats.py 2>&1 | tail -5
python3 -c "import json; d = json.load(open('public/dashboard_data.json')); print(json.dumps(d.get('idle_gap_aggregate'), indent=2))"
```

Expected: Dict mit drei Feldern, sinnvolle Werte.

### Task 2.4: Session-Detail UI

- [ ] **Step 2.4.1: Render-Funktion in session_detail.js**

In `templates/session_detail.js` direkt vor der Stelle, wo die "Errors"-Sektion gerendert wird (suche via `grep -n "errors\|Errors" templates/session_detail.js`), folgenden Render-Code einfügen.

Zuerst die Funktion am oberen Rand des File (nach IIFE-Open, vor den ersten DOM-Calls):

```javascript
function renderIdleGapPanel(sess) {
  const igs = sess.idle_gap_summary;
  if (!igs) return '';
  if ((igs.mid?.count || 0) === 0 && (igs.long?.count || 0) === 0) return '';

  const L = (window.D && window.D.locale && window.D.locale.idleGap) || {};
  const T = {
    title:    L.title    || 'Idle Gaps',
    short:    L.short    || '<5 min',
    mid:      L.mid      || '5–60 min',
    long:     L.long     || '>1 h',
    turns:    L.turns    || 'turns',
    overspend: L.overspend || 'Mehrverbrauch durch Cache-Verlust wegen Pausen',
    pctOf:    L.pctOf    || 'dieser Session',
    tip:      L.tip      || 'Sessions nicht offen lassen bei längeren Pausen.',
  };

  const fmtNum = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n));

  const maxCount = Math.max(igs.short.count, igs.mid.count, igs.long.count, 1);
  const bar = (count) => {
    const w = Math.round((count / maxCount) * 24);
    return '█'.repeat(w) + '░'.repeat(24 - w);
  };

  const rows = [
    {label: T.short, b: igs.short},
    {label: T.mid,   b: igs.mid},
    {label: T.long,  b: igs.long},
  ].map(r =>
    '<div class="igp-row">' +
      '<span class="igp-lbl">' + r.label + '</span>' +
      '<span class="igp-bar">' + bar(r.b.count) + '</span>' +
      '<span class="igp-num">' + r.b.count + ' ' + T.turns + ' · ' + fmtNum(r.b.cache_creation_tokens) + ' tok</span>' +
    '</div>'
  ).join('');

  const oversp = igs.estimated_overspend_tokens || 0;
  const overspPct = igs.estimated_overspend_pct_of_session || 0;

  return (
    '<div class="card idle-gap-panel">' +
      '<h3>' + T.title + '</h3>' +
      '<div class="igp-rows">' + rows + '</div>' +
      (oversp > 0 ?
        '<div class="igp-summary">≈ ' + fmtNum(oversp) + ' tok ' + T.overspend +
        ' (≈ ' + overspPct + '% ' + T.pctOf + ')</div>' : '') +
      '<div class="igp-tip">ⓘ ' + T.tip + '</div>' +
    '</div>'
  );
}
```

Dann an der Render-Stelle (wo die Sections zusammengebaut werden) den Output einfügen. Such die Stelle wo "Tools" oder "Errors" gerendert wird:

```javascript
html += renderIdleGapPanel(sess);
```

- [ ] **Step 2.4.2: CSS für Idle-Gap-Panel**

An `templates/session_detail.css` anhängen:

```css
.idle-gap-panel { font-family: monospace; }
.idle-gap-panel h3 { margin-bottom: 8px; }
.igp-rows { display: flex; flex-direction: column; gap: 4px; }
.igp-row { display: grid; grid-template-columns: 90px 28ch 1fr; align-items: center; gap: 12px; font-size: 13px; }
.igp-lbl { color: var(--vc-text, #ddd); }
.igp-bar { color: var(--vc-accent, #a78bfa); letter-spacing: -1px; white-space: nowrap; }
.igp-num { color: var(--vc-text2, #999); }
.igp-summary { margin-top: 12px; font-size: 14px; color: var(--vc-text, #ddd); }
.igp-tip { margin-top: 8px; font-size: 12px; color: var(--vc-text2, #999); }
```

- [ ] **Step 2.4.3: node --check**

```bash
node --check templates/session_detail.js && echo OK
```

Expected: `OK`.

- [ ] **Step 2.4.4: Build + headless smoke**

```bash
python3 extract_stats.py >/tmp/ext_step24.log 2>&1 && echo OK
cd public && python3 -m http.server 8765 >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
SESS=$(ls sessions/*.html | head -1 | xargs basename .html)
PWC=$(find ~/.cache/ms-playwright -name 'chrome' -path '*chrome-linux*' 2>/dev/null | head -1)
if [ -n "$PWC" ]; then
  "$PWC" --headless --disable-gpu --dump-dom "http://localhost:8765/sessions/$SESS.html" 2>&1 | grep -i "idle-gap\|Idle Gaps" | head -3
fi
kill $SERVER_PID
cd ..
```

Expected: HTML enthält die idle-gap-Panel-Klassen (wenn die Session welche hat) oder nichts (wenn Session keine mid/long-Gaps hatte). Beide Fälle OK.

### Task 2.5: Dashboard-Aggregat-Karte

- [ ] **Step 2.5.1: HTML-Slot im Costs-Tab**

In `templates/dashboard.html` such die Costs-Tab-Sektion (`<div class="tab-content active" id="tab-costs">`). Nach den bestehenden KPI-Cards aber vor den Charts, folgenden Container einfügen:

```html
      <div id="idleGapAggregateCard" class="vc-card vc-idle-aggregate" style="display:none;">
        <!-- populated by renderIdleGapAggregateCard() -->
      </div>
```

- [ ] **Step 2.5.2: Render-Funktion in dashboard.js**

In `templates/dashboard.js` nach den bestehenden Render-Helpers (vor `renderPlan` z.B.) anhängen:

```javascript
function renderIdleGapAggregateCard() {
  const el = document.getElementById('idleGapAggregateCard');
  if (!el) return;
  const agg = (F.idle_gap_aggregate) || null;
  if (!agg || !agg.total_overspend_tokens) {
    el.style.display = 'none';
    return;
  }
  const L = (D.locale && D.locale.idleGap) || {};
  const T = {
    dashTitle: L.dashTitle || 'Idle-Gap-Mehrverbrauch (gesamte Range)',
    sessions:  L.sessions  || 'Sessions',
  };
  const fmtTokens = (n) => n >= 1_000_000 ? (n/1_000_000).toFixed(1) + 'M' : (n >= 1000 ? (n/1000).toFixed(0) + 'k' : String(n));
  el.innerHTML =
    '<span class="vc-k">' + T.dashTitle + '</span> ' +
    '<span class="vc-v">≈ ' + fmtTokens(agg.total_overspend_tokens) + ' Tokens · ≈ $' + (agg.total_overspend_usd || 0).toFixed(2) + ' · ' +
    (agg.session_count_with_overspend || 0) + ' ' + T.sessions + '</span>';
  el.style.display = '';
}
```

Im Costs-Tab-Renderer (`renderCosts()` oder analog) am Ende `renderIdleGapAggregateCard()` aufrufen. Falls die Date-Range-Filter-Logik die Session-Liste umkonfiguriert (`F.sessions` etc.) und neu rendert: dafür sorgen, dass `idle_gap_aggregate` aus der **gefilterten** Liste neu berechnet wird. Code:

```javascript
function recomputeIdleGapAggregate(filteredSessions) {
  let totalOversp = 0;
  let withOversp = 0;
  for (const s of filteredSessions) {
    const igs = s.idle_gap_summary;
    if (igs && igs.estimated_overspend_tokens > 0) {
      totalOversp += igs.estimated_overspend_tokens;
      withOversp += 1;
    }
  }
  F.idle_gap_aggregate = {
    total_overspend_tokens: totalOversp,
    total_overspend_usd: Math.round(totalOversp * 3.75 / 1_000_000 * 100) / 100,
    session_count_with_overspend: withOversp,
  };
}
```

Diese Funktion im date-range-handler nach der Filterung aufrufen, dann `renderIdleGapAggregateCard()` erneut aufrufen.

- [ ] **Step 2.5.3: CSS für Aggregat-Karte**

An `templates/dashboard.css` anhängen:

```css
.vc-idle-aggregate { padding: 8px 12px; margin-top: 12px; border: 1px solid var(--vc-border, #333); background: var(--vc-bg2, #1a1a1a); font-family: monospace; font-size: 13px; }
.vc-idle-aggregate .vc-k { color: var(--vc-text2, #999); }
.vc-idle-aggregate .vc-v { color: var(--vc-text, #ddd); }
```

### Task 2.6: Locales + DOCUMENTATION

- [ ] **Step 2.6.1: Locales**

In `locales/de.json` einen neuen Top-Level-Key `idleGap` anlegen (oder unter dem passenden bestehenden Container):

```json
"idleGap": {
  "title": "Idle Gaps",
  "short": "<5 min",
  "mid": "5–60 min",
  "long": ">1 h",
  "turns": "Turns",
  "overspend": "Mehrverbrauch durch Cache-Verlust wegen Pausen",
  "pctOf": "dieser Session",
  "tip": "Sessions nicht offen lassen bei längeren Pausen.",
  "dashTitle": "Idle-Gap-Mehrverbrauch (gesamte Range)",
  "sessions": "Sessions"
}
```

In `locales/en.json` analog mit Englisch:

```json
"idleGap": {
  "title": "Idle Gaps",
  "short": "<5 min",
  "mid": "5–60 min",
  "long": ">1 h",
  "turns": "turns",
  "overspend": "extra tokens spent on cache rebuild after pauses",
  "pctOf": "of this session",
  "tip": "Don't leave sessions open during longer breaks.",
  "dashTitle": "Idle-gap overhead (full range)",
  "sessions": "sessions"
}
```

- [ ] **Step 2.6.2: DOCUMENTATION**

An `docs/DOCUMENTATION_de.md` anhängen:

```markdown
## Idle-Gap-Korrelation

Pro Session wird jeder Turn nach seiner Pause zum vorigen Turn
klassifiziert in einen von drei Buckets:

- `short`: gap < 5 Minuten (normaler Coding-Flow)
- `mid`:   5 Minuten ≤ gap < 60 Minuten (Cache wahrscheinlich kalt)
- `long`:  gap ≥ 60 Minuten (Cache definitiv kalt)

Der Output (`idle_gap_summary` im Session-JSON) enthält pro Bucket
Turn-Count und summierte cache_creation-Tokens, dazu eine
Overspend-Schätzung:

- **Baseline:** Median der cache_creation-Werte aus dem `short`-Bucket
  (Fallback: Session-Median wenn `short` leer)
- **Overspend pro Turn (mid/long):** `max(0, cache_creation - baseline)`
- **Summe** = `estimated_overspend_tokens`
- **Prozentual:** Anteil an der gesamten cache_creation der Session

Das Dashboard-Aggregat (`idle_gap_aggregate`) summiert über alle
Sessions in der gewählten Date-Range und schätzt die USD-Kosten via
Sonnet-4.x cache_write_5m-Preis ($3.75 / 1M Tokens).
```

### Task 2.7: Tests + Smoke + Commit + Deploy

- [ ] **Step 2.7.1: Tests + Build**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -10
node --check templates/dashboard.js && node --check templates/session_detail.js && echo OK
python3 extract_stats.py >/tmp/ext_task2.log 2>&1 && echo OK
```

Expected: alles OK.

- [ ] **Step 2.7.2: Headless smoke**

```bash
cd public && python3 -m http.server 8765 >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
PWC=$(find ~/.cache/ms-playwright -name 'chrome' -path '*chrome-linux*' 2>/dev/null | head -1)
if [ -n "$PWC" ]; then
  "$PWC" --headless --disable-gpu --dump-dom http://localhost:8765/ 2>&1 | grep -i "idle-gap\|idleGap\|Idle" | head -5
fi
kill $SERVER_PID
cd ..
```

- [ ] **Step 2.7.3: Manueller Browser-Spot-Check**

User-Prompt: "Öffne im Browser den Dev-Server und prüfe:
1. Costs-Tab zeigt die neue 'Idle-Gap-Mehrverbrauch'-Karte (oder ist versteckt wenn Daten 0)
2. Mindestens eine längere Session-Detail-Seite zeigt die neue 'Idle Gaps'-Sektion mit ASCII-Bars"

Wenn UI nicht passt: fixen vor Commit.

- [ ] **Step 2.7.4: Commit**

```bash
git add extract_stats.py tests/test_plan_optimizer.py templates/session_detail.js templates/session_detail.css templates/dashboard.html templates/dashboard.js templates/dashboard.css locales/de.json locales/en.json docs/DOCUMENTATION_de.md
git status
git commit -m "feat: idle-gap correlation analysis (Task 2)

Per-session classification of turn gaps into <5min / 5min-1h / >1h
buckets, with overspend estimate based on baseline cache_creation
from short-bucket median. Dashboard aggregate sums across the
filtered date range and converts to USD via Sonnet cache_write_5m
rate.

UI: new 'Idle Gaps' section on session detail (hidden when no
mid/long gaps); new aggregate card on Costs tab."
```

- [ ] **Step 2.7.5: Deploy + Live-Validierung**

```bash
./update_dashboard.sh 2>&1 | tail -5
```

Im Browser prüfen: Costs-Tab-Card erscheint (oder bleibt versteckt), eine bekannt-mit-Pausen-Session zeigt die Idle-Gaps-Sektion mit sinnvollen Zahlen.

---

## Task 3: Limit-Events Detektion + Visualisierung

**Files:**
- Modify: `extract_stats.py` (`_categorize_error`, neuer Helper `_detect_5h_fingerprint_events`, Capture-Code, Aggregation)
- Modify: `tests/test_plan_optimizer.py`
- Modify: `templates/dashboard.html` (neuer Tab-Container)
- Modify: `templates/dashboard.js` (Tab-Registrierung, `renderLimits()`)
- Modify: `templates/dashboard.css`
- Modify: `locales/de.json`, `locales/en.json`
- Modify: `docs/DOCUMENTATION_de.md`

### Task 3.1: Rate-Limit-Kategorie + explizite Events

- [ ] **Step 3.1.1: Failing tests anhängen**

An `tests/test_plan_optimizer.py` anhängen:

```python


# ── Task 3: limit-event detection (explicit) ───────────────────────

from extract_stats import _categorize_error


def test_categorize_rate_limit_error_string():
    assert _categorize_error("rate_limit_error", "API") == "rate_limit"


def test_categorize_429_status():
    assert _categorize_error("HTTP 429 Too Many Requests", "API") == "rate_limit"


def test_categorize_over_capacity():
    assert _categorize_error("API is over capacity", "API") == "rate_limit"


def test_categorize_usage_limit_reached():
    assert _categorize_error("Usage limit reached. Reset at 17:00 UTC.", "API") == "rate_limit"


def test_categorize_non_rate_limit_falls_back():
    # Existing category 'permission_denied' still works.
    assert _categorize_error("Permission denied", "Bash") == "permission_denied"
```

- [ ] **Step 3.1.2: Tests laufen, FAIL erwartet**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v -k rate_limit 2>&1 | tail -15
```

Expected: die 4 rate-limit-Tests fallen mit `other` statt `rate_limit`.

- [ ] **Step 3.1.3: `_categorize_error` erweitern**

In `extract_stats.py` Zeile 890–917, am **Anfang** der Klassifikations-Kette (vor allen anderen if-Branches), neue Pattern einfügen:

```python
    if ("rate_limit_error" in msg_lower
            or "429" in msg_lower
            or "over capacity" in msg_lower
            or "overloaded" in msg_lower
            or "usage limit reached" in msg_lower
            or "limit reached" in msg_lower):
        return "rate_limit"
```

- [ ] **Step 3.1.4: Tests grün**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -10
```

Expected: alle Tests passen.

### Task 3.2: Explizite Limit-Event-Capture

- [ ] **Step 3.2.1: Sess-Init erweitern**

In `extract_stats.py` Session-Init-Dict (rund um Zeile 1075) folgenden Eintrag hinzufügen:

```python
"limit_event_candidates": [],  # populated during error-capture (Task 3)
```

- [ ] **Step 3.2.2: Capture-Code an `_categorize_error`-Aufruf hängen**

In `extract_stats.py` Zeile 1132–1146 (wo `is_error`-Blocks zur Session geschrieben werden), nach dem `sess["errors"].append({...})`-Block folgenden Block ergänzen:

```python
                                            if category == "rate_limit":
                                                sess["limit_event_candidates"].append({
                                                    "type": "explicit",
                                                    "subtype": "rate_limit_error",
                                                    "timestamp": timestamp or "",
                                                    "session_id": session_id,
                                                    "confidence": "high",
                                                })
```

Hinweis: `session_id` ist die Variable, die den aktuellen Session-Identifier hält. Falls in dieser Stelle die Variable anders heißt, an den lokalen Namen anpassen (`grep -n "session_id\|sessionId" extract_stats.py | head -10` zur Orientierung).

- [ ] **Step 3.2.3: Zusätzlich: assistant-message error-field prüfen**

Im `elif msg_type == "assistant":`-Block (Zeile 1170+), nach dem `usage = message.get("usage", {})` folgenden Block einfügen:

```python
                                # Check for top-level error field on assistant messages (rate-limit etc.)
                                err = message.get("error") or obj.get("error")
                                if isinstance(err, dict):
                                    err_msg = str(err.get("message", "")) + " " + str(err.get("type", ""))
                                    if _categorize_error(err_msg, "API") == "rate_limit":
                                        sess["limit_event_candidates"].append({
                                            "type": "explicit",
                                            "subtype": err.get("type", "rate_limit_error"),
                                            "timestamp": timestamp or "",
                                            "session_id": session_id,
                                            "confidence": "high",
                                        })
```

### Task 3.3: 5h-Fingerprint-Heuristik

- [ ] **Step 3.3.1: Failing tests**

An `tests/test_plan_optimizer.py` anhängen:

```python


# ── Task 3: 5h-fingerprint heuristic ───────────────────────────────

from extract_stats import _detect_5h_fingerprint_events
from datetime import datetime, timezone, timedelta


def _prompt(ts_iso, session_id="s1"):
    return {"timestamp": ts_iso, "session_id": session_id}


def test_5h_fingerprint_clean_5h_gap_with_active_prefix_detected():
    # Active morning (3 prompts ±2h before gap), then 5h gap, then resumption.
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt((base + timedelta(minutes=-90)).isoformat()),  # active prefix
        _prompt((base + timedelta(minutes=-30)).isoformat()),
        _prompt(base.isoformat()),                              # last before gap
        _prompt((base + timedelta(hours=5, minutes=2)).isoformat(), "s2"),  # resumption
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert len(events) == 1
    assert events[0]["confidence"] in ("high", "medium")
    assert events[0]["session_id"] == "s2"


def test_5h_fingerprint_isolated_gap_without_activity_rejected():
    # Only the 'before gap' prompt, no preceding activity within 2h.
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=5, minutes=2)).isoformat()),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert events == []


def test_5h_fingerprint_short_gap_ignored():
    # 4h gap is below the 4h45m minimum.
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt((base + timedelta(minutes=-30)).isoformat()),
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=4)).isoformat()),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert events == []


def test_5h_fingerprint_long_gap_ignored():
    # 6h gap is above 5h30m maximum.
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    prompts = [
        _prompt((base + timedelta(minutes=-30)).isoformat()),
        _prompt(base.isoformat()),
        _prompt((base + timedelta(hours=6)).isoformat()),
    ]
    events = _detect_5h_fingerprint_events(prompts)
    assert events == []
```

- [ ] **Step 3.3.2: Tests laufen, ImportError**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v -k 5h 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3.3.3: Konstanten + Implementation**

In `extract_stats.py` am Top (mit anderen Konstanten):

```python
# 5h-fingerprint heuristic for Anthropic plan-tier rate limits.
# These constants encode the heuristic used to detect "user hit a 5h
# session limit and waited for reset". Documented in DOCUMENTATION_de.md.
LIMIT_5H_GAP_MIN_SEC = 4 * 3600 + 45 * 60   # 4h45m
LIMIT_5H_GAP_MAX_SEC = 5 * 3600 + 30 * 60   # 5h30m
LIMIT_5H_RESET_TOLERANCE_SEC = 15 * 60      # ±15 min around the 5h anchor
LIMIT_5H_ACTIVE_WINDOW_SEC = 2 * 3600       # active-prefix lookback
LIMIT_5H_DAY_START_HOUR = 7                 # local time
LIMIT_5H_DAY_END_HOUR = 22                  # local time
```

Implementation einfügen nach `_compute_idle_gap_summary`:

```python
def _detect_5h_fingerprint_events(prompts: list[dict]) -> list[dict]:
    """Detect 5h-rate-limit fingerprints in a chronological list of user prompts.

    prompts: [{"timestamp": ISO8601 str, "session_id": str}, ...]
    Returns events sorted by timestamp.
    """
    if len(prompts) < 2:
        return []

    parsed: list[tuple[datetime, str]] = []
    for p in prompts:
        ts = p.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed.append((dt, p.get("session_id", "")))
        except (ValueError, TypeError):
            continue
    parsed.sort(key=lambda x: x[0])

    events = []
    for i in range(1, len(parsed)):
        t_a, _ = parsed[i - 1]
        t_b, sid_b = parsed[i]
        gap_sec = (t_b - t_a).total_seconds()
        if not (LIMIT_5H_GAP_MIN_SEC <= gap_sec <= LIMIT_5H_GAP_MAX_SEC):
            continue

        # Active-prefix check: ≥1 other prompt within [t_a - 2h, t_a).
        active_prefix = any(
            t_a - timedelta(seconds=LIMIT_5H_ACTIVE_WINDOW_SEC) <= parsed[j][0] < t_a
            for j in range(i - 1)
        )

        # Day-window check on both endpoints (local time).
        t_a_local = t_a.astimezone()
        t_b_local = t_b.astimezone()
        in_day = (LIMIT_5H_DAY_START_HOUR <= t_a_local.hour <= LIMIT_5H_DAY_END_HOUR
                  and LIMIT_5H_DAY_START_HOUR <= t_b_local.hour <= LIMIT_5H_DAY_END_HOUR)

        # Reset-alignment: t_b within ±15min of t_a + 5h.
        anchor = t_a + timedelta(hours=5)
        aligned = abs((t_b - anchor).total_seconds()) <= LIMIT_5H_RESET_TOLERANCE_SEC

        hits = sum([active_prefix, in_day, aligned])
        if hits < 2:  # 2 of 3 needed (counting active_prefix as gate)
            continue
        if not active_prefix:
            continue  # active_prefix is mandatory

        confidence = "high" if (in_day and aligned) else "medium"

        events.append({
            "type": "heuristic",
            "subtype": "5h_fingerprint",
            "timestamp": t_b.isoformat(),
            "gap_start": t_a.isoformat(),
            "gap_end": t_b.isoformat(),
            "session_id": sid_b,
            "confidence": confidence,
        })

    return events
```

- [ ] **Step 3.3.4: Tests grün**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -10
```

Expected: alle Tests passen.

### Task 3.4: Cycle-Zuordnung + Globaler Aggregat

- [ ] **Step 3.4.1: User-Prompts global sammeln**

In `extract_stats.py` parse_session_transcripts (oder dem Top-Level-Build, wo alle Sessions schon parsed sind), nach dem Sessions-Loop einen Block einfügen, der alle User-Prompts (timestamp + session_id) sammelt:

```python
    # Collect all user prompts globally for 5h-fingerprint heuristic.
    all_user_prompts = []
    for sid, sess in sessions.items():
        for ts_ms in sess.get("timestamps", []):
            # Note: timestamps are mixed user+assistant; we accept all here
            # since the heuristic is about activity gaps, not strict
            # user-only prompts.
            all_user_prompts.append({
                "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
                "session_id": sid,
            })
    fingerprint_events = _detect_5h_fingerprint_events(all_user_prompts)
```

Hinweis: Wenn ein präziseres Per-User-Prompt-Tracking existiert (such mit `grep -n "user_message_count\|first_prompt" extract_stats.py | head -10`), das nutzen statt der gemischten timestamps.

- [ ] **Step 3.4.2: Explizite Events aus allen Sessions sammeln**

Direkt nach dem Sessions-Loop:

```python
    all_explicit_events = []
    for sid, sess in sessions.items():
        for ev in sess.get("limit_event_candidates", []):
            all_explicit_events.append(ev)
```

- [ ] **Step 3.4.3: Merge + Top-Level-Output**

```python
    all_limit_events = all_explicit_events + fingerprint_events
    all_limit_events.sort(key=lambda e: e.get("timestamp", ""))
    dashboard_data["limit_events_all"] = all_limit_events
```

- [ ] **Step 3.4.4: Pro Cycle in plan_analysis anhängen**

In `build_plan_analysis()` rund um Zeile 1624 (wo `period_entry`-Dict gebaut wird), nach der Zeile mit `"cost_per_day": ...,` folgenden Block einfügen:

```python
            cycle_events = [
                e for e in all_limit_events
                if cycle_start <= (e.get("timestamp") or "")[:10] <= cycle_end
            ]
            period_entry["limit_events"] = cycle_events
            period_entry["limit_event_count"] = len(cycle_events)
```

Hierfür muss `build_plan_analysis()` Zugriff auf `all_limit_events` haben. Entweder als Parameter durchreichen (cleanste Lösung), oder als Modul-globale Variable setzen.

Bevorzugter Weg: Parameter ergänzen:

```python
def build_plan_analysis(daily_cost_series, session_list, first_session=None, all_limit_events=None):
    all_limit_events = all_limit_events or []
    ...
```

und an der Aufruf-Stelle (such `grep -n "build_plan_analysis(" extract_stats.py`) `all_limit_events=all_limit_events` mitgeben.

- [ ] **Step 3.4.5: Privates Feld droppen**

Sess-Output cleanup: `sess.pop("limit_event_candidates", None)` an der gleichen Stelle wo `_assistant_turns` gedroppt wird.

- [ ] **Step 3.4.6: Build + sanity**

```bash
python3 extract_stats.py 2>&1 | tail -5
python3 -c "import json; d = json.load(open('public/dashboard_data.json')); print('limit_events_all count:', len(d.get('limit_events_all', []))); print('first 2:', json.dumps(d.get('limit_events_all', [])[:2], indent=2))"
```

Expected: Count und Sample sichtbar (oder 0 wenn keine).

### Task 3.5: Limits-Tab UI — Container + Tab-Registrierung

- [ ] **Step 3.5.1: HTML-Container**

In `templates/dashboard.html` analog zu `<div class="tab-content" id="tab-plan">` einen neuen Container hinzufügen, direkt nach dem Plan-Tab-Block:

```html
  <div class="tab-content" id="tab-limits">
    <div class="vc-tab-h">
      <div class="vc-tab-h-title">Limits &amp; Empfehlung</div>
      <div class="vc-tab-h-rule"></div>
      <div class="vc-tab-h-meta" id="vcLimitsMeta"></div>
    </div>
    <div id="limitsEventTimeline" class="vc-limits-section">
      <!-- populated by renderLimits() -->
    </div>
    <div id="limitsPlanRec" class="vc-limits-section">
      <!-- populated by renderLimits() — Task 4 -->
    </div>
  </div>
```

- [ ] **Step 3.5.2: Tab-Registrierung**

Such in `templates/dashboard.js` die Stelle wo `TAB_NAMES` o.ä. definiert ist (`grep -n "TAB_NAMES\|tab-plan\|'plan'" templates/dashboard.js`). Limits-Tab hinzufügen, etwa:

```javascript
// In der TAB_NAMES-Definition (oder analog):
{ id: 'limits', label: 'Limits' }
```

Falls Tab-Renderer in einem Dispatcher-Pattern liegen, `renderLimits` dort registrieren.

### Task 3.6: Limits-Tab UI — Event-Timeline rendern

- [ ] **Step 3.6.1: `renderLimits()` Funktion**

In `templates/dashboard.js` einfügen (nach `renderPlan()`):

```javascript
// ── Tab: Limits (Tasks 3+4) ──────────────────────────────────────
function renderLimits() {
  renderLimitsEventTimeline();
  renderPlanRecommendation();  // Task 4 will fill this in
}

function renderLimitsEventTimeline() {
  const el = document.getElementById('limitsEventTimeline');
  if (!el) return;
  const cycles = (F.plan_analysis && F.plan_analysis.periods) || [];
  const allEvents = F.limit_events_all || [];
  if (!cycles.length) {
    el.innerHTML = '<p class="vc-empty">Keine Plan-Cycles vorhanden.</p>';
    return;
  }

  const L = (D.locale && D.locale.limits) || {};
  const T = {
    title: L.eventsTitle || 'Limit Events',
    events: L.events || 'events',
    explicit: L.explicit || 'Explicit rate-limit error',
    heuristic: L.heuristic || '5h-Fingerprint (Heuristik)',
    click: L.click || 'Klick auf Event → Session öffnen (wenn verfügbar)',
  };

  // Group events by cycle (cycle_start string lookup).
  const eventsByPeriod = new Map();
  cycles.forEach((c, idx) => eventsByPeriod.set(idx, c.limit_events || []));

  const rows = cycles.map((cy, idx) => {
    const events = eventsByPeriod.get(idx) || [];
    const cyStart = new Date(cy.start);
    const cyEnd = new Date(cy.end);
    const cyDurMs = Math.max(1, cyEnd - cyStart);
    const markers = events.map(ev => {
      const ts = new Date(ev.timestamp || ev.gap_end || cy.start);
      const pct = Math.max(0, Math.min(100, 100 * (ts - cyStart) / cyDurMs));
      const cls = ev.type === 'explicit'
        ? 'evt evt-explicit'
        : (ev.confidence === 'high' ? 'evt evt-heuristic-high' : 'evt evt-heuristic-med');
      const tooltip = (ev.type === 'explicit' ? T.explicit : T.heuristic) +
                      ' · ' + (ev.subtype || '') +
                      ' · ' + (ev.timestamp || ev.gap_end || '');
      const href = ev.session_id ? ('sessions/' + ev.session_id + '.html') : '#';
      return '<a class="' + cls + '" style="left:' + pct.toFixed(1) + '%" title="' +
             tooltip.replace(/"/g, '&quot;') + '" href="' + href + '"></a>';
    }).join('');
    return (
      '<div class="lim-row">' +
        '<div class="lim-lbl">' + (cy.plan || '') + ' · ' + cy.start.slice(0, 7) + '</div>' +
        '<div class="lim-bar">' + markers + '</div>' +
        '<div class="lim-cnt">' + events.length + ' ' + T.events + '</div>' +
      '</div>'
    );
  }).join('');

  el.innerHTML =
    '<h3>' + T.title + '</h3>' +
    '<div class="lim-rows">' + rows + '</div>' +
    '<div class="lim-legend">' +
      '<span class="evt evt-explicit"></span> ' + T.explicit + ' &nbsp; ' +
      '<span class="evt evt-heuristic-high"></span> ' + T.heuristic +
    '</div>' +
    '<div class="lim-tip">' + T.click + '</div>';
}

function renderPlanRecommendation() {
  // Task 4 will implement this. Stub for now so renderLimits() doesn't crash.
  const el = document.getElementById('limitsPlanRec');
  if (!el) return;
  el.innerHTML = '';
}
```

Und im Tab-Renderer-Dispatcher `renderLimits()` registrieren. Konkret: such in dashboard.js wo `renderPlan()` aufgerufen wird (`grep -n "renderPlan()" templates/dashboard.js`) und `renderLimits()` an passender Stelle hinzufügen.

- [ ] **Step 3.6.2: CSS für Limits-Tab**

An `templates/dashboard.css` anhängen:

```css
.vc-limits-section { margin: 20px 0; }
.vc-limits-section h3 { margin-bottom: 12px; }
.lim-rows { display: flex; flex-direction: column; gap: 4px; }
.lim-row { display: grid; grid-template-columns: 180px 1fr 90px; align-items: center; gap: 12px; font-size: 13px; }
.lim-lbl { color: var(--vc-text2, #999); font-family: monospace; }
.lim-bar { position: relative; height: 16px; background: var(--vc-bg2, #1a1a1a); border-radius: 3px; }
.lim-cnt { color: var(--vc-text2, #999); text-align: right; font-family: monospace; }
.lim-bar .evt { position: absolute; top: 2px; width: 8px; height: 12px; border-radius: 2px; transform: translateX(-50%); cursor: pointer; }
.evt-explicit { background: var(--vc-accent-red, #ef4444); }
.evt-heuristic-high { background: var(--vc-accent, #a78bfa); }
.evt-heuristic-med { background: var(--vc-accent, #a78bfa); opacity: 0.55; }
.lim-legend { margin-top: 12px; font-size: 12px; color: var(--vc-text2, #999); }
.lim-legend .evt { position: relative; display: inline-block; width: 10px; height: 10px; vertical-align: middle; transform: none; margin-right: 4px; }
.lim-tip { margin-top: 6px; font-size: 12px; color: var(--vc-text2, #999); }
.vc-empty { color: var(--vc-text2, #999); font-style: italic; }
```

- [ ] **Step 3.6.3: Build + node check**

```bash
node --check templates/dashboard.js && echo OK
python3 extract_stats.py >/tmp/ext_step36.log 2>&1 && echo OK
```

### Task 3.7: Locales + DOCUMENTATION + Smoke + Commit + Deploy

- [ ] **Step 3.7.1: Locales**

`locales/de.json` neuer Block:

```json
"limits": {
  "tabLabel": "Limits",
  "eventsTitle": "Limit Events",
  "events": "Events",
  "explicit": "Expliziter Rate-Limit-Error",
  "heuristic": "5h-Fingerprint (Heuristik)",
  "click": "Klick auf Event → Session öffnen (wenn verfügbar)"
}
```

`locales/en.json`:

```json
"limits": {
  "tabLabel": "Limits",
  "eventsTitle": "Limit Events",
  "events": "events",
  "explicit": "Explicit rate-limit error",
  "heuristic": "5h-fingerprint (heuristic)",
  "click": "Click an event to open the session (when available)"
}
```

- [ ] **Step 3.7.2: DOCUMENTATION**

An `docs/DOCUMENTATION_de.md` anhängen:

```markdown
## Limit-Event-Detection

Zwei Detektionsquellen werden kombiniert.

### Quelle A: Explizite Errors

In den JSONL-Transcripts werden Tool-Result-Blöcke und assistant-message
`error`-Felder nach folgenden Patterns durchsucht:

- `rate_limit_error` (Anthropic-API-Error-Typ)
- `429` (HTTP-Status-Code)
- `over capacity`, `overloaded` (UI-Texte)
- `usage limit reached`, `limit reached` (Web-UI-Texte)

Treffer werden mit `confidence: "high"` und `type: "explicit"` als
Limit-Event gespeichert. Zusätzlich erhält der Error die Kategorie
`rate_limit` in der existierenden Error-Liste.

### Quelle B: 5h-Fingerprint-Heuristik

Auf der globalen Timeline aller Aktivitäts-Timestamps wird nach Lücken
gesucht, deren Form auf ein gerissenes 5h-Session-Limit hindeutet:

1. Gap-Dauer: `4h45m ≤ gap ≤ 5h30m`
2. **Aktivitäts-Prefix (Pflicht):** ≥1 weitere Aktivität innerhalb der
   2 Stunden vor dem Gap-Start.
3. **Tageszeit-Fenster:** Beide Endpunkte zwischen 07:00 und 22:00
   lokaler Zeit (vermeidet "5h = Nachtschlaf").
4. **Reset-Alignment:** Gap-Ende liegt innerhalb von ±15 Minuten um
   `Gap-Start + 5h` (Reset-Anchor).

Confidence:
- `high`: Alle vier Kriterien erfüllt.
- `medium`: Aktivitäts-Prefix + 1 von {Tageszeit-Fenster, Reset-Alignment}.
- darunter: verworfen.

Lokale Zeitzone via `astimezone()`-Default (System-TZ).

### Cycle-Zuordnung

Events werden im `plan_analysis.periods[].limit_events` pro
Billing-Cycle gruppiert. Eine globale Liste `limit_events_all` ist
zusätzlich im `dashboard_data.json` enthalten.
```

- [ ] **Step 3.7.3: Tests + smoke**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -10
node --check templates/dashboard.js && echo OK
python3 extract_stats.py >/tmp/ext_task3.log 2>&1 && echo OK

cd public && python3 -m http.server 8765 >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
PWC=$(find ~/.cache/ms-playwright -name 'chrome' -path '*chrome-linux*' 2>/dev/null | head -1)
if [ -n "$PWC" ]; then
  "$PWC" --headless --disable-gpu --dump-dom http://localhost:8765/ 2>&1 | grep -i "tab-limits\|Limit Events" | head -3
fi
kill $SERVER_PID
cd ..
```

- [ ] **Step 3.7.4: Manueller Browser-Spot-Check**

User-Prompt: "Klick auf den neuen Tab 'Limits'. Du solltest die Timeline-Sektion sehen, mit einer horizontalen Linie pro Plan-Cycle. Wenn du keine Limit-Events hast, sind die Linien leer — das ist OK."

- [ ] **Step 3.7.5: Commit**

```bash
git add extract_stats.py tests/test_plan_optimizer.py templates/dashboard.html templates/dashboard.js templates/dashboard.css locales/de.json locales/en.json docs/DOCUMENTATION_de.md
git status
git commit -m "feat: limit-event detection + new Limits tab (Task 3)

Two detection sources combined: explicit rate_limit_error / 429 /
'over capacity' patterns from JSONL error blocks (confidence: high),
plus a 5h-fingerprint heuristic on global activity timeline
(active-prefix + day-window + reset-alignment, confidence: high/medium).

New top-level Limits tab renders per-cycle event timeline. Plan
Recommendation section is stubbed and filled in Task 4."
```

- [ ] **Step 3.7.6: Deploy + Live-Validierung**

```bash
./update_dashboard.sh 2>&1 | tail -5
```

Browser: neuer Limits-Tab klickbar, Timeline erscheint. Falls Limit-Events vorhanden: Marker sichtbar, Tooltip funktioniert, Klick auf Marker mit `session_id` öffnet Session.

---

## Task 4: Plan-Recommendation

**Files:**
- Modify: `extract_stats.py` (Konstanten, `_normalize_tier_name`, `_estimate_tier_capacity_usd`, `_summarize_recommendation`, wire-up in build_plan_analysis)
- Modify: `tests/test_plan_optimizer.py`
- Modify: `templates/dashboard.js` (`renderPlanRecommendation`)
- Modify: `templates/dashboard.css`
- Modify: `config.example.json`
- Modify: `locales/de.json`, `locales/en.json`
- Modify: `docs/DOCUMENTATION_de.md`

### Task 4.1: Konstanten + `_normalize_tier_name`

- [ ] **Step 4.1.1: Failing tests**

An `tests/test_plan_optimizer.py` anhängen:

```python


# ── Task 4: plan-recommendation ────────────────────────────────────

from extract_stats import (
    _normalize_tier_name,
    _estimate_tier_capacity_usd,
    _summarize_recommendation,
    PLAN_TIER_FACTORS,
)


def test_normalize_pro_variants():
    assert _normalize_tier_name("Pro") == "Pro"
    assert _normalize_tier_name("pro plan") == "Pro"
    assert _normalize_tier_name("Pro (annual)") == "Pro"


def test_normalize_max5x_variants():
    assert _normalize_tier_name("Max 5x") == "Max 5x"
    assert _normalize_tier_name("max5x") == "Max 5x"
    assert _normalize_tier_name("5x") == "Max 5x"


def test_normalize_max20x_variants():
    assert _normalize_tier_name("Max 20x") == "Max 20x"
    assert _normalize_tier_name("max20x") == "Max 20x"
    assert _normalize_tier_name("20x") == "Max 20x"


def test_normalize_unknown_returns_none():
    assert _normalize_tier_name("Enterprise") is None
    assert _normalize_tier_name("") is None
```

- [ ] **Step 4.1.2: FAIL erwartet**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v -k normalize 2>&1 | tail -10
```

- [ ] **Step 4.1.3: Konstanten + Helper**

In `extract_stats.py` am Top (nach den existierenden Konstanten):

```python
# Plan-recommendation constants (Task 4).
# Source: Anthropic pricing communication / docs page (Pro = 1×, Max 5x = 5×,
# Max 20x = 20×). Exact token limits are not published — these factors are
# rough relative-capacity estimates from Anthropic, not measurements.
PLAN_TIER_FACTORS = {"Pro": 1.0, "Max 5x": 5.0, "Max 20x": 20.0}

# Fallback Pro-tier capacity in USD-API-equivalent per billing cycle.
# Used only when no limit events are available for empirical calibration
# and no config override is set. Heavily disclaimed in the UI.
PRO_CAPACITY_USD_DEFAULT = 100.0


def _normalize_tier_name(raw: str) -> str | None:
    """Map user-config plan strings to PLAN_TIER_FACTORS keys."""
    if not raw:
        return None
    s = str(raw).lower().strip()
    # Strip annual suffix.
    s = s.replace("(annual)", "").strip()
    if s in ("pro", "pro plan"):
        return "Pro"
    s_compact = s.replace(" ", "")
    if s_compact in ("max5x", "5x", "max-5x"):
        return "Max 5x"
    if s_compact in ("max20x", "20x", "max-20x"):
        return "Max 20x"
    return None
```

- [ ] **Step 4.1.4: Tests grün**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v -k normalize 2>&1 | tail -10
```

### Task 4.2: `_estimate_tier_capacity_usd`

- [ ] **Step 4.2.1: Failing tests**

```python


def test_estimate_capacity_override_takes_precedence():
    r = _estimate_tier_capacity_usd("Max 5x", {}, {}, override_pro=200.0)
    assert r["source"] == "config_override"
    assert r["base_pro_usd"] == 200.0
    assert r["capacities"]["Pro"] == 200.0
    assert r["capacities"]["Max 5x"] == 1000.0
    assert r["capacities"]["Max 20x"] == 4000.0


def test_estimate_capacity_empirical_from_limit_events():
    # User on Max 5x, 3 cycles with limit events: api_cost 480, 510, 540.
    # Median = 510 → Pro capacity = 510 / 5 = 102.
    events_by_cycle = {"c1": [{"x": 1}], "c2": [{"x": 1}], "c3": [{"x": 1}]}
    cost_by_cycle = {"c1": 480.0, "c2": 510.0, "c3": 540.0}
    r = _estimate_tier_capacity_usd("Max 5x", events_by_cycle, cost_by_cycle, None)
    assert r["source"] == "empirical"
    assert r["base_pro_usd"] == 102.0


def test_estimate_capacity_fallback_to_default_without_events():
    r = _estimate_tier_capacity_usd("Max 5x", {}, {}, None)
    assert r["source"] == "default"
    assert r["base_pro_usd"] == 100.0  # PRO_CAPACITY_USD_DEFAULT
```

- [ ] **Step 4.2.2: FAIL erwartet, dann Implementation**

In `extract_stats.py` nach `_normalize_tier_name`:

```python
def _estimate_tier_capacity_usd(
    current_tier: str,
    limit_events_by_cycle: dict[str, list],
    api_cost_by_cycle: dict[str, float],
    override_pro: float | None,
) -> dict:
    """Return per-tier capacity in USD-API-equivalent.

    Calibration priority:
      1. config override (plan_capacity_override_pro_usd) — user knows best
      2. empirical from limit-hit cycles on current tier
      3. hardcoded PRO_CAPACITY_USD_DEFAULT
    """
    if override_pro is not None and override_pro > 0:
        base = float(override_pro)
        source = "config_override"
    else:
        limit_hit_costs = [
            api_cost_by_cycle[cid]
            for cid, evts in limit_events_by_cycle.items()
            if evts and api_cost_by_cycle.get(cid, 0) > 0
        ]
        if limit_hit_costs:
            current_factor = PLAN_TIER_FACTORS.get(current_tier, 5.0)
            base = statistics.median(limit_hit_costs) / current_factor
            source = "empirical"
        else:
            base = PRO_CAPACITY_USD_DEFAULT
            source = "default"

    capacities = {t: round(base * f, 2) for t, f in PLAN_TIER_FACTORS.items()}
    return {"capacities": capacities, "base_pro_usd": round(base, 2), "source": source}
```

- [ ] **Step 4.2.3: Tests grün**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v -k estimate_capacity 2>&1 | tail -10
```

### Task 4.3: `_summarize_recommendation`

- [ ] **Step 4.3.1: Failing tests**

```python


def test_recommendation_recommends_cheapest_holding_tier():
    # Pro held in 1/3, Max5x in 3/3 → Max5x recommended (threshold 0.8).
    cycles = [
        {"tier_utilization": {"Pro": 50,  "Max 5x": 10, "Max 20x": 3}},  # Pro held
        {"tier_utilization": {"Pro": 150, "Max 5x": 30, "Max 20x": 8}},  # only Max5x+
        {"tier_utilization": {"Pro": 200, "Max 5x": 40, "Max 20x": 10}},
    ]
    r = _summarize_recommendation(cycles, current_tier="Max 5x")
    assert r["recommended_tier"] == "Max 5x"
    assert r["held_count"]["Pro"] == 1
    assert r["held_count"]["Max 5x"] == 3
    assert r["total_cycles"] == 3


def test_recommendation_recommends_pro_if_always_held():
    cycles = [
        {"tier_utilization": {"Pro": 50, "Max 5x": 10, "Max 20x": 3}},
        {"tier_utilization": {"Pro": 80, "Max 5x": 16, "Max 20x": 4}},
    ]
    r = _summarize_recommendation(cycles, current_tier="Max 5x")
    assert r["recommended_tier"] == "Pro"


def test_recommendation_none_if_nothing_holds():
    cycles = [
        {"tier_utilization": {"Pro": 150, "Max 5x": 150, "Max 20x": 150}},
    ]
    r = _summarize_recommendation(cycles, current_tier="Max 20x")
    assert r["recommended_tier"] is None
```

- [ ] **Step 4.3.2: Implementation**

In `extract_stats.py` nach `_estimate_tier_capacity_usd`:

```python
def _summarize_recommendation(
    cycles: list[dict],
    current_tier: str,
    threshold_pct: float = 0.8,
) -> dict:
    """Pick cheapest tier that holds (≤100%) in ≥ threshold_pct of cycles."""
    held = {tier: 0 for tier in PLAN_TIER_FACTORS}
    for c in cycles:
        for tier, pct in (c.get("tier_utilization") or {}).items():
            if pct <= 100:
                held[tier] += 1
    total = len(cycles)

    recommended = None
    for tier in ("Pro", "Max 5x", "Max 20x"):
        if total > 0 and held[tier] / total >= threshold_pct:
            recommended = tier
            break

    return {
        "current_tier": current_tier,
        "recommended_tier": recommended,
        "held_count": held,
        "total_cycles": total,
        "threshold_pct": threshold_pct,
    }
```

- [ ] **Step 4.3.3: Tests grün**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -10
```

Expected: alle Tests passen.

### Task 4.4: Integration in `build_plan_analysis`

- [ ] **Step 4.4.1: Config-Lookup**

In `extract_stats.py` rund um `PLAN_HISTORY = CONFIG.get("plan_history", [])` (Zeile 189) ergänzen:

```python
PLAN_CAPACITY_OVERRIDE_PRO_USD = CONFIG.get("plan_capacity_override_pro_usd")
```

- [ ] **Step 4.4.2: Per-Cycle Utilization in build_plan_analysis**

In `build_plan_analysis()`, am **Ende** der Funktion vor dem `return`, folgenden Block einfügen:

```python
    # ── Plan Recommendation (Task 4) ───────────────────────────────
    # Build cycle-id → limit-event list and cycle-id → api-cost mapping
    # from the periods list (cycle id = "start_end" string).
    limit_events_by_cycle = {}
    api_cost_by_cycle = {}
    for p in periods:
        cid = p["start"] + "_" + p["end"]
        limit_events_by_cycle[cid] = p.get("limit_events", [])
        api_cost_by_cycle[cid] = p.get("api_cost", 0)

    raw_current_tier = current_plan.get("plan", "")
    normalized_current = _normalize_tier_name(raw_current_tier) or "Max 5x"

    cap_info = _estimate_tier_capacity_usd(
        normalized_current,
        limit_events_by_cycle,
        api_cost_by_cycle,
        PLAN_CAPACITY_OVERRIDE_PRO_USD,
    )

    # Decorate each period with tier utilization.
    rec_cycles = []
    for p in periods:
        api = p.get("api_cost", 0)
        util = {
            tier: round(100 * api / cap)
            for tier, cap in cap_info["capacities"].items()
            if cap > 0
        }
        rec_cycles.append({
            "cycle_start": p["start"],
            "cycle_end": p["end"],
            "label": p["plan"] + " · " + p["start"][:7],
            "api_cost": api,
            "tier_utilization": util,
            "limit_event_count": p.get("limit_event_count", 0),
        })

    summary = _summarize_recommendation(rec_cycles, normalized_current)
    plan_recommendation = {
        **summary,
        "calibration": cap_info,
        "cycles": rec_cycles,
    }
```

Im finalen `return` der Funktion (oder im Dict, das `build_plan_analysis` zurückgibt) `plan_recommendation` mit-zurückgeben. Such die Return-Stelle (`grep -n "return" extract_stats.py | grep -i plan` oder Funktion durchscrollen) und das Dict erweitern, z.B.:

```python
    return {
        "periods": periods,
        "current_billing": current_billing,
        "total_savings": ...,
        ...
        "plan_recommendation": plan_recommendation,
    }
```

- [ ] **Step 4.4.3: Top-Level-Output**

Wo das Aufrufer-Code `build_plan_analysis` aufruft (such mit `grep -n "build_plan_analysis(" extract_stats.py`), das resultierende Dict in `dashboard_data` enthalten:

```python
    plan_analysis_result = build_plan_analysis(daily_cost_series, session_list, first_session, all_limit_events=all_limit_events)
    dashboard_data["plan_analysis"] = plan_analysis_result
    dashboard_data["plan_recommendation"] = plan_analysis_result.get("plan_recommendation")
```

(Wenn `plan_analysis` schon im dashboard ist, nur die `plan_recommendation`-Zeile zusätzlich einfügen.)

- [ ] **Step 4.4.4: Sanity**

```bash
python3 extract_stats.py 2>&1 | tail -5
python3 -c "import json; d = json.load(open('public/dashboard_data.json')); print(json.dumps(d.get('plan_recommendation'), indent=2)[:1500])"
```

Expected: Dict mit current_tier, recommended_tier, held_count, calibration, cycles.

### Task 4.5: Config-Beispiel + UI

- [ ] **Step 4.5.1: config.example.json**

In `config.example.json` neuen Top-Level-Key hinzufügen:

```json
"plan_capacity_override_pro_usd": null
```

(Komma-Platzierung beachten — bestehende JSON-Syntax wahren.)

- [ ] **Step 4.5.2: `renderPlanRecommendation` ausfüllen**

In `templates/dashboard.js` die Stub-Funktion `renderPlanRecommendation` (eingefügt in Step 3.6.1) ersetzen:

```javascript
function renderPlanRecommendation() {
  const el = document.getElementById('limitsPlanRec');
  if (!el) return;
  const pr = F.plan_recommendation || null;
  if (!pr || !pr.cycles || !pr.cycles.length) {
    el.innerHTML = '';
    return;
  }

  const L = (D.locale && D.locale.planRec) || {};
  const T = {
    title:        L.title || 'Plan-Empfehlung',
    cycle:        L.cycle || 'Cycle',
    current:      L.current || 'Aktueller Tier',
    rec:          L.rec || 'Empfehlung',
    held:         L.held || 'hielt in',
    of:           L.of || 'von',
    cycles:       L.cycles || 'Cycles',
    cal:          L.cal || 'Kalibrierung',
    calEmpirical: L.calEmpirical || 'empirisch',
    calDefault:   L.calDefault || 'Default-Fallback',
    calOverride:  L.calOverride || 'Override aus config',
    disclaimer:   L.disclaimer || 'Schätzung basierend auf Anthropic-Faktoren (1:5:20). Anthropic publiziert keine exakten Token-Limits. Tatsächliche Limits können abweichen.',
  };

  const fmtPct = (n) => n + '%';
  const mark = (n) => n <= 100 ? '✓' : '⚠';

  const headerRow = '<tr><th>' + T.cycle + '</th><th>Pro</th><th>Max 5x</th><th>Max 20x</th></tr>';
  const bodyRows = pr.cycles.map(c => {
    const u = c.tier_utilization || {};
    return '<tr>' +
      '<td class="cyc-lbl">' + (c.label || c.cycle_start) + '</td>' +
      '<td class="' + (u.Pro > 100 ? 'over' : 'under') + '">' + fmtPct(u.Pro || 0) + ' ' + mark(u.Pro || 0) + '</td>' +
      '<td class="' + ((u['Max 5x'] || 0) > 100 ? 'over' : 'under') + '">' + fmtPct(u['Max 5x'] || 0) + ' ' + mark(u['Max 5x'] || 0) + '</td>' +
      '<td class="' + ((u['Max 20x'] || 0) > 100 ? 'over' : 'under') + '">' + fmtPct(u['Max 20x'] || 0) + ' ' + mark(u['Max 20x'] || 0) + '</td>' +
    '</tr>';
  }).join('');

  const hc = pr.held_count || {};
  const tc = pr.total_cycles || 0;
  const recLine = pr.recommended_tier
    ? T.rec + ': ' + pr.recommended_tier + ' (' + T.held + ' ' + (hc[pr.recommended_tier] || 0) + '/' + tc + ' ' + T.cycles + ')'
    : T.rec + ': —';

  const cal = pr.calibration || {};
  const calSrc = cal.source === 'empirical' ? T.calEmpirical
    : cal.source === 'config_override' ? T.calOverride
    : T.calDefault;
  const calLine = T.cal + ': ' + calSrc + ' (Pro=$' + (cal.base_pro_usd || 0) + '/Cycle)';

  el.innerHTML =
    '<h3>' + T.title + '</h3>' +
    '<table class="plan-rec-table"><thead>' + headerRow + '</thead><tbody>' + bodyRows + '</tbody></table>' +
    '<div class="plan-rec-summary">' +
      '<div>' + T.current + ': ' + (pr.current_tier || '—') + '</div>' +
      '<div>' + recLine + '</div>' +
      '<div class="plan-rec-cal">' + calLine + '</div>' +
    '</div>' +
    '<div class="plan-rec-disclaimer">⚠ ' + T.disclaimer + '</div>';
}
```

- [ ] **Step 4.5.3: CSS**

An `templates/dashboard.css` anhängen:

```css
.plan-rec-table { border-collapse: collapse; width: 100%; margin-top: 8px; font-family: monospace; font-size: 13px; }
.plan-rec-table th, .plan-rec-table td { border-bottom: 1px solid var(--vc-border, #333); padding: 4px 8px; text-align: right; }
.plan-rec-table th:first-child, .plan-rec-table td.cyc-lbl { text-align: left; color: var(--vc-text2, #999); }
.plan-rec-table td.over { color: var(--vc-accent-red, #ef4444); }
.plan-rec-table td.under { color: var(--vc-text, #ddd); }
.plan-rec-summary { margin-top: 16px; font-size: 14px; }
.plan-rec-summary > div { margin-bottom: 4px; }
.plan-rec-cal { color: var(--vc-text2, #999); font-size: 12px; }
.plan-rec-disclaimer { margin-top: 16px; padding: 8px 12px; border: 1px solid var(--vc-accent-red, #ef4444); border-radius: 3px; color: var(--vc-text, #ddd); font-size: 13px; background: rgba(239, 68, 68, 0.08); }
```

### Task 4.6: Locales + DOCUMENTATION

- [ ] **Step 4.6.1: Locales**

`locales/de.json` neuer Block:

```json
"planRec": {
  "title": "Plan-Empfehlung",
  "cycle": "Cycle",
  "current": "Aktueller Tier",
  "rec": "Empfehlung",
  "held": "hielt in",
  "of": "von",
  "cycles": "Cycles",
  "cal": "Kalibrierung",
  "calEmpirical": "empirisch",
  "calDefault": "Default-Fallback",
  "calOverride": "Override aus config",
  "disclaimer": "Schätzung basierend auf Anthropic-Faktoren (1:5:20). Anthropic publiziert keine exakten Token-Limits. Tatsächliche Limits können abweichen."
}
```

`locales/en.json` analog mit Englisch.

- [ ] **Step 4.6.2: DOCUMENTATION**

An `docs/DOCUMENTATION_de.md` anhängen:

```markdown
## Plan-Recommendation

Pro Billing-Cycle wird die hypothetische Auslastung auf jedem
Plan-Tier berechnet (Pro / Max 5x / Max 20x). Empfohlen wird der
**billigste Tier**, der in **mindestens 80% der Cycles** unter 100%
Auslastung blieb.

### Tier-Faktoren

| Tier | Faktor |
|---|---|
| Pro | 1.0 |
| Max 5x | 5.0 |
| Max 20x | 20.0 |

Quelle: Anthropic-Pricing-Kommunikation. Anthropic publiziert keine
exakten Token-Limits — die Faktoren sind grobe relative
Kapazitäts-Schätzungen.

### Kapazitäts-Kalibrierung

Es wird eine **USD-API-Equivalent-Kapazität pro Cycle** pro Tier
berechnet. Quelle in dieser Priorität:

1. **Config-Override:** `plan_capacity_override_pro_usd` in `config.json`.
   Wenn gesetzt: `Pro-Capacity = override`, `Max5x = 5×override`,
   `Max20x = 20×override`.
2. **Empirisch:** Wenn Task 3 mindestens ein Limit-Event auf dem
   aktuellen Tier findet:
   `Pro-Capacity = median(api_cost in limit-hit cycles) / current_tier_factor`.
3. **Default-Fallback:** `Pro-Capacity = 100 USD/Cycle`.

Die Kalibrier-Quelle (`empirical` / `config_override` / `default`)
wird im UI transparent angezeigt.

### Disclaimer

Anthropic publiziert keine exakten Token-Limits. Die Recommendation
ist eine Schätzung — bei Wechsel des Tiers kann die tatsächliche
Auslastung von der berechneten abweichen. Bei kritischen Entscheidungen
zuerst eine konservative Cycle (Max-Auslastung) prüfen, nicht den
Schnitt.
```

### Task 4.7: Smoke + Commit + Deploy

- [ ] **Step 4.7.1: Tests + node check + build**

```bash
python3 -m pytest tests/test_plan_optimizer.py -v 2>&1 | tail -15
node --check templates/dashboard.js && echo OK
python3 extract_stats.py >/tmp/ext_task4.log 2>&1 && echo OK
```

Expected: alle pytest grün, node OK, extract sauber.

- [ ] **Step 4.7.2: Headless smoke + Spot-Check**

```bash
cd public && python3 -m http.server 8765 >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
PWC=$(find ~/.cache/ms-playwright -name 'chrome' -path '*chrome-linux*' 2>/dev/null | head -1)
if [ -n "$PWC" ]; then
  "$PWC" --headless --disable-gpu --dump-dom http://localhost:8765/ 2>&1 | grep -i "plan-rec\|Plan-Empfehlung\|recommended_tier" | head -5
fi
kill $SERVER_PID
cd ..
```

Im Browser User-Prompt: "Klick auf Limits-Tab. Du solltest unter der Event-Timeline jetzt die Plan-Recommendation-Tabelle mit %-Werten pro Tier, die Empfehlungs-Zeile, die Kalibrier-Quelle und die rote Disclaimer-Box sehen."

- [ ] **Step 4.7.3: Commit**

```bash
git add extract_stats.py tests/test_plan_optimizer.py templates/dashboard.js templates/dashboard.css config.example.json locales/de.json locales/en.json docs/DOCUMENTATION_de.md
git status
git commit -m "feat: plan-tier recommendation with empirical calibration (Task 4)

Per-cycle utilization on Pro / Max 5x / Max 20x using Anthropic's
1:5:20 relative factor. Capacity calibration prefers empirical median
of api_cost in limit-hit cycles (current tier), falls back to a \$100
Pro default, and respects an optional config override.

Recommendation = cheapest tier that held (<=100%) in >=80% of cycles.
UI rendered in Limits tab with prominent disclaimer about Anthropic's
unpublished exact limits."
```

- [ ] **Step 4.7.4: Deploy + Live-Validierung**

```bash
./update_dashboard.sh 2>&1 | tail -5
```

Im Browser Limits-Tab prüfen. Akzeptanz: Tabelle vorhanden, Empfehlungs-Zeile sinnvoll, Kalibrier-Quelle transparent, Disclaimer sichtbar.

---

## Finalisierung

### Task 5: Wrap-up

- [ ] **Step 5.1: Final pytest run**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: alle bestehenden + neuen Tests grün.

- [ ] **Step 5.2: CHANGELOG-Entry**

Datei `docs/CHANGELOG.md` (anlegen falls nicht vorhanden) oder oben ergänzen:

```markdown
## Plan-Optimizer & Limit-Watchdog

- **Cache-Flush-Detection (gap-based):** Ersetzt die rate-basierte Heuristik.
  Drei Bedingungen pflichtig (post-buildup, Gap überschreitet Cache-TTL,
  cache_creation > 2× rolling-median). Historische Werte fallen niedriger aus.
- **Idle-Gap-Analyse:** Neue Sektion auf Session-Detail-Seiten + Aggregat-Karte
  auf Costs-Tab. Quantifiziert Cache-Verlust durch Pausen.
- **Limit-Events:** Neuer "Limits"-Tab. Detektion aus expliziten
  rate_limit_error-Responses + 5h-Fingerprint-Heuristik. Timeline pro
  Billing-Cycle.
- **Plan-Recommendation:** Per-Cycle-Auslastung auf Pro / Max 5x / Max 20x mit
  empirischer Kapazitäts-Kalibrierung aus Limit-Events
  (Fallback: $100 Pro/Cycle Default, Config-Override möglich).
- **Config:** Neues optionales Feld `plan_capacity_override_pro_usd`.

Versionsnummer wird separat geklärt.
```

```bash
git add docs/CHANGELOG.md
git commit -m "docs: changelog entry for plan-optimizer + limit-watchdog"
```

- [ ] **Step 5.3: Branch-Status**

```bash
git log --oneline main..HEAD
git status
```

Expected: 5 oder 6 Commits sichtbar (Pre-flight + 4 Tasks + Changelog).

- [ ] **Step 5.4: User-Handoff-Hinweis**

Print: "Branch `feature/plan-optimizer-and-limit-watchdog` ist fertig. Tasks 1-4 deployed und live-validiert. Versionsnummer + Tag + Push entscheidet der User separat. TODO_v2.md enthält die deferred Items (Weekly-Heuristik, API pay-per-use, Predictions)."

---

## Self-Review (durch Plan-Author durchzuführen)

**Spec coverage check** (Mapping Spec-Sektion → Plan-Task):

- Spec §"Task 1 — Gap-basierte Cache-Flush-Detection" → Plan Task 1.1–1.5 ✓
- Spec §"Task 2 — Idle-Gap-Korrelations-Analyse" → Plan Task 2.1–2.7 ✓
- Spec §"Task 3 — Limit-Events Detektion + Visualisierung" → Plan Task 3.1–3.7 ✓
- Spec §"Task 4 — Plan-Recommendation" → Plan Task 4.1–4.7 ✓
- Spec §"Testing-Strategie" → Pytest-Tests in jeder Task, headless-smoke in jedem Closure-Step ✓
- Spec §"Deployment-Ordnung" → Strikt 1→2→3→4, Deploy + Live-Validierung in jeder Task ✓
- Spec §"Config-Erweiterung" → Task 4.5.1 ✓
- Spec §"Out-of-Scope-Ideen-Sammelbecken" → Pre-flight Task 0.4 (TODO_v2.md) ✓

**Placeholder scan:** keine TBD/TODO/FIXME im Plan; alle Code-Blocks vollständig.

**Type consistency check:** `_assistant_turns`-Schema (`{ts, cache_creation, cache_read}`) in Tasks 1+2 konsistent verwendet. `limit_event_candidates`-Schema in Task 3 konsistent (`{type, subtype, timestamp, session_id, confidence}`). `tier_utilization`-Schema in Task 4 konsistent (`{Pro, Max 5x, Max 20x}` Keys). `_normalize_tier_name`-Output-Strings matchen `PLAN_TIER_FACTORS`-Keys.
