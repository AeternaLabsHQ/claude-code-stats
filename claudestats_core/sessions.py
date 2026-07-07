"""Session state machine: fold parsed transcript objects into per-session
aggregates (subagent linking, per-model buckets, daily splits)."""
from dataclasses import dataclass

from collections import defaultdict
from datetime import datetime, timezone

from . import settings
from .anomalies import (_compute_idle_gap_summary, _detect_cache_flushes,
                        summarize_context_window)
from .attribution import (WRITE_CATEGORIES, attribute_turn_tokens,
                          attribute_write_categories)
from .classify import (_classify_api_error, _classify_tool_error,
                       _classify_user_entry, _is_user_plan_limit_text,
                       _merge_streamed_assistant_entries, _route_tool_error)
from .pricing import calc_cost


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


@dataclass
class SessionFileMeta:
    """Datei-/Herkunfts-Metadaten eines Transcripts, vom Driver geliefert."""
    source_label: str
    file_session_id: str      # Datei-Stem (bei Subagents die agent-Datei)
    project_name: str         # Name des Projekt-Verzeichnisses
    file_size: int = 0
    is_subagent: bool = False
    parent_session_id: str = ""
    agent_id: str = ""
    agent_type: str = ""
    agent_description: str = ""


def absorb_file(sessions, meta, parsed_objs):
    """Faltet die geparsten JSONL-Objekte EINER Transcript-Datei in sessions.

    Herkunftsneutral: der CLI-Driver liefert parsed_objs aus Dateien, der
    Collector-Server aus dem DB-Export. Duplikate (session bereits aus
    anderer Quelle geparst) werden wie bisher uebersprungen - first seen wins.
    """
    source_label = meta.source_label
    file_session_id = meta.file_session_id
    project_name = meta.project_name
    file_size = meta.file_size
    is_subagent = meta.is_subagent
    parent_id = meta.parent_session_id
    sub_agent_id = meta.agent_id
    sub_agent_type = meta.agent_type
    sub_agent_desc = meta.agent_description

    # Skip if this session was already parsed from an earlier
    # source pass (migration, another additional source, or the
    # primary dir). First seen wins: parsing the same transcript
    # again would double count every token and cost.
    if file_session_id in sessions:
        _prev_src = sessions[file_session_id].get("source", settings.SOURCE_LABEL)
        if _prev_src != source_label:
            print(f"      NOTE: {file_session_id} already parsed from "
                  f"source '{_prev_src}'; skipping duplicate in "
                  f"'{source_label}'")
        return

    # Collapse stream-split assistant rows (Claude Code writes
    # one JSONL line per content block, each repeating the same
    # usage) into one entry per response before any accounting,
    # so tokens/cost/calls/message counts are not multiplied by
    # the block count. See _merge_streamed_assistant_entries.
    for obj in _merge_streamed_assistant_entries(parsed_objs):
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


def finalize_sessions(sessions):
    """Subagent-Linking + per-Session-Ableitungen nach dem letzten absorb_file."""
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
    return sessions
