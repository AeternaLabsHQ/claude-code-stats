# Session Log

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
