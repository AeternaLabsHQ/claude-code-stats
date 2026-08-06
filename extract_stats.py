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
from datetime import datetime, timezone
from pathlib import Path

from claudestats_core.pricing import (
    PRICING, DEFAULT_PRICING, _version, derive_model_display,
    get_model_display, pricing_for_display, resolve_pricing,
    build_pricing_warnings, calc_cost,
)
from claudestats_core.attribution import (
    attribute_turn_tokens, WRITE_CATEGORIES, _block_weight,
    _block_category, attribute_write_categories,
)
from claudestats_core.classify import (
    _is_user_plan_limit_text, _classify_user_entry,
    _merge_streamed_assistant_entries, _classify_tool_error,
    _clean_error_text, _route_tool_error, _extract_command_label,
    _classify_api_error,
)
from claudestats_core.anomalies import (
    CONTEXT_1M_THRESHOLD, summarize_context_window,
    _detect_cache_flushes, _compute_idle_gap_summary,
)
from claudestats_core.limits import (
    _WEEKDAY_BY_ANCHOR, PLAN_TIER_FACTORS, PRO_CAPACITY_USD_DEFAULT,
    _normalize_tier_name, FIVE_HOUR_MS, _compute_5h_windows, _compute_weekly_buckets,
    _estimate_5h_window_cap_usd, _detect_5h_fingerprint_events,
    _iso_to_ms, _dedupe_limit_events, _match_limit_events_to_windows,
    _count_5h_hits,
)
from claudestats_core.sessions import (
    _merge_model_buckets, _absorb_subagent, _link_subagents,
    _day_from_ms, split_session_by_day,
    SessionFileMeta, absorb_file, finalize_sessions,
)
from claudestats_core.plan_analysis import (
    _month_day_clamped, _expand_billing_cycles, _recommend_tier,
    _tier_holds_in_cycle, _switch_arrow_for_cycle, build_plan_analysis,
    _plan_currency_symbol,
)
from claudestats_core.aggregate import project_display_name, build_dashboard_data

# ── Configuration ──────────────────────────────────────────────────────────
# Allows redirecting the config source via an environment variable, so
# test runs don't depend on a local config.json.
_cfg_env = os.environ.get("CLAUDE_STATS_CONFIG")
CONFIG_PATH = Path(_cfg_env) if _cfg_env else Path(__file__).parent / "config.json"
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

# Minimum messages a session-day slice needs before it enters the daily
# cache-efficiency box-plot series. 1-2 message sessions have no realistic
# cache-hit opportunity and only drag the distribution down. MUST match the
# client-side rebuild filter in templates/dashboard.js (plan B contract).
CACHE_EFF_MIN_MESSAGES = 3

# Anthropic weekly limits reset on a per-user weekday, not on ISO weeks.
# config.json "week_anchor" ("mon".."sun") sets that weekday for the weekly
# bucketing AND the frontend chart markers (exported as data["week_anchor"]).
WEEK_ANCHOR = str(CONFIG.get("week_anchor", "mon")).strip().lower()[:3]
if WEEK_ANCHOR not in _WEEKDAY_BY_ANCHOR:
    print(f"  WARNING: invalid week_anchor {CONFIG.get('week_anchor')!r} "
          f"in config.json; falling back to 'mon'")
    WEEK_ANCHOR = "mon"

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

VERSION = "1.0.0"

OUTPUT_DIR = Path(__file__).parent / "public"
DASHBOARD_DATA = OUTPUT_DIR / "dashboard_data.json"
DASHBOARD_HTML = OUTPUT_DIR / "index.html"
TEMPLATE_HTML = Path(__file__).parent / "dashboard_template.html"

# ── Plan Configuration (from config.json) ────────────────────────────────
PLAN_HISTORY = CONFIG.get("plan_history", [])
PLAN_CAPACITY_OVERRIDE_PRO_USD = CONFIG.get("plan_capacity_override_pro_usd")

import claudestats_core.settings as _core_settings
_core_settings.configure(
    week_anchor=WEEK_ANCHOR,
    plan_history=PLAN_HISTORY,
    plan_capacity_override_pro_usd=PLAN_CAPACITY_OVERRIDE_PRO_USD,
    cache_eff_min_messages=CACHE_EFF_MIN_MESSAGES,
    source_label=SOURCE_LABEL,
    locale=LOCALE,
    display_name=CONFIG.get("display_name"),
)


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


def parse_session_transcripts():
    """Parse all session JSONL transcripts from all sources."""
    sessions = {}
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

                meta = SessionFileMeta(
                    source_label=source_label,
                    file_session_id=file_session_id,
                    project_name=project_name,
                    file_size=file_size,
                )
                if "/subagents/" in str(jsonl_file):
                    meta.is_subagent = True
                    meta.parent_session_id = jsonl_file.parent.parent.name
                    if file_session_id.startswith("agent-"):
                        meta.agent_id = file_session_id[len("agent-"):]
                    meta_path = jsonl_file.with_suffix(".meta.json")
                    try:
                        if sudo_user:
                            _mc = sudo_read_text(meta_path, sudo_user)
                            if _mc:
                                _mj = json.loads(_mc)
                                meta.agent_type = _mj.get("agentType", "") or ""
                                meta.agent_description = _mj.get("description", "") or ""
                        elif meta_path.exists():
                            with open(meta_path, "r", encoding="utf-8", errors="replace") as _mf:
                                _mj = json.load(_mf)
                            meta.agent_type = _mj.get("agentType", "") or ""
                            meta.agent_description = _mj.get("description", "") or ""
                    except (OSError, json.JSONDecodeError):
                        pass

                try:
                    if sudo_user:
                        _content = sudo_read_text(jsonl_file, sudo_user)
                        if _content is None:
                            continue
                        _line_iter = _content.split("\n")
                    else:
                        _line_iter = open(jsonl_file, "r", encoding="utf-8", errors="replace").readlines()

                    _parsed_objs = []
                    for line in _line_iter:
                        total_lines += 1
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        _parsed_objs.append(obj)

                    absorb_file(sessions, meta, _parsed_objs)

                except Exception as e:
                    print(f"      ERROR reading {jsonl_file.name}: {e}")

    finalize_sessions(sessions)

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

    _detail_objs = []
    for line in _lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            _detail_objs.append(obj)

    # Same stream-split collapse as the stats pass, so the detail transcript
    # shows one bubble per response (all its text/tools together) with the
    # response's real cost (final usage from its last line), not one
    # fragmented bubble per content block each stamped with a partial usage.
    _tid_to_tool = {}       # tool_use id -> tool name, for tool_result errors
    _last_mode = None       # dedupe mode markers: emit only on change
    _last_perm = None       # dedupe permission-mode markers: emit only on change
    for obj in _merge_streamed_assistant_entries(_detail_objs):
            msg_type = obj.get("type")
            timestamp = obj.get("timestamp", "")

            # Real user-plan rate-limit events surface as isApiErrorMessage
            # entries (type: "assistant", message.role: "assistant") with
            # specific phrasing. Emit a chat marker so the Limits-tab
            # event-link has a visible landing spot. Skip the normal
            # assistant-message processing afterwards so the same text does
            # not appear twice in the chat (which would also push the
            # marker out of view when the page scrolls to the anchor).
            if obj.get("isApiErrorMessage"):
                _api_msg = obj.get("message", {})
                _api_txt = _api_msg.get("content", "") if isinstance(_api_msg, dict) else ""
                if isinstance(_api_txt, list):
                    _api_txt = next((b.get("text", "") for b in _api_txt
                                     if isinstance(b, dict) and b.get("type") == "text"), "")
                _api_txt = str(_api_txt)
                if _is_user_plan_limit_text(_api_txt):
                    # Dedicated rate-limit marker (also the Limits-tab anchor).
                    messages.append({
                        "role": "rate_limit",
                        "content": _api_txt[:400],
                        "timestamp": timestamp,
                    })
                    continue
                if _api_txt.strip():
                    # Other backend failure (auth / 5xx / overload / timeout …).
                    messages.append({
                        "role": "error",
                        "source": "backend",
                        "category": _classify_api_error(_api_txt),
                        "tool": "",
                        "content": _api_txt[:300],
                        "timestamp": timestamp,
                    })
                    continue

            if msg_type == "user":
                message = obj.get("message", {})
                content = message.get("content", "")

                # Compaction is a type:"user" entry flagged isCompactSummary
                # (the dead type:"summary" branch never fires). Emit a marker
                # instead of dumping the continuation note as a fake user msg.
                if obj.get("isCompactSummary"):
                    messages.append({"role": "compaction", "timestamp": timestamp})
                    continue

                if isinstance(content, list):
                    texts = []
                    tool_results = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "tool_result":
                                tool_results.append(block)
                            elif block.get("type") == "text":
                                texts.append(block.get("text", ""))
                    if tool_results:
                        # Tool results carry no chat text, but failed ones become
                        # error / rejected markers right after the call.
                        for tr in tool_results:
                            if not tr.get("is_error"):
                                continue
                            etxt = str(tr.get("content", ""))
                            if "<tool_use_error>" in etxt:
                                etxt = etxt.split("<tool_use_error>")[-1].split("</tool_use_error>")[0]
                            tname = _tid_to_tool.get(tr.get("tool_use_id", ""), "")
                            esrc, ecat = _classify_tool_error(etxt, tname)
                            if esrc == "user":
                                if ecat == "rejected":
                                    messages.append({
                                        "role": "rejected", "tool": tname,
                                        "content": etxt[:200], "timestamp": timestamp,
                                    })
                                # cancelled parallel-call cascades are noise → skip
                                continue
                            messages.append({
                                "role": "error", "source": esrc, "category": ecat,
                                "tool": tname, "content": _clean_error_text(etxt)[:2000],
                                "timestamp": timestamp,
                            })
                        continue
                    content = "\n".join(texts)

                if isinstance(content, str) and (content.startswith("<command") or content.startswith("<local-command")):
                    # Slash-command invocation → marker (command *output* is dropped).
                    label = _extract_command_label(content)
                    if label:
                        messages.append({"role": "command", "content": label, "timestamp": timestamp})
                    continue

                if isinstance(content, str) and content.startswith("[Request interrupted"):
                    messages.append({"role": "interrupt", "content": content[:160], "timestamp": timestamp})
                    continue

                if not content:
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
                thinking_parts = []
                tools = []
                for block in content_blocks:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") in ("thinking", "redacted_thinking"):
                            thinking_parts.append(block.get("thinking", ""))
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            tool_input = block.get("input", {})
                            _tid = block.get("id", "")
                            if _tid:
                                _tid_to_tool[_tid] = tool_name
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
                thinking = "\n\n".join(t for t in thinking_parts if t).strip()
                # thinking_parts is populated for every thinking block, even
                # signature-only ones. Modern models (Opus 4.7/4.8) return
                # encrypted thinking, so the text is empty: we still flag that
                # the turn reasoned, but only attach text when it exists.
                had_thinking = bool(thinking_parts)
                if not text and not tools and not thinking:
                    continue

                _amsg = {
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
                }
                if thinking:
                    _amsg["thinking"] = thinking[:8000]
                if had_thinking:
                    _amsg["thought"] = True
                messages.append(_amsg)

            elif msg_type == "progress":
                data_obj = obj.get("data", {})
                if data_obj.get("type") == "hook_progress":
                    messages.append({
                        "role": "hook",
                        "hook_event": data_obj.get("hookEvent", ""),
                        "hook_name": data_obj.get("hookName", ""),
                        "timestamp": timestamp,
                    })

            elif msg_type == "attachment":
                # type:"attachment" is overwhelmingly internal plumbing
                # (task_reminder, *_delta, skill_listing, *_effort_*, hook
                # results …), NOT user file/image uploads. Surface only the
                # few types that represent real content events; drop the rest.
                _att = obj.get("attachment", "")
                _atype = ""
                if isinstance(_att, dict):
                    _atype = str(_att.get("type", ""))
                else:
                    _s = str(_att)
                    if "'type':" in _s:
                        _atype = _s.split("'type':", 1)[1].split(",", 1)[0].strip(" '\"}")
                _EFFORT = {"ultra_effort_enter": "Ultra effort on",
                           "ultra_effort_exit": "Ultra effort off",
                           "ultrathink_effort": "Ultrathink"}
                _ATTACH_SHOW = {"edited_text_file": "Edited file",
                                "image": "Image", "file": "File",
                                "pasted_text": "Pasted text",
                                "pasted_contents": "Pasted content",
                                "selected_lines": "Selection"}
                if _atype in _EFFORT:
                    messages.append({"role": "effort", "content": _EFFORT[_atype], "timestamp": timestamp})
                elif _atype in _ATTACH_SHOW:
                    messages.append({"role": "attachment", "content": _ATTACH_SHOW[_atype], "timestamp": timestamp})

            elif msg_type == "mode":
                _mv = str(obj.get("mode", ""))
                if _mv and _mv != _last_mode:
                    _last_mode = _mv
                    messages.append({"role": "mode", "content": "Mode: " + _mv, "timestamp": timestamp})

            elif msg_type == "permission-mode":
                _pv = str(obj.get("permissionMode", ""))
                if _pv and _pv != _last_perm:
                    _last_perm = _pv
                    messages.append({"role": "mode", "content": "Permission: " + _pv, "timestamp": timestamp})

            elif msg_type == "queue-operation":
                _qc = str(obj.get("content", "")).strip()
                if _qc:
                    messages.append({
                        "role": "queue",
                        "content": (str(obj.get("operation", "queue")) + ": " + _qc)[:200],
                        "timestamp": timestamp,
                    })

    return messages


def generate_dashboard(data):
    """Generate self-contained HTML dashboard with embedded data."""
    data_json = json.dumps(data, ensure_ascii=False)
    # Same </script>-in-string protection as session pages: avoid premature
    # script-tag close when any embedded text contains "</...".
    data_json_inline = data_json.replace("</", "<\\/")

    if TEMPLATE_HTML.exists():
        with open(TEMPLATE_HTML, "r", encoding="utf-8") as f:
            template = f.read()
        html = template.replace("/*__DASHBOARD_DATA__*/", f"const DASHBOARD_DATA = {data_json_inline};")
        html = _inject_locale(html, LOCALE)
    else:
        html = build_inline_html(data_json_inline)

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


def _provision_custom_css(out_dir):
    """Copy custom.css.example to public/, and create empty custom.css if missing.

    The dashboard HTML links to a sibling `custom.css`. We always refresh
    the example so users see the latest set of overridable variables, but
    never overwrite a user-edited custom.css.
    """
    base_dir = Path(__file__).parent
    src_example = base_dir / "templates" / "custom.css.example"
    if src_example.exists():
        (out_dir / "custom.css.example").write_text(
            src_example.read_text(encoding="utf-8"), encoding="utf-8"
        )
    target = out_dir / "custom.css"
    if not target.exists():
        target.write_text(
            "/* Your custom CSS overrides. See custom.css.example for available variables. */\n",
            encoding="utf-8",
        )


def _font_face_css():
    """Inline the bundled fonts as @font-face rules with data URIs.

    The dashboard used to pull Manrope and JetBrains Mono from Google on
    every page load, which sends a request to a third party from a tool
    whose whole point is that the data stays local. Both families are OFL
    licensed, so they ship with the repo instead. Embedding them keeps the
    generated page self-contained: no extra files to copy when deploying.
    """
    import base64

    base_dir = Path(__file__).parent
    fonts = [
        ("Manrope", "Manrope[wght].woff2", "400 800"),
        ("JetBrains Mono", "JetBrainsMono[wght].woff2", "400 600"),
    ]
    rules = []
    for family, filename, weight_range in fonts:
        path = base_dir / "assets" / "fonts" / filename
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2-variations');"
            f"font-weight:{weight_range};font-style:normal;font-display:swap;}}"
        )
    return "".join(rules)


def _locale_script_tag():
    """Inline the locale as window.__LOCALE__ so bundled page/component JS
    can resolve UI strings at runtime. Must be emitted BEFORE the JS bundle.
    "</" is escaped so no embedded string can close the script tag early."""
    locale_json = json.dumps(LOCALE, ensure_ascii=False).replace("</", "<\\/")
    return f"<script>window.__LOCALE__ = {locale_json};</script>"


def _get_html_template():
    """Return the HTML template string with placeholders for data, styles, scripts."""
    base_dir = Path(__file__).parent
    html = (base_dir / "templates" / "dashboard.html").read_text(encoding="utf-8")
    css = (base_dir / "templates" / "dashboard.css").read_text(encoding="utf-8")
    js = (base_dir / "templates" / "dashboard.js").read_text(encoding="utf-8")
    table_css = (base_dir / "templates" / "components" / "session_table.css").read_text(encoding="utf-8")
    table_js = (base_dir / "templates" / "components" / "session_table.js").read_text(encoding="utf-8")
    filters_css = (base_dir / "templates" / "components" / "session_filters.css").read_text(encoding="utf-8")
    filters_js = (base_dir / "templates" / "components" / "session_filters.js").read_text(encoding="utf-8")
    shared_js = (base_dir / "templates" / "components" / "shared_helpers.js").read_text(encoding="utf-8")
    css = filters_css + "\n" + table_css + "\n" + css
    js = shared_js + "\n" + filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{_font_face_css()}{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"{_locale_script_tag()}\n<script>{js}</script>")
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
        # Embedded inside <script>...</script>: a literal "</script>" inside any
        # message text (e.g. when the user pastes HTML / discusses inline scripts)
        # would close the script tag prematurely and break the page. Escape the
        # boundary case; "<\/" is equivalent to "</" inside a JS string literal.
        session_json = session_json.replace("</", "<\\/")

        html = _get_session_html_template()
        html = html.replace('"__SESSION_DATA__"', session_json)
        flow_json = json.dumps(flow_data, ensure_ascii=False, separators=(',', ':'))
        flow_json = flow_json.replace("</", "<\\/")
        html = html.replace('"__FLOW_DATA__"', flow_json)
        html = html.replace('__VERSION__', VERSION)
        body_classes = "flow-hidden" if CONFIG.get("hide_session_flow", False) else ""
        html = html.replace('__BODY_CLASSES__', body_classes)

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
    shared_js = (base_dir / "templates" / "components" / "shared_helpers.js").read_text(encoding="utf-8")
    js = shared_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{_font_face_css()}{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"{_locale_script_tag()}\n<script>{js}</script>")
    # Locale tokens are resolved at template stage, BEFORE any session data
    # is inserted, so user text containing "__L_..." can never be rewritten.
    html = _inject_locale(html, LOCALE)
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
    table_css = (base_dir / "templates" / "components" / "session_table.css").read_text(encoding="utf-8")
    table_js = (base_dir / "templates" / "components" / "session_table.js").read_text(encoding="utf-8")
    filters_css = (base_dir / "templates" / "components" / "session_filters.css").read_text(encoding="utf-8")
    filters_js = (base_dir / "templates" / "components" / "session_filters.js").read_text(encoding="utf-8")
    shared_js = (base_dir / "templates" / "components" / "shared_helpers.js").read_text(encoding="utf-8")
    css = filters_css + "\n" + table_css + "\n" + css
    js = shared_js + "\n" + filters_js + "\n" + table_js + "\n" + js
    html = html.replace("<!-- STYLES -->", f"<style>{_font_face_css()}{css}</style>")
    html = html.replace("<!-- SCRIPTS -->", f"{_locale_script_tag()}\n<script>{js}</script>")
    # Same ordering rule as the session template: tokens before data.
    html = _inject_locale(html, LOCALE)
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

    _provision_custom_css(OUTPUT_DIR)

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

    # Idle-gap aggregate is computed client-side in dashboard.js
    # (recomputeIdleGapAggregate) from F.sessions, so it tracks the
    # active date-range filter. No Python-side precomputation.

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
