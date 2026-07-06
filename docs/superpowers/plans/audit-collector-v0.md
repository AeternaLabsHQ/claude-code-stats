# Audit Collector v0 - Build Spec

Verteilte, mandantenfähige, manipulationssichere Telemetrie- und Kosten-Erfassung
für Claude Code. Self-hosted, Aeterna-Muster. Baut auf der bestehenden
`claude-stats`-Domänenlogik (v2: Kosten, Cache-Anomalie, Limits, Per-Tool-
Attribution) auf. Wie diese Logik verpackt und ausgeführt wird (Batch-Skript,
Library, DB-getriebener Service), ist eine **offene** Architektur-Entscheidung,
siehe Abschnitt 10.

Status: Entwurf für v0. Enterprise/GoBD und redigierter Stats-only-Stream sind
bewusst Roadmap, nicht v0.

---

## 1. Ziel und Trust-Modell

Was v0 kaufen soll: ein **vollständiges, geordnetes, manipulations-nachweisbares**
Protokoll dessen, was Claude-Code-Agents auf den Clients tatsächlich getan haben,
zentral eingesammelt und für Kosten/Statistik durch die bestehende Engine auswertbar.

Gegen wen muss das Log verteidigbar sein:

- gegen Dritte (Transport, Storage) -> TLS + Hash-Chain
- gegen den Server-Betreiber selbst -> **Client-seitige Signatur** (der Betreiber
  hat den Private Key nie). Das ist der Punkt, der aus einer Statistik-Sammlung
  ein Audit macht.
- gegen "unauffälliges Weglassen" -> Vollständigkeitsnachweis (parentUuid-DAG +
  monotone seq)

Vertrauensanker: **der Client bezeugt seine eigene Aktivität.** Der Client ist die
Autorität darüber, was er getan hat; der Server ist nur Sammler und Ordner.

Nicht-Ziel in v0: kontrollieren, was ein Agent DARF (Rollen/Identitäts-Governance).
Rein erfassen, was er TUT.

---

## 2. Komponenten

| Komponente | Aufgabe | Dependencies |
|---|---|---|
| **Agent** | tailt lokale `~/.claude/projects/**/*.jsonl`, signiert neue Records, sendet an Collector | Python + eine Krypto-Lib (`cryptography`/PyNaCl) |
| **Collector (Server)** | verifiziert Signatur, dedupliziert, hängt in Hash-Chain, speichert append-only | Server-Framework + Krypto-Lib + DB (PostgreSQL) |
| **Engine (Domänenlogik)** | v2-Rechenkern: Kosten, Cache-Anomalie, Limits, Attribution. Verpackung + Ausführungsmodell offen (Abschnitt 10) | stdlib-fähig |
| **Verifier** | eigenständiges Script: rechnet Chain nach, prüft alle Signaturen, meldet erste Divergenz | Python + Krypto-Lib |

**Dependency-Grenze:** die neue Krypto-Dependency lebt in Agent, Collector und
Verifier. Ob und wie die Domänenlogik stdlib-rein bleibt, hängt an der
Architektur-Entscheidung (Abschnitt 10); der Server-Driver (DB, Web-Framework) darf
ohnehin Dependencies mitbringen, das ist die neue Komponente, nicht das
veröffentlichte Tool.

---

## 3. Datenfluss

```
Client                         Collector                        Dashboard
------                         ---------                        ---------
JSONL append   --tail-->  POST /v1/ingest
  (parentUuid-DAG)          |-- Signatur verifizieren
                            |-- dedup auf record_uuid
                            |-- seq zuweisen (per Tenant, monoton)
                            |-- chain_hash = H(prev || bind || sig)
                            |-- INSERT append-only
                            +-> ack {seq, chain_hash}

                          Store  -->  Domänenlogik  -->  API / HTML
                                       (Architektur offen, Abschnitt 10)
```

Nebeneffekt, der ein bekanntes Problem löst: Claude Code löscht Transcripts >30 Tage
(siehe README `cleanupPeriodDays`). Sobald der Agent sie geschickt hat, ist der
zentrale Store das **dauerhafte Archiv**. Die Ephemeralität der Quelle wird zum
Feature des Collectors, nicht zum Risiko.

---

## 4. Payload-Schema

Der innere Claude-Code-Record wird **verbatim** durchgereicht (Audit = roh). Der
Wrapper fügt nur Identität und Integrität hinzu.

```jsonc
{
  "agent_id":     "agt_7f3c...",          // vom Enrollment vergeben
  "pubkey_id":    "ed25519:ab12...",      // Fingerprint des Agent-Pubkeys
  "tenant":       "aeternalabs",
  "seat": {
    "machine":      "cortex",
    "os_user":      "andie",
    "source_label": "cortex:andie"        // = dein bestehendes source_label-Konzept
  },
  "session_id":   "<aus JSONL>",
  "record_uuid":  "<aus JSONL: uuid>",    // FELDNAME an echtem JSONL verifizieren
  "parent_uuid":  "<aus JSONL: parentUuid | null>",
  "captured_at":  "2026-07-06T12:00:00Z", // wann der Agent versandt hat
  "record_sha256":"<hex>",                // = sha256(canon(raw))
  "sig":          "<base64 ed25519>",     // Signatur ueber 'bind' (s. u.)
  "raw":          { /* JSONL-Zeile als Objekt, unveraendert */ }
}
```

`/v1/ingest` nimmt ein **Batch** solcher Records (Array), damit der Hot Path
effizient bleibt. Volumen ist niedrig (Dev-Telemetrie), Signatur pro Record ist
vertretbar; Batch-Merkle-Root ist Optimierung für später (Roadmap).

### Kanonisierung (der klassische Footgun)

Chain und Signatur sind nur reproduzierbar, wenn Agent, Server und Verifier
**exakt dieselbe** Serialisierung hashen:

```python
def canon(obj) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

record_sha256 = sha256(canon(raw)).hexdigest()
```

An einer Stelle definieren, aus Agent + Server + Verifier importieren. Nie
kopieren.

---

## 5. Integritäts-Design (drei Schichten)

### 5.1 parentUuid-DAG (nativ, kostenlos)

Jeder Claude-Code-Record zeigt per `parentUuid` auf seinen Vorgänger. Ein
fehlender Record hinterlässt ein hängendes `parentUuid`. Der Server prüft pro
Session, ob die DAG-Kette lückenlos ist. Das ist Intra-Session-Vollständigkeit
ohne eigene Krypto.

### 5.2 Per-Tenant-Hash-Chain (Manipulation + Reihenfolge)

Append-only. Jeder gespeicherte Record bekommt:

```
bind        = sha256(  utf8(tenant)      + 0x00
                     + utf8(session_id)  + 0x00
                     + utf8(record_uuid) + 0x00
                     + record_sha256 )                  # Kontext-Bindung
                                                         # verhindert Relocation/Replay
                                                         # in andere Tenants/Sessions

seq         = <monoton, pro Tenant>
prev_hash   = <chain_hash von seq-1, bzw. GENESIS>
chain_hash  = sha256( utf8(prev_hash) + 0x00
                    + utf8(bind)       + 0x00
                    + utf8(pubkey_id)  + 0x00
                    + utf8(sig) )
```

Jede nachträgliche Änderung, Löschung oder Umsortierung bricht die Kette ab dem
betroffenen Punkt. `GET /v1/chain/head` gibt den aktuellen Kopf zurück.

### 5.3 Ed25519-Agent-Signatur (gegen den Betreiber)

Der Agent signiert `bind` mit seinem Private Key. Der Server verifiziert gegen den
beim Enrollment registrierten Public Key und speichert die Signatur mit. Weil der
Server den Private Key nicht besitzt, kann er keinen Record fälschen oder ändern,
ohne dass die Signatur ungültig wird.

**Warum nicht HMAC:** HMAC ist symmetrisch, der Server müsste den Schlüssel kennen
und könnte damit selbst fälschen. Für "Audit gegen den Betreiber" ist asymmetrisch
Pflicht.

### Was jede Schicht beweist

| Angriff | parentUuid | Hash-Chain | Signatur |
|---|---|---|---|
| Record inhaltlich verändert | - | ja | ja |
| Record in der Mitte gelöscht | ja (Session) | ja | - |
| Records umsortiert | - | ja | - |
| Record in fremden Tenant/Session verschoben | - | ja (bind) | ja (bind) |
| Betreiber fälscht/ändert nachträglich | - | nein* | **ja** |

\* Chain allein nicht, weil ohne Geheimnis nachrechenbar. Erst die Signatur (5.3)
und später TSA (Roadmap) schließen das.

---

## 6. Endpunkte

Klein, REST, self-hostable.

| Methode | Pfad | Zweck |
|---|---|---|
| `POST` | `/v1/enroll` | Enrollment-Token -> Agent-Credentials; registriert Agent-Pubkey. Admin-gated. |
| `POST` | `/v1/ingest` | Hot Path. Batch signierter Records. Idempotent (dedup auf record_uuid). |
| `GET`  | `/v1/chain/head` | aktueller Chain-Kopf `{seq, chain_hash, ts}` pro Tenant (Monitoring/Verify) |
| `GET`  | `/v1/export` | Records fuer Tenant/Zeitraum dumpen (Engine-Input + Auditor-Export) |

### `/v1/ingest` Response (pro Record im Batch)

```jsonc
{ "record_uuid": "...",
  "status":      "accepted" | "duplicate" | "rejected",
  "seq":         12345,
  "prev_hash":   "...",
  "chain_hash":  "...",
  "reason":      "bad_signature | dangling_parent | ..." }  // nur bei rejected
```

Verifier ist ein **eigenständiges Script**, kein Endpunkt: es lädt via `/v1/export`,
rechnet die Chain mit derselben `canon()` nach und verifiziert jede Signatur gegen
die enrollten Pubkeys. Meldet die erste Divergenz. Dass ein Dritter das offline
reproduzieren kann, ist genau das, was das Log glaubwürdig macht.

---

## 7. Auth

Zwei getrennte Belange, nicht vermischen:

- **Transport-Auth (wer darf posten):** Bearer-Token pro Agent, revozierbar.
  Wenn du deinen bestehenden OAuth-Stack (PullMD/Scripta) wiederverwenden willst:
  OAuth 2.1 **Client-Credentials-Grant** statt rohem API-Key. Interaktiver
  Flow ist für Maschinen falsch, Client-Credentials ist der richtige.
- **Content-Attestierung (was wurde bezeugt):** Ed25519-Signatur pro Record.
  Non-repudiable, unabhängig vom Transport-Token.

Der Transport-Token ist widerrufbar (kompromittierter Agent), ohne die bereits
signierten Records ungültig zu machen. Genau deshalb getrennt.

### Enrollment-Flow

```
1. Admin erzeugt im Server-UI einen einmaligen Enrollment-Token (kurzlebig).
2. Agent startet, generiert LOKAL ein Ed25519-Keypair.
3. Agent -> POST /v1/enroll { enrollment_token, pubkey, machine, os_user }
4. Server: validiert Token, registriert pubkey, vergibt agent_id + Transport-Token.
5. Private Key bleibt auf dem Client. Verlaesst ihn nie.
```

---

## 8. Idempotenz und Vollständigkeit

- **Dedup:** Schlüssel ist `record_uuid` (aus JSONL). Der Agent darf/wird bei
  Retry/Neustart überlappend senden; der Server nimmt jeden uuid genau einmal
  in die Chain. Doppelte Token-Zählung ist ein Audit-Killer.
- **Agent-State:** kleine lokale SQLite/JSON pro Datei:
  `{inode, size, last_offset, last_uuid}`. Fast Path über Offset, Sicherheitsnetz
  über uuid-Dedup serverseitig. Inode-Wechsel erkennt Rotation/Ersetzung.
- **seq:** serverseitig monoton pro Tenant -> lückenlose Gesamtordnung.
- **parentUuid-Gap:** Server meldet `dangling_parent`, wenn ein referenzierter
  Vorgänger (noch) fehlt (kann bei Out-of-Order-Batch temporär sein -> Grace-Fenster).

---

## 9. Storage und WORM

- **Transport:** TLS Pflicht. Roh-JSONL enthält Code, Pfade, evtl. Secrets,
  Memories (deine eigene README warnt davor). In Roh-Audit-Modus ist F2/
  `--no-memories` client-seitig AUS - ein redigiertes Audit-Log ist kein
  vollständiges Audit-Log.
- **At Rest:** mindestens Disk-/DB-Verschlüsselung in v0. App-Level-Feldverschlüsselung
  der `raw`-Payload ist Roadmap. Wichtig: die Chain hasht den **Klartext**
  (`record_sha256` über `canon(raw)`), damit Integrität unabhängig von
  Storage-Key-Rotation bleibt. Ciphertext + Klartext-Hash speichern.
- **DB-WORM:** App-Rolle bekommt nur `INSERT` auf die Ingest-Tabelle, `UPDATE`/
  `DELETE` werden entzogen. Defense in Depth zusätzlich zur Chain.

---

## 10. Kern-Architektur (offene Analyse)

Bewusst NICHT vorbeantwortet. Das ist die eigentliche Architektur-Analyse und
gehört an das stärkere Modell (Fable), nicht in diese Spec. Hier stehen nur die
Fakten und die Frage, keine Empfehlung.

**Fakten:**

- Heutiger Ausführungsmodus: `extract_stats.py` walkt alle Dateien, rechnet die
  komplette Historie neu, erzeugt statisches HTML. Das Frontend baut in
  `filterData()` die Serien client-seitig aus den Sessions neu auf.
- Dieser Modus ist auf einen lokalen Single-User zugeschnitten. Für einen
  mandantenfähigen Server, der über Monate Records vieler Seats sammelt, sind
  sowohl der periodische Vollscan als auch das client-seitige Neurechnen fraglich
  (Datenmenge passt nicht mehr in den Browser, Vollscan-Kosten wachsen mit der
  Historie).
- Die Domänenlogik (Kosten-Mapping, Cache-Anomalie-Erkennung, Limit-Fingerprints,
  Per-Tool-Attribution) ist teuer kalibriert: mehrere Umschreibungen der
  Limit-Mathematik, cache_write_1h-Sonderfall, Char-Heuristik. Andies erklärte
  Präferenz ist, diese Kalibrierung nicht zu regressieren.
- Postgres liegt bereits im Stack (OpenBrain, pgvector).
- Das lokale CLI/Single-User-Tool soll weiter existieren.

**Zu analysieren:**

- Wie sollte der Kern strukturiert werden, wenn er vom lokalen Batch-Tool zum
  mandantenfähigen Server + DB wird? Skript beibehalten und wrappen, Logik
  entkoppeln und teilen, voll DB-nativ (ingest -> compute -> serve), oder etwas
  dazwischen?
- Rechenmodell: inkrementell beim Ingest, Aggregations-Query on demand,
  materialisierte Views, Kombination?
- Wie bleibt die bestehende Kalibrierung erhalten, während sich der
  Ausführungsmodus ändert, und wie verhält sich das zum lokalen CLI-Tool?

**Deliverable:** eine begründete Architektur-Empfehlung mit Optionen, Trade-offs
und einem klaren v0-Schnitt. Analysieren und entscheiden lassen, nicht raten.

---

## 11. Roadmap (bewusst NICHT v0)

- **RFC 3161 Timestamping** des Chain-Heads (stündlich/täglich an eine TSA).
  Beweist "dieser Zustand existierte zu Zeit T, nicht rückdatiert". Der ehrliche
  Baustein hinter dem Wort revisionssicher. ~halber Tag.
- **Transparency-Anchoring:** Chain-Head zusätzlich in ein append-only Ziel
  außerhalb deiner Kontrolle spiegeln (Git-Commit, öffentliches Log).
- **Stats-only-Modus:** separater, redigierter Stream (deine Entscheidung 1).
  Eigener Stream, kein Filter auf dem Audit-Stream.
- **Batch-Merkle-Root + Signed Tree Head** statt Signatur pro Record, falls
  Volumen es je verlangt.
- **GoBD/Enterprise:** Zertifizierungs-nahe Ausbaustufe. Erst wenn ein zahlender
  Kunde es verlangt, nicht auf Verdacht.

---

## 12. Der v0-Schnitt (Scope-Zaun)

**In v0:**

- Agent: tailt JSONL, hält lokalen Offset/uuid-State, signiert (Ed25519), sendet Batch
- Collector: `/v1/enroll`, `/v1/ingest`, `/v1/chain/head`, `/v1/export`
- Integrität: parentUuid-Check + Per-Tenant-Hash-Chain + Ed25519-Signatur
- Storage: append-only, DB-WORM-Grants, Disk-/DB-Encryption, TLS
- Auth: Enrollment -> Transport-Token (oder OAuth Client-Credentials) + Content-Signatur
- Verifier-Script (offline reproduzierbar)
- Kern-Architektur gemäß Analyse (Abschnitt 10) entschieden und umgesetzt; Server-Driver liest aus dem Store

**Nicht in v0 (Roadmap):** TSA-Timestamping, Transparency-Anchoring, Stats-only-Stream,
App-Level-Feldverschlüsselung, Merkle/STH, GoBD-Zertifizierung.

**Vorbedingung:** die Kern-Architektur-Analyse aus Abschnitt 10 treffen
(idealerweise mit Fable), BEVOR der Collector gebaut wird. Erst diese Analyse und
die Kern-Entscheidung, dann der Server drumherum. Das genaue Server-Rechenmodell
(inkrementell / Query / materialisierte Views) darf danach noch evolvieren.
