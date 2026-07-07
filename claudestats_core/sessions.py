"""Session state machine: fold parsed transcript objects into per-session
aggregates (subagent linking, per-model buckets, daily splits)."""
from collections import defaultdict
from datetime import datetime, timezone


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
