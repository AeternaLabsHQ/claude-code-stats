# Plan 5: Raw-Byte Format-Law Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the audit format law so `record_sha256` is computed over the verbatim raw JSONL line bytes (not over a re-serialized canonical JSON form), transport the bytes as base64 (`raw_b64`), store them verbatim as `BYTEA`, and remove `canon()` from the record path entirely.

**Architecture:** Today `record_sha256 = sha256(canon(parsed_json))`, which forces every agent language to reproduce Python's canonical JSON serialization byte-for-byte (the classic cross-language footgun, Spec §4). Option B (Andie-approved 2026-07-07) makes the hash input the exact line bytes as read from disk. Because those exact bytes now travel over the wire and are stored verbatim, verification re-hashes the stored bytes with no re-serialization, so a producer's serialization choice becomes a private detail of that producer. Any language can then implement a conformant agent with only `sha256(bytes)` + `ed25519(bytes)` — no canonicalization. This also makes storage *more* faithful to Spec §1 ("raw JSONL verbatim"): the previous `JSONB` column silently reordered keys, dropped duplicate keys, and normalized whitespace; `BYTEA` does none of that.

**Tech Stack:** Python 3.10+, FastAPI, psycopg3, Postgres 17, `cryptography` (Ed25519), pytest. Repo: `/home/andie/projects/audit-collector` (NO remote, never push).

## Global Constraints

- **The format law is the contract.** `bind`, `sig`, and `chain_hash` formulas are UNCHANGED (pure byte concatenation, `collector/chain.py` + `collector/crypto.py`). ONLY the definition of `record_sha256` changes, and its single ripple through the callers.
- **Record bytes = verbatim.** A record's bytes are the bytes of one JSONL line *between* `\n` separators, taken verbatim with NO transformation. A trailing `\r` (CRLF file) is PART of the record bytes and must NOT be stripped before hashing. Any stripping reintroduces the cross-language ambiguity this change exists to kill.
- **`record_sha256 = sha256(record_bytes).hexdigest()`** (lowercase hex).
- **`raw_b64 = base64.b64encode(record_bytes).decode("ascii")`** — RFC 4648 standard alphabet, WITH padding, NO line breaks (Python `base64.b64encode` default). Decode with `base64.b64decode`.
- **Sidecar records** (`type: "x-meta-sidecar"`) are agent-constructed, not read from a file. The agent serializes the sidecar dict to bytes with `json.dumps(obj, ensure_ascii=False).encode("utf-8")`; those exact bytes ARE the record bytes, stored verbatim. The serialization choice is private to the agent because the bytes travel and are stored verbatim — no cross-agent canonical agreement is required.
- **`file_size` approximation** (compute driver): `sum(len(record_bytes))` over non-sidecar records of a session (no newline added). This is normalized to `0` on both sides of the calibration proof, so the value is advisory only; state it explicitly so implementers do not guess.
- **Ingest validation** preserves current behavior exactly plus the byte-decode gate. Order per record: (1) `agent_mismatch`; (2) base64 decode of `raw_b64` must succeed else `bad_raw_b64`; (3) decoded bytes must `json.loads` to a `dict` else `raw_not_json` (this preserves the old `raw: dict` pydantic invariant); (4) `sha256(decoded_bytes)` must equal `record_sha256` else `sha256_mismatch`; (5) signature via `verify_bind` else `bad_signature`. Do NOT add record_uuid-content re-verification — it was not present before; keep behavior minimal and faithful.
- **No data migration.** Nothing is deployed; this is a clean break. Delete the old canon-based vectors entirely — do not keep them as a second source of truth.
- **Semantic dedup consequence** (document, do not code around): under `canon`, two byte-different but semantically identical serializations of the same `record_uuid` deduped as `duplicate`; under raw bytes they now yield `duplicate_mismatch`. For attestation this is stricter and correct (changed bytes = changed content), but a `dos2unix`'d or re-synced file will now raise mismatches. This is a documented property, handled in Task 4.
- **Reviewer/implementer model tiers:** implementers on sonnet; task reviewers on opus for Tasks 1-3 (format-law + wire + calibration are integrity-critical), sonnet for Task 4 (docs); final whole-branch review on fable.

## Reference Vectors (authoritative — computed with the real `collector.chain` module)

The canonical reference record is the UTF-8 encoding of this exact JSON text (compact, no spaces), which is **195 bytes**:

```
{"type":"user","uuid":"11111111-2222-3333-4444-555555555555","parentUuid":null,"sessionId":"aaaabbbb-cccc-dddd-eeee-ffff00001111","message":{"role":"user","content":"Testvektor: ümlaut & 🎯"}}
```

| Quantity | Value |
|---|---|
| `len(record_bytes)` | `195` |
| `record_sha256` | `393bc3b3103dcb2f097bf5dcf2cc15fe18d89c8daa4da70ba2759e155caae949` |
| `raw_b64` | `eyJ0eXBlIjoidXNlciIsInV1aWQiOiIxMTExMTExMS0yMjIyLTMzMzMtNDQ0NC01NTU1NTU1NTU1NTUiLCJwYXJlbnRVdWlkIjpudWxsLCJzZXNzaW9uSWQiOiJhYWFhYmJiYi1jY2NjLWRkZGQtZWVlZS1mZmZmMDAwMDExMTEiLCJtZXNzYWdlIjp7InJvbGUiOiJ1c2VyIiwiY29udGVudCI6IlRlc3R2ZWt0b3I6IMO8bWxhdXQgJiDwn46vIn19` |
| `bind_hex("aeternalabs", sessionId, uuid, record_sha256)` | `23a40c94cc7126993d555d91b9583cf5bbec753e94df2afd08c336eac2d33601` |
| `chain_hash_hex(GENESIS, bind, "ed25519:abababababababab", "PLACEHOLDER")` | `121c7229e7ffe8ba0a764825cf20b6b8c48b8f401e92bba09991fe26052573cf` |

Verbatim-ness vectors (pin that NO transformation happens):

| Case | `record_bytes` | `record_sha256` |
|---|---|---|
| CRLF (trailing `\r` kept) | canonical bytes + `b"\r"` | `cc46a7a2ba62fba53671b26c16016f06d561f2c3283e1238916f66586a5c0bbf` |
| Minimal ASCII | `b'{"a":1}'` | `015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862` |

The Ed25519 signature vector and keypair round-trip in `tests/test_canon_chain_crypto.py` are INDEPENDENT of the record hash (they sign a literal bind string) and stay unchanged.

---

### Task 1: New raw-byte hash primitive + reference vectors (additive)

Land the new law function and pin the new vectors WITHOUT touching any caller. The old `collector/canon.py` and its dict-based `record_sha256_hex` stay in place this task, so the suite stays fully green (old path intact, new path independently tested). This isolates the constitutional change for its own reviewer gate before the cutover consumes the constants.

**Files:**
- Modify: `collector/crypto.py` (add `record_sha256_hex(raw_bytes: bytes) -> str`)
- Test: `tests/test_record_hash_vectors.py` (create)

**Interfaces:**
- Produces: `collector.crypto.record_sha256_hex(raw_bytes: bytes) -> str` — lowercase hex sha256 of the given bytes. This is the permanent home of the record-hash law; the identically-named dict-based function in `collector/canon.py` is transitional and deleted in Task 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_record_hash_vectors.py`:

```python
import base64

from collector.crypto import record_sha256_hex
from collector.chain import GENESIS, bind_hex, chain_hash_hex

LINE_STR = ('{"type":"user","uuid":"11111111-2222-3333-4444-555555555555",'
            '"parentUuid":null,'
            '"sessionId":"aaaabbbb-cccc-dddd-eeee-ffff00001111",'
            '"message":{"role":"user","content":"Testvektor: ümlaut & \U0001f3af"}}')
LINE_BYTES = LINE_STR.encode("utf-8")
SID = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
UUID = "11111111-2222-3333-4444-555555555555"


def test_record_sha256_over_raw_bytes():
    assert len(LINE_BYTES) == 195
    assert record_sha256_hex(LINE_BYTES) == \
        "393bc3b3103dcb2f097bf5dcf2cc15fe18d89c8daa4da70ba2759e155caae949"


def test_raw_b64_roundtrip():
    b64 = base64.b64encode(LINE_BYTES).decode("ascii")
    assert base64.b64decode(b64) == LINE_BYTES
    assert record_sha256_hex(base64.b64decode(b64)) == \
        "393bc3b3103dcb2f097bf5dcf2cc15fe18d89c8daa4da70ba2759e155caae949"


def test_bind_over_raw_byte_hash():
    rs = record_sha256_hex(LINE_BYTES)
    assert bind_hex("aeternalabs", SID, UUID, rs) == \
        "23a40c94cc7126993d555d91b9583cf5bbec753e94df2afd08c336eac2d33601"


def test_chain_over_raw_byte_bind():
    assert chain_hash_hex(GENESIS,
        "23a40c94cc7126993d555d91b9583cf5bbec753e94df2afd08c336eac2d33601",
        "ed25519:abababababababab", "PLACEHOLDER") == \
        "121c7229e7ffe8ba0a764825cf20b6b8c48b8f401e92bba09991fe26052573cf"


def test_verbatim_crlf_not_stripped():
    assert record_sha256_hex(LINE_BYTES + b"\r") == \
        "cc46a7a2ba62fba53671b26c16016f06d561f2c3283e1238916f66586a5c0bbf"
    # A trailing CR changes the hash — proves no stripping.
    assert record_sha256_hex(LINE_BYTES + b"\r") != record_sha256_hex(LINE_BYTES)


def test_verbatim_minimal_ascii():
    assert record_sha256_hex(b'{"a":1}') == \
        "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/andie/projects/audit-collector && python -m pytest tests/test_record_hash_vectors.py -v`
Expected: FAIL with `ImportError: cannot import name 'record_sha256_hex' from 'collector.crypto'`.

- [ ] **Step 3: Add the primitive**

Append to `collector/crypto.py` (it already imports `hashlib`):

```python
def record_sha256_hex(raw_bytes: bytes) -> str:
    """Format law (Spec §4): the record hash is sha256 over the VERBATIM raw
    line bytes. No canonicalization — the exact bytes travel and are stored,
    so any language reproduces this with sha256(bytes)."""
    return hashlib.sha256(raw_bytes).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/andie/projects/audit-collector && python -m pytest tests/test_record_hash_vectors.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `cd /home/andie/projects/audit-collector && python -m pytest -q`
Expected: all previously-passing tests still pass (old canon path untouched); 6 new tests added.

- [ ] **Step 6: Commit**

```bash
cd /home/andie/projects/audit-collector
git add collector/crypto.py tests/test_record_hash_vectors.py
git commit -m "feat(format): add raw-byte record_sha256_hex primitive + reference vectors"
```

---

### Task 2: Server-side cutover to raw_b64 + BYTEA

Migrate the wire model, ingest path, DB storage/export, compute driver, and verifier to the raw-byte law. Because the E2E and calibration tests drive the *agent* (still producing the old wire this task), temporarily skip exactly those two with a reason pointing to Task 3. Everything else stays green.

**Files:**
- Modify: `collector/models.py:26-38` (WrapperRecord: `raw: dict` → `raw_b64: str`)
- Modify: `collector/app.py:14` (import), `collector/app.py:58-99` (ingest), `collector/app.py:121-137` (export)
- Modify: `collector/db.py:35-76` (insert_chained raw bytes), `collector/db.py:101-113` (export_iter)
- Modify: `sql/002_tables.sql:54` (`raw JSONB` → `raw BYTEA`)
- Modify: `collector/compute.py:7-13` (docstring + imports), `collector/compute.py:29-47` (parse bytes, file_size)
- Modify: `tools/verifier.py:24` (import), `tools/verifier.py:68` (hash raw_b64)
- Modify: `tests/test_canon_chain_crypto.py` (drop dead canon-vector assertions; see Step 1)
- Modify: `tests/test_ingest.py`, `tests/test_db_worm_and_chain.py`, `tests/test_export_verifier.py`, `tests/test_compute.py`, `tests/test_dashboard_endpoint.py` (construct `raw_b64` instead of `raw`)
- Modify: `tests/test_agent_e2e.py`, `tests/test_calibration_e2e.py` (add skip marker — un-skipped in Task 3)

**Interfaces:**
- Consumes: `collector.crypto.record_sha256_hex(raw_bytes: bytes)` from Task 1.
- Produces: wire field `raw_b64: str` on `WrapperRecord`; `records.raw` column is `BYTEA`; `export_iter` yields rows whose `raw` is `bytes`/memoryview; `/v1/export` ndjson lines carry key `raw_b64` (base64 string) and NO `raw` key; `compute.rebuild_tenant` reads bytes.

- [ ] **Step 1: Reference-vector test cleanup**

In `tests/test_canon_chain_crypto.py` DELETE the now-dead `test_canon_reference_vector` (it asserts `canon` length + dict-based `record_sha256_hex`) and remove `canon, record_sha256_hex` from the top-of-file import (`from collector.canon import canon, record_sha256_hex`). Also DELETE `test_bind_reference_vector` (its value is the old canon-based bind; the raw-byte bind vector now lives in `tests/test_record_hash_vectors.py`). In `test_chain_reference_vector`, replace the old bind literal `baebfb47...2e71` with the new one `23a40c94cc7126993d555d91b9583cf5bbec753e94df2afd08c336eac2d33601` and the expected chain hash `bf4937...f035` with `121c7229e7ffe8ba0a764825cf20b6b8c48b8f401e92bba09991fe26052573cf`. Leave `test_ed25519_reference_vector` and `test_keypair_roundtrip` untouched.

- [ ] **Step 2: Migrate the wire model**

In `collector/models.py`, change `WrapperRecord.raw`:

```python
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sig: str = Field(min_length=64)
    raw_b64: str = Field(min_length=1)
```

- [ ] **Step 3: Migrate ingest**

In `collector/app.py`, change the import on line 14 from `from .canon import record_sha256_hex` to `from .crypto import b64d, record_sha256_hex, verify_bind` (and remove the separate `from .crypto import b64d, verify_bind` on line 16). Rewrite the ingest per-record loop body (lines 65-85) so it decodes, validates, and stores bytes:

```python
    for i, rec in enumerate(body.records):
        if (rec.agent_id != agent["id"] or rec.pubkey_id != agent["pubkey_id"]
                or rec.tenant != agent["tenant_name"]):
            results[i] = {"record_uuid": rec.record_uuid,
                          "status": "rejected", "reason": "agent_mismatch"}
            continue
        try:
            raw_bytes = b64d(rec.raw_b64)
        except Exception:
            results[i] = {"record_uuid": rec.record_uuid,
                          "status": "rejected", "reason": "bad_raw_b64"}
            continue
        try:
            parsed = _json.loads(raw_bytes)
        except Exception:
            parsed = None
        if not isinstance(parsed, dict):
            results[i] = {"record_uuid": rec.record_uuid,
                          "status": "rejected", "reason": "raw_not_json"}
            continue
        if record_sha256_hex(raw_bytes) != rec.record_sha256:
            results[i] = {"record_uuid": rec.record_uuid,
                          "status": "rejected", "reason": "sha256_mismatch"}
            continue
        b = bind_hex(rec.tenant, rec.session_id, rec.record_uuid,
                     rec.record_sha256)
        if not verify_bind(pub_raw, b, rec.sig):
            results[i] = {"record_uuid": rec.record_uuid,
                          "status": "rejected", "reason": "bad_signature"}
            continue
        accepted_items.append((i, {
            "session_id": rec.session_id, "record_uuid": rec.record_uuid,
            "parent_uuid": rec.parent_uuid, "line_index": rec.line_index,
            "captured_at": rec.captured_at, "record_sha256": rec.record_sha256,
            "sig_b64": rec.sig, "pubkey_id": rec.pubkey_id,
            "raw_bytes": raw_bytes}))
```

- [ ] **Step 4: Migrate export serialization**

In `collector/app.py`, rewrite the `lines()` generator inside `export` (lines 132-135) so raw bytes become `raw_b64` and no `raw` key is emitted:

```python
    def lines():
        import base64 as _b64
        for row in cdb.export_iter(conn, tid, from_seq, to_seq):
            row["captured_at"] = str(row["captured_at"])
            row["raw_b64"] = _b64.b64encode(bytes(row.pop("raw"))).decode("ascii")
            yield _json.dumps(row, ensure_ascii=False, default=str) + "\n"
```

- [ ] **Step 5: Migrate DB insert + export column**

In `collector/db.py`, `insert_chained`: change the `raw`-writing element of the INSERT params (last item on line 68) from `json.dumps(it["raw"], ensure_ascii=False)` to `it["raw_bytes"]`. The `json` import at the top of `db.py` becomes unused there once this is the only user — if so, remove `import json` from `db.py`. `export_iter` (line 102-104) already selects `raw`; it now returns bytes/memoryview — no SQL change needed, but confirm the column list still contains `raw`.

- [ ] **Step 6: Migrate the schema**

In `sql/002_tables.sql` line 54 change `raw JSONB NOT NULL,` to `raw BYTEA NOT NULL,`. `dashboard_cache` in `sql/003_dashboard_cache.sql` stays `JSONB` (it holds computed output, not attested content — do NOT change it).

- [ ] **Step 7: Migrate compute**

In `collector/compute.py`: update the module docstring line 8 to read `file_size = Summe der len(raw-Bytes); project_name aus raw.cwd gemunged.`; remove `from .canon import canon` (line 13). Rewrite `_sessions_from_records` rows-parsing so each row's bytes are parsed once and their length captured:

```python
    sessions = {}
    for session_id, rws in by_session.items():
        rws.sort(key=lambda r: (r["line_index"], r["seq"]))
        raws, sidecar, raw_len_sum = [], None, 0
        for r in rws:
            raw_bytes = bytes(r["raw"])
            obj = json.loads(raw_bytes)
            if isinstance(obj, dict) and obj.get("type") == "x-meta-sidecar":
                sidecar = obj
            else:
                raws.append(obj)
                raw_len_sum += len(raw_bytes)
```

Add `import json` at the top of `compute.py`. In the `SessionFileMeta(...)` construction change `file_size=sum(len(canon(r)) for r in raws),` to `file_size=raw_len_sum,`.

- [ ] **Step 8: Migrate verifier**

In `tools/verifier.py`: change the import on line 24 from `from collector.canon import record_sha256_hex` to `from collector.crypto import b64d, record_sha256_hex` (and drop `b64d` from the line-26 crypto import to avoid a duplicate). Replace line 68 `rs = record_sha256_hex(r["raw"])` with:

```python
            rs = record_sha256_hex(b64d(r["raw_b64"]))
```

- [ ] **Step 9: Migrate the affected tests to raw_b64**

In `tests/test_ingest.py`, `tests/test_db_worm_and_chain.py`, `tests/test_export_verifier.py`, `tests/test_compute.py`, `tests/test_dashboard_endpoint.py`: wherever a wrapper/record is built with a `raw` dict, replace it so the record bytes are the source of truth. The canonical builder pattern to use everywhere (adapt to each test's local helper):

```python
import base64, json
from collector.crypto import record_sha256_hex

def make_record_fields(raw_obj):
    raw_bytes = json.dumps(raw_obj, ensure_ascii=False).encode("utf-8")
    return {
        "raw_b64": base64.b64encode(raw_bytes).decode("ascii"),
        "record_sha256": record_sha256_hex(raw_bytes),
    }
```

For `test_compute.py` (which inserts rows directly into the `records` table), insert `raw` as bytes: `json.dumps(raw_obj, ensure_ascii=False).encode("utf-8")` instead of a dict/JSON string, and compute `record_sha256` from those same bytes. For any assertion that read `row["raw"]` as a dict from export, update it to decode `row["raw_b64"]`.

- [ ] **Step 10: Skip the two agent-coupled E2E tests (temporary, un-done in Task 3)**

At the top of `tests/test_agent_e2e.py` and `tests/test_calibration_e2e.py` add a module-level skip:

```python
import pytest
pytestmark = pytest.mark.skip(
    reason="agent wire cutover pending Plan 5 Task 3 (raw_b64)")
```

- [ ] **Step 11: Run the suite**

Run: `cd /home/andie/projects/audit-collector && python -m pytest -q`
Expected: all tests pass; `test_agent_e2e` and `test_calibration_e2e` reported as skipped. No failures. (Postgres must be up: `docker compose up -d`.)

- [ ] **Step 12: Manual server round-trip sanity (no agent)**

Run this inline check (uses the test DB fixture path already exercised by `test_export_verifier.py`) to confirm ingest→export→verifier works end-to-end on the new wire:

Run: `cd /home/andie/projects/audit-collector && python -m pytest tests/test_export_verifier.py -v`
Expected: PASS — export emits `raw_b64`, verifier re-hashes decoded bytes, chain verifies (rc 0).

- [ ] **Step 13: Commit**

```bash
cd /home/andie/projects/audit-collector
git add collector/models.py collector/app.py collector/db.py collector/compute.py \
        sql/002_tables.sql tools/verifier.py tests/
git commit -m "feat(format): cut server, storage, export, compute, verifier to raw_b64/BYTEA"
```

---

### Task 3: Agent-side cutover + delete canon + un-skip E2E

Make the agent emit `raw_b64` over the raw-byte law: the scanner must return the verbatim line bytes, the wrapper hashes those bytes and carries `raw_b64`, and sidecars serialize their own bytes. Then un-skip the two E2E tests and delete the now-dead `canon.py`.

**Files:**
- Modify: `agent/scanner.py:59-76` (return verbatim line bytes)
- Modify: `agent/wrapper.py:1-70` (import, `build_wrapper`, `build_sidecar_wrapper`)
- Modify: `agent/cli.py:85-99` (thread bytes into wrapper builders)
- Modify: `tests/test_agent_state_scanner.py`, `tests/test_agent_wrapper_config.py`, `tests/test_agent_client_cli.py` (new scanner tuple + wrapper `raw_b64`)
- Modify: `tests/test_agent_e2e.py`, `tests/test_calibration_e2e.py` (REMOVE the skip added in Task 2; migrate their wrapper construction to `raw_b64`)
- Delete: `collector/canon.py`

**Interfaces:**
- Consumes: `collector.crypto.record_sha256_hex(raw_bytes: bytes)`.
- Produces: `scanner.read_new_lines` returns `(parsed, new_offset, line_index, identity)` where `parsed` is a list of `(line_index, raw_bytes, obj)` triples (`raw_bytes` = verbatim line bytes, `obj` = parsed dict). `build_wrapper(raw_bytes, obj, *, ...)` and `build_sidecar_wrapper(...)` emit wrappers with a `raw_b64` field and no `raw` field.

- [ ] **Step 1: Write failing scanner test**

In `tests/test_agent_state_scanner.py` add a test that pins verbatim bytes (adapt the existing fixture that writes a `.jsonl` and calls `read_new_lines`):

```python
def test_read_new_lines_returns_verbatim_bytes(tmp_path, agent_conn):
    p = tmp_path / "s.jsonl"
    line = '{"uuid":"u1","sessionId":"s","x":"ä"}'
    p.write_text(line + "\n", encoding="utf-8")
    parsed, off, li, identity = scanner.read_new_lines(agent_conn, p)
    assert len(parsed) == 1
    idx, raw_bytes, obj = parsed[0]
    assert raw_bytes == line.encode("utf-8")   # verbatim, no re-encode
    assert obj == {"uuid": "u1", "sessionId": "s", "x": "ä"}
```

(Use whatever fixture name the existing scanner tests use for the SQLite connection; match the file's conventions.)

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /home/andie/projects/audit-collector && python -m pytest tests/test_agent_state_scanner.py::test_read_new_lines_returns_verbatim_bytes -v`
Expected: FAIL — current `parsed` items are `(line_index, obj)` 2-tuples, unpack into 3 fails / `raw_bytes` wrong.

- [ ] **Step 3: Migrate the scanner to keep bytes**

In `agent/scanner.py`, rewrite the parsing loop (lines 61-76) so the verbatim `rawline` bytes are preserved and returned. The emptiness check may `strip()` but the RETURNED/HASHED bytes must be the unstripped `rawline`:

```python
    parsed = []
    for rawline in buf[:end + 1].split(b"\n"):
        if not rawline.strip():
            continue
        line_index += 1
        try:
            obj = json.loads(rawline.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            print(f"  WARN: {path.name}: Zeile {line_index} kein JSON, "
                  f"uebersprungen (v0-Limitation)", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            print(f"  WARN: {path.name}: Zeile {line_index} kein Objekt, "
                  f"uebersprungen", file=sys.stderr)
            continue
        parsed.append((line_index, rawline, obj))
    return parsed, offset + end + 1, line_index, identity
```

Note: `rawline` is the verbatim bytes between `\n` boundaries and INCLUDES a trailing `\r` if the file is CRLF — that is intentional (Global Constraints: verbatim). Hash the `rawline`, not a stripped/re-encoded form.

- [ ] **Step 4: Run scanner test to confirm pass**

Run: `cd /home/andie/projects/audit-collector && python -m pytest tests/test_agent_state_scanner.py -v`
Expected: PASS (existing scanner tests may need their tuple-unpacking updated to 3-tuples — update them in this step to match).

- [ ] **Step 5: Migrate the wrapper**

Rewrite `agent/wrapper.py`. `build_wrapper` now takes the verbatim bytes plus the parsed object (the object is only used to extract `uuid`/`parentUuid`, never to re-hash):

```python
"""Wrapper-Records bauen (Spec §4 + Architektur-Entscheidungen 1-3).

record_sha256 = sha256(rohe Zeilen-Bytes verbatim); raw reist als raw_b64.
Keine Kanonisierung mehr - die exakten Bytes werden transportiert und
gespeichert. Importiert das Format-Gesetz aus collector.* - NIE kopieren.
"""
import base64
import hashlib
import json

from collector.chain import bind_hex
from collector.crypto import record_sha256_hex, sign_bind


def synth_record_uuid(session_id: str, line_index: int,
                      record_sha256: str) -> str:
    h = hashlib.sha256(
        f"{session_id}:{line_index}:{record_sha256}".encode("utf-8")
    ).hexdigest()
    return f"synth:{h}"


def extract_session_id(raw: dict, file_stem: str, is_subagent: bool) -> str:
    if is_subagent:
        return file_stem
    sid = raw.get("sessionId")
    return sid if isinstance(sid, str) and sid else file_stem


def build_wrapper(raw_bytes: bytes, obj: dict, *, session_id: str,
                  line_index: int, captured_at: str, identity: dict,
                  priv_raw: bytes) -> dict:
    rs = record_sha256_hex(raw_bytes)
    uuid = obj.get("uuid")
    record_uuid = (uuid if isinstance(uuid, str) and uuid
                   else synth_record_uuid(session_id, line_index, rs))
    parent = obj.get("parentUuid")
    b = bind_hex(identity["tenant"], session_id, record_uuid, rs)
    return {
        "agent_id": identity["agent_id"],
        "pubkey_id": identity["pubkey_id"],
        "tenant": identity["tenant"],
        "seat": {"machine": identity["machine"],
                 "os_user": identity["os_user"],
                 "source_label": identity["source_label"]},
        "session_id": session_id,
        "record_uuid": record_uuid,
        "parent_uuid": parent if isinstance(parent, str) and parent else None,
        "line_index": line_index,
        "captured_at": captured_at,
        "record_sha256": rs,
        "sig": sign_bind(priv_raw, b),
        "raw_b64": base64.b64encode(raw_bytes).decode("ascii"),
    }


def build_sidecar_wrapper(sidecar_json: dict, *, file_name: str,
                          agent_file_stem: str, captured_at: str,
                          identity: dict, priv_raw: bytes) -> dict:
    obj = {"type": "x-meta-sidecar", "file": file_name,
           "content": sidecar_json}
    raw_bytes = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return build_wrapper(raw_bytes, obj, session_id=agent_file_stem,
                         line_index=1, captured_at=captured_at,
                         identity=identity, priv_raw=priv_raw)
```

- [ ] **Step 6: Migrate the CLI call sites**

In `agent/cli.py`, update the scan loop (around lines 94-99) to unpack the 3-tuple and pass both bytes and object:

```python
                parsed, new_offset, new_li, identity = (
                    scanner.read_new_lines(conn, path))
                for line_index, raw_bytes, raw in parsed:
                    session_id = extract_session_id(raw, file_stem, is_subagent)
                    wrappers.append(build_wrapper(
                        raw_bytes, raw, session_id=session_id,
                        line_index=line_index, captured_at=captured_at,
                        identity=ident, priv_raw=priv))
```

(Match the exact variable names the surrounding CLI code already uses for `new_offset`/`new_li`/state persistence — only the loop unpacking and the `build_wrapper` call change.)

- [ ] **Step 7: Migrate agent unit tests**

In `tests/test_agent_wrapper_config.py` and `tests/test_agent_client_cli.py`: update every `build_wrapper(...)` call to the new signature `build_wrapper(raw_bytes, obj, ...)`, and assert the wrapper carries `raw_b64` (decode it and compare to `raw_bytes`) instead of a `raw` dict. Where a test previously passed a dict, derive `raw_bytes = json.dumps(obj, ensure_ascii=False).encode("utf-8")` and pass both.

- [ ] **Step 8: Un-skip and migrate the E2E + calibration tests**

Remove the `pytestmark = pytest.mark.skip(...)` lines added in Task 2 from `tests/test_agent_e2e.py` and `tests/test_calibration_e2e.py`. Migrate any wrapper/record construction inside them to the new `build_wrapper` signature / `raw_b64` wire. The calibration test's core assertion (file-way KPIs `==` db-way KPIs, strict, with `file_size` normalized to 0) must remain unchanged in intent and still pass.

- [ ] **Step 9: Delete the dead canon module**

Run: `cd /home/andie/projects/audit-collector && grep -rn "canon" collector/ agent/ tools/ tests/`
Expected: NO remaining references except possibly comments. If clean, delete the file:

```bash
cd /home/andie/projects/audit-collector && git rm collector/canon.py
```

If `grep` still finds a live import, fix it before deleting.

- [ ] **Step 10: Run the full suite (no skips)**

Run: `cd /home/andie/projects/audit-collector && python -m pytest -q`
Expected: ALL tests pass, ZERO skips (the two E2E tests now run and pass). Postgres up.

- [ ] **Step 11: Full manual agent round-trip**

Run: `cd /home/andie/projects/audit-collector && python -m pytest tests/test_agent_e2e.py tests/test_calibration_e2e.py -v`
Expected: PASS — enroll → scan → export → verifier `--expected-head` (rc 0), and file-way == db-way calibration equality holds.

- [ ] **Step 12: Commit**

```bash
cd /home/andie/projects/audit-collector
git add agent/ tools/ tests/ collector/canon.py
git commit -m "feat(format): cut agent to raw_b64, delete canon, restore E2E/calibration"
```

---

### Task 4: Documentation, spec, and memory

Record the format-law change everywhere it is documented, honestly note the dedup consequence, and update the architecture Änderungsprotokoll and spec §4. No code.

**Files:**
- Modify: `/home/andie/projects/audit-collector/README.md` (format-law section, integrity layers, dedup consequence)
- Modify: `/home/andie/projects/audit-collector/docs/FOLLOWUPS.md` (accepted residual risk: byte-strict dedup consequence)
- Modify: `docs/superpowers/plans/audit-collector-v0.md` (Spec §4 — record hash definition; this worktree)
- Modify: `docs/superpowers/plans/audit-collector-v0-architektur.md` (Änderungsprotokoll + new decision entry)

**Interfaces:** None (docs).

- [ ] **Step 1: README format-law section**

Update the README's format-law / integrity description: `record_sha256` is now `sha256` over the verbatim raw JSONL line bytes; the wire carries `raw_b64` (base64, RFC 4648, padded); the server stores `raw` as `BYTEA` verbatim; the verifier re-hashes the decoded bytes. State explicitly that this REMOVES the cross-language canonicalization requirement — a conformant agent in any language needs only `sha256(bytes)` + Ed25519, and that `BYTEA` verbatim storage is strictly more faithful to Spec §1 than the previous `JSONB`. Remove any lingering reference to `canon` in the record path.

- [ ] **Step 2: README dedup-consequence line**

Add one honest sentence: under byte-strict hashing, two byte-different but semantically identical serializations of the same `record_uuid` now yield `duplicate_mismatch` (not `duplicate`); a `dos2unix` or re-sync of a source file can therefore raise mismatches. This is correct for attestation (changed bytes = changed content).

- [ ] **Step 3: FOLLOWUPS residual risk**

Under "Akzeptierte Restrisiken" in `docs/FOLLOWUPS.md`, add: byte-strict dedup — re-encoded/re-synced source files raise `duplicate_mismatch` where canon-based dedup did not; intended, documented, feeds the Observability ticket's mismatch logging.

- [ ] **Step 4: Spec §4 correction**

In `docs/superpowers/plans/audit-collector-v0.md` §4, update the record-hash definition to the raw-byte law (was canon-based). Keep the change surgical and mark it with a dated correction note in the same style as the earlier §5 correction (commit `6aedf67`). Do NOT rewrite unrelated spec prose.

- [ ] **Step 5: Architecture doc decision entry + Änderungsprotokoll**

In `docs/superpowers/plans/audit-collector-v0-architektur.md`, add a new decision entry (raw-byte format law, Option B, Andie-approved 2026-07-07) and an Änderungsprotokoll line dated 2026-07-07 recording: motivation (dependency-free cross-platform agents), the byte-boundary rule, `raw_b64`/`BYTEA`, `canon` removal, and the dedup consequence.

- [ ] **Step 6: Commit (audit-collector docs)**

```bash
cd /home/andie/projects/audit-collector
git add README.md docs/FOLLOWUPS.md
git commit -m "docs: raw-byte format law, dedup consequence, integrity note"
```

- [ ] **Step 7: Commit (claude-stats plan/spec/architecture docs)**

```bash
cd /home/andie/projects/claude-stats/.claude/worktrees/core-extraction
git add docs/superpowers/plans/audit-collector-v0.md \
        docs/superpowers/plans/audit-collector-v0-architektur.md \
        docs/superpowers/plans/2026-07-07-plan5-raw-byte-format-law.md
git commit -m "docs(audit): plan 5 + spec §4 raw-byte law + architecture decision"
```

- [ ] **Step 8: Update memory (controller task, after final review)**

After the final whole-branch review passes, update `project_audit_collector_repo.md`: the format law is now raw-byte based (`record_sha256 = sha256(raw line bytes)`, `raw_b64` wire, `BYTEA` storage, `canon` removed); note this unblocks non-Python agents. Keep the "Agent/Verifier importieren dieselben Module" note but scope it to Python; the wire protocol + vectors are the actual cross-language contract.

---

## Self-Review

**1. Spec coverage:** §4 (format law) — the whole plan; the raw-byte definition + `raw_b64` + `BYTEA` cover it, spec text updated in Task 4. §1 (raw verbatim) — strengthened by `BYTEA`, noted in docs. §5 (bind/sig/chain) — unchanged formulas, vectors re-pinned (Tasks 1-2). §6 (verifier) — Task 2 Step 8. §11/§12 scope fence — unchanged; no new roadmap features pulled in. Calibration non-regression — Task 3 Step 8/11 keeps the file-way==db-way proof intact.

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". Every code step shows the code; every reference value is the authoritative computed constant; test code is complete. The one place that says "match the file's conventions" (scanner fixture name, CLI variable names) is because those are pre-existing local names the implementer reads in-file, not new content — acceptable.

**3. Type consistency:** `record_sha256_hex(raw_bytes: bytes) -> str` is used identically in Tasks 1 (define), 2 (server/verifier/compute), 3 (wrapper). `build_wrapper(raw_bytes, obj, *, ...)` signature in Task 3 Step 5 matches its call site in Step 6 and the scanner 3-tuple `(line_index, raw_bytes, obj)` produced in Step 3. Wire field `raw_b64` is consistent across models (Task 2 Step 2), ingest (Step 3), export (Step 4), verifier (Step 8), and wrapper (Task 3 Step 5). `it["raw_bytes"]` in the accepted-item dict (Task 2 Step 3) matches the DB insert (Step 5).
