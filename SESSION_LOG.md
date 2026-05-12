# Session Log

## 2026-05-12 — DE-Sprachbutton aus Topbar entfernt
Kurze Aufräum-Session. Der "DE"-Button in der Variant-C-Topbar war nie ein echter Sprach-Switch — Klick öffnete nur einen Alert ("Language is set in config.json, edit and re-run extract_stats.py"). i18n läuft bei claude-stats build-time: `extract_stats.py` lädt `locales/{lang}.json` via `load_locale()` und `_inject_locale()` ersetzt `__L_section_key__`-Platzhalter im HTML; der komplette Locale geht zusätzlich als `D.locale` ins `DASHBOARD_DATA` für JS-runtime-Strings. User: "es verwirrt nur" → Button komplett entfernt. Geänderte Files: `templates/dashboard.html` (Button-Markup), `templates/dashboard.js` (Click-Handler, parallele Session hatte exakt dasselbe in 542fd95 schon committed), `locales/en.json` + `locales/de.json` (verwaiste `top.lang_label`/`top.lang_title`-Keys gelöscht).

## 2026-05-07 — Session-Tabelle: Resize, Lightbox, CSV/XLSX-Export, Chat an Pos 3
Folgesession zur Tabellen-Umstellung. Spalten in der Breite anpassbar gemacht (Drag-Handle 5 px am rechten Rand jedes `<th>`; Drag setzt explizite Width, Doppelklick togglet zwischen fit-to-content und reset, Rechtsklick = reset). Beim Wechsel auf `table-layout: fixed` werden natürliche Breiten der nicht-resized Spalten als `frozenWidths`-Snapshot eingefroren, sonst auto-distribute der Browser den Restplatz. Lightbox-Modus via CSS-only `.st-fullscreen`-Klasse (`position: fixed; inset: 0`), Toggle per ⛶-Button oder ESC. Persistenz pro Kontext in localStorage.

CSV-Export hinzugefügt: Locale-abhängiger Separator (DE→`;`, EN→`,`), Floats kriegen `=`-Prefix damit Excel sie als Formel evaluiert und nicht als Datum coercet (`11,1` → sonst „11. Jan", mit `=11,1` bleibt's numerisch). UTF-8-BOM, RFC-4180-Quoting. XLSX-Export via SheetJS Community lazy-loaded vom CDN — native Cell-Types (Date, Number, String), Spaltenbreiten automatisch aus Inhalt der ersten 50 Zeilen. Beide Buttons auf Dashboard in die `session-filters`-Bar vor „Download all" verschoben (passt inhaltlich, alle Export-Aktionen zentral); auf Project-Detail-Seite bleiben sie in der Tabellen-Toolbar.

Chat-Spalte von letzter Position auf Position 3 (nach Project) verschoben. Migration in localStorage zieht `chat_link` automatisch hinter `project` (oder `date` auf Project-Detail), kein User-Reset nötig.

Initial-Bug-Report „Chat-Ansicht kaputt" entpuppte sich als einmaliger Browser-Glitch — Lesson: bei UI-Bugs zuerst nach Symptom/Console-Fehler fragen.

Deploy via `echo 0 > .last_build && ./update_dashboard.sh` (bypass für Template-only-Edits, sonst skipped der Cron).

## 2026-05-07 — Session-Übersicht als Tabelle + Variant-C lokal auf main gemergt
Variant-C-Branch (47 Commits, kein Push) lokal auf main gemergt. Session-Übersicht von Card-Liste auf wiederverwendbare Tabellen-Komponente umgestellt — `templates/components/session_table.{js,css}` mit 25 wählbaren Spalten in 8 Gruppen, Default 8, Picker via Zahnrad, Sort + Page-Size + Spalten persistiert per Kontext (dashboard / projectDetail) in localStorage. Dashboard- und Project-Detail-Seite nutzen die gleiche Komponente; Project-Detail blendet die Project-Spalte automatisch aus. `extract_stats.py` prepended die Komponenten-Files in beide Page-Builds. Smoke-Test mit headless chromium, dann Deploy via `update_dashboard.sh` nach Eiche. v1.0.0-Release deferred bis User die Tabelle im echten Browser bestätigt.
→ docs/superpowers/specs/2026-05-05-session-table-design.md

## 2026-04-30 — Variant-C "Terminal" Dashboard Redesign (autonomous)
Komplette Umstellung des Dashboards auf den Variant-C-Look (Branch `feat/variant-c-terminal`): monospace-forward, single-accent terracotta, hairline borders, kein border-radius, light + dark mode mit prefers-color-scheme + explicit toggle (system/light/dark cycle). User war AFK, ganze Nacht autonom umgesetzt.

**Phase 0 — Template-Extraktion:** HTML/CSS/JS aus `extract_stats.py` Inline-Strings (~6500 Zeilen) in `templates/dashboard.{html,css,js}`, `templates/project_detail.*`, `templates/session_detail.*` ausgelagert. `_get_html_template()`/`_get_session_html_template()`/`_get_project_html_template()` lesen jetzt die Files via Marker-Replace (`<!-- STYLES -->` / `<!-- SCRIPTS -->`). Output strukturell byte-identisch verifiziert (nur DASHBOARD_DATA varies durch live-Daten).

**Phase 1 — Persistent Shell:** Variant-C-Tokens scoped auf `.vc`-Klasse (vermeidet Konflikt mit Legacy-Multi-Color), neuer Top-Bar (Brand, USER/PLAN/RANGE, Lang/Theme-Toggle, F2-Hint, UTC-Time), Primary-Nav mit Tabs links und Quick-Filter + Range-Buttons rechts (Filter wie versprochen erhalten), 5-Cell KPI-Strip (API EQUIVALENT primary in terracotta, Sessions, Messages, Output Tokens, Cache Hit). Chart.js-Defaults via `setupVcChartDefaults()` neu gesetzt (Geist Mono, hairline dotted gridlines, kein border-radius).

**Phase 2 — Tab-Redesign:** Statt Big-Bang-Rewrite pragmatischer Mix aus `.vc`-Scope-Override für Legacy-Komponenten (chart-box, data-table, plan-highlight, kpi-card, etc.) + `↳`-Section-Header pro Tab. Heatmap auf single-accent terracotta mit opacity-Gradient (`0.08 + intensity * 0.92`). MODEL_COLORS und chartColors als Proxy umgebaut, lesen `--vc-*` CSS-Vars zur Laufzeit. F2-Anonymization-Toast in Terminal-Style. Anon-Blur für unvorhersehbare Texte (Plan-Titel, Skills, Hooks).

**Phase 3 — Detail-Seiten:** Project + Session Detail Pages bekommen eigene `.vc`-Token-Definitionen, Variant-C-Top-Bar (mini, mit Back-Link), Re-Skin-Overrides für Header/Stats-Bar/Chat-Panel/Sidebar/Message-Cards/Filter-Buttons. Session-Detail: Chat-Messages auto-blurred via MutationObserver in Anon-Mode. F2-Hotkey auf Detail-Pages aktiviert.

**Pre-existing Fix:** `cost_local`-Config-Key wurde auf code-Seite nicht respektiert (Migration von cost_eur war halb), Fallback-Patch eingebaut damit der Build läuft.

**Phasen-Tags:** `phase-0-complete`, `phase-1-complete`, `phase-2-complete`, `phase-3-complete`. ~25 Commits, ~1600 Plus-Zeilen, alle bestehenden Features erhalten (F2-Anonymization, Schnellfilter, Range-Buttons, MD-Export, Session-Replay, Detail-Drill-Through). Subagents bewusst nicht eingesetzt — Inline-Execution war für die enge Diff-Verifikation und das durchgehende Visual-Tracking effizienter.

## 2026-04-30 — Hotfix Model-Detail Token-Spalten (v0.8.2)
Bug im Model-Detail-Table: Spalten "Input" und "Cache Read" waren immer 0. Ursache: `model_breakdown` pro Session enthielt nur `cost`, `output_tokens` und `calls` - der Dashboard-JS rekonstruiert `F.model_summary` aber aus diesen Per-Session-Breakdowns und las `input_tokens`/`cache_read_tokens`, die nie gesetzt wurden. Felder in `extract_stats.py` ergänzt.

## 2026-04-24 — Hotfix URL-Loop & Robust JSON (v0.8.1)
URL-Feedback-Loop bei SPA-Catch-All-Hosting entdeckt und gefixt: Client-Guard redirected von doppelten /sessions/-Pfaden auf /. Zusätzlich JSON-Extrahierung im Bulk-Download von Regex auf indexOf umgestellt (robuster gegen const FLOW in Chat-Content und große Strings). v0.8.1 als Patch-Release.

## 2026-04-24 — Markdown Chat Export (v0.8.0)
Neues Feature: Chat-Export als Markdown (einzeln per Session-Button, bulk als ZIP via Sessions-Tab). Parallel aufgeräumt: externer PR #12 (Opus 4.7 Pricing) integriert mit Credit für @JasonTofte, Pre-Release-Fixes gebündelt, Branches aufgeräumt, v0.6.0–v0.8.0 als GitHub-Releases getaggt (Backfill für die Lücke seit v0.5.0).
→ `docs/superpowers/specs/2026-04-24-session-chat-markdown-download-design.md`
