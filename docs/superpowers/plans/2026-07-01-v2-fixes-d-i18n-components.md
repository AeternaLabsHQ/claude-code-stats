# Teilplan D: i18n + Komponenten + Detail-Seiten-JS - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Lokalisierung des Dashboards wird auf alle drei Seitentypen (Dashboard, Projekt-Detail, Session-Detail) und beide Komponenten ausgeweitet, tote Locale-Keys werden entfernt, und die vierfach duplizierten JS-Helper werden in eine gemeinsame Datei vereinheitlicht - inklusive der Behavior-Fixes F16 (Filter-Clamping), F17 (escHtml-Quotes), F18 (Anon-Blur Session-Seite), F19 (F2-Re-Render Projekt-Seite) und F28-JS (Activity-Palette).

**Architecture:** Ein einziger Locale-Liefermechanismus fuer alle Seiten: extract_stats.py injiziert `window.__LOCALE__` (das komplette LOCALE-Objekt) als Script-Tag vor dem gebuendelten JS und wendet `_inject_locale` (fuer `__L_*`-Tokens) neu auch auf Session- und Projekt-Seiten an. Eine neue Datei `templates/components/shared_helpers.js` (Namespace `VCShared`) wird als erstes Modul in alle drei Seiten-Bundles eingebunden; die vier lokalen Helper-Kopien werden durch Aliase ersetzt. Komponenten lesen Strings zur Laufzeit aus `window.__LOCALE__` mit englischen Fallbacks.

**Tech Stack:** Python 3 (extract_stats.py, pytest), Vanilla JS (kein Build-Step, Inlining durch extract_stats.py), JSON-Locales.

## Global Constraints

- KEINE Em-Dashes (U+2014) in neuen oder geaenderten Strings; bestehende Em-Dashes in Prosa-Strings werden durch `-` ersetzt. Alleinstehende `—`-Glyphen als Leerwert-Platzhalter in Tabellenzellen (z.B. `'<span class="st-muted">—</span>'`) sind visuelle Symbole und bleiben.
- pytest muss nach jedem Task gruen sein: `python3 -m pytest tests/ -q` (Stand vor Plan D: 195+ passed; Teilplaene A-C haben eventuell Tests ergaenzt).
- `node --check <datei>` nach jeder JS-Aenderung.
- Keine Aenderungen an Deploy-Skripten (update_dashboard.sh u.ae.).
- Dieser Plan laeuft NACH Teilplan A und B (extract_stats.py und dashboard.js sind dort veraendert worden). Alle Edits nutzen deshalb Code-Anker (exakte Suchstrings) statt Zeilennummern. Wenn ein Anker nicht gefunden wird: erst `grep -n` nach dem Kernbegriff, Kontext lesen, dann analog anwenden. Zwei bekannte Ueberschneidungen: (a) Teilplan B loescht in dashboard.js die toten Funktionen `vcSection`/`vcDistbar`/`vcStatRows`/`vcMiscGrid`/`vcAnonWrap`, `sessionCacheEff`+`effStyle`, `MODEL_COLORS`, `makeSourceBadge`, `chartColors`/`buildVcChartColors`, `switchTab` - dieser Plan fasst diese Funktionen NICHT an; wenn ein Anker in geloeschtem Code laege, entfaellt der Edit ersatzlos. (b) Teilplan C aendert session_detail.css grossflaechig - der CSS-Edit in Task 7 wird deshalb ueber die `body.anon-mode .anon-blur`-Regel geankert, die C nicht entfernt.

## Entscheidungen (im Plan fixiert, nicht neu diskutieren)

1. **Locale-Zugriff der Komponenten:** ueber das globale `window.__LOCALE__` (nicht ueber ctx-Parameter), damit Spalten-Definitionen, die zur Parse-Zeit der IIFE entstehen, bereits lokalisiert sind. Das Locale-Script-Tag wird von extract_stats.py garantiert VOR dem JS-Bundle eingefuegt.
2. **13 "tote" sessions_tab-Keys:** Nur `sessions_count_suffix` hat im aktuellen UI eine Verwendungsstelle (Tabellen-Meta "N sessions") und wird wiederbelebt. Die uebrigen 10 (`sort_date_desc`, `sort_date_asc`, `sort_cost_desc`, `sort_cost_asc`, `sort_messages_desc`, `messages_suffix`, `api_calls_suffix`, `page_prefix`, `page_separator`, `models_label`, `session_label`, `slug_label` - das sind 12) stammen aus dem alten Sessions-Tab vor der Komponenten-Migration; die zugehoerigen UI-Elemente (Sort-Dropdown, expandierte Zeilen, "Seite X von Y"-Paginierung) existieren nicht mehr. Sie werden geloescht (mit Grep-Verifikation in Task 2), nicht kuenstlich wiederbelebt.
3. **F18 (Anon-Blur Chat):** statt Selektor-Reparatur in `blurMessages()` eine reine CSS-Loesung (`body.anon-mode .msg-content { filter: blur(4px) }`). Die JS-Funktion samt MutationObserver wird geloescht - CSS uebersteht Re-Renders von selbst.
4. **F15-Label:** Die Werte von `activity.hourly` und `activity.weekday` bekommen den Zusatz "(local time)" / "(lokale Zeit)" direkt im Locale-Wert; kein Code-Edit noetig.
5. **Theme-IIFE-Unification** betrifft nur die beiden Detail-Seiten (`VCShared.vcInitThemePage()`). Das Dashboard behaelt seine eigene Theme-Verdrahtung (sie refresht zusaetzlich Charts); nur dessen F2-anonNote wird auf die gemeinsame Factory umgestellt.
6. **session_detail.js Zeile ~454:** Der deutsche Hardcode `'"Reasoning" = Turns ohne Tool-Call.'` in der sonst englischen Datei wird ueber den neuen Key `costs.tool_share_expl_short` lokalisiert (behebt den Sprachmix).

## Dateistruktur

- Neu: `templates/components/shared_helpers.js` (VCShared: escHtml, fmtTokens, fmtUSD, modelClass, calcCacheEff, effStyle, vcAnonNote, vcInitThemePage, localeCode)
- Neu: `tests/test_locale_parity.py`
- Modify: `locales/en.json`, `locales/de.json`
- Modify: `extract_stats.py` (nur `_get_html_template`, `_get_session_html_template`, `_get_project_html_template`, `generate_session_pages`-Umfeld: Locale-Script + Bundling + `_inject_locale`)
- Modify: `templates/dashboard.js`, `templates/dashboard.html`, `templates/session_detail.js`, `templates/session_detail.css` (eine Regel), `templates/project_detail.js`, `templates/project_detail.html`, `templates/components/session_table.js`, `templates/components/session_filters.js`

---

### Task 1: Guard-Test test_locale_parity.py

**Files:**
- Create: `tests/test_locale_parity.py`

**Interfaces:**
- Consumes: `locales/en.json`, `locales/de.json`, `templates/**/*.html|js`
- Produces: pytest-Guard, der Key-Paritaet, Platzhalter-Paritaet, Em-Dash-Freiheit und `__L_*`-Token-Aufloesung absichert. Alle spaeteren Tasks muessen diesen Test gruen halten.

- [ ] **Step 1: Test schreiben**

```python
"""Locale parity guard: en.json and de.json must stay structurally identical,
free of em dashes, and every __L_*__ token used in templates must resolve."""
import json
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOCALES = BASE / "locales"
TEMPLATES = BASE / "templates"


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


class LocaleParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
        cls.de = json.loads((LOCALES / "de.json").read_text(encoding="utf-8"))
        cls.flat_en = flatten(cls.en)
        cls.flat_de = flatten(cls.de)

    def test_key_sets_identical(self):
        only_en = set(self.flat_en) - set(self.flat_de)
        only_de = set(self.flat_de) - set(self.flat_en)
        self.assertFalse(only_en or only_de,
                         f"only in en: {sorted(only_en)}; only in de: {sorted(only_de)}")

    def test_placeholders_match(self):
        ph = re.compile(r"\{[a-zA-Z0-9_]+\}")
        for key, en_val in self.flat_en.items():
            de_val = self.flat_de.get(key)
            if not isinstance(en_val, str) or not isinstance(de_val, str):
                continue
            self.assertEqual(sorted(ph.findall(en_val)), sorted(ph.findall(de_val)),
                             f"placeholder mismatch in {key}")

    def test_no_em_dashes(self):
        for name, flat in (("en", self.flat_en), ("de", self.flat_de)):
            for key, val in flat.items():
                if isinstance(val, str):
                    self.assertNotIn("—", val, f"em dash in {name}:{key}")

    def test_template_tokens_resolve(self):
        valid = set()
        for sec, val in self.en.items():
            if isinstance(val, dict):
                for k in val:
                    valid.add(f"__L_{sec}_{k}__")
            elif isinstance(val, str):
                valid.add(f"__L_{sec}__")
        sources = (list(TEMPLATES.glob("*.html")) + list(TEMPLATES.glob("*.js"))
                   + list((TEMPLATES / "components").glob("*.js")))
        self.assertTrue(sources, "no template sources found")
        token_re = re.compile(r"__L_[A-Za-z0-9_]+__")
        for path in sources:
            for tok in token_re.findall(path.read_text(encoding="utf-8")):
                self.assertIn(tok, valid, f"{path.name}: unresolved token {tok}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Test ausfuehren - erwartet PASS**

Run: `python3 -m pytest tests/test_locale_parity.py -v`
Expected: 4 passed. (Das ist ein Guard, kein Bugfix-Test: Paritaet und Token-Aufloesung stimmen aktuell schon; der Test verhindert Regressionen durch die folgenden Tasks.)

- [ ] **Step 3: Gesamte Suite ausfuehren**

Run: `python3 -m pytest tests/ -q`
Expected: alles gruen.

- [ ] **Step 4: Commit**

```bash
git add tests/test_locale_parity.py
git commit -m "test: add locale parity guard (key sets, placeholders, em dashes, __L_ tokens)"
```

---

### Task 2: Neue Locale-Keys in en.json und de.json

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/de.json`

**Interfaces:**
- Produces: Alle Keys, die die Tasks 5-10 konsumieren. Sektionen/Namen exakt wie hier definiert - spaetere Tasks referenzieren sie woertlich: `kpi.tokens`, `kpi.tip_*`, `kpi.per_day_suffix`, `kpi.per_session_suffix`, `costs.tool_share_*`, `costs.wc_*`, `plan.full_period_label`, `plan.full_period_hint`, `dialogs.*`, `errors.*`, `planRec.<14 neue>`, `project_detail.<neue>`, `sessions_tab.<neue>`.
- Keys, die Teilplan B konsumiert (z.B. `costs.toggle_tokens`, `cacheFlush.*`, `limits.*`), werden NICHT umbenannt.

- [ ] **Step 1: Grep-Verifikation der 12 zu loeschenden sessions_tab-Keys**

Run:
```bash
for k in sort_date_desc sort_date_asc sort_cost_desc sort_cost_asc sort_messages_desc \
         messages_suffix api_calls_suffix page_prefix page_separator models_label \
         session_label slug_label; do
  echo "== $k"
  grep -rn "$k" templates/ extract_stats.py | grep -v '^Binary'
done
```
Expected: 0 Treffer pro Key (Treffer nur in locales/ sind ok und erscheinen hier nicht, weil locales/ nicht gegrept wird). Falls ein Key doch Treffer hat: NICHT loeschen, im Task-Report vermerken.

- [ ] **Step 2: en.json erweitern**

In `locales/en.json` die folgenden Aenderungen (Sektionen existieren bereits, sofern nicht "neu" vermerkt; Reihenfolge innerhalb der Sektion: neue Keys ans Ende):

`kpi` ergaenzen:
```json
    "tokens": "Tokens",
    "per_day_suffix": "/day",
    "per_session_suffix": "/session",
    "tip_api_equivalent": "What this usage would cost via the API (without subscription). Below: actual subscription cost paid in the selected period.",
    "tip_tokens": "Tokens are the text units processed by the language model (approx. 0.75 words per token)",
    "tip_tokens_total": "Total tokens (input + output + cache)",
    "tip_output": "Text generated by Claude",
    "tip_input": "New (non-cached) input tokens per request",
    "tip_cache_read": "Conversation context read from cache – resent every turn, hence the large number",
    "tip_cache_write": "Tokens written to the prompt cache",
    "tip_sessions_per_day": "Sessions per day across the active span (first to last session) of the selected range."
```

`costs` ergaenzen:
```json
    "tool_share_title": "Output-Token Share by Tool",
    "tool_share_expl": "Output-token share. \"Reasoning\" = turns with no tool calls (pure model thinking).",
    "tool_share_expl_short": "\"Reasoning\" = turns with no tool calls.",
    "wc_title": "Output Tokens by Activity",
    "wc_expl": "Where the model's output tokens go. \"Pre-Tool Narration\" = text emitted right before a tool call (separate assistant message); \"Final Answers\" = pure-text turns ending the response.",
    "wc_screen_text": "Final Answers",
    "wc_screen_text_narration": "Pre-Tool Narration",
    "wc_thinking": "Thinking",
    "wc_file_writes": "File Writes",
    "wc_bash_commands": "Bash Commands",
    "wc_tool_inputs": "Other Tool Inputs"
```

`activity` - zwei WERTE aendern (F15-Label):
```json
    "hourly": "Time of Day Distribution (Messages, local time)",
    "weekday": "Weekday Distribution (local time)",
```

`plan` ergaenzen:
```json
    "full_period_label": "always full period",
    "full_period_hint": "The range filter (All / 7D / 30D ...) does not apply here. Plan & Billing always reflects the full tracked billing period."
```

`planRec` ergaenzen (die 14 bisher fehlenden Keys aus Finding 31, ohne Em-Dashes):
```json
    "windows": "5h-windows",
    "weeks": "Weeks",
    "hitsTitle": "Limit Hits by Tier",
    "fiveHHits": "5h-limit hits",
    "weeklyHits": "Weekly-limit hits",
    "none": "None - no tier holds without hits",
    "optimal": "optimal - no change needed",
    "totals": "Total hits across all cycles",
    "recTag": "recommended",
    "curTag": "current",
    "calDerived": "derived from 5h cap",
    "capPerWindow": "per 5h-window",
    "capPerWeek": "per week",
    "anchors": "anchor windows"
```

`project_detail` ergaenzen:
```json
    "top_tools": "Top Tools",
    "skills": "Skills",
    "sessions_heading": "Sessions",
    "kpi_sessions": "Sessions",
    "kpi_messages": "Messages",
    "kpi_tokens": "Tokens",
    "kpi_est_cost": "Est. Cost",
    "subagents": "Subagents",
    "commits": "Commits",
    "pushes": "Pushes",
    "prs": "PRs",
    "errors_label": "Errors",
    "tool_errors_note": "tool errors in this project",
    "no_workflow": "No workflow events",
    "more_suffix": "...and {n} more",
    "wf_read": "Read",
    "wf_edit": "Edit",
    "wf_write": "Write",
    "wf_commit": "Commit",
    "wf_push": "Push",
    "wf_pr": "PR",
    "wf_agent": "Agent"
```

Neue Sektion `dialogs` (nach `planRec` einfuegen):
```json
  "dialogs": {
    "zip_confirm": "Download {n} sessions as ZIP? This can take a moment.",
    "zip_lib_error": "Could not load the ZIP library (offline?).",
    "zip_load_errors": "{n} sessions could not be loaded - see console.",
    "xlsx_lib_error": "Could not load the XLSX library (offline?).",
    "loading_progress": "Loading {i}/{n}...",
    "zipping": "Zipping..."
  }
```

Neue Sektion `errors` (nach `dialogs`):
```json
  "errors": {
    "cat_rejected": "Rejected",
    "cat_file_not_found": "File Not Found",
    "cat_edit_not_unique": "Edit Not Unique",
    "cat_edit_no_match": "Edit No Match",
    "cat_stale_read": "Stale Read",
    "cat_permission_denied": "Permission Denied",
    "cat_timeout": "Timeout",
    "cat_command_not_found": "Cmd Not Found",
    "cat_exit_code": "Exit Code Error",
    "cat_syntax_error": "Syntax Error",
    "cat_import_error": "Import Error",
    "cat_hook_error": "Hook Error",
    "cat_edit_failed": "Edit Failed",
    "cat_rate_limit": "Rate Limit",
    "cat_server_overload": "Server Overload",
    "cat_auth": "Auth",
    "cat_server_error": "Server Error",
    "cat_connection": "Connection",
    "cat_invalid_request": "Invalid Request",
    "cat_content_filter": "Content Filter",
    "cat_other": "Other",
    "src_backend": "Backend",
    "src_tool": "Tool",
    "src_hook": "Hook",
    "src_rejected": "Rejected",
    "src_user": "User",
    "errors_unit": "errors",
    "tool_calls_unit": "tool calls",
    "cancelled_note": "cancelled",
    "cancelled_note_suffix": "(not counted as errors)",
    "no_tasks": "No tasks found"
  }
```

`sessions_tab` KOMPLETT ersetzen durch (behaelt `all_projects`, `search_placeholder`, belebt `sessions_count_suffix` wieder, loescht die 12 in Step 1 verifizierten Keys, ergaenzt Komponenten-Keys):
```json
  "sessions_tab": {
    "all_projects": "All Projects",
    "all_sources": "All Sources",
    "search_placeholder": "Search prompts...",
    "sessions_count_suffix": " sessions",
    "session_suffix_one": " session",
    "bulk_download_btn": "⬇ Download Sessions ({n})",
    "bulk_download_title": "Download all currently filtered sessions as a ZIP of Markdown files",
    "col_date": "Date",
    "col_project": "Project",
    "col_chat_link": "Chat",
    "col_first_prompt": "First Prompt",
    "col_source": "Source",
    "col_model": "Model",
    "col_duration": "Duration",
    "col_messages": "Messages",
    "col_user_messages": "User Msgs",
    "col_assistant_messages": "Assistant Msgs",
    "col_tool_results": "Tool Results",
    "col_command_messages": "Commands",
    "col_interrupts": "Interrupts",
    "col_meta_messages": "Meta",
    "col_api_calls": "API Calls",
    "col_input_tokens": "Input",
    "col_output_tokens": "Output",
    "col_cache_read_tokens": "Cache Read",
    "col_cache_write_tokens": "Cache Write",
    "col_reasoning_tokens": "Reasoning",
    "col_total_tokens": "Total Tokens",
    "col_cost": "Cost",
    "col_reasoning_cost": "Reasoning Cost",
    "col_cache_eff": "Cache Eff.",
    "col_compactions": "⚡ Comp.",
    "col_flushes": "↻ Flushes",
    "col_tool_calls": "Tool Calls",
    "col_file_ops": "File Ops",
    "col_agent_dispatches": "Agents",
    "col_file_size": "Size MB",
    "col_errors": "Errors",
    "group_identity": "Identity",
    "group_volume": "Volume",
    "group_tokens": "Tokens",
    "group_cost": "Cost",
    "group_cache": "Cache Health",
    "group_activity": "Activity",
    "group_errors": "Errors",
    "group_action": "Action",
    "f_user_messages": "User Msgs",
    "f_messages": "Messages",
    "f_duration_min": "Duration",
    "f_total_tokens": "Total Tokens",
    "f_cost": "Cost",
    "f_cache_eff": "Cache Eff.",
    "f_tool_calls": "Tool Calls",
    "f_agent_dispatches": "Agent Dispatches",
    "f_errors": "Error Count",
    "preset_real": "Real sessions only",
    "preset_costly": "Costly sessions only",
    "more_filters": "More filters",
    "clear_all": "Clear all",
    "reset": "Reset",
    "close": "Close",
    "min_placeholder": "min",
    "max_placeholder": "max",
    "clear_aria_prefix": "Clear ",
    "min_aria_suffix": " minimum",
    "max_aria_suffix": " maximum",
    "reset_default": "Reset to default",
    "hide_optional": "Hide all optional",
    "choose_columns": "Choose columns",
    "fullscreen_title": "Fullscreen",
    "exit_fullscreen_title": "Exit fullscreen (Esc)",
    "export_csv_title": "Export visible filter as CSV",
    "export_xlsx_title": "Export visible filter as XLSX (Excel)",
    "no_match": "No sessions match the current filter.",
    "rows_label": "Rows: ",
    "open_chat": "Open chat",
    "multiday_tip": "Multi-day session - active through {end} ({n} days)",
    "resize_tip": "Drag to resize, double-click to fit, right-click to reset"
  }
```

- [ ] **Step 3: de.json spiegelbildlich erweitern**

Gleiche Struktur, deutsche Werte. `kpi`:
```json
    "tokens": "Tokens",
    "per_day_suffix": "/Tag",
    "per_session_suffix": "/Session",
    "tip_api_equivalent": "Was diese Nutzung über die API kosten würde (ohne Abo). Darunter: tatsächlich bezahlter Abo-Preis im gewählten Zeitraum.",
    "tip_tokens": "Tokens sind die Texteinheiten die das Sprachmodell verarbeitet (ca. 0.75 Worte pro Token)",
    "tip_tokens_total": "Summe aller Tokens (Input + Output + Cache)",
    "tip_output": "Von Claude generierter Text",
    "tip_input": "Neue (nicht gecachte) Eingabe-Tokens pro Request",
    "tip_cache_read": "Konversationskontext aus dem Cache gelesen – wird bei jedem Turn erneut gesendet, daher die hohe Zahl",
    "tip_cache_write": "Tokens die in den Cache geschrieben wurden",
    "tip_sessions_per_day": "Sitzungen pro Tag über die aktive Spanne (erste bis letzte Sitzung) des gewählten Zeitraums."
```

`costs`:
```json
    "tool_share_title": "Output-Token-Anteil nach Tool",
    "tool_share_expl": "Anteil der Output-Tokens. \"Reasoning\" = Turns ohne Tool-Call (reines Denken).",
    "tool_share_expl_short": "\"Reasoning\" = Turns ohne Tool-Call.",
    "wc_title": "Output-Tokens nach Aktivität",
    "wc_expl": "Wohin die Output-Tokens des Modells gehen. \"Pre-Tool Narration\" = Text direkt vor einem Tool-Call (separate Assistant-Message); \"Final Answers\" = reine Text-Turns am Ende der Antwort.",
    "wc_screen_text": "Finale Antworten",
    "wc_screen_text_narration": "Pre-Tool-Narration",
    "wc_thinking": "Thinking",
    "wc_file_writes": "Datei-Schreibvorgänge",
    "wc_bash_commands": "Bash-Befehle",
    "wc_tool_inputs": "Andere Tool-Inputs"
```

`activity`-Werte:
```json
    "hourly": "Tageszeit-Verteilung (Nachrichten, lokale Zeit)",
    "weekday": "Wochentags-Verteilung (lokale Zeit)",
```

`plan`:
```json
    "full_period_label": "immer voller Zeitraum",
    "full_period_hint": "Der Zeitraum-Filter (All / 7D / 30D ...) gilt hier nicht. Plan & Abrechnung zeigt immer den gesamten erfassten Abrechnungszeitraum."
```

`planRec`:
```json
    "windows": "5h-Fenster",
    "weeks": "Wochen",
    "hitsTitle": "Limit-Hits nach Tier",
    "fiveHHits": "5h-Limit-Hits",
    "weeklyHits": "Weekly-Limit-Hits",
    "none": "Keiner - kein Tier hält ohne Hits",
    "optimal": "optimal - keine Änderung nötig",
    "totals": "Hits gesamt über alle Zyklen",
    "recTag": "empfohlen",
    "curTag": "aktuell",
    "calDerived": "aus 5h-Cap abgeleitet",
    "capPerWindow": "pro 5h-Fenster",
    "capPerWeek": "pro Woche",
    "anchors": "Anker-Fenster"
```

`project_detail`:
```json
    "top_tools": "Top-Tools",
    "skills": "Skills",
    "sessions_heading": "Sessions",
    "kpi_sessions": "Sessions",
    "kpi_messages": "Nachrichten",
    "kpi_tokens": "Tokens",
    "kpi_est_cost": "Gesch. Kosten",
    "subagents": "Subagents",
    "commits": "Commits",
    "pushes": "Pushes",
    "prs": "PRs",
    "errors_label": "Fehler",
    "tool_errors_note": "Tool-Fehler in diesem Projekt",
    "no_workflow": "Keine Workflow-Events",
    "more_suffix": "...und {n} weitere",
    "wf_read": "Read",
    "wf_edit": "Edit",
    "wf_write": "Write",
    "wf_commit": "Commit",
    "wf_push": "Push",
    "wf_pr": "PR",
    "wf_agent": "Agent"
```

`dialogs`:
```json
  "dialogs": {
    "zip_confirm": "{n} Sessions als ZIP herunterladen? Das kann einen Moment dauern.",
    "zip_lib_error": "ZIP-Bibliothek konnte nicht geladen werden (offline?).",
    "zip_load_errors": "{n} Sessions konnten nicht geladen werden - siehe Konsole.",
    "xlsx_lib_error": "XLSX-Bibliothek konnte nicht geladen werden (offline?).",
    "loading_progress": "Lade {i}/{n}...",
    "zipping": "Packe ZIP..."
  }
```

`errors`:
```json
  "errors": {
    "cat_rejected": "Abgelehnt",
    "cat_file_not_found": "Datei nicht gefunden",
    "cat_edit_not_unique": "Edit nicht eindeutig",
    "cat_edit_no_match": "Edit ohne Treffer",
    "cat_stale_read": "Veralteter Read",
    "cat_permission_denied": "Berechtigung verweigert",
    "cat_timeout": "Timeout",
    "cat_command_not_found": "Befehl nicht gefunden",
    "cat_exit_code": "Exit-Code-Fehler",
    "cat_syntax_error": "Syntaxfehler",
    "cat_import_error": "Import-Fehler",
    "cat_hook_error": "Hook-Fehler",
    "cat_edit_failed": "Edit fehlgeschlagen",
    "cat_rate_limit": "Rate Limit",
    "cat_server_overload": "Server überlastet",
    "cat_auth": "Auth",
    "cat_server_error": "Server-Fehler",
    "cat_connection": "Verbindung",
    "cat_invalid_request": "Ungültiger Request",
    "cat_content_filter": "Content-Filter",
    "cat_other": "Sonstige",
    "src_backend": "Backend",
    "src_tool": "Tool",
    "src_hook": "Hook",
    "src_rejected": "Abgelehnt",
    "src_user": "User",
    "errors_unit": "Fehler",
    "tool_calls_unit": "Tool-Calls",
    "cancelled_note": "abgebrochen",
    "cancelled_note_suffix": "(zählen nicht als Fehler)",
    "no_tasks": "Keine Tasks gefunden"
  }
```

`sessions_tab` KOMPLETT ersetzen (deutsche Werte, gleiche Keys wie en):
```json
  "sessions_tab": {
    "all_projects": "Alle Projekte",
    "all_sources": "Alle Quellen",
    "search_placeholder": "Suche in Prompts...",
    "sessions_count_suffix": " Sessions",
    "session_suffix_one": " Session",
    "bulk_download_btn": "⬇ Sessions laden ({n})",
    "bulk_download_title": "Alle aktuell gefilterten Sessions als ZIP mit Markdown-Dateien herunterladen",
    "col_date": "Datum",
    "col_project": "Projekt",
    "col_chat_link": "Chat",
    "col_first_prompt": "Erster Prompt",
    "col_source": "Quelle",
    "col_model": "Modell",
    "col_duration": "Dauer",
    "col_messages": "Nachrichten",
    "col_user_messages": "User-Msgs",
    "col_assistant_messages": "Assistant-Msgs",
    "col_tool_results": "Tool-Results",
    "col_command_messages": "Commands",
    "col_interrupts": "Interrupts",
    "col_meta_messages": "Meta",
    "col_api_calls": "API Calls",
    "col_input_tokens": "Input",
    "col_output_tokens": "Output",
    "col_cache_read_tokens": "Cache Read",
    "col_cache_write_tokens": "Cache Write",
    "col_reasoning_tokens": "Reasoning",
    "col_total_tokens": "Tokens gesamt",
    "col_cost": "Kosten",
    "col_reasoning_cost": "Reasoning-Kosten",
    "col_cache_eff": "Cache-Eff.",
    "col_compactions": "⚡ Comp.",
    "col_flushes": "↻ Flushes",
    "col_tool_calls": "Tool-Calls",
    "col_file_ops": "Datei-Ops",
    "col_agent_dispatches": "Agents",
    "col_file_size": "MB",
    "col_errors": "Fehler",
    "group_identity": "Identität",
    "group_volume": "Volumen",
    "group_tokens": "Tokens",
    "group_cost": "Kosten",
    "group_cache": "Cache-Gesundheit",
    "group_activity": "Aktivität",
    "group_errors": "Fehler",
    "group_action": "Aktion",
    "f_user_messages": "User-Msgs",
    "f_messages": "Nachrichten",
    "f_duration_min": "Dauer",
    "f_total_tokens": "Tokens gesamt",
    "f_cost": "Kosten",
    "f_cache_eff": "Cache-Eff.",
    "f_tool_calls": "Tool-Calls",
    "f_agent_dispatches": "Agent-Dispatches",
    "f_errors": "Fehleranzahl",
    "preset_real": "Nur echte Sessions",
    "preset_costly": "Nur teure Sessions",
    "more_filters": "Mehr Filter",
    "clear_all": "Alle entfernen",
    "reset": "Zurücksetzen",
    "close": "Schließen",
    "min_placeholder": "min",
    "max_placeholder": "max",
    "clear_aria_prefix": "Entfernen: ",
    "min_aria_suffix": " Minimum",
    "max_aria_suffix": " Maximum",
    "reset_default": "Auf Standard zurücksetzen",
    "hide_optional": "Alle optionalen ausblenden",
    "choose_columns": "Spalten wählen",
    "fullscreen_title": "Vollbild",
    "exit_fullscreen_title": "Vollbild verlassen (Esc)",
    "export_csv_title": "Sichtbaren Filter als CSV exportieren",
    "export_xlsx_title": "Sichtbaren Filter als XLSX (Excel) exportieren",
    "no_match": "Keine Sessions entsprechen dem aktuellen Filter.",
    "rows_label": "Zeilen: ",
    "open_chat": "Chat öffnen",
    "multiday_tip": "Mehrtages-Session - aktiv bis {end} ({n} Tage)",
    "resize_tip": "Ziehen zum Anpassen, Doppelklick für Auto-Breite, Rechtsklick zum Zurücksetzen"
  }
```

- [ ] **Step 4: Paritaets-Test ausfuehren**

Run: `python3 -m pytest tests/test_locale_parity.py -v && python3 -m json.tool locales/en.json > /dev/null && python3 -m json.tool locales/de.json > /dev/null && echo JSON_OK`
Expected: 4 passed, JSON_OK. Achtung: Der Token-Aufloesungs-Test schlaegt fehl, falls ein Template noch `__L_sessions_tab_<geloeschter_key>__` nutzt - laut Step 1 gibt es keine; falls doch, Step 1 wiederholen.

- [ ] **Step 5: Commit**

```bash
git add locales/en.json locales/de.json
git commit -m "feat(i18n): add planRec/dialogs/errors/component keys, retire dead sessions_tab keys"
```

---

### Task 3: shared_helpers.js anlegen

**Files:**
- Create: `templates/components/shared_helpers.js`

**Interfaces:**
- Produces: globales `window.VCShared` mit exakt diesen Signaturen (Tasks 5-8 verlassen sich darauf): `escHtml(s) -> string` (escapt & < > " '), `fmtTokens(n) -> string`, `fmtUSD(n, decimals=2) -> string` (locale-formatiert ueber `window.__LOCALE__.locale_code`), `modelClass(m) -> ''|'opus'|'sonnet'|'haiku'`, `calcCacheEff(s) -> number|null`, `effStyle(pct) -> {color, emoji, label}`, `vcAnonNote(isOn)`, `vcInitThemePage()`, `localeCode() -> string`.
- Consumes: `window.__LOCALE__` (Task 4 injiziert es; bis dahin greift der 'en-US'-Fallback).

- [ ] **Step 1: Datei schreiben**

```js
// ── Shared page helpers (VCShared) ──────────────────────────────
// Single source of truth for escaping, number formatting, model
// badges, cache-efficiency styling, the F2 anon note and the
// detail-page theme/UTC wiring. Bundled as the FIRST script into
// dashboard, project-detail and session-detail pages by
// extract_stats.py, so every later script may assume window.VCShared.
(function() {
  'use strict';

  function localeCode() {
    return (typeof window !== 'undefined' && window.__LOCALE__ && window.__LOCALE__.locale_code) || 'en-US';
  }

  // Escapes text for BOTH element and attribute context (quotes included).
  // null/undefined become '' (the old div.textContent trick rendered
  // "undefined" for undefined input and left quotes unescaped).
  function escHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmtTokens(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return String(n);
  }

  function fmtUSD(n, decimals) {
    const d = decimals == null ? 2 : decimals;
    return '$' + (Number(n) || 0).toLocaleString(localeCode(), {
      minimumFractionDigits: d, maximumFractionDigits: d,
    });
  }

  function modelClass(m) {
    const l = String(m || '').toLowerCase();
    if (l.includes('opus')) return 'opus';
    if (l.includes('sonnet')) return 'sonnet';
    if (l.includes('haiku')) return 'haiku';
    return '';
  }

  function calcCacheEff(s) {
    const inputSum = (s.input_tokens || 0) + (s.cache_read_tokens || 0) + (s.cache_write_tokens || 0);
    if (inputSum === 0) return null;
    return (s.cache_read_tokens || 0) / inputSum * 100;
  }

  function effStyle(pct) {
    if (pct == null) return { color: 'var(--text2)', emoji: '—', label: '—' };
    if (pct >= 80) return { color: 'var(--green)', emoji: '✅', label: pct.toFixed(1) + '%' };
    if (pct >= 50) return { color: 'var(--amber)', emoji: '⚠️', label: pct.toFixed(1) + '%' };
    return { color: 'var(--red)', emoji: '❌', label: pct.toFixed(1) + '%' };
  }

  // One F2 note style for all three pages (Modern SaaS variant).
  function vcAnonNote(isOn) {
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.className = 'vc';
      note.style.cssText = 'position:fixed;top:14px;right:14px;padding:8px 14px;border-radius:var(--vc-radius-sm,10px);border:1px solid var(--vc-accent,#c2562f);background:var(--vc-panel,#ffffff);box-shadow:var(--vc-shadow);font-family:var(--vc-font-mono,JetBrains Mono,ui-monospace,monospace);font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;color:var(--vc-accent,#c2562f);';
      document.body.appendChild(note);
    }
    note.textContent = isOn ? '> ANONYMIZATION ON' : '> ANONYMIZATION OFF';
    note.style.opacity = '1';
    setTimeout(function() { note.style.opacity = '0'; }, 2000);
  }

  // Theme toggle + UTC clock for the two detail pages. The dashboard keeps
  // its own theme wiring (it additionally refreshes charts on toggle).
  function vcInitThemePage() {
    function prefersDark() {
      try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
      catch (e) { return false; }
    }
    function applyTheme(t) {
      document.documentElement.classList.remove('theme-light', 'theme-dark');
      document.documentElement.classList.add('theme-' + t);
      const btn = document.getElementById('vcThemeToggle');
      if (btn) btn.innerHTML = t === 'dark' ? '&#9790;' : '&#9737;';
    }
    const saved = localStorage.getItem('vc-theme');
    const initial = (saved === 'light' || saved === 'dark') ? saved : (prefersDark() ? 'dark' : 'light');
    applyTheme(initial);
    const toggle = document.getElementById('vcThemeToggle');
    if (toggle) {
      toggle.addEventListener('click', function() {
        const cur = document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light';
        const n = cur === 'dark' ? 'light' : 'dark';
        localStorage.setItem('vc-theme', n);
        applyTheme(n);
      });
    }
    function utc() {
      const el = document.getElementById('vcUtcTime');
      if (!el) return;
      el.textContent = new Date().toISOString().slice(11, 19) + ' UTC';
    }
    utc();
    setInterval(utc, 1000);
  }

  window.VCShared = {
    localeCode: localeCode,
    escHtml: escHtml,
    fmtTokens: fmtTokens,
    fmtUSD: fmtUSD,
    modelClass: modelClass,
    calcCacheEff: calcCacheEff,
    effStyle: effStyle,
    vcAnonNote: vcAnonNote,
    vcInitThemePage: vcInitThemePage,
  };
})();
```

- [ ] **Step 2: Syntax-Preflight**

Run: `node --check templates/components/shared_helpers.js`
Expected: kein Output (Exit 0).

- [ ] **Step 3: Commit**

```bash
git add templates/components/shared_helpers.js
git commit -m "feat(js): add VCShared helper module (escaping, formatting, anon note, theme init)"
```

---

### Task 4: extract_stats.py - Locale-Injektion + Bundling fuer alle drei Seiten

**Files:**
- Modify: `extract_stats.py` (Funktionen `_get_html_template`, `_get_session_html_template`, `_get_project_html_template`; neue Helper-Funktion `_locale_script_tag`)

**Interfaces:**
- Produces: `window.__LOCALE__` auf allen drei Seiten (vor jedem Seiten-JS verfuegbar); `__L_*`-Token-Ersetzung auch auf Session-/Projekt-Seiten; `shared_helpers.js` als erstes Bundle-Modul auf allen drei Seiten.
- Consumes: `templates/components/shared_helpers.js` (Task 3), `LOCALE`, `_inject_locale`.

- [ ] **Step 1: Helper `_locale_script_tag` direkt VOR `def _get_html_template` einfuegen**

```python
def _locale_script_tag():
    """Inline the locale as window.__LOCALE__ so bundled page/component JS
    can resolve UI strings at runtime. Must be emitted BEFORE the JS bundle.
    "</" is escaped so no embedded string can close the script tag early."""
    locale_json = json.dumps(LOCALE, ensure_ascii=False).replace("</", "<\\/")
    return f"<script>window.__LOCALE__ = {locale_json};</script>"
```

- [ ] **Step 2: `_get_html_template` erweitern**

Anker: die Zeilen
```python
    css = filters_css + "\n" + table_css + "\n" + css
    js = filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
```
in `_get_html_template` ersetzen durch:
```python
    shared_js = (base_dir / "templates" / "components" / "shared_helpers.js").read_text(encoding="utf-8")
    css = filters_css + "\n" + table_css + "\n" + css
    js = shared_js + "\n" + filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"{_locale_script_tag()}\n<script>{js}</script>")
```

- [ ] **Step 3: `_get_session_html_template` erweitern**

Anker: die Zeilen
```python
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html
```
in `_get_session_html_template` ersetzen durch:
```python
    shared_js = (base_dir / "templates" / "components" / "shared_helpers.js").read_text(encoding="utf-8")
    js = shared_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"{_locale_script_tag()}\n<script>{js}</script>")
    # Locale tokens are resolved at template stage, BEFORE any session data
    # is inserted, so user text containing "__L_..." can never be rewritten.
    html = _inject_locale(html, LOCALE)
    return html
```

- [ ] **Step 4: `_get_project_html_template` erweitern**

Anker: die Zeilen
```python
    css = filters_css + "\n" + table_css + "\n" + css
    js = filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html
```
in `_get_project_html_template` ersetzen durch:
```python
    shared_js = (base_dir / "templates" / "components" / "shared_helpers.js").read_text(encoding="utf-8")
    css = filters_css + "\n" + table_css + "\n" + css
    js = shared_js + "\n" + filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"{_locale_script_tag()}\n<script>{js}</script>")
    # Same ordering rule as the session template: tokens before data.
    html = _inject_locale(html, LOCALE)
    return html
```

- [ ] **Step 5: Verifikation**

Run: `python3 -m py_compile extract_stats.py && python3 -m pytest tests/ -q`
Expected: kompiliert, Tests gruen.

Run (Smoke - erzeugt echte Seiten):
```bash
python3 extract_stats.py > /tmp/extract_run.log 2>&1; tail -3 /tmp/extract_run.log
OUT=$(python3 -c "import extract_stats as e; print(e.OUTPUT_DIR)")
grep -c "window.__LOCALE__" "$OUT/index.html"
ls "$OUT/sessions/" | head -1 | xargs -I{} grep -c "window.__LOCALE__" "$OUT/sessions/{}"
ls "$OUT/projects/" | head -1 | xargs -I{} grep -c "window.__LOCALE__" "$OUT/projects/{}"
```
Expected: jeweils `1`.

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py
git commit -m "feat(i18n): inject window.__LOCALE__ + __L_ tokens into all pages, bundle shared helpers"
```

---

### Task 5: dashboard.js auf VCShared umstellen

**Files:**
- Modify: `templates/dashboard.js`

**Interfaces:**
- Consumes: `VCShared` (Task 3), `window.__LOCALE__` (Task 4).
- Produces: dashboard.js ohne eigene escHtml/fmt/fmtUSD/fmtTokens/modelClass-Implementierungen; F2-Note ueber `VCShared.vcAnonNote` (vereinheitlicht den Stil, ersetzt die alten Terminal-Palette-Fallbacks `#b04a2f`/`#fbfaf6`/'Geist Mono').

- [ ] **Step 1: Helper-Aliase setzen**

Anker (Dateianfang):
```js
const fmt = n => n.toLocaleString(D.locale.locale_code);
const fmtUSD = n => '$' + n.toLocaleString(D.locale.locale_code, {minimumFractionDigits:2, maximumFractionDigits:2});
```
ersetzen durch:
```js
const fmt = n => (Number(n) || 0).toLocaleString(VCShared.localeCode());
const fmtUSD = n => VCShared.fmtUSD(n);
```

Anker:
```js
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
```
ersetzen durch:
```js
const escHtml = VCShared.escHtml;
```

Danach: `grep -n "function fmtTokens\|const fmtTokens\|function modelClass\|const modelClass" templates/dashboard.js`. Jede noch existierende lokale Definition (Teilplan B kann Umfeld veraendert haben) durch die Alias-Form ersetzen:
```js
const fmtTokens = VCShared.fmtTokens;
const modelClass = VCShared.modelClass;
```
Falls eine Funktion nicht (mehr) existiert: Schritt fuer diese Funktion entfaellt.

- [ ] **Step 2: F2-Note auf Factory umstellen**

Anker (im F2-Keydown-Handler):
```js
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.className = 'vc';
      note.style.cssText = 'position:fixed;top:14px;right:14px;padding:8px 14px;border:1px solid var(--vc-accent,#b04a2f);background:var(--vc-panel,#fbfaf6);font-family:\'Geist Mono\',\'JetBrains Mono\',ui-monospace,monospace;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;color:var(--vc-accent,#b04a2f);';
      document.body.appendChild(note);
    }
    note.textContent = anonMode ? '> ANONYMIZATION ON' : '> ANONYMIZATION OFF';
    note.style.opacity = '1';
    setTimeout(() => { note.style.opacity = '0'; }, 2000);
```
ersetzen durch:
```js
    VCShared.vcAnonNote(anonMode);
```

- [ ] **Step 3: Manuelles Quote-Escaping am Limit-Event-Tooltip abloesen**

Anker (Limits-Tab, Event-Marker):
```js
      const titleAttr = tooltip.replace(/"/g, '&quot;');
```
ersetzen durch:
```js
      // escHtml escapes quotes since the VCShared migration, and additionally
      // covers & < > which the old manual replace left unescaped.
      const titleAttr = escHtml(tooltip);
```

- [ ] **Step 4: Verifikation**

Run: `node --check templates/dashboard.js && python3 -m pytest tests/ -q`
Expected: Exit 0, Tests gruen.

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.js
git commit -m "refactor(js): dashboard uses VCShared helpers and unified anon note"
```

---

### Task 6: Komponenten auf VCShared + F16 (Filter-Clamping) + F17 (Quote-Escaping wirksam)

**Files:**
- Modify: `templates/components/session_table.js`
- Modify: `templates/components/session_filters.js`

**Interfaces:**
- Consumes: `VCShared`.
- Produces: Komponenten-Helper als Aliase; `refreshRanges()` mutiert/persistiert keine User-Bounds mehr; getippte Filterwerte werden roh gespeichert.

- [ ] **Step 1: session_table.js Helper ersetzen**

Anker (Block ab `// ── Helpers ──`):
```js
  function escHtml(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }
  function fmtUSD(n) {
    n = Number(n) || 0;
    return '$' + n.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  }
```
ersetzen durch:
```js
  const escHtml = VCShared.escHtml;
  // Note: fmtUSD now formats with the configured locale (was: browser locale).
  const fmtUSD = n => VCShared.fmtUSD(n);
```

Anker:
```js
  function fmtTokens(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return String(n);
  }
  function modelClass(m) {
    const l = String(m || '').toLowerCase();
    if (l.includes('opus')) return 'opus';
    if (l.includes('sonnet')) return 'sonnet';
    if (l.includes('haiku')) return 'haiku';
    return '';
  }
  function calcCacheEff(s) {
    const inputSum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
    if (inputSum === 0) return null;
    return (s.cache_read_tokens||0) / inputSum * 100;
  }
  function effStyle(pct) {
    if (pct == null) return {color:'var(--text2)', emoji:'—', label:'—'};
    if (pct >= 80) return {color:'var(--green)', emoji:'✅', label:pct.toFixed(1)+'%'};
    if (pct >= 50) return {color:'var(--amber)', emoji:'⚠️', label:pct.toFixed(1)+'%'};
    return {color:'var(--red)', emoji:'❌', label:pct.toFixed(1)+'%'};
  }
```
ersetzen durch:
```js
  const fmtTokens = VCShared.fmtTokens;
  const modelClass = VCShared.modelClass;
  const calcCacheEff = VCShared.calcCacheEff;
  const effStyle = VCShared.effStyle;
```
Im Header-Kommentar der Datei den Satz `Self-contained: defines its own helpers so it works inside both dashboard.js and project_detail.js without conflicts.` ersetzen durch `Depends on shared_helpers.js (VCShared), which extract_stats.py bundles before this file on every page.`

- [ ] **Step 2: F17-Wirksamkeit pruefen (kein Code-Edit)**

`escHtml` escapt jetzt `"` - damit sind die Attribut-Kontexte `title="' + escHtml(raw) + '"` (First-Prompt, Multiday-Tooltip) und `title="'+escHtml(f.path)+'"` (project_detail, Task 8) nicht mehr injizierbar.
Run: `grep -n 'title="' templates/components/session_table.js`
Expected: alle Treffer nutzen escHtml oder statische Strings; keine weitere Aktion.

- [ ] **Step 3: session_filters.js - F16-Fix**

Anker:
```js
    function refreshRanges() {
      ranges = computeRanges(getPool());
      // Clamp current bounds into the new range
      ATTRIBUTES.forEach(a => {
        const v = state[a.id];
        const r = ranges[a.id];
        if (v.min != null) v.min = Math.min(Math.max(v.min, r.min), r.max);
        if (v.max != null) v.max = Math.min(Math.max(v.max, r.min), r.max);
      });
      persist();
    }
```
ersetzen durch:
```js
    function refreshRanges() {
      ranges = computeRanges(getPool());
      // Stored bounds stay exactly as the user set them. Sliders clamp
      // visually via valueToPos and predicates use the raw values, so a
      // pool change (range switch, empty pool) must never rewrite or
      // persist user filters.
    }
```

Anker (in `buildRow`, Funktion `commit`):
```js
        if (num == null || isNaN(num)) { setBound(attr.id, side, null); }
        else { setBound(attr.id, side, Math.min(Math.max(num, r.min), r.max)); }
```
ersetzen durch:
```js
        if (num == null || isNaN(num)) { setBound(attr.id, side, null); }
        else { setBound(attr.id, side, num); }
```

- [ ] **Step 4: Verifikation**

Run: `node --check templates/components/session_table.js && node --check templates/components/session_filters.js && python3 -m pytest tests/ -q`
Expected: Exit 0, Tests gruen.

Manueller Trace (im Report festhalten): state `{cost:{min:5}}` + Poolwechsel mit p99-Ceil 1 -> `refreshRanges()` laesst `min:5` unveraendert; localStorage unveraendert; Chip zeigt weiterhin `Cost >=5.00`.

- [ ] **Step 5: Commit**

```bash
git add templates/components/session_table.js templates/components/session_filters.js
git commit -m "fix(components): stop destructive filter-bound clamping, use shared escaping/formatting"
```

---

### Task 7: session_detail.js - VCShared, F18, F28-JS, F39, idleGap-i18n, Em-Dashes

**Files:**
- Modify: `templates/session_detail.js`
- Modify: `templates/session_detail.css` (eine neue Regel)

**Interfaces:**
- Consumes: `VCShared`, `window.__LOCALE__.idleGap` (8 vorhandene Keys), `window.__LOCALE__.costs.tool_share_title|tool_share_expl_short|wc_*`.
- Produces: keine.

- [ ] **Step 1: Helper-Aliase + F39**

Anker (Dateianfang):
```js
const fmt = n => n.toLocaleString();
const fmtUSD = n => '$' + n.toFixed(4);
const fmtTokens = n => { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); };
```
ersetzen durch (loescht das ungenutzte `fmt` - vorher verifizieren: `grep -n "\bfmt(" templates/session_detail.js` muss 0 Treffer liefern):
```js
const fmtUSD = n => VCShared.fmtUSD(n, 4); // 4dp: per-session costs are small
const fmtTokens = VCShared.fmtTokens;
```

Anker:
```js
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function fmtTime(ts) { if(!ts) return ''; const d=new Date(typeof ts==='number'?ts:ts); return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
```
ersetzen durch:
```js
const escHtml = VCShared.escHtml;
function fmtTime(ts) { if(!ts) return ''; const d=new Date(ts); return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
```

Anker:
```js
function modelClass(m) { const l=(m||'').toLowerCase(); if(l.includes('opus')) return 'opus'; if(l.includes('sonnet')) return 'sonnet'; if(l.includes('haiku')) return 'haiku'; return ''; }
function cacheEff(s) {
  const inputSum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
  if (inputSum === 0) return null;
  return (s.cache_read_tokens||0) / inputSum * 100;
}
function effStyle(pct) {
  if (pct == null) return {color:'var(--text2)', emoji:'—', label:'—'};
  if (pct >= 80) return {color:'var(--green)', emoji:'✅', label:pct.toFixed(1)+'%'};
  if (pct >= 50) return {color:'var(--amber)', emoji:'⚠️', label:pct.toFixed(1)+'%'};
  return {color:'var(--red)', emoji:'❌', label:pct.toFixed(1)+'%'};
}
```
ersetzen durch:
```js
const modelClass = VCShared.modelClass;
const cacheEff = VCShared.calcCacheEff;
const effStyle = VCShared.effStyle;
```

- [ ] **Step 2: idleGap-Panel auf Locale-Keys**

Anker:
```js
  // session_detail has no locale injection (matches existing convention:
  // 'Duration', 'Messages', 'Tool Calls' etc. are hardcoded English).
  const T = {
    title:     'Idle Gaps',
    short:     '<5 min',
    mid:       '5–60 min',
    long:      '>1 h',
    turns:     'turns',
    overspend: 'extra tokens spent on cache rebuild after pauses',
    pctOf:     'of this session',
    tip:       "Don't leave sessions open during longer breaks.",
  };
```
ersetzen durch:
```js
  const IG_L = (window.__LOCALE__ && window.__LOCALE__.idleGap) || {};
  const T = {
    title:     IG_L.title     || 'Idle Gaps',
    short:     IG_L.short     || '<5 min',
    mid:       IG_L.mid       || '5-60 min',
    long:      IG_L.long      || '>1 h',
    turns:     IG_L.turns     || 'turns',
    overspend: IG_L.overspend || 'extra tokens spent on cache rebuild after pauses',
    pctOf:     IG_L.pctOf     || 'of this session',
    tip:       IG_L.tip       || "Don't leave sessions open during longer breaks.",
  };
```

- [ ] **Step 3: Em-Dashes in Tooltips (F31-Teil)**

Anker: `'1M context window used — peak '` ersetzen durch `'1M context window used - peak '`.
Anker: `' — exceeds the 200k standard window (1M enabled)'` ersetzen durch `' - exceeds the 200k standard window (1M enabled)'`.

- [ ] **Step 4: Sidebar-Titel + deutscher Hardcode (F35-Teil)**

Anker:
```js
  sideHtml += '<div class="sidebar-card"><h4>Output-Token Share by Tool</h4>' +
    '<p style="font-size:11px;opacity:0.6;margin:0 0 8px 0">"Reasoning" = Turns ohne Tool-Call.</p>' +
```
ersetzen durch:
```js
  const TS_L = (window.__LOCALE__ && window.__LOCALE__.costs) || {};
  sideHtml += '<div class="sidebar-card"><h4>' + (TS_L.tool_share_title || 'Output-Token Share by Tool') + '</h4>' +
    '<p style="font-size:11px;opacity:0.6;margin:0 0 8px 0">' + (TS_L.tool_share_expl_short || '"Reasoning" = turns with no tool calls.') + '</p>' +
```

- [ ] **Step 5: F28-JS - Activity-Palette auf Earth-Tones**

Anker:
```js
const WC_DEF = [
  ['screen_text',           'Final Answers',     '#10b981'],
  ['screen_text_narration', 'Pre-Tool Narration','#06b6d4'],
  ['thinking',              'Thinking',          '#94a3b8'],
  ['file_writes',           'File Writes',       '#6366f1'],
  ['bash_commands',         'Bash Commands',     '#f59e0b'],
  ['tool_inputs',           'Other Tool Inputs', '#a855f7'],
];
```
ersetzen durch:
```js
// Colors = _VC_CAT[0..5] from dashboard.js in WC_CAT_ORDER (keep in sync),
// so the same category renders identically on dashboard and session page.
const WC_L = (window.__LOCALE__ && window.__LOCALE__.costs) || {};
const WC_DEF = [
  ['screen_text',           WC_L.wc_screen_text           || 'Final Answers',      '#c4623f'],
  ['screen_text_narration', WC_L.wc_screen_text_narration || 'Pre-Tool Narration', '#7aa589'],
  ['thinking',              WC_L.wc_thinking              || 'Thinking',           '#cda43f'],
  ['file_writes',           WC_L.wc_file_writes           || 'File Writes',        '#a8442a'],
  ['bash_commands',         WC_L.wc_bash_commands         || 'Bash Commands',      '#6f8f9e'],
  ['tool_inputs',           WC_L.wc_tool_inputs           || 'Other Tool Inputs',  '#9b7bb0'],
];
```

- [ ] **Step 6: F18 - Anon-Blur per CSS, blurMessages loeschen**

In `templates/session_detail.css`, direkt NACH der Zeile
```css
body.anon-mode .anon-blur { filter: blur(4px); user-select: none; }
```
einfuegen:
```css
/* F2 anon mode: blur chat content directly (survives chat re-renders;
   replaces the old blurMessages() JS whose selectors never matched). */
body.anon-mode .msg-content,
body.anon-mode .msg-thinking,
body.anon-mode .msg-tools { filter: blur(4px); user-select: none; }
```
Hinweis: Teilplan C hat session_detail.css umgebaut - die `.anon-blur`-Regel per `grep -n "anon-blur" templates/session_detail.css` lokalisieren.

In `templates/session_detail.js` den kompletten Block loeschen - Anker von
```js
  // Anon-blur message content (user prompts and assistant outputs are unpredictable)
  function blurMessages() {
```
bis einschliesslich
```js
  if (chat) {
    new MutationObserver(() => setTimeout(blurMessages, 100)).observe(chat, {childList: true, subtree: true});
  }
```
(ersatzlos; die Zeilen `const titleEl = ...` / `titleEl.classList.add('anon-blur')` davor bleiben).

- [ ] **Step 7: F2-Note + Theme-IIFE auf VCShared**

Anker (F2-Handler-Innenleben, von `let note = document.getElementById('anonNote');` bis `setTimeout(() => { note.style.opacity = '0'; }, 2000);`) ersetzen durch:
```js
    VCShared.vcAnonNote(document.body.classList.contains('anon-mode'));
```

Anker (Theme-IIFE-Anfang):
```js
(function() {
  function vcSystemPrefersDark() {
```
Den Block von `function vcSystemPrefersDark() {` bis einschliesslich `setInterval(utc, 1000);` ersetzen durch:
```js
  VCShared.vcInitThemePage();
```
(Der Rest der IIFE - Titel-Blur - bleibt.)

- [ ] **Step 8: Verifikation**

Run: `node --check templates/session_detail.js && python3 -m pytest tests/ -q && grep -c "blurMessages" templates/session_detail.js`
Expected: Syntax ok, Tests gruen, `0` blurMessages-Treffer.

- [ ] **Step 9: Commit**

```bash
git add templates/session_detail.js templates/session_detail.css
git commit -m "fix(session): CSS-based anon blur, earth-tone activity palette, locale idle-gap panel, shared helpers"
```

---

### Task 8: project_detail - VCShared, F19, Lokalisierung

**Files:**
- Modify: `templates/project_detail.js`
- Modify: `templates/project_detail.html`

**Interfaces:**
- Consumes: `VCShared`, `window.__LOCALE__.project_detail` (Task 2), `_inject_locale` auf Projekt-Seiten (Task 4).
- Produces: keine.

- [ ] **Step 1: Helper-Aliase + Locale-Zugriff**

Anker (Dateianfang, nach `const P = ...`):
```js
const fmt = n => n.toLocaleString();
const fmtUSD = n => '$'+n.toFixed(2);
const fmtTokens = n => { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); };
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function modelClass(m) { const l=(m||'').toLowerCase(); if(l.includes('opus')) return 'opus'; if(l.includes('sonnet')) return 'sonnet'; if(l.includes('haiku')) return 'haiku'; return ''; }
```
ersetzen durch:
```js
const PD_L = (window.__LOCALE__ && window.__LOCALE__.project_detail) || {};
const pdl = (key, fallback) => PD_L[key] != null ? PD_L[key] : fallback;
const fmt = n => (Number(n) || 0).toLocaleString(VCShared.localeCode());
const fmtUSD = n => VCShared.fmtUSD(n);
const fmtTokens = VCShared.fmtTokens;
const escHtml = VCShared.escHtml;
const modelClass = VCShared.modelClass;
```
(`modelClass` wird aktuell nirgends in project_detail.js aufgerufen - `grep -n "modelClass(" templates/project_detail.js`; wenn 0 Nutzungen ausser der Definition: Alias weglassen und Definition ersatzlos loeschen.)

- [ ] **Step 2: JS-Strings lokalisieren**

KPI-Block - Anker `'<div class="kpi-card"><div class="label">Sessions</div>...` (4 Karten) ersetzen durch:
```js
document.getElementById('kpiGrid').innerHTML =
  '<div class="kpi-card"><div class="label">'+pdl('kpi_sessions','Sessions')+'</div><div class="value" style="color:var(--blue)">'+P.stats.total_sessions+'</div></div>' +
  '<div class="kpi-card"><div class="label">'+pdl('kpi_messages','Messages')+'</div><div class="value" style="color:var(--green)">'+fmt(P.stats.total_messages)+'</div></div>' +
  '<div class="kpi-card"><div class="label">'+pdl('kpi_tokens','Tokens')+'</div><div class="value" style="color:var(--purple)">'+fmtTokens(P.stats.total_tokens)+'</div></div>' +
  '<div class="kpi-card"><div class="label">'+pdl('kpi_est_cost','Est. Cost')+'</div><div class="value" style="color:var(--orange)">'+fmtUSD(P.stats.total_cost)+'</div></div>';
```

Skills - Anker `'<div class="tools-section"><h3>Skills</h3>...`: `<h3>Skills</h3>` -> `<h3>'+pdl('skills','Skills')+'</h3>`.

Memory - Anker `...classList.toggle(\'expanded\')">Project Memory</h3>`: `Project Memory` -> `'+pdl('memory','Project Memory')+'`.

Info-Grid - im selben Muster:
- `'<div class="info-card"><h4>Subagents</h4>'` -> `'<div class="info-card"><h4>'+pdl('subagents','Subagents')+'</h4>'`
- `'<div class="info-card"><h4>Git Operations</h4>'` -> `'<div class="info-card"><h4>'+pdl('git_operations','Git Operations')+'</h4>'`
- `'<span class="lbl">Commits</span>'` -> `'<span class="lbl">'+pdl('commits','Commits')+'</span>'`; analog `Pushes` -> `pdl('pushes','Pushes')`, `PRs` -> `pdl('prs','PRs')`
- `'<div class="info-card"><h4>Errors</h4>'` -> `'<div class="info-card"><h4>'+pdl('errors_label','Errors')+'</h4>'`
- `'tool errors in this project'` -> `'+pdl('tool_errors_note','tool errors in this project')+'` (im umgebenden String)

Top-Files - Anker `'<div class="tools-section"><h3>Top Files</h3>' + '<table class="file-table"><thead><tr><th>File</th><th>Reads</th><th>Edits</th><th>Writes</th></tr></thead><tbody>'` ersetzen durch:
```js
    '<div class="tools-section"><h3>'+pdl('top_files','Top Files')+'</h3>' +
    '<table class="file-table"><thead><tr><th>'+pdl('th_file','File')+'</th><th>'+pdl('th_reads','Reads')+'</th><th>'+pdl('th_edits','Edits')+'</th><th>'+pdl('th_writes','Writes')+'</th></tr></thead><tbody>' +
```

Workflow - Anker `const wfLabels = {read:'Read',edit:'Edit',write:'Write',git_commit:'Commit',git_push:'Push',git_pr:'PR',agent:'Agent'};` ersetzen durch:
```js
const wfLabels = {
  read: pdl('wf_read','Read'), edit: pdl('wf_edit','Edit'), write: pdl('wf_write','Write'),
  git_commit: pdl('wf_commit','Commit'), git_push: pdl('wf_push','Push'),
  git_pr: pdl('wf_pr','PR'), agent: pdl('wf_agent','Agent'),
};
```
Anker `'<div style="color:var(--text2);padding:20px">No workflow events</div>'`: `No workflow events` -> `'+pdl('no_workflow','No workflow events')+'`.

Workflow-"mehr"-Zeile - Anker:
```js
  }).join('') + (filtered.length > 200 ? '<div style="color:var(--text2);padding:8px;font-size:12px">...and '+(filtered.length-200)+' more</div>' : '');
```
ersetzen durch:
```js
  }).join('') + (filtered.length > 200 ? '<div style="color:var(--text2);padding:8px;font-size:12px">'+pdl('more_suffix','...and {n} more').replace('{n}', filtered.length-200)+'</div>' : '');
```

- [ ] **Step 3: F19 + F2-Note + Theme-IIFE**

F2-Handler komplett ersetzen - Anker `document.addEventListener('keydown', function(e) { if (e.key === 'F2') {` bis zum zugehoerigen `});`:
```js
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    document.body.classList.toggle('anon-mode');
    // F19: re-render immediately so the table picks up anon-mode
    // (renderTable reads body class + applies anonSource substitution).
    pdRender();
    VCShared.vcAnonNote(document.body.classList.contains('anon-mode'));
  }
});
```

Abschluss-IIFE ersetzen - Anker `(function() { function v(name, fb) {` bis zum Datei-Ende `})();`:
```js
(function() {
  VCShared.vcInitThemePage();

  // Project name + meta
  const nameEl = document.getElementById('vcProjectName');
  if (nameEl && typeof P !== 'undefined' && P.name) {
    nameEl.textContent = P.name;
    nameEl.classList.add('anon-blur'); // Project names get blurred in anon-mode
  }
  const metaEl = document.getElementById('vcProjectMeta');
  if (metaEl && typeof P !== 'undefined') {
    const stats = P.stats || {};
    metaEl.textContent = (stats.total_sessions || 0) + ' sessions · ' + (stats.total_messages || 0) + ' msgs · $' + (stats.total_cost || 0).toFixed(2);
  }
})();
```
(Damit sind das tote `v()` und die duplizierte Theme-Logik entfernt - F39-Rest.)

- [ ] **Step 4: project_detail.html Tokens**

- `<button class="proj-tab active" data-tab="overview">Overview</button>` -> `...>__L_project_detail_overview__</button>`
- `<button class="proj-tab" data-tab="workflow">Workflow</button>` -> `...>__L_project_detail_workflow__</button>`
- `<h3>Top Tools</h3>` -> `<h3>__L_project_detail_top_tools__</h3>`
- `<h3 style="margin:24px 0 16px;font-size:15px">Sessions</h3>` -> `<h3 style="margin:24px 0 16px;font-size:15px">__L_project_detail_sessions_heading__</h3>`

- [ ] **Step 5: Verifikation**

Run: `node --check templates/project_detail.js && python3 -m pytest tests/ -q`
Expected: Syntax ok, Tests gruen (inkl. Token-Aufloesungs-Test aus Task 1, der die neuen `__L_project_detail_*__`-Tokens gegen Task-2-Keys prueft).

- [ ] **Step 6: Commit**

```bash
git add templates/project_detail.js templates/project_detail.html
git commit -m "fix(project): localize page strings, immediate F2 re-render, shared helpers"
```

---

### Task 9: dashboard.js/html i18n - F30, F33, F35, planRec-Fallbacks

**Files:**
- Modify: `templates/dashboard.js`
- Modify: `templates/dashboard.html`

**Interfaces:**
- Consumes: Keys aus Task 2 (`kpi.tip_*`, `kpi.tokens`, `kpi.per_*`, `dialogs.*`, `errors.*`, `costs.wc_*`, `plan.full_period_*`, `sessions_tab.all_sources`, `sessions_tab.bulk_download_*`).
- Produces: keine `locale_code === 'de'`-Ternaries mehr; keine hartkodierten `'en-US'` in lebendem Code; keine deutschen Hardcodes.

- [ ] **Step 1: F30 - die 8 Ternaries ersetzen**

Jeweils Anker suchen (`grep -n "locale_code === 'de'" templates/dashboard.js`) und ersetzen:
1. KPI-Karte api_equivalent: `tip: D.locale.locale_code === 'de' ? 'Was diese Nutzung ...' : 'What this usage ...'` -> `tip: D.locale.kpi.tip_api_equivalent`
2. KPI-Karte tokens: `label:'Tokens', value:'', sub:'', tip: D.locale.locale_code === 'de' ? 'Tokens sind ...' : 'Tokens are ...'` -> `label:D.locale.kpi.tokens, value:'', sub:'', tip: D.locale.kpi.tip_tokens`
3. `valEl.title = D.locale.locale_code === 'de' ? 'Summe aller Tokens (Input + Output + Cache)' : 'Total tokens (input + output + cache)';` -> `valEl.title = D.locale.kpi.tip_tokens_total;`
4.-7. Der ttOut/ttIn/ttCR/ttCW-Block:
```js
    const ttOut = D.locale.kpi.tip_output;
    const ttIn = D.locale.kpi.tip_input;
    const ttCR = D.locale.kpi.tip_cache_read;
    const ttCW = D.locale.kpi.tip_cache_write;
```
8. `sessSub.title = D.locale.locale_code === 'de' ? 'Sitzungen pro Tag ...' : 'Sessions per day ...';` -> `sessSub.title = D.locale.kpi.tip_sessions_per_day;`

Danach: `grep -c "locale_code === 'de'" templates/dashboard.js` -> Expected `0`.

- [ ] **Step 2: F33 - Dialoge**

In `bulkDownloadSessions`:
- `if (sessions.length > 100 && !confirm(sessions.length + ' Sessions als ZIP herunterladen? Das kann einen Moment dauern.')) return;` ->
```js
  if (sessions.length > 100 && !confirm(D.locale.dialogs.zip_confirm.replace('{n}', sessions.length))) return;
```
- `alert('ZIP-Bibliothek konnte nicht geladen werden (offline?).');` -> `alert(D.locale.dialogs.zip_lib_error);`
- `btn.textContent = 'Loading ' + (i + 1) + '/' + sessions.length + '…';` -> `btn.textContent = D.locale.dialogs.loading_progress.replace('{i}', i + 1).replace('{n}', sessions.length);`
- `btn.textContent = 'Zipping…';` -> `btn.textContent = D.locale.dialogs.zipping;`
- `alert(errors + ' sessions konnten nicht geladen werden — siehe Konsole.');` -> `alert(D.locale.dialogs.zip_load_errors.replace('{n}', errors));`

In `updateBulkBtnLabel`: `btn.textContent = '⬇ Download Sessions (' + n + ')';` -> `btn.textContent = D.locale.sessions_tab.bulk_download_btn.replace('{n}', n);`

- [ ] **Step 3: F35 - en-US, Label-Maps, planRec-Fallback-Em-Dashes**

- `function fmtVcUsd(n) { return '$' + (n || 0).toLocaleString('en-US', ...` -> `'en-US'` durch `D.locale.locale_code` ersetzen.
- `sessEl.textContent = sessions.toLocaleString('en-US');` und `msgEl.textContent = msgs.toLocaleString('en-US');` -> jeweils `D.locale.locale_code`.
- `sessSub.innerHTML = '<b>' + perDay.toFixed(1) + '</b>/day';` -> `... + D.locale.kpi.per_day_suffix;` und `msgSub.innerHTML = '<b>' + perSession + '</b>/session';` -> `... + D.locale.kpi.per_session_suffix;`
- Verbleibende `toLocaleString('en-US')`-Treffer pruefen: `grep -n "'en-US'" templates/dashboard.js`. Treffer in Funktionen, die Teilplan B als tot geloescht hat, existieren nicht mehr; lebende Treffer analog umstellen. Expected am Ende: 0 Treffer.
- `const WC_LABELS = { screen_text: 'Final Answers', ... };` ersetzen durch:
```js
const WC_LABELS = {
  screen_text: D.locale.costs.wc_screen_text,
  screen_text_narration: D.locale.costs.wc_screen_text_narration,
  thinking: D.locale.costs.wc_thinking,
  file_writes: D.locale.costs.wc_file_writes,
  bash_commands: D.locale.costs.wc_bash_commands,
  tool_inputs: D.locale.costs.wc_tool_inputs,
};
```
- `const catLabels = {'rejected':'Rejected', ...};` ersetzen durch:
```js
  const EL = D.locale.errors;
  const catLabels = {'rejected':EL.cat_rejected,'file_not_found':EL.cat_file_not_found,'edit_not_unique':EL.cat_edit_not_unique,'edit_no_match':EL.cat_edit_no_match,'stale_read':EL.cat_stale_read,'permission_denied':EL.cat_permission_denied,'timeout':EL.cat_timeout,'command_not_found':EL.cat_command_not_found,'exit_code':EL.cat_exit_code,'syntax_error':EL.cat_syntax_error,'import_error':EL.cat_import_error,'hook_error':EL.cat_hook_error,'edit_failed':EL.cat_edit_failed,'rate_limit':EL.cat_rate_limit,'server_overload':EL.cat_server_overload,'auth':EL.cat_auth,'server_error':EL.cat_server_error,'connection':EL.cat_connection,'invalid_request':EL.cat_invalid_request,'content_filter':EL.cat_content_filter,'other':EL.cat_other};
  const srcLabels = {'backend':EL.src_backend,'tool':EL.src_tool,'hook':EL.src_hook,'rejected':EL.src_rejected,'user':EL.src_user};
```
- Fehler-Kopfzeile: `'</span> errors / <span style="font-weight:600">'+(es.total_tool_calls||0)+'</span> tool calls</div>'` -> `'</span> '+EL.errors_unit+' / <span style="font-weight:600">'+(es.total_tool_calls||0)+'</span> '+EL.tool_calls_unit+'</div>'`; `' cancelled <span style="opacity:.7">(not counted as errors)</span>'` -> `' '+EL.cancelled_note+' <span style="opacity:.7">'+EL.cancelled_note_suffix+'</span>'`; `'No tasks found'` -> `EL.no_tasks` (Anker: `taskEl.innerHTML = '<div style="color:var(--text2)">No tasks found</div>'`).
- planRec-Fallback-Em-Dashes: in beiden T-Maps `'None — no tier holds without hits'` -> `'None - no tier holds without hits'` und `'optimal — no change needed'` -> `'optimal - no change needed'`.

- [ ] **Step 4: dashboard.html Tokens**

- `<select id="filterSource"><option value="">All Sources</option></select>` -> `...>__L_sessions_tab_all_sources__</option>...`
- bulkDownloadBtn: `title="Download all currently filtered sessions as a ZIP of Markdown files"` -> `title="__L_sessions_tab_bulk_download_title__"`
- Plan-Tab-Header: `<span class="vc-fullrange-hint" title="The range filter (All / 7D / 30D …) does not apply here. Plan &amp; Billing always reflects the full tracked billing period.">&#9432; always full period</span>` -> `<span class="vc-fullrange-hint" title="__L_plan_full_period_hint__">&#9432; __L_plan_full_period_label__</span>`
- `<h3>Output-Token Share by Tool</h3>` -> `<h3>__L_costs_tool_share_title__</h3>`; der zugehoerige `<p ...>Output-token share. "Reasoning" = ...</p>` -> `<p style="font-size:12px;opacity:0.7;margin:0 0 8px 0">__L_costs_tool_share_expl__</p>`
- `<h3>Output Tokens by Activity</h3>` -> `<h3>__L_costs_wc_title__</h3>`; der zugehoerige `<p ...>Where the model's output tokens go. ...</p>` -> `<p style="font-size:12px;opacity:0.7;margin:0 0 8px 0">__L_costs_wc_expl__</p>`

- [ ] **Step 5: Verifikation**

Run: `node --check templates/dashboard.js && python3 -m pytest tests/ -q && grep -c "locale_code === 'de'\|'en-US'" templates/dashboard.js`
Expected: Syntax ok, Tests gruen, `0`.

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.js templates/dashboard.html
git commit -m "fix(i18n): dashboard reads locale keys instead of de-ternaries, en-US hardcodes and German dialogs"
```

---

### Task 10: Komponenten-Strings auf sessions_tab-Keys (F32)

**Files:**
- Modify: `templates/components/session_table.js`
- Modify: `templates/components/session_filters.js`

**Interfaces:**
- Consumes: `window.__LOCALE__.sessions_tab` + `window.__LOCALE__.dialogs` (Task 2/4).
- Produces: vollstaendig lokalisierter Sessions-Tab auf Dashboard UND Projekt-Seiten; englische Fallbacks bleiben im Code (Robustheit, falls Locale fehlt).

- [ ] **Step 1: session_table.js - Lookup-Helper + Label-Lokalisierung**

Direkt nach den Helper-Aliasen aus Task 6 einfuegen:
```js
  function stL(key, fallback) {
    const sec = (typeof window !== 'undefined' && window.__LOCALE__ && window.__LOCALE__.sessions_tab) || {};
    return sec[key] != null ? sec[key] : fallback;
  }
  function dlgL(key, fallback) {
    const sec = (typeof window !== 'undefined' && window.__LOCALE__ && window.__LOCALE__.dialogs) || {};
    return sec[key] != null ? sec[key] : fallback;
  }
```

Direkt nach `const COLUMNS_BY_ID = Object.fromEntries(COLUMNS.map(c => [c.id, c]));` einfuegen:
```js
  // Localize column + group labels in place; built-in English acts as fallback.
  COLUMNS.forEach(c => { c.label = stL('col_' + c.id, c.label); });
  Object.keys(GROUP_LABELS).forEach(g => { GROUP_LABELS[g] = stL('group_' + g, GROUP_LABELS[g]); });
```

- [ ] **Step 2: session_table.js - UI-Strings**

- `xlsxBtn.title = 'Export visible filter as XLSX (Excel)';` -> `xlsxBtn.title = stL('export_xlsx_title', 'Export visible filter as XLSX (Excel)');`
- `csvBtn.title = 'Export visible filter as CSV';` -> `csvBtn.title = stL('export_csv_title', 'Export visible filter as CSV');`
- `fsBtn.title = 'Fullscreen';` -> `fsBtn.title = stL('fullscreen_title', 'Fullscreen');` (beide Vorkommen: Initial + `setFullscreen`-off-Zweig)
- `fsBtn.title = on ? 'Exit fullscreen (Esc)' : 'Fullscreen';` -> `fsBtn.title = on ? stL('exit_fullscreen_title', 'Exit fullscreen (Esc)') : stL('fullscreen_title', 'Fullscreen');`
- `gear.title = 'Choose columns';` -> `gear.title = stL('choose_columns', 'Choose columns');`
- `reset.textContent = 'Reset to default';` -> `reset.textContent = stL('reset_default', 'Reset to default');`
- `minimal.textContent = 'Hide all optional';` -> `minimal.textContent = stL('hide_optional', 'Hide all optional');`
- `td.textContent = 'No sessions match the current filter.';` -> `td.textContent = stL('no_match', 'No sessions match the current filter.');`
- `meta.textContent = total + ' session' + (total === 1 ? '' : 's');` -> `meta.textContent = total + (total === 1 ? stL('session_suffix_one', ' session') : stL('sessions_count_suffix', ' sessions'));`
- `sizeLbl.textContent = 'Rows: ';` -> `sizeLbl.textContent = stL('rows_label', 'Rows: ');`
- `handle.title = 'Drag to resize, double-click to fit, right-click to reset';` -> `handle.title = stL('resize_tip', 'Drag to resize, double-click to fit, right-click to reset');`
- Chat-Spalte: `title="Open chat"` -> `title="' + escHtml(stL('open_chat', 'Open chat')) + '"` (im Render-String).
- Multiday-Tooltip (Date-Spalte): Anker
```js
            const tip = 'Multi-day session — active through ' + (endDay || '?') + ' (' + nDays + ' days)';
```
ersetzen durch:
```js
            const tip = stL('multiday_tip', 'Multi-day session - active through {end} ({n} days)')
              .replace('{end}', endDay || '?').replace('{n}', nDays);
```
- XLSX: `xlsxBtn.innerHTML = 'Loading…';` -> `xlsxBtn.innerHTML = escHtml(dlgL('loading_progress', 'Loading...').replace('{i}', '').replace('{n}', '')) || 'Loading...';` - NEIN, zu verrenkt: stattdessen `xlsxBtn.innerHTML = 'Loading…';` unveraendert lassen und nur `alert('XLSX-Bibliothek konnte nicht geladen werden (offline?).');` -> `alert(dlgL('xlsx_lib_error', 'Could not load the XLSX library (offline?).'));` ersetzen. ('Loading…'/'Building…' sind kurzlebige Button-Zustaende; wer sie lokalisieren will, ergaenzt eigene Keys - hier bewusst nicht Teil des Plans, im Report als bekannte Luecke nennen.)

- [ ] **Step 3: session_filters.js - Labels + UI-Strings**

Nach `'use strict';` einfuegen:
```js
  function sfL(key, fallback) {
    const sec = (typeof window !== 'undefined' && window.__LOCALE__ && window.__LOCALE__.sessions_tab) || {};
    return sec[key] != null ? sec[key] : fallback;
  }
```

Nach `ATTRIBUTES.forEach(a => { ATTRIBUTES_BY_ID[a.id] = a; });` einfuegen:
```js
  ATTRIBUTES.forEach(a => { a.label = sfL('f_' + a.id, a.label); });
```

`const GROUP_LABELS = { volume: 'Volume', tokens: 'Tokens', cost: 'Cost', cache: 'Cache Health', activity: 'Activity', errors: 'Errors', };` ersetzen durch:
```js
  const GROUP_LABELS = {
    volume: sfL('group_volume', 'Volume'),
    tokens: sfL('group_tokens', 'Tokens'),
    cost: sfL('group_cost', 'Cost'),
    cache: sfL('group_cache', 'Cache Health'),
    activity: sfL('group_activity', 'Activity'),
    errors: sfL('group_errors', 'Errors'),
  };
```

Weitere Ersetzungen:
- PRESETS: `label: 'Real sessions only'` -> `label: sfL('preset_real', 'Real sessions only')`; `label: 'Costly sessions only'` -> `label: sfL('preset_costly', 'Costly sessions only')`
- `toggle.innerHTML = '&#9881; More filters'` -> `toggle.innerHTML = '&#9881; ' + sfL('more_filters', 'More filters')`
- `ca.textContent = 'Clear all';` -> `ca.textContent = sfL('clear_all', 'Clear all');`
- `reset.textContent = 'Reset';` -> `reset.textContent = sfL('reset', 'Reset');`
- `closeBtn.textContent = 'Close';` -> `closeBtn.textContent = sfL('close', 'Close');`
- `iMin.placeholder = 'min';` -> `iMin.placeholder = sfL('min_placeholder', 'min');`; `iMax.placeholder = 'max';` -> `iMax.placeholder = sfL('max_placeholder', 'max');`
- `x.setAttribute('aria-label', 'Clear ' + a.label);` -> `x.setAttribute('aria-label', sfL('clear_aria_prefix', 'Clear ') + a.label);`
- `sMin.setAttribute('aria-label', attr.label + ' minimum');` -> `... attr.label + sfL('min_aria_suffix', ' minimum'));`; analog max.

- [ ] **Step 4: Verifikation**

Run: `node --check templates/components/session_table.js && node --check templates/components/session_filters.js && python3 -m pytest tests/ -q`
Expected: Syntax ok, Tests gruen.

- [ ] **Step 5: Commit**

```bash
git add templates/components/session_table.js templates/components/session_filters.js
git commit -m "feat(i18n): localize session table and filter components via sessions_tab keys"
```

---

### Task 11: Restliche tote Locale-Keys loeschen (F7-locale)

**Files:**
- Modify: `locales/en.json`, `locales/de.json`

**Interfaces:**
- Consumes: finalen Stand aller JS/HTML-Dateien (Tasks 5-10 abgeschlossen).
- Produces: keine.

- [ ] **Step 1: Kandidaten mechanisch verifizieren**

Kandidatenliste (aus dem Review; NACH den Teilplaenen A-D erneut pruefen, weil B/D Nutzungen entfernt oder ergaenzt haben koennen): `tabs.projects`, `tabs.agents`, `tabs.limits`, `limits.tabLabel`, `planRec.held`, `planRec.of`, `planRec.cycles`, `plan.comparison_title`, `plan.comparison_subtitle`, `plan.api_label`, `plan.plan_label`, `insights.configuration`, `insights.system_info`, `insights.performance`, `insights.peak_cpu`, `insights.peak_memory`, `insights.total_storage`, `insights.transcripts`, `insights.debug_logs`, `insights.file_history_label`, `insights.sect_environment`, `insights.sect_environment_meta`, `insights.sect_errors`, `insights.sect_errors_meta`, `agents.th_type`, `agents.th_description`, `agents.th_count`, `agents.th_error`, `agents.top_errors`, `kpi.input_prefix`, `kpi.output_tokens`, `activity.daily_sessions`, `costs.model_dist`, `projects.top15`, `projects.top15_label`.

Verifikationsskript (im Scratchpad ablegen und ausfuehren):
```python
import re
from pathlib import Path

CANDIDATES = [
    ("tabs", "projects"), ("tabs", "agents"), ("tabs", "limits"),
    ("limits", "tabLabel"),
    ("planRec", "held"), ("planRec", "of"), ("planRec", "cycles"),
    ("plan", "comparison_title"), ("plan", "comparison_subtitle"),
    ("plan", "api_label"), ("plan", "plan_label"),
    ("insights", "configuration"), ("insights", "system_info"),
    ("insights", "performance"), ("insights", "peak_cpu"), ("insights", "peak_memory"),
    ("insights", "total_storage"), ("insights", "transcripts"), ("insights", "debug_logs"),
    ("insights", "file_history_label"),
    ("insights", "sect_environment"), ("insights", "sect_environment_meta"),
    ("insights", "sect_errors"), ("insights", "sect_errors_meta"),
    ("agents", "th_type"), ("agents", "th_description"), ("agents", "th_count"),
    ("agents", "th_error"), ("agents", "top_errors"),
    ("kpi", "input_prefix"), ("kpi", "output_tokens"),
    ("activity", "daily_sessions"), ("costs", "model_dist"),
    ("projects", "top15"), ("projects", "top15_label"),
]
sources = []
for pat in ("templates/*.html", "templates/*.js", "templates/components/*.js"):
    sources += list(Path(".").glob(pat))
sources.append(Path("extract_stats.py"))
texts = {p: p.read_text(encoding="utf-8") for p in sources}
for sec, key in CANDIDATES:
    pats = [
        f"__L_{sec}_{key}__",
        rf"\.{re.escape(sec)}\.{re.escape(key)}\b",
        rf"{re.escape(sec)}\[['\"]{re.escape(key)}['\"]\]",
        rf"\bL\.{re.escape(key)}\b",
        rf"\bT\.{re.escape(key)}\b",
    ]
    hits = []
    for p, t in texts.items():
        for pat in pats:
            for m in re.finditer(pat, t):
                line = t.count("\n", 0, m.start()) + 1
                hits.append(f"{p}:{line}:{m.group(0)}")
    status = "DEAD -> delete" if not hits else "IN USE -> KEEP"
    print(f"{sec}.{key}: {status}")
    for h in hits:
        print("   ", h)
```
Achtung Alias-Patterns (`L.<key>` / `T.<key>`): treffen breit - jeden IN-USE-Treffer manuell pruefen, ob das Alias wirklich auf diese Sektion zeigt (z.B. zeigt `T.cycle` in planRec auf den LEBENDEN Key `planRec.cycle`, waehrend `planRec.cycles` tot sein kann). Nur Keys mit Status DEAD (oder ausschliesslich Fehlzuordnungs-Treffern) loeschen.

- [ ] **Step 2: Verifizierte tote Keys aus BEIDEN JSON-Dateien loeschen**

Fuer jeden DEAD-Key den Eintrag in en.json und de.json entfernen. `weekdays` und alle in Tasks 2-10 verdrahteten Keys NICHT anfassen.

- [ ] **Step 3: Verifikation**

Run: `python3 -m pytest tests/test_locale_parity.py tests/ -q`
Expected: gruen (Paritaet haelt, kein Template referenziert einen geloeschten Key).

- [ ] **Step 4: Commit**

```bash
git add locales/en.json locales/de.json
git commit -m "chore(i18n): delete verified-dead locale keys"
```

---

### Task 12: Endabnahme - Vollgenerierung de+en, Headless-Smoke

**Files:**
- Keine Aenderungen (nur Verifikation; temporaere Config-Aenderung wird zurueckgesetzt).

- [ ] **Step 1: Suite + Syntax komplett**

Run:
```bash
python3 -m pytest tests/ -q
for f in templates/dashboard.js templates/session_detail.js templates/project_detail.js \
         templates/components/session_table.js templates/components/session_filters.js \
         templates/components/shared_helpers.js; do node --check "$f" || echo "FAIL $f"; done
```
Expected: Tests gruen, keine FAIL-Zeile.

- [ ] **Step 2: Generierung in beiden Sprachen + Token-Check**

```bash
CUR_LANG=$(python3 -c "import json; print(json.load(open('config.json')).get('language','en'))")
OUT=$(python3 -c "import extract_stats as e; print(e.OUTPUT_DIR)")
for lang in de en; do
  python3 - "$lang" <<'EOF'
import json, sys
cfg = json.load(open('config.json'))
cfg['language'] = sys.argv[1]
json.dump(cfg, open('config.json', 'w'), indent=2, ensure_ascii=False)
EOF
  python3 extract_stats.py > /tmp/gen_$lang.log 2>&1 || { echo "GEN FAIL $lang"; tail -5 /tmp/gen_$lang.log; }
  echo "== $lang: rohe __L_-Tokens (erwartet 0 pro Datei):"
  grep -l "__L_" "$OUT/index.html" $(ls "$OUT"/projects/*.html | head -2) $(ls "$OUT"/sessions/*.html | head -2) 2>/dev/null || echo "  keine - OK"
done
python3 - "$CUR_LANG" <<'EOF'
import json, sys
cfg = json.load(open('config.json'))
cfg['language'] = sys.argv[1]
json.dump(cfg, open('config.json', 'w'), indent=2, ensure_ascii=False)
EOF
python3 extract_stats.py > /dev/null 2>&1
```
Expected: pro Sprache "keine - OK". Config steht danach wieder auf dem Ausgangswert (wichtig: Cron deployt aus diesem Working Dir).

- [ ] **Step 3: Headless-Smoke (JS-Fehler + Stichproben)**

```bash
CHROME=$(ls ~/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
OUT=$(python3 -c "import extract_stats as e; print(e.OUTPUT_DIR)")
for page in "$OUT/index.html" "$(ls "$OUT"/projects/*.html | head -1)" "$(ls "$OUT"/sessions/*.html | head -1)"; do
  echo "== $page"
  "$CHROME" --headless --disable-gpu --no-sandbox --virtual-time-budget=5000 \
    --enable-logging=stderr --v=0 --dump-dom "file://$page" 2>&1 >/dev/null \
    | grep -i "console.*error\|uncaught" || echo "  keine JS-Fehler"
done
```
Expected: dreimal "keine JS-Fehler". Zusaetzlich Stichprobe (Sprache de): `grep -o "Alle Projekte\|Spalten" "$OUT/index.html" | sort -u` liefert Treffer, sobald config auf de generiert wurde (Schritt fuer den Report dokumentieren, mit welcher Sprache zuletzt generiert wurde).

- [ ] **Step 4: Abschluss-Commit (falls Step 2/3 Fixes noetig machten, sonst entfaellt er)**

```bash
git status --short   # frisch pruefen (parallele Sessions moeglich!)
```
Nur bei tatsaechlichen Aenderungen committen.

---

## Self-Review (durchgefuehrt beim Planschreiben)

1. **Spec-Abdeckung:** F30 (Task 9 Step 1), F31 (Task 2 planRec + Task 9 Step 3 + Task 7 Step 3), F32+F34 (Tasks 2, 4, 8, 10), F33 (Task 9 Step 2, Task 10 Step 2), F35 (Task 9 Steps 3-4), F7-locale (Task 2 Step 1 fuer sessions_tab, Task 11 fuer den Rest), F16 (Task 6 Step 3), F17 (Task 3 escHtml + Task 6 + Task 5 Step 3 fuer die abgeloeste Sonderbehandlung), F18 (Task 7 Step 6), F19 (Task 8 Step 3), F28-JS (Task 7 Step 5), F39 (Task 7 Step 1, Task 8 Step 3), F40 (Tasks 3-8), F15-Label (Task 2 activity-Werte). Bewusste Luecke: 'Loading…'/'Building…'-Buttonzustaende der XLSX-Exportfunktion bleiben englisch (in Task 10 dokumentiert).
2. **Platzhalter-Scan:** Alle Steps enthalten konkreten Code oder exakte Suchanker; keine TBD/TODO-Marker.
3. **Namens-Konsistenz:** `VCShared.*`-Signaturen in Task 3 = Nutzung in Tasks 5-8; Key-Namen in Task 2 = Lookups in Tasks 7-10 (stichprobenhaft gegengeprueft: `sessions_tab.col_agent_dispatches`, `dialogs.zip_load_errors`, `errors.cat_command_not_found`, `project_detail.more_suffix`, `plan.full_period_hint`).
