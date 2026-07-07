#!/usr/bin/env python3
"""
Claude Code Usage Statistics Extractor
Parses all Claude Code data sources and generates a dashboard.

Note: The generated HTML uses innerHTML for rendering trusted, locally-generated
data only. No external/untrusted input is rendered as HTML. All user-provided
text (prompts) is escaped via textContent before display.
"""

import calendar
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claudestats_core.pricing import (
    PRICING, DEFAULT_PRICING, _version, derive_model_display,
    get_model_display, pricing_for_display, resolve_pricing,
    build_pricing_warnings, calc_cost,
)

# ── Configuration ──────────────────────────────────────────────────────────
# Config-Override fuer hermetische Laeufe (Golden-Master, Server-Driver).
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
_WEEKDAY_BY_ANCHOR = {"mon": 0, "tue": 1, "wed": 2, "thu": 3,
                      "fri": 4, "sat": 5, "sun": 6}
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

VERSION = "0.8.2"

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

# Plan-recommendation constants (Task 4).
# Source: Anthropic pricing communication / docs page (Pro = 1×, Max 5x = 5×,
# Max 20x = 20×). Exact token limits are not published — these factors are
# rough relative-capacity estimates from Anthropic, not measurements.
PLAN_TIER_FACTORS = {"Pro": 1.0, "Max 5x": 5.0, "Max 20x": 20.0}

# Fallback Pro-tier capacity in USD-API-equivalent per billing cycle.
# Used only when no limit events are available for empirical calibration
# and no config override is set. Heavily disclaimed in the UI.
PRO_CAPACITY_USD_DEFAULT = 100.0


def _normalize_tier_name(raw):
    """Map user-config plan strings to PLAN_TIER_FACTORS keys."""
    if not raw:
        return None
    s = str(raw).lower().strip()
    s = s.replace("(annual)", "").strip()
    if s in ("pro", "pro plan"):
        return "Pro"
    s_compact = s.replace(" ", "")
    if s_compact in ("max5x", "5x", "max-5x"):
        return "Max 5x"
    if s_compact in ("max20x", "20x", "max-20x"):
        return "Max 20x"
    return None


FIVE_HOUR_MS = 5 * 60 * 60 * 1000


def _compute_5h_windows(turns):
    """Group chronological per-turn data into Anthropic 5h-session windows.

    A 5h-window opens with the first turn after the previous window closes,
    and stays open for 5h. Any turn within that 5h is part of the same
    window — matches Claude Code's actual session-limit semantics. Returns
    a list of {start_ts, end_ts, cost, turn_count, session_ids} dicts.
    """
    if not turns:
        return []
    sorted_turns = sorted(turns, key=lambda t: t.get("ts", 0))
    windows = []
    current = None
    for t in sorted_turns:
        ts = t.get("ts")
        if ts is None:
            continue
        if current is None or ts >= current["start_ts"] + FIVE_HOUR_MS:
            if current is not None:
                windows.append(current)
            current = {
                "start_ts": ts,
                "end_ts": ts,
                "cost": 0.0,
                "turn_count": 0,
                "session_ids": set(),
            }
        current["end_ts"] = ts
        current["cost"] += t.get("cost", 0.0)
        current["turn_count"] += 1
        sid = t.get("session_id")
        if sid:
            current["session_ids"].add(sid)
    if current is not None:
        windows.append(current)
    # Convert session_ids set to sorted list for JSON-friendliness.
    for w in windows:
        w["session_ids"] = sorted(w["session_ids"])
    return windows


def _compute_weekly_buckets(turns, anchor_weekday=None):
    """Group chronological per-turn data into calendar weeks starting on
    the configured anchor weekday (config.json "week_anchor", default
    Monday).

    Returns a list of {week_key, week_start_ts, week_end_ts, cost,
    turn_count, session_ids} dicts sorted by week_start_ts. week_key is
    the ISO date (YYYY-MM-DD, UTC) of the week's first day."""
    if anchor_weekday is None:
        anchor_weekday = _WEEKDAY_BY_ANCHOR[WEEK_ANCHOR]
    if not turns:
        return []
    buckets = {}
    for t in turns:
        ts = t.get("ts")
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        week_start = (dt - timedelta(days=(dt.weekday() - anchor_weekday) % 7)
                      ).replace(hour=0, minute=0, second=0, microsecond=0)
        key = week_start.strftime("%Y-%m-%d")
        if key not in buckets:
            buckets[key] = {
                "week_key": key,
                "week_start_ts": int(week_start.timestamp() * 1000),
                "week_end_ts": int(week_start.timestamp() * 1000)
                               + 7 * 24 * 3600 * 1000 - 1,
                "cost": 0.0,
                "turn_count": 0,
                "session_ids": set(),
            }
        b = buckets[key]
        b["cost"] += t.get("cost", 0.0)
        b["turn_count"] += 1
        sid = t.get("session_id")
        if sid:
            b["session_ids"].add(sid)
    for b in buckets.values():
        b["session_ids"] = sorted(b["session_ids"])
    return sorted(buckets.values(), key=lambda b: b["week_start_ts"])


def _estimate_5h_window_cap_usd(windows, limit_event_window_ids,
                                 cycle_tier_by_window_id, override_pro):
    """Estimate per-tier 5h-window cap from windows that hit a limit event.

    Each limit-hit window's cost ≈ 100% of the cap on the tier that was
    active during that window. Normalise to a Pro baseline by dividing by
    that tier's factor (1.0 for Pro, 5.0 for Max 5x, 20.0 for Max 20x),
    take the median across all limit-hit windows, then scale. The result
    is floored at the most expensive limit-event-free window per tier
    (normalised to Pro), since the true cap cannot be below a cost that
    was actually reached without a cutoff.

    override_pro: USD per Pro-tier 5h-window (config override)
    cycle_tier_by_window_id: window_index → normalized tier name (or None)
    limit_event_window_ids: set of window indices that contain a limit event
    """
    if override_pro is not None and override_pro > 0:
        base = float(override_pro)
        source = "config_override"
        anchors = []
    else:
        anchors = []
        for idx in limit_event_window_ids:
            if idx >= len(windows):
                continue
            w = windows[idx]
            tier = cycle_tier_by_window_id.get(idx)
            factor = PLAN_TIER_FACTORS.get(tier)
            if not factor or w["cost"] <= 0:
                continue
            anchors.append(w["cost"] / factor)
        if anchors:
            base = statistics.median(anchors)
            source = "empirical"
        else:
            base = PRO_CAPACITY_USD_DEFAULT
            source = "default"

    # Plausibility floor: the true cap on tier T is at least the cost of
    # the most expensive window on T that did NOT contain a limit event --
    # had it been over the cap, it would have been cut off. Anchors biased
    # low (resume-side windows, misaligned window starts) would otherwise
    # produce caps the observed data already refutes. A config override is
    # authoritative and never floored.
    floor_pro = 0.0
    for i, w in enumerate(windows):
        if i in limit_event_window_ids:
            continue
        tier = cycle_tier_by_window_id.get(i)
        factor = PLAN_TIER_FACTORS.get(tier)
        if not factor or w["cost"] <= 0:
            continue
        floor_pro = max(floor_pro, w["cost"] / factor)
    floor_applied = False
    if source != "config_override" and floor_pro > base:
        base = floor_pro
        floor_applied = True

    caps = {t: round(base * f, 2) for t, f in PLAN_TIER_FACTORS.items()}
    return {
        "caps_per_window": caps,
        "base_pro_per_window_usd": round(base, 2),
        "anchor_window_count": len(anchors),
        "source": source,
        "floor_pro_per_window_usd": round(floor_pro, 2),
        "floor_applied": floor_applied,
    }


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


WRITE_CATEGORIES = (
    "screen_text",            # text in turns with NO tool_use — final answers / pure explanations
    "screen_text_narration",  # text in turns WITH tool_use — "let me check…" inter-tool narration
    "thinking",
    "file_writes",
    "bash_commands",
    "tool_inputs",
)
_FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _block_weight(block):
    """Approximate char-count of model-generated payload for one content block.

    Used as a proportional weight to split a message's output_tokens across blocks.
    Tool-use blocks include the tool name + compact JSON of input parameters,
    since both are emitted by the model.
    """
    if not isinstance(block, dict):
        return 0
    btype = block.get("type")
    if btype == "text":
        return len(block.get("text") or "")
    if btype == "thinking":
        return len(block.get("thinking") or "")
    if btype == "tool_use":
        name = block.get("name") or ""
        inp = block.get("input")
        try:
            payload = json.dumps(inp, ensure_ascii=False, separators=(",", ":")) if inp is not None else ""
        except (TypeError, ValueError):
            payload = str(inp) if inp is not None else ""
        return len(name) + len(payload)
    return 0


def _block_category(block, turn_has_tools):
    """Map a content block to one of WRITE_CATEGORIES, or None if it doesn't generate tokens.

    `turn_has_tools` distinguishes a text block in a tool-using turn (narration
    between tool calls, visible to user) from a text block in a pure-text turn
    (final answer / explanation).
    """
    if not isinstance(block, dict):
        return None
    btype = block.get("type")
    if btype == "text":
        return "screen_text_narration" if turn_has_tools else "screen_text"
    if btype == "thinking":
        return "thinking"
    if btype == "tool_use":
        name = block.get("name") or ""
        if name in _FILE_WRITE_TOOLS:
            return "file_writes"
        if name == "Bash":
            return "bash_commands"
        return "tool_inputs"
    return None


def attribute_write_categories(content_blocks, output_tokens):
    """Split a turn's output_tokens across write categories by char-weight heuristic.

    Heuristic: each content block contributes a weight equal to the char-count
    of the payload the model had to generate (text body, thinking body, or
    tool name + JSON of input). The message's output_tokens are distributed
    proportionally; rounding remainder goes to the last non-zero bucket so
    totals reconcile exactly.
    """
    result = {cat: 0 for cat in WRITE_CATEGORIES}
    if not output_tokens or not content_blocks:
        return result

    turn_has_tools = any(
        isinstance(b, dict) and b.get("type") == "tool_use"
        for b in content_blocks
    )

    per_block = []
    total_weight = 0
    for block in content_blocks:
        cat = _block_category(block, turn_has_tools)
        if cat is None:
            continue
        w = _block_weight(block)
        if w <= 0:
            continue
        per_block.append((cat, w))
        total_weight += w

    if total_weight <= 0:
        # No measurable payload — dump everything into screen_text as a safe fallback.
        result["screen_text"] = output_tokens
        return result

    allocated = 0
    last_idx = len(per_block) - 1
    for i, (cat, w) in enumerate(per_block):
        if i < last_idx:
            tokens = int(round(output_tokens * w / total_weight))
        else:
            tokens = output_tokens - allocated
        result[cat] += tokens
        allocated += tokens
    return result


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


# Empirically derived from real Claude Code JSONLs: only these phrases
# uniquely indicate a USER-plan rate-limit hit (vs auth, server overload,
# network, invalid request). Used by the isApiErrorMessage-driven
# limit-event detection — see _is_user_plan_limit_text().
_USER_PLAN_LIMIT_SIGNALS = (
    "you've hit your limit",         # Claude Code 5h-session cap banner
    "hit your org's monthly usage",  # Weekly/monthly org cap
    "usage limit reached",
    "plan limit reached",
    "rate limit reached",            # "API Error: Rate limit reached"
)


def _is_user_plan_limit_text(text: str) -> bool:
    """True iff an API-error message clearly indicates a user / plan
    rate-limit. Distinguishes from auth / server-overload / network errors
    that Claude Code also reports via isApiErrorMessage."""
    t = (text or "").lower()
    return any(needle in t for needle in _USER_PLAN_LIMIT_SIGNALS)


# Categories a type:"user" transcript entry can fall into. Only "prompt"
# is a message the person actually typed; the rest are synthetic entries
# Claude Code emits on the "user" channel. Tracked as separate metrics.
USER_ENTRY_CATEGORIES = ("prompt", "tool_result", "command", "interrupt", "meta")


def _classify_user_entry(obj: dict) -> str:
    """Classify a type:"user" transcript entry into one of
    USER_ENTRY_CATEGORIES. Precedence: tool_result > command > interrupt >
    meta > prompt. Claude Code records tool_result blocks on the "user"
    channel, and emits slash-command / interrupt / meta wrappers as user
    entries too; none of those are messages the person actually typed.
    Mirrors the per-session chat transcript filter (which is why the
    session detail page already shows only real prompts)."""
    # Compaction summaries arrive as type:"user" with a plain-string body;
    # they are a synthetic continuation note, counted via `compactions`.
    if obj.get("isCompactSummary"):
        return "meta"
    content = obj.get("message", {}).get("content", "")
    if isinstance(content, list):
        # tool_result blocks are delivered on the user channel
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return "tool_result"
        text = next((b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"), "")
    elif isinstance(content, str):
        text = content
    else:
        text = ""
    text = text.strip()
    if text.startswith("<command") or text.startswith("<local-command"):
        return "command"
    if text.startswith("[Request interrupted"):
        return "interrupt"
    if obj.get("isMeta"):
        return "meta"
    if not text:
        # empty, non-tool-result user entry (e.g. attachment-only) — not a
        # typed prompt; bucket with meta rather than inflating the count
        return "meta"
    return "prompt"


def _merge_model_buckets(dst: dict, src: dict) -> None:
    """Add every per-model token/cost/call bucket in `src` into `dst`
    (summing numeric fields). Used to fold a subagent session's usage into
    its parent so headline totals (cost, tokens, per-model) reflect true
    API spend. `src` is left unchanged."""
    for model, sb in src.items():
        db = dst[model]
        for key, val in sb.items():
            if isinstance(val, (int, float)):
                db[key] = db.get(key, 0) + val


def _absorb_subagent(parent, sub, sub_type="", sub_desc=""):
    """Fold a subagent session's API usage into its parent session.

    Appends a per-subagent summary entry to parent["subagents"] and merges
    the subagent's model buckets (session totals and per-day) into the
    parent. The subagent's turns live only in its own transcript file, so
    this counts each turn exactly once. The caller removes the subagent
    from the top-level sessions dict afterwards."""
    sub_tokens = sum(m["input_tokens"] + m["output_tokens"]
                     for m in sub["models"].values())
    sub_cost = sum(m["cost"] for m in sub["models"].values())
    parent["subagents"].append({
        "agent_id": sub["session_id"],
        "type": sub_type,
        "description": sub_desc,
        "tokens": sub_tokens,
        "cost": round(sub_cost, 4),
        "messages": sub["message_count"],
        "tools": dict(sub["tools"]),
    })
    _merge_model_buckets(parent["models"], sub["models"])
    for day, mdict in sub.get("daily_models", {}).items():
        _merge_model_buckets(parent["daily_models"][day], mdict)


def _link_subagents(sessions):
    """Attach every subagent session to its parent and absorb its usage.

    Subagents whose parent transcript is missing (cleaned up by
    cleanupPeriodDays or never parsed) are KEPT as standalone sessions:
    deleting them would silently drop their tokens and cost from every
    total. Returns the orphan count."""
    subagent_ids = [sid for sid, s in sessions.items() if s.get("is_subagent")]
    orphan_count = 0
    for sub_id in subagent_ids:
        sub = sessions[sub_id]
        parent_id = sub.get("parent_session_id", "")
        if not (parent_id and parent_id in sessions):
            orphan_count += 1
            continue
        parent = sessions[parent_id]
        sub_agent_id = sub.get("agent_id", "")
        # Resolve subagent type: primary = meta.json on disk, secondary =
        # matching dispatch in parent
        sub_type = sub.get("agent_type", "")
        sub_desc = sub.get("agent_description", "")
        if not sub_type and sub_agent_id:
            for ad in parent.get("agent_dispatches", []):
                if ad.get("agent_id") == sub_agent_id:
                    sub_type = ad.get("type", "")
                    if not sub_desc:
                        sub_desc = ad.get("description", "")
                    break
        # Still no type? Insert synthetic dispatch so aggregation counts
        # the spawn once.
        if not sub_type:
            sub_type = "<unlinked>"
            parent.setdefault("agent_dispatches", []).append({
                "type": "<unlinked>",
                "description": sub_desc,
                "tool_use_id": "",
                "agent_id": sub_agent_id,
            })
        elif sub_agent_id:
            # We have a type but did the parent dispatch get linked? If not,
            # backfill agent_id on the first matching dispatch by type that's
            # still unlinked.
            for ad in parent.get("agent_dispatches", []):
                if ad.get("agent_id"):
                    continue
                if ad.get("type") == sub_type:
                    ad["agent_id"] = sub_agent_id
                    break
        _absorb_subagent(parent, sub, sub_type, sub_desc)
        del sessions[sub_id]
    if orphan_count:
        print(f"  WARNING: {orphan_count} subagent session(s) have no reachable "
              f"parent transcript; keeping them as standalone sessions so "
              f"their tokens and cost still count.")
    return orphan_count


_DAILY_FIELDS = (
    "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens",
    "cost", "calls",
)


def _day_from_ms(ms: int) -> str:
    """UTC calendar day (YYYY-MM-DD) for an epoch-millisecond timestamp."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def split_session_by_day(daily_models, model_totals,
                         daily_message_count, total_message_count,
                         start_day):
    """Distribute one session's per-model spend and message count across the
    days they actually occurred.

    `daily_models[day][model]` and `daily_message_count[day]` hold the share
    that carried a parseable per-message timestamp. Any remainder (turns/
    messages whose timestamp could not be parsed) is dumped on `start_day`, so
    the returned per-day values reconcile EXACTLY with the session totals
    (`model_totals`, `total_message_count`).

    Returns `(per_day_models, per_day_messages)` where
    `per_day_models[day][model]` is a fresh bucket dict (raw model keys; the
    caller maps to display names) and `per_day_messages[day]` is an int.
    """
    per_day_models = {}
    attributed = defaultdict(lambda: {k: 0 for k in _DAILY_FIELDS})
    for day, mdict in daily_models.items():
        day_out = per_day_models.setdefault(day, {})
        for model, b in mdict.items():
            dst = day_out.setdefault(model, {k: 0 for k in _DAILY_FIELDS})
            for k in _DAILY_FIELDS:
                v = b.get(k, 0)
                dst[k] += v
                attributed[model][k] += v

    for model, tb in model_totals.items():
        remainder = {k: tb.get(k, 0) - attributed[model].get(k, 0)
                     for k in _DAILY_FIELDS}
        if remainder["cost"] < 0:
            remainder["cost"] = 0.0
        _int_left = (remainder["input_tokens"] or remainder["output_tokens"]
                     or remainder["cache_read_input_tokens"]
                     or remainder["cache_creation_input_tokens"]
                     or remainder["calls"])
        if _int_left or remainder["cost"] > 1e-6:
            dst = per_day_models.setdefault(start_day, {}).setdefault(
                model, {k: 0 for k in _DAILY_FIELDS})
            for k in _DAILY_FIELDS:
                dst[k] += remainder[k]

    per_day_messages = dict(daily_message_count)
    remainder_msgs = total_message_count - sum(per_day_messages.values())
    if remainder_msgs:
        per_day_messages[start_day] = per_day_messages.get(start_day, 0) + remainder_msgs

    return per_day_models, per_day_messages


def _merge_streamed_assistant_entries(entries: list) -> list:
    """Collapse stream-split assistant rows back into one entry per API
    response.

    Claude Code writes ONE JSONL line per assistant content block
    (thinking / text / each tool_use). Every line of a single response
    shares the same message.id and repeats the identical final `usage`
    object. Counting per line therefore multiplies tokens / cost / calls /
    message counts by the number of content blocks. We merge consecutive
    assistant lines with the same message.id into a single entry (content
    blocks concatenated, usage/timestamp/uuid kept from the first line) so
    downstream accounting sees one response = one entry, exactly once.

    message.id is globally unique per API response, so all rows of one
    response are merged into the single entry at its first occurrence — even
    when they are NOT consecutive. Agentic turns interleave one response's
    tool_use rows with the tool_result (type:"user") rows that come back, so
    the same message.id can recur dozens of times spread across the
    transcript; consecutive-only merging would miss those. Assistant entries
    without a message.id (rare) and the older one-line-per-response format
    both pass through unchanged. The input list is not mutated; interleaved
    non-assistant entries keep their position."""
    merged = []
    targets = {}        # message.id -> the merge-target entry in `merged`
    for e in entries:
        if not isinstance(e, dict) or e.get("type") != "assistant":
            merged.append(e)
            continue
        mid = (e.get("message") or {}).get("id")
        if mid and mid in targets:
            targets[mid]["message"]["content"].extend(
                (e.get("message") or {}).get("content", []) or []
            )
            continue
        # first sighting of this response: shallow-copy so input stays intact
        copy = dict(e)
        msg = dict(e.get("message") or {})
        msg["content"] = list(msg.get("content", []) or [])
        copy["message"] = msg
        merged.append(copy)
        if mid:
            targets[mid] = copy
    return merged


def _classify_tool_error(msg: str, tool_name: str) -> tuple:
    """Classify a tool_result `is_error` payload into (source, category).

    source is one of: "user" (the person declined / a parallel sibling was
    cancelled — NOT a failure), "hook" (a PreToolUse/PostToolUse hook
    failed), or "tool" (the tool call genuinely failed).

    Deliberately does NOT recognise backend categories (rate_limit /
    server_overload): those keywords routinely appear *inside* a tool's own
    stdout/stderr (test output, code being edited, tracebacks) and matching
    them here miscategorises ordinary tool failures as API rate-limits.
    Genuine backend errors arrive on the isApiErrorMessage channel and are
    classified by _classify_api_error()."""
    m = msg.lower()
    # user-driven, not failures
    if "cancelled:" in m or "canceled:" in m or "parallel tool call" in m:
        return ("user", "cancelled")
    if ("doesn't want to proceed" in m or "does not want to proceed" in m
            or "tool use was rejected" in m or "user rejected" in m):
        return ("user", "rejected")
    # hook failures
    if "hook error" in m or "hook_error" in m:
        return ("hook", "hook_error")
    # genuine tool failures
    if "no replacement was performed" in m or "old_string not found" in m \
            or "string to replace not found" in m:
        cat = "edit_no_match"
    elif "not unique" in m or "multiple occurrences" in m or "matches of the string" in m:
        cat = "edit_not_unique"
    elif ("has not been read yet" in m or "has been modified since read" in m):
        cat = "stale_read"
    elif "does not exist" in m or "no such file" in m or ("not found" in m and "command not found" not in m):
        cat = "file_not_found"
    elif "command not found" in m:
        cat = "command_not_found"
    elif "permission" in m or "denied" in m:
        cat = "permission_denied"
    elif "timeout" in m or "timed out" in m:
        cat = "timeout"
    elif "syntaxerror" in m or "syntax error" in m:
        cat = "syntax_error"
    elif "importerror" in m or "modulenotfounderror" in m:
        cat = "import_error"
    elif "exit code" in m or "returned non-zero" in m:
        cat = "exit_code"
    elif tool_name == "Edit":
        cat = "edit_failed"
    else:
        cat = "other"
    return ("tool", cat)


_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _clean_error_text(s) -> str:
    """Make a raw tool-error payload readable: strip ANSI escape sequences
    (color/cursor codes that Bash output carries) and carriage returns, and
    trim trailing whitespace. Newlines are preserved."""
    if not s:
        return ""
    s = _ANSI_CSI_RE.sub("", str(s))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.rstrip()


def _route_tool_error(source: str, category: str):
    """Decide how a classified tool error is accounted. Returns the source
    label to count it under, or None if it is NOT a real error.

    A cancelled parallel-call sibling is not a failure (-> None, tracked as
    cancelled_count). A user rejection DOES count as an error under its own
    "rejected" source. Genuine tool / hook / backend failures keep their
    source."""
    if source == "user":
        if category == "cancelled":
            return None
        return "rejected"
    return source


def _extract_command_label(text: str) -> str:
    """Pull a readable slash-command label out of a `<command-name>` wrapper.
    Returns "" for command *output* (`<local-command-stdout>`) or plain text,
    so only genuine invocations become chat markers."""
    if "<command-name>" not in text:
        return ""
    name = text.split("<command-name>", 1)[1].split("</command-name>", 1)[0].strip()
    if not name:
        return ""
    if not name.startswith("/"):
        name = "/" + name
    args = ""
    if "<command-args>" in text:
        args = text.split("<command-args>", 1)[1].split("</command-args>", 1)[0].strip()
    return (name + " " + args).strip()


def _classify_api_error(text: str) -> str:
    """Categorise an isApiErrorMessage payload (always source "backend")."""
    t = (text or "").lower()
    if ("hit your limit" in t or "usage limit" in t or "rate limit" in t
            or "rate_limit_error" in t or re.search(r"\b429\b", t)):
        return "rate_limit"
    if "overloaded" in t or re.search(r"\b529\b", t):
        return "server_overload"
    if ("authentication" in t or "run /login" in t or re.search(r"\b401\b", t)
            or "invalid authentication" in t):
        return "auth"
    if (re.search(r"\b5\d\d\b", t) or "internal server error" in t
            or "bad gateway" in t or "server-side issue" in t):
        return "server_error"
    if ("idle timeout" in t or "socket" in t or "connection was closed" in t
            or "timed out" in t or "timeout" in t):
        return "connection"
    if "content filtering" in t or "content filter" in t:
        return "content_filter"
    if ("prompt is too long" in t or "too long" in t or "invalid_request" in t
            or re.search(r"\b400\b", t) or "could not process" in t):
        return "invalid_request"
    return "other"


# The standard context window caps the prompt at ~200k tokens. Any assistant
# turn whose prompt context exceeds this provably ran with the 1M-context window
# enabled, so we use it as the detection boundary (strictly greater).
CONTEXT_1M_THRESHOLD = 200_000


def summarize_context_window(turns: list[dict], threshold: int = CONTEXT_1M_THRESHOLD) -> dict:
    """Detect whether (and when) a session used the 1M-context window.

    Per-turn prompt context = input + cache_read + cache_creation. The standard
    window caps that at ~200k tokens, so a turn over the threshold can only have
    run with 1M enabled. This measures the *actual* context reached, not the
    setting: a session that enabled 1M but stayed under 200k is not flagged.

    Returns {"peak_context_tokens", "used_1m_context", "first_1m_at"} where
    first_1m_at is the timestamp of the chronologically earliest over-threshold
    turn (or None if the window was never exceeded).
    """
    peak = 0
    first_1m_at = None
    for t in turns:
        ctx = (t.get("input", 0) or 0) + (t.get("cache_read", 0) or 0) + (t.get("cache_creation", 0) or 0)
        if ctx > peak:
            peak = ctx
        if ctx > threshold:
            ts = t.get("timestamp")
            if ts is not None and (first_1m_at is None or ts < first_1m_at):
                first_1m_at = ts
    return {
        "peak_context_tokens": peak,
        "used_1m_context": peak > threshold,
        "first_1m_at": first_1m_at,
    }


def _detect_cache_flushes(turns: list[dict], has_1h_cache: bool,
                          compaction_ts_ms: list[int] | None = None) -> dict:
    """Gap-based + no-gap cache-flush detection in one pass.

    Gap flush (TTL victim) - unchanged semantics:
      1. Cache was previously established (post-buildup phase)
      2. Gap since previous turn exceeds the active cache TTL
      3. Turn's cache_creation > 2x rolling median of post-buildup
         cache_creation values (floor: 100 tokens)

    No-gap flush (anomaly; e.g. the 2026 Claude Code mid-work
    invalidation bugs): conditions 1+3, but the gap is BELOW the TTL
    and the turn's cache_read collapses to under 50% of the previous
    turn's - the cache was rebuilt although it cannot have expired.
    nogap_rewrite_tokens sums the cache_creation of those turns.
    Turns within 120s of a compaction event are excluded from the
    no-gap classification - compaction legitimately rebuilds the cache.
    """
    result = {"gap_flushes": 0, "nogap_flushes": 0, "nogap_rewrite_tokens": 0}
    if len(turns) < 3:
        return result

    gap_threshold_ms = (3600 if has_1h_cache else 300) * 1000
    sorted_turns = sorted(turns, key=lambda t: t["ts"])

    buildup_over = False
    creation_history: list[int] = []

    for i, t in enumerate(sorted_turns):
        prev = sorted_turns[i - 1] if i > 0 else None

        if (not buildup_over
                and t["cache_read"] > t["cache_creation"]
                and t["cache_read"] > 0):
            buildup_over = True
            continue

        if not buildup_over:
            continue

        if t["cache_creation"] > 0:
            creation_history.append(t["cache_creation"])

        if not prev:
            continue
        if len(creation_history) < 3:
            continue
        median = statistics.median(creation_history[:-1])
        if t["cache_creation"] <= 2 * max(median, 100):
            continue

        gap_ms = t["ts"] - prev["ts"]
        if gap_ms >= gap_threshold_ms:
            result["gap_flushes"] += 1
        elif prev["cache_read"] > 0 and t["cache_read"] < 0.5 * prev["cache_read"]:
            near_compaction = any(
                abs(t["ts"] - c) < 120_000 for c in (compaction_ts_ms or [])
            )
            if not near_compaction:
                result["nogap_flushes"] += 1
                result["nogap_rewrite_tokens"] += t["cache_creation"]

    return result


def _compute_idle_gap_summary(turns: list[dict]) -> dict | None:
    """Classify per-turn gaps into short/mid/long buckets and estimate
    overspend from lost cache-warmth.

    Returns None for sessions with <2 turns (no gap possible).
    """
    if len(turns) < 2:
        return None

    sorted_turns = sorted(turns, key=lambda t: t["ts"])
    buckets = {
        "short": {"count": 0, "cache_creation_tokens": 0, "values": []},
        "mid":   {"count": 0, "cache_creation_tokens": 0, "values": []},
        "long":  {"count": 0, "cache_creation_tokens": 0, "values": []},
    }

    for i in range(1, len(sorted_turns)):
        gap_sec = (sorted_turns[i]["ts"] - sorted_turns[i - 1]["ts"]) / 1000
        cc = sorted_turns[i]["cache_creation"]
        if gap_sec < 300:
            bucket = "short"
        elif gap_sec < 3600:
            bucket = "mid"
        else:
            bucket = "long"
        buckets[bucket]["count"] += 1
        buckets[bucket]["cache_creation_tokens"] += cc
        buckets[bucket]["values"].append(cc)

    if buckets["short"]["values"]:
        baseline = int(statistics.median(buckets["short"]["values"]))
    else:
        all_ccs = [t["cache_creation"] for t in sorted_turns if t["cache_creation"] > 0]
        baseline = int(statistics.median(all_ccs)) if all_ccs else 0

    overspend = 0
    for bucket_name in ("mid", "long"):
        for cc in buckets[bucket_name]["values"]:
            overspend += max(0, cc - baseline)

    total_cc = sum(t["cache_creation"] for t in sorted_turns)
    overspend_pct = round(100 * overspend / total_cc) if total_cc > 0 else 0

    for b in buckets.values():
        b.pop("values", None)

    return {
        "short": buckets["short"],
        "mid": buckets["mid"],
        "long": buckets["long"],
        "estimated_overspend_tokens": overspend,
        "estimated_overspend_pct_of_session": overspend_pct,
        "baseline_per_turn_tokens": baseline,
    }


# 5h-fingerprint heuristic for Anthropic plan-tier rate limits.
LIMIT_5H_GAP_MIN_SEC = 4 * 3600 + 45 * 60   # 4h45m
LIMIT_5H_GAP_MAX_SEC = 5 * 3600 + 30 * 60   # 5h30m
LIMIT_5H_RESET_TOLERANCE_SEC = 15 * 60      # ±15 min around the 5h anchor
LIMIT_5H_ACTIVE_WINDOW_SEC = 2 * 3600       # active-prefix lookback
LIMIT_5H_DAY_START_HOUR = 7                 # local time
LIMIT_5H_DAY_END_HOUR = 22                  # local time


def _detect_5h_fingerprint_events(prompts: list[dict]) -> list[dict]:
    """Detect 5h-rate-limit fingerprints in a chronological list of user prompts.

    prompts: [{"timestamp": ISO8601 str, "session_id": str}, ...]
    Returns events sorted by timestamp.
    """
    if len(prompts) < 2:
        return []

    parsed: list[tuple[datetime, str]] = []
    for p in prompts:
        ts = p.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed.append((dt, p.get("session_id", "")))
        except (ValueError, TypeError):
            continue
    parsed.sort(key=lambda x: x[0])

    events = []
    for i in range(1, len(parsed)):
        t_a, _ = parsed[i - 1]
        t_b, sid_b = parsed[i]
        gap_sec = (t_b - t_a).total_seconds()
        if not (LIMIT_5H_GAP_MIN_SEC <= gap_sec <= LIMIT_5H_GAP_MAX_SEC):
            continue

        active_prefix = any(
            t_a - timedelta(seconds=LIMIT_5H_ACTIVE_WINDOW_SEC) <= parsed[j][0] < t_a
            for j in range(i - 1)
        )
        if not active_prefix:
            continue

        t_a_local = t_a.astimezone()
        t_b_local = t_b.astimezone()
        in_day = (LIMIT_5H_DAY_START_HOUR <= t_a_local.hour <= LIMIT_5H_DAY_END_HOUR
                  and LIMIT_5H_DAY_START_HOUR <= t_b_local.hour <= LIMIT_5H_DAY_END_HOUR)

        anchor = t_a + timedelta(hours=5)
        aligned = abs((t_b - anchor).total_seconds()) <= LIMIT_5H_RESET_TOLERANCE_SEC

        confidence = "high" if (in_day and aligned) else "medium"
        events.append({
            "type": "heuristic",
            "subtype": "5h_fingerprint",
            "timestamp": t_b.isoformat(),
            "gap_start": t_a.isoformat(),
            "gap_end": t_b.isoformat(),
            "session_id": sid_b,
            "confidence": confidence,
        })

    return events


LIMIT_EVENT_CLUSTER_SEC = 15 * 60  # events closer than this describe one limit hit


def _iso_to_ms(s):
    """ISO-8601 string → epoch ms, or None if unparseable."""
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OSError, AttributeError, TypeError):
        return None


def _dedupe_limit_events(events):
    """Collapse limit events that describe the same underlying limit hit.

    Parallel sessions surface the same banner within seconds of each other,
    and retries repeat it minutes later. Sorted by time, an event merges
    into the current cluster when it is within LIMIT_EVENT_CLUSTER_SEC of
    the cluster's last event; the earliest event represents the cluster and
    `merged_count` records how many raw events it absorbed. Events without
    a parseable timestamp are kept unmerged at the end.
    """
    parsed, rest = [], []
    for ev in events:
        ms = _iso_to_ms(ev.get("timestamp"))
        if ms is None:
            rest.append(ev)
        else:
            parsed.append((ms, ev))
    parsed.sort(key=lambda x: x[0])
    deduped = []
    last_ms = None
    for ms, ev in parsed:
        if last_ms is not None and ms - last_ms <= LIMIT_EVENT_CLUSTER_SEC * 1000:
            deduped[-1]["merged_count"] += 1
        else:
            ev = dict(ev)
            ev["merged_count"] = 1
            deduped.append(ev)
        last_ms = ms
    return deduped + rest


def _match_limit_events_to_windows(events, windows):
    """Map limit events to the 5h-window that actually hit the cap.

    Fingerprint events carry the resume time in `timestamp`/`gap_end`; the
    limited window is the one containing the last activity BEFORE the gap
    (`gap_start`). Explicit banner events fire inside the limited window
    but AFTER its last assistant turn, so match against the full
    [start, start+5h) span rather than [start, last-turn]. Returns the set
    of matched window indices.
    """
    matched = set()
    for ev in events:
        if ev.get("subtype") == "5h_fingerprint":
            ev_ms = _iso_to_ms(ev.get("gap_start"))
        else:
            ev_ms = _iso_to_ms(ev.get("timestamp"))
        if ev_ms is None:
            continue
        for i, w in enumerate(windows):
            if w["start_ts"] <= ev_ms < w["start_ts"] + FIVE_HOUR_MS:
                matched.add(i)
                break
    return matched


def _count_5h_hits(indexed_windows, caps, tier_by_idx, anchor_ids):
    """Per-tier hit counts for a list of (window_index, window) pairs.

    A window counts as a hit for tier U when its cost exceeds U's cap, OR
    when it contains a detected limit event and U is not above the tier
    that was active -- a real hit on the active tier is by definition also
    a hit on every cheaper tier, regardless of what the USD proxy says.
    """
    hits = {}
    for tier, cap in caps.items():
        n = 0
        for i, w in indexed_windows:
            active = tier_by_idx.get(i)
            anchored = (i in anchor_ids and active in PLAN_TIER_FACTORS
                        and tier in PLAN_TIER_FACTORS
                        and PLAN_TIER_FACTORS[tier] <= PLAN_TIER_FACTORS[active])
            if anchored or (cap > 0 and w["cost"] > cap):
                n += 1
        hits[tier] = n
    return hits


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
                sub_agent_id = ""
                sub_agent_type = ""
                sub_agent_desc = ""
                if is_subagent:
                    parent_id = jsonl_file.parent.parent.name
                    # File stem: "agent-XXXXXXX" -> extract bare id "XXXXXXX"
                    if file_session_id.startswith("agent-"):
                        sub_agent_id = file_session_id[len("agent-"):]
                    # Sidecar meta.json: {"agentType": "...", "description": "..."}
                    meta_path = jsonl_file.with_suffix(".meta.json")
                    try:
                        if sudo_user:
                            _mc = sudo_read_text(meta_path, sudo_user)
                            if _mc:
                                _mj = json.loads(_mc)
                                sub_agent_type = _mj.get("agentType", "") or ""
                                sub_agent_desc = _mj.get("description", "") or ""
                        elif meta_path.exists():
                            with open(meta_path, "r", encoding="utf-8", errors="replace") as _mf:
                                _mj = json.load(_mf)
                            sub_agent_type = _mj.get("agentType", "") or ""
                            sub_agent_desc = _mj.get("description", "") or ""
                    except (OSError, json.JSONDecodeError):
                        pass

                # Skip if this session was already parsed from an earlier
                # source pass (migration, another additional source, or the
                # primary dir). First seen wins: parsing the same transcript
                # again would double count every token and cost.
                if file_session_id in sessions:
                    _prev_src = sessions[file_session_id].get("source", SOURCE_LABEL)
                    if _prev_src != source_label:
                        print(f"      NOTE: {file_session_id} already parsed from "
                              f"source '{_prev_src}'; skipping duplicate in "
                              f"'{source_label}'")
                    continue

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

                    # Collapse stream-split assistant rows (Claude Code writes
                    # one JSONL line per content block, each repeating the same
                    # usage) into one entry per response before any accounting,
                    # so tokens/cost/calls/message counts are not multiplied by
                    # the block count. See _merge_streamed_assistant_entries.
                    for obj in _merge_streamed_assistant_entries(_parsed_objs):
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
                                    "daily_models": defaultdict(lambda: defaultdict(lambda: {
                                        "input_tokens": 0,
                                        "output_tokens": 0,
                                        "cache_read_input_tokens": 0,
                                        "cache_creation_input_tokens": 0,
                                        "cost": 0.0,
                                        "calls": 0,
                                    })),
                                    "daily_message_count": defaultdict(int),
                                    "hour_hist": defaultdict(int),
                                    "weekday_hist": defaultdict(int),
                                    "tools": defaultdict(int),
                                    "tool_tokens": defaultdict(lambda: {
                                        "calls": 0,
                                        "output_tokens": 0,
                                        "cost": 0.0,
                                    }),
                                    "reasoning_output_tokens": 0,
                                    "reasoning_cost": 0.0,
                                    "write_categories": {cat: 0 for cat in WRITE_CATEGORIES},
                                    "skills": defaultdict(int),
                                    "hooks": defaultdict(int),
                                    "compactions": 0,
                                    "compaction_events": [],
                                    "cache_flush_count": 0,
                                    "_assistant_turns": [],  # private: {"ts","cache_creation","cache_read","model"} dicts per assistant turn — dropped before serialization
                                    "_pending_text_tokens": 0,  # private: screen_text from most recent pure-text assistant turn, awaiting narration-vs-final classification — dropped before serialization
                                    "message_count": 0,
                                    "user_message_count": 0,
                                    "assistant_message_count": 0,
                                    "tool_result_count": 0,
                                    "command_message_count": 0,
                                    "interrupt_count": 0,
                                    "meta_message_count": 0,
                                    "first_prompt": "",
                                    "file_size": file_size,
                                    "slug": obj.get("slug", ""),
                                    "source": source_label,
                                    "agent_dispatches": [],
                                    "subagents": [],
                                    "is_subagent": False,
                                    "parent_session_id": "",
                                    "agent_id": "",
                                    "agent_type": "",
                                    "agent_description": "",
                                    "error_count": 0,
                                    "errors": [],
                                    "cancelled_count": 0,
                                    "rejected_count": 0,
                                    "errors_by_source": defaultdict(int),
                                    "limit_event_candidates": [],
                                    "user_timestamps": [],  # private: user-prompt ts_ms only, dropped before serialization
                                    "file_ops": [],
                                    "git_ops": [],
                                }

                            sess = sessions[session_id]

                            # Mark subagent status (may be set multiple times, that's fine)
                            if is_subagent:
                                sess["is_subagent"] = True
                                sess["parent_session_id"] = parent_id
                                if sub_agent_id:
                                    sess["agent_id"] = sub_agent_id
                                if sub_agent_type and not sess["agent_type"]:
                                    sess["agent_type"] = sub_agent_type
                                if sub_agent_desc and not sess["agent_description"]:
                                    sess["agent_description"] = sub_agent_desc

                            if obj.get("cwd") and not sess["project_path"]:
                                sess["project_path"] = obj["cwd"]

                            if obj.get("slug") and not sess["slug"]:
                                sess["slug"] = obj["slug"]

                            # Collect timestamps. Only conversational entries
                            # (prompts, tool results, assistant turns) define the
                            # session's start/end/duration; external markers like
                            # pr-link arrive hours-to-days later and would inflate
                            # duration by up to tens of hours.
                            _ts_counts_for_duration = msg_type in ("user", "assistant")
                            ts_ms_for_msg = None
                            if timestamp:
                                if isinstance(timestamp, str):
                                    try:
                                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                        ts_ms_for_msg = int(dt.timestamp() * 1000)
                                        if _ts_counts_for_duration:
                                            sess["timestamps"].append(ts_ms_for_msg)
                                    except (ValueError, OSError):
                                        pass
                                elif isinstance(timestamp, (int, float)):
                                    ts_ms_for_msg = int(timestamp)
                                    if _ts_counts_for_duration:
                                        sess["timestamps"].append(ts_ms_for_msg)

                            # API-error messages flagged by Claude Code itself.
                            # This is the canonical channel for real user-plan
                            # rate-limit hits (e.g. "You've hit your limit ·
                            # resets 6pm (Europe/Berlin)"). Sibling buckets
                            # like auth / overloaded / 500 share the flag, so
                            # filter to plan-limit phrasing only.
                            if obj.get("isApiErrorMessage"):
                                _api_msg = obj.get("message", {})
                                _api_txt = _api_msg.get("content", "") if isinstance(_api_msg, dict) else ""
                                if isinstance(_api_txt, list):
                                    _api_txt = next((b.get("text", "") for b in _api_txt
                                                     if isinstance(b, dict) and b.get("type") == "text"), "")
                                _api_txt = str(_api_txt)
                                if _is_user_plan_limit_text(_api_txt):
                                    sess["limit_event_candidates"].append({
                                        "type": "explicit",
                                        "subtype": "user_plan_limit",
                                        "timestamp": str(timestamp) if timestamp else "",
                                        "session_id": session_id,
                                        "confidence": "high",
                                        "message_text": _api_txt[:400],
                                    })
                                # Real backend/API failure (rate-limit, overload,
                                # auth, 5xx, timeout, invalid request). Counted as
                                # an error with source "backend" so the source
                                # breakdown is complete. The limit-event tab above
                                # is a separate view of the same signal.
                                if _api_txt.strip():
                                    sess["error_count"] += 1
                                    sess["errors_by_source"]["backend"] += 1
                                    sess["errors"].append({
                                        "message": _api_txt[:200],
                                        "tool": "",
                                        "source": "backend",
                                        "category": _classify_api_error(_api_txt),
                                        "tool_use_id": "",
                                        "timestamp": timestamp or "",
                                    })

                            # User messages
                            if msg_type == "user":
                                # Resolve pending text-only assistant turn: followed by a user
                                # message → it was a final answer, keep as screen_text.
                                sess["_pending_text_tokens"] = 0

                                # Compaction: Claude Code records it as a
                                # type:"user" entry flagged isCompactSummary.
                                if obj.get("isCompactSummary"):
                                    sess["compactions"] += 1
                                    _cts = ""
                                    if isinstance(timestamp, str):
                                        _cts = timestamp
                                    elif isinstance(timestamp, (int, float)):
                                        try:
                                            _cts = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()
                                        except (ValueError, OSError):
                                            _cts = str(timestamp)
                                    sess["compaction_events"].append({"timestamp": _cts})

                                # Classify the user-channel entry. Only genuine
                                # typed prompts count toward user_message_count /
                                # message_count; tool_results, slash-commands,
                                # interrupts and meta entries are tracked as their
                                # own metrics so they no longer inflate User Msgs.
                                _ucat = _classify_user_entry(obj)
                                if _ucat == "prompt":
                                    sess["message_count"] += 1
                                    sess["user_message_count"] += 1
                                    if ts_ms_for_msg is not None:
                                        sess["user_timestamps"].append(ts_ms_for_msg)
                                    if ts_ms_for_msg is not None:
                                        sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
                                        _lt = datetime.fromtimestamp(ts_ms_for_msg / 1000)
                                        sess["hour_hist"][_lt.hour] += 1
                                        sess["weekday_hist"][_lt.weekday()] += 1
                                elif _ucat == "tool_result":
                                    sess["tool_result_count"] += 1
                                elif _ucat == "command":
                                    sess["command_message_count"] += 1
                                elif _ucat == "interrupt":
                                    sess["interrupt_count"] += 1
                                elif _ucat == "meta":
                                    sess["meta_message_count"] += 1

                                # Link Agent tool_result -> dispatch via tool_use_id + toolUseResult.agentId
                                tur = obj.get("toolUseResult") if isinstance(obj.get("toolUseResult"), dict) else None
                                message = obj.get("message", {})
                                content = message.get("content", "")
                                if isinstance(content, list):
                                    for block in content:
                                        if (isinstance(block, dict)
                                            and block.get("type") == "tool_result"
                                            and tur and tur.get("agentId")):
                                            tid = block.get("tool_use_id", "")
                                            if tid:
                                                for ad in sess.get("agent_dispatches", []):
                                                    if ad.get("tool_use_id") == tid:
                                                        ad["agent_id"] = tur.get("agentId", "")
                                                        break
                                        if isinstance(block, dict) and block.get("is_error"):
                                            error_msg = str(block.get("content", ""))
                                            if "<tool_use_error>" in error_msg:
                                                error_msg = error_msg.split("<tool_use_error>")[-1].split("</tool_use_error>")[0]
                                            tid = block.get("tool_use_id", "")
                                            tool_name = sess.get("_tool_id_map", {}).get(tid, "unknown")
                                            source, category = _classify_tool_error(error_msg, tool_name)
                                            eff_source = _route_tool_error(source, category)
                                            if eff_source is None:
                                                # Cancelled parallel-call sibling: not a failure,
                                                # tracked separately, kept out of error_count.
                                                sess["cancelled_count"] += 1
                                            else:
                                                # tool / hook / backend failures AND user
                                                # rejections all count as errors (rejection
                                                # under its own "rejected" source).
                                                if eff_source == "rejected":
                                                    sess["rejected_count"] += 1
                                                sess["error_count"] += 1
                                                sess["errors_by_source"][eff_source] += 1
                                                sess["errors"].append({
                                                    "message": error_msg[:200],
                                                    "tool": tool_name,
                                                    "source": eff_source,
                                                    "category": category,
                                                    "tool_use_id": tid,
                                                    "timestamp": timestamp or "",
                                                })
                                            # NOTE: tool_result.is_error is intentionally NOT
                                            # used as a limit-event signal, and backend
                                            # categories (rate_limit / overload) are NOT matched
                                            # here — tool output often mentions those words
                                            # incidentally. Real backend errors come in via
                                            # isApiErrorMessage (source "backend") below.

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
                                # Resolve pending text-only assistant turn: followed by another
                                # assistant message → it was narration before action, shift its
                                # screen_text tokens into the narration bucket.
                                _pending = sess.get("_pending_text_tokens", 0)
                                if _pending > 0:
                                    sess["write_categories"]["screen_text"] -= _pending
                                    sess["write_categories"]["screen_text_narration"] += _pending
                                sess["_pending_text_tokens"] = 0

                                sess["message_count"] += 1
                                sess["assistant_message_count"] += 1
                                if ts_ms_for_msg is not None:
                                    sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
                                    _lt = datetime.fromtimestamp(ts_ms_for_msg / 1000)
                                    sess["hour_hist"][_lt.hour] += 1
                                    sess["weekday_hist"][_lt.weekday()] += 1

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

                                    turn_cost = calc_cost(model, usage)
                                    m["cost"] += turn_cost
                                    m["calls"] += 1

                                    # Per-turn capture for gap-based cache-flush + idle-gap analysis (Tasks 1+2).
                                    turn_ts_ms = None
                                    if timestamp:
                                        if isinstance(timestamp, str):
                                            try:
                                                _dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                                turn_ts_ms = int(_dt.timestamp() * 1000)
                                            except (ValueError, OSError):
                                                pass
                                        elif isinstance(timestamp, (int, float)):
                                            turn_ts_ms = int(timestamp)
                                    turn_output = usage.get("output_tokens", 0)
                                    if turn_ts_ms is not None:
                                        sess["_assistant_turns"].append({
                                            "ts": turn_ts_ms,
                                            "timestamp": timestamp,
                                            "input": usage.get("input_tokens", 0),
                                            "cache_creation": usage.get("cache_creation_input_tokens", 0),
                                            "cache_read": usage.get("cache_read_input_tokens", 0),
                                            "model": model,
                                            "cost": turn_cost,
                                        })
                                    if turn_ts_ms is not None:
                                        _dm = sess["daily_models"][_day_from_ms(turn_ts_ms)][model]
                                        _dm["input_tokens"] += usage.get("input_tokens", 0)
                                        _dm["output_tokens"] += usage.get("output_tokens", 0)
                                        _dm["cache_read_input_tokens"] += usage.get("cache_read_input_tokens", 0)
                                        _dm["cache_creation_input_tokens"] += usage.get("cache_creation_input_tokens", 0)
                                        _dm["cost"] += turn_cost
                                        _dm["calls"] += 1

                                    turn_tool_names = [
                                        b.get("name", "unknown")
                                        for b in message.get("content", [])
                                        if isinstance(b, dict) and b.get("type") == "tool_use"
                                    ]
                                    attrib = attribute_turn_tokens(turn_output, turn_cost, turn_tool_names)
                                    for entry in attrib["per_tool"]:
                                        tt = sess["tool_tokens"][entry["tool"]]
                                        tt["output_tokens"] += entry["output_tokens"]
                                        tt["cost"] += entry["cost"]
                                    sess["reasoning_output_tokens"] += attrib["reasoning_output_tokens"]
                                    sess["reasoning_cost"] += attrib["reasoning_cost"]

                                    wc_attrib = attribute_write_categories(
                                        message.get("content", []), turn_output
                                    )
                                    for cat, tokens in wc_attrib.items():
                                        sess["write_categories"][cat] += tokens

                                    # If this turn was pure text (no tool_use), keep its
                                    # screen_text tokens pending: a following assistant message
                                    # means narration; a following user message means final answer.
                                    _turn_has_tools = any(
                                        isinstance(b, dict) and b.get("type") == "tool_use"
                                        for b in message.get("content", [])
                                    )
                                    if not _turn_has_tools:
                                        sess["_pending_text_tokens"] = wc_attrib.get("screen_text", 0)

                                for block in message.get("content", []):
                                    if isinstance(block, dict) and block.get("type") == "tool_use":
                                        tool_name = block.get("name", "unknown")
                                        # Map tool_use_id -> tool_name for error attribution
                                        tool_id = block.get("id", "")
                                        if tool_id:
                                            sess.setdefault("_tool_id_map", {})[tool_id] = tool_name
                                        sess["tools"][tool_name] += 1
                                        sess["tool_tokens"][tool_name]["calls"] += 1
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
                                                "tool_use_id": block.get("id", ""),
                                                "agent_id": "",  # filled when tool_result arrives
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

                except Exception as e:
                    print(f"      ERROR reading {jsonl_file.name}: {e}")

    # Link subagents to parent sessions and remove them from the top level;
    # orphans (parent transcript missing) stay so their spend is not lost.
    _link_subagents(sessions)

    # Compute gap-based cache-flush count from per-turn data (Task 1).
    # _assistant_turns stays on the session for build_dashboard_data() to
    # use in the 5h-window aggregation; it gets dropped in there before
    # serialization.
    for sess in sessions.values():
        turns = sess.get("_assistant_turns", [])
        has_1h = any(
            m.get("cache_1h_tokens", 0) > 0
            for m in sess.get("models", {}).values()
        )
        compaction_ts_ms = []
        for ev in sess.get("compaction_events", []):
            ts = ev.get("timestamp")
            if not ts:
                continue
            try:
                compaction_ts_ms.append(int(
                    datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() * 1000
                ))
            except (ValueError, OSError, OverflowError):
                continue
        flushes = _detect_cache_flushes(turns, has_1h, compaction_ts_ms)
        sess["cache_flush_count"] = flushes["gap_flushes"]
        sess["cache_nogap_flush_count"] = flushes["nogap_flushes"]
        sess["cache_nogap_rewrite_tokens"] = flushes["nogap_rewrite_tokens"]
        sess["idle_gap_summary"] = _compute_idle_gap_summary(turns)
        ctx_window = summarize_context_window(turns)
        sess["peak_context_tokens"] = ctx_window["peak_context_tokens"]
        sess["used_1m_context"] = ctx_window["used_1m_context"]
        sess["first_1m_at"] = ctx_window["first_1m_at"]

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
    # response's real cost, not one fragmented bubble per content block each
    # stamped with the repeated full usage.
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
                # encrypted thinking, so the text is empty — we still flag that
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


def _month_day_clamped(year, month, day):
    """Naive datetime for (year, month, day) with the day clamped to the
    month's last day. Billing anchors like 31 survive short months this
    way: callers pass the anchor day each time (never the clamped result),
    so Jan 31 -> Feb 28 -> Mar 31."""
    return datetime(year, month, min(day, calendar.monthrange(year, month)[1]))


def _expand_billing_cycles(ph, start_str, end_str):
    """Expand a plan period into per-month accounting cycles with per-cycle cost.

    Returns list of dicts: {start, end, cost_usd, cost_local}.
    - Monthly plans: one entry per billing month, full plan cost per entry.
    - Annual plans: one entry per *month* within the annual cycle, plan cost / 12
      per entry. This avoids the annual price appearing against a partial month
      when the plan ends mid-cycle.
    """
    billing_day = ph.get("billing_day")
    billing_cycle = ph.get("billing_cycle", "monthly")
    full_cost_usd = ph["cost_usd"]
    full_cost_local = ph.get("cost_local", ph.get("cost_eur"))

    if billing_cycle == "annual":
        per_cycle_usd = full_cost_usd / 12
        per_cycle_local = (full_cost_local / 12) if full_cost_local else None
    else:
        per_cycle_usd = full_cost_usd
        per_cycle_local = full_cost_local

    if not billing_day:
        return [{
            "start": start_str, "end": end_str,
            "cost_usd": per_cycle_usd, "cost_local": per_cycle_local,
        }]

    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    cycles = []
    cycle_start = start_dt
    while cycle_start <= end_dt:
        ny = cycle_start.year + (1 if cycle_start.month == 12 else 0)
        nm = 1 if cycle_start.month == 12 else cycle_start.month + 1
        # Clamp to the target month's length so day 29-31 anchors neither
        # raise ValueError nor skip whole months; passing billing_day (not
        # the clamped previous start) keeps the anchor across short months.
        next_billing = _month_day_clamped(ny, nm, billing_day)
        cycle_end = min(next_billing - timedelta(days=1), end_dt)
        cycles.append({
            "start": cycle_start.strftime("%Y-%m-%d"),
            "end": cycle_end.strftime("%Y-%m-%d"),
            "cost_usd": per_cycle_usd,
            "cost_local": per_cycle_local,
        })
        cycle_start = next_billing
    return cycles


WEEKLY_VS_5H_RATIO = 7  # weekly cap ≈ 7 × 5h-cap (rough — one full 5h-session per day × 7 days)

REC_RECENT_CYCLES = 3         # recommendation looks at the last N billing cycles
REC_5H_HIT_QUOTA = 0.05       # tier holds if it hits in <=5% of recent 5h-windows
REC_WEEKLY_HIT_ALLOWANCE = 1  # ...and in at most this many recent weeks


def _recommend_tier(rec_cycles):
    """Cheapest tier whose recent hit rate stays inside the tolerance.

    Only the last REC_RECENT_CYCLES cycles count -- usage from months ago,
    shaped by a different plan, should not disqualify a tier forever. A
    tier holds when its 5h hits are <= REC_5H_HIT_QUOTA of the recent
    window count and its weekly hits are <= REC_WEEKLY_HIT_ALLOWANCE.
    Returns (recommended_tier_or_None, basis_dict).
    """
    recent = rec_cycles[-REC_RECENT_CYCLES:]
    window_total = sum(c.get("total_5h_windows", 0) for c in recent)
    tier_5h = {t: sum(c.get("tier_5h_hits", {}).get(t, 0) for c in recent)
               for t in PLAN_TIER_FACTORS}
    tier_weekly = {t: sum(c.get("tier_weekly_hits", {}).get(t, 0) for c in recent)
                   for t in PLAN_TIER_FACTORS}
    recommended = None
    # When window_total == 0, quota == 0.0 and any tier with 0 hits passes;
    # "Pro" is the cheapest conservative fallback with no usage data.
    for tier in ("Pro", "Max 5x", "Max 20x"):
        if (tier_5h[tier] <= REC_5H_HIT_QUOTA * window_total
                and tier_weekly[tier] <= REC_WEEKLY_HIT_ALLOWANCE):
            recommended = tier
            break
    basis = {
        "recent_cycles": len(recent),
        "recent_window_total": window_total,
        "hit_quota": REC_5H_HIT_QUOTA,
        "weekly_allowance": REC_WEEKLY_HIT_ALLOWANCE,
        "tier_recent_5h_hits": tier_5h,
        "tier_recent_weekly_hits": tier_weekly,
    }
    return recommended, basis


_TIER_PRICE_ORDER = ("Pro", "Max 5x", "Max 20x")


def _tier_holds_in_cycle(cycle, tier):
    """Whether `tier` would have stayed inside tolerance for this one cycle.

    Reuses the same constants as _recommend_tier (REC_5H_HIT_QUOTA,
    REC_WEEKLY_HIT_ALLOWANCE), applied to this cycle's own window/week
    counts. Introduces no new threshold.
    """
    windows = cycle.get("total_5h_windows", 0)
    hits_5h = cycle.get("tier_5h_hits", {}).get(tier, 0)
    hits_weekly = cycle.get("tier_weekly_hits", {}).get(tier, 0)
    return (hits_5h <= REC_5H_HIT_QUOTA * windows
            and hits_weekly <= REC_WEEKLY_HIT_ALLOWANCE)


def _switch_arrow_for_cycle(cycle, recommended_tier):
    """Per-cycle switch hint: None | "down" | "up".

    Points from the cycle's active tier toward the globally recommended
    tier, but only when a switch was actually warranted that cycle:
      - downgrade ("down"): recommended is cheaper AND held this cycle.
      - upgrade   ("up"):   recommended is pricier AND the active tier did
                            NOT hold this cycle.
    See docs/superpowers/specs/2026-06-10-limits-recommendation-redesign.md.
    """
    active = cycle.get("active_tier")
    if not recommended_tier or not active or active == recommended_tier:
        return None
    try:
        ai = _TIER_PRICE_ORDER.index(active)
        ri = _TIER_PRICE_ORDER.index(recommended_tier)
    except ValueError:
        return None
    if ri < ai:  # recommended cheaper -> downgrade only if it would have held
        return "down" if _tier_holds_in_cycle(cycle, recommended_tier) else None
    # recommended pricier -> upgrade only if the active tier did not hold
    return "up" if not _tier_holds_in_cycle(cycle, active) else None


def build_plan_analysis(daily_cost_series, session_list, first_session=None,
                          all_limit_events=None, windows_5h=None, weekly_buckets=None):
    """Analyze cost savings per plan period and current billing cycle.

    If first_session is given, billing cycles that end strictly before that date
    are excluded from the periods list (and totals) - they represent paid time
    with no tracked Claude usage.
    """
    all_limit_events = all_limit_events or []
    if not PLAN_HISTORY:
        # No subscription configured (API-only user): nothing to compare
        # against, and the current-billing block below would crash on
        # PLAN_HISTORY[-1]. The caller treats None as "no plan section".
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    periods = []
    for ph in PLAN_HISTORY:
        start = ph["start"]
        end = ph["end"] or today
        billing_cycle = ph.get("billing_cycle", "monthly")
        cycles = _expand_billing_cycles(ph, start, end)

        for cycle in cycles:
            cycle_start = cycle["start"]
            cycle_end = cycle["end"]
            # Skip cycle that started today (handled by current_billing)
            if cycle_start == today:
                continue
            # Skip cycles entirely before the first tracked session
            if first_session and cycle_end < first_session:
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

            plan_cost_usd = cycle["cost_usd"]
            plan_cost_local = cycle["cost_local"]
            savings = api_cost - plan_cost_usd

            # Per-cycle FX rate: cost_local / cost_usd
            fx = (plan_cost_local / plan_cost_usd) if (plan_cost_local and plan_cost_usd) else None
            cost_per_day = api_cost / total_days if total_days > 0 else 0

            plan_label = ph["plan"]
            if billing_cycle == "annual":
                plan_label = plan_label + " (annual)"

            period_entry = {
                "plan": plan_label,
                "start": cycle_start,
                "end": cycle_end,
                "total_days": total_days,
                "days_active": days_active,
                "plan_cost_local": round(plan_cost_local, 2) if plan_cost_local is not None else None,
                "plan_cost_usd": round(plan_cost_usd, 2),
                "currency_symbol": ph.get("currency_symbol"),
                "api_cost": round(api_cost, 2),
                "savings": round(savings, 2),
                "roi_factor": round(api_cost / plan_cost_usd, 1) if plan_cost_usd > 0 else 0,
                "sessions": session_count,
                "messages": message_count,
                "cost_per_day": round(cost_per_day, 2),
                # In-progress cycle of the open plan: truncated to today here,
                # enriched with full-period framing after current_billing below.
                "is_current": ph.get("end") is None and cycle_end == today,
            }
            if fx is not None:
                period_entry["api_cost_local"] = round(api_cost * fx, 2)
                period_entry["savings_local"] = round(savings * fx, 2)
                period_entry["cost_per_day_local"] = round(cost_per_day * fx, 2)

            cycle_events = [
                e for e in all_limit_events
                if cycle_start <= ((e.get("timestamp") or "")[:10]) <= cycle_end
            ]
            period_entry["limit_events"] = cycle_events
            period_entry["limit_event_count"] = len(cycle_events)
            periods.append(period_entry)

    # Current billing period (from last billing day to now)
    current_plan = PLAN_HISTORY[-1]
    billing_day = current_plan.get("billing_day", 1)
    current_billing_cycle = current_plan.get("billing_cycle", "monthly")
    today_dt = datetime.now(timezone.utc)

    if current_billing_cycle == "annual":
        # Anchor annual cycle on the plan's start date (month+day)
        plan_start_dt = datetime.strptime(current_plan["start"], "%Y-%m-%d")
        anchor_month = plan_start_dt.month
        anchor_day = plan_start_dt.day
        # Anniversary in current year
        try:
            anniversary = today_dt.replace(month=anchor_month, day=anchor_day,
                                           hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            anniversary = today_dt.replace(month=anchor_month, day=28,
                                           hour=0, minute=0, second=0, microsecond=0)
        if anniversary <= today_dt:
            billing_start = anniversary
            billing_end = billing_start.replace(year=billing_start.year + 1)
        else:
            billing_start = anniversary.replace(year=anniversary.year - 1)
            billing_end = anniversary
    else:
        # Find current monthly billing period start. billing_day is clamped
        # to each month's length so day 29-31 anchors cannot raise ValueError
        # in short months.
        candidate = _month_day_clamped(
            today_dt.year, today_dt.month, billing_day
        ).replace(tzinfo=timezone.utc)
        if candidate <= today_dt:
            billing_start = candidate
        else:
            py = today_dt.year - 1 if today_dt.month == 1 else today_dt.year
            pm = 12 if today_dt.month == 1 else today_dt.month - 1
            billing_start = _month_day_clamped(py, pm, billing_day).replace(
                tzinfo=timezone.utc)

        # Find next billing date (same clamped anchor logic)
        ny = billing_start.year + (1 if billing_start.month == 12 else 0)
        nm = 1 if billing_start.month == 12 else billing_start.month + 1
        billing_end = _month_day_clamped(ny, nm, billing_day).replace(
            tzinfo=timezone.utc)

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

    current_plan_cost_usd = current_plan["cost_usd"]
    current_plan_cost_local = current_plan.get("cost_local", current_plan.get("cost_eur"))
    current_fx = (current_plan_cost_local / current_plan_cost_usd) if (current_plan_cost_local and current_plan_cost_usd) else None
    current_savings = current_api_cost - current_plan_cost_usd
    current_cost_per_day = current_api_cost / days_elapsed if days_elapsed > 0 else 0

    current_billing = {
        "plan": current_plan["plan"],
        "period_start": billing_start_str,
        "period_end": billing_end_str,
        "days_elapsed": days_elapsed,
        "days_total": days_total,
        "days_remaining": days_remaining,
        "plan_cost_local": current_plan_cost_local,
        "plan_cost_usd": current_plan_cost_usd,
        "currency_symbol": current_plan.get("currency_symbol"),
        "api_cost": round(current_api_cost, 2),
        "projected_cost": round(projected_cost, 2),
        "savings": round(current_savings, 2),
        "roi_factor": round(current_api_cost / current_plan_cost_usd, 1) if current_plan_cost_usd > 0 else 0,
        "sessions": len(current_sessions),
        "messages": sum(s["messages"] for s in current_sessions),
        "cost_per_day": round(current_cost_per_day, 2),
    }
    if current_fx is not None:
        current_billing["api_cost_local"] = round(current_api_cost * current_fx, 2)
        current_billing["projected_cost_local"] = round(projected_cost * current_fx, 2)
        current_billing["savings_local"] = round(current_savings * current_fx, 2)
        current_billing["cost_per_day_local"] = round(current_cost_per_day * current_fx, 2)

    # Enrich the in-progress period row with full-period framing: the real
    # period end (next billing day − 1), elapsed/total days, and a projected
    # ROI. The row's money figures stay actual (so-far) so totals stay honest;
    # only the date/days/ROI gain forward-looking context.
    for p in periods:
        if p.get("is_current"):
            p["period_end_full"] = (billing_end - timedelta(days=1)).strftime("%Y-%m-%d")
            p["days_total_full"] = days_total
            p["days_elapsed"] = days_elapsed
            p["projected_roi"] = round(projected_cost / current_plan_cost_usd, 1) if current_plan_cost_usd > 0 else 0
            break

    # Total savings across all periods
    total_api = sum(p["api_cost"] for p in periods)
    total_plan = sum(p["plan_cost_usd"] for p in periods)
    total_api_local = sum(p.get("api_cost_local", 0) for p in periods)
    total_plan_local = sum((p.get("plan_cost_local") or 0) for p in periods)
    have_local_totals = any("api_cost_local" in p for p in periods)

    # Global currency symbol: prefer the most recent plan that has one
    currency_symbol = None
    for ph in reversed(PLAN_HISTORY):
        if ph.get("currency_symbol"):
            currency_symbol = ph["currency_symbol"]
            break

    # ── Plan Recommendation (Task 4) ───────────────────────────────
    # Anthropic plans cap usage per 5h-window and per week, not per month.
    # We compute hit-counts on each tier hypothesis: "how many 5h-windows /
    # weeks in this cycle would have exceeded that tier's cap?"
    raw_current_tier = current_plan.get("plan", "")
    normalized_current = _normalize_tier_name(raw_current_tier)
    if raw_current_tier and normalized_current is None:
        print(f"  WARN: plan name '{raw_current_tier}' not recognized for "
              f"recommendation; falling back to 'Max 5x'. Accepted forms: "
              f"Pro / Max 5x / Max 20x (case-insensitive, '(annual)' suffix OK).")
    if normalized_current is None:
        normalized_current = "Max 5x"

    windows_5h = windows_5h or []
    weekly_buckets = weekly_buckets or []
    all_limit_events = all_limit_events or []

    # Determine the tier that was active during each window (lookup against
    # PLAN_HISTORY using the window's start_ts).
    def _tier_at_ts(ts_ms):
        if ts_ms is None:
            return None
        d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        for ph in PLAN_HISTORY:
            start = ph.get("start", "")
            end = ph.get("end") or "9999-12-31"
            if start <= d <= end:
                return _normalize_tier_name(ph.get("plan", ""))
        return None

    cycle_tier_by_window_idx = {i: _tier_at_ts(w["start_ts"]) for i, w in enumerate(windows_5h)}

    # Match limit events to their calibration-anchor windows -- the windows
    # whose cost ≈ 100% of the active tier's 5h cap.
    limit_event_window_ids = _match_limit_events_to_windows(all_limit_events, windows_5h)

    cap_info_5h = _estimate_5h_window_cap_usd(
        windows_5h, limit_event_window_ids,
        cycle_tier_by_window_idx, PLAN_CAPACITY_OVERRIDE_PRO_USD,
    )

    # Weekly caps: rough estimate as WEEKLY_VS_5H_RATIO × 5h cap. We don't
    # have a separate weekly-fingerprint detector yet, so the calibration
    # source for weekly is "derived_from_5h" — surfaced in the UI so the
    # estimate is not presented as primary evidence.
    cap_info_weekly = {
        "caps_per_week": {t: round(c * WEEKLY_VS_5H_RATIO, 2)
                           for t, c in cap_info_5h["caps_per_window"].items()},
        "ratio_vs_5h": WEEKLY_VS_5H_RATIO,
        "source": "derived_from_5h",
    }

    def _cycle_contains_ts(p, ts_ms):
        if ts_ms is None:
            return False
        d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return p["start"] <= d <= p["end"]

    rec_cycles = []
    for p in periods:
        api = p.get("api_cost", 0)
        cycle_windows = [(i, w) for i, w in enumerate(windows_5h)
                         if _cycle_contains_ts(p, w["start_ts"])]
        cycle_weeks   = [b for b in weekly_buckets if _cycle_contains_ts(p, b["week_start_ts"])]
        hits_5h = _count_5h_hits(cycle_windows, cap_info_5h["caps_per_window"],
                                 cycle_tier_by_window_idx, limit_event_window_ids)
        hits_weekly = {}
        for tier, cap in cap_info_weekly["caps_per_week"].items():
            hits_weekly[tier] = sum(1 for b in cycle_weeks if b["cost"] > cap) if cap > 0 else 0
        rec_cycles.append({
            "cycle_start": p["start"],
            "cycle_end":   p["end"],
            "label": p["start"][:7] + " · " + p["plan"],
            "active_tier": _normalize_tier_name(p["plan"]),
            "api_cost": api,
            "total_5h_windows": len(cycle_windows),
            "total_weeks":      len(cycle_weeks),
            "tier_5h_hits":     hits_5h,
            "tier_weekly_hits": hits_weekly,
            "limit_event_count": p.get("limit_event_count", 0),
        })

    # Totals over all cycles feed the per-cycle tables; the recommendation
    # itself only looks at recent cycles with a hit-quota tolerance.
    tier_total_5h     = {t: sum(c["tier_5h_hits"].get(t, 0) for c in rec_cycles)
                          for t in PLAN_TIER_FACTORS}
    tier_total_weekly = {t: sum(c["tier_weekly_hits"].get(t, 0) for c in rec_cycles)
                          for t in PLAN_TIER_FACTORS}
    recommended_tier, rec_basis = _recommend_tier(rec_cycles)

    # Per-cycle switch hint (None | "down" | "up") for the heatmap arrows.
    for c in rec_cycles:
        c["switch_arrow"] = _switch_arrow_for_cycle(c, recommended_tier)

    plan_recommendation = {
        "current_tier":     normalized_current,
        "recommended_tier": recommended_tier,
        "rec_basis": rec_basis,
        "total_cycles":     len(rec_cycles),
        "tier_total_5h_hits":     tier_total_5h,
        "tier_total_weekly_hits": tier_total_weekly,
        "calibration_5h":      cap_info_5h,
        "calibration_weekly":  cap_info_weekly,
        "cycles": rec_cycles,
    }

    result = {
        "periods": periods,
        "current_billing": current_billing,
        "currency_symbol": currency_symbol,
        "total_api_cost": round(total_api, 2),
        "total_plan_cost": round(total_plan, 2),
        "total_savings": round(total_api - total_plan, 2),
        "overall_roi": round(total_api / total_plan, 1) if total_plan > 0 else 0,
        "plan_recommendation": plan_recommendation,
    }
    if have_local_totals:
        result["total_api_cost_local"] = round(total_api_local, 2)
        result["total_plan_cost_local"] = round(total_plan_local, 2)
        result["total_savings_local"] = round(total_api_local - total_plan_local, 2)
    return result


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
        "cache_1h_tokens": 0,
        "cost": 0.0, "calls": 0
    })
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    total_messages = 0
    seen_model_ids = set()

    for sid, sess in sessions.items():
        timestamps = sorted(sess["timestamps"])
        if not timestamps:
            continue

        start_ts = min(timestamps)
        end_ts = max(timestamps)

        start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
        date_str = start_dt.strftime("%Y-%m-%d")

        duration_s = (end_ts - start_ts) / 1000

        session_cost = 0.0
        session_input = 0
        session_output = 0
        session_cache_read = 0
        session_cache_write = 0
        session_calls = 0
        model_breakdown = {}

        for model, mdata in sess["models"].items():
            seen_model_ids.add(model)
            session_cost += mdata["cost"]
            session_input += mdata["input_tokens"]
            session_output += mdata["output_tokens"]
            session_cache_read += mdata["cache_read_input_tokens"]
            session_cache_write += mdata["cache_creation_input_tokens"]
            session_calls += mdata["calls"]

            display_model = get_model_display(model)

            mt = model_totals[display_model]
            mt["input_tokens"] += mdata["input_tokens"]
            mt["output_tokens"] += mdata["output_tokens"]
            mt["cache_read_tokens"] += mdata["cache_read_input_tokens"]
            mt["cache_write_tokens"] += mdata["cache_creation_input_tokens"]
            mt["cache_1h_tokens"] += mdata.get("cache_1h_tokens", 0)
            mt["cost"] += mdata["cost"]
            mt["calls"] += mdata["calls"]

            model_breakdown[display_model] = {
                "cost": round(mdata["cost"], 4),
                "input_tokens": mdata["input_tokens"],
                "output_tokens": mdata["output_tokens"],
                "cache_read_tokens": mdata["cache_read_input_tokens"],
                "calls": mdata["calls"],
            }

        per_day_models, per_day_messages = split_session_by_day(
            sess.get("daily_models", {}),
            sess["models"],
            sess.get("daily_message_count", {}),
            sess["message_count"],
            start_day=date_str,
        )
        for _day, _mdict in per_day_models.items():
            _day_in = 0
            _day_cr = 0
            for _model, _b in _mdict.items():
                _dm = get_model_display(_model)
                daily_costs[_day][_dm] += _b["cost"]
                daily_tokens[_day][_dm]["input"] += _b["input_tokens"]
                daily_tokens[_day][_dm]["output"] += _b["output_tokens"]
                daily_tokens[_day][_dm]["cache_read"] += _b["cache_read_input_tokens"]
                daily_tokens[_day][_dm]["cache_write"] += _b["cache_creation_input_tokens"]
                _day_in += _b["input_tokens"] + _b["cache_read_input_tokens"] + _b["cache_creation_input_tokens"]
                _day_cr += _b["cache_read_input_tokens"]
            # Skip structurally trivial slices; mirrors the frontend filter
            # (CACHE_EFF_MIN_MESSAGES) so server series == client rebuild.
            if _day_in > 0 and per_day_messages.get(_day, 0) >= CACHE_EFF_MIN_MESSAGES:
                daily_cache_eff[_day].append(_day_cr / _day_in * 100)
        for _day, _n in per_day_messages.items():
            daily_messages[_day] += _n
        for _day in set(per_day_models) | set(per_day_messages):
            daily_sessions[_day] += 1

        _active_days = set(per_day_models) | set(per_day_messages)
        session_per_day = None
        if len(_active_days) > 1:
            session_per_day = {}
            for _day in sorted(_active_days):
                _models_out = {}
                for _model, _b in per_day_models.get(_day, {}).items():
                    _dm = get_model_display(_model)
                    e = _models_out.setdefault(_dm, {
                        "cost": 0.0, "input_tokens": 0, "output_tokens": 0,
                        "cache_read_tokens": 0, "cache_write_tokens": 0,
                    })
                    e["cost"] += _b["cost"]
                    e["input_tokens"] += _b["input_tokens"]
                    e["output_tokens"] += _b["output_tokens"]
                    e["cache_read_tokens"] += _b["cache_read_input_tokens"]
                    e["cache_write_tokens"] += _b["cache_creation_input_tokens"]
                for e in _models_out.values():
                    e["cost"] = round(e["cost"], 4)
                session_per_day[_day] = {
                    "messages": per_day_messages.get(_day, 0),
                    "models": _models_out,
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

        for _h, _c in sess["hour_hist"].items():
            hourly_messages[_h] += _c
        for _w, _c in sess["weekday_hist"].items():
            weekday_messages[_w] += _c

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
            "tool_results": sess["tool_result_count"],
            "command_messages": sess["command_message_count"],
            "interrupts": sess["interrupt_count"],
            "meta_messages": sess["meta_message_count"],
            "input_tokens": session_input,
            "output_tokens": session_output,
            "cache_read_tokens": session_cache_read,
            "cache_write_tokens": session_cache_write,
            "peak_context_tokens": sess.get("peak_context_tokens", 0),
            "used_1m_context": sess.get("used_1m_context", False),
            "first_1m_at": sess.get("first_1m_at"),
            "api_calls": session_calls,
            "primary_model": primary_model,
            "model_breakdown": model_breakdown,
            "per_day": session_per_day,
            "hour_hist": dict(sess["hour_hist"]),
            "weekday_hist": dict(sess["weekday_hist"]),
            "tools": dict(sess["tools"]),
            "tool_tokens": {
                name: {
                    "calls": v["calls"],
                    "output_tokens": v["output_tokens"],
                    "cost": round(v["cost"], 4),
                }
                for name, v in sess["tool_tokens"].items()
            },
            "reasoning_output_tokens": sess["reasoning_output_tokens"],
            "reasoning_cost": round(sess["reasoning_cost"], 4),
            "write_categories": dict(sess["write_categories"]),
            "skills": dict(sess["skills"]),
            "hooks": dict(sess["hooks"]),
            "compactions": sess["compactions"],
            "compaction_events": sess["compaction_events"],
            "cache_flush_count": sess.get("cache_flush_count", 0),
            "cache_nogap_flush_count": sess.get("cache_nogap_flush_count", 0),
            "cache_nogap_rewrite_tokens": sess.get("cache_nogap_rewrite_tokens", 0),
            "idle_gap_summary": sess.get("idle_gap_summary"),
            "first_prompt": sess["first_prompt"],
            "slug": sess["slug"],
            "file_size_mb": round(sess["file_size"] / 1_048_576, 2),
            "agent_dispatches": sess.get("agent_dispatches", []),
            "subagents": sess.get("subagents", []),
            "error_count": sess.get("error_count", 0),
            "cancelled_count": sess.get("cancelled_count", 0),
            "rejected_count": sess.get("rejected_count", 0),
            "errors_by_source": dict(sess.get("errors_by_source", {})),
            "errors": [{"message": e["message"], "tool": e.get("tool", "unknown"), "source": e.get("source", "tool"), "category": e.get("category", "other"), "timestamp": e.get("timestamp", "")} for e in sess.get("errors", [])],
            "file_ops_count": len(sess.get("file_ops", [])),
            "git_ops": sess.get("git_ops", []),
            "source": sess.get("source", SOURCE_LABEL),
            "is_subagent": bool(sess.get("is_subagent")),
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

    daily_token_series = []
    for d in all_dates:
        entry = {"date": d}
        day_total = 0
        day_tok = daily_tokens.get(d, {})
        for m in all_models:
            tb = day_tok.get(m)
            val = (tb["input"] + tb["output"]) if tb else 0
            entry[m] = val
            day_total += val
        entry["total"] = day_total
        daily_token_series.append(entry)

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
        p = pricing_for_display(mname_display)

        cost_by_type["input"] += mdata["input_tokens"] * p["input"] / 1_000_000
        cost_by_type["output"] += mdata["output_tokens"] * p["output"] / 1_000_000
        cost_by_type["cache_read"] += mdata["cache_read_tokens"] * p["cache_read"] / 1_000_000
        # Split cache writes by TTL: 1h writes cost 2x input, 5m writes 1.25x.
        _w1h = min(mdata.get("cache_1h_tokens", 0), mdata["cache_write_tokens"])
        _w5m = mdata["cache_write_tokens"] - _w1h
        cost_by_type["cache_write"] += (
            _w5m * p["cache_write_5m"] + _w1h * p["cache_write_1h"]
        ) / 1_000_000

    cost_by_type = {k: round(v, 2) for k, v in cost_by_type.items()}

    # Cache efficiency: what would cache_read tokens have cost at full input price?
    cache_savings = 0.0
    for mname_display, mdata in model_totals.items():
        p = pricing_for_display(mname_display)
        full_price = mdata["cache_read_tokens"] * p["input"] / 1_000_000
        cache_price = mdata["cache_read_tokens"] * p["cache_read"] / 1_000_000
        cache_savings += full_price - cache_price

    cost_by_type["cache_savings"] = round(cache_savings, 2)

    # Claude models seen in the data with no explicit PRICING entry: their cost
    # is only an estimate (DEFAULT_PRICING), so surface them for the user to add.
    pricing_warnings = build_pricing_warnings(seen_model_ids)

    # ── Global Tool Aggregation ───────────────────────────────────────────
    global_tools = defaultdict(int)
    for s in session_list:
        for tool_name, count in s.get("tools", {}).items():
            global_tools[tool_name] += count
    tool_ranking = sorted(global_tools.items(), key=lambda x: -x[1])
    tool_summary = [{"name": n, "count": c} for n, c in tool_ranking]

    # Global Tool Token Aggregation (cost + output tokens per tool)
    global_tool_tokens = {}
    global_reasoning_output = 0
    global_reasoning_cost = 0.0
    for s in session_list:
        for tname, td in (s.get("tool_tokens") or {}).items():
            agg = global_tool_tokens.setdefault(tname, {"calls": 0, "output_tokens": 0, "cost": 0.0})
            agg["calls"] += td.get("calls", 0)
            agg["output_tokens"] += td.get("output_tokens", 0)
            agg["cost"] += td.get("cost", 0.0)
        global_reasoning_output += s.get("reasoning_output_tokens", 0)
        global_reasoning_cost += s.get("reasoning_cost", 0.0)

    tool_token_summary = sorted(
        [{"name": n, **v, "cost": round(v["cost"], 4)} for n, v in global_tool_tokens.items()],
        key=lambda x: -x["output_tokens"],
    )

    global_write_categories = {cat: 0 for cat in WRITE_CATEGORIES}
    for s in session_list:
        wc = s.get("write_categories") or {}
        for cat in WRITE_CATEGORIES:
            global_write_categories[cat] += wc.get(cat, 0)
    _wc_total = sum(global_write_categories.values()) or 1
    write_categories_summary = [
        {
            "category": cat,
            "output_tokens": global_write_categories[cat],
            "share": round(global_write_categories[cat] / _wc_total, 4),
        }
        for cat in WRITE_CATEGORIES
    ]

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
    total_cancelled = 0
    total_rejected = 0
    errors_by_tool = defaultdict(int)
    errors_by_category = defaultdict(int)
    errors_by_source = defaultdict(int)
    for s in session_list:
        total_errors += s.get("error_count", 0)
        total_cancelled += s.get("cancelled_count", 0)
        total_rejected += s.get("rejected_count", 0)
        for e in s.get("errors", []):
            errors_by_tool[e.get("tool", "unknown")] += 1
            errors_by_category[e.get("category", "other")] += 1
            errors_by_source[e.get("source", "tool")] += 1
    # True tool-call count (every tool_use across all sessions), NOT the
    # number of assistant API calls: one API call can carry several parallel
    # tool_use blocks, and the UI labels this number "tool calls".
    total_tool_calls = sum(global_tools.values())

    # Global Git Ops
    total_commits = sum(len([g for g in s.get("git_ops", []) if g.get("type") == "commit"]) for s in session_list)
    total_pushes = sum(len([g for g in s.get("git_ops", []) if g.get("type") == "push"]) for s in session_list)
    total_prs = sum(len([g for g in s.get("git_ops", []) if g.get("type") == "pr"]) for s in session_list)

    dc = dot_claude
    account = dc.get("oauthAccount", {})

    # ── Limit-Event-Detection (Task 3) ────────────────────────────────────
    # Collect USER prompts only (not assistant turns) for the 5h-fingerprint
    # heuristic. Using mixed timestamps would allow assistant-only sequences
    # to qualify as 'gaps' and inflate false positives.
    all_user_prompts_for_limits = []
    for sid, sess in sessions.items():
        for ts_ms in sess.get("user_timestamps", []):
            try:
                all_user_prompts_for_limits.append({
                    "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
                    "session_id": sid,
                })
            except (OSError, ValueError):
                continue
    fingerprint_events = _detect_5h_fingerprint_events(all_user_prompts_for_limits)

    # Aggregate explicit events from all sessions. Drop private fields.
    explicit_events = []
    for sid, sess in sessions.items():
        for ev in sess.get("limit_event_candidates", []):
            explicit_events.append(ev)
        sess.pop("limit_event_candidates", None)
        sess.pop("user_timestamps", None)
        sess.pop("_pending_text_tokens", None)
        sess.pop("daily_models", None)
        sess.pop("daily_message_count", None)

    all_limit_events = _dedupe_limit_events(explicit_events + fingerprint_events)
    all_limit_events.sort(key=lambda e: e.get("timestamp", ""))

    # ── 5h-Window + Weekly aggregation across ALL sessions ──────────────
    # Build a chronological flat list of every assistant turn (timestamp +
    # cost + session_id) so we can group into Anthropic-shaped 5h and weekly
    # buckets. Drops the per-session _assistant_turns afterwards.
    all_turns = []
    for sid, sess in sessions.items():
        for t in sess.get("_assistant_turns", []):
            all_turns.append({
                "ts": t.get("ts"),
                "cost": t.get("cost", 0.0),
                "session_id": sid,
            })
        sess.pop("_assistant_turns", None)
    all_turns.sort(key=lambda t: t.get("ts", 0))
    windows_5h     = _compute_5h_windows(all_turns)
    weekly_buckets = _compute_weekly_buckets(all_turns)

    # ── Plan-Analyse ───────────────────────────────────────────────────────
    first_session_date = all_dates[0] if all_dates else None
    plan_analysis = build_plan_analysis(
        daily_cost_series, session_list,
        first_session=first_session_date,
        all_limit_events=all_limit_events,
        windows_5h=windows_5h,
        weekly_buckets=weekly_buckets,
    )

    # ── Actual plan cost for KPI ─────────────────────────────────────────
    actual_plan_cost = plan_analysis.get("total_plan_cost", 0) if plan_analysis else 0
    # plan_recommendation is consumed by the frontend at the top level only;
    # pop it out of the nested plan dict so it is serialized exactly once.
    plan_recommendation = (
        plan_analysis.pop("plan_recommendation", None) if plan_analysis else None
    )

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "locale": LOCALE,
        "week_anchor": WEEK_ANCHOR,
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
        "plan_recommendation": plan_recommendation,
        "daily_costs": daily_cost_series,
        "daily_tokens": daily_token_series,
        "cumulative_costs": cumulative_series,
        "daily_messages": daily_message_series,
        "daily_cache_efficiency": daily_cache_efficiency_series,
        "hourly_distribution": hourly_dist,
        "weekday_distribution": weekday_dist,
        "models": all_models,
        "model_summary": model_summary,
        "cost_by_token_type": cost_by_type,
        "pricing_warnings": pricing_warnings,
        "projects": project_list,
        "sessions": session_list,
        "tool_summary": tool_summary,
        "tool_token_summary": tool_token_summary,
        "write_categories_summary": write_categories_summary,
        "reasoning_summary": {
            "output_tokens": global_reasoning_output,
            "cost": round(global_reasoning_cost, 4),
        },
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
            "total_cancelled": total_cancelled,
            "total_rejected": total_rejected,
            "by_source": sorted([{"source": s, "count": n} for s, n in errors_by_source.items()], key=lambda x: -x["count"]),
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
        "limit_events_all": all_limit_events,
    }

    return data


def generate_dashboard(data):
    """Generate self-contained HTML dashboard with embedded data."""
    data_json = json.dumps(data, ensure_ascii=False)
    # Same </script>-in-string protection as session pages — avoid premature
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
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
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
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
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
    html = html.replace("<!-- STYLES -->", f"<style>{css}</style>")
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
