# Session Log

## 2026-04-30 — Hotfix Model-Detail Token-Spalten (v0.8.2)
Bug im Model-Detail-Table: Spalten "Input" und "Cache Read" waren immer 0. Ursache: `model_breakdown` pro Session enthielt nur `cost`, `output_tokens` und `calls` - der Dashboard-JS rekonstruiert `F.model_summary` aber aus diesen Per-Session-Breakdowns und las `input_tokens`/`cache_read_tokens`, die nie gesetzt wurden. Felder in `extract_stats.py` ergänzt.

## 2026-04-24 — Hotfix URL-Loop & Robust JSON (v0.8.1)
URL-Feedback-Loop bei SPA-Catch-All-Hosting entdeckt und gefixt: Client-Guard redirected von doppelten /sessions/-Pfaden auf /. Zusätzlich JSON-Extrahierung im Bulk-Download von Regex auf indexOf umgestellt (robuster gegen const FLOW in Chat-Content und große Strings). v0.8.1 als Patch-Release.

## 2026-04-24 — Markdown Chat Export (v0.8.0)
Neues Feature: Chat-Export als Markdown (einzeln per Session-Button, bulk als ZIP via Sessions-Tab). Parallel aufgeräumt: externer PR #12 (Opus 4.7 Pricing) integriert mit Credit für @JasonTofte, Pre-Release-Fixes gebündelt, Branches aufgeräumt, v0.6.0–v0.8.0 als GitHub-Releases getaggt (Backfill für die Lücke seit v0.5.0).
→ `docs/superpowers/specs/2026-04-24-session-chat-markdown-download-design.md`
