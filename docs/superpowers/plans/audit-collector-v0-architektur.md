# Audit Collector v0 - Kern-Architektur-Analyse (§10)

Status: FREIGEGEBEN durch Andie am 2026-07-06, mit zwei Änderungen gegenüber
der ursprünglichen Empfehlung (siehe Abschnitt 7): eigenes Collector-Repo statt
Monorepo, Stack-Entscheidung auf Merit-Basis statt Bestands-Argument.
Datum: 2026-07-06

---

## 0. Faktischer Befund: JSONL-Feldnamen (Klärungspunkt aus der Spec)

Geprüft an einer echten Session-JSONL unter
`~/.claude/projects/-home-andie-projects-claude-stats/` (aktuelle Datei, 42 Zeilen,
9 Record-Typen):

- Das eindeutige Record-Feld heißt **`uuid`**, der Vorgänger-Zeiger **`parentUuid`**.
  Beide existieren - aber **nur auf Message-artigen Records** (`user`, `assistant`,
  `attachment`).
- **Kein `uuid`/`parentUuid`** haben die Metadaten-Typen: `last-prompt`, `mode`,
  `permission-mode`, `bridge-session`, `file-history-snapshot`, `ai-title`.
  In der Beispieldatei sind das ~45% der Zeilen.
- `parentUuid` ist auch bei uuid-tragenden Records legitim `null` (Session-Root,
  `attachment`-Records). Die DAG-Prüfung muss mehrere Roots pro Session erlauben.
- Assistant-Stream-Split (bekannt): mehrere Zeilen pro `message.id` mit
  wiederholter `usage`, aber jede Zeile hat eigene `uuid`. Konsequenz: Collector
  dedupliziert auf Zeilen-Ebene (`uuid`), die Engine dedupliziert weiterhin auf
  `message.id`-Ebene für Token-Zählung. Zwei verschiedene Dedup-Ebenen, beide nötig.

**Konsequenzen für §4/§8 (Entscheidung nötig, siehe Abschnitt 6):**

1. `record_uuid` als universeller Dedup-Schlüssel funktioniert nicht für ~45% der
   Zeilen. Ein vollständiges Roh-Audit muss diese Zeilen trotzdem shippen.
2. Empfehlung: synthetischer Schlüssel für uuid-lose Zeilen:
   `synth:<sha256(session_id || line_index || record_sha256)>`. Dafür braucht der
   Wrapper ein `line_index`-Feld (Zeilennummer in der Quelldatei) - billig, macht
   zusätzlich die Reihenfolge-Rekonstruktion deterministisch (uuid-lose Records
   hängen nicht in der parentUuid-DAG).
3. Subagent-Transcripts liegen als `agent-<id>.jsonl` + `agent-<id>.meta.json`
   Sidecar. Das Sidecar ist keine JSONL-Zeile, wird aber vom Subagent-Linking der
   Engine gebraucht. Empfehlung: Agent shippt das Sidecar als synthetischen Record
   (`type: "x-meta-sidecar"`, raw = Sidecar-Inhalt).

---

## 1. Ist-Analyse des Kerns

`extract_stats.py`: 4617 Zeilen, ein Modul, drei Schichten ineinander:

- **I/O + Discovery:** `parse_session_transcripts()` (~600 Zeilen) mischt
  Quellen-Discovery (Multi-Source, sudo-Pfade), Datei-Iteration und die
  Session-State-Machine. Dazu ~10 `load_*()` Loader für Nicht-Transcript-Quellen
  (history, plans, todos, telemetry, tasks ...).
- **Domänenlogik (die teure Kalibrierung):** weitgehend reine Funktionen auf
  geparsten Datenstrukturen: `calc_cost`, `attribute_turn_tokens`,
  `attribute_write_categories`, `_compute_5h_windows`,
  `_estimate_5h_window_cap_usd`, `_detect_cache_flushes`,
  `_detect_5h_fingerprint_events`, `_merge_streamed_assistant_entries`,
  `_link_subagents`, `build_plan_analysis`, `build_dashboard_data`.
- **Präsentation:** HTML-Generierung, Locale-Injection, Session-/Projekt-Seiten.

Sicherheitsnetz: ~25 Test-Dateien, überwiegend auf die Domänenfunktionen gerichtet.

Entscheidender struktureller Glücksfall: **die Spec reicht `raw` verbatim durch.**
Ein Record aus der DB ist byte-identisch mit der JSONL-Zeile auf dem Client. Damit
kann derselbe Parser-Code beide Quellen lesen - die Engine muss nicht wissen, ob
eine Zeile aus einer Datei oder aus `SELECT raw FROM records` kommt.

---

## 2. Optionen mit Trade-offs

### Option A: Skript wrappen (Collector materialisiert JSONL-Dateien, `extract_stats.py` läuft pro Tenant)

- Pro: nahezu null Engine-Arbeit, Kalibrierung per Definition unangetastet, v0 sehr schnell.
- Contra (hart): zweiter Persistenzpfad neben dem Audit-Store. Die Stats würden aus
  re-materialisierten Dateien gerechnet, nicht aus dem verifizierten Store - für ein
  Audit-Tool konzeptionell falsch (Divergenzrisiko zwischen dem, was die Chain
  beweist, und dem, was das Dashboard zeigt). Mandanten-Trennung per
  Verzeichnis-Konvention, kein Auth-Modell fürs Dashboard, statisches HTML pro
  Tenant. Der Vollscan wächst mit der Historie, und der zentrale Store ist explizit
  das Langzeit-Archiv (>30-Tage-Problem), d.h. die Historie wächst unbegrenzt.
- Fazit: als Dauerzustand ungeeignet; als Übergangs-Hack unnötig, weil Option B
  nicht viel teurer ist.

### Option B: Logik entkoppeln (Kern als Package, zwei dünne Driver)

Kern-Package (stdlib-rein, gemäß Dependency-Grenze §2):

- Session-Builder: nimmt einen Iterator von (source_label, session_id,
  Zeilen-Objekten) und baut das Session-Modell. Das ist die heutige State-Machine
  aus `parse_session_transcripts()`, minus Discovery.
- Alle Domänenfunktionen unverändert (Signaturen erhalten).
- `build_dashboard_data()` als Aggregations-Einstieg.

Zwei Driver:

- **CLI-Driver** = heutiges `extract_stats.py`: Datei-Discovery, sudo-Quellen,
  `load_*()`-Loader, HTML-Generierung. Bleibt als Entry-Point bestehen, ruft den Kern.
- **Server-Driver** (neue Komponente, darf Dependencies haben): liest Records pro
  Tenant aus Postgres, füttert denselben Kern, materialisiert das Ergebnis.

- Pro: eine Quelle der Wahrheit für die Kalibrierung; Tests zeigen weiter auf den
  Kern; CLI-Tool lebt unverändert weiter; der Server rechnet aus dem verifizierten
  Store.
- Contra: Refactor am Monolithen = genau dort Regressionsrisiko, wo es nicht sein
  darf. Beherrschbar, weil der Schnitt mechanisch ist (I/O raus, Funktionen
  verschieben) und mit Golden-Master abgesichert wird (siehe Abschnitt 4).

### Option C: Voll DB-nativ (Aggregation in SQL, inkrementell beim Ingest)

- Pro: theoretisch beste Skalierung, Queries on demand.
- Contra (K.o.): die Kalibrierung müsste nach SQL portiert werden - 5h-Fenster,
  Limit-Fingerprints, Cache-Flush-Detection und Stream-Merge sind sequenzielle
  State-Machines über Turn-Folgen, in SQL grausam und garantiert regressiv.
  Doppelte Wartung (Python-CLI + SQL-Server) für identische Semantik. Direkter
  Verstoß gegen die erklärte Präferenz. Für das reale Volumen (Dev-Telemetrie,
  einstellige bis niedrige zweistellige Seat-Zahl) völlig überdimensioniert.

---

## 3. Rechenmodell

- **Inkrementell pro Record beim Ingest:** falsch für diesen Kern. Die Logik ist
  sessionweise/fensterweise, nicht record-weise. Record-inkrementelles
  Zustands-Management wäre ein Rewrite durch die Hintertür (= Option C in grün).
- **On-demand-Vollscan pro Dashboard-Hit:** funktioniert anfangs, skaliert aber
  linear mit der (unbegrenzt wachsenden) Historie und verschwendet Arbeit, weil
  sich alte Sessions nie ändern.
- **Empfehlung: inkrementell auf Session-Granularität, materialisiert auf
  Tenant-Ebene.** Die Session ist die natürliche Inkrement-Einheit: fast die
  gesamte Kalibrierung ist intra-session; sessionübergreifend sind nur billige
  Aggregationen (Tagesserien, Plan-Analyse) über per-Session-Summaries.

Konkret:

1. Ingest schreibt append-only und markiert `(tenant, session_id)` dirty.
2. Ein Compute-Schritt (Background-Task mit Debounce ~30-60 s; Cron gleichwertig)
   liest nur die dirty Sessions komplett aus der DB (Session-Rescan ist
   Millisekunden bis Sekunden), baut per-Session-Summaries (JSONB) und rebaut das
   Tenant-Dashboard-JSON aus allen Summaries.
3. Das Dashboard-Frontend bekommt dieses JSON per API statt inline - der
   `noFilter`-Fast-Path des v2-Frontends konsumiert server-vorbereitete Daten
   bereits direkt, das Frontend kann fast unverändert weiterleben.

Ein Session-Rescan statt Record-Inkrement bedeutet: Idempotenz geschenkt
(Re-Ingest, Out-of-Order, Grace-Fenster für `dangling_parent` ändern nichts am
Ergebnis - die Session wird einfach nochmal gerechnet). Materialisierte Postgres-
Views braucht v0 nicht; die Materialisierung ist das Tenant-JSON.

---

## 4. Wie die Kalibrierung erhalten bleibt

1. **Golden-Master vor dem ersten Refactor-Schritt:** heutiges
   `dashboard_data.json` auf den echten lokalen Daten einfrieren (plus die
   bestehenden Fixtures). Nach jedem Refactor-Schritt: Diff muss leer sein (bis
   auf Timestamps). Das ist der Nicht-Regressions-Beweis, nicht "Tests grün".
2. **Mechanischer Schnitt:** Funktionen verschieben, Signaturen erhalten; einzige
   inhaltliche Änderung ist die Trennung Discovery vs. Session-Builder.
3. **E2E-Kalibrierungs-Beweis am Ende:** dieselben JSONL-Daten einmal durchs
   CLI-Tool, einmal durch Agent -> Collector -> Server-Driver. Beide
   Dashboard-JSONs müssen übereinstimmen. Das testet zusätzlich, dass der
   DB-Weg (Ordnung, Dedup, Sidecars) semantisch identisch mit dem Datei-Weg ist.
4. Die bestehenden ~25 Testmodule zeigen weiter auf den Kern; neu dazu kommen nur
   Collector-/Agent-/Verifier-Tests.

---

## 5. Empfehlung und v0-Schnitt

**Option B, mit dem Rechenmodell aus Abschnitt 3.** Kern als stdlib-reines
Package im claude-stats-Repo, CLI-Driver bleibt `extract_stats.py`, Server-Driver
liest aus Postgres, rechnet session-inkrementell, materialisiert pro Tenant.

Bewusst NICHT in v0: Record-inkrementelle Berechnung, SQL-Aggregation,
materialisierte Postgres-Views, Frontend-Umbau über den API-Anschluss hinaus.
Das Rechenmodell darf danach evolvieren (Spec §12 sagt das explizit) - der
Session-Rescan ist der Zustand, aus dem man später am billigsten weiteroptimiert,
weil er keine verteilte Zustandslogik hinterlässt.

### Task-Breakdown (Reihenfolge = Abhängigkeit)

1. **Golden-Master-Harness** - Freeze des heutigen Outputs (real + Fixtures).
2. **Kern-Extraktion** - Package (z.B. `claudestats_core/`): Session-Builder mit
   Zeilen-Iterator-Interface, Domänenfunktionen, `build_dashboard_data`;
   CLI-Driver umstellen; Golden-Master identisch.
3. **Schema-Finalisierung** - uuid-lose Records, `line_index`, Sidecar-Records
   (Entscheidungen unten), dann Payload/Dedup festnageln.
4. **Collector-Server** - `/v1/enroll`, `/v1/ingest`, `/v1/chain/head`,
   `/v1/export`; Postgres-Schema; Chain + Signaturprüfung; WORM-Grants.
5. **Agent** - tail, Offset/uuid-State, Ed25519-Signatur, Batch-Send,
   Subagent-Verzeichnisse + Sidecars.
6. **Verifier-Script** - offline, gegen `/v1/export`, gemeinsame `canon()`.
7. **Server-Compute-Driver** - dirty-marking, Session-Rescan, per-Session-Summary,
   Tenant-JSON, API + minimales Dashboard-Serving hinter Auth.
8. **E2E-Kalibrierungs-Beweis** - CLI vs. Server auf denselben Daten (Abschnitt 4.3).

---

## 6. Entscheidungen (getroffen am 2026-07-06)

1. **uuid-lose Zeilen:** mitshippen mit synthetischem Schlüssel
   `synth:<sha256(session_id || line_index || record_sha256)>`. ENTSCHIEDEN.
2. **`line_index` ins Wrapper-Schema (§4-Ergänzung):** ja, additiv. ENTSCHIEDEN.
3. **Sidecar-Handling:** `agent-*.meta.json` als synthetischer Record
   (`type: "x-meta-sidecar"`). ENTSCHIEDEN.
4. **Repo-Schnitt:** eigenes Collector-Repo ab Tag 1 (Andie-Vorgabe). Der Kern
   wird im claude-stats-Repo als installierbares Package extrahiert
   (`pyproject.toml`); das Collector-Repo pinnt ihn als Git-Dependency auf
   Tag/Commit. Kalibrierungs-Version im Collector damit explizit und auditierbar.
   ENTSCHIEDEN.
5. **Server-Stack (auf Merit-Basis entschieden, nicht nach Bestand):**
   - **Python:** erzwungen durch die Architektur - der Compute-Driver importiert
     den Python-Kern; jede andere Sprache hieße zweite Runtime + IPC ohne Gewinn.
   - **FastAPI:** `/v1/ingest` ist eine Audit-Grenze; strikte Payload-Validierung
     (Pydantic) ist dort inhaltliches Feature. OpenAPI-Spec gratis als formale
     Schnittstelle für Agent und Dritt-Verifier. Flask böte nichts davon,
     Django/DRF ist Overkill, Litestar ebenbürtig ohne Mehrwert.
   - **PostgreSQL + psycopg 3:** WORM braucht rollenbasierte Grants (SQLite: kein
     Rollenmodell, raus). JSONB für `raw`, transaktionale per-Tenant-seq,
     Backup/PITR fürs Langzeit-Archiv. Bestand ist Betriebsbonus, nicht Argument.
   - **`cryptography`** (statt PyNaCl): breiter auditiert, Referenz-Lib.
   - **Transport-Auth: opake Per-Agent-Bearer-Tokens** (gehasht at rest, einzeln
     revozierbar) statt OAuth 2.1 Client-Credentials. OAuth lohnt erst bei
     gemeinsamer Identitäts-Ebene mehrerer Services; Token-Ausgabe bleibt als
     austauschbare Komponente geschnitten, OAuth-Andockung ist Roadmap-Option.
   ENTSCHIEDEN.
6. **Compute-Trigger:** Debounce-on-Ingest. ENTSCHIEDEN.

---

## 6b. Befund aus dem Final-Review von Plan 2 (2026-07-07): Grenzen der Chain ohne Anker

Empirisch bewiesen (Angriffs-Probe im Review): Ein Storage-Betreiber mit
DB-Superuser, aber OHNE Agent-Private-Keys, kann Records aus der Mitte löschen
oder umsortieren und die Chain nachversiegeln - sha256 ohne Geheimnis ist für
jeden nachrechenbar, und die Ed25519-Signatur deckt nur `bind`
(tenant/session/uuid/inhalt), nicht die Position. Der Verifier akzeptiert den
manipulierten Export (rc=0). Was die Signatur hart garantiert: keine
Inhaltsfälschung, keine Record-Fabrikation. Vollständigkeit/Ordnung gegen den
Betreiber braucht einen EXTERNEN Anker - exakt der TSA-/Transparency-Punkt der
Roadmap (§11), also kein neues Loch, aber eine Präzisierung dessen, was v0
schon kauft.

Mitigation in v0 umgesetzt: `tools/verifier.py --expected-head SEQ:CHAIN_HASH` -
ein Auditor, der den Chain-Kopf out-of-band notiert (z.B. regelmäßig
`GET /v1/chain/head` archiviert), erkennt Truncation/Löschung damit HEUTE.

**Vorschlag an Andie (Spec ist dein Dokument, daher nicht still editiert):**
In §5 der Spec ("Was jede Schicht beweist") die Zeilen "Record in der Mitte
gelöscht" und "Records umsortiert" in der Hash-Chain-Spalte mit demselben
Sternchen versehen wie die Betreiber-Zeile ("Chain allein nicht, weil ohne
Geheimnis nachrechenbar - erst mit extern gesichertem Chain-Kopf bzw. TSA").
Die Spec-Fußnote sagt das sinngemäß schon; die Tabellenzellen wenden es nur
nicht konsistent an.

## 7. Änderungsprotokoll

- 2026-07-06: Ursprüngliche Empfehlung in Punkt 4 (Monorepo) von Andie gedreht:
  eigenes Repo ab Tag 1. Punkt 5 neu begründet auf Merit-Basis (Andie-Vorgabe:
  Bestand ist kein Argument); Ergebnis inhaltlich gleich bei Framework/DB, aber
  Transport-Auth von "OAuth-Stack andocken" auf einfache revozierbare
  Bearer-Tokens geändert.
