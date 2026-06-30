## 2026-06-30 — Q&A: Cache-Token-Kostenberechnung erklärt

User fragte, wie Cache-Token-Kosten berechnet werden. calc_cost() in extract_stats.py erklärt: cache_read_input_tokens und cache_creation_input_tokens werden getrennt bepreist (≈0.1× bzw. ≈1.25× Input-Preis). Nicht-offensichtlicher Befund: PRICING enthält pro Modell auch einen cache_write_1h-Satz, der im aktiven Pfad nie verwendet wird — calc_cost() rechnet Cache-Creation immer mit der 5m-Rate, um Claude Codes eigene Kostenberechnung nachzubilden (JSONL liefert keine 5m/1h-Aufschlüsselung). Reine Lesesession, keine Code-Änderungen.
→ Reference-Thought in open-brain (claude-stats-Projekt)

## 2026-06-30 — Doku-Catch-up: README, CHANGELOG, DE-Technikdoku auf v2

User fragte, ob README und alle Dokus aktuell sind. README war seit 2026-06-06 auf v2-Basis, aber ohne die seitdem dazugekommenen Features (Multi-Day-Badges, aktivitätsbasierter Datumsfilter, Chat-Tagestrenner, projected ROI); CHANGELOG.md hing seit 2026-05-19 noch am alten 8-Tab-Pre-v2-Design fest; docs/DOCUMENTATION_de.md (lokal, gitignored) beschrieb noch die 7-Tab-Struktur ohne Fable 5/Opus 4.8/Cache-Anomaly-Detection und mit einer falschen UTC-Zeitzonen-Aussage. Alle drei gegen den aktuellen Code verifiziert und aktualisiert; CHANGELOG bekam einen neuen `[Unreleased] - v2`-Block statt einer erfundenen Versionsnummer. README+CHANGELOG committed (93a7331).
→ README.md, CHANGELOG.md, docs/DOCUMENTATION_de.md (lokal)

## 2026-06-30 — Plan & Billing: Limit-Tabellen-Layout zentriert

User-Screenshot zeigte die zwei Heatmap-Tabellen "5h-limit hits"/"Weekly-limit hits" unschön linksbündig geklebt mit viel Leerraum rechts. 3 Mockup-Optionen per AskUserQuestion gezeigt, User wählte "in Hälften zentriert". `.ph-tables` von Flexbox (content-width) auf CSS-Grid (1fr 1fr, justify-items:center) umgestellt, Responsive-Breakpoint bei 860px ergänzt (Kollaps auf eine zentrierte Spalte).
→ templates/dashboard.css

## 2026-06-12 — Per-Tag-Attribution + Datums-Anzeige-Fixes (2 Feature-Bundles gemergt)

Dual-Layer-Bug "dori fehlt heute/gestern" behoben: sowohl Backend (extract_stats.py) als auch Frontend (filterData) bucketeten Sessions auf den Starttag. Bundle 1 (feature/per-day-token-attribution, 8 Commits): split_session_by_day-Helper mit Reconciliation-Invariante, daily_models/daily_message_count beim Parsen, daily_tokens-Serie + per-session per_day, filterData noFilter-Fastpath nutzt D.daily_* direkt. Bundle 2 (feature/activity-time-and-dates, 5 Commits): hourly/weekday per tatsächlicher Nachricht-Zeit, aktivitäts-basierter Datums-Filter, Mehrtages-Badge in Sessions-Tabelle, Tages-Trenner + Datum in Chat/Copy/Markdown-Export. Beide Bundles via Fast-Forward in feature/dashboard-rethink-v2 gemergt (HEAD a6e6362), 195 Tests grün, Headless-Render 0 Fehler.
→ extract_stats.py, templates/dashboard.js, templates/components/session_table.{js,css}, templates/session_detail.{js,css}

## 2026-06-12 — Dori-Datenlücke analysiert: Laptop-Sync-Task tot seit 12.05.

Debugging-Session ohne Code-Änderungen: Fehlende laptop:dori-Daten auf den stehengebliebenen robocopy-Mirror-Task auf DAD-NB-11 zurückgeführt (lief nur am 2026-05-12, 4 Läufe). Lesepfad und Konnektivität nachweislich OK (smbstatus, Samba-Logs, dashboard_data.json-Abgleich); Fix liegt auf der Laptop-Seite (Task Scheduler).
→ Memory: project_dori_source.md aktualisiert

## 2026-06-11 — Dashboard UI-Polish: KPI-Strip, Billing-Bar, Wochenmarker, Limits-Layout

Umfangreiche UI-Polish-Runde auf feature/dashboard-rethink-v2: KPI-Strip komplett überarbeitet (neue Reihenfolge, TOKENS-Kachel OUT/IN side-by-side, SESSIONS/day statt kaputtem Median), Fortschrittsbalken Plan & Billing als Green→Rot-Gradient-Reveal, Dienstag-Wochenmarker auf den Token-Charts, Plan-Tab Range-Filter ausgeblendet mit Hint, Limit-Hits-Tabellen mit Überschrift + date-first Labels + engerer Spaltenabstand, Segoe-UI-Deadcode aus 3 CSS-Dateien entfernt.
→ templates/dashboard.{html,css,js}, extract_stats.py, templates/{project_detail,session_detail}.css

## 2026-06-10 — Sessions-Export-Buttons + Limits-Redesign-Spec

