#!/usr/bin/env python3
"""
Claude Code Usage Statistics Extractor
Parses all Claude Code data sources and generates a dashboard.

Note: The generated HTML uses innerHTML for rendering trusted, locally-generated
data only. No external/untrusted input is rendered as HTML. All user-provided
text (prompts) is escaped via textContent before display.
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"
CONFIG_EXAMPLE = Path(__file__).parent / "config.example.json"


def load_config():
    """Load config.json, exit with helpful message if missing."""
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        print(f"Copy {CONFIG_EXAMPLE.name} to {CONFIG_PATH.name} and adjust to your setup.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()


def load_locale(lang):
    """Load locale file for the given language."""
    locale_path = Path(__file__).parent / "locales" / f"{lang}.json"
    if not locale_path.exists():
        print(f"WARNING: Locale '{lang}' not found, falling back to 'en'")
        locale_path = Path(__file__).parent / "locales" / "en.json"
    with open(locale_path, "r", encoding="utf-8") as f:
        return json.load(f)


LANG = CONFIG.get("language", "en")
LOCALE = load_locale(LANG)

CLAUDE_DIR = Path(os.path.expanduser("~/.claude"))
PROJECTS_DIR = CLAUDE_DIR / "projects"
DOT_CLAUDE_JSON = Path(os.path.expanduser("~/.claude.json"))
STATS_CACHE = CLAUDE_DIR / "stats-cache.json"
HISTORY_JSONL = CLAUDE_DIR / "history.jsonl"

# ── Migration Backup (optional, configured in config.json) ───────────────
_mig = CONFIG.get("migration", {})
MIGRATION_ENABLED = _mig.get("enabled", False)
if MIGRATION_ENABLED and _mig.get("dir"):
    MIGRATION_DIR = Path(os.path.expanduser(_mig["dir"]))
    MIGRATION_CLAUDE_DIR = MIGRATION_DIR / _mig.get("claude_dir_name", ".claude-windows")
    MIGRATION_PROJECTS_DIR = MIGRATION_CLAUDE_DIR / "projects"
    MIGRATION_DOT_CLAUDE_JSON = MIGRATION_DIR / _mig.get("dot_claude_json_name", ".claude-windows.json")
    MIGRATION_STATS_CACHE = MIGRATION_CLAUDE_DIR / "stats-cache.json"
    MIGRATION_HISTORY_JSONL = MIGRATION_CLAUDE_DIR / "history.jsonl"
else:
    MIGRATION_ENABLED = False
    MIGRATION_DIR = None
    MIGRATION_CLAUDE_DIR = None
    MIGRATION_PROJECTS_DIR = None
    MIGRATION_DOT_CLAUDE_JSON = None
    MIGRATION_STATS_CACHE = None
    MIGRATION_HISTORY_JSONL = None

# ── Additional Sources (optional, configured in config.json) ──────────────
ADDITIONAL_SOURCES = []
for _src in CONFIG.get("additional_sources", []):
    _claude_dir = Path(_src["claude_dir"])
    _dot_claude_json = Path(_src["dot_claude_json"]) if _src.get("dot_claude_json") else None
    if _claude_dir.exists():
        ADDITIONAL_SOURCES.append({
            "label": _src.get("label", _claude_dir.name),
            "claude_dir": _claude_dir,
            "projects_dir": _claude_dir / "projects",
            "dot_claude_json": _dot_claude_json,
            "stats_cache": _claude_dir / "stats-cache.json",
            "history_jsonl": _claude_dir / "history.jsonl",
        })

VERSION = "0.7.0"

OUTPUT_DIR = Path(__file__).parent / "public"
DASHBOARD_DATA = OUTPUT_DIR / "dashboard_data.json"
DASHBOARD_HTML = OUTPUT_DIR / "index.html"
TEMPLATE_HTML = Path(__file__).parent / "dashboard_template.html"

# ── Plan Configuration (from config.json) ────────────────────────────────
PLAN_HISTORY = CONFIG.get("plan_history", [])

# ── Pricing (USD per 1M tokens) ───────────────────────────────────────────
PRICING = {
    # Claude 4.7
    "claude-opus-4-7": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.7"
    },
    # Claude 4.6
    "claude-opus-4-6": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.6"
    },
    "claude-sonnet-4-6": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4.6"
    },
    # Claude 4.5
    "claude-opus-4-5-20251101": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.5"
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4.5"
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.00, "output": 5.00,
        "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00,
        "display": "Haiku 4.5"
    },
    # Claude 4.1
    "claude-opus-4-1-20250805": {
        "input": 15.00, "output": 75.00,
        "cache_read": 1.50, "cache_write_5m": 18.75, "cache_write_1h": 30.00,
        "display": "Opus 4.1"
    },
    # Claude 4.0
    "claude-opus-4-20250514": {
        "input": 15.00, "output": 75.00,
        "cache_read": 1.50, "cache_write_5m": 18.75, "cache_write_1h": 30.00,
        "display": "Opus 4"
    },
    "claude-sonnet-4-20250514": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4"
    },
    # Claude 3.7
    "claude-sonnet-3-7-20250219": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 3.7"
    },
    # Claude 3.5
    "claude-haiku-3-5-20241022": {
        "input": 0.80, "output": 4.00,
        "cache_read": 0.08, "cache_write_5m": 1.00, "cache_write_1h": 1.60,
        "display": "Haiku 3.5"
    },
    # Claude 3
    "claude-3-opus-20240229": {
        "input": 15.00, "output": 75.00,
        "cache_read": 1.50, "cache_write_5m": 18.75, "cache_write_1h": 30.00,
        "display": "Opus 3"
    },
    "claude-3-haiku-20240307": {
        "input": 0.25, "output": 1.25,
        "cache_read": 0.03, "cache_write_5m": 0.30, "cache_write_1h": 0.50,
        "display": "Haiku 3"
    },
}

# Fallback for unknown models (use mid-range pricing)
DEFAULT_PRICING = {
    "input": 3.00, "output": 15.00,
    "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
    "display": "Unknown"
}


def get_model_display(model_id):
    return PRICING.get(model_id, DEFAULT_PRICING)["display"]


def calc_cost(model_id, usage):
    """Calculate cost for a single API call based on usage tokens.

    Uses the standard cache write rate (1.25x input price) for all cache
    creation tokens, matching Claude Code's own cost calculation.
    """
    p = PRICING.get(model_id, DEFAULT_PRICING)

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)

    cost = (
        input_tokens * p["input"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
        + cache_read * p["cache_read"] / 1_000_000
        + cache_creation * p["cache_write_5m"] / 1_000_000
    )
    return cost


def project_display_name(project_path):
    """Extract a short display name from a project path."""
    if not project_path:
        return "Unknown"
    p = project_path.replace("\\", "/")
    parts = p.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else project_path


def load_stats_cache():
    """Load stats-cache.json from all sources."""
    merged = {}
    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_STATS_CACHE)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["stats_cache"])
    sources.append(STATS_CACHE)
    for path in sources:
        if path and path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Additive merge of numeric counters
            for key in ("totalSessions", "totalMessages"):
                merged[key] = merged.get(key, 0) + data.get(key, 0)
            # Keep other fields from latest source
            for key, val in data.items():
                if key not in ("totalSessions", "totalMessages"):
                    merged[key] = val
    return merged


def load_dot_claude():
    """Load .claude.json from all sources, merge projects."""
    merged = {}
    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_DOT_CLAUDE_JSON)
    for _as in ADDITIONAL_SOURCES:
        if _as["dot_claude_json"]:
            sources.append(_as["dot_claude_json"])
    sources.append(DOT_CLAUDE_JSON)
    for path in sources:
        if not path or not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge projects dict (both sources contribute)
        if "projects" in data:
            merged.setdefault("projects", {}).update(data["projects"])
        # All other keys: latest (current) wins
        for key, val in data.items():
            if key != "projects":
                merged[key] = val
    # Sum numStartups from both
    total_startups = 0
    for path in sources:
        if not path or not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        total_startups += data.get("numStartups", 0)
    if total_startups:
        merged["numStartups"] = total_startups
    return merged


def load_history():
    """Load history.jsonl from all sources."""
    prompts = []
    seen_ids = set()
    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_HISTORY_JSONL)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["history_jsonl"])
    sources.append(HISTORY_JSONL)
    for path in sources:
        if not path or not path.exists():
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # Deduplicate by sessionId + timestamp
                    dedup_key = (obj.get("sessionId", ""), obj.get("timestamp", 0))
                    if dedup_key in seen_ids:
                        continue
                    seen_ids.add(dedup_key)
                    prompts.append({
                        "display": obj.get("display", ""),
                        "timestamp": obj.get("timestamp", 0),
                        "project": obj.get("project", ""),
                        "sessionId": obj.get("sessionId", ""),
                    })
                except json.JSONDecodeError:
                    continue
    prompts.sort(key=lambda p: p["timestamp"])
    return prompts


def load_plans():
    """Load plan files from all sources."""
    plans = []
    seen_filenames = set()
    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_CLAUDE_DIR)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["claude_dir"])
    sources.append(CLAUDE_DIR)
    for claude_dir in sources:
        plans_dir = claude_dir / "plans"
        if not plans_dir.exists():
            continue
        for md_file in sorted(plans_dir.glob("*.md")):
            if md_file.name in seen_filenames:
                continue
            seen_filenames.add(md_file.name)
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
                # Extract title from first heading
                title = md_file.stem
                for line in text.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                # Get creation time from file
                stat = md_file.stat()
                plans.append({
                    "filename": md_file.name,
                    "slug": md_file.stem,
                    "title": title,
                    "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "size_kb": round(stat.st_size / 1024, 1),
                    "lines": len(text.splitlines()),
                })
            except Exception:
                continue
    return plans


def load_plugins():
    """Load plugin data from all sources."""
    result = {"installed": [], "settings": {}, "marketplace_stats": []}
    seen_plugins = set()

    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_CLAUDE_DIR)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["claude_dir"])
    sources.append(CLAUDE_DIR)
    for claude_dir in sources:
        plugins_dir = claude_dir / "plugins"

        # Installed plugins
        installed_file = plugins_dir / "installed_plugins.json"
        if installed_file.exists():
            try:
                data = json.loads(installed_file.read_text(encoding="utf-8"))
                for name, versions in data.get("plugins", {}).items():
                    if not versions or name in seen_plugins:
                        continue
                    seen_plugins.add(name)
                    v = versions[0]  # Latest version
                    result["installed"].append({
                        "name": name,
                        "short_name": name.split("@")[0],
                        "marketplace": name.split("@")[1] if "@" in name else "",
                        "version": v.get("version", ""),
                        "installed_at": v.get("installedAt", ""),
                        "last_updated": v.get("lastUpdated", ""),
                    })
            except Exception:
                pass

        # Marketplace install counts (merge, latest wins)
        counts_file = plugins_dir / "install-counts-cache.json"
        if counts_file.exists():
            try:
                data = json.loads(counts_file.read_text(encoding="utf-8"))
                counts = {c["plugin"]: c["unique_installs"] for c in data.get("counts", [])}
                if isinstance(result["marketplace_stats"], dict):
                    result["marketplace_stats"].update(counts)
                else:
                    result["marketplace_stats"] = counts
            except Exception:
                pass

    # Settings from current installation only
    settings_file = CLAUDE_DIR / "settings.json"
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            result["settings"] = {
                "permission_mode": settings.get("permissions", {}).get("defaultMode", ""),
                "auto_updates": settings.get("autoUpdatesChannel", ""),
                "enabled_plugins": settings.get("enabledPlugins", {}),
            }
        except Exception:
            pass

    return result


def load_todos():
    """Load todo/task data from all sources."""
    total = 0
    completed = 0
    pending = 0
    files = 0
    seen_files = set()
    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_CLAUDE_DIR)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["claude_dir"])
    sources.append(CLAUDE_DIR)
    for claude_dir in sources:
        todos_dir = claude_dir / "todos"
        if not todos_dir.exists():
            continue
        for jf in todos_dir.glob("*.json"):
            if jf.name in seen_files:
                continue
            seen_files.add(jf.name)
            try:
                data = json.loads(jf.read_text(encoding="utf-8", errors="replace"))
                if not isinstance(data, list):
                    continue
                files += 1
                for item in data:
                    total += 1
                    st = item.get("status", "")
                    if st == "completed":
                        completed += 1
                    elif st in ("pending", "in_progress"):
                        pending += 1
            except Exception:
                continue
    return {"total": total, "completed": completed, "pending": pending, "files": files}


def load_file_history_stats():
    """Count files in file-history from all sources."""
    total_files = 0
    total_size = 0
    sessions = 0
    seen_sessions = set()
    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_CLAUDE_DIR)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["claude_dir"])
    sources.append(CLAUDE_DIR)
    for claude_dir in sources:
        fh_dir = claude_dir / "file-history"
        if not fh_dir.exists():
            continue
        for sess_dir in fh_dir.iterdir():
            if not sess_dir.is_dir():
                continue
            if sess_dir.name in seen_sessions:
                continue
            seen_sessions.add(sess_dir.name)
            sessions += 1
            for f in sess_dir.iterdir():
                if f.is_file():
                    total_files += 1
                    total_size += f.stat().st_size
    return {
        "total_files": total_files,
        "total_sessions": sessions,
        "total_size_mb": round(total_size / 1_048_576, 1),
    }


def calc_storage():
    """Calculate storage breakdown for ~/.claude/ + migration backup."""
    breakdown = {}
    total = 0

    # Current ~/.claude
    for item in CLAUDE_DIR.iterdir():
        try:
            if item.is_file():
                sz = item.stat().st_size
                breakdown[item.name] = sz
                total += sz
            elif item.is_dir():
                dir_size = 0
                for f in item.rglob("*"):
                    if f.is_file():
                        try:
                            dir_size += f.stat().st_size
                        except OSError:
                            pass
                breakdown[item.name + "/"] = dir_size
                total += dir_size
        except OSError:
            pass

    # Migration backup as single entry
    if MIGRATION_ENABLED and MIGRATION_CLAUDE_DIR and MIGRATION_CLAUDE_DIR.exists():
        migration_size = 0
        for f in MIGRATION_CLAUDE_DIR.rglob("*"):
            if f.is_file():
                try:
                    migration_size += f.stat().st_size
                except OSError:
                    pass
        if MIGRATION_DOT_CLAUDE_JSON and MIGRATION_DOT_CLAUDE_JSON.exists():
            try:
                migration_size += MIGRATION_DOT_CLAUDE_JSON.stat().st_size
            except OSError:
                pass
        if migration_size > 0:
            breakdown["_migration-backup/"] = migration_size
            total += migration_size

    # Additional sources as single entries
    for _as in ADDITIONAL_SOURCES:
        src_size = 0
        if _as["claude_dir"].exists():
            for f in _as["claude_dir"].rglob("*"):
                if f.is_file():
                    try:
                        src_size += f.stat().st_size
                    except OSError:
                        pass
        if _as["dot_claude_json"] and _as["dot_claude_json"].exists():
            try:
                src_size += _as["dot_claude_json"].stat().st_size
            except OSError:
                pass
        if src_size > 0:
            breakdown[f"_{_as['label']}/"] = src_size
            total += src_size

    # Sort by size descending
    sorted_items = sorted(breakdown.items(), key=lambda x: -x[1])
    return {
        "total_mb": round(total / 1_048_576, 1),
        "items": [{"name": k, "size_mb": round(v / 1_048_576, 2)} for k, v in sorted_items if v > 0],
    }


def load_telemetry():
    """Load telemetry data from all sources."""
    per_session = defaultdict(lambda: {
        "peak_rss_mb": 0, "peak_heap_mb": 0, "max_cpu_pct": 0,
        "max_uptime_s": 0, "event_count": 0,
    })
    env_info = {}

    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_CLAUDE_DIR)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["claude_dir"])
    sources.append(CLAUDE_DIR)

    for claude_dir in sources:
        tel_dir = claude_dir / "telemetry"
        if not tel_dir.exists():
            continue
        for tf in sorted(tel_dir.glob("*.json")):
            try:
                with open(tf, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ed = evt.get("event_data", {})
                        sid = ed.get("session_id", "")
                        if not sid:
                            continue

                        # Extract env info (take latest)
                        env = ed.get("env", {})
                        if env and not env_info:
                            env_info = {
                                "platform": env.get("platform", ""),
                                "node_version": env.get("node_version", ""),
                                "terminal": env.get("terminal", ""),
                                "arch": env.get("arch", ""),
                                "claude_version": env.get("version", ""),
                            }

                        proc_str = ed.get("process", "")
                        if not proc_str:
                            continue
                        try:
                            proc = json.loads(proc_str) if isinstance(proc_str, str) else proc_str
                        except (json.JSONDecodeError, TypeError):
                            continue

                        ps = per_session[sid]
                        ps["event_count"] += 1
                        rss_mb = round(proc.get("rss", 0) / 1_048_576, 1)
                        heap_mb = round(proc.get("heapUsed", 0) / 1_048_576, 1)
                        cpu_pct = round(proc.get("cpuPercent", 0), 1)
                        uptime_s = round(proc.get("uptime", 0))

                        if rss_mb > ps["peak_rss_mb"]:
                            ps["peak_rss_mb"] = rss_mb
                        if heap_mb > ps["peak_heap_mb"]:
                            ps["peak_heap_mb"] = heap_mb
                        if cpu_pct > ps["max_cpu_pct"]:
                            ps["max_cpu_pct"] = cpu_pct
                        if uptime_s > ps["max_uptime_s"]:
                            ps["max_uptime_s"] = uptime_s
            except Exception:
                continue

    return {
        "per_session": dict(per_session),
        "env_info": env_info,
        "total_events": sum(s["event_count"] for s in per_session.values()),
    }


def load_project_memories(skip_memories=False):
    """Load MEMORY.md files per project."""
    if skip_memories:
        return {}

    memories = {}
    sources = []
    if MIGRATION_ENABLED and MIGRATION_CLAUDE_DIR:
        proj_dir = MIGRATION_CLAUDE_DIR / "projects"
        if proj_dir.exists():
            sources.append(proj_dir)
    for _as in ADDITIONAL_SOURCES:
        if _as["projects_dir"].exists():
            sources.append(_as["projects_dir"])
    if PROJECTS_DIR.exists():
        sources.append(PROJECTS_DIR)

    for projects_dir in sources:
        for memory_file in projects_dir.rglob("memory/MEMORY.md"):
            project_dir_name = memory_file.parent.parent.name
            if project_dir_name in memories:
                continue
            try:
                content = memory_file.read_text(encoding="utf-8", errors="replace")
                memories[project_dir_name] = {
                    "content": content,
                    "size_kb": round(memory_file.stat().st_size / 1024, 1),
                    "lines": len(content.splitlines()),
                }
            except Exception:
                continue
    return memories


def load_tasks():
    """Load task management data from all sources."""
    all_tasks = []
    session_count = 0
    seen_sessions = set()

    sources = []
    if MIGRATION_ENABLED:
        sources.append(MIGRATION_CLAUDE_DIR)
    for _as in ADDITIONAL_SOURCES:
        sources.append(_as["claude_dir"])
    sources.append(CLAUDE_DIR)

    for claude_dir in sources:
        tasks_dir = claude_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for sess_dir in sorted(tasks_dir.iterdir()):
            if not sess_dir.is_dir() or sess_dir.name in seen_sessions:
                continue
            seen_sessions.add(sess_dir.name)
            task_files = sorted(
                [f for f in sess_dir.glob("*.json") if f.stem.isdigit()],
                key=lambda f: int(f.stem)
            )
            if not task_files:
                continue
            session_count += 1
            for tf in task_files:
                try:
                    task = json.loads(tf.read_text(encoding="utf-8", errors="replace"))
                    task["_session_id"] = sess_dir.name
                    all_tasks.append(task)
                except Exception:
                    continue

    status_counts = defaultdict(int)
    for t in all_tasks:
        status_counts[t.get("status", "unknown")] += 1

    return {
        "tasks": [{"subject": t.get("subject", ""), "status": t.get("status", ""), "session_id": t.get("_session_id", "")} for t in all_tasks],
        "session_count": session_count,
        "total": len(all_tasks),
        "status_counts": dict(status_counts),
        "completed": status_counts.get("completed", 0),
        "pending": status_counts.get("pending", 0),
        "in_progress": status_counts.get("in_progress", 0),
    }


def _categorize_error(msg: str, tool_name: str) -> str:
    """Categorize an error message into a human-readable category."""
    msg_lower = msg.lower()
    if "rejected" in msg_lower or "doesn't want to proceed" in msg_lower:
        return "rejected"
    if "does not exist" in msg_lower or "not found" in msg_lower or "no such file" in msg_lower:
        return "file_not_found"
    if "not unique" in msg_lower or "multiple occurrences" in msg_lower:
        return "edit_not_unique"
    if "no replacement was performed" in msg_lower or "old_string not found" in msg_lower:
        return "edit_no_match"
    if "permission" in msg_lower or "denied" in msg_lower:
        return "permission_denied"
    if "timeout" in msg_lower or "timed out" in msg_lower:
        return "timeout"
    if "command not found" in msg_lower:
        return "command_not_found"
    if "exit code" in msg_lower or "returned non-zero" in msg_lower:
        return "exit_code"
    if "syntaxerror" in msg_lower or "syntax error" in msg_lower:
        return "syntax_error"
    if "importerror" in msg_lower or "modulenotfounderror" in msg_lower:
        return "import_error"
    if "hook error" in msg_lower or "hook_error" in msg_lower:
        return "hook_error"
    if tool_name == "Edit":
        return "edit_failed"
    return "other"


def parse_session_transcripts():
    """Parse all session JSONL transcripts from all sources."""
    sessions = {}  # session_id -> session_data
    total_files = 0
    total_lines = 0

    sources = []
    if MIGRATION_ENABLED and MIGRATION_PROJECTS_DIR and MIGRATION_PROJECTS_DIR.exists():
        sources.append(("migration", MIGRATION_PROJECTS_DIR))
    for _as in ADDITIONAL_SOURCES:
        if _as["projects_dir"].exists():
            sources.append((_as["label"], _as["projects_dir"]))
    if PROJECTS_DIR.exists():
        sources.append(("current", PROJECTS_DIR))

    if not sources:
        print(f"  WARNING: No projects directories found")
        return sessions

    for source_label, projects_dir in sources:
        print(f"  Source: {source_label} ({projects_dir})")
        project_dirs = sorted(projects_dir.iterdir())
        total_dirs = len(project_dirs)

        for idx, project_dir in enumerate(project_dirs):
            if not project_dir.is_dir():
                continue

            project_name = project_dir.name
            jsonl_files = sorted(project_dir.rglob("*.jsonl"))

            if not jsonl_files:
                continue

            print(f"    [{idx+1}/{total_dirs}] {project_name} ({len(jsonl_files)} files)")

            for jsonl_file in jsonl_files:
                total_files += 1
                file_session_id = jsonl_file.stem
                file_size = jsonl_file.stat().st_size

                # Detect subagent sessions
                is_subagent = "/subagents/" in str(jsonl_file)
                parent_id = ""
                if is_subagent:
                    parent_id = jsonl_file.parent.parent.name

                # Skip if this session was already fully parsed from migration
                if file_session_id in sessions and source_label == "current":
                    # Same session file in both sources — skip duplicate
                    continue

                try:
                    with open(jsonl_file, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            total_lines += 1
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            msg_type = obj.get("type")
                            # For subagent files, use the file stem as session_id
                            # (the sessionId field points to the parent)
                            session_id = file_session_id if is_subagent else obj.get("sessionId", file_session_id)
                            timestamp = obj.get("timestamp")

                            if session_id not in sessions:
                                sessions[session_id] = {
                                    "session_id": session_id,
                                    "project_dir": project_name,
                                    "project_path": obj.get("cwd", ""),
                                    "timestamps": [],
                                    "models": defaultdict(lambda: {
                                        "input_tokens": 0,
                                        "output_tokens": 0,
                                        "cache_read_input_tokens": 0,
                                        "cache_creation_input_tokens": 0,
                                        "cache_5m_tokens": 0,
                                        "cache_1h_tokens": 0,
                                        "cost": 0.0,
                                        "calls": 0,
                                    }),
                                    "tools": defaultdict(int),
                                    "skills": defaultdict(int),
                                    "hooks": defaultdict(int),
                                    "compactions": 0,
                                    "compaction_events": [],
                                    "message_count": 0,
                                    "user_message_count": 0,
                                    "assistant_message_count": 0,
                                    "first_prompt": "",
                                    "file_size": file_size,
                                    "slug": obj.get("slug", ""),
                                    "source": source_label,
                                    "agent_dispatches": [],
                                    "subagents": [],
                                    "is_subagent": False,
                                    "parent_session_id": "",
                                    "error_count": 0,
                                    "errors": [],
                                    "file_ops": [],
                                    "git_ops": [],
                                }

                            sess = sessions[session_id]

                            # Mark subagent status (may be set multiple times, that's fine)
                            if is_subagent:
                                sess["is_subagent"] = True
                                sess["parent_session_id"] = parent_id

                            if obj.get("cwd") and not sess["project_path"]:
                                sess["project_path"] = obj["cwd"]

                            if obj.get("slug") and not sess["slug"]:
                                sess["slug"] = obj["slug"]

                            # Collect timestamps
                            if timestamp:
                                if isinstance(timestamp, str):
                                    try:
                                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                        ts_ms = int(dt.timestamp() * 1000)
                                        sess["timestamps"].append(ts_ms)
                                    except (ValueError, OSError):
                                        pass
                                elif isinstance(timestamp, (int, float)):
                                    sess["timestamps"].append(int(timestamp))

                            # User messages
                            if msg_type == "user":
                                sess["message_count"] += 1
                                sess["user_message_count"] += 1

                                # Extract errors from tool results
                                message = obj.get("message", {})
                                content = message.get("content", "")
                                if isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("is_error"):
                                            sess["error_count"] += 1
                                            error_msg = str(block.get("content", ""))
                                            if "<tool_use_error>" in error_msg:
                                                error_msg = error_msg.split("<tool_use_error>")[-1].split("</tool_use_error>")[0]
                                            tid = block.get("tool_use_id", "")
                                            tool_name = sess.get("_tool_id_map", {}).get(tid, "unknown")
                                            category = _categorize_error(error_msg, tool_name)
                                            sess["errors"].append({
                                                "message": error_msg[:200],
                                                "tool": tool_name,
                                                "category": category,
                                                "tool_use_id": tid,
                                                "timestamp": timestamp or "",
                                            })

                                if not sess["first_prompt"]:
                                    message = obj.get("message", {})
                                    content = message.get("content", "")
                                    if isinstance(content, str):
                                        text = content
                                    elif isinstance(content, list):
                                        text = ""
                                        for block in content:
                                            if isinstance(block, dict) and block.get("type") == "text":
                                                text = block.get("text", "")
                                                break
                                    else:
                                        text = ""

                                    if (text
                                        and not text.startswith("<command")
                                        and not text.startswith("<local-command")
                                        and not text.startswith("[Request interrupted")
                                        and "tool_result" not in str(content)[:100]):
                                        sess["first_prompt"] = text[:200]

                            # Assistant messages with token usage
                            elif msg_type == "assistant":
                                sess["message_count"] += 1
                                sess["assistant_message_count"] += 1

                                message = obj.get("message", {})
                                model = message.get("model", "unknown")
                                usage = message.get("usage", {})

                                if usage and usage.get("output_tokens", 0) > 0:
                                    m = sess["models"][model]
                                    m["input_tokens"] += usage.get("input_tokens", 0)
                                    m["output_tokens"] += usage.get("output_tokens", 0)
                                    m["cache_read_input_tokens"] += usage.get("cache_read_input_tokens", 0)
                                    m["cache_creation_input_tokens"] += usage.get("cache_creation_input_tokens", 0)

                                    cache_info = usage.get("cache_creation", {})
                                    m["cache_5m_tokens"] += cache_info.get("ephemeral_5m_input_tokens", 0)
                                    m["cache_1h_tokens"] += cache_info.get("ephemeral_1h_input_tokens", 0)

                                    m["cost"] += calc_cost(model, usage)
                                    m["calls"] += 1

                                for block in message.get("content", []):
                                    if isinstance(block, dict) and block.get("type") == "tool_use":
                                        tool_name = block.get("name", "unknown")
                                        # Map tool_use_id -> tool_name for error attribution
                                        tool_id = block.get("id", "")
                                        if tool_id:
                                            sess.setdefault("_tool_id_map", {})[tool_id] = tool_name
                                        sess["tools"][tool_name] += 1
                                        # Track skills specifically
                                        if tool_name == "Skill":
                                            skill_name = block.get("input", {}).get("skill", "unknown")
                                            sess["skills"][skill_name] += 1

                                        # Track agent dispatches
                                        if tool_name == "Agent":
                                            agent_input = block.get("input", {})
                                            sess["agent_dispatches"].append({
                                                "type": agent_input.get("subagent_type", "general-purpose"),
                                                "description": agent_input.get("description", ""),
                                            })

                                        # File operations
                                        if tool_name in ("Read", "Edit", "Write"):
                                            tool_input = block.get("input", {})
                                            file_path = tool_input.get("file_path", "")
                                            if file_path:
                                                sess["file_ops"].append({
                                                    "op": tool_name.lower(),
                                                    "path": file_path,
                                                    "timestamp": timestamp or "",
                                                })

                                        # Git operations from Bash
                                        if tool_name == "Bash":
                                            cmd = block.get("input", {}).get("command", "")
                                            if "git commit" in cmd:
                                                msg = ""
                                                if '-m "' in cmd:
                                                    msg = cmd.split('-m "')[1].split('"')[0]
                                                elif "-m '" in cmd:
                                                    msg = cmd.split("-m '")[1].split("'")[0]
                                                sess["git_ops"].append({"type": "commit", "message": msg[:200], "timestamp": timestamp or ""})
                                            elif "git push" in cmd:
                                                sess["git_ops"].append({"type": "push", "message": cmd[:200], "timestamp": timestamp or ""})
                                            elif "gh pr create" in cmd:
                                                sess["git_ops"].append({"type": "pr", "message": cmd[:200], "timestamp": timestamp or ""})

                            elif msg_type == "progress":
                                data_obj = obj.get("data", {})
                                if data_obj.get("type") == "hook_progress":
                                    hook_name = data_obj.get("hookName", "")
                                    if hook_name:
                                        sess["hooks"][hook_name] += 1

                            elif msg_type == "summary":
                                sess["compactions"] += 1
                                ts_str = ""
                                if timestamp:
                                    if isinstance(timestamp, str):
                                        ts_str = timestamp
                                    elif isinstance(timestamp, (int, float)):
                                        try:
                                            ts_str = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()
                                        except (ValueError, OSError):
                                            ts_str = str(timestamp)
                                sess["compaction_events"].append({"timestamp": ts_str})

                except Exception as e:
                    print(f"      ERROR reading {jsonl_file.name}: {e}")

    # Link subagents to parent sessions and remove from top-level
    subagent_ids = [sid for sid, s in sessions.items() if s.get("is_subagent")]
    for sub_id in subagent_ids:
        sub = sessions[sub_id]
        parent_id = sub.get("parent_session_id", "")
        if parent_id and parent_id in sessions:
            # Calculate subagent totals
            sub_tokens = sum(m["input_tokens"] + m["output_tokens"] for m in sub["models"].values())
            sub_cost = sum(m["cost"] for m in sub["models"].values())
            sessions[parent_id]["subagents"].append({
                "agent_id": sub["session_id"],
                "tokens": sub_tokens,
                "cost": round(sub_cost, 4),
                "messages": sub["message_count"],
                "tools": dict(sub["tools"]),
            })
        del sessions[sub_id]

    migration_count = sum(1 for s in sessions.values() if s.get("source") == "migration")
    current_count = sum(1 for s in sessions.values() if s.get("source") == "current")
    print(f"  Parsed {total_files} files, {total_lines} lines, {len(sessions)} sessions"
          f" (migration: {migration_count}, current: {current_count})")
    return sessions


def extract_session_messages(session_id, project_dir_name):
    """Extract per-message data for a single session for replay view."""
    messages = []

    # Search for the JSONL file
    sources = []
    if MIGRATION_ENABLED and MIGRATION_PROJECTS_DIR and MIGRATION_PROJECTS_DIR.exists():
        sources.append(MIGRATION_PROJECTS_DIR)
    for _as in ADDITIONAL_SOURCES:
        if _as["projects_dir"].exists():
            sources.append(_as["projects_dir"])
    if PROJECTS_DIR.exists():
        sources.append(PROJECTS_DIR)

    jsonl_path = None
    for projects_dir in sources:
        candidate = projects_dir / project_dir_name / f"{session_id}.jsonl"
        if candidate.exists():
            jsonl_path = candidate
            break
        # Also search subdirectories
        for f in (projects_dir / project_dir_name).rglob(f"{session_id}.jsonl"):
            jsonl_path = f
            break
        if jsonl_path:
            break

    if not jsonl_path:
        return messages

    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")
            timestamp = obj.get("timestamp", "")

            if msg_type == "user":
                message = obj.get("message", {})
                content = message.get("content", "")
                # Skip tool results
                if isinstance(content, list):
                    texts = []
                    is_tool_result = False
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "tool_result":
                                is_tool_result = True
                                break
                            if block.get("type") == "text":
                                texts.append(block.get("text", ""))
                    if is_tool_result:
                        continue
                    content = "\n".join(texts)

                if not content or content.startswith("<command") or content.startswith("<local-command"):
                    continue

                messages.append({
                    "role": "user",
                    "content": content,
                    "timestamp": timestamp,
                })

            elif msg_type == "assistant":
                message = obj.get("message", {})
                model = message.get("model", "unknown")
                usage = message.get("usage", {})
                content_blocks = message.get("content", [])

                text_parts = []
                tools = []
                for block in content_blocks:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            tool_input = block.get("input", {})
                            tool_info = {"name": tool_name}
                            if tool_name == "Bash":
                                tool_info["detail"] = tool_input.get("command", "")[:200]
                            elif tool_name in ("Read", "Edit", "Write"):
                                tool_info["detail"] = tool_input.get("file_path", "")
                            elif tool_name in ("Grep", "Glob"):
                                tool_info["detail"] = tool_input.get("pattern", "")
                            elif tool_name == "Skill":
                                tool_info["detail"] = tool_input.get("skill", "")
                            elif tool_name == "Agent":
                                tool_info["detail"] = tool_input.get("description", "")[:100]
                                tool_info["agent_type"] = tool_input.get("subagent_type", "general-purpose")
                                tool_info["agent_prompt"] = tool_input.get("prompt", "")[:2000]
                            tools.append(tool_info)

                text = "\n".join(text_parts)
                if not text and not tools:
                    continue

                messages.append({
                    "role": "assistant",
                    "content": text,
                    "model": get_model_display(model),
                    "tokens": {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                        "cache_read": usage.get("cache_read_input_tokens", 0),
                        "cache_write": usage.get("cache_creation_input_tokens", 0),
                    },
                    "cost": round(calc_cost(model, usage), 4),
                    "tools": tools,
                    "timestamp": timestamp,
                })

            elif msg_type == "progress":
                data_obj = obj.get("data", {})
                if data_obj.get("type") == "hook_progress":
                    messages.append({
                        "role": "hook",
                        "hook_event": data_obj.get("hookEvent", ""),
                        "hook_name": data_obj.get("hookName", ""),
                        "timestamp": timestamp,
                    })

            elif msg_type == "summary":
                messages.append({
                    "role": "compaction",
                    "timestamp": timestamp,
                })

    return messages


def _split_into_billing_cycles(start_str, end_str, billing_day):
    """Split a date range into monthly billing cycles based on billing_day."""
    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_str, "%Y-%m-%d")

    cycles = []
    cycle_start = start_dt

    while cycle_start <= end_dt:
        # Next billing date is billing_day of the following month
        if cycle_start.month == 12:
            next_billing = cycle_start.replace(
                year=cycle_start.year + 1, month=1, day=billing_day
            )
        else:
            next_billing = cycle_start.replace(
                month=cycle_start.month + 1, day=billing_day
            )

        cycle_end = min(next_billing - timedelta(days=1), end_dt)
        cycles.append((
            cycle_start.strftime("%Y-%m-%d"),
            cycle_end.strftime("%Y-%m-%d"),
        ))
        cycle_start = next_billing

    return cycles


def build_plan_analysis(daily_cost_series, session_list):
    """Analyze cost savings per plan period and current billing cycle."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    periods = []
    for ph in PLAN_HISTORY:
        start = ph["start"]
        end = ph["end"] or today
        billing_day = ph.get("billing_day")

        # Split into monthly billing cycles if billing_day is set
        if billing_day:
            cycles = _split_into_billing_cycles(start, end, billing_day)
        else:
            cycles = [(start, end)]

        for cycle_start, cycle_end in cycles:
            # Skip cycle that started today (handled by current_billing)
            if cycle_start == today:
                continue
            # Sum API costs in this cycle
            api_cost = sum(
                dc.get("total", 0)
                for dc in daily_cost_series
                if cycle_start <= dc["date"] <= cycle_end
            )

            # Count sessions and messages
            sess_in_period = [
                s for s in session_list
                if cycle_start <= s["date"] <= cycle_end
            ]
            session_count = len(sess_in_period)
            message_count = sum(s["messages"] for s in sess_in_period)
            days_active = len(set(s["date"] for s in sess_in_period))

            # Calculate days in period
            start_dt = datetime.strptime(cycle_start, "%Y-%m-%d")
            end_dt = datetime.strptime(cycle_end, "%Y-%m-%d")
            total_days = (end_dt - start_dt).days + 1

            plan_cost_usd = ph["cost_usd"]
            savings = api_cost - plan_cost_usd

            periods.append({
                "plan": ph["plan"],
                "start": cycle_start,
                "end": cycle_end,
                "total_days": total_days,
                "days_active": days_active,
                "plan_cost_eur": ph["cost_eur"],
                "plan_cost_usd": plan_cost_usd,
                "api_cost": round(api_cost, 2),
                "savings": round(savings, 2),
                "roi_factor": round(api_cost / plan_cost_usd, 1) if plan_cost_usd > 0 else 0,
                "sessions": session_count,
                "messages": message_count,
                "cost_per_day": round(api_cost / total_days, 2) if total_days > 0 else 0,
            })

    # Current billing period (from last billing day to now)
    current_plan = PLAN_HISTORY[-1]
    billing_day = current_plan.get("billing_day", 1)
    today_dt = datetime.now(timezone.utc)

    # Find current billing period start
    if today_dt.day >= billing_day:
        billing_start = today_dt.replace(day=billing_day)
    else:
        # Previous month
        if today_dt.month == 1:
            billing_start = today_dt.replace(year=today_dt.year - 1, month=12, day=billing_day)
        else:
            billing_start = today_dt.replace(month=today_dt.month - 1, day=billing_day)

    # Find next billing date
    if today_dt.month == 12:
        billing_end = billing_start.replace(year=billing_start.year + 1, month=1)
    else:
        billing_end = billing_start.replace(month=billing_start.month + 1)

    billing_start_str = billing_start.strftime("%Y-%m-%d")
    billing_end_str = billing_end.strftime("%Y-%m-%d")

    current_api_cost = sum(
        dc.get("total", 0)
        for dc in daily_cost_series
        if billing_start_str <= dc["date"] <= today
    )

    days_elapsed = (today_dt - billing_start).days + 1
    days_total = (billing_end - billing_start).days
    days_remaining = max(0, days_total - days_elapsed)

    # Project cost for full period
    if days_elapsed > 0:
        projected_cost = current_api_cost / days_elapsed * days_total
    else:
        projected_cost = 0

    current_sessions = [s for s in session_list if billing_start_str <= s["date"] <= today]

    current_billing = {
        "plan": current_plan["plan"],
        "period_start": billing_start_str,
        "period_end": billing_end_str,
        "days_elapsed": days_elapsed,
        "days_total": days_total,
        "days_remaining": days_remaining,
        "plan_cost_eur": current_plan["cost_eur"],
        "plan_cost_usd": current_plan["cost_usd"],
        "api_cost": round(current_api_cost, 2),
        "projected_cost": round(projected_cost, 2),
        "savings": round(current_api_cost - current_plan["cost_usd"], 2),
        "roi_factor": round(current_api_cost / current_plan["cost_usd"], 1) if current_plan["cost_usd"] > 0 else 0,
        "sessions": len(current_sessions),
        "messages": sum(s["messages"] for s in current_sessions),
        "cost_per_day": round(current_api_cost / days_elapsed, 2) if days_elapsed > 0 else 0,
    }

    # Total savings across all periods
    total_api = sum(p["api_cost"] for p in periods)
    total_plan = sum(p["plan_cost_usd"] for p in periods)

    return {
        "periods": periods,
        "current_billing": current_billing,
        "total_api_cost": round(total_api, 2),
        "total_plan_cost": round(total_plan, 2),
        "total_savings": round(total_api - total_plan, 2),
        "overall_roi": round(total_api / total_plan, 1) if total_plan > 0 else 0,
    }


def build_dashboard_data(sessions, stats_cache, dot_claude, history,
                         plans=None, plugins=None, todos=None,
                         file_history=None, storage=None,
                         telemetry=None, tasks=None, memories=None):
    """Aggregate all data into the dashboard data structure."""

    session_list = []

    daily_costs = defaultdict(lambda: defaultdict(float))
    daily_tokens = defaultdict(lambda: defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}))
    daily_messages = defaultdict(int)
    daily_sessions = defaultdict(int)
    hourly_messages = defaultdict(int)
    weekday_messages = defaultdict(int)
    project_stats = defaultdict(lambda: {
        "sessions": 0, "messages": 0, "cost": 0.0,
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "file_size": 0
    })
    model_totals = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "cost": 0.0, "calls": 0
    })
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    total_messages = 0

    for sid, sess in sessions.items():
        timestamps = sorted(sess["timestamps"])
        if not timestamps:
            continue

        start_ts = min(timestamps)
        end_ts = max(timestamps)

        start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
        date_str = start_dt.strftime("%Y-%m-%d")
        hour = start_dt.hour
        weekday = start_dt.weekday()

        duration_s = (end_ts - start_ts) / 1000

        session_cost = 0.0
        session_input = 0
        session_output = 0
        session_cache_read = 0
        session_cache_write = 0
        session_calls = 0
        model_breakdown = {}

        for model, mdata in sess["models"].items():
            session_cost += mdata["cost"]
            session_input += mdata["input_tokens"]
            session_output += mdata["output_tokens"]
            session_cache_read += mdata["cache_read_input_tokens"]
            session_cache_write += mdata["cache_creation_input_tokens"]
            session_calls += mdata["calls"]

            display_model = get_model_display(model)
            daily_costs[date_str][display_model] += mdata["cost"]

            daily_tokens[date_str][display_model]["input"] += mdata["input_tokens"]
            daily_tokens[date_str][display_model]["output"] += mdata["output_tokens"]
            daily_tokens[date_str][display_model]["cache_read"] += mdata["cache_read_input_tokens"]
            daily_tokens[date_str][display_model]["cache_write"] += mdata["cache_creation_input_tokens"]

            mt = model_totals[display_model]
            mt["input_tokens"] += mdata["input_tokens"]
            mt["output_tokens"] += mdata["output_tokens"]
            mt["cache_read_tokens"] += mdata["cache_read_input_tokens"]
            mt["cache_write_tokens"] += mdata["cache_creation_input_tokens"]
            mt["cost"] += mdata["cost"]
            mt["calls"] += mdata["calls"]

            model_breakdown[display_model] = {
                "cost": round(mdata["cost"], 4),
                "output_tokens": mdata["output_tokens"],
                "calls": mdata["calls"],
            }

        total_cost += session_cost
        total_input += session_input
        total_output += session_output
        total_cache_read += session_cache_read
        total_cache_write += session_cache_write
        total_messages += sess["message_count"]

        proj_name = project_display_name(sess["project_path"])
        ps = project_stats[proj_name]
        ps["sessions"] += 1
        ps["messages"] += sess["message_count"]
        ps["cost"] += session_cost
        ps["input_tokens"] += session_input
        ps["output_tokens"] += session_output
        ps["cache_read_tokens"] += session_cache_read
        ps["cache_write_tokens"] += session_cache_write
        ps["file_size"] += sess["file_size"]

        daily_messages[date_str] += sess["message_count"]
        daily_sessions[date_str] += 1
        hourly_messages[hour] += sess["user_message_count"]
        weekday_messages[weekday] += sess["user_message_count"]

        primary_model = "Unknown"
        max_output = 0
        for model, mdata in sess["models"].items():
            if mdata["output_tokens"] > max_output:
                max_output = mdata["output_tokens"]
                primary_model = get_model_display(model)

        session_list.append({
            "session_id": sid,
            "project": proj_name,
            "project_dir": sess["project_dir"],
            "date": date_str,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "duration_min": round(duration_s / 60, 1),
            "cost": round(session_cost, 4),
            "messages": sess["message_count"],
            "user_messages": sess["user_message_count"],
            "assistant_messages": sess["assistant_message_count"],
            "input_tokens": session_input,
            "output_tokens": session_output,
            "cache_read_tokens": session_cache_read,
            "cache_write_tokens": session_cache_write,
            "api_calls": session_calls,
            "primary_model": primary_model,
            "model_breakdown": model_breakdown,
            "tools": dict(sess["tools"]),
            "skills": dict(sess["skills"]),
            "hooks": dict(sess["hooks"]),
            "compactions": sess["compactions"],
            "compaction_events": sess["compaction_events"],
            "first_prompt": sess["first_prompt"],
            "slug": sess["slug"],
            "file_size_mb": round(sess["file_size"] / 1_048_576, 2),
            "agent_dispatches": sess.get("agent_dispatches", []),
            "subagents": sess.get("subagents", []),
            "error_count": sess.get("error_count", 0),
            "errors": [{"message": e["message"], "tool": e.get("tool", "unknown"), "category": e.get("category", "other"), "timestamp": e.get("timestamp", "")} for e in sess.get("errors", [])],
            "file_ops_count": len(sess.get("file_ops", [])),
            "git_ops": sess.get("git_ops", []),
        })

    session_list.sort(key=lambda s: s["start"])

    all_dates = sorted(set(
        list(daily_costs.keys()) + list(daily_messages.keys())
    ))

    all_models = sorted(model_totals.keys())

    daily_cost_series = []
    cumulative_cost = 0.0
    cumulative_series = []

    for d in all_dates:
        entry = {"date": d}
        day_total = 0.0
        for m in all_models:
            val = daily_costs[d].get(m, 0.0)
            entry[m] = round(val, 4)
            day_total += val
        entry["total"] = round(day_total, 4)
        daily_cost_series.append(entry)

        cumulative_cost += day_total
        cumulative_series.append({"date": d, "cost": round(cumulative_cost, 2)})

    daily_message_series = [
        {"date": d, "messages": daily_messages.get(d, 0), "sessions": daily_sessions.get(d, 0)}
        for d in all_dates
    ]

    hourly_dist = [{"hour": h, "messages": hourly_messages.get(h, 0)} for h in range(24)]

    weekday_names = LOCALE.get("weekdays", ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
    weekday_dist = [
        {"day": weekday_names[i], "messages": weekday_messages.get(i, 0)}
        for i in range(7)
    ]

    project_list = []
    for pname, pdata in sorted(project_stats.items(), key=lambda x: -x[1]["cost"]):
        project_list.append({
            "name": pname,
            "sessions": pdata["sessions"],
            "messages": pdata["messages"],
            "cost": round(pdata["cost"], 2),
            "input_tokens": pdata["input_tokens"],
            "output_tokens": pdata["output_tokens"],
            "cache_read_tokens": pdata["cache_read_tokens"],
            "cache_write_tokens": pdata["cache_write_tokens"],
            "file_size_mb": round(pdata["file_size"] / 1_048_576, 1),
        })

    model_summary = []
    for mname, mdata in sorted(model_totals.items(), key=lambda x: -x[1]["cost"]):
        model_summary.append({
            "model": mname,
            "cost": round(mdata["cost"], 2),
            "input_tokens": mdata["input_tokens"],
            "output_tokens": mdata["output_tokens"],
            "cache_read_tokens": mdata["cache_read_tokens"],
            "cache_write_tokens": mdata["cache_write_tokens"],
            "calls": mdata["calls"],
        })

    cost_by_type = {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0}
    for mname_display, mdata in model_totals.items():
        model_id = None
        for mid, mp in PRICING.items():
            if mp["display"] == mname_display:
                model_id = mid
                break
        if not model_id:
            model_id = list(PRICING.keys())[0]
        p = PRICING[model_id]

        cost_by_type["input"] += mdata["input_tokens"] * p["input"] / 1_000_000
        cost_by_type["output"] += mdata["output_tokens"] * p["output"] / 1_000_000
        cost_by_type["cache_read"] += mdata["cache_read_tokens"] * p["cache_read"] / 1_000_000
        cost_by_type["cache_write"] += mdata["cache_write_tokens"] * p["cache_write_5m"] / 1_000_000

    cost_by_type = {k: round(v, 2) for k, v in cost_by_type.items()}

    # Cache efficiency: what would cache_read tokens have cost at full input price?
    cache_savings = 0.0
    for mname_display, mdata in model_totals.items():
        model_id = None
        for mid, mp in PRICING.items():
            if mp["display"] == mname_display:
                model_id = mid
                break
        if not model_id:
            model_id = list(PRICING.keys())[0]
        p = PRICING[model_id]
        full_price = mdata["cache_read_tokens"] * p["input"] / 1_000_000
        cache_price = mdata["cache_read_tokens"] * p["cache_read"] / 1_000_000
        cache_savings += full_price - cache_price

    cost_by_type["cache_savings"] = round(cache_savings, 2)

    # ── Global Tool Aggregation ───────────────────────────────────────────
    global_tools = defaultdict(int)
    for s in session_list:
        for tool_name, count in s.get("tools", {}).items():
            global_tools[tool_name] += count
    tool_ranking = sorted(global_tools.items(), key=lambda x: -x[1])
    tool_summary = [{"name": n, "count": c} for n, c in tool_ranking]

    # Global Skills Aggregation
    global_skills = defaultdict(int)
    for s in session_list:
        for skill_name, count in s.get("skills", {}).items():
            global_skills[skill_name] += count
    skill_ranking = sorted(global_skills.items(), key=lambda x: -x[1])
    skill_summary = [{"name": n, "count": c} for n, c in skill_ranking]

    # Global Hooks Aggregation
    global_hooks = defaultdict(int)
    for s in session_list:
        for hook_name, count in s.get("hooks", {}).items():
            global_hooks[hook_name] += count
    hook_ranking = sorted(global_hooks.items(), key=lambda x: -x[1])
    hook_summary = [{"name": n, "count": c} for n, c in hook_ranking]

    # Global Agent/Subagent Aggregation
    global_agent_types = defaultdict(int)
    global_agent_descriptions = defaultdict(int)
    total_agent_dispatches = 0
    for s in session_list:
        for ad in s.get("agent_dispatches", []):
            global_agent_types[ad.get("type", "general-purpose")] += 1
            global_agent_descriptions[ad.get("description", "")] += 1
            total_agent_dispatches += 1
    agent_type_summary = sorted(global_agent_types.items(), key=lambda x: -x[1])
    agent_desc_summary = sorted(global_agent_descriptions.items(), key=lambda x: -x[1])[:10]

    # Global Error Aggregation
    total_errors = 0
    errors_by_tool = defaultdict(int)
    errors_by_category = defaultdict(int)
    for s in session_list:
        total_errors += s.get("error_count", 0)
        for e in s.get("errors", []):
            errors_by_tool[e.get("tool", "unknown")] += 1
            errors_by_category[e.get("category", "other")] += 1
    total_tool_calls = sum(s.get("api_calls", 0) for s in session_list)

    # Global Git Ops
    total_commits = sum(len([g for g in s.get("git_ops", []) if g.get("type") == "commit"]) for s in session_list)
    total_pushes = sum(len([g for g in s.get("git_ops", []) if g.get("type") == "push"]) for s in session_list)
    total_prs = sum(len([g for g in s.get("git_ops", []) if g.get("type") == "pr"]) for s in session_list)

    dc = dot_claude
    account = dc.get("oauthAccount", {})

    # ── Plan-Analyse ───────────────────────────────────────────────────────
    plan_analysis = build_plan_analysis(daily_cost_series, session_list)

    # ── Actual plan cost for KPI ─────────────────────────────────────────
    actual_plan_cost = plan_analysis.get("total_plan_cost", 0)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "locale": LOCALE,
        "account": {
            "name": CONFIG.get("display_name") or account.get("displayName", ""),
            "email": account.get("emailAddress", ""),
        },
        "kpi": {
            "total_cost": round(total_cost, 2),
            "actual_plan_cost": actual_plan_cost,
            "total_sessions": len(session_list),
            "total_messages": total_messages,
            "total_output_tokens": total_output,
            "total_input_tokens": total_input,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_write_tokens": total_cache_write,
            "first_session": all_dates[0] if all_dates else "",
            "last_session": all_dates[-1] if all_dates else "",
            "total_projects": len(project_list),
        },
        "plan": plan_analysis,
        "daily_costs": daily_cost_series,
        "cumulative_costs": cumulative_series,
        "daily_messages": daily_message_series,
        "hourly_distribution": hourly_dist,
        "weekday_distribution": weekday_dist,
        "models": all_models,
        "model_summary": model_summary,
        "cost_by_token_type": cost_by_type,
        "projects": project_list,
        "sessions": session_list,
        "tool_summary": tool_summary,
        "skill_summary": skill_summary,
        "hook_summary": hook_summary,
        "agent_summary": {
            "total_dispatches": total_agent_dispatches,
            "type_distribution": [{"type": t, "count": c} for t, c in agent_type_summary],
            "top_descriptions": [{"desc": d, "count": c} for d, c in agent_desc_summary],
        },
        "error_summary": {
            "total_errors": total_errors,
            "total_tool_calls": total_tool_calls,
            "error_rate": round(total_errors / max(total_tool_calls, 1) * 100, 2),
            "by_tool": sorted([{"tool": t, "count": c} for t, c in errors_by_tool.items()], key=lambda x: -x["count"]),
            "by_category": sorted([{"category": c, "count": n} for c, n in errors_by_category.items()], key=lambda x: -x["count"]),
        },
        "git_summary": {
            "commits": total_commits,
            "pushes": total_pushes,
            "prs": total_prs,
        },
        "insights": {
            "plans": plans or [],
            "plugins": plugins or {},
            "todos": todos or {},
            "file_history": file_history or {},
            "storage": storage or {},
            "tasks": tasks or {},
            "telemetry": telemetry or {},
            "memories_count": len(memories) if memories else 0,
        },
        "_memories": memories or {},
        "_file_ops_by_session": {sid: sess.get("file_ops", []) for sid, sess in sessions.items()},
    }

    return data


def generate_dashboard(data):
    """Generate self-contained HTML dashboard with embedded data."""
    data_json = json.dumps(data, ensure_ascii=False)

    if TEMPLATE_HTML.exists():
        with open(TEMPLATE_HTML, "r", encoding="utf-8") as f:
            template = f.read()
        html = template.replace("/*__DASHBOARD_DATA__*/", f"const DASHBOARD_DATA = {data_json};")
        html = _inject_locale(html, LOCALE)
    else:
        html = build_inline_html(data_json)

    with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Dashboard written to: {DASHBOARD_HTML}")


def _inject_locale(html, locale):
    """Replace __L_section_key__ placeholders with locale values."""
    for section_key, section_val in locale.items():
        if isinstance(section_val, dict):
            for key, val in section_val.items():
                placeholder = f"__L_{section_key}_{key}__"
                html = html.replace(placeholder, str(val))
        elif isinstance(section_val, str):
            placeholder = f"__L_{section_key}__"
            html = html.replace(placeholder, str(section_val))
    return html


def build_inline_html(data_json):
    """Build the complete HTML dashboard with embedded data.

    Security note: All data is locally generated from the user's own
    Claude Code session files. User-provided text (prompts) is escaped
    via a dedicated escHtml() function using textContent before display.
    """
    html = _get_html_template()
    html = _inject_locale(html, LOCALE)
    html = html.replace('"__DATA_PLACEHOLDER__"', data_json)
    html = html.replace('__VERSION__', VERSION)
    return html


def _get_html_template():
    """Return the HTML template string with a placeholder for data."""
    return '''<!DOCTYPE html>
<html lang="__L_html_lang__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code Dashboard</title>
<link rel="icon" type="image/png" href="favicon.png">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
:root {
  --bg: #0f1117;
  --bg2: #1a1d27;
  --bg3: #242836;
  --border: #2d3348;
  --text: #e2e8f0;
  --text2: #94a3b8;
  --accent: #6366f1;
  --accent2: #818cf8;
  --green: #22c55e;
  --orange: #f59e0b;
  --red: #ef4444;
  --blue: #3b82f6;
  --purple: #a855f7;
  --cyan: #06b6d4;
  --pink: #ec4899;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,-apple-system,sans-serif; font-size:14px; }
.header { background:var(--bg2); border-bottom:1px solid var(--border); padding:16px 24px; display:flex; align-items:center; justify-content:space-between; }
.header h1 { font-size:20px; font-weight:600; }
.header h1 span { color:var(--accent2); }
.header .meta { color:var(--text2); font-size:13px; }
.time-filter { display:flex; gap:4px; }
.time-filter button { background:var(--bg3); border:1px solid var(--border); color:var(--text2); padding:6px 14px; border-radius:6px; font-size:12px; font-weight:600; cursor:pointer; transition:all .2s; }
.time-filter button:hover { color:var(--text); background:var(--bg3); border-color:var(--accent); }
.time-filter button.active { background:var(--accent); color:white; border-color:var(--accent); }
.container { max-width:1400px; margin:0 auto; padding:20px; }

/* KPI Cards */
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:24px; }
.kpi-card { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; }
.kpi-card .label { color:var(--text2); font-size:12px; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; }
.kpi-card .value { font-size:28px; font-weight:700; }
.kpi-card .sub { color:var(--text2); font-size:12px; margin-top:4px; }
.kpi-card.cost .value { color:var(--orange); }
.kpi-card.sessions .value { color:var(--blue); }
.kpi-card.messages .value { color:var(--green); }
.kpi-card.tokens .value { color:var(--purple); }

/* Tabs */
.tabs { display:flex; gap:4px; margin-bottom:20px; background:var(--bg2); padding:4px; border-radius:10px; border:1px solid var(--border); }
.tab-btn { flex:1; padding:10px 16px; background:transparent; border:none; color:var(--text2); font-size:14px; font-weight:500; cursor:pointer; border-radius:8px; transition:all .2s; }
.tab-btn:hover { color:var(--text); background:var(--bg3); }
.tab-btn.active { background:var(--accent); color:white; }
.tab-content { display:none; }
.tab-content.active { display:block; }

/* Chart containers */
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px; }
.chart-grid.full { grid-template-columns:1fr; }
.chart-box { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; }
.chart-box h3 { font-size:15px; font-weight:600; margin-bottom:16px; color:var(--text); }
.chart-box canvas { max-height:350px; }
.chart-box.tall canvas { max-height:500px; }

/* Tables */
.data-table { width:100%; border-collapse:collapse; }
.data-table th { text-align:left; padding:10px 12px; font-size:12px; color:var(--text2); text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid var(--border); cursor:pointer; user-select:none; white-space:nowrap; }
.data-table th:hover { color:var(--accent2); }
.data-table th.sort-asc::after { content:" \\25B2"; font-size:10px; }
.data-table th.sort-desc::after { content:" \\25BC"; font-size:10px; }
.data-table td { padding:10px 12px; border-bottom:1px solid var(--border); font-size:13px; }
.data-table tr:hover td { background:var(--bg3); }
.data-table .num { text-align:right; font-variant-numeric:tabular-nums; }

/* Session cards */
.session-filters { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }
.session-filters select, .session-filters input { background:var(--bg3); border:1px solid var(--border); color:var(--text); padding:8px 12px; border-radius:8px; font-size:13px; }
.session-filters select { min-width:200px; }
.session-card { background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:12px; cursor:pointer; transition:border-color .2s; }
.session-card:hover { border-color:var(--accent); }
.session-card .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.session-card .project { color:var(--accent2); font-weight:600; font-size:14px; }
.session-card .cost { color:var(--orange); font-weight:700; font-size:16px; }
.session-card .info { display:flex; gap:16px; color:var(--text2); font-size:12px; flex-wrap:wrap; }
.session-card .info span { display:flex; align-items:center; gap:4px; }
.session-card .prompt { color:var(--text2); font-size:12px; margin-top:8px; padding-top:8px; border-top:1px solid var(--border); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.session-card .details { display:none; margin-top:12px; padding-top:12px; border-top:1px solid var(--border); }
.session-card.expanded .details { display:block; }
.session-card .tools { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.session-card .tool-tag { background:var(--bg3); padding:2px 8px; border-radius:4px; font-size:11px; color:var(--text2); }
.model-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }
.model-badge.opus { background:rgba(168,85,247,0.2); color:var(--purple); }
.model-badge.sonnet { background:rgba(59,130,246,0.2); color:var(--blue); }
.model-badge.haiku { background:rgba(34,197,94,0.2); color:var(--green); }

.pagination { display:flex; gap:8px; justify-content:center; margin-top:16px; align-items:center; }
.pagination button { background:var(--bg3); border:1px solid var(--border); color:var(--text); padding:6px 14px; border-radius:6px; cursor:pointer; }
.pagination button:hover { background:var(--accent); }
.pagination .info { color:var(--text2); padding:6px 0; font-size:13px; }

/* Plan Tab */
.plan-highlight { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; margin-bottom:24px; }
.plan-card { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; }
.plan-card .label { color:var(--text2); font-size:12px; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; }
.plan-card .value { font-size:26px; font-weight:700; }
.plan-card .sub { color:var(--text2); font-size:12px; margin-top:4px; }
.plan-card.savings .value { color:var(--green); }
.plan-card.roi .value { color:var(--cyan); }
.plan-card.plan-type .value { color:var(--accent2); }
.plan-card.api-cost .value { color:var(--orange); }

.billing-progress { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:24px; margin-bottom:24px; }
.billing-progress h3 { font-size:15px; font-weight:600; margin-bottom:16px; }
.progress-bar-outer { background:var(--bg3); border-radius:8px; height:32px; overflow:hidden; position:relative; margin-bottom:12px; }
.progress-bar-inner { height:100%; border-radius:8px; transition:width .5s; display:flex; align-items:center; justify-content:flex-end; padding-right:10px; font-size:12px; font-weight:600; }
.progress-stats { display:flex; gap:24px; flex-wrap:wrap; color:var(--text2); font-size:13px; }
.progress-stats .stat-item { display:flex; flex-direction:column; gap:2px; }
.progress-stats .stat-val { color:var(--text); font-weight:600; font-size:15px; }

.plan-comparison { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:20px; }
.plan-comparison h3 { font-size:15px; font-weight:600; margin-bottom:8px; }
.plan-comparison .bar-row { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.plan-comparison .bar-label { width:160px; flex-shrink:0; font-size:13px; color:var(--text2); }
.plan-comparison .bar-track { flex:1; background:var(--bg3); border-radius:6px; height:24px; overflow:hidden; }
.plan-comparison .bar-fill { height:100%; border-radius:6px; display:flex; align-items:center; padding-left:8px; font-size:11px; font-weight:600; min-width:2px; }
.plan-comparison .bar-val { min-width:80px; text-align:right; font-size:13px; font-weight:600; }

/* Insights Tab */
.config-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.config-item { padding:10px 14px; background:var(--bg3); border-radius:8px; }
.config-item .ci-label { font-size:11px; color:var(--text2); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }
.config-item .ci-value { font-size:14px; font-weight:600; }
.misc-stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.misc-stat { padding:16px; background:var(--bg3); border-radius:8px; text-align:center; }
.misc-stat .ms-val { font-size:24px; font-weight:700; color:var(--accent2); }
.misc-stat .ms-label { font-size:12px; color:var(--text2); margin-top:4px; }
.plugin-status { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }
.plugin-status.active { background:rgba(34,197,94,0.2); color:var(--green); }
.plugin-status.inactive { background:rgba(239,68,68,0.2); color:var(--red); }

/* Activity Heatmap */
.heatmap-container { margin-bottom:20px; }
.heatmap-scroll { overflow-x:auto; }
.heatmap-grid { display:flex; gap:2px; }
.heatmap-col { display:flex; flex-direction:column; gap:2px; }
.heatmap-cell { width:13px; height:13px; border-radius:2px; position:relative; }
.heatmap-cell:hover::after { content:attr(data-tip); position:absolute; bottom:18px; left:50%; transform:translateX(-50%); background:var(--bg2); border:1px solid var(--border); padding:4px 8px; border-radius:4px; font-size:11px; white-space:nowrap; z-index:10; color:var(--text); pointer-events:none; }
.heatmap-labels { display:flex; flex-direction:column; gap:2px; margin-right:4px; padding-top:18px; }
.heatmap-labels span { height:13px; font-size:10px; color:var(--text2); line-height:13px; }
.heatmap-legend { display:flex; align-items:center; gap:4px; margin-top:8px; justify-content:flex-end; font-size:11px; color:var(--text2); }
.heatmap-legend .cell { width:13px; height:13px; border-radius:2px; }
.heatmap-months { display:flex; font-size:10px; color:var(--text2); margin-bottom:2px; }
.heatmap-months span { text-align:center; }

.tag { display:inline-block; padding:3px 10px; border-radius:6px; font-size:12px; font-weight:600; }

@media (max-width:900px) {
  .chart-grid { grid-template-columns:1fr; }
  .kpi-grid { grid-template-columns:repeat(2,1fr); }
  .config-grid { grid-template-columns:1fr; }
  .misc-stat-grid { grid-template-columns:1fr 1fr; }
}
@media (max-width:640px) {
  .header { flex-wrap:wrap; gap:10px; padding:12px 16px; }
  .header h1 { width:100%; font-size:17px; }
  .header .meta { width:100%; order:10; }
  .header label { font-size:11px; }
  .header input[type="text"] { flex:1; min-width:0; width:auto; }
  .time-filter { flex-wrap:wrap; }
  .tabs { overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none; gap:2px; flex-wrap:nowrap; }
  .tabs::-webkit-scrollbar { display:none; }
  .tab-btn { flex:0 0 auto; padding:8px 12px; font-size:13px; white-space:nowrap; }
  .container { padding:12px; }
  .kpi-grid { grid-template-columns:1fr; }
  .chart-box:has(.data-table) { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .data-table { min-width:500px; }
  .session-filters { gap:8px; }
  .session-filters select { min-width:0; flex:1; }
  .session-filters input { flex:1; min-width:0; }
  .config-grid { grid-template-columns:1fr; }
  .misc-stat-grid { grid-template-columns:1fr; }
  .plan-comparison .bar-label { width:100px; font-size:12px; }
  .plan-comparison .bar-val { min-width:60px; font-size:12px; }
  .plan-highlight { grid-template-columns:1fr; }
  .progress-stats { gap:12px; }
  .chart-box canvas { max-height:280px; }
}
</style>
</head>
<body>

<div class="header">
  <h1><span>__L_header_title_prefix__</span> __L_header_title_suffix__</h1>
  <div class="time-filter" id="timeFilter"></div>
  <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2);cursor:pointer;user-select:none" title="__L_header_hide_empty_hint__">
    <input type="checkbox" id="hideEmptySessions" checked style="accent-color:var(--accent);cursor:pointer" />
    __L_header_hide_empty__
  </label>
  <input type="text" id="projectFilter" placeholder="Filter projects..." style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:6px 14px;border-radius:6px;font-size:12px;width:180px;outline:none;" />
  <div class="meta" id="headerMeta"></div>
</div>

<div class="container">
  <div class="kpi-grid" id="kpiGrid"></div>

  <div class="tabs" id="tabBar"></div>

  <div class="tab-content active" id="tab-costs">
    <div class="chart-grid full">
      <div class="chart-box"><h3>__L_costs_daily_cost__</h3><canvas id="chartDailyCost"></canvas></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_costs_cumulative__</h3><canvas id="chartCumCost"></canvas></div>
      <div class="chart-box"><h3>__L_costs_model_dist__</h3><canvas id="chartModelDist"></canvas></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_costs_token_type__</h3><canvas id="chartTokenType"></canvas></div>
      <div class="chart-box">
        <h3>__L_costs_model_detail__</h3>
        <table class="data-table" id="modelTable">
          <thead><tr>
            <th>__L_costs_th_model__</th><th class="num">__L_costs_th_api_value__</th><th class="num">__L_costs_th_output__</th>
            <th class="num">__L_costs_th_input__</th><th class="num">__L_costs_th_cache_read__</th><th class="num">__L_costs_th_api_calls__</th>
          </tr></thead>
          <tbody id="modelTableBody"></tbody>
        </table>
      </div>
    </div>
    <div class="chart-grid">
      <div class="chart-box" id="cacheEfficiency">
        <h3>__L_costs_cache_efficiency__</h3>
        <div class="kpi-grid" id="cacheKpi"></div>
      </div>
    </div>
  </div>

  <div class="tab-content" id="tab-activity">
    <div class="chart-box heatmap-container">
      <h3>__L_activity_heatmap__</h3>
      <div class="heatmap-scroll">
        <div id="heatmapMonths" class="heatmap-months"></div>
        <div style="display:flex">
          <div class="heatmap-labels"><span></span><span>Mon</span><span></span><span>Wed</span><span></span><span>Fri</span><span></span></div>
          <div id="activityHeatmap" class="heatmap-grid"></div>
        </div>
      </div>
      <div class="heatmap-legend">
        <span>Less</span>
        <div class="cell" style="background:var(--bg3)"></div>
        <div class="cell" style="background:rgba(99,102,241,0.2)"></div>
        <div class="cell" style="background:rgba(99,102,241,0.4)"></div>
        <div class="cell" style="background:rgba(99,102,241,0.7)"></div>
        <div class="cell" style="background:var(--accent)"></div>
        <span>More</span>
      </div>
    </div>
    <div class="chart-grid full">
      <div class="chart-box"><h3>__L_activity_daily_messages__</h3><canvas id="chartDailyMsgs"></canvas></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_activity_hourly__</h3><canvas id="chartHourly"></canvas></div>
      <div class="chart-box"><h3>__L_activity_weekday__</h3><canvas id="chartWeekday"></canvas></div>
    </div>
    <div class="chart-grid full">
      <div class="chart-box"><h3>__L_activity_daily_sessions__</h3><canvas id="chartDailySessions"></canvas></div>
    </div>
  </div>

  <div class="tab-content" id="tab-projects">
    <div class="chart-grid full">
      <div class="chart-box tall"><h3>__L_projects_top15__</h3><canvas id="chartProjectCost"></canvas></div>
    </div>
    <div class="chart-box">
      <h3>__L_projects_all_projects__</h3>
      <table class="data-table sortable" id="projectTable">
        <thead><tr>
          <th data-sort="name">__L_projects_th_project__</th>
          <th data-sort="sessions" class="num">__L_projects_th_sessions__</th>
          <th data-sort="messages" class="num">__L_projects_th_messages__</th>
          <th data-sort="cost" class="num">__L_projects_th_api_value__</th>
          <th data-sort="output_tokens" class="num">__L_projects_th_output_tokens__</th>
          <th data-sort="file_size_mb" class="num">__L_projects_th_file_size__</th>
        </tr></thead>
        <tbody id="projectTableBody"></tbody>
      </table>
    </div>
  </div>

  <div class="tab-content" id="tab-sessions">
    <div class="session-filters">
      <select id="filterProject"><option value="">__L_sessions_tab_all_projects__</option></select>
      <select id="filterSort">
        <option value="date-desc">__L_sessions_tab_sort_date_desc__</option>
        <option value="date-asc">__L_sessions_tab_sort_date_asc__</option>
        <option value="cost-desc">__L_sessions_tab_sort_cost_desc__</option>
        <option value="cost-asc">__L_sessions_tab_sort_cost_asc__</option>
        <option value="messages-desc">__L_sessions_tab_sort_messages_desc__</option>
      </select>
      <input type="text" id="filterSearch" placeholder="__L_sessions_tab_search_placeholder__">
      <span class="meta" id="sessionCount"></span>
    </div>
    <div id="sessionList"></div>
    <div class="pagination" id="sessionPagination"></div>
  </div>

  <div class="tab-content" id="tab-plan">
    <div class="plan-highlight" id="planKpi"></div>
    <div class="billing-progress" id="billingProgress"></div>
    <div class="plan-comparison" id="planComparison">
      <h3>__L_plan_comparison_title__</h3>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_plan_savings_by_period__</h3><canvas id="chartPlanSavings"></canvas></div>
      <div class="chart-box"><h3>__L_plan_avg_cost_per_day__</h3><canvas id="chartCostPerDay"></canvas></div>
    </div>
    <div class="chart-box" style="margin-top:20px">
      <h3>__L_plan_period_detail__</h3>
      <table class="data-table" id="planTable">
        <thead><tr>
          <th>__L_plan_th_period__</th><th>__L_plan_th_plan__</th><th class="num">__L_plan_th_days__</th>
          <th class="num">__L_plan_th_api_cost__</th><th class="num">__L_plan_th_plan_cost__</th>
          <th class="num">__L_plan_th_savings__</th><th class="num">__L_plan_th_roi__</th>
          <th class="num">__L_plan_th_sessions__</th><th class="num">__L_plan_th_messages__</th>
        </tr></thead>
        <tbody id="planTableBody"></tbody>
      </table>
    </div>
  </div>

  <div class="tab-content" id="tab-insights">
    <div class="chart-grid">
      <div class="chart-box tall"><h3>__L_insights_tool_usage__</h3><canvas id="chartToolUsage"></canvas></div>
      <div class="chart-box"><h3>__L_insights_storage__</h3><canvas id="chartStorage"></canvas></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box">
        <h3>__L_insights_plugins__</h3>
        <table class="data-table" id="pluginTable">
          <thead><tr>
            <th>__L_insights_th_plugin__</th><th>__L_insights_th_status__</th><th>__L_insights_th_version__</th>
            <th class="num">__L_insights_th_global_installs__</th><th>__L_insights_th_installed_at__</th>
          </tr></thead>
          <tbody id="pluginTableBody"></tbody>
        </table>
      </div>
      <div class="chart-box">
        <h3>__L_insights_configuration__</h3>
        <div id="configInfo"></div>
      </div>
    </div>
    <div class="chart-grid">
      <div class="chart-box">
        <h3>__L_insights_plan_mode_plans__</h3>
        <table class="data-table" id="plansTable">
          <thead><tr>
            <th>__L_insights_th_title__</th><th>__L_insights_th_created__</th><th class="num">__L_insights_th_lines__</th><th class="num">__L_insights_th_kb__</th>
          </tr></thead>
          <tbody id="plansTableBody"></tbody>
        </table>
      </div>
      <div class="chart-box">
        <h3>__L_insights_file_snapshots_title__</h3>
        <div id="miscStats"></div>
      </div>
    </div>
    <div class="chart-grid">
      <div class="chart-box">
        <h3>__L_insights_skills__</h3>
        <div id="skillsList"></div>
      </div>
      <div class="chart-box">
        <h3>__L_insights_hooks__</h3>
        <div id="hooksList"></div>
      </div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_insights_system_info__</h3><div id="systemInfo"></div></div>
      <div class="chart-box"><h3>__L_insights_git_ops__</h3><div id="gitOpsInfo"></div></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_insights_memory_per_session__</h3><canvas id="memoryChart" height="200"></canvas></div>
      <div class="chart-box"><h3>__L_insights_error_rate_over_time__</h3><canvas id="errorRateChart" height="200"></canvas></div>
    </div>
  </div>

  <div class="tab-content" id="tab-agents">
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_agents_subagent_types__</h3><canvas id="agentTypesChart" height="250"></canvas></div>
      <div class="chart-box"><h3>__L_agents_top_descriptions__</h3><canvas id="agentDescsChart" height="250"></canvas></div>
    </div>
    <div class="kpi-grid" id="agentKpis"></div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_agents_task_overview__</h3><div id="taskOverview"></div></div>
      <div class="chart-box"><h3>__L_agents_error_overview__</h3><div id="errorOverview"></div></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><h3>__L_agents_errors_by_category__</h3><canvas id="errorByCategoryChart" height="250"></canvas></div>
      <div class="chart-box"><h3>__L_agents_errors_by_tool__</h3><canvas id="errorByToolChart" height="250"></canvas></div>
    </div>
  </div>
</div>

<script>
const D = "__DATA_PLACEHOLDER__";

// ── Helpers ────────────────────────────────────────────────────────────
const fmt = n => n.toLocaleString(D.locale.locale_code);
const fmtUSD = n => '$' + n.toLocaleString(D.locale.locale_code, {minimumFractionDigits:2, maximumFractionDigits:2});
const fmtTokens = n => {
  if (n >= 1e9) return (n/1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return n.toString();
};

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

const MODEL_COLORS = {
  'Opus 4.6': '#a855f7', 'Opus 4.5': '#7c3aed',
  'Sonnet 4.5': '#3b82f6', 'Haiku 4.5': '#22c55e',
  'Unknown': '#6b7280'
};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#1e293b';

const scaleDefaults = {
  x: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
  y: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
};

// ── Filtered Data & Time Filter ────────────────────────────────────────
let F = {};
const charts = {};
let currentDays = 0;
let anonMode = false;
let agentTypesChartInstance, agentDescsChartInstance, errorByCatChartInstance, errorByToolChartInstance;
const chartColors = ['#6366f1','#22c55e','#f59e0b','#ef4444','#a855f7','#06b6d4','#ec4899','#3b82f6','#f97316','#14b8a6'];
let currentProjectFilter = '';

function calcFilteredPlanCost(filteredDates) {
  if (!filteredDates.length || !D.plan) return D.kpi.actual_plan_cost;
  const minDate = filteredDates[0];
  const maxDate = filteredDates[filteredDates.length - 1];
  let cost = 0;
  // Sum plan costs for periods that overlap with the filtered date range
  const allPeriods = (D.plan.periods || []).concat(D.plan.current_billing ? [D.plan.current_billing] : []);
  allPeriods.forEach(p => {
    const pStart = p.start || p.period_start;
    const pEnd = p.end || p.period_end;
    if (!pStart || !pEnd) return;
    // Check overlap
    if (pEnd < minDate || pStart > maxDate) return;
    // Calculate overlap fraction
    const overlapStart = pStart > minDate ? pStart : minDate;
    const overlapEnd = pEnd < maxDate ? pEnd : maxDate;
    const totalDays = p.total_days || p.days_total || 30;
    const msPerDay = 86400000;
    const overlapDays = Math.round((new Date(overlapEnd) - new Date(overlapStart)) / msPerDay) + 1;
    const fraction = Math.min(1, overlapDays / totalDays);
    cost += (p.plan_cost_usd || 0) * fraction;
  });
  return Math.round(cost * 100) / 100;
}

function filterData(days, projectFilter) {
  if (days !== undefined) currentDays = days;
  if (projectFilter !== undefined) currentProjectFilter = projectFilter;

  let cutoff = '';
  if (currentDays > 0) {
    const d = new Date();
    d.setDate(d.getDate() - currentDays);
    cutoff = d.toISOString().slice(0, 10);
  }

  const pf = currentProjectFilter.toLowerCase().trim();

  // Filter sessions by date AND project
  const hideEmpty = document.getElementById('hideEmptySessions')?.checked;
  let filteredSessions = D.sessions;
  if (hideEmpty) filteredSessions = filteredSessions.filter(s => s.messages > 0 || s.output_tokens > 0);
  if (cutoff) filteredSessions = filteredSessions.filter(s => s.date >= cutoff);
  if (pf) filteredSessions = filteredSessions.filter(s => (s.project || '').toLowerCase().includes(pf));
  F.sessions = filteredSessions;

  // Rebuild daily aggregates from filtered sessions
  const dailyCostMap = {};
  const dailyMsgMap = {};
  F.sessions.forEach(s => {
    if (!s.date) return;
    if (!dailyMsgMap[s.date]) dailyMsgMap[s.date] = {date: s.date, messages: 0, sessions: 0};
    dailyMsgMap[s.date].messages += s.messages || 0;
    dailyMsgMap[s.date].sessions += 1;
    if (!dailyCostMap[s.date]) dailyCostMap[s.date] = {date: s.date, total: 0};
    dailyCostMap[s.date].total += s.cost || 0;
    Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
      dailyCostMap[s.date][model] = (dailyCostMap[s.date][model] || 0) + (d.cost || 0);
    });
  });
  const allDates = [...new Set([...Object.keys(dailyCostMap), ...Object.keys(dailyMsgMap)])].sort();
  F.daily_costs = allDates.map(d => dailyCostMap[d] || {date: d, total: 0});
  F.daily_messages = allDates.map(d => dailyMsgMap[d] || {date: d, messages: 0, sessions: 0});

  // Recalculate cumulative costs from filtered daily costs
  let cum = 0;
  F.cumulative_costs = F.daily_costs.map(r => { cum += r.total; return {date: r.date, cost: cum}; });

  // Recalculate model_summary from filtered sessions
  const modelMap = {};
  F.sessions.forEach(s => {
    Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
      if (!modelMap[model]) modelMap[model] = {model, cost:0, input_tokens:0, output_tokens:0, cache_read_tokens:0, calls:0};
      modelMap[model].cost += d.cost || 0;
      modelMap[model].input_tokens += d.input_tokens || 0;
      modelMap[model].output_tokens += d.output_tokens || 0;
      modelMap[model].cache_read_tokens += d.cache_read_tokens || 0;
      modelMap[model].calls += d.calls || 0;
    });
  });
  F.model_summary = Object.values(modelMap).sort((a, b) => b.cost - a.cost);

  // cost_by_token_type: scale by ratio of filtered cost to original cost
  const filteredTotalCost = F.model_summary.reduce((s, m) => s + m.cost, 0);
  const ratio = D.kpi.total_cost > 0 ? filteredTotalCost / D.kpi.total_cost : 0;
  F.cost_by_token_type = {
    input: D.cost_by_token_type.input * ratio,
    output: D.cost_by_token_type.output * ratio,
    cache_read: D.cost_by_token_type.cache_read * ratio,
    cache_write: D.cost_by_token_type.cache_write * ratio,
    cache_savings: (D.cost_by_token_type.cache_savings || 0) * ratio,
  };

  // Recalculate projects from filtered sessions
  const projMap = {};
  F.sessions.forEach(s => {
    if (!projMap[s.project]) projMap[s.project] = {name: s.project, sessions:0, messages:0, cost:0, output_tokens:0, file_size_mb: 0};
    const p = projMap[s.project];
    p.sessions++;
    p.messages += s.messages || 0;
    p.cost += s.cost || 0;
    p.output_tokens += s.output_tokens || 0;
    p.file_size_mb = Math.max(p.file_size_mb, s.file_size_mb || 0);
  });
  F.projects = Object.values(projMap).sort((a, b) => b.cost - a.cost);

  // Recalculate hourly_distribution
  const hourly = Array.from({length:24}, (_, i) => ({hour: i, messages: 0}));
  F.sessions.forEach(s => {
    if (s.start) {
      const h = new Date(s.start).getHours();
      hourly[h].messages += s.messages || 0;
    }
  });
  F.hourly_distribution = hourly;

  // Recalculate weekday_distribution
  const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const weekday = [0,0,0,0,0,0,0];
  F.sessions.forEach(s => {
    if (s.start) {
      const d = new Date(s.start).getDay();
      weekday[d] += s.messages || 0;
    }
  });
  // Reorder to Mon-Sun
  F.weekday_distribution = [1,2,3,4,5,6,0].map(i => ({day: dayNames[i], messages: weekday[i]}));

  // Recalculate tool_summary
  const toolMap = {};
  F.sessions.forEach(s => {
    Object.entries(s.tools || {}).forEach(([name, count]) => {
      toolMap[name] = (toolMap[name] || 0) + count;
    });
  });
  F.tool_summary = Object.entries(toolMap).map(([name, count]) => ({name, count})).sort((a, b) => b.count - a.count);

  // Recalculate KPI
  const totalCost = filteredTotalCost;
  const totalSessions = F.sessions.length;
  const totalMessages = F.sessions.reduce((s, x) => s + (x.messages || 0), 0);
  const totalOutputTokens = F.sessions.reduce((s, x) => s + (x.output_tokens || 0), 0);
  const totalInputTokens = F.sessions.reduce((s, x) => s + (x.input_tokens || 0), 0);
  const totalCacheReadTokens = F.sessions.reduce((s, x) => s + (x.cache_read_tokens || 0), 0);
  const totalCacheWriteTokens = F.sessions.reduce((s, x) => s + (x.cache_write_tokens || 0), 0);
  const dates = F.sessions.map(s => s.date).filter(Boolean).sort();
  F.kpi = {
    total_cost: totalCost,
    actual_plan_cost: calcFilteredPlanCost(dates),
    total_sessions: totalSessions,
    total_messages: totalMessages,
    total_output_tokens: totalOutputTokens,
    total_input_tokens: totalInputTokens,
    total_cache_read_tokens: totalCacheReadTokens,
    total_cache_write_tokens: totalCacheWriteTokens,
    first_session: dates.length > 0 ? dates[0] : D.kpi.first_session,
    last_session: dates.length > 0 ? dates[dates.length - 1] : D.kpi.last_session,
  };

  // Recalculate agent_summary from filtered sessions
  const agentTypeMap = {};
  const agentDescMap = {};
  let totalDispatches = 0;
  F.sessions.forEach(s => {
    (s.agent_dispatches || []).forEach(ad => {
      totalDispatches++;
      const t = ad.type || 'unknown';
      agentTypeMap[t] = (agentTypeMap[t] || 0) + 1;
      const d = ad.description || ad.desc || '';
      if (d) agentDescMap[d] = (agentDescMap[d] || 0) + 1;
    });
    (s.subagents || []).forEach(sa => {
      totalDispatches++;
      const t = sa.type || 'unknown';
      agentTypeMap[t] = (agentTypeMap[t] || 0) + 1;
    });
  });
  F.agent_summary = {
    total_dispatches: totalDispatches,
    type_distribution: Object.entries(agentTypeMap).map(([type, count]) => ({type, count})).sort((a,b) => b.count - a.count),
    top_descriptions: Object.entries(agentDescMap).map(([desc, count]) => ({desc, count})).sort((a,b) => b.count - a.count).slice(0, 10),
  };

  // Recalculate error_summary from filtered sessions
  const fErrors = F.sessions.reduce((s, x) => s + (x.error_count || 0), 0);
  const fToolCalls = F.sessions.reduce((s, x) => s + (x.api_calls || 0), 0);
  const fErrByTool = {}, fErrByCat = {};
  F.sessions.forEach(s => {
    (s.errors || []).forEach(e => {
      fErrByTool[e.tool || 'unknown'] = (fErrByTool[e.tool || 'unknown'] || 0) + 1;
      fErrByCat[e.category || 'other'] = (fErrByCat[e.category || 'other'] || 0) + 1;
    });
  });
  F.error_summary = {
    total_errors: fErrors,
    total_tool_calls: fToolCalls,
    error_rate: fToolCalls > 0 ? +(fErrors / fToolCalls * 100).toFixed(2) : 0,
    by_tool: Object.entries(fErrByTool).map(([tool, count]) => ({tool, count})).sort((a,b) => b.count - a.count),
    by_category: Object.entries(fErrByCat).map(([category, count]) => ({category, count})).sort((a,b) => b.count - a.count),
  };
}

function initTimeFilter() {
  const container = document.getElementById('timeFilter');
  const options = [{label:'All', days:0},{label:'7D', days:7},{label:'30D', days:30},{label:'90D', days:90},{label:'1Y', days:365}];
  options.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.textContent = opt.label;
    if (i === 0) btn.classList.add('active');
    btn.addEventListener('click', () => {
      container.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyFilter(opt.days);
    });
    container.appendChild(btn);
  });
}

function applyFilter(days, projectFilter) {
  filterData(days, projectFilter);

  // Destroy all existing Chart.js instances
  Object.keys(charts).forEach(k => { if (charts[k]) { charts[k].destroy(); delete charts[k]; } });

  // Clear dynamic DOM containers
  document.getElementById('kpiGrid').textContent = '';
  document.getElementById('modelTableBody').textContent = '';
  document.getElementById('projectTableBody').textContent = '';

  // Re-render (but NOT renderPlan)
  renderKPI();
  renderCosts();
  renderActivity();
  renderProjects();
  renderSessions();
  renderToolUsageChart();
  renderAgentsTab();
}

function renderToolUsageChart() {
  const tools = (F.tool_summary || []).slice(0, 20);
  if (tools.length > 0) {
    charts.toolUsage = new Chart(document.getElementById('chartToolUsage'), {
      type: 'bar',
      data: { labels: tools.map(t => t.name),
        datasets: [{ label: D.locale.insights.tool_calls, data: tools.map(t => t.count),
          backgroundColor: tools.map((_, i) => 'hsl(' + (i * 18) + ',60%,55%)'), borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: { x: { ...scaleDefaults.x, title: { display: true, text: D.locale.insights.tool_calls, color: '#64748b' } },
          y: { ...scaleDefaults.y, ticks: { font: { size: 11 } } } } }
    });
  }
}

// ── KPI Cards ──────────────────────────────────────────────────────────
function renderKPI() {
  const k = F.kpi;
  const dispName = anonMode ? 'Anonymous' : D.account.name;
  document.getElementById('headerMeta').textContent =
    dispName + ' | ' + k.first_session + ' \u2013 ' + k.last_session +
    ' | ' + D.locale.header.generated + ': ' + new Date(D.generated_at).toLocaleString(D.locale.locale_code);

  const grid = document.getElementById('kpiGrid');
  const cards = [
    {cls:'cost', label:D.locale.kpi.api_equivalent, value:fmtUSD(k.total_cost), sub:D.locale.kpi.api_equivalent_sub + fmtUSD(k.actual_plan_cost), tip: D.locale.locale_code === 'de' ? 'Was diese Nutzung \u00fcber die API kosten w\u00fcrde (ohne Abo). Darunter: tats\u00e4chlich bezahlter Abo-Preis im gew\u00e4hlten Zeitraum.' : 'What this usage would cost via the API (without subscription). Below: actual subscription cost paid in the selected period.'},
    {cls:'messages', label:D.locale.kpi.messages, value:fmt(k.total_messages), sub:D.locale.kpi.messages_sub_prefix+k.total_sessions+D.locale.kpi.messages_sub_suffix},
    {cls:'sessions', label:D.locale.kpi.sessions, value:fmt(k.total_sessions), sub:k.first_session+' - '+k.last_session},
    {cls:'tokens', label:'Tokens', value:'', sub:'', tip: D.locale.locale_code === 'de' ? 'Tokens sind die Texteinheiten die das Sprachmodell verarbeitet (ca. 0.75 Worte pro Token)' : 'Tokens are the text units processed by the language model (approx. 0.75 words per token)'},
  ];
  cards.forEach(c => {
    const div = document.createElement('div');
    div.className = 'kpi-card ' + c.cls;
    const lbl = document.createElement('div'); lbl.className = 'label'; lbl.textContent = c.label;
    if (c.tip) lbl.title = c.tip;
    const val = document.createElement('div'); val.className = 'value'; val.textContent = c.value;
    const sub = document.createElement('div'); sub.className = 'sub'; sub.textContent = c.sub;
    div.appendChild(lbl); div.appendChild(val); div.appendChild(sub);
    grid.appendChild(div);
  });

  // Token breakdown card — replace placeholder with detailed version
  const tokCard = grid.querySelector('.kpi-card.tokens');
  if (tokCard) {
    const totalIn = (k.total_input_tokens||0) + (k.total_cache_read_tokens||0) + (k.total_cache_write_tokens||0);
    const valEl = tokCard.querySelector('.value');
    valEl.textContent = fmtTokens(totalIn + (k.total_output_tokens||0));
    valEl.title = D.locale.locale_code === 'de' ? 'Summe aller Tokens (Input + Output + Cache)' : 'Total tokens (input + output + cache)';
    const sub = tokCard.querySelector('.sub');
    sub.style.cssText = 'line-height:1.6;font-size:0.78em';
    sub.textContent = '';
    const line1 = document.createElement('span');
    line1.textContent = 'Out: ' + fmtTokens(k.total_output_tokens||0) + ' \u00b7 In: ' + fmtTokens(k.total_input_tokens||0);
    const br = document.createElement('br');
    const line2 = document.createElement('span');
    line2.textContent = 'Cache Read: ' + fmtTokens(k.total_cache_read_tokens||0) + ' \u00b7 Write: ' + fmtTokens(k.total_cache_write_tokens||0);
    const ttOut = D.locale.locale_code === 'de' ? 'Von Claude generierter Text' : 'Text generated by Claude';
    const ttIn = D.locale.locale_code === 'de' ? 'Neue (nicht gecachte) Eingabe-Tokens pro Request' : 'New (non-cached) input tokens per request';
    const ttCR = D.locale.locale_code === 'de' ? 'Konversationskontext aus dem Cache gelesen \\u2013 wird bei jedem Turn erneut gesendet, daher die hohe Zahl' : 'Conversation context read from cache \\u2013 resent every turn, hence the large number';
    const ttCW = D.locale.locale_code === 'de' ? 'Tokens die in den Cache geschrieben wurden' : 'Tokens written to the prompt cache';
    line1.title = 'Out: ' + ttOut + '\\nIn: ' + ttIn;
    line2.title = 'Cache Read: ' + ttCR + '\\nWrite: ' + ttCW;
    sub.appendChild(line1);
    sub.appendChild(br);
    sub.appendChild(line2);
  }
}

// ── Tabs ───────────────────────────────────────────────────────────────
const TAB_NAMES = [
  {id:'costs', label:D.locale.tabs.costs},
  {id:'activity', label:D.locale.tabs.activity},
  {id:'projects', label:D.locale.tabs.projects},
  {id:'sessions', label:D.locale.tabs.sessions},
  {id:'plan', label:D.locale.tabs.plan},
  {id:'insights', label:D.locale.tabs.insights},
  {id:'agents', label:D.locale.tabs.agents},
];

function initTabs() {
  const bar = document.getElementById('tabBar');
  TAB_NAMES.forEach((t, i) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = t.label;
    btn.addEventListener('click', () => switchTab(t.id, btn));
    bar.appendChild(btn);
  });
}

function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

// ── Tab 1: Costs ───────────────────────────────────────────────────────
function renderCosts() {
  const dates = F.daily_costs.map(d => d.date);
  const models = D.models;

  charts.dailyCost = new Chart(document.getElementById('chartDailyCost'), {
    type: 'bar',
    data: {
      labels: dates,
      datasets: models.map(m => ({
        label: m,
        data: F.daily_costs.map(d => d[m] || 0),
        backgroundColor: MODEL_COLORS[m] || '#6b7280',
        borderRadius: 2,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } }, tooltip: { mode: 'index', intersect: false } },
      scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, stacked: true, title: { display: true, text: 'USD', color: '#64748b' } } }
    }
  });

  charts.cumCost = new Chart(document.getElementById('chartCumCost'), {
    type: 'line',
    data: {
      labels: F.cumulative_costs.map(d => d.date),
      datasets: [{ label: D.locale.costs.cumulative_label, data: F.cumulative_costs.map(d => d.cost),
        borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: 'USD', color: '#64748b' } } } }
  });

  charts.modelDist = new Chart(document.getElementById('chartModelDist'), {
    type: 'doughnut',
    data: {
      labels: F.model_summary.map(m => m.model),
      datasets: [{ data: F.model_summary.map(m => m.cost),
        backgroundColor: F.model_summary.map(m => MODEL_COLORS[m.model] || '#6b7280'), borderWidth: 0 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 16 } },
        tooltip: { callbacks: { label: ctx => ctx.label + ': ' + fmtUSD(ctx.raw) + ' (' + (F.kpi.total_cost > 0 ? (ctx.raw / F.kpi.total_cost * 100).toFixed(1) : '0.0') + '%)' } } } }
  });

  const cbt = F.cost_by_token_type;
  charts.tokenType = new Chart(document.getElementById('chartTokenType'), {
    type: 'bar',
    data: {
      labels: ['Input', 'Output', 'Cache Read', 'Cache Write'],
      datasets: [{ data: [cbt.input, cbt.output, cbt.cache_read, cbt.cache_write],
        backgroundColor: ['#3b82f6', '#a855f7', '#22c55e', '#f59e0b'], borderRadius: 6 }]
    },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: { ...scaleDefaults.x, title: { display: true, text: 'USD', color: '#64748b' } }, y: scaleDefaults.y } }
  });

  // Model table
  const tbody = document.getElementById('modelTableBody');
  F.model_summary.forEach(m => {
    const tr = document.createElement('tr');
    const cells = [m.model, fmtUSD(m.cost), fmtTokens(m.output_tokens), fmtTokens(m.input_tokens), fmtTokens(m.cache_read_tokens), fmt(m.calls)];
    cells.forEach((val, i) => {
      const td = document.createElement('td');
      if (i > 0) td.className = 'num';
      td.textContent = val;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Cache Efficiency
  const ct = F.cost_by_token_type;
  const cacheKpi = document.getElementById('cacheKpi');
  if (cacheKpi && ct) {
    const cacheRead = F.sessions.reduce((s,se) => s + (se.cache_read_tokens || 0), 0);
    const cacheWrite = F.sessions.reduce((s,se) => s + (se.cache_write_tokens || 0), 0);
    cacheKpi.innerHTML = [
      '<div class="kpi-card"><div class="label">Cache Read Tokens</div>',
      '<div class="value" style="color:var(--cyan)">' + fmtTokens(cacheRead) + '</div></div>',
      '<div class="kpi-card"><div class="label">Cache Write Tokens</div>',
      '<div class="value" style="color:var(--blue)">' + fmtTokens(cacheWrite) + '</div></div>',
      '<div class="kpi-card savings"><div class="label">Estimated Cache Savings</div>',
      '<div class="value" style="color:var(--green)">' + fmtUSD(ct.cache_savings || 0) + '</div>',
      '<div class="sub">vs. full input pricing</div></div>'
    ].join('');
  }
}

function renderHeatmap() {
  const container = document.getElementById('activityHeatmap');
  const monthsEl = document.getElementById('heatmapMonths');
  if (!container) return;
  const msgMap = {};
  F.daily_messages.forEach(d => { msgMap[d.date] = d.messages; });
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - (24 * 7) + 1);
  while (startDate.getDay() !== 1) startDate.setDate(startDate.getDate() - 1);
  let maxMsg = 0;
  const td = new Date(startDate);
  while (td <= today) { const k = td.toISOString().slice(0,10); maxMsg = Math.max(maxMsg, msgMap[k]||0); td.setDate(td.getDate()+1); }
  let html = '';
  const weeks = [];
  const d = new Date(startDate);
  let cw = [];
  while (d <= today) {
    const k = d.toISOString().slice(0,10);
    const m = msgMap[k]||0;
    let bg = 'var(--bg3)';
    if (m > 0 && maxMsg > 0) {
      const r = m/maxMsg;
      if (r > 0.7) bg = 'var(--accent)';
      else if (r > 0.4) bg = 'rgba(99,102,241,0.7)';
      else if (r > 0.2) bg = 'rgba(99,102,241,0.4)';
      else bg = 'rgba(99,102,241,0.2)';
    }
    cw.push('<div class="heatmap-cell" style="background:'+bg+'" data-tip="'+k+': '+m+' messages"></div>');
    if (d.getDay()===0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); cw=[]; }
    d.setDate(d.getDate()+1);
  }
  if (cw.length>0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); }
  weeks.forEach(w => { html += '<div class="heatmap-col">'+w.join('')+'</div>'; });
  container.innerHTML = html;
  if (monthsEl) {
    const months = [];
    const md = new Date(startDate);
    let lastMonth = -1, weekIdx = 0;
    while (md <= today) {
      if (md.getDay()===1) { if(md.getMonth()!==lastMonth) { months.push({idx:weekIdx,label:md.toLocaleString('default',{month:'short'})}); lastMonth=md.getMonth(); } weekIdx++; }
      md.setDate(md.getDate()+1);
    }
    monthsEl.innerHTML = '';
    monthsEl.style.paddingLeft = '20px';
    months.forEach((m,i) => {
      const span = document.createElement('span');
      span.textContent = m.label;
      span.style.width = ((i<months.length-1 ? months[i+1].idx-m.idx : weekIdx-m.idx)*15)+'px';
      monthsEl.appendChild(span);
    });
  }
}

// ── Tab 2: Activity ────────────────────────────────────────────────────
function renderActivity() {
  charts.dailyMsgs = new Chart(document.getElementById('chartDailyMsgs'), {
    type: 'bar',
    data: { labels: F.daily_messages.map(d => d.date),
      datasets: [{ label: D.locale.activity.messages_label, data: F.daily_messages.map(d => d.messages), backgroundColor: '#6366f1', borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: scaleDefaults }
  });

  const maxHourly = Math.max(...F.hourly_distribution.map(x => x.messages || 1));
  charts.hourly = new Chart(document.getElementById('chartHourly'), {
    type: 'polarArea',
    data: { labels: F.hourly_distribution.map(h => h.hour + ':00'),
      datasets: [{ data: F.hourly_distribution.map(h => h.messages),
        backgroundColor: F.hourly_distribution.map(h => 'rgba(99,102,241,' + (0.3 + 0.7 * (h.messages / maxHourly)) + ')'),
        borderWidth: 1, borderColor: '#2d3348' }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { r: { ticks: { color: '#64748b', backdropColor: 'transparent' }, grid: { color: '#1e293b' } } } }
  });

  charts.weekday = new Chart(document.getElementById('chartWeekday'), {
    type: 'bar',
    data: { labels: F.weekday_distribution.map(d => d.day),
      datasets: [{ label: D.locale.activity.messages_label, data: F.weekday_distribution.map(d => d.messages),
        backgroundColor: F.weekday_distribution.map((d, i) => i >= 5 ? '#f59e0b' : '#6366f1'), borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } }, scales: scaleDefaults }
  });

  charts.dailySessions = new Chart(document.getElementById('chartDailySessions'), {
    type: 'bar',
    data: { labels: F.daily_messages.map(d => d.date),
      datasets: [{ label: D.locale.activity.sessions_label, data: F.daily_messages.map(d => d.sessions), backgroundColor: '#06b6d4', borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: scaleDefaults }
  });
  renderHeatmap();
}

// ── Tab 3: Projects ────────────────────────────────────────────────────
function renderProjects() {
  const top = F.projects.slice(0, 15);
  charts.projectCost = new Chart(document.getElementById('chartProjectCost'), {
    type: 'bar',
    data: { labels: top.map(p => anonMode ? anonName(p.name) : p.name.split('/').pop()),
      datasets: [{ label: D.locale.projects.top15_label, data: top.map(p => p.cost), backgroundColor: '#6366f1', borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: { ...scaleDefaults.x, title: { display: true, text: 'USD', color: '#64748b' } },
        y: { ...scaleDefaults.y, ticks: { font: { size: 11 } } } } }
  });
  renderProjectTable('cost', 'desc');
}

function renderProjectTable(sortKey, sortDir) {
  const sorted = [...F.projects].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortDir === 'asc' ? va - vb : vb - va;
  });
  const tbody = document.getElementById('projectTableBody');
  tbody.textContent = '';
  sorted.forEach(p => {
    const tr = document.createElement('tr');
    const slug = D.project_slugs && D.project_slugs[p.name];
    const dispPName = anonMode ? anonName(p.name) : p.name;
    const nameCell = (!anonMode && slug) ? '<a href="projects/'+slug+'.html">'+escHtml(dispPName)+'</a>' : escHtml(dispPName);
    const cells = [
      {html: nameCell, cls: ''},
      {val: p.sessions, cls: 'num'},
      {val: fmt(p.messages), cls: 'num'},
      {val: fmtUSD(p.cost), cls: 'num'},
      {val: fmtTokens(p.output_tokens), cls: 'num'},
      {val: String(p.file_size_mb), cls: 'num'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      if (c.html) { td.innerHTML = c.html; } else { td.textContent = c.val; }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// ── Tab 4: Sessions ────────────────────────────────────────────────────
let sessionPage = 0;
const SESSION_PER_PAGE = 20;

function getFilteredSessions() {
  let list = [...F.sessions];
  const proj = document.getElementById('filterProject').value;
  const search = document.getElementById('filterSearch').value.toLowerCase();
  const sort = document.getElementById('filterSort').value;

  if (proj) list = list.filter(s => s.project === proj);
  if (search) list = list.filter(s =>
    (s.first_prompt || '').toLowerCase().includes(search) ||
    s.project.toLowerCase().includes(search));

  const [key, dir] = sort.split('-');
  list.sort((a, b) => {
    const va = key === 'date' ? a.start : a[key];
    const vb = key === 'date' ? b.start : b[key];
    if (typeof va === 'string') return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    return dir === 'asc' ? va - vb : vb - va;
  });
  return list;
}

function renderSessions() {
  const sel = document.getElementById('filterProject');
  const currentVal = sel.value;
  // Clear and rebuild options from filtered sessions
  while (sel.options.length > 1) sel.remove(1);
  const projects = [...new Set(F.sessions.map(s => s.project))].sort();
  projects.forEach(p => {
    const o = document.createElement('option');
    o.value = p; o.textContent = anonMode ? anonName(p) : p;
    sel.appendChild(o);
  });
  // Restore selection if still valid
  if (projects.includes(currentVal)) sel.value = currentVal;
  sessionPage = 0;
  renderSessionList();
}

function buildSessionCard(s) {
  const card = document.createElement('div');
  card.className = 'session-card';
  card.addEventListener('click', () => card.classList.toggle('expanded'));

  const modelClass = s.primary_model.toLowerCase().includes('opus') ? 'opus' :
                     s.primary_model.toLowerCase().includes('sonnet') ? 'sonnet' : 'haiku';

  // Top row
  const top = document.createElement('div'); top.className = 'top';
  const projSpan = document.createElement('span'); projSpan.className = 'project'; projSpan.textContent = anonMode ? anonName(s.project) : s.project;
  const costSpan = document.createElement('span'); costSpan.className = 'cost'; costSpan.textContent = fmtUSD(s.cost);
  const rightGroup = document.createElement('span'); rightGroup.style.display = 'flex'; rightGroup.style.alignItems = 'center';
  if (!anonMode) {
    const chatLink = document.createElement('a'); chatLink.href = 'sessions/' + s.session_id + '.html';
    chatLink.textContent = 'Chat'; chatLink.addEventListener('click', function(e) { e.stopPropagation(); });
    chatLink.style.cssText = 'color:var(--accent2);font-size:12px;padding:4px 10px;border:1px solid var(--accent);border-radius:6px;margin-right:8px;text-decoration:none';
    rightGroup.appendChild(chatLink);
  }
  rightGroup.appendChild(costSpan);
  top.appendChild(projSpan); top.appendChild(rightGroup);
  card.appendChild(top);

  // Info row
  const info = document.createElement('div'); info.className = 'info';
  const infoParts = [
    new Date(s.start).toLocaleString(D.locale.locale_code),
    s.duration_min + ' min',
    fmt(s.messages) + D.locale.sessions_tab.messages_suffix,
    fmt(s.api_calls) + D.locale.sessions_tab.api_calls_suffix,
  ];
  infoParts.forEach(t => { const sp = document.createElement('span'); sp.textContent = t; info.appendChild(sp); });
  const badge = document.createElement('span'); badge.className = 'model-badge ' + modelClass; badge.textContent = s.primary_model;
  info.appendChild(badge);
  if (s.compactions > 0) {
    const compSpan = document.createElement('span'); compSpan.style.color = 'var(--amber)';
    compSpan.innerHTML = '&#9889; ' + s.compactions;
    info.appendChild(compSpan);
  }
  card.appendChild(info);

  // Prompt
  if (s.first_prompt && !anonMode) {
    const prompt = document.createElement('div'); prompt.className = 'prompt';
    prompt.textContent = s.first_prompt;
    card.appendChild(prompt);
  }

  // Details (expandable)
  const details = document.createElement('div'); details.className = 'details';

  const modelDetail = Object.entries(s.model_breakdown || {})
    .map(([m, d]) => m + ': ' + fmtUSD(d.cost) + ' (' + fmtTokens(d.output_tokens) + ' out, ' + d.calls + ' calls)')
    .join(', ');
  const p1 = document.createElement('p'); p1.style.marginBottom = '8px';
  const b1 = document.createElement('strong'); b1.textContent = D.locale.sessions_tab.models_label;
  p1.appendChild(b1);
  p1.appendChild(document.createTextNode(modelDetail));
  details.appendChild(p1);

  const p2 = document.createElement('p');
  p2.textContent = 'Output: ' + fmtTokens(s.output_tokens) + ' | Input: ' + fmtTokens(s.input_tokens) + ' | Cache Read: ' + fmtTokens(s.cache_read_tokens);
  details.appendChild(p2);

  const toolEntries = Object.entries(s.tools || {}).sort((a,b) => b[1]-a[1]).slice(0, 10);
  if (toolEntries.length > 0) {
    const toolsDiv = document.createElement('div'); toolsDiv.className = 'tools'; toolsDiv.style.marginTop = '8px';
    const b2 = document.createElement('strong'); b2.textContent = 'Tools: '; toolsDiv.appendChild(b2);
    toolEntries.forEach(([name, count]) => {
      const tag = document.createElement('span'); tag.className = 'tool-tag';
      tag.textContent = name + ' (' + count + ')';
      toolsDiv.appendChild(tag);
    });
    details.appendChild(toolsDiv);
  }

  const p3 = document.createElement('p');
  p3.style.marginTop = '8px'; p3.style.color = 'var(--text2)'; p3.style.fontSize = '11px';
  p3.textContent = D.locale.sessions_tab.session_label + s.session_id + D.locale.sessions_tab.slug_label + (s.slug || '-');
  details.appendChild(p3);

  card.appendChild(details);
  return card;
}

function renderSessionList() {
  const filtered = getFilteredSessions();
  const total = filtered.length;
  const pages = Math.ceil(total / SESSION_PER_PAGE);
  sessionPage = Math.min(sessionPage, Math.max(pages - 1, 0));

  const start = sessionPage * SESSION_PER_PAGE;
  const page = filtered.slice(start, start + SESSION_PER_PAGE);

  document.getElementById('sessionCount').textContent = total + D.locale.sessions_tab.sessions_count_suffix;

  const container = document.getElementById('sessionList');
  container.textContent = '';
  page.forEach(s => container.appendChild(buildSessionCard(s)));

  // Pagination
  const pagDiv = document.getElementById('sessionPagination');
  pagDiv.textContent = '';
  if (pages > 1) {
    if (sessionPage > 0) {
      const first = document.createElement('button'); first.textContent = '\u00AB';
      first.addEventListener('click', () => { sessionPage = 0; renderSessionList(); });
      const prev = document.createElement('button'); prev.textContent = '\u2039';
      prev.addEventListener('click', () => { sessionPage--; renderSessionList(); });
      pagDiv.appendChild(first); pagDiv.appendChild(prev);
    }
    const info = document.createElement('span'); info.className = 'info';
    info.textContent = D.locale.sessions_tab.page_prefix + (sessionPage + 1) + D.locale.sessions_tab.page_separator + pages;
    pagDiv.appendChild(info);
    if (sessionPage < pages - 1) {
      const next = document.createElement('button'); next.textContent = '\u203A';
      next.addEventListener('click', () => { sessionPage++; renderSessionList(); });
      const last = document.createElement('button'); last.textContent = '\u00BB';
      last.addEventListener('click', () => { sessionPage = pages - 1; renderSessionList(); });
      pagDiv.appendChild(next); pagDiv.appendChild(last);
    }
  }
}

// ── Tab 5: Plan & Billing ──────────────────────────────────────────────
function renderPlan() {
  const plan = D.plan;
  if (!plan) return;
  const cb = plan.current_billing;

  // KPI cards
  const grid = document.getElementById('planKpi');
  const kpis = [
    {cls:'plan-type', label:D.locale.plan.current_plan, value:cb.plan, sub:fmtUSD(cb.plan_cost_usd) + D.locale.plan.monthly_suffix + (cb.plan_cost_eur != null ? ' (' + cb.plan_cost_eur.toFixed(2) + ' \\u20ac)' : '')},
    {cls:'api-cost', label:D.locale.plan.total_api_cost, value:fmtUSD(plan.total_api_cost), sub:D.locale.plan.total_api_sub},
    {cls:'savings', label:D.locale.plan.total_savings, value:fmtUSD(plan.total_savings), sub:D.locale.plan.total_savings_sub},
    {cls:'roi', label:D.locale.plan.roi_factor, value:plan.overall_roi + 'x', sub:D.locale.plan.roi_sub},
  ];
  kpis.forEach(c => {
    const div = document.createElement('div');
    div.className = 'plan-card ' + c.cls;
    const lbl = document.createElement('div'); lbl.className = 'label'; lbl.textContent = c.label;
    const val = document.createElement('div'); val.className = 'value'; val.textContent = c.value;
    const sub = document.createElement('div'); sub.className = 'sub'; sub.textContent = c.sub;
    div.appendChild(lbl); div.appendChild(val); div.appendChild(sub);
    grid.appendChild(div);
  });

  // Billing progress
  const bp = document.getElementById('billingProgress');
  const pct = Math.min(100, Math.round(cb.days_elapsed / cb.days_total * 100));
  const barColor = cb.api_cost > cb.plan_cost_usd * 0.8 ? 'var(--green)' : 'var(--accent)';

  const h3 = document.createElement('h3');
  h3.textContent = D.locale.plan.billing_period + ' (' + cb.period_start + ' \u2013 ' + cb.period_end + ')';
  bp.appendChild(h3);

  const outer = document.createElement('div'); outer.className = 'progress-bar-outer';
  const inner = document.createElement('div'); inner.className = 'progress-bar-inner';
  inner.style.width = pct + '%';
  inner.style.background = 'linear-gradient(90deg, var(--accent), ' + barColor + ')';
  inner.textContent = pct + '%';
  outer.appendChild(inner);
  bp.appendChild(outer);

  const stats = document.createElement('div'); stats.className = 'progress-stats';
  const statItems = [
    {label:D.locale.plan.day, val:cb.days_elapsed + ' / ' + cb.days_total},
    {label:D.locale.plan.api_cost_so_far, val:fmtUSD(cb.api_cost)},
    {label:D.locale.plan.projected, val:fmtUSD(cb.projected_cost)},
    {label:D.locale.plan.savings_so_far, val:fmtUSD(cb.savings)},
    {label:D.locale.plan.roi, val:cb.roi_factor + 'x'},
    {label:D.locale.plan.sessions, val:String(cb.sessions)},
    {label:D.locale.plan.messages, val:fmt(cb.messages)},
    {label:D.locale.plan.avg_per_day, val:fmtUSD(cb.cost_per_day)},
  ];
  statItems.forEach(s => {
    const item = document.createElement('div'); item.className = 'stat-item';
    const lbl = document.createElement('span'); lbl.textContent = s.label;
    const val = document.createElement('span'); val.className = 'stat-val'; val.textContent = s.val;
    item.appendChild(lbl); item.appendChild(val);
    stats.appendChild(item);
  });
  bp.appendChild(stats);

  // Comparison bars
  const comp = document.getElementById('planComparison');
  const maxApi = Math.max(...plan.periods.map(p => p.api_cost), 1);

  plan.periods.forEach(p => {
    const row = document.createElement('div'); row.className = 'bar-row';
    const label = document.createElement('div'); label.className = 'bar-label';
    label.textContent = p.plan + ' (' + p.start.slice(5) + ' - ' + p.end.slice(5) + ')';

    const track = document.createElement('div'); track.className = 'bar-track';
    const apiBar = document.createElement('div'); apiBar.className = 'bar-fill';
    apiBar.style.width = (p.api_cost / maxApi * 100) + '%';
    apiBar.style.background = 'var(--orange)';
    apiBar.textContent = D.locale.plan.api_label;
    track.appendChild(apiBar);

    const val = document.createElement('div'); val.className = 'bar-val';
    val.textContent = fmtUSD(p.api_cost);
    val.style.color = 'var(--orange)';

    row.appendChild(label); row.appendChild(track); row.appendChild(val);
    comp.appendChild(row);

    const row2 = document.createElement('div'); row2.className = 'bar-row';
    const label2 = document.createElement('div'); label2.className = 'bar-label';
    label2.style.color = 'var(--text2)';
    label2.textContent = '';

    const track2 = document.createElement('div'); track2.className = 'bar-track';
    const planBar = document.createElement('div'); planBar.className = 'bar-fill';
    planBar.style.width = (p.plan_cost_usd / maxApi * 100) + '%';
    planBar.style.background = 'var(--accent)';
    planBar.textContent = D.locale.plan.plan_label;
    track2.appendChild(planBar);

    const val2 = document.createElement('div'); val2.className = 'bar-val';
    val2.textContent = fmtUSD(p.plan_cost_usd);
    val2.style.color = 'var(--accent2)';

    row2.appendChild(label2); row2.appendChild(track2); row2.appendChild(val2);
    comp.appendChild(row2);
  });

  // Charts
  const periodLabels = plan.periods.map(p => p.plan + ' (' + p.start.slice(5) + ')');

  new Chart(document.getElementById('chartPlanSavings'), {
    type: 'bar',
    data: {
      labels: periodLabels,
      datasets: [
        {label: D.locale.plan.api_cost_label, data: plan.periods.map(p => p.api_cost), backgroundColor: 'rgba(245,158,11,0.7)', borderRadius: 4},
        {label: D.locale.plan.plan_cost_label, data: plan.periods.map(p => p.plan_cost_usd), backgroundColor: 'rgba(99,102,241,0.7)', borderRadius: 4},
      ]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: 'USD', color: '#64748b' } } } }
  });

  new Chart(document.getElementById('chartCostPerDay'), {
    type: 'bar',
    data: {
      labels: periodLabels,
      datasets: [{ label: D.locale.plan.api_cost_per_day_label, data: plan.periods.map(p => p.cost_per_day),
        backgroundColor: plan.periods.map(p => p.plan === 'Max' ? 'rgba(34,197,94,0.7)' : 'rgba(245,158,11,0.7)'),
        borderRadius: 4 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: D.locale.plan.usd_per_day, color: '#64748b' } } } }
  });

  // Period table
  const tbody = document.getElementById('planTableBody');
  plan.periods.forEach(p => {
    const tr = document.createElement('tr');
    const cells = [
      {val: p.start + ' \\u2013 ' + p.end, cls:''},
      {val: p.plan, cls:''},
      {val: p.total_days + ' (' + p.days_active + D.locale.plan.active_suffix + ')', cls:'num'},
      {val: fmtUSD(p.api_cost), cls:'num'},
      {val: fmtUSD(p.plan_cost_usd), cls:'num'},
      {val: fmtUSD(p.savings), cls:'num'},
      {val: p.roi_factor + 'x', cls:'num'},
      {val: String(p.sessions), cls:'num'},
      {val: fmt(p.messages), cls:'num'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.textContent = c.val;
      if (c.val.startsWith('$') && parseFloat(c.val.replace(/[^0-9.-]/g, '')) > 100) td.style.color = 'var(--green)';
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Total row
  const trTotal = document.createElement('tr');
  trTotal.style.fontWeight = '700';
  trTotal.style.borderTop = '2px solid var(--border)';
  const totalCells = [
    {val: D.locale.plan.total, cls:''},
    {val: '', cls:''},
    {val: '', cls:'num'},
    {val: fmtUSD(plan.total_api_cost), cls:'num'},
    {val: fmtUSD(plan.total_plan_cost), cls:'num'},
    {val: fmtUSD(plan.total_savings), cls:'num'},
    {val: plan.overall_roi + 'x', cls:'num'},
    {val: '', cls:'num'},
    {val: '', cls:'num'},
  ];
  totalCells.forEach(c => {
    const td = document.createElement('td');
    if (c.cls) td.className = c.cls;
    td.textContent = c.val;
    trTotal.appendChild(td);
  });
  tbody.appendChild(trTotal);
}

// ── Tab 6: Insights ───────────────────────────────────────────────────
function renderInsights() {
  const ins = D.insights;
  if (!ins) return;

  // Tool usage chart
  renderToolUsageChart();

  // Storage chart
  const storage = ins.storage || {};
  const storageItems = (storage.items || []).filter(s => s.size_mb >= 0.1);
  if (storageItems.length > 0) {
    new Chart(document.getElementById('chartStorage'), {
      type: 'doughnut',
      data: { labels: storageItems.map(s => s.name),
        datasets: [{ data: storageItems.map(s => s.size_mb),
          backgroundColor: storageItems.map((_, i) => 'hsl(' + (i * 40 + 200) + ',55%,50%)'), borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { color: '#94a3b8', padding: 8, font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.raw + ' MB' } } } }
    });
  }

  // Plugin table
  const plugins = ins.plugins || {};
  const installed = plugins.installed || [];
  const enabled = plugins.settings?.enabled_plugins || {};
  const mktStats = plugins.marketplace_stats || {};
  const tbody = document.getElementById('pluginTableBody');
  installed.forEach(p => {
    const tr = document.createElement('tr');
    const isEnabled = enabled[p.name] !== false;
    const globalInstalls = mktStats[p.name] || 0;
    const cells = [
      {val: p.short_name, cls: ''},
      {val: isEnabled ? D.locale.insights.active : D.locale.insights.inactive, cls: '', badge: isEnabled ? 'active' : 'inactive'},
      {val: p.version, cls: ''},
      {val: globalInstalls > 0 ? fmt(globalInstalls) : '-', cls: 'num'},
      {val: p.installed_at ? new Date(p.installed_at).toLocaleDateString(D.locale.locale_code) : '-', cls: ''},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      if (c.badge) {
        const span = document.createElement('span');
        span.className = 'plugin-status ' + c.badge;
        span.textContent = c.val;
        td.appendChild(span);
      } else {
        td.textContent = c.val;
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Config info
  const configDiv = document.getElementById('configInfo');
  const settings = plugins.settings || {};
  const configItems = [
    {label: D.locale.insights.permission_mode, value: settings.permission_mode || '-'},
    {label: D.locale.insights.auto_updates, value: settings.auto_updates || '-'},
    {label: D.locale.insights.plugins_installed, value: String(installed.length)},
    {label: D.locale.insights.plugins_active, value: String(Object.values(enabled).filter(v => v).length)},
    {label: D.locale.insights.total_storage, value: (storage.total_mb || 0) + ' MB'},
    {label: D.locale.insights.transcripts, value: ((storage.items || []).find(s => s.name === 'projects/') || {}).size_mb + ' MB'},
    {label: D.locale.insights.debug_logs, value: ((storage.items || []).find(s => s.name === 'debug/') || {}).size_mb + ' MB'},
    {label: D.locale.insights.file_history_label, value: ((storage.items || []).find(s => s.name === 'file-history/') || {}).size_mb + ' MB'},
  ];
  const grid = document.createElement('div'); grid.className = 'config-grid';
  configItems.forEach(c => {
    const item = document.createElement('div'); item.className = 'config-item';
    const lbl = document.createElement('div'); lbl.className = 'ci-label'; lbl.textContent = c.label;
    const val = document.createElement('div'); val.className = 'ci-value'; val.textContent = c.value;
    item.appendChild(lbl); item.appendChild(val);
    grid.appendChild(item);
  });
  configDiv.appendChild(grid);

  // Plans table
  const plans = ins.plans || [];
  const plansTbody = document.getElementById('plansTableBody');
  plans.forEach(p => {
    const tr = document.createElement('tr');
    const cells = [
      {val: p.title, cls: ''},
      {val: new Date(p.created).toLocaleDateString(D.locale.locale_code), cls: ''},
      {val: String(p.lines), cls: 'num'},
      {val: String(p.size_kb), cls: 'num'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.textContent = c.val;
      tr.appendChild(td);
    });
    plansTbody.appendChild(tr);
  });

  // Misc stats (file history + todos)
  const fh = ins.file_history || {};
  const todos = ins.todos || {};
  const miscDiv = document.getElementById('miscStats');
  const miscGrid = document.createElement('div'); miscGrid.className = 'misc-stat-grid';
  const miscItems = [
    {val: String(fh.total_files || 0), label: D.locale.insights.file_snapshots},
    {val: String(fh.total_sessions || 0), label: D.locale.insights.sessions_with_snapshots},
    {val: (fh.total_size_mb || 0) + ' MB', label: D.locale.insights.snapshot_size},
    {val: String(todos.total || 0), label: D.locale.insights.todos_total},
    {val: String(todos.completed || 0), label: D.locale.insights.todos_completed},
    {val: todos.total > 0 ? Math.round(todos.completed / todos.total * 100) + '%' : '-', label: D.locale.insights.completion_rate},
  ];
  miscItems.forEach(m => {
    const div = document.createElement('div'); div.className = 'misc-stat';
    const val = document.createElement('div'); val.className = 'ms-val'; val.textContent = m.val;
    const lbl = document.createElement('div'); lbl.className = 'ms-label'; lbl.textContent = m.label;
    div.appendChild(val); div.appendChild(lbl);
    miscGrid.appendChild(div);
  });
  miscDiv.appendChild(miscGrid);

  // Skills
  const skillsEl = document.getElementById('skillsList');
  if (skillsEl && D.skill_summary && D.skill_summary.length > 0) {
    skillsEl.innerHTML = D.skill_summary.map(s =>
      '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border)">' +
      '<span style="font-size:13px;color:var(--text)">' + escHtml(s.name) + '</span>' +
      '<span class="tool-tag" style="background:rgba(168,85,247,0.2);color:var(--purple)">' + s.count + 'x</span>' +
      '</div>'
    ).join('');
  } else if (skillsEl) {
    skillsEl.innerHTML = '<p style="color:var(--text2);font-size:13px;padding:12px">No skills used yet</p>';
  }

  // Hooks
  const hooksEl = document.getElementById('hooksList');
  if (hooksEl && D.hook_summary && D.hook_summary.length > 0) {
    hooksEl.innerHTML = D.hook_summary.map(h => {
      const parts = h.name.split(':');
      const event = parts[0] || '';
      const name = parts.slice(1).join(':') || h.name;
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border)">' +
        '<div><span class="model-badge" style="background:rgba(245,158,11,0.2);color:var(--orange);font-size:10px;margin-right:6px">' + escHtml(event) + '</span><span style="font-size:13px">' + escHtml(name) + '</span></div>' +
        '<span class="tool-tag">' + h.count + 'x</span>' +
        '</div>';
    }).join('');
  } else if (hooksEl) {
    hooksEl.innerHTML = '<p style="color:var(--text2);font-size:13px;padding:12px">No hooks fired yet</p>';
  }

  // System info
  const envInfo = D.insights?.telemetry?.env_info || {};
  const sysEl = document.getElementById('systemInfo');
  if (sysEl) {
    sysEl.innerHTML =
      '<div class="sidebar-row"><span class="label">Platform</span><span class="val">'+(envInfo.platform||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Node</span><span class="val">'+(envInfo.node_version||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Claude Code</span><span class="val">'+(envInfo.claude_version||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Terminal</span><span class="val">'+(envInfo.terminal||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Arch</span><span class="val">'+(envInfo.arch||'\\u2014')+'</span></div>';
  }

  // Git ops
  const gs = D.git_summary || {};
  const gitEl = document.getElementById('gitOpsInfo');
  if (gitEl) {
    gitEl.innerHTML =
      '<div class="sidebar-row"><span class="label">__L_insights_commits__</span><span class="val" style="color:var(--green)">'+(gs.commits||0)+'</span></div>' +
      '<div class="sidebar-row"><span class="label">__L_insights_pushes__</span><span class="val" style="color:var(--blue)">'+(gs.pushes||0)+'</span></div>' +
      '<div class="sidebar-row"><span class="label">__L_insights_pull_requests__</span><span class="val" style="color:var(--purple)">'+(gs.prs||0)+'</span></div>';
  }

  // Memory per session chart
  const telSessions = D.insights?.telemetry?.per_session || {};
  const memData = D.sessions.filter(s => telSessions[s.session_id]).map(s => ({
    date: s.date, rss: telSessions[s.session_id].peak_rss_mb
  }));
  if (memData.length > 0) {
    new Chart(document.getElementById('memoryChart'), {
      type: 'bar',
      data: {
        labels: memData.map(d => d.date),
        datasets: [{ label: 'Peak RSS (MB)', data: memData.map(d => d.rss), backgroundColor: 'rgba(168,85,247,0.6)', borderRadius:3 }]
      },
      options: { responsive:true, plugins:{legend:{labels:{color:'#e2e8f0'}}}, scales:{ x:{ticks:{color:'#94a3b8',maxTicksLimit:15}}, y:{ticks:{color:'#94a3b8'}} } }
    });
  }

  // Error rate over time chart
  const dailyErrors = {};
  D.sessions.forEach(s => {
    if (!dailyErrors[s.date]) dailyErrors[s.date] = {errors:0, calls:0};
    dailyErrors[s.date].errors += s.error_count || 0;
    dailyErrors[s.date].calls += s.api_calls || 0;
  });
  const errDates = Object.keys(dailyErrors).sort();
  const errRates = errDates.map(d => dailyErrors[d].calls > 0 ? +(dailyErrors[d].errors / dailyErrors[d].calls * 100).toFixed(1) : 0);
  if (errDates.length > 0) {
    new Chart(document.getElementById('errorRateChart'), {
      type: 'line',
      data: {
        labels: errDates,
        datasets: [{ label: 'Error Rate (%)', data: errRates, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', fill:true, tension:0.3 }]
      },
      options: { responsive:true, plugins:{legend:{labels:{color:'#e2e8f0'}}}, scales:{ x:{ticks:{color:'#94a3b8',maxTicksLimit:15}}, y:{ticks:{color:'#94a3b8'}, beginAtZero:true} } }
    });
  }
}

// ── Tab 7: Agents ──────────────────────────────────────────────────────

function renderAgentsTab() {
  const as = F.agent_summary || D.agent_summary || {};
  const es = F.error_summary || D.error_summary || {};

  // Subagent types donut
  const atd = as.type_distribution || [];
  if (agentTypesChartInstance) agentTypesChartInstance.destroy();
  if (atd.length > 0) {
    agentTypesChartInstance = new Chart(document.getElementById('agentTypesChart'), {
      type: 'doughnut',
      data: {
        labels: atd.map(d => d.type),
        datasets: [{ data: atd.map(d => d.count), backgroundColor: chartColors }]
      },
      options: { responsive:true, plugins:{ legend:{ position:'right', labels:{color:'#e2e8f0',font:{size:11}} } } }
    });
  }

  // Top descriptions bar
  const tds = as.top_descriptions || [];
  if (agentDescsChartInstance) agentDescsChartInstance.destroy();
  if (tds.length > 0) {
    agentDescsChartInstance = new Chart(document.getElementById('agentDescsChart'), {
      type: 'bar',
      data: {
        labels: tds.map(d => d.desc.length > 30 ? d.desc.slice(0,30)+'...' : d.desc),
        datasets: [{ data: tds.map(d => d.count), backgroundColor: 'rgba(99,102,241,0.7)', borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:'#94a3b8'}}, y:{ticks:{color:'#94a3b8',font:{size:10}}} } }
    });
  }

  // KPI cards
  const kpiEl = document.getElementById('agentKpis');
  kpiEl.innerHTML = '';
  const agentKpis = [
    {val: as.total_dispatches || 0, color:'var(--purple)', label:'__L_agents_dispatches__'},
    {val: (F.insights?.tasks?.total || D.insights?.tasks?.total || 0), color:'var(--cyan)', label:'__L_agents_total_tasks__'},
    {val: (es.error_rate || 0) + '%', color:'var(--red)', label:'__L_agents_error_rate__'},
  ];
  agentKpis.forEach(k => {
    const div = document.createElement('div');
    div.className = 'kpi-card';
    div.innerHTML = '<div class="label">'+k.label+'</div><div class="value" style="color:'+k.color+'">'+k.val+'</div>';
    kpiEl.appendChild(div);
  });

  // Task overview
  const taskEl = document.getElementById('taskOverview');
  const tasks = D.insights?.tasks || {};
  if (tasks.total > 0) {
    const pct = Math.round((tasks.completed / tasks.total) * 100);
    taskEl.innerHTML =
      '<div style="display:flex;gap:16px;align-items:center;margin-bottom:12px">' +
        '<div style="width:80px;height:80px;position:relative"><canvas id="taskDonut"></canvas></div>' +
        '<div><div style="font-size:24px;font-weight:700">'+pct+'%</div><div style="color:var(--text2);font-size:12px">__L_agents_task_completion__</div></div>' +
      '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<span class="tag" style="background:rgba(34,197,94,0.15);color:var(--green)">\\u2713 '+tasks.completed+' completed</span>' +
        '<span class="tag" style="background:rgba(99,102,241,0.15);color:var(--accent2)">\\u25B6 '+(tasks.in_progress||0)+' in progress</span>' +
        '<span class="tag" style="background:rgba(148,163,184,0.15);color:var(--text2)">\\u25CB '+(tasks.pending||0)+' pending</span>' +
      '</div>';
    new Chart(document.getElementById('taskDonut'), {
      type: 'doughnut',
      data: { labels:['Completed','Pending','In Progress'], datasets:[{data:[tasks.completed,tasks.pending||0,tasks.in_progress||0], backgroundColor:['#22c55e','#94a3b8','#6366f1']}] },
      options: { cutout:'70%', responsive:true, plugins:{legend:{display:false}} }
    });
  } else {
    taskEl.innerHTML = '<div style="color:var(--text2)">No tasks found</div>';
  }

  // Error overview
  const errEl = document.getElementById('errorOverview');
  const catLabels = {'rejected':'Rejected','file_not_found':'File Not Found','edit_not_unique':'Edit Not Unique','edit_no_match':'Edit No Match','permission_denied':'Permission Denied','timeout':'Timeout','command_not_found':'Cmd Not Found','exit_code':'Exit Code Error','syntax_error':'Syntax Error','import_error':'Import Error','hook_error':'Hook Error','edit_failed':'Edit Failed','other':'Other'};
  const topCats = (es.by_category || []).slice(0, 5);
  errEl.innerHTML =
    '<div style="margin-bottom:12px"><span style="font-size:20px;font-weight:700;color:var(--red)">'+(es.total_errors||0)+'</span> errors / <span style="font-weight:600">'+(es.total_tool_calls||0)+'</span> tool calls</div>' +
    '<div style="font-size:12px;color:var(--text2);margin-bottom:8px">__L_agents_error_rate__: '+(es.error_rate||0)+'%</div>' +
    '<div style="margin-top:12px">' + topCats.map(c =>
      '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">' +
        '<span style="font-size:12px">'+(catLabels[c.category]||c.category)+'</span>' +
        '<span style="font-size:12px;font-weight:600;color:var(--red)">'+c.count+'</span></div>'
    ).join('') + '</div>';

  // Error by category doughnut
  const ebc = es.by_category || [];
  if (errorByCatChartInstance) errorByCatChartInstance.destroy();
  if (ebc.length > 0) {
    const errColors = ['#ef4444','#f97316','#eab308','#22c55e','#06b6d4','#6366f1','#a855f7','#ec4899','#64748b','#78716c','#84cc16','#14b8a6','#f43f5e'];
    errorByCatChartInstance = new Chart(document.getElementById('errorByCategoryChart'), {
      type: 'doughnut',
      data: {
        labels: ebc.map(e => catLabels[e.category] || e.category),
        datasets: [{ data: ebc.map(e => e.count), backgroundColor: errColors }]
      },
      options: { responsive:true, plugins:{ legend:{ position:'right', labels:{color:'#e2e8f0',font:{size:11}} } } }
    });
  }

  // Error by tool bar chart
  const ebt = (es.by_tool || []).slice(0, 10);
  if (errorByToolChartInstance) errorByToolChartInstance.destroy();
  if (ebt.length > 0) {
    errorByToolChartInstance = new Chart(document.getElementById('errorByToolChart'), {
      type: 'bar',
      data: {
        labels: ebt.map(e => e.tool),
        datasets: [{ data: ebt.map(e => e.count), backgroundColor: 'rgba(239,68,68,0.7)', borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:'#94a3b8'}}, y:{ticks:{color:'#94a3b8',font:{size:11}}} } }
    });
  }
}

// ── Sortable Tables ────────────────────────────────────────────────────
document.querySelectorAll('.sortable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    const table = th.closest('table');
    const current = th.classList.contains('sort-asc') ? 'asc' : th.classList.contains('sort-desc') ? 'desc' : null;
    table.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
    const dir = current === 'desc' ? 'asc' : 'desc';
    th.classList.add('sort-' + dir);
    renderProjectTable(key, dir);
  });
});

// ── Filter events ──────────────────────────────────────────────────────
document.getElementById('filterProject').addEventListener('change', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('filterSort').addEventListener('change', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('filterSearch').addEventListener('input', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('hideEmptySessions').addEventListener('change', () => { applyFilter(currentDays); });

// ── Init ───────────────────────────────────────────────────────────────
filterData(0, '');
initTimeFilter();
let pfTimer;
document.getElementById('projectFilter').addEventListener('input', function() {
  clearTimeout(pfTimer);
  pfTimer = setTimeout(() => applyFilter(undefined, this.value), 300);
});
initTabs();
renderKPI();
renderCosts();
renderActivity();
renderProjects();
renderSessions();
renderPlan();
renderInsights();
renderAgentsTab();

// F2 Anonymization mode
const anonMap = {};
let anonCounter = 0;
function anonName(name) {
  if (!anonMap[name]) { anonCounter++; anonMap[name] = 'Project ' + anonCounter; }
  return anonMap[name];
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    anonMode = !anonMode;
    document.body.classList.toggle('anon-mode', anonMode);
    // Re-render everything via applyFilter (handles cleanup)
    applyFilter(currentDays);
    // Show/hide notification
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.style.cssText = 'position:fixed;top:12px;right:12px;padding:8px 16px;border-radius:8px;font-size:12px;font-weight:600;z-index:9999;transition:opacity 0.3s;';
      document.body.appendChild(note);
    }
    note.style.background = anonMode ? 'var(--green)' : 'var(--red)';
    note.style.color = 'white';
    note.textContent = anonMode ? 'Anonymization ON' : 'Anonymization OFF';
    note.style.opacity = '1';
    setTimeout(() => { note.style.opacity = '0'; }, 2000);
  }
});
</script>
<div style="text-align:center;padding:24px 0 8px;color:#475569;font-size:11px;">v__VERSION__</div>
<div style="text-align:center;padding:0 0 16px;color:#64748b;font-size:10px;">Contains private data &mdash; do not share publicly | Press F2 to toggle anonymization | <a href="https://github.com/AeternaLabsHQ/claude-code-stats" style="color:#818cf8" target="_blank">GitHub</a></div>
</body>
</html>'''


def build_session_flow(messages):
    """Build a flow graph from the flat message list for Canvas visualization."""
    if not messages:
        return {"agents": [], "events": [], "edges": []}

    # Main agent is always present
    agents = [{
        "id": "main",
        "name": "Claude",
        "type": "main",
        "parent_id": None,
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "cost": 0.0,
        "tools_summary": {}
    }]
    agents.append({
        "id": "user",
        "name": "User",
        "type": "user",
        "parent_id": None,
        "tokens": None,
        "cost": None,
        "tools_summary": {}
    })
    events = []
    edges = []
    edges.append({"from": "user", "to": "main", "type": "conversation"})
    subagent_counter = 0

    # Determine session start time for relative timestamps
    first_ts = None
    for m in messages:
        ts = m.get("timestamp")
        if ts:
            if isinstance(ts, str):
                try:
                    first_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
                except Exception:
                    first_ts = 0
            elif isinstance(ts, (int, float)):
                first_ts = float(ts)
            break
    if first_ts is None:
        first_ts = 0

    def relative_t(timestamp):
        """Convert a timestamp to milliseconds relative to session start."""
        if not timestamp:
            return 0
        if isinstance(timestamp, str):
            try:
                ts_ms = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() * 1000
                return max(0, ts_ms - first_ts)
            except Exception:
                return 0
        elif isinstance(timestamp, (int, float)):
            return max(0, float(timestamp) - first_ts)
        return 0

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        t = relative_t(msg.get("timestamp"))

        if role == "user":
            events.append({
                "type": "message",
                "agent_id": "main",
                "role": "user",
                "t": t,
                "msg_index": i
            })

        elif role == "assistant":
            tokens = msg.get("tokens", {})
            agents[0]["tokens"]["input"] += tokens.get("input", 0)
            agents[0]["tokens"]["output"] += tokens.get("output", 0)
            agents[0]["tokens"]["cache_read"] += tokens.get("cache_read", 0)
            agents[0]["tokens"]["cache_write"] += tokens.get("cache_write", 0)
            agents[0]["cost"] += msg.get("cost", 0.0)

            events.append({
                "type": "message",
                "agent_id": "main",
                "role": "assistant",
                "t": t,
                "msg_index": i
            })

            for tool in msg.get("tools", []):
                tool_name = tool.get("name", "")
                agents[0]["tools_summary"][tool_name] = agents[0]["tools_summary"].get(tool_name, 0) + 1

                if tool_name == "Agent":
                    agent_id = f"subagent-{subagent_counter}"
                    subagent_counter += 1
                    agents.append({
                        "id": agent_id,
                        "name": tool.get("detail", "Sub-agent")[:80],
                        "type": tool.get("agent_type", "general-purpose"),
                        "parent_id": "main",
                        "tokens": None,
                        "cost": None,
                        "tools_summary": {}
                    })
                    edges.append({
                        "from": "main",
                        "to": agent_id,
                        "type": "dispatch"
                    })
                    events.append({
                        "type": "agent_spawn",
                        "agent_id": agent_id,
                        "parent_id": "main",
                        "t": t,
                        "msg_index": i
                    })
                else:
                    events.append({
                        "type": "tool_call",
                        "agent_id": "main",
                        "tool": tool_name,
                        "detail": tool.get("detail", "")[:120],
                        "t": t,
                        "msg_index": i
                    })

        elif role == "compaction":
            events.append({
                "type": "compaction",
                "agent_id": "main",
                "t": t,
                "msg_index": i
            })

        elif role == "hook":
            events.append({
                "type": "hook",
                "agent_id": "main",
                "hook_name": msg.get("hook_name", ""),
                "t": t,
                "msg_index": i
            })

    # Count user messages for the user node
    user_msg_count = sum(1 for e in events if e.get("type") == "message" and e.get("role") == "user")
    # Update user node with message count (agents[1] is the user node)
    agents[1]["message_count"] = user_msg_count

    events.sort(key=lambda e: e["t"])

    return {"agents": agents, "events": events, "edges": edges}


def generate_session_pages(sessions, session_list):
    """Generate individual HTML pages for each session."""
    sessions_dir = OUTPUT_DIR / "sessions"
    sessions_dir.mkdir(exist_ok=True)

    count = 0
    for sess_data in session_list:
        sid = sess_data["session_id"]
        project_dir = sess_data.get("project_dir", "")
        messages = extract_session_messages(sid, project_dir)

        if not messages:
            continue

        flow_data = build_session_flow(messages)

        session_json = json.dumps({
            "session": sess_data,
            "messages": messages,
        }, ensure_ascii=False)

        html = _get_session_html_template()
        html = html.replace('"__SESSION_DATA__"', session_json)
        flow_json = json.dumps(flow_data, ensure_ascii=False, separators=(',', ':'))
        html = html.replace('"__FLOW_DATA__"', flow_json)
        html = html.replace('__VERSION__', VERSION)

        out_path = sessions_dir / f"{sid}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1

    print(f"  Generated {count} session pages in {sessions_dir}")


def _get_session_html_template():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Session Detail</title>
<link rel="icon" type="image/png" href="../favicon.png">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<style>
:root { --bg:#0f1117; --bg2:#1a1d27; --bg3:#242836; --border:#2d3348; --text:#e2e8f0; --text2:#94a3b8; --accent:#6366f1; --accent2:#818cf8; --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --blue:#3b82f6; --purple:#a855f7; --cyan:#06b6d4; --amber:#f59e0b; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,-apple-system,sans-serif; font-size:14px; }
a { color:var(--accent2); text-decoration:none; }
a:hover { text-decoration:underline; }
.header { background:var(--bg2); border-bottom:1px solid var(--border); padding:16px 24px; }
.header-top { display:flex; align-items:center; gap:16px; margin-bottom:8px; }
.header h1 { font-size:18px; font-weight:600; flex:1; }
.session-meta { display:flex; gap:16px; color:var(--text2); font-size:12px; flex-wrap:wrap; }
.session-meta span { display:flex; align-items:center; gap:4px; }
.model-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }
.model-badge.opus { background:rgba(168,85,247,0.2); color:var(--purple); }
.model-badge.sonnet { background:rgba(59,130,246,0.2); color:var(--blue); }
.model-badge.haiku { background:rgba(34,197,94,0.2); color:var(--green); }
.stats-bar { display:grid; grid-template-columns:repeat(6,1fr); gap:12px; padding:16px 24px; background:var(--bg2); border-bottom:1px solid var(--border); }
.stat-card { text-align:center; }
.stat-card .label { font-size:11px; color:var(--text2); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }
.stat-card .value { font-size:20px; font-weight:700; }
.main-layout { display:grid; grid-template-columns:2fr 1fr; gap:0; max-width:1600px; margin:0 auto; }
.chat-panel { padding:0 0 20px 0; flex:1; overflow-y:auto; border-right:1px solid var(--border); }
.left-column{display:flex;flex-direction:column;max-height:calc(100vh - 180px);overflow:hidden}
.flow-container{position:relative;height:40%;min-height:200px;background:#0a0a0f;border-bottom:1px solid #1a1a2e}
.flow-container.fullscreen{position:fixed;top:0;left:0;right:0;bottom:0;height:100vh!important;z-index:1000;min-height:unset}
.flow-container canvas{width:100%;height:100%;display:block}
.flow-toolbar{position:absolute;top:8px;left:8px;display:flex;gap:6px;z-index:10}
.flow-toolbar button{background:rgba(10,10,15,0.8);color:#8888aa;border:1px solid #1a1a2e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px;backdrop-filter:blur(4px)}
.flow-toolbar button:hover{color:#00d4ff;border-color:#00d4ff40}
.flow-toolbar button.active{color:#00d4ff;border-color:#00d4ff60}
.flow-toolbar .speed-btn{min-width:32px;text-align:center}
.flow-fitall{position:absolute;top:8px;right:8px;z-index:10}
.flow-fitall button{background:rgba(10,10,15,0.8);color:#8888aa;border:1px solid #1a1a2e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px}
.flow-fitall button:hover{color:#00d4ff;border-color:#00d4ff40}
.flow-progress{position:absolute;bottom:0;left:0;right:0;height:10px;background:#0a0a0f;z-index:10;cursor:pointer}
.flow-progress-bar{height:100%;background:linear-gradient(90deg,#00d4ff,#ff00aa);width:0%;transition:width 0.1s;border-radius:0 2px 2px 0}
.flow-tooltip{position:absolute;display:none;background:rgba(10,10,15,0.95);border:1px solid #00d4ff40;border-radius:6px;padding:8px 12px;color:#ccc;font-size:11px;pointer-events:none;z-index:20;max-width:280px;backdrop-filter:blur(8px)}
.flow-toggle{display:none;width:100%;padding:8px;background:#12121f;color:#8888aa;border:none;border-bottom:1px solid #1a1a2e;cursor:pointer;font-size:12px}
.flow-toggle:hover{color:#00d4ff;background:#15152a}
.chat-toolbar { position:sticky; top:0; z-index:10; background:var(--bg); padding:10px 24px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:8px; }
.chat-toolbar .filter-group { display:flex; gap:0; }
.chat-toolbar .filter-btn { padding:5px 14px; font-size:12px; font-weight:600; border:1px solid var(--border); background:var(--bg2); color:var(--text2); cursor:pointer; transition:all 0.15s; }
.chat-toolbar .filter-btn:first-child { border-radius:6px 0 0 6px; }
.chat-toolbar .filter-btn:last-child { border-radius:0 6px 6px 0; }
.chat-toolbar .filter-btn:not(:first-child) { border-left:0; }
.chat-toolbar .filter-btn.active { background:var(--accent); color:white; border-color:var(--accent); }
.chat-toolbar .filter-btn.active + .filter-btn { border-left-color:var(--accent); }
.chat-toolbar .copy-btn { margin-left:auto; padding:5px 12px; font-size:12px; font-weight:600; border:1px solid var(--border); background:var(--bg2); color:var(--text2); cursor:pointer; border-radius:6px; transition:all 0.15s; display:flex; align-items:center; gap:4px; }
.chat-toolbar .copy-btn:hover { background:var(--bg3); color:var(--text); }
.chat-toolbar .copy-btn.copied { background:rgba(34,197,94,0.15); border-color:var(--green); color:var(--green); }
.chat-messages { padding:20px 24px; }
.msg { margin-bottom:16px; padding:12px 16px; border-radius:10px; }
.msg.user { background:rgba(34,197,94,0.06); border:1px solid rgba(34,197,94,0.25); border-left:4px solid var(--green); }
.msg.assistant { background:var(--bg3); border:1px solid var(--border); border-left:4px solid var(--purple); }
.msg-header { display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:12px; }
.msg-role { width:24px; height:24px; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700; flex-shrink:0; }
.msg-role.user { background:var(--green); color:white; }
.msg-role.assistant { background:var(--purple); color:white; }
.msg-time { color:var(--text2); }
.msg-model { margin-left:auto; }
.msg-tokens { color:var(--text2); font-size:11px; font-family:monospace; }
.msg-content { font-size:13px; line-height:1.6; white-space:pre-wrap; word-break:break-word; }
.msg-content code { background:var(--bg); padding:1px 4px; border-radius:3px; font-size:12px; }
.msg-content pre { background:var(--bg); border-radius:6px; padding:12px; margin:8px 0; overflow-x:auto; }
.msg-content pre code { background:transparent; padding:0; }
.msg-tools { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.tool-badge { background:var(--bg); padding:2px 8px; border-radius:4px; font-size:11px; color:var(--cyan); font-family:monospace; border:1px solid var(--border); max-width:350px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.msg-expand { color:var(--accent2); cursor:pointer; font-size:12px; margin-top:4px; }
.marker { padding:6px 16px; margin-bottom:8px; font-size:11px; border-radius:6px; display:flex; align-items:center; gap:8px; }
.marker.hook { background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); color:var(--amber); }
.marker.compaction { background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); color:var(--red); }
.marker.agent-dispatch { background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.3); color:var(--accent2); cursor:pointer; flex-wrap:wrap; }
.marker.agent-dispatch .agent-prompt { display:none; width:100%; margin-top:8px; padding:8px 12px; background:var(--bg); border-radius:6px; font-size:12px; line-height:1.5; white-space:pre-wrap; word-break:break-word; color:var(--text); max-height:400px; overflow-y:auto; }
.marker.agent-dispatch.expanded .agent-prompt { display:block; }
.agent-type-badge { display:inline-block; padding:1px 6px; border-radius:3px; font-size:10px; font-weight:600; background:rgba(99,102,241,0.25); color:var(--accent2); margin-left:6px; }
.sidebar { padding:20px; max-height:calc(100vh - 180px); overflow-y:auto; }
.sidebar-card { background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:12px; }
.sidebar-card h4 { font-size:13px; font-weight:600; margin-bottom:10px; color:var(--text2); text-transform:uppercase; letter-spacing:0.5px; }
.sidebar-row { display:flex; justify-content:space-between; padding:4px 0; font-size:13px; }
.sidebar-row .label { color:var(--text2); }
.sidebar-row .val { font-weight:600; font-variant-numeric:tabular-nums; }
.sidebar-tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; margin:2px; background:var(--bg3); }
.compaction-timeline { margin-top:8px; }
.compaction-event { padding:4px 8px; font-size:11px; color:var(--amber); border-left:2px solid var(--amber); margin-bottom:4px; }
@media (max-width:1000px) { .main-layout { grid-template-columns:1fr; } .stats-bar { grid-template-columns:repeat(3,1fr); } .flow-container{display:none} .flow-container.visible{display:block;height:50%} .flow-toggle{display:block} }
@media(min-width:1000px) and (max-width:1400px){.flow-container{height:35%}}
</style>
</head>
<body>
<div class="header">
  <div class="header-top">
    <a href="../index.html">&larr; Back to Dashboard</a>
    <h1 id="sessionTitle"></h1>
  </div>
  <div class="session-meta" id="sessionMeta"></div>
</div>
<div class="stats-bar" id="statsBar"></div>
<div class="main-layout">
  <div class="left-column">
    <div class="flow-container">
      <canvas id="flow-canvas"></canvas>
      <div class="flow-toolbar">
        <button id="flow-rewind" title="Restart">&#9198;</button>
        <button id="flow-play" class="active" title="Play/Pause">&#9654;</button>
        <button class="speed-btn active" data-speed="1">1x</button>
        <button class="speed-btn" data-speed="2">2x</button>
        <button class="speed-btn" data-speed="5">5x</button>
        <button class="speed-btn" data-speed="0" title="Skip to end">&#9199;</button>
        <button class="speed-btn" id="flow-showall" title="Show all nodes">&#9673;</button>
      </div>
      <div class="flow-fitall"><button id="flow-fullscreen" title="Fullscreen">&#x26F6;</button><button id="flow-fit" title="Fit all nodes">&#8982;</button></div>
      <div class="flow-progress"><div class="flow-progress-bar" id="flow-progress"></div></div>
      <div class="flow-tooltip" id="flow-tooltip"></div>
    </div>
    <button class="flow-toggle" id="flow-toggle">Show Flow</button>
    <div class="chat-panel">
      <div class="chat-toolbar">
        <div class="filter-group">
          <button class="filter-btn active" data-filter="all">All</button>
          <button class="filter-btn" data-filter="user">User</button>
          <button class="filter-btn" data-filter="assistant">Agent</button>
          <button class="filter-btn" data-filter="agent-dispatch">Subagents</button>
        </div>
        <button class="copy-btn" id="copyBtn">&#128203; Copy</button>
      </div>
      <div class="chat-messages" id="chatPanel"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar"></div>
</div>
<script>
const S = "__SESSION_DATA__";
const FLOW = "__FLOW_DATA__";
const sess = S.session;
const msgs = S.messages;
const fmt = n => n.toLocaleString();
const fmtUSD = n => '$' + n.toFixed(4);
const fmtTokens = n => { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); };
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function fmtTime(ts) { if(!ts) return ''; const d=new Date(typeof ts==='number'?ts:ts); return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function modelClass(m) { const l=(m||'').toLowerCase(); if(l.includes('opus')) return 'opus'; if(l.includes('sonnet')) return 'sonnet'; if(l.includes('haiku')) return 'haiku'; return ''; }

document.getElementById('sessionTitle').textContent = sess.project;
document.getElementById('sessionMeta').innerHTML =
  '<span>Session: <code>'+sess.session_id.slice(0,8)+'</code></span>' +
  '<span>'+new Date(sess.start).toLocaleDateString()+' '+new Date(sess.start).toLocaleTimeString()+'</span>' +
  '<span class="model-badge '+modelClass(sess.primary_model)+'">'+escHtml(sess.primary_model)+'</span>';

const toolCount = Object.values(sess.tools||{}).reduce((s,v)=>s+v,0);
document.getElementById('statsBar').innerHTML =
  '<div class="stat-card"><div class="label">Duration</div><div class="value">'+sess.duration_min+'m</div></div>' +
  '<div class="stat-card"><div class="label">Messages</div><div class="value" style="color:var(--green)">'+sess.messages+'</div></div>' +
  '<div class="stat-card"><div class="label">Tool Calls</div><div class="value" style="color:var(--cyan)">'+toolCount+'</div></div>' +
  '<div class="stat-card"><div class="label">Tokens</div><div class="value" style="color:var(--purple)">'+fmtTokens(sess.input_tokens+sess.output_tokens)+'</div></div>' +
  '<div class="stat-card"><div class="label">Est. Cost</div><div class="value" style="color:var(--orange)">'+fmtUSD(sess.cost)+'</div></div>' +
  '<div class="stat-card"><div class="label">Compactions</div><div class="value" style="color:'+((sess.compactions||0)>0?'var(--amber)':'var(--text2)')+'">'+((sess.compactions||0))+'</div></div>';

// Simple markdown rendering
function renderMd(text) {
  if (!text) return '';
  let h = escHtml(text);
  h = h.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, function(m,lang,code) { return '<pre><code class="language-'+lang+'">'+code+'</code></pre>'; });
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
  return h;
}

// Chat panel
const chatEl = document.getElementById('chatPanel');
let chatHtml = '';
msgs.forEach((m,i) => {
  if (m.role==='hook') {
    chatHtml += '<div class="marker hook" id="marker-'+i+'"><span>&#9881;</span> Hook: '+escHtml(m.hook_name)+' <span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='compaction') {
    chatHtml += '<div class="marker compaction" id="marker-'+i+'"><span>&#9889;</span> Context Compaction <span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else {
    // Check for Agent dispatches in tools
    const agentTools = (m.tools || []).filter(t => t.name === 'Agent');
    agentTools.forEach(at => {
      chatHtml += '<div class="marker agent-dispatch agent-toggle" id="marker-'+i+'-a">' +
        '<span>&#129302;</span> Agent: <strong>'+escHtml(at.detail || 'unnamed')+'</strong>' +
        '<span class="agent-type-badge">'+escHtml(at.agent_type || 'general-purpose')+'</span>' +
        '<span style="margin-left:auto;font-size:11px;opacity:0.7">'+fmtTime(m.timestamp)+' &#9660; click to expand</span>' +
        (at.agent_prompt ? '<div class="agent-prompt">'+escHtml(at.agent_prompt)+'</div>' : '') +
      '</div>';
    });

    const isLong = (m.content||'').length > 2000;
    const display = isLong ? m.content.slice(0,2000) : m.content;
    const hasAgentDispatch = agentTools.length > 0;
    chatHtml += '<div class="msg '+m.role+(hasAgentDispatch?' has-agent-dispatch':'')+'" id="msg-'+i+'">' +
      '<div class="msg-header">' +
        '<div class="msg-role '+m.role+'">'+(m.role==='user'?'U':'A')+'</div>' +
        '<span class="msg-time">'+fmtTime(m.timestamp)+'</span>' +
        (m.model ? '<span class="msg-model"><span class="model-badge '+modelClass(m.model)+'">'+escHtml(m.model)+'</span></span>' : '') +
        (m.tokens ? '<span class="msg-tokens">'+fmtTokens(m.tokens.input)+'in / '+fmtTokens(m.tokens.output)+'out</span>' : '') +
      '</div>' +
      '<div class="msg-content" id="mc'+i+'">'+renderMd(display)+'</div>' +
      (isLong ? '<div class="msg-expand" data-idx="'+i+'">Show full message ('+(m.content.length/1000).toFixed(1)+'K chars)</div>' : '') +
      (m.tools && m.tools.length>0 ? '<div class="msg-tools">'+m.tools.map(t =>
        '<span class="tool-badge"'+(t.name==='Agent'?' style="background:rgba(99,102,241,0.15);color:var(--accent2);border-color:var(--accent)"':'')+'>'
        +escHtml(t.name)+(t.detail ? ' '+escHtml(t.detail) : '')+'</span>'
      ).join('')+'</div>' : '') +
    '</div>';
  }
});
chatEl.innerHTML = chatHtml;

// Expand handlers
document.querySelectorAll('.msg-expand').forEach(el => {
  el.addEventListener('click', function() {
    const idx = parseInt(this.getAttribute('data-idx'));
    document.getElementById('mc'+idx).innerHTML = renderMd(msgs[idx].content);
    this.remove();
  });
});

// Agent dispatch toggle
document.querySelectorAll('.agent-toggle').forEach(el => {
  el.addEventListener('click', function() { this.classList.toggle('expanded'); });
});

// Syntax highlighting
document.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));

// Role filter
let activeFilter = 'all';
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    activeFilter = this.getAttribute('data-filter');
    document.querySelectorAll('#chatPanel > .msg, #chatPanel > .marker').forEach(el => {
      if (activeFilter === 'all') { el.style.display = ''; return; }
      if (activeFilter === 'agent-dispatch') {
        // Show agent-dispatch markers and messages with agent dispatches
        if (el.classList.contains('agent-dispatch')) { el.style.display = ''; return; }
        if (el.classList.contains('has-agent-dispatch')) { el.style.display = ''; return; }
        el.style.display = 'none'; return;
      }
      if (el.classList.contains('marker')) { el.style.display = 'none'; return; }
      el.style.display = el.classList.contains(activeFilter) ? '' : 'none';
    });
  });
});

// Copy to clipboard
document.getElementById('copyBtn').addEventListener('click', function() {
  const btn = this;
  const lines = [];
  document.querySelectorAll('#chatPanel > .msg, #chatPanel > .marker').forEach(el => {
    if (el.style.display === 'none') return;
    if (el.classList.contains('marker')) {
      lines.push('[' + el.textContent.trim() + ']');
    } else {
      const role = el.classList.contains('user') ? 'User' : 'Assistant';
      const content = el.querySelector('.msg-content');
      lines.push('--- ' + role + ' ---');
      lines.push(content ? content.textContent.trim() : '');
    }
    lines.push('');
  });
  navigator.clipboard.writeText(lines.join('\\n')).then(() => {
    btn.innerHTML = '&#10003; Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = '&#128203; Copy'; btn.classList.remove('copied'); }, 2000);
  });
});

// Sidebar
const sideEl = document.getElementById('sidebar');
let sideHtml = '';
sideHtml += '<div class="sidebar-card"><h4>Token Breakdown</h4>' +
  '<div class="sidebar-row"><span class="label">Input Tokens</span><span class="val">'+fmtTokens(sess.input_tokens)+'</span></div>' +
  '<div class="sidebar-row"><span class="label">Output Tokens</span><span class="val">'+fmtTokens(sess.output_tokens)+'</span></div>' +
  '<div class="sidebar-row"><span class="label">Cache Read</span><span class="val">'+fmtTokens(sess.cache_read_tokens)+'</span></div>' +
  '<div class="sidebar-row"><span class="label">Cache Write</span><span class="val">'+fmtTokens(sess.cache_write_tokens)+'</span></div>' +
  '</div>';
const tools = Object.entries(sess.tools||{}).sort((a,b)=>b[1]-a[1]);
if (tools.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Tools Used</h4>' +
    tools.slice(0,15).map(([n,c]) => '<div class="sidebar-row"><span class="label">'+escHtml(n)+'</span><span class="val">'+c+'x</span></div>').join('') +
    '</div>';
}
const skills = Object.entries(sess.skills||{}).sort((a,b)=>b[1]-a[1]);
if (skills.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Skills Used</h4>' +
    skills.map(([n,c]) => '<span class="sidebar-tag" style="color:var(--purple)">'+escHtml(n)+' '+c+'x</span>').join('') +
    '</div>';
}
const hooks = Object.entries(sess.hooks||{}).sort((a,b)=>b[1]-a[1]);
if (hooks.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Hooks Fired</h4>' +
    hooks.map(([n,c]) => '<div class="sidebar-row"><span class="label" style="color:var(--amber)">'+escHtml(n)+'</span><span class="val">'+c+'x</span></div>').join('') +
    '</div>';
}
if (sess.compaction_events && sess.compaction_events.length>0) {
  sideHtml += '<div class="sidebar-card" style="border-color:rgba(245,158,11,0.3)"><h4 style="color:var(--amber)">Compaction Timeline</h4>' +
    '<div class="compaction-timeline">' +
    sess.compaction_events.map(e => '<div class="compaction-event">'+fmtTime(e.timestamp)+'</div>').join('') +
    '</div></div>';
}
const models = Object.entries(sess.model_breakdown||{});
if (models.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Model Breakdown</h4>' +
    models.map(([m,d]) => '<div class="sidebar-row"><span class="label"><span class="model-badge '+modelClass(m)+'">'+escHtml(m)+'</span></span><span class="val">'+fmtUSD(d.cost)+' ('+d.calls+' calls)</span></div>').join('') +
    '</div>';
}
sideHtml += '<div class="sidebar-card"><h4>Metadata</h4>' +
  '<div class="sidebar-row"><span class="label">Session ID</span><span class="val" style="font-size:11px;font-family:monospace">'+sess.session_id.slice(0,12)+'...</span></div>' +
  '<div class="sidebar-row"><span class="label">File Size</span><span class="val">'+sess.file_size_mb+' MB</span></div>' +
  '</div>';
sideEl.innerHTML = sideHtml;

class SessionFlow {
  constructor(canvas, flowData, chatContainer) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.flow = flowData;
    this.chat = chatContainer;
    this.dpr = window.devicePixelRatio || 1;
    this.W = 0; this.H = 0;
    // Camera
    this.cam = {x:0, y:0, scale:1, tx:0, ty:0, ts:1, vx:0, vy:0};
    // Nodes and edges (populated later)
    this.nodes = []; this.edges = []; this.toolNodes = [];
    // Particles
    this.bgParticles = [];
    this.edgeParticles = [];
    // Effects queue
    this.effects = [];
    this.reverseBursts = [];
    // Interaction state
    this.hovered = null; this.selected = null;
    this.dragging = null; this.panning = false;
    this.panStart = {x:0,y:0}; this.panCamStart = {x:0,y:0};
    this.userOverride = false;
    // Auto-play state
    this.playing = true; this.playSpeed = 1;
    this.playTime = 0; this.playIndex = 0;
    this.playDone = false;
    this.showAll = false;
    this.convEdgeOpacity = 0;
    this.responseEdgeOpacity = 0;
    this._userMsgCount = 0;
    this._assistantMsgCount = 0;
    // Sprite cache
    this.sprites = {};
    // Hex grid params
    this.hexSize = 30;
    // Init
    this._resize();
    this._initBgParticles(60);
    this._preRenderSprites();
    this._initGraph();
    if (!this.flow.events || this.flow.events.length === 0) {
      this.allNodes.forEach(n => { n.opacity = 1; n.targetOpacity = 1; });
      this.playDone = true;
    }
    if (this.nodes.length > 0) {
      this.nodes[0].targetOpacity = 1;
      this._lastActiveNode = this.nodes[0];
      this.effects.push({type:"spawn", node:this.nodes[0], t:0, dur:1.0});
    }
    // Show user node immediately alongside main agent
    var userNode = this.allNodes.find(function(n) { return n.id === 'user'; });
    if (userNode) {
      userNode.targetOpacity = 1;
      this.effects.push({type:'spawn', node:userNode, t:0, dur:1.0});
    }
    this._fitAll();
    this._bindEvents();
    this._raf();
  }

  _resize() {
    var r = this.canvas.parentElement.getBoundingClientRect();
    if (Math.abs(r.width - this.W) < 1 && Math.abs(r.height - this.H) < 1) return;
    this.W = r.width; this.H = r.height;
    this.canvas.width = this.W * this.dpr;
    this.canvas.height = this.H * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  _initBgParticles(n) {
    this.bgParticles = [];
    for (let i = 0; i < n; i++) {
      this.bgParticles.push({
        x: Math.random() * 2000 - 1000,
        y: Math.random() * 2000 - 1000,
        r: Math.random() * 1.5 + 0.3,
        a: Math.random() * 0.3 + 0.05,
        vx: (Math.random() - 0.5) * 0.15,
        vy: (Math.random() - 0.5) * 0.15
      });
    }
  }

  _preRenderSprites() {
    const sz = 32;
    const colors = [
      ["glow", "0,212,255"],
      ["glowOrange", "255,136,0"],
      ["glowMagenta", "255,0,170"],
      ["glowGreen", "0,255,136"]
    ];
    for (const [name, rgb] of colors) {
      const c = document.createElement("canvas");
      c.width = sz; c.height = sz;
      const g = c.getContext("2d");
      const gr = g.createRadialGradient(sz/2,sz/2,0,sz/2,sz/2,sz/2);
      gr.addColorStop(0, "rgba(255,255,255,0.9)");
      gr.addColorStop(0.3, "rgba(" + rgb + ",0.4)");
      gr.addColorStop(1, "rgba(" + rgb + ",0)");
      g.fillStyle = gr; g.fillRect(0,0,sz,sz);
      this.sprites[name] = c;
    }
  }

  worldToScreen(wx, wy) {
    return {
      x: (wx - this.cam.x) * this.cam.scale + this.W / 2,
      y: (wy - this.cam.y) * this.cam.scale + this.H / 2
    };
  }
  screenToWorld(sx, sy) {
    return {
      x: (sx - this.W / 2) / this.cam.scale + this.cam.x,
      y: (sy - this.H / 2) / this.cam.scale + this.cam.y
    };
  }

  _hexPath(ctx, cx, cy, r) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 3 * i - Math.PI / 6;
      const px = cx + r * Math.cos(a), py = cy + r * Math.sin(a);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.closePath();
  }

  _diamondPath(ctx, cx, cy, r) {
    ctx.beginPath();
    ctx.moveTo(cx, cy - r);
    ctx.lineTo(cx + r * 0.7, cy);
    ctx.lineTo(cx, cy + r);
    ctx.lineTo(cx - r * 0.7, cy);
    ctx.closePath();
  }

  _drawHexGrid(ctx) {
    const s = this.hexSize;
    const w = s * Math.sqrt(3), h = s * 1.5;
    const tl = this.screenToWorld(0, 0);
    const br = this.screenToWorld(this.W, this.H);
    const startCol = Math.floor(tl.x / w) - 1;
    const endCol = Math.ceil(br.x / w) + 1;
    const startRow = Math.floor(tl.y / h) - 1;
    const endRow = Math.ceil(br.y / h) + 1;

    ctx.strokeStyle = "rgba(30,30,60,0.3)";
    ctx.lineWidth = 0.5;
    for (let row = startRow; row <= endRow; row++) {
      for (let col = startCol; col <= endCol; col++) {
        const ox = row % 2 === 0 ? 0 : w / 2;
        const cx = col * w + ox;
        const cy = row * h;
        const sc = this.worldToScreen(cx, cy);
        const sr = s * this.cam.scale;
        if (sr < 3) continue;
        this._hexPath(ctx, sc.x, sc.y, sr);
        ctx.stroke();
      }
    }
  }

  _drawBgParticles(ctx) {
    for (const p of this.bgParticles) {
      if (this.playing && !this.playDone) {
        p.x += p.vx; p.y += p.vy;
      }
      const sc = this.worldToScreen(p.x, p.y);
      ctx.globalAlpha = p.a;
      ctx.fillStyle = "#4444aa";
      ctx.beginPath();
      ctx.arc(sc.x, sc.y, p.r * this.cam.scale, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  _drawBackground(ctx) {
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(0, 0, this.W, this.H);
    this._drawHexGrid(ctx);
    this._drawBgParticles(ctx);
  }

  _initGraph() {
    const agents = this.flow.agents || [];
    const flowEdges = this.flow.edges || [];
    this.nodes = [];
    this.edges = [];
    this.toolNodes = [];
    const nodeMap = {};

    agents.forEach((a, i) => {
      var isMain = a.type === 'main';
      var isUser = a.type === 'user';
      const node = {
        id: a.id, name: a.name, type: isUser ? 'user' : (isMain ? 'main' : 'subagent'),
        parentId: a.parent_id, data: a,
        x: isUser ? -250 : (isMain ? 0 : 150 + (Math.random() - 0.5) * 100),
        y: isUser ? 0 : (isMain ? 0 : (Math.random() - 0.5) * 200),
        vx: 0, vy: 0,
        fx: isUser ? -250 : null,
        fy: isUser ? 0 : null,
        r: isUser ? 40 : (isMain ? 50 : 35),
        color: isUser ? '#00ff88' : (isMain ? '#00d4ff' : '#ff00aa'),
        opacity: 0, targetOpacity: 0,
        lastActiveTime: 0,
        scanPhase: Math.random() * Math.PI * 2,
        glowPulse: Math.random() * Math.PI * 2
      };
      this.nodes.push(node);
      nodeMap[a.id] = node;
    });

    agents.forEach(a => {
      const parent = nodeMap[a.id];
      if (!parent) return;
      const tools = a.tools_summary || {};
      Object.entries(tools).forEach(([name, count]) => {
        if (name === "Agent") return;
        const tn = {
          id: a.id + "-tool-" + name, name: name, type: "tool",
          parentId: a.id, count: count, displayCount: 0,
          x: parent.x + 80 + Math.random() * 80,
          y: parent.y + (Math.random() - 0.5) * 100,
          vx: 0, vy: 0, fx: null, fy: null,
          r: 20, color: "#ff8800",
          opacity: 0, targetOpacity: 0,
          lastActiveTime: 0,
          glowPulse: Math.random() * Math.PI * 2
        };
        this.toolNodes.push(tn);
        nodeMap[tn.id] = tn;
        this.edges.push({from: parent, to: tn, type: "tool", particles: []});
      });
    });

    flowEdges.forEach(e => {
      const from = nodeMap[e.from], to = nodeMap[e.to];
      if (from && to) {
        this.edges.push({from, to, type: e.type || "dispatch", particles: []});
      }
    });

    this.allNodes = [...this.nodes, ...this.toolNodes];
    var self = this;
    this.nodeMap = {};
    this.allNodes.forEach(function(n) { self.nodeMap[n.id] = n; });
  }

  _stepSimulation() {
    const nodes = this.allNodes.filter(n => n.opacity > 0.01);
    if (nodes.length === 0) return;
    const CHARGE = -800, LINK_DIST = 250, TOOL_DIST = 120;
    const CENTER = 0.03, DECAY = 0.4, COLLISION = 20;

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) d2 = 1;
        const f = CHARGE / d2;
        const fx = dx / Math.sqrt(d2) * f, fy = dy / Math.sqrt(d2) * f;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    for (const e of this.edges) {
      if (e.from.opacity < 0.01 || e.to.opacity < 0.01) continue;
      const dx = e.to.x - e.from.x, dy = e.to.y - e.from.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const target = e.type === "tool" ? TOOL_DIST : LINK_DIST;
      const f = (d - target) * 0.05;
      const fx = dx / d * f, fy = dy / d * f;
      e.from.vx += fx; e.from.vy += fy;
      e.to.vx -= fx; e.to.vy -= fy;
    }

    for (const n of nodes) {
      n.vx -= n.x * CENTER;
      n.vy -= n.y * CENTER;
    }

    // Push tools and sub-agents to the right of main agent
    for (var ni = 0; ni < nodes.length; ni++) {
      var node = nodes[ni];
      if (node.type === 'user' || node.type === 'main') continue;
      // Gentle rightward force
      node.vx += 0.3;
      // Also push away from user node (left side)
      var userNode = this.nodeMap ? this.nodeMap['user'] : null;
      if (userNode) {
        var udx = node.x - userNode.x;
        if (udx < 150) {
          node.vx += (150 - udx) * 0.01;
        }
      }
    }

    let totalV = 0;
    for (const n of nodes) {
      if (n.fx !== null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; continue; }
      n.vx *= DECAY; n.vy *= DECAY;
      n.x += n.vx; n.y += n.vy;
      totalV += Math.abs(n.vx) + Math.abs(n.vy);
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const minD = a.r + b.r + COLLISION;
        if (d < minD) {
          const push = (minD - d) / 2;
          const px = dx / d * push, py = dy / d * push;
          a.x -= px; a.y -= py;
          b.x += px; b.y += py;
        }
      }
    }

    this._simSettled = totalV < 0.5;
  }

  _drawNodes(ctx) {
    const t = performance.now() / 1000;

    for (const n of this.toolNodes) {
      if (n.opacity < 0.05) continue;
      const s = this.worldToScreen(n.x, n.y);
      const r = n.r * this.cam.scale;
      ctx.globalAlpha = n.opacity;

      ctx.save();
      ctx.shadowColor = n.color;
      ctx.shadowBlur = 15 * this.cam.scale;
      this._diamondPath(ctx, s.x, s.y, r);
      ctx.fillStyle = "rgba(255,136,0,0.15)";
      ctx.fill();
      ctx.restore();

      this._diamondPath(ctx, s.x, s.y, r);
      ctx.strokeStyle = n.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      if (r > 8) {
        ctx.fillStyle = "#fff";
        ctx.font = Math.max(9, r * 0.5) + "px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        var showCount = this.playDone || this.showAll ? n.count : (n.displayCount || 0);
        const label = showCount > 1 ? n.name + " x" + showCount : n.name;
        ctx.fillText(label, s.x, s.y + r + 12);
      }
    }

    for (const n of this.nodes) {
      if (n.opacity < 0.05) continue;
      const s = this.worldToScreen(n.x, n.y);
      const r = n.r * this.cam.scale;
      ctx.globalAlpha = n.opacity;

      // Draw shape based on type
      if (n.type === 'user') {
        // Outer glow
        ctx.save();
        ctx.shadowColor = n.color;
        ctx.shadowBlur = 25 * this.cam.scale;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 1.05, 0, Math.PI * 2);
        ctx.fillStyle = n.color + '10';
        ctx.fill(); ctx.fill();
        ctx.restore();
        // Circle fill
        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.fillStyle = '#0d0d1a';
        ctx.fill();
        // Circle border
        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.strokeStyle = n.color + '80';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // Pulsing ring
        var pulse = 0.6 + Math.sin(t * 1.5 + n.glowPulse) * 0.4;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 0.85, 0, Math.PI * 2);
        var pulseHex = Math.round(pulse * 40).toString(16).padStart(2,'0');
        ctx.strokeStyle = n.color + pulseHex;
        ctx.lineWidth = 1;
        ctx.stroke();
        // User icon
        ctx.fillStyle = '#fff';
        ctx.font = 'bold ' + Math.max(16, r * 0.5) + 'px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('\u263A', s.x, s.y);
        // Label
        ctx.font = Math.max(9, r * 0.25) + 'px monospace';
        ctx.fillStyle = n.color;
        ctx.fillText('User', s.x, s.y + r + 14);
        // Selection highlight
        if (this.selected === n || this.hovered === n) {
          ctx.beginPath();
          ctx.arc(s.x, s.y, r + 4, 0, Math.PI * 2);
          ctx.strokeStyle = '#ffffff60';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      } else {
        ctx.save();
        ctx.shadowColor = n.color;
        ctx.shadowBlur = 25 * this.cam.scale;
        this._hexPath(ctx, s.x, s.y, r * 1.05);
        ctx.fillStyle = n.color + "10";
        ctx.fill(); ctx.fill();
        ctx.restore();

        this._hexPath(ctx, s.x, s.y, r);
        ctx.fillStyle = "#0d0d1a";
        ctx.fill();

        ctx.save();
        this._hexPath(ctx, s.x, s.y, r);
        ctx.clip();
        const scanY = s.y - r + ((t * 40 + n.scanPhase * 50) % (r * 2));
        const scanGrad = ctx.createLinearGradient(s.x, scanY - 20, s.x, scanY + 20);
        scanGrad.addColorStop(0, "transparent");
        scanGrad.addColorStop(0.5, n.color + "15");
        scanGrad.addColorStop(1, "transparent");
        ctx.fillStyle = scanGrad;
        ctx.fillRect(s.x - r, s.y - r, r * 2, r * 2);
        ctx.restore();

        this._hexPath(ctx, s.x, s.y, r);
        ctx.strokeStyle = n.color + "80";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        const pulse = 0.6 + Math.sin(t * 1.5 + n.glowPulse) * 0.4;
        this._hexPath(ctx, s.x, s.y, r * 0.85);
        const pulseHex = Math.round(pulse * 40).toString(16).padStart(2,"0");
        ctx.strokeStyle = n.color + pulseHex;
        ctx.lineWidth = 1;
        ctx.stroke();

        if (r > 15) {
          ctx.fillStyle = "#fff";
          ctx.font = "bold " + Math.max(10, r * 0.28) + "px monospace";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          const icon = n.type === "main" ? "✦" : n.data.type.charAt(0).toUpperCase();
          ctx.fillText(icon, s.x, s.y - 2);
          ctx.font = Math.max(9, r * 0.22) + "px monospace";
          ctx.fillStyle = n.color;
          // Two-line name label
          var fullName = n.name || '';
          if (fullName.length <= 20) {
            ctx.fillText(fullName, s.x, s.y + r + 14);
          } else {
            // Split into two lines at a word boundary near the middle
            var mid = Math.floor(fullName.length / 2);
            var spaceAfter = fullName.indexOf(' ', mid);
            var spaceBefore = fullName.lastIndexOf(' ', mid);
            var splitAt;
            if (spaceAfter !== -1 && spaceAfter < mid + 10) {
              splitAt = spaceAfter;
            } else if (spaceBefore > 0) {
              splitAt = spaceBefore;
            } else {
              splitAt = 20; // No good space found, just cut
            }
            var line1 = fullName.slice(0, splitAt);
            var line2 = fullName.slice(splitAt).trim();
            if (line2.length > 22) line2 = line2.slice(0, 20) + '..';
            ctx.fillText(line1, s.x, s.y + r + 12);
            ctx.fillText(line2, s.x, s.y + r + 24);
          }
        }

        if (this.selected === n || this.hovered === n) {
          this._hexPath(ctx, s.x, s.y, r + 4);
          ctx.strokeStyle = "#ffffff60";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  _cubicBezier(t, p0, p1, p2, p3) {
    const mt = 1 - t;
    return {
      x: mt*mt*mt*p0.x + 3*mt*mt*t*p1.x + 3*mt*t*t*p2.x + t*t*t*p3.x,
      y: mt*mt*mt*p0.y + 3*mt*mt*t*p1.y + 3*mt*t*t*p2.y + t*t*t*p3.y
    };
  }

  _initEdgeParticles(edge) {
    const n = edge.type === "dispatch" ? 6 : 3;
    edge.particles = [];
    for (let i = 0; i < n; i++) {
      edge.particles.push({
        t: i / n,
        speed: 0.003 + Math.random() * 0.002,
        wobble: Math.random() * Math.PI * 2,
        wobbleAmp: 2 + Math.random() * 3
      });
    }
  }

  _drawEdges(ctx) {
    for (const e of this.edges) {
      const fa = e.from, ta = e.to;
      if (fa.opacity < 0.05 || ta.opacity < 0.05) continue;

      const sf = this.worldToScreen(fa.x, fa.y);
      const st = this.worldToScreen(ta.x, ta.y);
      const alpha = Math.min(fa.opacity, ta.opacity);

      const dx = st.x - sf.x, dy = st.y - sf.y;
      const d = Math.sqrt(dx*dx + dy*dy) || 1;
      const nx = -dy/d, ny = dx/d;
      const off = d * 0.15;
      const cp1 = {x: sf.x + dx*0.3 + nx*off, y: sf.y + dy*0.3 + ny*off};
      const cp2 = {x: sf.x + dx*0.7 + nx*off, y: sf.y + dy*0.7 + ny*off};

      var edgeColor = e.type === "dispatch" ? "#00d4ff" : (e.type === "conversation" ? "#00ff88" : "#ff8800");
      var edgeAlpha = e.type === 'conversation' ? alpha * this.convEdgeOpacity : alpha;
      ctx.globalAlpha = edgeAlpha * 0.3;
      ctx.beginPath();
      ctx.moveTo(sf.x, sf.y);
      ctx.bezierCurveTo(cp1.x, cp1.y, cp2.x, cp2.y, st.x, st.y);
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = e.type === "dispatch" ? 2 : 1.5;
      ctx.stroke();

      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = edgeAlpha * 0.15;
      ctx.beginPath();
      ctx.moveTo(sf.x, sf.y);
      ctx.bezierCurveTo(cp1.x, cp1.y, cp2.x, cp2.y, st.x, st.y);
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = 4;
      ctx.stroke();
      ctx.restore();

      // Draw response edge (Claude → User) if active
      if (e.type === 'conversation' && this.responseEdgeOpacity > 0.01) {
        // Reverse direction: from target (main agent) to source (user), curving the opposite way
        var rcp1 = {x: sf.x + dx*0.3 - nx*off, y: sf.y + dy*0.3 - ny*off};
        var rcp2 = {x: sf.x + dx*0.7 - nx*off, y: sf.y + dy*0.7 - ny*off};
        ctx.globalAlpha = alpha * this.responseEdgeOpacity * 0.3;
        ctx.beginPath();
        ctx.moveTo(st.x, st.y);
        ctx.bezierCurveTo(rcp2.x, rcp2.y, rcp1.x, rcp1.y, sf.x, sf.y);
        ctx.strokeStyle = '#00d4ff';
        ctx.lineWidth = 2;
        ctx.stroke();
        // Glow
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.globalAlpha = alpha * this.responseEdgeOpacity * 0.15;
        ctx.beginPath();
        ctx.moveTo(st.x, st.y);
        ctx.bezierCurveTo(rcp2.x, rcp2.y, rcp1.x, rcp1.y, sf.x, sf.y);
        ctx.strokeStyle = '#00d4ff';
        ctx.lineWidth = 4;
        ctx.stroke();
        ctx.restore();
      }

      // Message counters drawn in _drawMessageCounters() after nodes

      // Only draw permanent particles for dispatch/tool edges, not conversation
      if (e.type !== 'conversation') {
        if (e.particles.length === 0) this._initEdgeParticles(e);
        const sprite = e.type === "dispatch" ? this.sprites.glow : this.sprites.glowOrange;
        ctx.globalAlpha = alpha;
        for (const p of e.particles) {
          var isHovered = this.hovered === fa || this.hovered === ta;
          var isFaded = fa.opacity < 0.5 || ta.opacity < 0.5;
          var particleSpeed = this.playing && !this.playDone && !isFaded ? p.speed : (isHovered ? p.speed * 1.5 : 0);
          p.t += particleSpeed;
          if (p.t > 1) p.t -= 1;
          p.wobble += 0.03;

          const pos = this._cubicBezier(p.t, sf, cp1, cp2, st);
          const tan = this._cubicBezier(Math.min(1, p.t + 0.01), sf, cp1, cp2, st);
          const tdx = tan.x - pos.x, tdy = tan.y - pos.y;
          const tl = Math.sqrt(tdx*tdx + tdy*tdy) || 1;
          const wobX = -tdy/tl * Math.sin(p.wobble) * p.wobbleAmp;
          const wobY = tdx/tl * Math.sin(p.wobble) * p.wobbleAmp;

          const sz = 10 * this.cam.scale;
          ctx.drawImage(sprite, pos.x + wobX - sz/2, pos.y + wobY - sz/2, sz, sz);

          for (let ti = 1; ti <= 3; ti++) {
            const tt = p.t - ti * 0.015;
            if (tt < 0) continue;
            const tp = this._cubicBezier(tt, sf, cp1, cp2, st);
            ctx.globalAlpha = alpha * (1 - ti * 0.3);
            ctx.drawImage(sprite, tp.x - sz*0.3, tp.y - sz*0.3, sz*0.6, sz*0.6);
          }
          ctx.globalAlpha = alpha;
        }
      }
    }
    ctx.globalAlpha = 1;

    // Draw particle bursts (user→agent and agent→user)
    var burstsToRemove = [];
    for (var bi = 0; bi < this.reverseBursts.length; bi++) {
      var burst = this.reverseBursts[bi];
      var bFrom = burst.from, bTo = burst.to;
      if (!bFrom || !bTo || bFrom.opacity < 0.05) { burstsToRemove.push(bi); continue; }

      if (this.playing && !this.playDone) {
        burst.t += burst.speed;
      }

      if (burst.t >= 1) {
        this.effects.push({type:'pulse', node:bTo, t:0, dur:0.8, color:burst.color});
        burstsToRemove.push(bi);
        continue;
      }

      // Draw particles traveling from burst.from to burst.to
      var sf = this.worldToScreen(bFrom.x, bFrom.y);
      var st = this.worldToScreen(bTo.x, bTo.y);
      var dx = st.x - sf.x, dy = st.y - sf.y;
      var d = Math.sqrt(dx*dx + dy*dy) || 1;
      var nx = -dy/d, ny = dx/d;
      var off = d * 0.15;
      var cp1 = {x: sf.x + dx*0.3 + nx*off, y: sf.y + dy*0.3 + ny*off};
      var cp2 = {x: sf.x + dx*0.7 + nx*off, y: sf.y + dy*0.7 + ny*off};

      var sprite = burst.color === '#00ff88' ? this.sprites.glowGreen : this.sprites.glow;
      ctx.globalAlpha = 0.9;
      for (var pi = 0; pi < burst.particles; pi++) {
        var pt = burst.t - pi * 0.04;
        if (pt < 0 || pt > 1) continue;
        var pos = this._cubicBezier(pt, sf, cp1, cp2, st);
        var sz = 12 * this.cam.scale;
        ctx.drawImage(sprite, pos.x - sz/2, pos.y - sz/2, sz, sz);
        for (var ti = 1; ti <= 3; ti++) {
          var tt = pt - ti * 0.02;
          if (tt < 0) continue;
          var tp = this._cubicBezier(tt, sf, cp1, cp2, st);
          ctx.globalAlpha = 0.9 * (1 - ti * 0.3);
          ctx.drawImage(sprite, tp.x - sz*0.3, tp.y - sz*0.3, sz*0.6, sz*0.6);
        }
        ctx.globalAlpha = 0.9;
      }
    }
    ctx.globalAlpha = 1;
    for (var ri = burstsToRemove.length - 1; ri >= 0; ri--) {
      this.reverseBursts.splice(burstsToRemove[ri], 1);
    }
  }

  _fitAll() {
    const visible = this.allNodes.filter(n => n.opacity > 0.1);
    if (visible.length === 0) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of visible) {
      minX = Math.min(minX, n.x - n.r);
      maxX = Math.max(maxX, n.x + n.r);
      minY = Math.min(minY, n.y - n.r);
      maxY = Math.max(maxY, n.y + n.r);
    }
    const pad = 80;
    const cw = maxX - minX + pad * 2, ch = maxY - minY + pad * 2;
    this.cam.tx = (minX + maxX) / 2;
    this.cam.ty = (minY + maxY) / 2;
    this.cam.ts = Math.min(this.W / cw, this.H / ch, 2.0);
    this.userOverride = false;
  }

  _raf() {
    const now = performance.now();
    const dt = this._lastFrame ? (now - this._lastFrame) / 1000 : 0.016;
    this._lastFrame = now;
    this._resize();
    this.cam.x += (this.cam.tx - this.cam.x) * 0.08;
    this.cam.y += (this.cam.ty - this.cam.y) * 0.08;
    this.cam.scale += (this.cam.ts - this.cam.scale) * 0.08;
    this.ctx.clearRect(0, 0, this.W, this.H);
    this._drawBackground(this.ctx);
    if (!this._simSettled) this._stepSimulation();
    for (const n of this.allNodes) {
      n.opacity += (n.targetOpacity - n.opacity) * 0.08;
    }
    if (!this.showAll && this.convEdgeOpacity > 0.01) {
      this.convEdgeOpacity *= 0.97; // slow fade
    } else if (!this.showAll) {
      this.convEdgeOpacity = 0;
    }
    if (!this.showAll && this.responseEdgeOpacity > 0.01) {
      this.responseEdgeOpacity *= 0.97;
    } else if (!this.showAll) {
      this.responseEdgeOpacity = 0;
    }
    this._stepPlayback(dt);
    this._drawEdges(this.ctx);
    this._drawNodes(this.ctx);
    this._drawMessageCounters(this.ctx);
    this._drawEffects(this.ctx, dt);
    requestAnimationFrame(() => this._raf());
  }

  _hitTest(sx, sy) {
    const w = this.screenToWorld(sx, sy);
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const n = this.nodes[i];
      if (n.opacity < 0.1) continue;
      const dx = w.x - n.x, dy = w.y - n.y;
      if (dx*dx + dy*dy < n.r*n.r) return n;
    }
    for (let i = this.toolNodes.length - 1; i >= 0; i--) {
      const n = this.toolNodes[i];
      if (n.opacity < 0.1) continue;
      const dx = w.x - n.x, dy = w.y - n.y;
      if (dx*dx + dy*dy < n.r*n.r) return n;
    }
    return null;
  }

  _updateTooltip(mx, my, node) {
    const el = document.getElementById("flow-tooltip");
    if (!el) return;
    if (!node) { el.style.display = "none"; return; }
    el.textContent = "";
    const h = document.createElement("h4");
    h.style.cssText = "color:#00d4ff;margin:0 0 4px;font-size:12px";
    h.textContent = node.name;
    el.appendChild(h);
    const addRow = (label, val) => {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;justify-content:space-between;gap:12px";
      const lbl = document.createElement("span");
      lbl.style.color = "#666"; lbl.textContent = label;
      const v = document.createElement("span");
      v.style.color = "#fff"; v.textContent = val;
      row.appendChild(lbl); row.appendChild(v);
      el.appendChild(row);
    };
    if (node.type === "tool") {
      addRow("Calls", String(node.count));
    } else {
      const d = node.data || {};
      addRow("Type", d.type || "main");
      if (d.tokens) addRow("Tokens", ((d.tokens.input+d.tokens.output)/1000).toFixed(1) + "K");
      if (d.cost != null) addRow("Cost", "$" + d.cost.toFixed(4));
    }
    el.style.display = "block";
    el.style.left = (mx + 15) + "px";
    el.style.top = (my + 15) + "px";
  }

  _hideTooltip() {
    const el = document.getElementById("flow-tooltip");
    if (el) el.style.display = "none";
  }

  _scrollToMessage(node) {
    var evt;
    if (node.type === "tool") {
      evt = this.flow.events.find(e => e.type === "tool_call" && e.tool === node.name && e.agent_id === node.parentId);
    }
    if (!evt) {
      evt = this.flow.events.find(e => e.agent_id === node.id);
    }
    if (!evt) return;
    const msgEl = document.getElementById("msg-" + evt.msg_index) || document.getElementById("marker-" + evt.msg_index);
    if (msgEl) {
      msgEl.scrollIntoView({behavior: "smooth", block: "center"});
      msgEl.style.outline = "2px solid #00d4ff";
      setTimeout(() => { msgEl.style.outline = ""; }, 2000);
    }
  }

  _compressTime(t, events) {
    if (!events || events.length === 0) return 0;
    var compressed = 0, prevT = 0;
    for (var i = 0; i < events.length; i++) {
      if (events[i].t > t) break;
      compressed += Math.max(300, Math.min(2000, events[i].t - prevT));
      prevT = events[i].t;
    }
    compressed += Math.max(0, Math.min(2000, t - prevT));
    return compressed;
  }

  _processEvent(evt) {
    var nodeMap = this.nodeMap;
    var agent, toolNode, toolId;
    switch (evt.type) {
      case "message":
        agent = nodeMap[evt.agent_id];
        var userNode = nodeMap['user'];
        if (agent) {
          agent.targetOpacity = 1;
          agent.lastActiveTime = this.playTime;
          this._lastActiveNode = agent;
          if (evt.role === "user") {
            this._userMsgCount++;
            // Burst from user to main agent
            if (userNode && agent) {
              userNode.lastActiveTime = this.playTime;
              userNode.targetOpacity = 1;
              this.reverseBursts.push({
                from: userNode,
                to: agent,
                t: 0,
                speed: 0.03,
                color: '#00ff88',
                particles: 3
              });
              this.convEdgeOpacity = 1;
              agent.glowPulse = 0;
            }
          } else if (evt.role === "assistant") {
            this._assistantMsgCount++;
            // Reverse burst from main agent back to user (response)
            if (userNode) {
              userNode.targetOpacity = 1;
              this.reverseBursts.push({
                from: agent,
                to: userNode,
                t: 0,
                speed: 0.02,
                color: '#00d4ff',
                particles: 3
              });
              this.responseEdgeOpacity = 1;
              userNode.glowPulse = 0;
            }
          }
        }
        break;
      case "tool_call":
        toolId = evt.agent_id + "-tool-" + evt.tool;
        toolNode = nodeMap[toolId];
        if (toolNode) {
          toolNode.targetOpacity = 1;
          toolNode.displayCount = (toolNode.displayCount || 0) + 1;
          toolNode.lastActiveTime = this.playTime;
          this.effects.push({type:"spawn", node:toolNode, t:0, dur:0.6});
        }
        agent = nodeMap[evt.agent_id];
        if (agent) { agent.targetOpacity = 1; agent.lastActiveTime = this.playTime; this._lastActiveNode = agent; }
        break;
      case "agent_spawn":
        var newAgent = nodeMap[evt.agent_id];
        if (newAgent) {
          newAgent.targetOpacity = 1;
          newAgent.lastActiveTime = this.playTime;
          this.effects.push({type:"spawn", node:newAgent, t:0, dur:1.0});
          this._lastActiveNode = newAgent;
          this._simSettled = false;
        }
        break;
      case "compaction":
        agent = nodeMap[evt.agent_id];
        if (agent) this.effects.push({type:"flash", node:agent, t:0, dur:0.5, color:"#ff3344"});
        break;
      case "hook":
        agent = nodeMap[evt.agent_id];
        if (agent) this.effects.push({type:"flash", node:agent, t:0, dur:0.4, color:"#ffcc00"});
        break;
    }
    // Auto-scroll chat during playback
    if (evt.msg_index != null && this.playing) {
      var msgEl = document.getElementById('msg-' + evt.msg_index) || document.getElementById('marker-' + evt.msg_index);
      if (msgEl) {
        msgEl.scrollIntoView({behavior: 'smooth', block: 'nearest'});
      }
    }
  }

  _stepPlayback(dt) {
    if (!this.playing || this.playDone) return;
    var events = this.flow.events || [];
    if (events.length === 0) { this.playDone = true; return; }
    var maxT = events[events.length - 1].t;
    this.playTime += dt * 1000 * this.playSpeed;
    while (this.playIndex < events.length) {
      var playT = this._compressTime(events[this.playIndex].t, events);
      if (playT > this.playTime) break;
      this._processEvent(events[this.playIndex]);
      this.playIndex++;
    }
    // Fade out nodes unused for more than 8 seconds (compressed time)
    if (!this.showAll) {
      var fadeThreshold = 8000;
      for (var ni = 0; ni < this.allNodes.length; ni++) {
        var node = this.allNodes[ni];
        if (node.type === 'main' || node.type === 'user') continue; // Never fade main/user
        if (node.targetOpacity > 0 && this.playTime - node.lastActiveTime > fadeThreshold) {
          node.targetOpacity = 0.15; // Dim but not invisible
        }
      }
    }
    var prog = document.getElementById("flow-progress");
    if (prog) {
      var maxCompressed = this._compressTime(maxT, events);
      prog.style.width = Math.min(100, (this.playTime / maxCompressed) * 100) + "%";
    }
    if (this.playIndex >= events.length) {
      this.playDone = true;
      this.allNodes.forEach(function(n) { n.targetOpacity = 1; });
    }
    if (!this.userOverride && this._lastActiveNode) {
      this.cam.tx = this._lastActiveNode.x;
      this.cam.ty = this._lastActiveNode.y;
    }
  }

  _skipToEnd() {
    this.showAll = true;
    this.allNodes.forEach(function(n) { n.opacity = 1; n.targetOpacity = 1; });
    this.toolNodes.forEach(function(n) { n.displayCount = n.count; });
    this.playDone = true;
    this.playIndex = (this.flow.events || []).length;
    this.convEdgeOpacity = 0.3;
    this.responseEdgeOpacity = 0.3;
    this._userMsgCount = 0;
    this._assistantMsgCount = 0;
    var evts = this.flow.events || [];
    for (var ei = 0; ei < evts.length; ei++) {
      if (evts[ei].type === 'message' && evts[ei].role === 'user') this._userMsgCount++;
      if (evts[ei].type === 'message' && evts[ei].role === 'assistant') this._assistantMsgCount++;
    }
    var prog = document.getElementById("flow-progress");
    if (prog) prog.style.width = "100%";
    this._fitAll();
  }

  _drawMessageCounters(ctx) {
    // Draw message counters anchored to node edges, rendered above nodes
    var userNode = this.nodeMap ? this.nodeMap['user'] : null;
    var mainNode = this.nodeMap ? this.nodeMap['main'] : null;
    if (!userNode || !mainNode || userNode.opacity < 0.05 || mainNode.opacity < 0.05) return;

    ctx.font = '10px monospace';
    ctx.textBaseline = 'middle';

    // User message count - anchored to right edge of User node
    if (this._userMsgCount > 0) {
      var us = this.worldToScreen(userNode.x, userNode.y);
      var ur = userNode.r * this.cam.scale;
      var umAlpha = this.convEdgeOpacity > 0.1 ? 0.8 : 0.35;
      ctx.globalAlpha = userNode.opacity * umAlpha;
      ctx.fillStyle = '#00ff88';
      ctx.textAlign = 'left';
      ctx.fillText(this._userMsgCount + '', us.x + ur + 8, us.y - ur * 0.5);
    }

    // Assistant message count - anchored to left edge of Claude node
    if (this._assistantMsgCount > 0) {
      var ms = this.worldToScreen(mainNode.x, mainNode.y);
      var mr = mainNode.r * this.cam.scale;
      var amAlpha = this.responseEdgeOpacity > 0.1 ? 0.8 : 0.35;
      ctx.globalAlpha = mainNode.opacity * amAlpha;
      ctx.fillStyle = '#00d4ff';
      ctx.textAlign = 'right';
      ctx.fillText(this._assistantMsgCount + '', ms.x - mr - 6, ms.y + mr * 0.5);
    }

    ctx.globalAlpha = 1;
  }

  _drawEffects(ctx, dt) {
    var toRemove = [];
    for (var i = 0; i < this.effects.length; i++) {
      var fx = this.effects[i];
      if (this.playing || this.playDone) fx.t += dt;
      var progress = fx.t / fx.dur;
      if (progress > 1) { toRemove.push(i); continue; }
      var n = fx.node;
      if (!n || n.opacity < 0.01) continue;
      var s = this.worldToScreen(n.x, n.y);
      var r = n.r * this.cam.scale;
      var color = fx.color || n.color;
      if (fx.type === "spawn") {
        var ringR = r * (1 + progress * 1.5);
        ctx.globalAlpha = (1 - progress) * 0.6;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(s.x, s.y, ringR, 0, Math.PI * 2);
        ctx.stroke();
        if (progress < 0.3) {
          ctx.globalAlpha = (1 - progress / 0.3) * 0.4;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(s.x, s.y, r * 1.2, 0, Math.PI * 2);
          ctx.fill();
        }
      } else if (fx.type === "pulse") {
        var pulseR = r + Math.sin(progress * Math.PI) * 15;
        ctx.globalAlpha = (1 - progress) * 0.5;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        this._hexPath(ctx, s.x, s.y, pulseR);
        ctx.stroke();
      } else if (fx.type === "flash") {
        ctx.globalAlpha = (1 - progress) * 0.7;
        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = 20;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 0.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }
    ctx.globalAlpha = 1;
    for (var j = toRemove.length - 1; j >= 0; j--) {
      this.effects.splice(toRemove[j], 1);
    }
  }

  _bindEvents() {
    const c = this.canvas;
    window.addEventListener("resize", () => this._resize());

    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.92 : 1.08;
      const newScale = Math.max(0.3, Math.min(3.0, this.cam.scale * factor));
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const before = this.screenToWorld(mx, my);
      this.cam.scale = newScale;
      const after = this.screenToWorld(mx, my);
      this.cam.x -= (after.x - before.x);
      this.cam.y -= (after.y - before.y);
      this.cam.tx = this.cam.x; this.cam.ty = this.cam.y;
      this.cam.ts = this.cam.scale;
      this.userOverride = true;
    }, {passive: false});

    this._dragDist = 0;
    this._mouseDownPos = {x:0, y:0};

    c.addEventListener("mousedown", (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      this._mouseDownPos = {x: mx, y: my};
      this._dragDist = 0;
      const hit = this._hitTest(mx, my);
      if (hit) {
        this.dragging = hit;
        hit.fx = hit.x; hit.fy = hit.y;
        this._simSettled = false;
      } else {
        this.panning = true;
        this.panStart = {x: mx, y: my};
        this.panCamStart = {x: this.cam.x, y: this.cam.y};
      }
    });

    c.addEventListener("mousemove", (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const ddx = mx - this._mouseDownPos.x, ddy = my - this._mouseDownPos.y;
      this._dragDist = Math.sqrt(ddx*ddx + ddy*ddy);
      if (this.dragging) {
        const w = this.screenToWorld(mx, my);
        this.dragging.fx = w.x; this.dragging.fy = w.y;
        this.dragging.x = w.x; this.dragging.y = w.y;
        this._simSettled = false;
      } else if (this.panning) {
        const dx = (mx - this.panStart.x) / this.cam.scale;
        const dy = (my - this.panStart.y) / this.cam.scale;
        this.cam.x = this.panCamStart.x - dx;
        this.cam.y = this.panCamStart.y - dy;
        this.cam.tx = this.cam.x; this.cam.ty = this.cam.y;
        this.cam.vx = -dx * 0.1; this.cam.vy = -dy * 0.1;
        this.userOverride = true;
      } else {
        const hit = this._hitTest(mx, my);
        this.hovered = hit;
        c.style.cursor = hit ? "pointer" : "grab";
        this._updateTooltip(mx, my, hit);
      }
    });

    c.addEventListener("mouseup", () => {
      if (this.dragging) {
        this.dragging.fx = null; this.dragging.fy = null;
        this._simSettled = false;
        this.dragging = null;
      }
      if (this.panning) {
        this.cam.tx = this.cam.x + this.cam.vx * 5;
        this.cam.ty = this.cam.y + this.cam.vy * 5;
      }
      this.panning = false;
    });

    c.addEventListener("mouseleave", () => {
      this.hovered = null;
      this._hideTooltip();
    });

    c.addEventListener("click", (e) => {
      if (this._dragDist > 5) return;
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const hit = this._hitTest(mx, my);
      this.selected = hit;
      if (hit) this._scrollToMessage(hit);
    });

    const fitBtn = document.getElementById("flow-fit");
    if (fitBtn) fitBtn.addEventListener("click", () => this._fitAll());

    var self = this;
    var fsBtn = document.getElementById('flow-fullscreen');
    if (fsBtn) fsBtn.addEventListener('click', function() {
      var fc = document.querySelector('.flow-container');
      if (!fc) return;
      var isFs = fc.classList.toggle('fullscreen');
      fsBtn.textContent = isFs ? '\u2716' : '\u26F6';
      fsBtn.title = isFs ? 'Exit fullscreen' : 'Fullscreen';
      self._resize();
      self._fitAll();
    });

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        var fc = document.querySelector('.flow-container');
        if (fc && fc.classList.contains('fullscreen')) {
          fc.classList.remove('fullscreen');
          if (fsBtn) { fsBtn.textContent = '\u26F6'; fsBtn.title = 'Fullscreen'; }
          self._resize();
          self._fitAll();
        }
      }
    });
    var playBtn = document.getElementById("flow-play");
    if (playBtn) playBtn.addEventListener("click", function() {
      self.playing = !self.playing;
      playBtn.textContent = self.playing ? "\u25B6" : "\u23F8";
    });

    var showAllBtn = document.getElementById("flow-showall");
    if (showAllBtn) showAllBtn.addEventListener("click", function() {
      self.showAll = !self.showAll;
      showAllBtn.classList.toggle("active", self.showAll);
      if (self.showAll) {
        self.allNodes.forEach(function(n) { n.targetOpacity = 1; });
      }
    });

    var rewindBtn = document.getElementById("flow-rewind");
    if (rewindBtn) rewindBtn.addEventListener("click", function() {
      self.playTime = 0;
      self.playIndex = 0;
      self.playDone = false;
      self.showAll = false;
      self.effects = [];
      self.reverseBursts = [];
      self._userMsgCount = 0;
      self._assistantMsgCount = 0;
      self.allNodes.forEach(function(n) { n.opacity = 0; n.targetOpacity = 0; });
      self.toolNodes.forEach(function(n) { n.displayCount = 0; });
      // Show user and main agent immediately
      if (self.nodes.length > 0) {
        self.nodes[0].targetOpacity = 1;
        self.effects.push({type:"spawn", node:self.nodes[0], t:0, dur:1.0});
      }
      var userNode = self.allNodes.find(function(n) { return n.id === "user"; });
      if (userNode) {
        userNode.targetOpacity = 1;
        self.effects.push({type:"spawn", node:userNode, t:0, dur:1.0});
      }
      self.playing = true;
      if (playBtn) playBtn.textContent = "\u25B6";
      var prog = document.getElementById("flow-progress");
      if (prog) prog.style.width = "0%";
      self.userOverride = false;
      self._fitAll();
      if (showAllBtn) showAllBtn.classList.remove("active");
    });

    document.querySelectorAll(".speed-btn").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var speed = parseInt(btn.dataset.speed);
        if (isNaN(speed)) return; // skip non-speed buttons like showall
        if (speed === 0) { self._skipToEnd(); return; }
        self.playSpeed = speed;
        document.querySelectorAll(".speed-btn").forEach(function(b) { b.classList.remove("active"); });
        btn.classList.add("active");
      });
    });

    var progBar = document.querySelector(".flow-progress");
    if (progBar) progBar.addEventListener("click", function(e) {
      var rect = progBar.getBoundingClientRect();
      var pct = (e.clientX - rect.left) / rect.width;
      var events = self.flow.events || [];
      if (events.length === 0) return;
      var maxT = self._compressTime(events[events.length - 1].t, events);
      self.playTime = pct * maxT;
      self.playIndex = 0;
      self._userMsgCount = 0;
      self._assistantMsgCount = 0;
      self.allNodes.forEach(function(n) { n.opacity = 0; n.targetOpacity = 0; });
      self.toolNodes.forEach(function(n) { n.displayCount = 0; });
      self.effects = [];
      self.reverseBursts = [];
      self.playDone = false;
      var wasPlaying = self.playing;
      self.playing = true;
      self._stepPlayback(0);
      self.playing = wasPlaying;
    });
  }
}

if (FLOW && FLOW.agents && FLOW.agents.length > 0 && FLOW.events && FLOW.events.length > 0) {
  const fc = document.getElementById("flow-canvas");
  const cp = document.querySelector(".chat-panel");
  if (fc && cp) {
    window._sessionFlow = new SessionFlow(fc, FLOW, cp);
  }
} else {
  var fc = document.querySelector('.flow-container');
  if (fc) fc.style.display = 'none';
}

document.querySelectorAll(".msg,.marker").forEach(function(el) {
  el.addEventListener("click", function() {
    if (!window._sessionFlow) return;
    var match = (el.id || "").match(/(?:msg|marker)-(\d+)/);
    var idx = match ? parseInt(match[1]) : NaN;
    if (isNaN(idx)) return;
    var sf = window._sessionFlow;
    var evt = sf.flow.events.find(function(e) { return e.msg_index === idx; });
    if (!evt) return;
    var node = sf.allNodes.find(function(n) { return n.id === evt.agent_id; });
    if (node) {
      sf.selected = node;
      sf.effects.push({type:"pulse", node:node, t:0, dur:1.0});
    }
  });
});

var flowToggle = document.getElementById('flow-toggle');
var flowContainer = document.querySelector('.flow-container');
if (flowToggle && flowContainer) {
  if (window.innerWidth < 1000) {
    flowContainer.style.display = 'none';
  }
  flowToggle.addEventListener('click', function() {
    var visible = flowContainer.classList.toggle('visible');
    flowContainer.style.display = visible ? 'block' : 'none';
    flowToggle.textContent = visible ? 'Hide Flow' : 'Show Flow';
    if (visible && window._sessionFlow) {
      window._sessionFlow._resize();
      window._sessionFlow._fitAll();
    }
  });
  window.addEventListener('resize', function() {
    if (window.innerWidth >= 1000) {
      flowToggle.style.display = 'none';
      flowContainer.style.display = '';
      flowContainer.classList.remove('visible');
    } else if (!flowContainer.classList.contains('visible')) {
      flowToggle.style.display = 'block';
      flowContainer.style.display = 'none';
    }
  });
}
</script>
</body>
</html>'''


def generate_project_pages(session_list, data=None):
    """Generate individual HTML pages for each project."""
    projects_dir = OUTPUT_DIR / "projects"
    projects_dir.mkdir(exist_ok=True)

    # Group sessions by project
    project_sessions = defaultdict(list)
    for s in session_list:
        project_sessions[s["project"]].append(s)

    count = 0
    slug_map = {}
    for proj_name, proj_sessions in project_sessions.items():
        proj_sessions.sort(key=lambda s: s["start"], reverse=True)

        total_cost = sum(s["cost"] for s in proj_sessions)
        total_messages = sum(s["messages"] for s in proj_sessions)
        total_tokens = sum(s["input_tokens"] + s["output_tokens"] for s in proj_sessions)

        proj_tools = defaultdict(int)
        proj_skills = defaultdict(int)
        for s in proj_sessions:
            for t, c in s.get("tools", {}).items():
                proj_tools[t] += c
            for sk, c in s.get("skills", {}).items():
                proj_skills[sk] += c

        # Memory for this project
        memory_content = ""
        if data and data.get("_memories"):
            proj_dir = proj_sessions[0].get("project_dir", "") if proj_sessions else ""
            if proj_dir in data["_memories"]:
                memory_content = data["_memories"][proj_dir].get("content", "")

        # File ops aggregation
        proj_file_ops = defaultdict(lambda: {"read": 0, "edit": 0, "write": 0})
        workflow_events = []
        file_ops_by_session = data.get("_file_ops_by_session", {}) if data else {}
        for s in proj_sessions:
            sid = s["session_id"]
            ops = file_ops_by_session.get(sid, [])
            for fo in ops:
                proj_file_ops[fo["path"]][fo["op"]] += 1
                workflow_events.append({
                    "type": fo["op"],
                    "path": fo["path"],
                    "timestamp": fo["timestamp"],
                    "session_id": sid,
                })
            # Add git ops to workflow
            for go in s.get("git_ops", []):
                workflow_events.append({
                    "type": "git_" + go["type"],
                    "message": go.get("message", ""),
                    "timestamp": go["timestamp"],
                    "session_id": sid,
                })
            # Add agent dispatches to workflow
            for ad in s.get("agent_dispatches", []):
                workflow_events.append({
                    "type": "agent",
                    "description": ad.get("description", ""),
                    "agent_type": ad.get("type", ""),
                    "timestamp": "",
                    "session_id": sid,
                })

        # Sort workflow by timestamp (events without timestamps go to end)
        workflow_events.sort(key=lambda e: e.get("timestamp", "") or "z")

        # Top files
        top_files = sorted(proj_file_ops.items(), key=lambda x: -(x[1]["edit"] + x[1]["write"] + x[1]["read"]))[:15]

        # Subagent types
        proj_agent_types = defaultdict(int)
        for s in proj_sessions:
            for ad in s.get("agent_dispatches", []):
                proj_agent_types[ad.get("type", "general-purpose")] += 1

        # Git ops counts
        proj_commits = sum(len([g for g in s.get("git_ops", []) if g["type"] == "commit"]) for s in proj_sessions)
        proj_pushes = sum(len([g for g in s.get("git_ops", []) if g["type"] == "push"]) for s in proj_sessions)
        proj_prs = sum(len([g for g in s.get("git_ops", []) if g["type"] == "pr"]) for s in proj_sessions)

        # Error count
        proj_errors = sum(s.get("error_count", 0) for s in proj_sessions)

        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', proj_name.replace('/', '_'))
        slug_map[proj_name] = slug

        project_json = json.dumps({
            "name": proj_name,
            "sessions": proj_sessions,
            "stats": {
                "total_sessions": len(proj_sessions),
                "total_messages": total_messages,
                "total_cost": round(total_cost, 2),
                "total_tokens": total_tokens,
            },
            "tools": dict(sorted(proj_tools.items(), key=lambda x: -x[1])),
            "skills": dict(sorted(proj_skills.items(), key=lambda x: -x[1])),
            "memory": memory_content,
            "top_files": [{"path": p, "ops": o} for p, o in top_files],
            "workflow": workflow_events[:500],
            "agent_types": dict(sorted(proj_agent_types.items(), key=lambda x: -x[1])),
            "git_ops": {"commits": proj_commits, "pushes": proj_pushes, "prs": proj_prs},
            "error_count": proj_errors,
        }, ensure_ascii=False)

        html = _get_project_html_template()
        html = html.replace('"__PROJECT_DATA__"', project_json)
        html = html.replace('__VERSION__', VERSION)

        out_path = projects_dir / f"{slug}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        count += 1

    print(f"  Generated {count} project pages in {projects_dir}")
    return slug_map


def _get_project_html_template():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Project Detail</title>
<link rel="icon" type="image/png" href="../favicon.png">
<style>
:root { --bg:#0f1117; --bg2:#1a1d27; --bg3:#242836; --border:#2d3348; --text:#e2e8f0; --text2:#94a3b8; --accent:#6366f1; --accent2:#818cf8; --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --blue:#3b82f6; --purple:#a855f7; --cyan:#06b6d4; --amber:#f59e0b; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,-apple-system,sans-serif; font-size:14px; }
a { color:var(--accent2); text-decoration:none; }
a:hover { text-decoration:underline; }
.header { background:var(--bg2); border-bottom:1px solid var(--border); padding:16px 24px; }
.header-top { display:flex; align-items:center; gap:16px; margin-bottom:4px; }
.header h1 { font-size:20px; font-weight:600; }
.container { max-width:1400px; margin:0 auto; padding:20px; }
.kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.kpi-card { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; text-align:center; }
.kpi-card .label { color:var(--text2); font-size:12px; text-transform:uppercase; margin-bottom:8px; }
.kpi-card .value { font-size:28px; font-weight:700; }
.tools-section { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:24px; }
.tools-section h3 { font-size:15px; font-weight:600; margin-bottom:12px; }
.tool-pills { display:flex; flex-wrap:wrap; gap:8px; }
.tool-pill { background:var(--bg3); padding:4px 12px; border-radius:16px; font-size:12px; display:flex; align-items:center; gap:6px; }
.tool-pill .count { color:var(--cyan); font-weight:600; }
.session-card { background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:12px; transition:border-color .2s; }
.session-card:hover { border-color:var(--accent); }
.session-card .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.session-card .cost { color:var(--orange); font-weight:700; font-size:16px; }
.session-card .info { display:flex; gap:16px; color:var(--text2); font-size:12px; flex-wrap:wrap; }
.model-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }
.model-badge.opus { background:rgba(168,85,247,0.2); color:var(--purple); }
.model-badge.sonnet { background:rgba(59,130,246,0.2); color:var(--blue); }
.model-badge.haiku { background:rgba(34,197,94,0.2); color:var(--green); }
.proj-tabs { display:flex; gap:0; margin-bottom:24px; border-bottom:2px solid var(--border); }
.proj-tab { padding:10px 20px; font-size:14px; font-weight:600; border:none; background:transparent; color:var(--text2); cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; }
.proj-tab.active { color:var(--accent2); border-bottom-color:var(--accent); }
.proj-tab-content { display:none; }
.proj-tab-content.active { display:block; }
.memory-card { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:24px; }
.memory-card h3 { font-size:15px; margin-bottom:12px; cursor:pointer; display:flex; align-items:center; gap:8px; }
.memory-card h3::before { content:'\\25b6'; font-size:10px; transition:transform 0.2s; }
.memory-card.expanded h3::before { transform:rotate(90deg); }
.memory-content { display:none; font-size:13px; line-height:1.6; white-space:pre-wrap; word-break:break-word; color:var(--text2); max-height:500px; overflow-y:auto; }
.memory-card.expanded .memory-content { display:block; }
.info-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:24px; }
.info-card { background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:16px; }
.info-card h4 { font-size:13px; color:var(--text2); text-transform:uppercase; margin-bottom:8px; }
.info-row { display:flex; justify-content:space-between; padding:4px 0; font-size:13px; }
.info-row .lbl { color:var(--text2); }
.info-row .val { font-weight:600; }
.file-table { width:100%; border-collapse:collapse; font-size:13px; }
.file-table th { text-align:left; padding:8px; color:var(--text2); font-size:11px; text-transform:uppercase; border-bottom:1px solid var(--border); }
.file-table td { padding:6px 8px; border-bottom:1px solid var(--border); }
.file-table td:not(:first-child) { text-align:center; font-variant-numeric:tabular-nums; }
.tag { display:inline-block; padding:3px 10px; border-radius:6px; font-size:12px; font-weight:600; margin:2px; }
.workflow-timeline { position:relative; padding-left:24px; }
.workflow-timeline::before { content:''; position:absolute; left:8px; top:0; bottom:0; width:2px; background:var(--border); }
.wf-entry { position:relative; margin-bottom:6px; padding:4px 0 4px 16px; font-size:12px; }
.wf-entry::before { content:''; position:absolute; left:-20px; top:8px; width:10px; height:10px; border-radius:50%; }
.wf-entry.read::before { background:var(--blue); }
.wf-entry.edit::before { background:var(--cyan); }
.wf-entry.write::before { background:var(--green); }
.wf-entry.git_commit::before { background:var(--orange); }
.wf-entry.git_push::before { background:var(--amber); }
.wf-entry.git_pr::before { background:var(--purple); }
.wf-entry.agent::before { background:var(--accent); }
.wf-entry .path { color:var(--text2); font-family:monospace; font-size:11px; }
.wf-entry .msg { color:var(--text); }
.wf-entry .ts { color:var(--text2); font-size:10px; margin-left:8px; }
.wf-filters { display:flex; gap:6px; margin-bottom:16px; flex-wrap:wrap; }
.wf-filter { padding:4px 12px; font-size:11px; border:1px solid var(--border); background:var(--bg2); color:var(--text2); cursor:pointer; border-radius:4px; }
.wf-filter.active { background:var(--accent); color:white; border-color:var(--accent); }
@media (max-width:900px) { .kpi-grid { grid-template-columns:repeat(2,1fr); } .info-grid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="header">
  <div class="header-top"><a href="../index.html">&larr; Back to Dashboard</a></div>
  <h1 id="projectTitle"></h1>
</div>
<div class="container">
  <div class="kpi-grid" id="kpiGrid"></div>
  <div class="proj-tabs">
    <button class="proj-tab active" data-tab="overview">Overview</button>
    <button class="proj-tab" data-tab="workflow">Workflow</button>
  </div>
  <div class="proj-tab-content active" id="ptab-overview">
    <div id="memorySection"></div>
    <div class="info-grid" id="infoGrid"></div>
    <div class="tools-section" id="toolsSection"><h3>Top Tools</h3><div class="tool-pills" id="toolPills"></div></div>
    <div id="skillsSection"></div>
    <div id="topFilesSection"></div>
    <h3 style="margin:24px 0 16px;font-size:15px">Sessions</h3>
    <div id="sessionList"></div>
  </div>
  <div class="proj-tab-content" id="ptab-workflow">
    <div class="wf-filters" id="wfFilters"></div>
    <div class="workflow-timeline" id="workflowTimeline"></div>
  </div>
</div>
<script>
const P = "__PROJECT_DATA__";
const fmt = n => n.toLocaleString();
const fmtUSD = n => '$'+n.toFixed(2);
const fmtTokens = n => { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); };
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function modelClass(m) { const l=(m||'').toLowerCase(); if(l.includes('opus')) return 'opus'; if(l.includes('sonnet')) return 'sonnet'; if(l.includes('haiku')) return 'haiku'; return ''; }

document.getElementById('projectTitle').textContent = P.name;
document.getElementById('kpiGrid').innerHTML =
  '<div class="kpi-card"><div class="label">Sessions</div><div class="value" style="color:var(--blue)">'+P.stats.total_sessions+'</div></div>' +
  '<div class="kpi-card"><div class="label">Messages</div><div class="value" style="color:var(--green)">'+fmt(P.stats.total_messages)+'</div></div>' +
  '<div class="kpi-card"><div class="label">Tokens</div><div class="value" style="color:var(--purple)">'+fmtTokens(P.stats.total_tokens)+'</div></div>' +
  '<div class="kpi-card"><div class="label">Est. Cost</div><div class="value" style="color:var(--orange)">'+fmtUSD(P.stats.total_cost)+'</div></div>';

document.getElementById('toolPills').innerHTML = Object.entries(P.tools).slice(0,20).map(([n,c]) =>
  '<div class="tool-pill"><span>'+escHtml(n)+'</span><span class="count">'+c+'x</span></div>'
).join('');

if (Object.keys(P.skills).length>0) {
  document.getElementById('skillsSection').innerHTML =
    '<div class="tools-section"><h3>Skills</h3><div class="tool-pills">' +
    Object.entries(P.skills).map(([n,c]) =>
      '<div class="tool-pill" style="border:1px solid rgba(168,85,247,0.3)"><span style="color:var(--purple)">'+escHtml(n)+'</span><span class="count" style="color:var(--purple)">'+c+'x</span></div>'
    ).join('') + '</div></div>';
}

// Tab switching
document.querySelectorAll('.proj-tab').forEach(tab => {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.proj-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.proj-tab-content').forEach(c => c.classList.remove('active'));
    this.classList.add('active');
    document.getElementById('ptab-'+this.dataset.tab).classList.add('active');
  });
});

// Memory
if (P.memory) {
  document.getElementById('memorySection').innerHTML =
    '<div class="memory-card" id="memCard"><h3 onclick="document.getElementById(\\\'memCard\\\').classList.toggle(\\\'expanded\\\')">Project Memory</h3><div class="memory-content">'+escHtml(P.memory)+'</div></div>';
}

// Info grid (subagents, git ops, errors)
let infoHtml = '';
const agentTypes = Object.entries(P.agent_types || {});
if (agentTypes.length > 0) {
  infoHtml += '<div class="info-card"><h4>Subagents</h4>' +
    agentTypes.map(([t,c]) => '<span class="tag" style="background:rgba(99,102,241,0.15);color:var(--accent2)">'+escHtml(t)+' '+c+'x</span>').join('') +
    '</div>';
}
const go = P.git_ops || {};
if ((go.commits||0) + (go.pushes||0) + (go.prs||0) > 0) {
  infoHtml += '<div class="info-card"><h4>Git Operations</h4>' +
    '<div class="info-row"><span class="lbl">Commits</span><span class="val" style="color:var(--green)">'+(go.commits||0)+'</span></div>' +
    '<div class="info-row"><span class="lbl">Pushes</span><span class="val" style="color:var(--blue)">'+(go.pushes||0)+'</span></div>' +
    '<div class="info-row"><span class="lbl">PRs</span><span class="val" style="color:var(--purple)">'+(go.prs||0)+'</span></div>' +
    '</div>';
}
if (P.error_count > 0) {
  infoHtml += '<div class="info-card"><h4>Errors</h4>' +
    '<div style="font-size:24px;font-weight:700;color:var(--red)">'+P.error_count+'</div>' +
    '<div style="color:var(--text2);font-size:12px">tool errors in this project</div></div>';
}
document.getElementById('infoGrid').innerHTML = infoHtml;

// Top files table
const tf = P.top_files || [];
if (tf.length > 0) {
  document.getElementById('topFilesSection').innerHTML =
    '<div class="tools-section"><h3>Top Files</h3>' +
    '<table class="file-table"><thead><tr><th>File</th><th>Reads</th><th>Edits</th><th>Writes</th></tr></thead><tbody>' +
    tf.map(f => {
      const short = f.path.split('/').slice(-2).join('/');
      return '<tr><td title="'+escHtml(f.path)+'"><code style="font-size:11px">'+escHtml(short)+'</code></td>' +
        '<td style="color:var(--blue)">'+(f.ops.read||0)+'</td>' +
        '<td style="color:var(--cyan)">'+(f.ops.edit||0)+'</td>' +
        '<td style="color:var(--green)">'+(f.ops.write||0)+'</td></tr>';
    }).join('') +
    '</tbody></table></div>';
}

document.getElementById('sessionList').innerHTML = P.sessions.map(s =>
  '<div class="session-card">' +
    '<div class="top">' +
      '<div>' +
        '<span style="color:var(--text2);font-size:12px">'+new Date(s.start).toLocaleDateString()+' '+new Date(s.start).toLocaleTimeString()+'</span>' +
        '<span class="model-badge '+modelClass(s.primary_model)+'" style="margin-left:8px">'+escHtml(s.primary_model)+'</span>' +
        ((s.compactions||0)>0 ? '<span style="color:var(--amber);font-size:12px;margin-left:8px">&#9889; '+s.compactions+'</span>' : '') +
      '</div>' +
      '<div style="display:flex;gap:12px;align-items:center">' +
        '<a href="../sessions/'+s.session_id+'.html" style="font-size:12px;padding:4px 10px;border:1px solid var(--accent);border-radius:6px">Chat</a>' +
        '<span class="cost">'+fmtUSD(s.cost)+'</span>' +
      '</div>' +
    '</div>' +
    '<div class="info">' +
      '<span>'+s.duration_min+'m</span>' +
      '<span>'+s.messages+' msgs</span>' +
      '<span>'+fmtTokens(s.input_tokens+s.output_tokens)+' tokens</span>' +
      '<span>'+s.api_calls+' API calls</span>' +
    '</div>' +
  '</div>'
).join('');

// Workflow timeline
const wf = P.workflow || [];
const wfTypes = ['read','edit','write','git_commit','git_push','git_pr','agent'];
const wfLabels = {read:'Read',edit:'Edit',write:'Write',git_commit:'Commit',git_push:'Push',git_pr:'PR',agent:'Agent'};
let activeWfFilters = new Set(wfTypes);

function renderWorkflow() {
  const filtered = wf.filter(e => activeWfFilters.has(e.type));
  const el = document.getElementById('workflowTimeline');
  if (filtered.length === 0) { el.innerHTML = '<div style="color:var(--text2);padding:20px">No workflow events</div>'; return; }
  const shown = filtered.slice(0, 200);
  el.innerHTML = shown.map(e => {
    let label = '';
    if (e.path) {
      const short = e.path.split('/').slice(-2).join('/');
      label = '<span class="path">'+escHtml(short)+'</span>';
    } else if (e.message) {
      label = '<span class="msg">'+escHtml(e.message.slice(0,80))+'</span>';
    } else if (e.description) {
      label = '<span class="msg">'+escHtml(e.description)+'</span>';
    }
    const ts = e.timestamp ? '<span class="ts">'+new Date(e.timestamp).toLocaleTimeString()+'</span>' : '';
    return '<div class="wf-entry '+e.type+'">'+label+ts+'</div>';
  }).join('') + (filtered.length > 200 ? '<div style="color:var(--text2);padding:8px;font-size:12px">...and '+(filtered.length-200)+' more</div>' : '');
}

document.getElementById('wfFilters').innerHTML = wfTypes.map(t =>
  '<button class="wf-filter active" data-type="'+t+'">'+wfLabels[t]+'</button>'
).join('');

document.querySelectorAll('.wf-filter').forEach(btn => {
  btn.addEventListener('click', function() {
    const type = this.dataset.type;
    if (activeWfFilters.has(type)) { activeWfFilters.delete(type); this.classList.remove('active'); }
    else { activeWfFilters.add(type); this.classList.add('active'); }
    renderWorkflow();
  });
});

renderWorkflow();
</script>
</body>
</html>'''


def main():
    print("Claude Code Statistics Extractor")
    print("=" * 50)
    print(f"  Primary:   {CLAUDE_DIR}")
    if MIGRATION_ENABLED:
        print(f"  Migration: {MIGRATION_CLAUDE_DIR}"
              f" ({'found' if MIGRATION_CLAUDE_DIR.exists() else 'not found'})")
    else:
        print(f"  Migration: disabled")

    t0 = time.time()

    print("\n[1/10] Loading stats-cache.json...")
    stats_cache = load_stats_cache()
    print(f"  Total sessions (from cache): {stats_cache.get('totalSessions', '?')}")
    print(f"  Total messages (from cache): {stats_cache.get('totalMessages', '?')}")

    print("\n[2/10] Loading .claude.json...")
    dot_claude = load_dot_claude()
    projects = dot_claude.get("projects", {})
    print(f"  Projects with metadata: {len(projects)}")

    print("\n[3/10] Loading history.jsonl...")
    history = load_history()
    print(f"  User prompts: {len(history)}")

    print("\n[4/10] Parsing session transcripts...")
    sessions = parse_session_transcripts()

    print("\n[5/10] Loading plans...")
    plans = load_plans()
    print(f"  Plan files: {len(plans)}")

    print("\n[6/10] Loading plugins...")
    plugins = load_plugins()
    print(f"  Installed plugins: {len(plugins['installed'])}")

    print("\n[7/10] Loading todos & file history...")
    todos = load_todos()
    file_history = load_file_history_stats()
    print(f"  Todos: {todos['total']} ({todos['completed']} completed)")
    print(f"  File history: {file_history['total_files']} snapshots in {file_history['total_sessions']} sessions")

    print("\n[8/10] Calculating storage...")
    storage = calc_storage()
    print(f"  Total ~/.claude size: {storage['total_mb']} MB")

    print("\n[9/10] Loading telemetry...")
    telemetry = load_telemetry()
    print(f"  Events: {telemetry['total_events']}, Sessions: {len(telemetry['per_session'])}")

    skip_memories = "--no-memories" in sys.argv
    print("\n[10/10] Loading memories & tasks...")
    memories = load_project_memories(skip_memories)
    tasks = load_tasks()
    print(f"  Memories: {len(memories)} projects")
    print(f"  Tasks: {tasks['total']} ({tasks['completed']} completed)")

    OUTPUT_DIR.mkdir(exist_ok=True)

    print("\nAggregating data...")
    data = build_dashboard_data(
        sessions, stats_cache, dot_claude, history,
        plans=plans, plugins=plugins, todos=todos,
        file_history=file_history, storage=storage,
        telemetry=telemetry, tasks=tasks, memories=memories,
    )

    print(f"\nWriting {DASHBOARD_DATA}...")
    with open(DASHBOARD_DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Size: {DASHBOARD_DATA.stat().st_size / 1024:.1f} KB")

    print(f"\nGenerating {DASHBOARD_HTML}...")
    generate_dashboard(data)
    print(f"  Size: {DASHBOARD_HTML.stat().st_size / 1024:.1f} KB")

    print(f"\nGenerating session pages...")
    generate_session_pages(sessions, data["sessions"])

    print(f"\nGenerating project pages...")
    project_slugs = generate_project_pages(data["sessions"], data=data)
    data["project_slugs"] = project_slugs
    # Re-generate dashboard with project slug mapping
    generate_dashboard(data)

    elapsed = time.time() - t0
    print(f"\n{'=' * 50}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  Sessions: {data['kpi']['total_sessions']}")
    print(f"  Messages: {data['kpi']['total_messages']}")
    print(f"  API-Aequivalent: ${data['kpi']['total_cost']:.2f}")
    print(f"  Projects: {data['kpi']['total_projects']}")
    print(f"  Models: {', '.join(data['models'])}")
    print("\n  \u26a0  Output may contain sensitive data. Do not publish without access control.")


if __name__ == "__main__":
    main()
