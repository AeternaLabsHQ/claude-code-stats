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
import subprocess
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

SOURCE_LABEL = CONFIG.get("source_label", "current")

# ── Migration Backup (optional, configured in config.json) ───────────────
_mig = CONFIG.get("migration", {})
MIGRATION_ENABLED = _mig.get("enabled", False)
MIGRATION_LABEL = _mig.get("label", "migration")
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
    _sudo_user = _src.get("sudo_user")
    if _sudo_user or _claude_dir.exists():
        ADDITIONAL_SOURCES.append({
            "label": _src.get("label", _claude_dir.name),
            "claude_dir": _claude_dir,
            "projects_dir": _claude_dir / "projects",
            "dot_claude_json": _dot_claude_json,
            "stats_cache": _claude_dir / "stats-cache.json",
            "history_jsonl": _claude_dir / "history.jsonl",
            "sudo_user": _sudo_user,
        })


def _get_sudo_user_for_path(path):
    """Look up the sudo_user for a path based on ADDITIONAL_SOURCES config."""
    path_str = str(path)
    for _as in ADDITIONAL_SOURCES:
        if _as.get("sudo_user") and path_str.startswith(str(_as["claude_dir"])):
            return _as["sudo_user"]
    return None


def read_text(path):
    """Read a text file, using sudo if the path belongs to a sudo_user source."""
    su = _get_sudo_user_for_path(path)
    if su:
        return sudo_read_text(path, su)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def path_exists(path):
    """Check if a path exists, using sudo if needed."""
    su = _get_sudo_user_for_path(path)
    if su:
        return sudo_path_exists(path, su)
    return path.exists()


def sudo_read_text(path, sudo_user):
    """Read a file as another user via sudo. Returns text content or None on error."""
    try:
        r = subprocess.run(
            ["sudo", "-n", "-u", sudo_user, "cat", str(path)],
            capture_output=True, text=True, timeout=30, cwd="/",
        )
        return r.stdout if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def sudo_path_exists(path, sudo_user):
    """Check if a path exists as another user via sudo."""
    r = subprocess.run(
        ["sudo", "-n", "-u", sudo_user, "test", "-e", str(path)],
        capture_output=True, timeout=5, cwd="/",
    )
    return r.returncode == 0


def sudo_list_dir(path, sudo_user):
    """List directory entries as another user. Returns list of Path objects."""
    r = subprocess.run(
        ["sudo", "-n", "-u", sudo_user, "find", str(path), "-maxdepth", "1", "-mindepth", "1"],
        capture_output=True, text=True, timeout=30, cwd="/",
    )
    if r.returncode != 0:
        print(f"    WARNING: sudo_list_dir failed for {path} (rc={r.returncode}): {r.stderr.strip()}")
        return []
    return [Path(p) for p in r.stdout.strip().split("\n") if p]


def sudo_find_files(path, pattern, sudo_user):
    """Find files matching a pattern as another user. Returns list of Path objects."""
    r = subprocess.run(
        ["sudo", "-n", "-u", sudo_user, "find", str(path), "-name", pattern, "-type", "f"],
        capture_output=True, text=True, timeout=60, cwd="/",
    )
    if r.returncode != 0:
        return []
    return [Path(p) for p in r.stdout.strip().split("\n") if p]


def sudo_file_size(path, sudo_user):
    """Get file size as another user. Returns size in bytes or 0."""
    r = subprocess.run(
        ["sudo", "-n", "-u", sudo_user, "stat", "-c", "%s", str(path)],
        capture_output=True, text=True, timeout=5, cwd="/",
    )
    try:
        return int(r.stdout.strip()) if r.returncode == 0 else 0
    except ValueError:
        return 0

VERSION = "0.8.2"

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


def attribute_turn_tokens(output_tokens, cost, tool_names):
    """Split a turn's output_tokens and cost across its tool_use blocks.

    Repeated tool names in the same turn collapse into a single entry whose
    share equals (count_of_that_tool / total_tools) of the turn.
    Turns with no tools attribute fully to the reasoning bucket.
    """
    if not tool_names:
        return {
            "per_tool": [],
            "reasoning_output_tokens": output_tokens,
            "reasoning_cost": cost,
        }

    n = len(tool_names)
    per_tool_counts = {}
    for name in tool_names:
        per_tool_counts[name] = per_tool_counts.get(name, 0) + 1

    per_tool = []
    items = list(per_tool_counts.items())
    allocated_tokens = 0
    allocated_cost = 0.0
    for i, (name, c) in enumerate(items):
        share = c / n
        if i < len(items) - 1:
            tokens = int(round(output_tokens * share))
            tcost = cost * share
        else:
            # Last entry absorbs rounding remainder so totals reconcile exactly.
            tokens = output_tokens - allocated_tokens
            tcost = cost - allocated_cost
        allocated_tokens += tokens
        allocated_cost += tcost
        per_tool.append({
            "tool": name,
            "output_tokens": tokens,
            "cost": tcost,
        })

    return {
        "per_tool": per_tool,
        "reasoning_output_tokens": 0,
        "reasoning_cost": 0.0,
    }


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
        if not path:
            continue
        content = read_text(path)
        if content is None:
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue
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
    _dot_claude_cache = {}
    for path in sources:
        if not path:
            continue
        content = read_text(path)
        if content is None:
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue
        _dot_claude_cache[str(path)] = data
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
        data = _dot_claude_cache.get(str(path))
        if not data:
            continue
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
        if not path:
            continue
        content = read_text(path)
        if content is None:
            continue
        for line in content.split("\n"):
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
        try:
            for sess_dir in fh_dir.iterdir():
                if not sess_dir.is_dir():
                    continue
                if sess_dir.name in seen_sessions:
                    continue
                seen_sessions.add(sess_dir.name)
                sessions += 1
                try:
                    for f in sess_dir.iterdir():
                        if f.is_file():
                            try:
                                total_size += f.stat().st_size
                                total_files += 1
                            except PermissionError:
                                pass
                except PermissionError:
                    pass
        except PermissionError:
            pass
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
                try:
                    if f.is_file():
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

    sources = []  # (label, projects_dir, sudo_user_or_None)
    if MIGRATION_ENABLED and MIGRATION_PROJECTS_DIR and MIGRATION_PROJECTS_DIR.exists():
        sources.append((MIGRATION_LABEL, MIGRATION_PROJECTS_DIR, None))
    for _as in ADDITIONAL_SOURCES:
        _su = _as.get("sudo_user")
        if _su:
            if sudo_path_exists(_as["projects_dir"], _su):
                sources.append((_as["label"], _as["projects_dir"], _su))
        elif _as["projects_dir"].exists():
            sources.append((_as["label"], _as["projects_dir"], None))
    if PROJECTS_DIR.exists():
        sources.append((SOURCE_LABEL, PROJECTS_DIR, None))

    if not sources:
        print(f"  WARNING: No projects directories found")
        return sessions

    for source_label, projects_dir, sudo_user in sources:
        print(f"  Source: {source_label} ({projects_dir}){' [sudo:'+sudo_user+']' if sudo_user else ''}")
        if sudo_user:
            project_dirs = sorted(sudo_list_dir(projects_dir, sudo_user))
        else:
            project_dirs = sorted(projects_dir.iterdir())
        total_dirs = len(project_dirs)

        for idx, project_dir in enumerate(project_dirs):
            if not sudo_user and not project_dir.is_dir():
                continue

            project_name = project_dir.name
            if sudo_user:
                jsonl_files = sorted(sudo_find_files(project_dir, "*.jsonl", sudo_user))
            else:
                jsonl_files = sorted(project_dir.rglob("*.jsonl"))

            if not jsonl_files:
                continue

            print(f"    [{idx+1}/{total_dirs}] {project_name} ({len(jsonl_files)} files)")

            for jsonl_file in jsonl_files:
                total_files += 1
                file_session_id = jsonl_file.stem
                if sudo_user:
                    file_size = sudo_file_size(jsonl_file, sudo_user)
                else:
                    file_size = jsonl_file.stat().st_size

                # Detect subagent sessions
                is_subagent = "/subagents/" in str(jsonl_file)
                parent_id = ""
                if is_subagent:
                    parent_id = jsonl_file.parent.parent.name

                # Skip if this session was already fully parsed from migration
                if file_session_id in sessions and source_label == SOURCE_LABEL:
                    # Same session file in both sources — skip duplicate
                    continue

                try:
                    if sudo_user:
                        _content = sudo_read_text(jsonl_file, sudo_user)
                        if _content is None:
                            continue
                        _line_iter = _content.split("\n")
                    else:
                        _line_iter = open(jsonl_file, "r", encoding="utf-8", errors="replace").readlines()

                    for line in _line_iter:
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

    migration_count = sum(1 for s in sessions.values() if s.get("source") == MIGRATION_LABEL)
    current_count = sum(1 for s in sessions.values() if s.get("source") == SOURCE_LABEL)
    print(f"  Parsed {total_files} files, {total_lines} lines, {len(sessions)} sessions"
          f" (migration: {migration_count}, current: {current_count})")
    return sessions


def extract_session_messages(session_id, project_dir_name):
    """Extract per-message data for a single session for replay view."""
    messages = []

    # Search for the JSONL file
    sources = []  # (projects_dir, sudo_user_or_None)
    if MIGRATION_ENABLED and MIGRATION_PROJECTS_DIR and MIGRATION_PROJECTS_DIR.exists():
        sources.append((MIGRATION_PROJECTS_DIR, None))
    for _as in ADDITIONAL_SOURCES:
        _su = _as.get("sudo_user")
        if _su:
            sources.append((_as["projects_dir"], _su))
        elif _as["projects_dir"].exists():
            sources.append((_as["projects_dir"], None))
    if PROJECTS_DIR.exists():
        sources.append((PROJECTS_DIR, None))

    jsonl_path = None
    found_sudo_user = None
    for projects_dir, su in sources:
        candidate = projects_dir / project_dir_name / f"{session_id}.jsonl"
        if su:
            if sudo_path_exists(candidate, su):
                jsonl_path = candidate
                found_sudo_user = su
                break
            # Also search subdirectories
            found = sudo_find_files(projects_dir / project_dir_name, f"{session_id}.jsonl", su)
            if found:
                jsonl_path = found[0]
                found_sudo_user = su
                break
        else:
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

    if found_sudo_user:
        _content = sudo_read_text(jsonl_path, found_sudo_user)
        _lines = _content.split("\n") if _content else []
    else:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            _lines = f.readlines()

    for line in _lines:
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
                "plan_cost_eur": ph.get("cost_eur", ph.get("cost_local")),
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
        "plan_cost_eur": current_plan.get("cost_eur", current_plan.get("cost_local")),
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
    daily_cache_eff = defaultdict(list)
    hourly_messages = defaultdict(int)
    weekday_messages = defaultdict(int)
    project_stats = defaultdict(lambda: {
        "sessions": 0, "messages": 0, "cost": 0.0,
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "file_size": 0, "sources": set()
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
                "input_tokens": mdata["input_tokens"],
                "output_tokens": mdata["output_tokens"],
                "cache_read_tokens": mdata["cache_read_input_tokens"],
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
        ps["sources"].add(sess.get("source", SOURCE_LABEL))

        daily_messages[date_str] += sess["message_count"]
        daily_sessions[date_str] += 1
        hourly_messages[hour] += sess["user_message_count"]
        weekday_messages[weekday] += sess["user_message_count"]

        sess_total_in = session_input + session_cache_read + session_cache_write
        if sess_total_in > 0 and sess["message_count"] >= 3:
            daily_cache_eff[date_str].append(session_cache_read / sess_total_in * 100)

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
            "source": sess.get("source", SOURCE_LABEL),
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

    def _quantile(sorted_vals, q):
        n = len(sorted_vals)
        if n == 0:
            return 0.0
        if n == 1:
            return sorted_vals[0]
        pos = (n - 1) * q
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        frac = pos - lo
        return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

    daily_cache_efficiency_series = []
    for d in all_dates:
        vals = daily_cache_eff.get(d, [])
        if not vals:
            continue
        sv = sorted(vals)
        n = len(sv)
        median = _quantile(sv, 0.5)
        q1 = _quantile(sv, 0.25)
        q3 = _quantile(sv, 0.75)
        iqr = q3 - q1
        lo_fence = q1 - 1.5 * iqr
        hi_fence = q3 + 1.5 * iqr
        # Whiskers: most-extreme values still within fences
        in_range = [v for v in sv if lo_fence <= v <= hi_fence]
        whisker_low = in_range[0] if in_range else sv[0]
        whisker_high = in_range[-1] if in_range else sv[-1]
        outliers = [round(v, 2) for v in sv if v < lo_fence or v > hi_fence]
        daily_cache_efficiency_series.append({
            "date": d,
            "sessions": n,
            "mean": round(sum(sv) / n, 2),
            "median": round(median, 2),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
            "whisker_low": round(whisker_low, 2),
            "whisker_high": round(whisker_high, 2),
            "min": round(sv[0], 2),
            "max": round(sv[-1], 2),
            "outliers": outliers,
        })

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
            "sources": sorted(pdata["sources"]),
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
        "daily_cache_efficiency": daily_cache_efficiency_series,
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
    """Return the HTML template string with placeholders for data, styles, scripts."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "dashboard.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "dashboard.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "dashboard.js").read_text(encoding="utf-8")
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html


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
            sess_data["has_chat"] = False
            continue
        sess_data["has_chat"] = True

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
    """Return the session detail HTML template string."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "session_detail.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "session_detail.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "session_detail.js").read_text(encoding="utf-8")
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html


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
    """Return the project detail HTML template string."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "project_detail.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "project_detail.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "project_detail.js").read_text(encoding="utf-8")
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"<script>{js}</script>")
    return html


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

    print(f"\nGenerating session pages...")
    generate_session_pages(sessions, data["sessions"])

    print(f"\nGenerating project pages...")
    project_slugs = generate_project_pages(data["sessions"], data=data)
    data["project_slugs"] = project_slugs

    print(f"\nWriting {DASHBOARD_DATA}...")
    with open(DASHBOARD_DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Size: {DASHBOARD_DATA.stat().st_size / 1024:.1f} KB")

    print(f"\nGenerating {DASHBOARD_HTML}...")
    generate_dashboard(data)
    print(f"  Size: {DASHBOARD_HTML.stat().st_size / 1024:.1f} KB")

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
