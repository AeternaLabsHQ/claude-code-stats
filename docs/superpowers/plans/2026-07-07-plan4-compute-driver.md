# Plan 4: Server-Compute-Driver + Dashboard-API + Kalibrierungs-Beweis

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Server-Driver des Audit Collector v0: `claudestats_core` (die
kalibrierte Engine aus Plan 1) konsumiert Records aus Postgres statt Dateien,
materialisiert pro Tenant das Dashboard-JSON hinter `/v1/dashboard`, und der
E2E-Kalibrierungs-Beweis zeigt: Datei-Weg und DB-Weg liefern semantisch
identische Ergebnisse.

**Architecture:** `collector/compute.py` rekonstruiert pro Session die
Zeilenfolge aus `records` (ORDER BY session_id, line_index, seq), baut
`SessionFileMeta` (Subagent-Erkennung über den `agent-`-Stem,
parent/agent-Metadaten aus `raw.sessionId` und den `x-meta-sidecar`-Records)
und ruft dieselbe Kette `absorb_file -> finalize_sessions ->
build_dashboard_data` wie der CLI-Driver. Caching über den Chain-Kopf:
`dashboard_cache(tenant_id, as_of_seq, data)` - Rebuild nur, wenn
`tenant_heads.last_seq` vom Cache abweicht. **Dokumentierte Abweichung von
Architektur-Entscheidung 6 (Debounce-on-Ingest):** v0 nutzt
Lazy-Rebuild-on-Read mit seq-Cache-Key - strikt einfacher (kein
Hintergrund-Worker, kein Timing), deterministisch idempotent, und die
Architektur erklärt den Compute-Trigger explizit für austauschbar. Debounce-
Worker bleibt Roadmap, falls Read-Latenz je stört.

**Tech Stack:** wie audit-collector (FastAPI/psycopg) + `claudestats-core`
als gepinnte Git-Dependency aus dem claude-stats-Repo (Branch
feature/core-extraction).

## Global Constraints

- Repo `/home/andie/projects/audit-collector`, Branch `main`, HEAD `a06a9d7`
  (50 Tests grün). Nie pushen.
- **Engine wird importiert, nie kopiert oder angepasst:** `collector/compute.py`
  ruft ausschließlich die Public API von `claudestats_core` (`SessionFileMeta`,
  `absorb_file`, `finalize_sessions`, `build_dashboard_data`, `settings`).
  Jede Modifikation an Engine-Verhalten ist ein Task-Abbruch.
- **Core-Pin:** Install via
  `pip install "claudestats-core @ git+file:///home/andie/projects/claude-stats@<HEAD-SHA von feature/core-extraction>"`
  (SHA beim Task-1-Lauf per `git -C /home/andie/projects/claude-stats rev-parse feature/core-extraction`
  ermitteln und im README festhalten). Nicht in pyproject-dependencies
  (file-URL ist maschinenspezifisch); README dokumentiert den Schritt und dass
  nach Merge/Publish auf eine GitHub-URL mit Tag umgestellt wird.
- **settings-Disziplin:** `claudestats_core.settings` ist Prozess-Global
  (dokumentiert in dessen Docstring). Der Server rechnet v0 mit den
  Core-Defaults (leere plan_history usw.); `rebuild_tenant` ruft
  `settings.configure(source_label=...)` NICHT - source_label kommt pro
  Session über `SessionFileMeta`, und der Fallback-Default greift nur für
  Alt-Sessions ohne Quelle. Tenant-spezifische Engine-Settings sind Roadmap.
- **Sidecar-Mapping:** Records mit `raw.type == "x-meta-sidecar"` werden VOR
  `absorb_file` herausgefiltert und liefern `agent_type`/`agent_description`
  (aus `raw.content.agentType`/`.description`) für die Meta der betroffenen
  Session.
- **Dokumentierte Näherungen des DB-Wegs** (fließen in die Normalisierung des
  Beweis-Tests, Task 4): `file_size` = Summe der `canon(raw)`-Bytelängen statt
  stat(); `project_name` = `raw.cwd` mit `/`->`-` gemunged (Claude-Code-
  Konvention) vom ersten Record mit cwd, sonst `""`.
- Nach jedem Task: `.venv/bin/pytest tests/ -q` grün.

## File Structure

```
collector/compute.py       # rebuild_tenant + Hilfen (Gruppierung, Meta-Bau)
sql/003_dashboard_cache.sql
collector/app.py           # + GET /v1/dashboard
tests/test_compute.py
tests/test_dashboard_endpoint.py
tests/test_calibration_e2e.py   # DER Beweis: Datei-Weg == DB-Weg
```

---

### Task 1: Core-Dependency installieren + Smoke

**Files:**
- Modify: `README.md` (Abschnitt "Engine-Dependency (claudestats-core)")
- Test: `tests/test_core_dependency.py`

- [ ] **Step 1: SHA ermitteln + installieren**

```bash
CORE_SHA=$(git -C /home/andie/projects/claude-stats rev-parse feature/core-extraction)
echo "$CORE_SHA"
.venv/bin/pip install "claudestats-core @ git+file:///home/andie/projects/claude-stats@${CORE_SHA}"
```

Expected: Install erfolgreich; `.venv/bin/python -c "import claudestats_core; print(claudestats_core.__name__)"` druckt `claudestats_core`.

- [ ] **Step 2: Failing Smoke-Test**

`tests/test_core_dependency.py`:

```python
def test_core_public_api_available():
    import claudestats_core as core
    for name in ("settings", "SessionFileMeta", "absorb_file",
                 "finalize_sessions", "build_dashboard_data"):
        assert hasattr(core, name), name


def test_core_engine_smoke():
    """Mini-Session durch die echte Engine - beweist, dass der Pin
    funktioniert und die API sich wie dokumentiert verhaelt."""
    import claudestats_core as core
    sessions = {}
    meta = core.SessionFileMeta(source_label="srv:test",
                                file_session_id="s1", project_name="-p")
    core.absorb_file(sessions, meta, [
        {"type": "user", "uuid": "u1", "parentUuid": None, "sessionId": "s1",
         "timestamp": "2026-07-07T10:00:00Z",
         "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "uuid": "u2", "parentUuid": "u1",
         "sessionId": "s1", "timestamp": "2026-07-07T10:00:05Z",
         "message": {"model": "claude-sonnet-5", "usage": {
             "input_tokens": 10, "output_tokens": 5}, "content": []}},
    ])
    core.finalize_sessions(sessions)
    data = core.build_dashboard_data(sessions, {}, {}, [])
    assert data["kpi"]["total_sessions"] == 1
    assert data["kpi"]["total_messages"] == 2
```

Run vor Install wäre rot; nach Step 1 grün: `.venv/bin/pytest tests/test_core_dependency.py -q` -> 2 passed.
(Falls `build_dashboard_data` mit diesen Minimal-Argumenten einen Fehler wirft,
weil ein Loader-Argument doch nicht None-fest ist: STOPP, BLOCKED melden mit
Traceback - das wäre ein Plan-1-API-Befund, nicht hier zu flicken.)

- [ ] **Step 3: README-Abschnitt** (Install-Kommando mit dem konkreten SHA,
  Hinweis auf spätere GitHub-URL, ein Satz zur settings-Prozess-Global-Regel).

- [ ] **Step 4: Voller Lauf + Commit**

```bash
.venv/bin/pytest tests/ -q   # 52 erwartet
git add tests/test_core_dependency.py README.md
git commit -m "feat(compute): pin claudestats-core engine dependency + smoke"
```

---

### Task 2: `collector/compute.py` - rebuild_tenant

**Files:**
- Create: `collector/compute.py`
- Test: `tests/test_compute.py`

**Interfaces:**
- Produces: `rebuild_tenant(conn, tenant_id: int) -> dict` (das
  Dashboard-JSON der Engine) und intern `_sessions_from_records(rows) ->
  dict[str, dict]` mit `rows` = Liste von dicts (session_id, line_index, seq,
  raw, source_label).

- [ ] **Step 1: Failing Tests**

`tests/test_compute.py`:

```python
import pytest

from collector import compute, db as cdb
from tests.test_db_worm_and_chain import _mk_tenant_agent


def _rec(session_id, uuid, line_index, raw, parent=None):
    import json
    from collector.canon import record_sha256_hex
    return {"session_id": session_id, "record_uuid": uuid,
            "parent_uuid": parent, "line_index": line_index,
            "captured_at": "2026-07-07T12:00:00Z",
            "record_sha256": record_sha256_hex(raw), "sig_b64": "c2ln",
            "pubkey_id": "ed25519:0000000000000000", "raw": raw}


def _seed(db, superuser_db):
    tid = _mk_tenant_agent(superuser_db)
    agent_row = {"id": "agt_x", "tenant_name": "t1"}
    items = [
        _rec("s1", "u1", 1, {"type": "user", "uuid": "u1", "parentUuid": None,
                             "sessionId": "s1", "cwd": "/home/x/proj",
                             "timestamp": "2026-07-07T10:00:00Z",
                             "message": {"role": "user", "content": "hi"}}),
        _rec("s1", "u2", 2, {"type": "assistant", "uuid": "u2",
                             "parentUuid": "u1", "sessionId": "s1",
                             "timestamp": "2026-07-07T10:00:05Z",
                             "message": {"model": "claude-sonnet-5",
                                         "usage": {"input_tokens": 10,
                                                   "output_tokens": 5},
                                         "content": []}}, parent="u1"),
        # uuid-lose Zeile (synth) - darf die Engine nicht stoeren
        _rec("s1", "synth:aaa", 3, {"type": "mode", "mode": "x",
                                    "sessionId": "s1"}),
        # Subagent-Session + Sidecar
        _rec("agent-a1", "v1", 1, {"type": "user", "uuid": "v1",
                                   "parentUuid": None, "sessionId": "s1",
                                   "timestamp": "2026-07-07T10:01:00Z",
                                   "message": {"role": "user",
                                               "content": "sub"}}),
        _rec("agent-a1", "synth:side", 1,
             {"type": "x-meta-sidecar", "file": "agent-a1.meta.json",
              "content": {"agentType": "reviewer", "description": "rev d"}}),
    ]
    cdb.insert_chained(db, tid, agent_row, items)
    db.commit()
    return tid


def test_rebuild_tenant_basic(db, superuser_db):
    tid = _seed(db, superuser_db)
    data = compute.rebuild_tenant(db, tid)
    # Subagent wird in den Parent absorbiert -> 1 Session im Dashboard
    assert data["kpi"]["total_sessions"] == 1
    sess = data["sessions"][0]
    assert sess["session_id"] == "s1"
    assert sess["source"] == "t1-src"
    assert data["kpi"]["total_messages"] >= 2


def test_rebuild_subagent_metadata(db, superuser_db):
    tid = _seed(db, superuser_db)
    data = compute.rebuild_tenant(db, tid)
    sess = data["sessions"][0]
    subs = sess.get("subagents", [])
    assert len(subs) == 1
    assert subs[0].get("agent_type") == "reviewer" or \
        subs[0].get("type") == "reviewer"


def test_rebuild_project_name_munged(db, superuser_db):
    tid = _seed(db, superuser_db)
    data = compute.rebuild_tenant(db, tid)
    assert any("-home-x-proj" in (p.get("project_dir") or p.get("name", ""))
               for p in [data["sessions"][0]]) or \
        data["sessions"][0]["project_dir"] == "-home-x-proj"
```

Hinweis an den Implementer: `_mk_tenant_agent` setzt source_label des Agents
nicht - erweitere die Helper-Nutzung: nach `_mk_tenant_agent` ein
`superuser_db.execute("UPDATE agents SET source_label='t1-src' WHERE id='agt_x'")`
in `_seed` (der Test oben erwartet `t1-src`). Die exakten Assertions zu
subagents/project_dir dürfen an die realen Engine-Feldnamen angepasst werden
(nachschauen in `claudestats_core.sessions._absorb_subagent` bzw.
`aggregate`-Session-Dict) - die Substanz (1 Session, Subagent absorbiert mit
Typ "reviewer", project_dir gemunged) ist bindend. Anpassungen im Report
dokumentieren.

Run: erwartetes FAIL (kein Modul collector.compute).

- [ ] **Step 2: Implementieren**

`collector/compute.py`:

```python
"""Server-Compute-Driver: Records aus Postgres -> claudestats_core-Engine.

Spiegelt die Datei-Driver-Semantik von extract_stats.parse_session_transcripts:
eine session_id entspricht einer Transcript-Datei; line_index gibt die
Zeilenreihenfolge; Subagent-Sessions heissen agent-<id>; Sidecar-Records
(x-meta-sidecar) tragen agentType/description und sind KEINE Transcript-Zeilen.
Naeherungen (dokumentiert, im Kalibrierungs-Beweis normalisiert):
file_size = Summe der canon(raw)-Laengen; project_name aus raw.cwd gemunged.
"""
from claudestats_core import (SessionFileMeta, absorb_file,
                              build_dashboard_data, finalize_sessions)

from .canon import canon


def _munge_project_name(cwd: str) -> str:
    return cwd.replace("/", "-") if cwd else ""


def _sessions_from_records(rows) -> dict:
    by_session = {}
    for row in rows:
        by_session.setdefault(row["session_id"], []).append(row)

    sessions = {}
    for session_id, rws in by_session.items():
        rws.sort(key=lambda r: (r["line_index"], r["seq"]))
        raws, sidecar = [], None
        for r in rws:
            raw = r["raw"]
            if isinstance(raw, dict) and raw.get("type") == "x-meta-sidecar":
                sidecar = raw
            else:
                raws.append(raw)
        is_subagent = session_id.startswith("agent-")
        parent_id = ""
        if is_subagent:
            parent_id = next((r.get("sessionId") for r in raws
                              if isinstance(r.get("sessionId"), str)), "") or ""
        cwd = next((r.get("cwd") for r in raws
                    if isinstance(r.get("cwd"), str) and r.get("cwd")), "")
        sidecar_content = (sidecar or {}).get("content", {}) or {}
        meta = SessionFileMeta(
            source_label=rws[0]["source_label"],
            file_session_id=session_id,
            project_name=_munge_project_name(cwd),
            file_size=sum(len(canon(r)) for r in raws),
            is_subagent=is_subagent,
            parent_session_id=parent_id,
            agent_id=session_id[len("agent-"):] if is_subagent else "",
            agent_type=str(sidecar_content.get("agentType", "") or ""),
            agent_description=str(sidecar_content.get("description", "") or ""),
        )
        absorb_file(sessions, meta, raws)
    return sessions


def rebuild_tenant(conn, tenant_id: int) -> dict:
    rows = conn.execute(
        "SELECT r.session_id, r.line_index, r.seq, r.raw,"
        " a.source_label"
        " FROM records r JOIN agents a ON a.id = r.agent_id"
        " WHERE r.tenant_id = %s"
        " ORDER BY r.session_id, r.line_index, r.seq",
        (tenant_id,)).fetchall()
    sessions = _sessions_from_records(rows)
    finalize_sessions(sessions)
    return build_dashboard_data(sessions, {}, {}, [])
```

(Falls `build_dashboard_data` weitere Pflicht-Loader-Strukturen verlangt -
sichtbar als KeyError/TypeError im Testlauf - die None-/Leer-Defaults exakt
wie in dessen Signatur nachziehen und im Report dokumentieren; NIE Engine-Code
anfassen.)

- [ ] **Step 3: Tests grün** -> `.venv/bin/pytest tests/ -q` (55 erwartet)

- [ ] **Step 4: Commit**

```bash
git add collector/compute.py tests/test_compute.py
git commit -m "feat(compute): rebuild_tenant - records to engine dashboard"
```

---

### Task 3: dashboard_cache + `GET /v1/dashboard`

**Files:**
- Create: `sql/003_dashboard_cache.sql`
- Modify: `collector/app.py`, README (Endpunkt-Tabelle + Trigger-Abweichung)
- Test: `tests/test_dashboard_endpoint.py`

**Interfaces:**
- `GET /v1/dashboard?tenant=<name>` - Auth wie chain/head (Admin ODER Agent
  desselben Tenants, auth-before-existence). Response:
  `{"tenant", "as_of_seq", "built_at", "data": <dashboard-json>}`.
  Cache-Hit wenn `dashboard_cache.as_of_seq == tenant_heads.last_seq`,
  sonst `rebuild_tenant` + Upsert.

- [ ] **Step 1: Schema**

`sql/003_dashboard_cache.sql`:

```sql
\set ON_ERROR_STOP on
CREATE TABLE IF NOT EXISTS dashboard_cache (
  tenant_id  BIGINT PRIMARY KEY REFERENCES tenants(id),
  as_of_seq  BIGINT NOT NULL,
  built_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  data       JSONB NOT NULL
);
GRANT SELECT, INSERT, UPDATE ON dashboard_cache TO collector_app;
```

Einspielen in beide DBs:

```bash
docker exec -i audit-collector-db psql -U postgres -d audit      < sql/003_dashboard_cache.sql
docker exec -i audit-collector-db psql -U postgres -d audit_test < sql/003_dashboard_cache.sql
```

- [ ] **Step 2: Failing Tests**

`tests/test_dashboard_endpoint.py` (nutzt die bestehenden Fixtures/Helper aus
test_ingest: `client`, `enrolled`, `_wrapped`, `_auth`):

```python
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", os.environ.get(
    "DATABASE_URL_TEST",
    "postgresql://collector_app:collector_dev_pw@localhost:5433/audit_test"))
os.environ.setdefault("ADMIN_TOKEN", "test-admin")

from collector.app import app
from tests.test_ingest import _auth, _wrapped, client, enrolled  # noqa: F401


def _ingest_one(client, enrolled, uuid="u1", li=1):
    rec = _wrapped(enrolled, "s1",
                   {"uuid": uuid, "type": "user", "sessionId": "s1",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "message": {"role": "user", "content": "hi"}}, li)
    r = client.post("/v1/ingest", json={"records": [rec]},
                    headers=_auth(enrolled))
    assert r.json()["results"][0]["status"] == "accepted"


def test_dashboard_builds_and_caches(db, client, enrolled):
    _ingest_one(client, enrolled)
    r = client.get("/v1/dashboard", params={"tenant": "aeternalabs"},
                   headers=_auth(enrolled))
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_seq"] == 1
    assert body["data"]["kpi"]["total_sessions"] == 1
    built_first = body["built_at"]
    # zweiter Aufruf ohne neuen Ingest -> Cache-Hit, built_at unveraendert
    r2 = client.get("/v1/dashboard", params={"tenant": "aeternalabs"},
                    headers=_auth(enrolled))
    assert r2.json()["built_at"] == built_first


def test_dashboard_invalidates_on_new_ingest(db, client, enrolled):
    _ingest_one(client, enrolled)
    r1 = client.get("/v1/dashboard", params={"tenant": "aeternalabs"},
                    headers=_auth(enrolled))
    _ingest_one(client, enrolled, uuid="u2", li=2)
    r2 = client.get("/v1/dashboard", params={"tenant": "aeternalabs"},
                    headers=_auth(enrolled))
    assert r2.json()["as_of_seq"] == 2
    assert r2.json()["built_at"] != r1.json()["built_at"]


def test_dashboard_auth(db, client, enrolled):
    _ingest_one(client, enrolled)
    assert client.get("/v1/dashboard",
                      params={"tenant": "aeternalabs"}).status_code == 401
    r = client.get("/v1/dashboard", params={"tenant": "aeternalabs"},
                   headers={"Authorization": "Bearer test-admin"})
    assert r.status_code == 200
```

- [ ] **Step 3: Endpoint implementieren** (`collector/app.py` ergänzen)

```python
from . import compute


@app.get("/v1/dashboard")
def dashboard(tenant: str, conn=Depends(get_conn),
              authorization: str | None = Header(default=None)):
    settings = load_settings()
    is_admin = secrets.compare_digest(authorization or "",
                                      f"Bearer {settings.admin_token}")
    if not is_admin:
        agent = require_agent(conn, authorization)
    tid = cdb.get_tenant_id(conn, tenant)
    if tid is None:
        raise HTTPException(status_code=404, detail="unknown_tenant")
    if not is_admin and agent["tenant_id"] != tid:
        raise HTTPException(status_code=403, detail="wrong_tenant")
    head = cdb.head(conn, tid)
    row = conn.execute(
        "SELECT as_of_seq, built_at, data FROM dashboard_cache"
        " WHERE tenant_id = %s", (tid,)).fetchone()
    if row and row["as_of_seq"] == head["seq"]:
        return {"tenant": tenant, "as_of_seq": row["as_of_seq"],
                "built_at": str(row["built_at"]), "data": row["data"]}
    data = compute.rebuild_tenant(conn, tid)
    row = conn.execute(
        "INSERT INTO dashboard_cache (tenant_id, as_of_seq, data)"
        " VALUES (%s, %s, %s)"
        " ON CONFLICT (tenant_id) DO UPDATE SET as_of_seq = excluded.as_of_seq,"
        " built_at = now(), data = excluded.data"
        " RETURNING as_of_seq, built_at",
        (tid, head["seq"], _json.dumps(data, ensure_ascii=False,
                                       default=str))).fetchone()
    return {"tenant": tenant, "as_of_seq": row["as_of_seq"],
            "built_at": str(row["built_at"]), "data": data}
```

- [ ] **Step 4: Tests grün** (58 erwartet), README ergänzen, Commit

```bash
git add sql/003_dashboard_cache.sql collector/app.py tests/test_dashboard_endpoint.py README.md
git commit -m "feat(compute): /v1/dashboard with seq-keyed cache (lazy rebuild)"
```

---

### Task 4: E2E-Kalibrierungs-Beweis (Datei-Weg == DB-Weg)

**Files:**
- Test: `tests/test_calibration_e2e.py`

Der Abschluss-Beweis des Gesamtsystems (Plan-1-Task-8-Versprechen): dieselben
JSONL-Daten einmal in Datei-Driver-Semantik direkt durch die Engine, einmal
über Agent -> Server -> `rebuild_tenant`. Nach definierter Normalisierung
müssen beide Dashboards identisch sein.

- [ ] **Step 1: Test schreiben**

`tests/test_calibration_e2e.py`:

```python
"""Kalibrierungs-Beweis: Datei-Weg == DB-Weg.

Weg A: Engine direkt mit Datei-Driver-Semantik (Meta aus Pfad + meta.json,
       file_size aus stat) - so arbeitet extract_stats.py.
Weg B: agent enroll+scan -> uvicorn-Server -> compute.rebuild_tenant.

Normalisierung (dokumentierte Naeherungen des DB-Wegs):
- alle "file_size"-Werte -> 0 (stat vs canon-Summe)
- "generated_at" entfernt
"""
import json
import subprocess
import sys

import pytest

from collector import compute
from tests.test_agent_e2e import (_mk_claude_tree, _mint, _run_cli, server)  # noqa: F401


def _normalize(obj):
    if isinstance(obj, dict):
        return {k: (0 if k == "file_size" else _normalize(v))
                for k, v in obj.items() if k != "generated_at"}
    if isinstance(obj, list):
        return [_normalize(x) for x in obj]
    return obj


def _way_a_files(tmp_path):
    import claudestats_core as core
    proj = tmp_path / "projects" / "-home-x-demo"
    sessions = {}
    for jsonl in sorted(proj.rglob("*.jsonl")):
        is_sub = "/subagents/" in str(jsonl)
        meta_kwargs = {}
        if is_sub:
            mp = jsonl.with_suffix(".meta.json")
            if mp.exists():
                mj = json.loads(mp.read_text(encoding="utf-8"))
                meta_kwargs = {"agent_type": mj.get("agentType", "") or "",
                               "agent_description": mj.get("description", "") or ""}
        objs = []
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                objs.append(json.loads(line))
        sid = (jsonl.stem if is_sub
               else next((o.get("sessionId") for o in objs
                          if o.get("sessionId")), jsonl.stem))
        meta = core.SessionFileMeta(
            source_label="cortex:andie", file_session_id=sid,
            project_name=jsonl.parent.parent.name if is_sub
            else jsonl.parent.name,
            file_size=jsonl.stat().st_size,
            is_subagent=is_sub,
            parent_session_id=jsonl.parent.parent.name if is_sub else "",
            agent_id=jsonl.stem[len("agent-"):] if is_sub else "",
            **meta_kwargs)
        core.absorb_file(sessions, meta, objs)
    core.finalize_sessions(sessions)
    return core.build_dashboard_data(sessions, {}, {}, [])


def test_file_way_equals_db_way(db, server, tmp_path):
    tok = _mint(db)
    _mk_claude_tree(tmp_path)

    # Weg B: Agent -> Server -> rebuild
    cfg = tmp_path / "agent" / "config.json"
    assert _run_cli(["enroll", "--server", server,
                     "--enrollment-token", tok,
                     "--source-label", "cortex:andie",
                     "--projects-dir", str(tmp_path / "projects"),
                     "--config", str(cfg)]).returncode == 0
    assert _run_cli(["scan", "--config", str(cfg)]).returncode == 0
    tid = db.execute("SELECT id FROM tenants WHERE name='aeternalabs'"
                     ).fetchone()["id"]
    way_b = compute.rebuild_tenant(db, tid)

    # Weg A: Datei-Semantik direkt
    way_a = _way_a_files(tmp_path)

    na, nb = _normalize(way_a), _normalize(way_b)
    assert na["kpi"] == nb["kpi"], (na["kpi"], nb["kpi"])
    assert len(na["sessions"]) == len(nb["sessions"])
    for sa, sb in zip(
            sorted(na["sessions"], key=lambda s: s["session_id"]),
            sorted(nb["sessions"], key=lambda s: s["session_id"])):
        assert sa == sb, (sa["session_id"],
                          {k: (sa[k], sb.get(k)) for k in sa
                           if sa[k] != sb.get(k)})
    assert na == nb
```

Hinweis: Das Fixture `_mk_claude_tree` stammt aus dem Agent-E2E; der
project_name-Vergleich funktioniert, weil Weg A hier bewusst dieselbe
Munging-Quelle nutzt wie der CLI-Driver (Verzeichnisname `-home-x-demo`) und
das Fixture-cwd... ACHTUNG: `_mk_claude_tree`-Records haben KEIN cwd-Feld ->
Weg B liefert project_name "" via cwd-Munging, Weg A liefert den
Verzeichnisnamen. Damit der Beweis nicht an dieser dokumentierten Näherung
scheitert: das Fixture wird NICHT geändert (es gehört dem Agent-E2E);
stattdessen erweitert der Test die Normalisierung um project-Namensfelder
ODER (besser, bindend): Weg A übergibt `project_name=""` für nicht-Subagent-
Dateien, wenn keine cwd in den Records steckt - exakt die DB-Weg-Semantik.
Der Implementer entscheidet sich für EINE Variante, begründet sie im Report,
und die KPI-/Session-Gleichheit bleibt in voller Schärfe bestehen.

- [ ] **Step 2: RED bestätigen, dann grün laufen lassen**

Der Test ist von Anfang an lauffähig (keine neue Produktionslogik) - er IST
der Beweis. Wenn er fehlschlägt, ist das ein ECHTER Kalibrierungs-Diff
zwischen Datei- und DB-Weg: analysieren, Ursache im Report dokumentieren,
BLOCKED melden, wenn die Ursache eine Semantik-Lücke im compute-Driver ist
(z.B. Ordering, Sidecar-Handling). NIEMALS per Normalisierung wegdefinieren,
was kein dokumentierter Näherungsfall ist.

Run: `.venv/bin/pytest tests/test_calibration_e2e.py -q -x` dann volle Suite
(59 erwartet).

- [ ] **Step 3: Commit**

```bash
git add tests/test_calibration_e2e.py
git commit -m "test: calibration proof - file-driver way equals db-compute way"
```

---

## Self-Review (beim Planschreiben durchgeführt)

1. **Spec-Abdeckung:** §12-Punkt "Kern-Architektur umgesetzt; Server-Driver
   liest aus dem Store" (Tasks 2-3), Architektur-Rechenmodell "inkrementell
   auf Session-Granularität, materialisiert pro Tenant" - v0-Vereinfachung:
   Lazy-Full-Rebuild mit seq-Cache statt Session-Dirty-Marking; bei
   Dev-Volumen identisches Ergebnis, dokumentierte Abweichung inkl. Debounce
   (Entscheidung 6) im Architektur-Doc nachzutragen, wenn Andie sie abnickt.
   Plan-1-Task-8-Versprechen (CLI vs Server auf denselben Daten) via Task 4.
2. **Platzhalter-Scan:** Code vollständig; zwei explizit als
   Implementer-Entscheidung markierte Stellen (Engine-Feldnamen-Assertions
   Task 2, project_name-Variante Task 4) sind bewusste, eng umzäunte
   Freiheitsgrade mit Berichtspflicht.
3. **Konsistenz:** rebuild_tenant-Row-Shape == compute-SQL == Test-Seeds;
   Dashboard-Endpoint nutzt bestehende Auth-Muster (compare_digest,
   auth-before-existence); Cache-Key = tenant_heads.last_seq == head()["seq"].
