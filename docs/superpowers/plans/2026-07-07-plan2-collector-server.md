# Plan 2: Collector-Server + Verifier (`audit-collector`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das neue Repo `audit-collector` mit dem mandantenfähigen, manipulations-
nachweisbaren Ingest-Server (enroll/ingest/chain-head/export), Postgres-Storage
mit WORM-Grants und dem offline reproduzierbaren Verifier-Script - gemäß Spec
`audit-collector-v0.md` §1-§9 und der freigegebenen Architektur
(`audit-collector-v0-architektur.md`, Abschnitt 6).

**Architecture:** FastAPI (sync) + psycopg 3 auf einer repo-eigenen Postgres-17-
Instanz (docker-compose, Port 5433). Append-only `records`-Tabelle mit
per-Tenant-Hash-Chain; seq-Vergabe serialisiert über row-lock auf
`tenant_heads`. Ed25519-Client-Signaturen werden serverseitig gegen enrollte
Pubkeys verifiziert; Transport-Auth über opake, gehashte, revozierbare
Bearer-Tokens. Kanonisierung/Chain/Krypto leben in EINEM Modul-Satz
(`collector/canon.py`, `chain.py`, `crypto.py`), aus dem Server, Verifier und
später der Agent (Plan 3) importieren. Der Verifier lädt `/v1/export` (JSONL)
und rechnet Chain + Signaturen + parentUuid-DAG offline nach.

**Tech Stack:** Python >= 3.10, FastAPI, uvicorn, psycopg[binary] 3, pydantic 2,
cryptography (Ed25519), pytest + httpx (TestClient), Docker Compose
(postgres:17-alpine). Kein Alembic in v0 (ein Schema-File, append-only Domäne).

## Global Constraints

- **Repo:** `/home/andie/projects/audit-collector`, frisches git-Repo, Branch
  `main`. NIEMALS pushen (kein Remote in v0). Der Name ist Andies Vorschlag
  zur Bestätigung; Umbenennen ist trivial (Verzeichnis + pyproject.name).
- **Niemals committen:** `.env` (Secrets), `*.key`, Datenbank-Volumes.
  `.gitignore` deckt das ab Task 1 ab.
- **Krypto-/Format-GESETZ** (Agent, Server, Verifier und Dritt-Implementierungen
  rechnen exakt so, Abweichung = Chain-Bruch):
  - `canon(obj) = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`
  - `record_sha256 = sha256(canon(raw)).hexdigest()` (lowercase hex)
  - `bind_hex = sha256(utf8(tenant) || 0x00 || utf8(session_id) || 0x00 || utf8(record_uuid) || 0x00 || utf8(record_sha256)).hexdigest()`
  - `sig_b64 = base64(Ed25519_sign(privkey, ascii(bind_hex)))` - signiert wird
    der ASCII-Hex-String, nicht die Rohbytes
  - `chain_hash = sha256(utf8(prev_chain_hash) || 0x00 || utf8(bind_hex) || 0x00 || utf8(pubkey_id) || 0x00 || utf8(sig_b64)).hexdigest()`;
    `prev_chain_hash` des ersten Records eines Tenants = Literal `"GENESIS"`; `seq` beginnt bei 1
  - `pubkey_id = "ed25519:" + sha256(raw_pubkey_32bytes).hexdigest()[:16]`
- **Referenz-Testvektoren** (mit CPython 3 + cryptography 41 berechnet; Tests
  aus Task 2 MÜSSEN exakt diese Werte reproduzieren):
  - raw = `{"type": "user", "uuid": "11111111-2222-3333-4444-555555555555", "parentUuid": None, "sessionId": "aaaabbbb-cccc-dddd-eeee-ffff00001111", "message": {"role": "user", "content": "Testvektor: ümlaut & 🎯"}}`
  - `len(canon(raw)) == 195`
  - `record_sha256 == "e4837f558dbf8eb95287c2fdaee928f8c3c617f5b9e21e27eeaff50bbdfe4002"`
  - bind für tenant=`aeternalabs`, session_id/record_uuid wie in raw:
    `bind_hex == "baebfb47bbb95ede0c63e07fe7b53cdcc343bbea6e5104fc08abb42a46122e71"`
  - chain für prev=`GENESIS`, pubkey_id=`ed25519:abababababababab`, sig_b64=`PLACEHOLDER`:
    `chain_hash == "bf4937fcf44c3ce43a3629b8be8a5bd645004a78631622de3123607562fbf035"`
  - Ed25519-Seed `bytes(range(32))` ->
    `pubkey_b64 == "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="`,
    `pubkey_id == "ed25519:56475aa75463474c"`,
    Signatur über ascii des obigen Test-bind-Strings
    `"e59f9c7d4c0a2e9b0000000000000000000000000000000000000000000000ff"` ->
    `sig_b64 == "JSmcG01WP8ClU6CKnnf0jxa/ClqNgo7Aq7Lmjxnw5HaEMA/7wh4tRWQpRqlA8Qh5e1DHRN7OY+1QUwMQ0GebDQ=="`
- **WORM:** Die App-Rolle `collector_app` hat auf `records` nur INSERT+SELECT,
  kein UPDATE/DELETE/TRUNCATE. Mutierbar sind nur `tenants`, `agents`,
  `enrollment_tokens`, `tenant_heads`. Ein Test beweist die Verweigerung.
- **TLS ist v0-out-of-scope im Server:** Der Server bindet auf 127.0.0.1;
  TLS terminiert der vorhandene Reverse-Proxy (Caddy). Im README dokumentieren.
- **Wrapper-Schema** = Spec §4 PLUS die entschiedenen Ergänzungen
  (Architektur-Doc Abschnitt 6): `line_index` (int >= 1, Zeilennummer in der
  Quelldatei), uuid-lose Zeilen kommen mit synthetischem
  `record_uuid = "synth:" + sha256(session_id || ":" || line_index || ":" || record_sha256).hexdigest()`
  (erzeugt der Agent, Plan 3 - der Server behandelt record_uuid als opakes,
  pro Tenant eindeutiges Feld), Sidecars als `type: "x-meta-sidecar"`-Records.
- **DB nur über Docker:** Auf dem Host gibt es kein psql. Alle SQL-Kommandos
  laufen als `docker exec -i audit-collector-db psql -U postgres -d <db> ...`.
  Port 5433 (5432 ist von yt-chronicle belegt).
- **Tests laufen gegen echtes Postgres** (Datenbank `audit_test`, wird pro
  Testlauf geleert). Keine DB-Mocks - das WORM-/Locking-/Dedup-Verhalten IST
  der Prüfgegenstand.
- Nach jedem Task: `python3 -m pytest tests/ -q` grün. Frequent commits gemäß
  Task-Steps.

## File Structure

```
audit-collector/
  pyproject.toml            # Package collector + tools, deps
  docker-compose.yml        # postgres:17-alpine, Port 5433, Volume
  .env.example              # DATABASE_URL, ADMIN_TOKEN (Beispielwerte)
  .gitignore
  README.md
  sql/001_schema.sql        # Tabellen, Rollen, WORM-Grants
  collector/__init__.py
  collector/canon.py        # canon(), record_sha256_hex()   (das GESETZ)
  collector/chain.py        # bind_hex(), chain_hash_hex(), GENESIS
  collector/crypto.py       # keygen, sign/verify, pubkey_id, b64-Helfer
  collector/settings.py     # Env-Konfig (DATABASE_URL, ADMIN_TOKEN)
  collector/db.py           # Pool, Head-Lock, Batch-Insert, Dedup, Queries
  collector/models.py       # Pydantic: WrapperRecord, IngestResponse, ...
  collector/auth.py         # Token mint/hash/lookup, Enrollment-Logik
  collector/app.py          # FastAPI: /v1/enroll /v1/ingest /v1/chain/head /v1/export
  tools/mint_enrollment_token.py   # Admin-CLI (statt Server-UI, v0)
  tools/verifier.py         # Standalone-Offline-Verifier
  tests/conftest.py         # DB-Reset-Fixture, TestClient, Testkeys
  tests/test_canon_chain_crypto.py
  tests/test_db_worm_and_chain.py
  tests/test_enroll_auth.py
  tests/test_ingest.py
  tests/test_export_verifier.py
```

Verantwortungen: `canon/chain/crypto` sind reine Funktionen ohne I/O (werden
in Plan 3 vom Agent importiert bzw. für den Agent kopiert/gepinnt). `db.py`
kapselt ALLE SQL-Zugriffe. `app.py` enthält nur HTTP-Verdrahtung + Statuscodes,
keine Domänenlogik.

---

### Task 1: Repo-Bootstrap, Docker-Postgres, Schema, WORM-Grants

**Files:**
- Create: `pyproject.toml`, `docker-compose.yml`, `.env.example`, `.gitignore`,
  `README.md`, `sql/001_schema.sql`, `collector/__init__.py`,
  `collector/settings.py`, `tests/conftest.py`, `tests/test_db_worm_and_chain.py`
  (nur der WORM-Teil; Chain-Teil kommt in Task 3)

**Interfaces:**
- Produces: laufende DB `audit` + `audit_test` auf `localhost:5433`; Rolle
  `collector_app` (Login, WORM-beschränkt); `collector.settings.SETTINGS`
  mit `database_url`, `admin_token`; pytest-Fixture `db` (geleerte Test-DB,
  psycopg-Connection) und `superuser_db` (postgres-Connection für Tamper-Tests).

- [ ] **Step 1: Verzeichnis + git init**

```bash
mkdir -p /home/andie/projects/audit-collector && cd /home/andie/projects/audit-collector
git init -b main
```

- [ ] **Step 2: Projektdateien anlegen**

`.gitignore`:

```
__pycache__/
*.egg-info/
.env
*.key
.pytest_cache/
.venv/
```

`.env.example`:

```
DATABASE_URL=postgresql://collector_app:collector_dev_pw@localhost:5433/audit
DATABASE_URL_TEST=postgresql://collector_app:collector_dev_pw@localhost:5433/audit_test
DATABASE_URL_SUPER=postgresql://postgres:audit_dev_root_pw@localhost:5433/audit_test
ADMIN_TOKEN=change-me-admin-token
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:17-alpine
    container_name: audit-collector-db
    environment:
      POSTGRES_PASSWORD: audit_dev_root_pw
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - audit_pgdata:/var/lib/postgresql/data
volumes:
  audit_pgdata:
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "audit-collector"
version = "0.1.0"
description = "Mandantenfaehiger, manipulations-nachweisbarer Telemetrie-Collector fuer Claude Code (Audit Collector v0)"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.110",
  "uvicorn>=0.29",
  "psycopg[binary]>=3.1",
  "pydantic>=2.6",
  "cryptography>=41",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]

[tool.setuptools]
packages = ["collector"]
```

`collector/__init__.py`: leer (nur Docstring `"""Audit Collector v0."""`).

`collector/settings.py`:

```python
"""Env-Konfiguration. Alle Secrets kommen aus der Umgebung/.env, nie aus Code."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_token: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        admin_token=os.environ["ADMIN_TOKEN"],
    )
```

`README.md` (Kurzform, wird in Task 6 vervollständigt):

```markdown
# audit-collector

Mandantenfähige, manipulations-nachweisbare Telemetrie-Erfassung für
Claude Code (Audit Collector v0). Spec und Architektur: siehe
claude-stats-Repo, docs/superpowers/plans/audit-collector-v0*.md.

## Dev-Setup

    docker compose up -d
    docker exec -i audit-collector-db psql -U postgres < sql/001_schema.sql
    cp .env.example .env   # Werte anpassen
    python3 -m venv .venv && .venv/bin/pip install -e .[dev]
    .venv/bin/pytest tests/ -q

Der Server bindet auf 127.0.0.1 (TLS terminiert der Reverse-Proxy).
```

- [ ] **Step 3: Schema schreiben**

`sql/001_schema.sql`:

```sql
-- Audit Collector v0 Schema. Append-only Kern: records.
-- Idempotent genug fuer Dev: DROP-frei, IF NOT EXISTS wo moeglich.

\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE audit' WHERE NOT EXISTS
  (SELECT FROM pg_database WHERE datname = 'audit') \gexec
SELECT 'CREATE DATABASE audit_test' WHERE NOT EXISTS
  (SELECT FROM pg_database WHERE datname = 'audit_test') \gexec

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'collector_app') THEN
    CREATE ROLE collector_app LOGIN PASSWORD 'collector_dev_pw';
  END IF;
END $$;

\connect audit
\i /dev/stdin
-- (Der Tabellen-Block unten wird per Shell zweimal eingespielt: audit + audit_test.
--  Siehe Step 4; dieser \i-Trick entfaellt dort, der Block steht in 002_tables.sql.)
```

Da `\connect` + Wiederholung über zwei DBs im Single-File unhandlich ist:
**zwei Dateien**. `sql/001_schema.sql` enthält NUR den DB/Rollen-Teil oben
(ohne die letzten zwei Zeilen `\connect`/`\i`), und `sql/002_tables.sql`:

```sql
-- Tabellen + Grants. Wird in JEDE der beiden DBs eingespielt (audit, audit_test).
\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS tenants (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enrollment_tokens (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  BIGINT NOT NULL REFERENCES tenants(id),
  token_hash TEXT NOT NULL UNIQUE,          -- sha256-hex des Klartext-Tokens
  expires_at TIMESTAMPTZ NOT NULL,
  used_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agents (
  id                   TEXT PRIMARY KEY,     -- "agt_<hex>"
  tenant_id            BIGINT NOT NULL REFERENCES tenants(id),
  pubkey_b64           TEXT NOT NULL,        -- raw 32 bytes, base64
  pubkey_id            TEXT NOT NULL UNIQUE, -- "ed25519:<16 hex>"
  machine              TEXT NOT NULL DEFAULT '',
  os_user              TEXT NOT NULL DEFAULT '',
  source_label         TEXT NOT NULL DEFAULT '',
  transport_token_hash TEXT NOT NULL UNIQUE, -- sha256-hex
  revoked_at           TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_heads (
  tenant_id  BIGINT PRIMARY KEY REFERENCES tenants(id),
  last_seq   BIGINT NOT NULL DEFAULT 0,
  chain_hash TEXT   NOT NULL DEFAULT 'GENESIS',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS records (
  tenant_id     BIGINT NOT NULL REFERENCES tenants(id),
  seq           BIGINT NOT NULL,
  agent_id      TEXT   NOT NULL REFERENCES agents(id),
  session_id    TEXT   NOT NULL,
  record_uuid   TEXT   NOT NULL,
  parent_uuid   TEXT,
  line_index    INTEGER NOT NULL,
  captured_at   TIMESTAMPTZ NOT NULL,
  record_sha256 TEXT NOT NULL,
  bind_hex      TEXT NOT NULL,
  sig_b64       TEXT NOT NULL,
  pubkey_id     TEXT NOT NULL,
  prev_hash     TEXT NOT NULL,
  chain_hash    TEXT NOT NULL,
  raw           JSONB NOT NULL,
  received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, seq),
  UNIQUE (tenant_id, record_uuid)
);
CREATE INDEX IF NOT EXISTS records_session_idx
  ON records (tenant_id, session_id, record_uuid);

-- WORM: App-Rolle darf records nur anfuegen und lesen.
GRANT CONNECT ON DATABASE audit TO collector_app;
GRANT USAGE ON SCHEMA public TO collector_app;
GRANT SELECT, INSERT ON records TO collector_app;
GRANT SELECT, INSERT, UPDATE ON tenants, enrollment_tokens, agents, tenant_heads TO collector_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO collector_app;
REVOKE UPDATE, DELETE, TRUNCATE ON records FROM collector_app;
```

(Die `GRANT CONNECT ... audit`-Zeile schlägt in `audit_test` fehl - deshalb
im Einspiel-Kommando für audit_test per `-v dbname=audit_test` ...; einfacher:
die GRANT-CONNECT-Zeile weglassen und stattdessen in `001_schema.sql`:
`GRANT CONNECT ON DATABASE audit, audit_test TO collector_app;` nach dem
Rollen-Block. So umsetzen.)

- [ ] **Step 4: DB hochfahren + Schema einspielen**

```bash
docker compose up -d
sleep 3
docker exec -i audit-collector-db psql -U postgres < sql/001_schema.sql
docker exec -i audit-collector-db psql -U postgres -d audit      < sql/002_tables.sql
docker exec -i audit-collector-db psql -U postgres -d audit_test < sql/002_tables.sql
```

Expected: keine Fehler; `docker exec -i audit-collector-db psql -U postgres -d audit -c "\dt"` zeigt die 5 Tabellen.

- [ ] **Step 5: venv + Install**

```bash
python3 -m venv .venv && .venv/bin/pip install -e .[dev]
```

- [ ] **Step 6: Failing WORM-Test schreiben**

`tests/conftest.py`:

```python
import os
import psycopg
import pytest

TEST_URL = os.environ.get(
    "DATABASE_URL_TEST",
    "postgresql://collector_app:collector_dev_pw@localhost:5433/audit_test",
)
SUPER_URL = os.environ.get(
    "DATABASE_URL_SUPER",
    "postgresql://postgres:audit_dev_root_pw@localhost:5433/audit_test",
)

TABLES = ["records", "tenant_heads", "agents", "enrollment_tokens", "tenants"]


@pytest.fixture()
def superuser_db():
    with psycopg.connect(SUPER_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture()
def db(superuser_db):
    # Reset als Superuser (App-Rolle DARF records nicht loeschen - by design)
    for t in TABLES:
        superuser_db.execute(f"DELETE FROM {t}")
    with psycopg.connect(TEST_URL, autocommit=False) as conn:
        yield conn
```

`tests/test_db_worm_and_chain.py` (erster Teil):

```python
import psycopg
import pytest


def _mk_tenant_agent(superuser_db):
    tid = superuser_db.execute(
        "INSERT INTO tenants (name) VALUES ('t1') RETURNING id").fetchone()[0]
    superuser_db.execute(
        "INSERT INTO agents (id, tenant_id, pubkey_b64, pubkey_id, transport_token_hash)"
        " VALUES ('agt_x', %s, 'pk', 'ed25519:0000000000000000', 'th')", (tid,))
    return tid


def _insert_record(conn, tid, seq, uuid):
    conn.execute(
        "INSERT INTO records (tenant_id, seq, agent_id, session_id, record_uuid,"
        " line_index, captured_at, record_sha256, bind_hex, sig_b64, pubkey_id,"
        " prev_hash, chain_hash, raw)"
        " VALUES (%s, %s, 'agt_x', 's1', %s, 1, now(), 'r', 'b', 'sig',"
        " 'ed25519:0000000000000000', 'GENESIS', 'c', '{}')",
        (tid, seq, uuid))


def test_app_role_cannot_update_or_delete_records(db, superuser_db):
    tid = _mk_tenant_agent(superuser_db)
    _insert_record(db, tid, 1, 'u1')
    db.commit()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("UPDATE records SET raw = '{\"x\":1}' WHERE seq = 1")
    db.rollback()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("DELETE FROM records WHERE seq = 1")
    db.rollback()


def test_record_uuid_unique_per_tenant(db, superuser_db):
    tid = _mk_tenant_agent(superuser_db)
    _insert_record(db, tid, 1, 'u1')
    db.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_record(db, tid, 2, 'u1')
    db.rollback()
```

- [ ] **Step 7: Tests laufen lassen**

Run: `.venv/bin/pytest tests/ -q`
Expected: 2 passed (die Grants aus Step 3/4 machen sie grün; falls
InsufficientPrivilege NICHT kommt, sind die REVOKEs kaputt -> Schema fixen,
nicht den Test).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: repo bootstrap - docker postgres, schema, WORM grants, settings"
```

---

### Task 2: canon / chain / crypto (das Format-Gesetz, TDD gegen Referenzvektoren)

**Files:**
- Create: `collector/canon.py`, `collector/chain.py`, `collector/crypto.py`
- Test: `tests/test_canon_chain_crypto.py`

**Interfaces:**
- Produces (von db/app/verifier/Agent konsumiert):
  - `canon(obj) -> bytes`; `record_sha256_hex(raw: dict) -> str`
  - `bind_hex(tenant: str, session_id: str, record_uuid: str, record_sha256: str) -> str`
  - `chain_hash_hex(prev_hash: str, bind_hex_val: str, pubkey_id: str, sig_b64: str) -> str`; `GENESIS = "GENESIS"`
  - `generate_keypair() -> tuple[bytes, bytes]` (priv_raw32, pub_raw32),
    `sign_bind(priv_raw32: bytes, bind_hex_val: str) -> str` (sig_b64),
    `verify_bind(pub_raw32: bytes, bind_hex_val: str, sig_b64: str) -> bool`,
    `pubkey_id_from_raw(pub_raw32: bytes) -> str`,
    `b64e(b: bytes) -> str`, `b64d(s: str) -> bytes`

- [ ] **Step 1: Failing Tests mit den Referenzvektoren aus den Global Constraints**

`tests/test_canon_chain_crypto.py`:

```python
import base64

from collector.canon import canon, record_sha256_hex
from collector.chain import GENESIS, bind_hex, chain_hash_hex
from collector.crypto import (b64d, b64e, generate_keypair,
                              pubkey_id_from_raw, sign_bind, verify_bind)

RAW = {"type": "user", "uuid": "11111111-2222-3333-4444-555555555555",
       "parentUuid": None, "sessionId": "aaaabbbb-cccc-dddd-eeee-ffff00001111",
       "message": {"role": "user", "content": "Testvektor: ümlaut & 🎯"}}


def test_canon_reference_vector():
    c = canon(RAW)
    assert len(c) == 195
    assert record_sha256_hex(RAW) == \
        "e4837f558dbf8eb95287c2fdaee928f8c3c617f5b9e21e27eeaff50bbdfe4002"


def test_bind_reference_vector():
    assert bind_hex("aeternalabs", RAW["sessionId"], RAW["uuid"],
                    record_sha256_hex(RAW)) == \
        "baebfb47bbb95ede0c63e07fe7b53cdcc343bbea6e5104fc08abb42a46122e71"


def test_chain_reference_vector():
    assert chain_hash_hex(GENESIS,
        "baebfb47bbb95ede0c63e07fe7b53cdcc343bbea6e5104fc08abb42a46122e71",
        "ed25519:abababababababab", "PLACEHOLDER") == \
        "bf4937fcf44c3ce43a3629b8be8a5bd645004a78631622de3123607562fbf035"


def test_ed25519_reference_vector():
    seed = bytes(range(32))
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert b64e(pub) == "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="
    assert pubkey_id_from_raw(pub) == "ed25519:56475aa75463474c"
    bind = "e59f9c7d4c0a2e9b0000000000000000000000000000000000000000000000ff"
    sig = sign_bind(seed, bind)
    assert sig == ("JSmcG01WP8ClU6CKnnf0jxa/ClqNgo7Aq7Lmjxnw5HaEMA/7wh4tRWQpRqlA8Qh5"
                   "e1DHRN7OY+1QUwMQ0GebDQ==")
    assert verify_bind(pub, bind, sig)
    assert not verify_bind(pub, bind.replace("f", "0"), sig)


def test_keypair_roundtrip():
    priv, pub = generate_keypair()
    assert len(priv) == 32 and len(pub) == 32
    sig = sign_bind(priv, "00" * 32)
    assert verify_bind(pub, "00" * 32, sig)
    assert b64d(b64e(pub)) == pub
```

Run: `.venv/bin/pytest tests/test_canon_chain_crypto.py -q`
Expected: FAIL (ModuleNotFoundError collector.canon)

- [ ] **Step 2: Implementieren**

`collector/canon.py`:

```python
"""Kanonisierung - der klassische Footgun (Spec §4).

EINE Definition fuer Agent, Server, Verifier. Nie kopieren, immer importieren
(der Agent in Plan 3 pinnt dieses Repo als Dependency oder vendored exakt
diese Datei mit Versions-Hash).
"""
import hashlib
import json


def canon(obj) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def record_sha256_hex(raw: dict) -> str:
    return hashlib.sha256(canon(raw)).hexdigest()
```

`collector/chain.py`:

```python
"""Per-Tenant-Hash-Chain (Spec §5.2). Alle Werte lowercase-hex-Strings."""
import hashlib

GENESIS = "GENESIS"
_SEP = b"\x00"


def bind_hex(tenant: str, session_id: str, record_uuid: str,
             record_sha256: str) -> str:
    h = hashlib.sha256()
    h.update(tenant.encode("utf-8")); h.update(_SEP)
    h.update(session_id.encode("utf-8")); h.update(_SEP)
    h.update(record_uuid.encode("utf-8")); h.update(_SEP)
    h.update(record_sha256.encode("utf-8"))
    return h.hexdigest()


def chain_hash_hex(prev_hash: str, bind_hex_val: str, pubkey_id: str,
                   sig_b64: str) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8")); h.update(_SEP)
    h.update(bind_hex_val.encode("utf-8")); h.update(_SEP)
    h.update(pubkey_id.encode("utf-8")); h.update(_SEP)
    h.update(sig_b64.encode("utf-8"))
    return h.hexdigest()
```

`collector/crypto.py`:

```python
"""Ed25519-Signaturen (Spec §5.3). Signiert wird der ASCII-Hex-bind-String."""
import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def generate_keypair() -> tuple[bytes, bytes]:
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv_raw, pub_raw


def sign_bind(priv_raw32: bytes, bind_hex_val: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(priv_raw32)
    return b64e(key.sign(bind_hex_val.encode("ascii")))


def verify_bind(pub_raw32: bytes, bind_hex_val: str, sig_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(pub_raw32).verify(
            b64d(sig_b64), bind_hex_val.encode("ascii"))
        return True
    except (InvalidSignature, ValueError):
        return False


def pubkey_id_from_raw(pub_raw32: bytes) -> str:
    return "ed25519:" + hashlib.sha256(pub_raw32).hexdigest()[:16]
```

- [ ] **Step 3: Tests grün**

Run: `.venv/bin/pytest tests/test_canon_chain_crypto.py -q`
Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add collector/canon.py collector/chain.py collector/crypto.py tests/test_canon_chain_crypto.py
git commit -m "feat: canon/chain/crypto primitives with reference vectors"
```

---

### Task 3: DB-Layer - Batch-Insert mit Head-Lock, Dedup, Chain

**Files:**
- Create: `collector/db.py`
- Modify: `tests/test_db_worm_and_chain.py` (Chain-Teil ergänzen)

**Interfaces:**
- Consumes: chain/canon (Task 2), Schema (Task 1)
- Produces:
  - `connect(url: str) -> psycopg.Connection` (autocommit=False)
  - `get_tenant_id(conn, name: str) -> int | None`; `create_tenant(conn, name) -> int`
  - `lock_head(conn, tenant_id) -> tuple[int, str]` - legt bei Bedarf die
    Head-Zeile an, `SELECT ... FOR UPDATE`, gibt (last_seq, chain_hash)
  - `insert_chained(conn, tenant_id, agent_row, items) -> list[dict]` -
    items = validierte Wrapper-Dicts in Batch-Reihenfolge; pro Item Ergebnis
    `{"record_uuid", "status": "accepted"|"duplicate", "seq", "prev_hash", "chain_hash"}`;
    aktualisiert tenant_heads; Chain überspringt Duplikate
  - `find_dangling(conn, tenant_id, session_ids: list[str]) -> set[str]` -
    record_uuids mit parent_uuid, dessen Ziel in (tenant, session) fehlt
  - `head(conn, tenant_id) -> dict`; `export_iter(conn, tenant_id, from_seq, to_seq)` -> Iterator über Record-Dicts in seq-Reihenfolge

- [ ] **Step 1: Failing Tests (Chain-Teil an test_db_worm_and_chain.py anhängen)**

```python
from collector import db as cdb
from collector.chain import GENESIS, bind_hex, chain_hash_hex


def _item(session_id, record_uuid, line_index=1, parent=None):
    return {"session_id": session_id, "record_uuid": record_uuid,
            "parent_uuid": parent, "line_index": line_index,
            "captured_at": "2026-07-07T12:00:00Z",
            "record_sha256": "ab" * 32, "sig_b64": "c2ln",
            "pubkey_id": "ed25519:0000000000000000",
            "raw": {"k": record_uuid}}


def test_insert_chained_assigns_seq_and_chain(db, superuser_db):
    tid = _mk_tenant_agent(superuser_db)
    agent_row = {"id": "agt_x", "tenant_name": "t1"}
    res = cdb.insert_chained(db, tid, agent_row,
                             [_item("s1", "u1"), _item("s1", "u2", 2, parent="u1")])
    db.commit()
    assert [r["status"] for r in res] == ["accepted", "accepted"]
    assert [r["seq"] for r in res] == [1, 2]
    b1 = bind_hex("t1", "s1", "u1", "ab" * 32)
    expect1 = chain_hash_hex(GENESIS, b1, "ed25519:0000000000000000", "c2ln")
    assert res[0]["prev_hash"] == GENESIS and res[0]["chain_hash"] == expect1
    assert res[1]["prev_hash"] == expect1
    assert cdb.head(db, tid)["seq"] == 2


def test_insert_chained_dedup(db, superuser_db):
    tid = _mk_tenant_agent(superuser_db)
    agent_row = {"id": "agt_x", "tenant_name": "t1"}
    cdb.insert_chained(db, tid, agent_row, [_item("s1", "u1")])
    db.commit()
    res = cdb.insert_chained(db, tid, agent_row,
                             [_item("s1", "u1"), _item("s1", "u3")])
    db.commit()
    assert res[0]["status"] == "duplicate" and res[0]["seq"] == 1
    assert res[1]["status"] == "accepted" and res[1]["seq"] == 2


def test_find_dangling(db, superuser_db):
    tid = _mk_tenant_agent(superuser_db)
    agent_row = {"id": "agt_x", "tenant_name": "t1"}
    cdb.insert_chained(db, tid, agent_row,
                       [_item("s1", "u2", 2, parent="u_missing")])
    db.commit()
    assert cdb.find_dangling(db, tid, ["s1"]) == {"u2"}
```

Run: erwartetes FAIL (kein Modul collector.db).

- [ ] **Step 2: Implementieren**

`collector/db.py`:

```python
"""Alle SQL-Zugriffe. seq-Vergabe serialisiert per Row-Lock auf tenant_heads."""
import json

import psycopg
from psycopg.rows import dict_row

from .chain import GENESIS, bind_hex, chain_hash_hex


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row)


def get_tenant_id(conn, name: str):
    row = conn.execute("SELECT id FROM tenants WHERE name = %s", (name,)).fetchone()
    return row["id"] if row else None


def create_tenant(conn, name: str) -> int:
    return conn.execute(
        "INSERT INTO tenants (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()["id"]


def lock_head(conn, tenant_id: int):
    conn.execute(
        "INSERT INTO tenant_heads (tenant_id) VALUES (%s)"
        " ON CONFLICT (tenant_id) DO NOTHING", (tenant_id,))
    row = conn.execute(
        "SELECT last_seq, chain_hash FROM tenant_heads"
        " WHERE tenant_id = %s FOR UPDATE", (tenant_id,)).fetchone()
    return row["last_seq"], row["chain_hash"]


def insert_chained(conn, tenant_id: int, agent_row: dict, items: list) -> list:
    """items: validierte Wrapper-Dicts in Batch-Reihenfolge. Ein Aufruf = eine
    Chain-Fortschreibung unter Head-Lock. Duplikate werden gemeldet, nicht
    eingefuegt, und unterbrechen die Chain nicht."""
    last_seq, prev = lock_head(conn, tenant_id)
    tenant_name = agent_row["tenant_name"]
    results = []
    for it in items:
        dup = conn.execute(
            "SELECT seq, prev_hash, chain_hash FROM records"
            " WHERE tenant_id = %s AND record_uuid = %s",
            (tenant_id, it["record_uuid"])).fetchone()
        if dup:
            results.append({"record_uuid": it["record_uuid"],
                            "status": "duplicate", "seq": dup["seq"],
                            "prev_hash": dup["prev_hash"],
                            "chain_hash": dup["chain_hash"]})
            continue
        b = bind_hex(tenant_name, it["session_id"], it["record_uuid"],
                     it["record_sha256"])
        ch = chain_hash_hex(prev, b, it["pubkey_id"], it["sig_b64"])
        last_seq += 1
        conn.execute(
            "INSERT INTO records (tenant_id, seq, agent_id, session_id,"
            " record_uuid, parent_uuid, line_index, captured_at, record_sha256,"
            " bind_hex, sig_b64, pubkey_id, prev_hash, chain_hash, raw)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (tenant_id, last_seq, agent_row["id"], it["session_id"],
             it["record_uuid"], it["parent_uuid"], it["line_index"],
             it["captured_at"], it["record_sha256"], b, it["sig_b64"],
             it["pubkey_id"], prev, ch, json.dumps(it["raw"], ensure_ascii=False)))
        results.append({"record_uuid": it["record_uuid"], "status": "accepted",
                        "seq": last_seq, "prev_hash": prev, "chain_hash": ch})
        prev = ch
    conn.execute(
        "UPDATE tenant_heads SET last_seq = %s, chain_hash = %s,"
        " updated_at = now() WHERE tenant_id = %s",
        (last_seq, prev, tenant_id))
    return results


def find_dangling(conn, tenant_id: int, session_ids: list) -> set:
    if not session_ids:
        return set()
    rows = conn.execute(
        "SELECT c.record_uuid FROM records c"
        " WHERE c.tenant_id = %s AND c.session_id = ANY(%s)"
        "   AND c.parent_uuid IS NOT NULL"
        "   AND NOT EXISTS (SELECT 1 FROM records p"
        "     WHERE p.tenant_id = c.tenant_id"
        "       AND p.session_id = c.session_id"
        "       AND p.record_uuid = c.parent_uuid)",
        (tenant_id, session_ids)).fetchall()
    return {r["record_uuid"] for r in rows}


def head(conn, tenant_id: int) -> dict:
    row = conn.execute(
        "SELECT last_seq AS seq, chain_hash, updated_at AS ts"
        " FROM tenant_heads WHERE tenant_id = %s", (tenant_id,)).fetchone()
    return row or {"seq": 0, "chain_hash": GENESIS, "ts": None}


def export_iter(conn, tenant_id: int, from_seq: int = 1, to_seq: int = None):
    q = ("SELECT seq, agent_id, session_id, record_uuid, parent_uuid,"
         " line_index, captured_at, record_sha256, bind_hex, sig_b64,"
         " pubkey_id, prev_hash, chain_hash, raw"
         " FROM records WHERE tenant_id = %s AND seq >= %s")
    params = [tenant_id, from_seq]
    if to_seq is not None:
        q += " AND seq <= %s"; params.append(to_seq)
    q += " ORDER BY seq"
    with conn.cursor() as cur:
        cur.execute(q, params)
        for row in cur:
            yield row
```

WICHTIG (im Test sichtbar): `conftest.db` verbindet als `collector_app` OHNE
dict_row - `cdb.insert_chained` nutzt aber dict-Zugriffe auf fetchone().
Deshalb in `tests/conftest.py` die db-Fixture auf
`psycopg.connect(TEST_URL, autocommit=False, row_factory=dict_row)` umstellen
(Import `from psycopg.rows import dict_row`) und in den Task-1-Tests
`fetchone()[0]`-Zugriffe des superuser_db unverändert lassen (superuser_db
bleibt ohne row_factory).

- [ ] **Step 3: Tests grün**

Run: `.venv/bin/pytest tests/ -q`
Expected: alle passed (Task-1-Tests + 3 neue)

- [ ] **Step 4: Commit**

```bash
git add collector/db.py tests/
git commit -m "feat: chained batch insert with tenant head lock, dedup, dangling detection"
```

---

### Task 4: Auth + Enrollment (Endpoint + Admin-CLI)

Bewusste Spec-Abweichung (dokumentiert in Architektur-Entscheidung 5): kein
Server-UI in v0; Enrollment-Tokens erzeugt ein Admin-CLI direkt gegen die DB.
Transport-Auth = opake Bearer-Tokens, sha256-gehasht gespeichert, revozierbar.

**Files:**
- Create: `collector/auth.py`, `collector/models.py` (Enroll-Teil),
  `collector/app.py` (App-Grundgerüst + /v1/enroll), `tools/mint_enrollment_token.py`
- Test: `tests/test_enroll_auth.py`

**Interfaces:**
- Produces:
  - `auth.sha256_hex(s: str) -> str`; `auth.new_token(prefix: str) -> str`
    (`prefix + secrets.token_urlsafe(32)`)
  - `auth.mint_enrollment_token(conn, tenant_name, ttl_hours=24) -> str` (legt Tenant bei Bedarf an)
  - `auth.enroll(conn, enrollment_token, pubkey_b64, machine, os_user, source_label) -> dict`
    -> `{"agent_id", "transport_token", "tenant", "pubkey_id"}`; wirft
    `auth.EnrollError("invalid_token"|"expired"|"used"|"bad_pubkey")`
  - `auth.agent_by_transport_token(conn, token: str) -> dict | None` -
    None wenn unbekannt/revoked; dict mit id, tenant_id, tenant_name,
    pubkey_b64, pubkey_id, source_label
  - FastAPI-App `collector.app:app`; `POST /v1/enroll` (Body:
    `{enrollment_token, pubkey, machine, os_user, source_label}`) ->
    201 `{agent_id, transport_token, tenant, pubkey_id}` | 403 `{detail}`
  - CLI: `.venv/bin/python tools/mint_enrollment_token.py <tenant> [--ttl-hours N]`
    druckt den Klartext-Token einmalig

- [ ] **Step 1: Failing Tests**

`tests/test_enroll_auth.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", os.environ.get(
    "DATABASE_URL_TEST",
    "postgresql://collector_app:collector_dev_pw@localhost:5433/audit_test"))
os.environ.setdefault("ADMIN_TOKEN", "test-admin")

from collector import auth
from collector.app import app
from collector.crypto import b64e, generate_keypair


@pytest.fixture()
def client(db):
    app.state.conn = db
    return TestClient(app)


def test_enroll_happy_path(db, client):
    tok = auth.mint_enrollment_token(db, "aeternalabs")
    db.commit()
    priv, pub = generate_keypair()
    r = client.post("/v1/enroll", json={
        "enrollment_token": tok, "pubkey": b64e(pub),
        "machine": "cortex", "os_user": "andie",
        "source_label": "cortex:andie"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["agent_id"].startswith("agt_")
    assert body["tenant"] == "aeternalabs"
    assert body["pubkey_id"].startswith("ed25519:")
    agent = auth.agent_by_transport_token(db, body["transport_token"])
    assert agent is not None and agent["id"] == body["agent_id"]


def test_enroll_token_single_use(db, client):
    tok = auth.mint_enrollment_token(db, "t1")
    db.commit()
    _, pub = generate_keypair()
    payload = {"enrollment_token": tok, "pubkey": b64e(pub),
               "machine": "m", "os_user": "u", "source_label": "m:u"}
    assert client.post("/v1/enroll", json=payload).status_code == 201
    assert client.post("/v1/enroll", json=payload).status_code == 403


def test_bad_enrollment_token_rejected(db, client):
    _, pub = generate_keypair()
    r = client.post("/v1/enroll", json={
        "enrollment_token": "nope", "pubkey": b64e(pub),
        "machine": "m", "os_user": "u", "source_label": "m:u"})
    assert r.status_code == 403


def test_revoked_agent_not_found_by_token(db, client):
    tok = auth.mint_enrollment_token(db, "t2")
    db.commit()
    _, pub = generate_keypair()
    body = client.post("/v1/enroll", json={
        "enrollment_token": tok, "pubkey": b64e(pub),
        "machine": "m", "os_user": "u", "source_label": "m:u"}).json()
    db.execute("UPDATE agents SET revoked_at = now() WHERE id = %s",
               (body["agent_id"],))
    db.commit()
    assert auth.agent_by_transport_token(db, body["transport_token"]) is None
```

Run: erwartetes FAIL.

- [ ] **Step 2: Implementieren**

`collector/models.py` (Enroll-Teil; Ingest-Modelle kommen in Task 5):

```python
"""Pydantic-Modelle der HTTP-Schnittstelle."""
from pydantic import BaseModel, Field


class EnrollRequest(BaseModel):
    enrollment_token: str = Field(min_length=8)
    pubkey: str = Field(min_length=40, max_length=60)  # base64 von 32 Bytes
    machine: str = ""
    os_user: str = ""
    source_label: str = ""


class EnrollResponse(BaseModel):
    agent_id: str
    transport_token: str
    tenant: str
    pubkey_id: str
```

`collector/auth.py`:

```python
"""Transport-Auth (Bearer, gehasht, revozierbar) + Enrollment (Spec §7)."""
import hashlib
import secrets

from .crypto import b64d, pubkey_id_from_raw
from . import db as cdb


class EnrollError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def mint_enrollment_token(conn, tenant_name: str, ttl_hours: int = 24) -> str:
    tid = cdb.get_tenant_id(conn, tenant_name) or cdb.create_tenant(conn, tenant_name)
    tok = new_token("enr_")
    conn.execute(
        "INSERT INTO enrollment_tokens (tenant_id, token_hash, expires_at)"
        " VALUES (%s, %s, now() + make_interval(hours => %s))",
        (tid, sha256_hex(tok), ttl_hours))
    return tok


def enroll(conn, enrollment_token: str, pubkey_b64: str, machine: str,
           os_user: str, source_label: str) -> dict:
    row = conn.execute(
        "SELECT et.id, et.tenant_id, et.expires_at < now() AS expired,"
        " et.used_at IS NOT NULL AS used, t.name AS tenant_name"
        " FROM enrollment_tokens et JOIN tenants t ON t.id = et.tenant_id"
        " WHERE et.token_hash = %s FOR UPDATE",
        (sha256_hex(enrollment_token),)).fetchone()
    if row is None:
        raise EnrollError("invalid_token")
    if row["used"]:
        raise EnrollError("used")
    if row["expired"]:
        raise EnrollError("expired")
    try:
        pub_raw = b64d(pubkey_b64)
        if len(pub_raw) != 32:
            raise ValueError
    except Exception:
        raise EnrollError("bad_pubkey")
    agent_id = "agt_" + secrets.token_hex(8)
    transport_token = new_token("act_")
    conn.execute(
        "INSERT INTO agents (id, tenant_id, pubkey_b64, pubkey_id, machine,"
        " os_user, source_label, transport_token_hash)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (agent_id, row["tenant_id"], pubkey_b64, pubkey_id_from_raw(pub_raw),
         machine, os_user, source_label, sha256_hex(transport_token)))
    conn.execute("UPDATE enrollment_tokens SET used_at = now() WHERE id = %s",
                 (row["id"],))
    return {"agent_id": agent_id, "transport_token": transport_token,
            "tenant": row["tenant_name"],
            "pubkey_id": pubkey_id_from_raw(pub_raw)}


def agent_by_transport_token(conn, token: str):
    return conn.execute(
        "SELECT a.id, a.tenant_id, a.pubkey_b64, a.pubkey_id, a.source_label,"
        " t.name AS tenant_name"
        " FROM agents a JOIN tenants t ON t.id = a.tenant_id"
        " WHERE a.transport_token_hash = %s AND a.revoked_at IS NULL",
        (sha256_hex(token),)).fetchone()
```

`collector/app.py` (Grundgerüst):

```python
"""FastAPI-App. Nur HTTP-Verdrahtung - Domänenlogik lebt in auth/db.

Connection-Handling v0: eine Connection pro Request aus settings.database_url;
Tests injizieren ihre Transaktions-Connection via app.state.conn.
"""
import contextlib

from fastapi import Depends, FastAPI, HTTPException, Request

from . import auth, db as cdb
from .models import EnrollRequest, EnrollResponse
from .settings import load_settings

app = FastAPI(title="audit-collector", version="0.1.0")


def get_conn(request: Request):
    injected = getattr(request.app.state, "conn", None)
    if injected is not None:
        yield injected
        return
    conn = cdb.connect(load_settings().database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.post("/v1/enroll", response_model=EnrollResponse, status_code=201)
def enroll(body: EnrollRequest, conn=Depends(get_conn)):
    try:
        result = auth.enroll(conn, body.enrollment_token, body.pubkey,
                             body.machine, body.os_user, body.source_label)
    except auth.EnrollError as e:
        raise HTTPException(status_code=403, detail=e.reason)
    return result
```

Hinweis für die Tests: die injizierte Test-Connection wird von den Tests
selbst committet/rollbackt; get_conn committet nur selbstgebaute Connections.
Der Doppel-Enroll-Test funktioniert, weil TestClient-Aufrufe sequenziell auf
derselben Connection laufen (FOR UPDATE + used_at in einer Transaktion).
Damit der zweite Aufruf den used_at des ersten sieht, MUSS der Test zwischen
den Aufrufen nichts tun - beide Statements laufen in derselben offenen
Transaktion, das ist korrekt.

`tools/mint_enrollment_token.py`:

```python
#!/usr/bin/env python3
"""Admin-CLI: einmaligen Enrollment-Token fuer einen Tenant erzeugen.

Usage: python tools/mint_enrollment_token.py <tenant> [--ttl-hours N]
Druckt den Klartext-Token EINMALIG. Er wird nur gehasht gespeichert.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import auth, db as cdb  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tenant")
    p.add_argument("--ttl-hours", type=int, default=24)
    args = p.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL nicht gesetzt (.env laden)")
    with cdb.connect(url) as conn:
        tok = auth.mint_enrollment_token(conn, args.tenant, args.ttl_hours)
        conn.commit()
    print(tok)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Tests grün**

Run: `.venv/bin/pytest tests/ -q`
Expected: alle passed

- [ ] **Step 4: CLI-Smoke**

```bash
set -a; source .env 2>/dev/null || cp .env.example .env && source .env; set +a
.venv/bin/python tools/mint_enrollment_token.py smoketest --ttl-hours 1
```

Expected: eine Zeile `enr_...`

- [ ] **Step 5: Commit**

```bash
git add collector/ tools/mint_enrollment_token.py tests/test_enroll_auth.py
git commit -m "feat: enrollment endpoint, hashed revocable transport tokens, mint CLI"
```

---

### Task 5: Ingest + Chain-Head Endpoints

**Files:**
- Modify: `collector/models.py` (Wrapper/Ingest-Modelle), `collector/app.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Produces:
  - `POST /v1/ingest` - Auth: `Authorization: Bearer <transport_token>`.
    Body: `{"records": [WrapperRecord, ...]}` (max 1000/Batch).
    WrapperRecord = Spec §4 + `line_index`:
    `{agent_id, pubkey_id, tenant, seat{machine, os_user, source_label},
      session_id, record_uuid, parent_uuid|null, line_index, captured_at,
      record_sha256, sig, raw}`
    Response 200: `{"results": [{record_uuid, status: accepted|duplicate|rejected,
      seq?, prev_hash?, chain_hash?, reason?, warnings?: ["dangling_parent"]}]}`
    401 bei fehlendem/unbekanntem/revoziertem Token.
  - Reject-Reasons: `bad_signature`, `sha256_mismatch`, `agent_mismatch`
    (agent_id/pubkey_id/tenant im Record passen nicht zum Token-Agent).
  - `GET /v1/chain/head?tenant=<name>` - Auth: Agent-Token desselben Tenants
    ODER Admin-Token. Response: `{tenant, seq, chain_hash, ts}`.

- [ ] **Step 1: Failing Tests**

`tests/test_ingest.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", os.environ.get(
    "DATABASE_URL_TEST",
    "postgresql://collector_app:collector_dev_pw@localhost:5433/audit_test"))
os.environ.setdefault("ADMIN_TOKEN", "test-admin")

from collector import auth
from collector.app import app
from collector.canon import record_sha256_hex
from collector.chain import bind_hex
from collector.crypto import b64e, generate_keypair, sign_bind


@pytest.fixture()
def client(db):
    app.state.conn = db
    return TestClient(app)


@pytest.fixture()
def enrolled(db, client):
    tok = auth.mint_enrollment_token(db, "aeternalabs")
    db.commit()
    priv, pub = generate_keypair()
    body = client.post("/v1/enroll", json={
        "enrollment_token": tok, "pubkey": b64e(pub),
        "machine": "cortex", "os_user": "andie",
        "source_label": "cortex:andie"}).json()
    db.commit()
    return {"priv": priv, **body}


def _wrapped(enrolled, session_id, raw, line_index, parent=None):
    rs = record_sha256_hex(raw)
    record_uuid = raw.get("uuid") or f"synth:{session_id}:{line_index}"
    b = bind_hex("aeternalabs", session_id, record_uuid, rs)
    return {"agent_id": enrolled["agent_id"], "pubkey_id": enrolled["pubkey_id"],
            "tenant": "aeternalabs",
            "seat": {"machine": "cortex", "os_user": "andie",
                     "source_label": "cortex:andie"},
            "session_id": session_id, "record_uuid": record_uuid,
            "parent_uuid": parent, "line_index": line_index,
            "captured_at": "2026-07-07T12:00:00Z",
            "record_sha256": rs, "sig": sign_bind(enrolled["priv"], b),
            "raw": raw}


def _auth(enrolled):
    return {"Authorization": f"Bearer {enrolled['transport_token']}"}


def test_ingest_accepts_and_chains(db, client, enrolled):
    recs = [_wrapped(enrolled, "s1", {"uuid": "u1", "type": "user"}, 1),
            _wrapped(enrolled, "s1", {"uuid": "u2", "type": "assistant",
                                      "parentUuid": "u1"}, 2, parent="u1")]
    r = client.post("/v1/ingest", json={"records": recs}, headers=_auth(enrolled))
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert [x["status"] for x in res] == ["accepted", "accepted"]
    assert res[0]["seq"] == 1 and res[1]["seq"] == 2
    assert "warnings" not in res[1] or res[1]["warnings"] == []


def test_ingest_idempotent_on_retry(db, client, enrolled):
    recs = [_wrapped(enrolled, "s1", {"uuid": "u1", "type": "user"}, 1)]
    client.post("/v1/ingest", json={"records": recs}, headers=_auth(enrolled))
    r2 = client.post("/v1/ingest", json={"records": recs}, headers=_auth(enrolled))
    assert r2.json()["results"][0]["status"] == "duplicate"
    assert r2.json()["results"][0]["seq"] == 1


def test_ingest_rejects_bad_signature(db, client, enrolled):
    rec = _wrapped(enrolled, "s1", {"uuid": "u1", "type": "user"}, 1)
    rec["sig"] = rec["sig"][:-4] + "AAA="
    r = client.post("/v1/ingest", json={"records": [rec]}, headers=_auth(enrolled))
    body = r.json()["results"][0]
    assert body["status"] == "rejected" and body["reason"] == "bad_signature"


def test_ingest_rejects_sha_mismatch(db, client, enrolled):
    rec = _wrapped(enrolled, "s1", {"uuid": "u1", "type": "user"}, 1)
    rec["raw"] = {"uuid": "u1", "type": "user", "tampered": True}
    r = client.post("/v1/ingest", json={"records": [rec]}, headers=_auth(enrolled))
    assert r.json()["results"][0]["reason"] == "sha256_mismatch"


def test_ingest_flags_dangling_parent(db, client, enrolled):
    rec = _wrapped(enrolled, "s1", {"uuid": "u9", "type": "user",
                                    "parentUuid": "u_missing"}, 9,
                   parent="u_missing")
    r = client.post("/v1/ingest", json={"records": [rec]}, headers=_auth(enrolled))
    body = r.json()["results"][0]
    assert body["status"] == "accepted"
    assert body.get("warnings") == ["dangling_parent"]


def test_ingest_requires_valid_token(db, client, enrolled):
    rec = _wrapped(enrolled, "s1", {"uuid": "u1"}, 1)
    r = client.post("/v1/ingest", json={"records": [rec]},
                    headers={"Authorization": "Bearer act_wrong"})
    assert r.status_code == 401


def test_chain_head(db, client, enrolled):
    recs = [_wrapped(enrolled, "s1", {"uuid": "u1"}, 1)]
    client.post("/v1/ingest", json={"records": recs}, headers=_auth(enrolled))
    r = client.get("/v1/chain/head", params={"tenant": "aeternalabs"},
                   headers=_auth(enrolled))
    assert r.status_code == 200
    assert r.json()["seq"] == 1 and len(r.json()["chain_hash"]) == 64
```

Run: erwartetes FAIL.

- [ ] **Step 2: Modelle ergänzen** (`collector/models.py` anhängen):

```python
class Seat(BaseModel):
    machine: str = ""
    os_user: str = ""
    source_label: str = ""


class WrapperRecord(BaseModel):
    agent_id: str
    pubkey_id: str
    tenant: str
    seat: Seat
    session_id: str = Field(min_length=1)
    record_uuid: str = Field(min_length=1)
    parent_uuid: str | None = None
    line_index: int = Field(ge=1)
    captured_at: str
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sig: str = Field(min_length=64)
    raw: dict


class IngestRequest(BaseModel):
    records: list[WrapperRecord] = Field(min_length=1, max_length=1000)
```

- [ ] **Step 3: Endpoints implementieren** (`collector/app.py` ergänzen):

```python
from fastapi import Header

from .canon import record_sha256_hex
from .chain import bind_hex
from .crypto import b64d, verify_bind
from .models import IngestRequest


def require_agent(conn, authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    agent = auth.agent_by_transport_token(conn, authorization[len("Bearer "):])
    if agent is None:
        raise HTTPException(status_code=401, detail="unknown_or_revoked_token")
    return agent


@app.post("/v1/ingest")
def ingest(body: IngestRequest, conn=Depends(get_conn),
           authorization: str | None = Header(default=None)):
    agent = require_agent(conn, authorization)
    pub_raw = b64d(agent["pubkey_b64"])
    accepted_items, results, order = [], {}, []
    for rec in body.records:
        order.append(rec.record_uuid)
        if (rec.agent_id != agent["id"] or rec.pubkey_id != agent["pubkey_id"]
                or rec.tenant != agent["tenant_name"]):
            results[rec.record_uuid] = {"record_uuid": rec.record_uuid,
                                        "status": "rejected",
                                        "reason": "agent_mismatch"}
            continue
        if record_sha256_hex(rec.raw) != rec.record_sha256:
            results[rec.record_uuid] = {"record_uuid": rec.record_uuid,
                                        "status": "rejected",
                                        "reason": "sha256_mismatch"}
            continue
        b = bind_hex(rec.tenant, rec.session_id, rec.record_uuid,
                     rec.record_sha256)
        if not verify_bind(pub_raw, b, rec.sig):
            results[rec.record_uuid] = {"record_uuid": rec.record_uuid,
                                        "status": "rejected",
                                        "reason": "bad_signature"}
            continue
        accepted_items.append({
            "session_id": rec.session_id, "record_uuid": rec.record_uuid,
            "parent_uuid": rec.parent_uuid, "line_index": rec.line_index,
            "captured_at": rec.captured_at, "record_sha256": rec.record_sha256,
            "sig_b64": rec.sig, "pubkey_id": rec.pubkey_id, "raw": rec.raw})
    if accepted_items:
        agent_row = {"id": agent["id"], "tenant_name": agent["tenant_name"]}
        for res in cdb.insert_chained(conn, agent["tenant_id"], agent_row,
                                      accepted_items):
            results[res["record_uuid"]] = res
        dangling = cdb.find_dangling(
            conn, agent["tenant_id"],
            sorted({i["session_id"] for i in accepted_items}))
        for uuid, res in results.items():
            if res["status"] == "accepted" and uuid in dangling:
                res["warnings"] = ["dangling_parent"]
    return {"results": [results[u] for u in order]}


@app.get("/v1/chain/head")
def chain_head(tenant: str, conn=Depends(get_conn),
               authorization: str | None = Header(default=None)):
    settings = load_settings()
    is_admin = (authorization == f"Bearer {settings.admin_token}")
    tid = cdb.get_tenant_id(conn, tenant)
    if tid is None:
        raise HTTPException(status_code=404, detail="unknown_tenant")
    if not is_admin:
        agent = require_agent(conn, authorization)
        if agent["tenant_id"] != tid:
            raise HTTPException(status_code=403, detail="wrong_tenant")
    h = cdb.head(conn, tid)
    return {"tenant": tenant, "seq": h["seq"], "chain_hash": h["chain_hash"],
            "ts": str(h["ts"]) if h["ts"] else None}
```

- [ ] **Step 4: Tests grün**

Run: `.venv/bin/pytest tests/ -q`
Expected: alle passed

- [ ] **Step 5: Commit**

```bash
git add collector/models.py collector/app.py tests/test_ingest.py
git commit -m "feat: ingest endpoint with signature verification, chaining, dedup, dangling warnings; chain head"
```

---

### Task 6: Export + Verifier + E2E-Tamper-Beweis + README

**Files:**
- Modify: `collector/app.py` (Export), `README.md` (vervollständigen)
- Create: `tools/verifier.py`
- Test: `tests/test_export_verifier.py`

**Interfaces:**
- Produces:
  - `GET /v1/export?tenant=<name>&from_seq=&to_seq=` - Auth: NUR Admin-Token.
    Response: `application/x-ndjson`, eine Zeile pro Record (alle
    Chain-Felder + raw), seq-aufsteigend.
  - `tools/verifier.py <export.jsonl> --tenant <name> [--pubkeys <json>]`:
    rechnet record_sha256 (aus raw via canon), bind, chain komplett nach,
    verifiziert jede Signatur gegen die Pubkey-Map (`{pubkey_id: pubkey_b64}`,
    Default: aus den Records selbst NICHT ableitbar -> Pflichtparameter oder
    per `--from-url` + Admin-Token vom Server holen; v0: --pubkeys-Datei),
    prüft die parentUuid-DAG pro Session (Grace: Records ohne Parent im Export
    werden als "dangling" GEMELDET, brechen aber nicht), meldet die ERSTE
    Chain-/Signatur-Divergenz mit seq und Exit 1; Exit 0 wenn alles gut.
- Der E2E-Test beweist: Manipulation einer Zeile in der DB (als Superuser,
  denn die App-Rolle KANN nicht) wird vom Verifier als Divergenz an genau
  dieser seq gemeldet.

- [ ] **Step 1: Failing Tests**

`tests/test_export_verifier.py`:

```python
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", os.environ.get(
    "DATABASE_URL_TEST",
    "postgresql://collector_app:collector_dev_pw@localhost:5433/audit_test"))
os.environ.setdefault("ADMIN_TOKEN", "test-admin")

from collector import auth
from collector.app import app
from collector.crypto import b64e, generate_keypair

from .test_ingest import _auth, _wrapped  # wiederverwendete Helfer


@pytest.fixture()
def client(db):
    app.state.conn = db
    return TestClient(app)


@pytest.fixture()
def enrolled(db, client):
    tok = auth.mint_enrollment_token(db, "aeternalabs")
    db.commit()
    priv, pub = generate_keypair()
    body = client.post("/v1/enroll", json={
        "enrollment_token": tok, "pubkey": b64e(pub),
        "machine": "cortex", "os_user": "andie",
        "source_label": "cortex:andie"}).json()
    db.commit()
    return {"priv": priv, "pub": pub, **body}


def _ingest_three(client, enrolled):
    recs = [
        _wrapped(enrolled, "s1", {"uuid": "u1", "type": "user"}, 1),
        _wrapped(enrolled, "s1", {"uuid": "u2", "type": "assistant",
                                  "parentUuid": "u1"}, 2, parent="u1"),
        _wrapped(enrolled, "s2", {"type": "mode", "mode": "x"}, 1),
    ]
    r = client.post("/v1/ingest", json={"records": recs},
                    headers=_auth(enrolled))
    assert all(x["status"] == "accepted" for x in r.json()["results"])


def _export(client):
    r = client.get("/v1/export", params={"tenant": "aeternalabs"},
                   headers={"Authorization": "Bearer test-admin"})
    assert r.status_code == 200
    return r.text


def _run_verifier(tmp_path, export_text, enrolled):
    exp = tmp_path / "export.jsonl"
    exp.write_text(export_text, encoding="utf-8")
    pk = tmp_path / "pubkeys.json"
    pk.write_text(json.dumps({enrolled["pubkey_id"]: b64e(enrolled["pub"])}),
                  encoding="utf-8")
    return subprocess.run(
        [sys.executable, "tools/verifier.py", str(exp),
         "--tenant", "aeternalabs", "--pubkeys", str(pk)],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_export_requires_admin(db, client, enrolled):
    _ingest_three(client, enrolled)
    r = client.get("/v1/export", params={"tenant": "aeternalabs"},
                   headers=_auth(enrolled))
    assert r.status_code == 403


def test_verifier_ok_on_clean_export(db, client, enrolled, tmp_path):
    _ingest_three(client, enrolled)
    db.commit()
    res = _run_verifier(tmp_path, _export(client), enrolled)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "OK" in res.stdout


def test_verifier_detects_tamper(db, superuser_db, client, enrolled, tmp_path):
    _ingest_three(client, enrolled)
    db.commit()
    superuser_db.execute(
        "UPDATE records SET raw = jsonb_set(raw, '{type}', '\"assistant\"')"
        " WHERE seq = 1")
    res = _run_verifier(tmp_path, _export(client), enrolled)
    assert res.returncode == 1
    assert "seq=1" in res.stdout


def test_verifier_reports_dangling(db, client, enrolled, tmp_path):
    rec = _wrapped(enrolled, "s3", {"uuid": "u9", "parentUuid": "ghost"}, 1,
                   parent="ghost")
    client.post("/v1/ingest", json={"records": [rec]}, headers=_auth(enrolled))
    db.commit()
    res = _run_verifier(tmp_path, _export(client), enrolled)
    assert res.returncode == 0          # dangling meldet, bricht nicht
    assert "dangling" in res.stdout
```

Run: erwartetes FAIL.

- [ ] **Step 2: Export-Endpoint** (`collector/app.py` ergänzen):

```python
import json as _json

from fastapi.responses import StreamingResponse


@app.get("/v1/export")
def export(tenant: str, from_seq: int = 1, to_seq: int | None = None,
           conn=Depends(get_conn),
           authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {load_settings().admin_token}":
        raise HTTPException(status_code=403, detail="admin_only")
    tid = cdb.get_tenant_id(conn, tenant)
    if tid is None:
        raise HTTPException(status_code=404, detail="unknown_tenant")
    rows = list(cdb.export_iter(conn, tid, from_seq, to_seq))

    def lines():
        for row in rows:
            row["captured_at"] = str(row["captured_at"])
            yield _json.dumps(row, ensure_ascii=False, default=str) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")
```

- [ ] **Step 3: Verifier**

`tools/verifier.py`:

```python
#!/usr/bin/env python3
"""Offline-Verifier (Spec §6): rechnet Chain + Signaturen + DAG nach.

Eigenstaendig reproduzierbar: braucht nur den Export (JSONL), den
Tenant-Namen und die Pubkey-Map {pubkey_id: pubkey_b64}. Meldet die ERSTE
Divergenz (Exit 1). Dangling parents werden gemeldet, brechen aber nicht
(Grace-Semantik wie beim Server).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.canon import record_sha256_hex          # noqa: E402
from collector.chain import GENESIS, bind_hex, chain_hash_hex  # noqa: E402
from collector.crypto import b64d, verify_bind         # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("export_file")
    p.add_argument("--tenant", required=True)
    p.add_argument("--pubkeys", required=True,
                   help="JSON-Datei {pubkey_id: pubkey_b64}")
    args = p.parse_args()

    with open(args.pubkeys, encoding="utf-8") as f:
        pubkeys = {k: b64d(v) for k, v in json.load(f).items()}

    prev = GENESIS
    expected_seq = 0
    sessions = {}          # session_id -> set(record_uuid)
    parents = []           # (seq, session_id, record_uuid, parent_uuid)
    n = 0

    with open(args.export_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            n += 1
            seq = r["seq"]
            expected_seq += 1
            if seq != expected_seq:
                print(f"DIVERGENZ seq={seq}: Luecke/Umsortierung"
                      f" (erwartet {expected_seq})")
                sys.exit(1)
            rs = record_sha256_hex(r["raw"])
            if rs != r["record_sha256"]:
                print(f"DIVERGENZ seq={seq}: record_sha256 stimmt nicht"
                      f" (raw wurde veraendert)")
                sys.exit(1)
            b = bind_hex(args.tenant, r["session_id"], r["record_uuid"], rs)
            if b != r["bind_hex"]:
                print(f"DIVERGENZ seq={seq}: bind stimmt nicht")
                sys.exit(1)
            pub = pubkeys.get(r["pubkey_id"])
            if pub is None:
                print(f"DIVERGENZ seq={seq}: unbekannte pubkey_id"
                      f" {r['pubkey_id']}")
                sys.exit(1)
            if not verify_bind(pub, b, r["sig_b64"]):
                print(f"DIVERGENZ seq={seq}: Signatur ungueltig")
                sys.exit(1)
            if r["prev_hash"] != prev:
                print(f"DIVERGENZ seq={seq}: prev_hash bricht die Chain")
                sys.exit(1)
            ch = chain_hash_hex(prev, b, r["pubkey_id"], r["sig_b64"])
            if ch != r["chain_hash"]:
                print(f"DIVERGENZ seq={seq}: chain_hash stimmt nicht")
                sys.exit(1)
            prev = ch
            sessions.setdefault(r["session_id"], set()).add(r["record_uuid"])
            if r.get("parent_uuid"):
                parents.append((seq, r["session_id"], r["record_uuid"],
                                r["parent_uuid"]))

    dangling = [(s, sid, u, pu) for (s, sid, u, pu) in parents
                if pu not in sessions.get(sid, set())]
    for seq, sid, u, pu in dangling:
        print(f"dangling parent: seq={seq} session={sid}"
              f" record={u} -> fehlender Vorgaenger {pu}")

    print(f"OK: {n} Records, Chain-Kopf {prev},"
          f" {len(dangling)} dangling parent(s)")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Tests grün**

Run: `.venv/bin/pytest tests/ -q`
Expected: alle passed (inkl. Tamper-Test: Superuser-UPDATE -> Verifier Exit 1
mit `seq=1`)

- [ ] **Step 5: README vervollständigen**

An `README.md` anfügen: Endpunkt-Tabelle (Spec §6), Auth-Modell (zwei Ebenen:
Transport-Token vs. Ed25519-Content-Attestierung), Enrollment-Ablauf mit
mint-CLI, Verifier-Aufruf mit Pubkey-Map, Hinweis WORM-Grants + Chain +
Verifier = drei unabhängige Integritätsschichten, TLS-via-Reverse-Proxy.
Formatvorgabe: sachlich, keine Marketing-Sprache, keine internen Codenamen.

- [ ] **Step 6: End-Verifikation + Commit**

```bash
.venv/bin/pytest tests/ -q
git add collector/app.py tools/verifier.py tests/test_export_verifier.py README.md
git commit -m "feat: admin export (ndjson), offline verifier with tamper detection, docs"
```

---

## Self-Review (beim Planschreiben durchgeführt)

1. **Spec-Abdeckung Plan-2-Scope:** §4 Wrapper (inkl. beschlossener
   line_index/synth-uuid-Ergänzungen serverseitig als opake Felder), §5.1
   (dangling-Detection + Verifier-DAG), §5.2 (Chain exakt nach Formel, GENESIS,
   seq monoton), §5.3 (Ed25519 gegen enrollten Pubkey, Signatur über bind),
   §6 (alle 4 Endpunkte + Response-Schema; Verifier als Script), §7 (zwei
   Auth-Ebenen, Enrollment-Flow; UI->CLI als dokumentierte v0-Abweichung),
   §8 (Dedup auf record_uuid, seq serverseitig, dangling mit Grace-Semantik),
   §9 (WORM-Grants + Test; TLS via Proxy dokumentiert; At-Rest-Encryption =
   Betriebsthema, README-Hinweis). Agent-State (§8) und JSONL-Tailing sind
   Plan 3; Engine-Anbindung ist Plan 4.
2. **Platzhalter-Scan:** alle Artefakte vollständig ausgeschrieben; einzige
   bewusste Prosa-Stellen: README-Inhaltsvorgabe (Task 6 Step 5) und der
   dokumentierte Zwei-Datei-Split in Task 1 Step 3.
3. **Konsistenz:** `_wrapped`/`_auth` werden in test_export_verifier aus
   test_ingest importiert (beide definiert); `insert_chained`-Item-Schlüssel
   == db.py-Zugriffe == app.py-Konstruktion; Reject-Reasons einheitlich;
   dict_row-Hinweis in Task 3 deckt die fetchone()-Zugriffe aus auth/db.
