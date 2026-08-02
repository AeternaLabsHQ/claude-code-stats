"""5h-window / weekly-bucket / plan-limit-event math."""
import statistics
from datetime import datetime, timedelta, timezone

from . import settings

# Anthropic weekly limits reset on a per-user weekday, not on ISO weeks.
# config.json "week_anchor" ("mon".."sun") sets that weekday for the weekly
# bucketing AND the frontend chart markers (exported as data["week_anchor"]).
_WEEKDAY_BY_ANCHOR = {"mon": 0, "tue": 1, "wed": 2, "thu": 3,
                      "fri": 4, "sat": 5, "sun": 6}

# Plan-recommendation constants (Task 4).
# Source: Anthropic pricing communication / docs page (Pro = 1×, Max 5x = 5×,
# Max 20x = 20×). Exact token limits are not published: these factors are
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
    window: matches Claude Code's actual session-limit semantics. Returns
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
        anchor_weekday = _WEEKDAY_BY_ANCHOR[settings.WEEK_ANCHOR]
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
