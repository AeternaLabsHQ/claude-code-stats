# Plan-Optimizer & Limit-Watchdog — Design

**Date:** 2026-05-17
**Branch:** to be created from `main` before implementation
**Status:** Approved (User delegated execution autonomy after design walkthrough)

## Goal

Positioniere claude-code-stats von "Logging-Dashboard" zu "Plan-Optimizer und Limit-Watchdog". Vier zusammenhängende Änderungen, strikt in Reihenfolge umzusetzen:

1. **Cache-Flush-Detection auf gap-basiert umstellen.** Heutiger Counter feuert am Session-Anfang falsch (Buildup wird als Flush gewertet). Neue Heuristik nutzt drei kombinierte Bedingungen: post-buildup, zeitlicher Gap überschreitet Cache-TTL, cache_creation signifikant über Session-Median.
2. **Idle-Gap-Korrelations-Analyse pro Session + globales Aggregat.** Quantifiziert, wieviele Tokens durch Pausen mit Cache-Verlust extra verbraucht wurden. Liefert die einzige wirklich actionable Metrik ("Sessions nicht offen lassen").
3. **Limit-Events detektieren** aus expliziten `rate_limit_error`-Responses + 5h-Fingerprint-Heuristik. Sichtbar in neuem "Limits"-Tab als Timeline pro Billing-Cycle.
4. **Plan-Recommendation** pro Billing-Cycle, kalibriert empirisch aus Task-3-Limit-Events (Fallback: Hardcoded-Default + Config-Override). Pro Cycle prozentuale Auslastung auf Pro / Max5x / Max20x, plus Empfehlung "billigster Tier, der in ≥80% der Cycles held".

## Non-Goals

- **Drift-Detection** ("hat sich seit Mai was an meinen Limits geändert"). Diskutiert, verworfen: ohne UI-%-Ground-Truth keine saubere passive Detection.
- **ML-basierte Anomalie-Erkennung.** Klassische Heuristiken mit transparenten Konstanten.
- **Echtzeit-Updates / Live-Dashboard.** Aktuelles 10min-Cron-Modell bleibt.
- **Predictive-Features.** Erst Real-Data-Detection, später ggf. Predictions.
- **API pay-per-use als vierte Vergleichs-Tier.** In Plan-Recommendation bleiben nur Pro / Max5x / Max20x.
- **Weekly-Limit-Heuristik.** Komplex, unsicher; nach v2-TODO verschoben. In v1.x nur 5h-Fingerprint + explizite Errors.
- **Neue UI-Komponenten in `templates/components/`.** Alle neuen UI-Teile werden inline in den bestehenden Render-Funktionen platziert (Limits-Tab in `dashboard.js`, Idle-Gap-Panel in `session_detail.js`), weil jeweils nur an einer Stelle gemountet.

## Architecture Overview

Alle vier Aufgaben folgen demselben Schnitt:

- **Backend (Python, `extract_stats.py`):** Extraktion, Klassifikation, Aggregation. Pre-computed Felder landen in `dashboard_data.json` und in den per-Session-JSONs unter `public/sessions/<id>.json`.
- **Frontend (JS, vanilla):** Liest die fertigen Felder und rendert. Keine JS-seitige Analytik außer Formatierung.
- **Build-Pipeline:** Existierende Template-Concat in `extract_stats.py` (analog zu Session-Filter-Branch). Keine neuen Tools.

**Geänderte Files:**

- `extract_stats.py` — neue private Funktionen, erweiterte Session-Datenstruktur, neue JSON-Felder unter `plan_analysis`, `idle_gap_aggregate`, `limit_events`, `plan_recommendation`.
- `templates/dashboard.html` — neuer `tab-limits` Container + Tab-Registrierung.
- `templates/dashboard.js` — `renderLimits()` Funktion, Tab-Renderer-Registrierung, Idle-Gap-Aggregat-Karte im Costs-Tab.
- `templates/dashboard.css` — Styling für Limits-Tab (Timeline, Recommendation-Tabelle, Disclaimer-Box).
- `templates/session_detail.js` + `templates/session_detail.css` — neue "Idle Gaps"-Sektion zwischen "Tools" und "Errors".
- `locales/de.json`, `locales/en.json` — neue Strings für UI-Labels.
- `config.example.json` — optionales `plan_capacity_override_pro_usd` Feld.
- `docs/DOCUMENTATION_de.md` — Erklärungen der vier neuen Metriken inkl. Heuristik-Begründungen und Konstanten-Quellen.
- `tests/` — reine Python-Unit-Tests für die vier Heuristiken (kein UI).

**Neue Files:**

- `docs/TODO_v2.md` — Sammelbecken für Out-of-Scope-Ideen während der Umsetzung.

---

## Task 1 — Gap-basierte Cache-Flush-Detection

### Datenstruktur

Heute sammelt `sess["timestamps"]` Zeitstempel für *alle* Events (nicht per Assistant-Turn). Für gap-basierte Detection brauche ich pro Assistant-Turn `(timestamp_ms, cache_creation, cache_read, model)`.

Neue private Liste während Ingest:
```python
sess["_assistant_turns"]: list[dict] = []
```
Jedes Element: `{"ts": int_ms, "cache_creation": int, "cache_read": int, "model": str}`.

Die Liste wird **vor JSON-Serialisierung gedroppt** (führender Underscore = private convention; bereits etabliert siehe `_tool_id_map`).

### Algorithmus

Ausgeführt am Ende des Session-Ingests, **bevor** Aggregations-Output gebaut wird.

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

        # Buildup-over signal: this turn read more from cache than it wrote.
        if (not buildup_over
                and t["cache_read"] > t["cache_creation"]
                and t["cache_read"] > 0):
            buildup_over = True
            continue  # transition turn — not classified

        if not buildup_over:
            continue

        # Now in post-buildup. Track creation history for median.
        if t["cache_creation"] > 0:
            creation_history.append(t["cache_creation"])

        if not prev:
            continue
        gap_ms = t["ts"] - prev["ts"]
        if gap_ms < gap_threshold_ms:
            continue

        # Significantly above running median?
        if len(creation_history) < 3:
            continue
        # Use history excluding the current turn for unbiased baseline.
        median = statistics.median(creation_history[:-1])
        if t["cache_creation"] > 2 * max(median, 100):
            flushes += 1

    return flushes
```

`has_1h_cache` ist `True` wenn die Session mindestens einen Turn mit `cache_1h_tokens > 0` hatte.

### Schwellwert-Begründung (für DOCUMENTATION_de.md)

| Parameter | Wert | Begründung |
|---|---|---|
| Gap-Threshold (short cache) | 5 min | Anthropic dokumentierter ephemerer Cache-TTL |
| Gap-Threshold (extended cache) | 60 min | Wenn Session überhaupt 1h-Cache nutzte, ist erwartete TTL höher; Auto-Detection vermeidet falsche Flush-Klassifizierung |
| Buildup-Ende-Signal | `cache_read > cache_creation AND cache_read > 0` | Der Punkt, an dem der Cache vom Kostenposten zum Asset wird |
| Significance-Multiplikator | 2× | Konservativ; nur deutlich überdurchschnittliche Creation-Kosten gelten als Flush |
| Median-Floor | 100 Tokens | Vermeidet div-by-zero und false positives in winzigen Sessions |
| Rolling statt global | — | Anpassung an Verteilung im Session-Verlauf statt durch Initial-Buildup verschmierter Wert |
| Minimum-Turns | 3 total + 3 post-buildup | Triviale Sessions liefern keine Klassifizierung |

### Validierung (Pflicht-Step in der Plan-Phase)

Lauf gegen ≥10 reale Sessions, gemischt: lange ununterbrochene Coding-Sessions, Sessions mit dokumentierten Mittagspausen, triviale Sub-Agent-Sessions. Akzeptanz:
- Buildup-Only-Session → 0 Flushes
- Pausen-Session → markierte Pausen (Turn-Indices ausgeben für Spot-Check)
- Triviale Session → 0 Flushes (Minimum-Guard)

Wenn 2× nicht passt: Wert anpassen, Anpassung dokumentieren, **bevor** committed wird.

### Migration / Backwards-Compat

Field-Name `cache_flush_count` bleibt; Semantik ändert sich. Hinweis in `DOCUMENTATION_de.md` + CHANGELOG-Entry für v1.x.

---

## Task 2 — Idle-Gap-Korrelations-Analyse

### Per-Turn-Klassifikation

Im selben Loop wie Task 1, klassifiziere jeden Turn nach Gap-Länge zum vorigen Turn:

| Bucket | Range |
|---|---|
| `short` | gap < 5min |
| `mid` | 5min ≤ gap < 60min |
| `long` | gap ≥ 60min |

Erster Turn der Session: kein Gap, nicht klassifiziert.

### Per-Session Output

Neues Feld in der per-Session-JSON:
```json
"idle_gap_summary": {
  "short": {"count": 42, "cache_creation_tokens": 12000},
  "mid":   {"count": 8,  "cache_creation_tokens": 88000},
  "long":  {"count": 2,  "cache_creation_tokens": 65000},
  "estimated_overspend_tokens": 130000,
  "estimated_overspend_pct_of_session": 18,
  "baseline_per_turn_tokens": 285
}
```

**Overspend-Berechnung:**
1. `baseline = median(cache_creation der short-Bucket-Turns)`. Wenn `short`-Bucket leer: Fallback auf Session-Gesamt-Median aller Turns mit `cache_creation > 0`.
2. Für jeden Turn in `mid` oder `long`: `overspend_i = max(0, cache_creation_i - baseline)`.
3. `estimated_overspend_tokens = sum(overspend_i)`.
4. `estimated_overspend_pct_of_session = round(100 * estimated_overspend_tokens / total_cache_creation_in_session)` (falls Denominator > 0).

### Session-Detail UI

Neue Sektion zwischen "Tools" und "Errors" in `session_detail.js`:

```
┌────────────────────────────────────────────────────────────┐
│ Idle Gaps                                                  │
│   <5 min     ████████████████████░░░░░  42 turns ·  12k tk │
│   5–60 min   ████░░░░░░░░░░░░░░░░░░░░░   8 turns ·  88k tk │
│   >1 h       █░░░░░░░░░░░░░░░░░░░░░░░░   2 turns ·  65k tk │
│                                                            │
│   ≈ 130k Tokens Mehrverbrauch durch Cache-Verlust          │
│   wegen Pausen (≈ 18% dieser Session)                      │
│                                                            │
│   ⓘ Sessions nicht offen lassen bei längeren Pausen.       │
└────────────────────────────────────────────────────────────┘
```

Sektion komplett versteckt, wenn:
- `idle_gap_summary` fehlt (Session hatte <3 Turns), ODER
- `mid["count"] == 0 AND long["count"] == 0` (kein Pausenproblem zu zeigen)

Bar-Längen relativ zum Maximum-Count der drei Buckets. Reine ASCII/Unicode-Bars per CSS, keine Chart-Bibliothek.

### Dashboard-Aggregat

Neues Feld `dashboard_data.json.idle_gap_aggregate` (vorberechnet für gesamten Daten-Range):
```json
"idle_gap_aggregate": {
  "total_overspend_tokens": 2400000,
  "total_overspend_usd": 8.40,
  "session_count_with_overspend": 47
}
```

UI: Kleine Karte unten im Costs-Tab unter den bestehenden KPIs:
```
[ Idle-Gap-Mehrverbrauch (gesamte Range): ≈ 2.4M Tokens · ≈ $8.40 · 47 Sessions ]
```

**Date-Range-Filter:** JS rechnet aus der gefilterten Session-Liste neu, indem es die `idle_gap_summary.estimated_overspend_tokens` jeder gefilterten Session summiert. USD-Schätzung via `cost_per_million_input_tokens` (cache_write_5m Mittelwert aller Modelle in der Range gewichtet, fallback Sonnet-5m).

---

## Task 3 — Limit-Events Detektion + Visualisierung

### Quelle A: Explizite Error-Responses

Neue Error-Kategorie `rate_limit` in `_categorize_error()` (Match-Patterns, in Reihenfolge):
- `"rate_limit_error"` (Anthropic-API-Error-Typ-String)
- `"429"` (HTTP-Statuscode in Klartext-Errors)
- `"over capacity"` / `"overloaded"` (UI-Texte)
- `"usage limit reached"` / `"limit reached"` (Anthropic-Web-UI-Texte)
- `"reset at"` (Anthropic-Limit-Message-Pattern)

Zusätzlich: prüfe assistant-Message-Strukturen auf:
- `obj["message"].get("error")` Field (wenn vorhanden, oft mit Typ-Info)
- Content-Blocks vom Typ `"error"` oder Text-Blocks deren `text` die obigen Patterns matched

Bei Match: `_categorize_error()` returnt `"rate_limit"`, der bestehende `sess["errors"]`-Append speichert `category="rate_limit"`, und zusätzlich wird ein Event in eine neue `sess["limit_event_candidates"]`-Liste geschrieben:
```python
{"type": "explicit", "subtype": <rate_limit_error|over_capacity|usage_limit|...>,
 "timestamp": <iso8601>, "session_id": <id>, "confidence": "high"}
```

### Quelle B: 5h-Fingerprint-Heuristik

Auf der **globalen Timeline aller User-Prompts** (project-global, denn 5h-Reset pausiert *alles*, nicht nur eine Session):

Algorithmus:
1. Alle User-Prompt-Timestamps sammeln, sortieren, dedupliziert.
2. Für jedes Paar aufeinanderfolgender Prompts `(t_a, t_b)`:
3. `gap = t_b - t_a`
4. Wenn `4h45m ≤ gap ≤ 5h30m`:
5. Aktivität-Check: gab es mindestens 1 weiteren User-Prompt in `[t_a - 2h, t_a]`? (Vermeidet false positives bei isolierten 5h-Lücken die nur Schlaf sind.)
6. Lokale-Zeit-Check: `t_a` in lokaler Zeit zwischen 07:00 und 22:00, **und** `t_b` in lokaler Zeit zwischen 07:00 und 22:00? (Vermeidet "5h = Nachtschlaf".)
7. Reset-Alignment-Check: ist `t_b` innerhalb von ±15min eines `t_a + 5h`-Anchors?
8. Wenn 1+5+6+7 alle erfüllt: Confidence `high`.
9. Wenn nur 5+6 oder 5+7 erfüllt (3 von 4): Confidence `medium`.
10. Unter 3/4: verwerfen.

Lokale Zeitzone via `time.tzname` / `datetime.now().astimezone().tzinfo`, Fallback UTC mit Warnung im Log.

Heuristik-Parameter (alle in `extract_stats.py` als Konstanten mit Begründung):
```python
LIMIT_5H_GAP_MIN_SEC = 4 * 3600 + 45 * 60  # 4h45m
LIMIT_5H_GAP_MAX_SEC = 5 * 3600 + 30 * 60  # 5h30m
LIMIT_5H_RESET_TOLERANCE_SEC = 15 * 60     # ±15min
LIMIT_5H_ACTIVE_WINDOW_SEC = 2 * 3600      # 2h vor Gap-Start
LIMIT_5H_DAY_START_HOUR = 7                # local
LIMIT_5H_DAY_END_HOUR = 22                 # local
```

Output: Events analog zu Quelle A:
```python
{"type": "heuristic", "subtype": "5h_fingerprint",
 "timestamp": <iso8601 von t_b>,  # Wiederaufnahme = wann das Limit nachließ
 "gap_start": <iso8601 von t_a>,
 "gap_end": <iso8601 von t_b>,
 "session_id": <session_id desjenigen User-Prompts der t_b ist>,
 "confidence": "high"|"medium"}
```

Bei der Sammlung der User-Prompts wird `(timestamp, session_id)` gepaart gespeichert, damit `t_b` direkt auf die Session gemappt werden kann.

### Cycle-Zuordnung

Beim Aufbau von `plan_analysis.periods`: pro Cycle alle Limit-Events filtern, deren `timestamp` (für expliziten Typ) bzw. `gap_end` (für Heuristik) in `[cycle_start, cycle_end]` fällt. Anhängen als `cycle["limit_events"]`.

Plus: globale Top-Level-Liste `dashboard_data.json.limit_events_all` (vor Cycle-Aufteilung) für eventuelles Debugging und für die Visualisierung.

### Limits-Tab UI — Sektion 1: Timeline

```
┌────────────────────────────────────────────────────────────┐
│ Limit Events                                               │
│                                                            │
│ Apr 2026  ──●──────●●──────────────────────────  3 events  │
│ Mar 2026  ────────────●─────────────────────────  1 event  │
│ Feb 2026  ──────────────────────────────────────  0 events │
│ Jan 2026  ──────────────────────────────────────  0 events │
│                                                            │
│ ● Explicit rate-limit error                                │
│ ● 5h-Fingerprint (Heuristik, confidence: high/medium)      │
│                                                            │
│ Klick auf Event → Session öffnen (wenn verfügbar)          │
└────────────────────────────────────────────────────────────┘
```

Pro Cycle eine horizontale `<div>`-Line, Länge = Cycle-Dauer in Tagen (CSS-`width` proportional). Event-Marker als absolut positionierte Punkte (left: `100 * (event_ts - cycle_start) / cycle_duration%`). Tooltip = Event-Details (Typ, Subtyp, Confidence, Timestamp). Marker mit `session_id` linken zu `public/sessions/<id>.html`.

Farben:
- `--vc-accent-red` für explizite Errors
- `--vc-accent` (Standard-Akzent) für 5h-Heuristik-`high`
- `--vc-accent` mit Opacity 0.6 für 5h-Heuristik-`medium`

---

## Task 4 — Plan-Recommendation

### Konstanten (in `extract_stats.py` Top)

```python
# Anthropic-stated approximate relative usage capacity per tier.
# Source: Anthropic pricing communication / docs page (Pro = 1×, Max 5x = 5×,
# Max 20x = 20×). Exact token limits are not published — these factors are
# rough relative-capacity estimates from Anthropic, not measurements.
PLAN_TIER_FACTORS = {"Pro": 1.0, "Max 5x": 5.0, "Max 20x": 20.0}


def _normalize_tier_name(raw: str) -> str | None:
    """Map user config plan strings to PLAN_TIER_FACTORS keys.

    Accepted forms (case-insensitive, whitespace-tolerant):
      'pro' / 'pro plan'              -> 'Pro'
      'max 5x' / 'max5x' / '5x'       -> 'Max 5x'
      'max 20x' / 'max20x' / '20x'    -> 'Max 20x'
    Annual-suffixed forms ('Pro (annual)') strip the suffix.
    Returns None if no match (caller falls back to default tier).
    """
```

(Implementation per the docstring; trivial pattern-matching.)

# Fallback Pro-tier capacity in USD-API-equivalent per billing cycle.
# Used only when no limit events are available for empirical calibration
# and no config override is set. Heavily disclaimed in the UI.
PRO_CAPACITY_USD_DEFAULT = 100.0
```

### Kalibrierungs-Logik

```python
def _estimate_tier_capacity_usd(current_tier: str,
                                 limit_events_by_cycle: dict[str, list],
                                 api_cost_by_cycle: dict[str, float],
                                 override_pro: float | None) -> dict[str, float]:
    """Return per-tier capacity in USD-API-equivalent.

    Calibration priority:
      1. config override (plan_capacity_override_pro_usd) — user knows best
      2. empirical from limit-hit cycles on current tier
      3. hardcoded PRO_CAPACITY_USD_DEFAULT
    """
    if override_pro is not None and override_pro > 0:
        base = override_pro
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

    capacities = {tier: base * factor for tier, factor in PLAN_TIER_FACTORS.items()}
    return {"capacities": capacities, "base_pro_usd": base, "source": source}
```

### Per-Cycle Utilization

```python
util_pct[tier] = round(100 * cycle_api_cost / capacities[tier])
```

Klassifikation:
- `≤ 100` → "held" (✓)
- `> 100` → "exceeded" (⚠)

### Recommendation-Logik

```python
def _summarize_recommendation(cycles, current_tier, threshold_pct=0.8):
    # Wie oft hielt jeder Tier?
    held = {tier: 0 for tier in PLAN_TIER_FACTORS}
    for c in cycles:
        for tier, pct in c["tier_utilization"].items():
            if pct <= 100:
                held[tier] += 1
    total = len(cycles)

    # Billigster Tier, der in >= threshold_pct der Cycles held.
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

### Output-Struktur in `dashboard_data.json`

```json
"plan_recommendation": {
  "current_tier": "Max 5x",
  "recommended_tier": "Max 5x",
  "held_count": {"Pro": 0, "Max 5x": 11, "Max 20x": 12},
  "total_cycles": 12,
  "threshold_pct": 0.8,
  "calibration": {
    "source": "empirical",
    "base_pro_usd": 102.0,
    "capacities": {"Pro": 102.0, "Max 5x": 510.0, "Max 20x": 2040.0}
  },
  "cycles": [
    {
      "cycle_start": "2026-04-01",
      "cycle_end": "2026-04-30",
      "label": "Apr 2026",
      "api_cost": 551.20,
      "tier_utilization": {"Pro": 540, "Max 5x": 108, "Max 20x": 27},
      "limit_event_count": 3
    }
  ]
}
```

### Limits-Tab UI — Sektion 2: Plan-Recommendation

```
┌────────────────────────────────────────────────────────────┐
│ Plan-Empfehlung                                            │
│                                                            │
│ Cycle           Pro      Max 5x    Max 20x                 │
│ ─────────────────────────────────────────────────────────  │
│ Apr 2026        540% ⚠   108% ⚠     27% ✓                  │
│ Mar 2026        320% ⚠    64% ✓     16% ✓                  │
│ Feb 2026        180% ⚠    36% ✓      9% ✓                  │
│ ...                                                        │
│                                                            │
│ Aktueller Tier: Max 5x                                     │
│ Empfehlung: Max 5x bleibt sinnvoll — hielt in 11/12 Cycles │
│ (Pro hätte in 0/12 gereicht, Max 20x in 12/12).            │
│                                                            │
│ Kalibrierung: empirisch (3 Limit-Events in deinen Daten,   │
│ Median bei $510 = 100% Max5x).                             │
│                                                            │
│ ⚠ Schätzung basierend auf Anthropic-Faktoren (1:5:20).     │
│   Anthropic publiziert keine exakten Token-Limits.         │
│   Tatsächliche Limits können abweichen.                    │
└────────────────────────────────────────────────────────────┘
```

Disclaimer-Box prominent (mit Border, Akzent-Farbe), nicht weggefaltet. Kalibrier-Quelle transparent: "empirisch (N Limit-Events)" / "Default-Fallback ($100/Cycle Pro)" / "User-Override aus config".

### Config-Erweiterung

`config.example.json`:
```json
{
  "plan_capacity_override_pro_usd": null
}
```

Doku-Hinweis: "Optional. Override the Pro-tier capacity baseline (USD-API-equivalent per billing cycle) used for plan recommendation. Defaults to empirical estimate from limit events, or $100/cycle if no limit events available."

---

## Testing-Strategie

| Layer | Methode |
|---|---|
| Python-Heuristiken (Tasks 1, 2 Math, 3 Parser, 4 Calibration) | `pytest`-Unit-Tests in `tests/test_plan_optimizer.py`, mit synthetischen Turn-Daten und Fixture-Sessions |
| JSON-Output-Schema | Smoke: `python3 extract_stats.py` + `jq` Existenz-Check der neuen Felder |
| JS-Syntax | `node --check` Preflight pro geänderter JS-Datei |
| UI-Rendering | Headless-Chromium (per `reference_local_ui_smoketest.md`), screenshot-grep nach erwarteten Strings |
| Regression | Dev-Server, manueller Browser-Spot-Check auf ≥5 Sessions + Dashboard nach jedem Task |

Tests laufen pro Task am Ende, **vor** Commit.

---

## Deployment-Ordnung

Strikt 1 → 2 → 3 → 4. Pro Task:

1. Code (Python + JS + Locales + Docs)
2. Unit-Tests grün
3. `python3 extract_stats.py` läuft sauber gegen echte Daten
4. `node --check` Syntax-Preflight
5. Headless-Chromium-Smoke
6. Manueller Browser-Spot-Check auf Dev-Server
7. Eigener Commit pro Task (Subject-Konvention beibehalten: `feat:` / `fix:` / `refactor:` Präfix)
8. Deploy via existierenden Cron / Local-Server, eine Cron-Runde live validieren
9. → nächste Task

Out-of-Scope-Ideen während der Umsetzung wandern in `docs/TODO_v2.md`, nicht in den Code.

---

## Open Questions / Annahmen

Keine offenen Fragen — User hat während Brainstorming volle Execution-Autonomie delegiert ("setze alles alleine um, ohne rückfragen"). Bei Unklarheiten in der Implementierung: nach Datenstruktur-Inspektion eigenständig entscheiden, Entscheidung in DOCUMENTATION_de.md festhalten.
