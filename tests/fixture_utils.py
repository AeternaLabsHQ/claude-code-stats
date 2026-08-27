"""Shared helpers for parser-level integration tests: write minimal JSONL
fixtures into temp dirs and point extract_stats' module globals at them.
This pattern is validated against the real parser (see plan probes)."""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es
import claudestats_core.settings as core_settings

STD_PLAN = {"plan": "Max 5x", "start": "2026-01-01", "end": None,
            "cost_usd": 100.0, "billing_day": 2, "billing_cycle": "monthly"}


def user_line(session_id="S1", ts="2026-06-10T10:00:00Z", text="hello world"):
    return {"type": "user", "sessionId": session_id, "timestamp": ts,
            "message": {"role": "user", "content": text}}


def assistant_line(session_id="S1", ts="2026-06-10T10:00:05Z", msg_id="m1",
                   model="claude-opus-4-8", output_tokens=100, content=None,
                   usage_extra=None):
    usage = {"input_tokens": 10, "output_tokens": output_tokens,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    if usage_extra:
        usage.update(usage_extra)
    return {"type": "assistant", "sessionId": session_id, "timestamp": ts,
            "uuid": "u-" + msg_id,
            "message": {"id": msg_id, "model": model,
                        "content": (content if content is not None
                                    else [{"type": "text", "text": "hi"}]),
                        "usage": usage}}


def write_jsonl(path, objs):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(o) for o in objs) + "\n",
                    encoding="utf-8")


@contextmanager
def patched_cache(cache_dir=None):
    """Point the scan cache at a temp dir, so a test run never reads or
    writes the real .cache/ next to extract_stats.py. Without this every
    parse in the suite would leave state behind for the next one."""
    import tempfile
    cache_dir = Path(cache_dir or tempfile.mkdtemp(prefix="cs-cache-"))
    saved = (es.CACHE_DIR, es.CACHE_PATH, es.PAGE_CACHE_PATH)
    es.CACHE_DIR = cache_dir
    es.CACHE_PATH = cache_dir / "scan_cache.json"
    es.PAGE_CACHE_PATH = cache_dir / "page_cache.json"
    try:
        yield cache_dir
    finally:
        (es.CACHE_DIR, es.CACHE_PATH, es.PAGE_CACHE_PATH) = saved


@contextmanager
def patched_sources(primary_dir, additional=None, plan_history=None,
                    cache_dir=None):
    """Point extract_stats' module globals at temp fixture dirs (hermetic:
    the user's real config.json values are saved and restored)."""
    saved = (es.PROJECTS_DIR, es.MIGRATION_ENABLED, es.ADDITIONAL_SOURCES,
             es.SOURCE_LABEL, es.PLAN_HISTORY)
    saved_core = (core_settings.SOURCE_LABEL, core_settings.PLAN_HISTORY)
    cache_ctx = patched_cache(cache_dir)
    cache_ctx.__enter__()
    es.PROJECTS_DIR = Path(primary_dir)
    es.MIGRATION_ENABLED = False
    es.ADDITIONAL_SOURCES = additional or []
    es.SOURCE_LABEL = "current"
    core_settings.SOURCE_LABEL = "current"
    es.PLAN_HISTORY = [dict(STD_PLAN)] if plan_history is None else plan_history
    core_settings.PLAN_HISTORY = es.PLAN_HISTORY
    try:
        yield es
    finally:
        (es.PROJECTS_DIR, es.MIGRATION_ENABLED, es.ADDITIONAL_SOURCES,
         es.SOURCE_LABEL, es.PLAN_HISTORY) = saved
        (core_settings.SOURCE_LABEL, core_settings.PLAN_HISTORY) = saved_core
        cache_ctx.__exit__(None, None, None)
