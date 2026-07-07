"""Aggregation entry point: turns parsed sessions into the dashboard data dict."""
from collections import defaultdict
from datetime import datetime, timezone

from . import settings
from .limits import (_compute_5h_windows, _compute_weekly_buckets,
                     _dedupe_limit_events, _detect_5h_fingerprint_events)
from .plan_analysis import build_plan_analysis
from .attribution import WRITE_CATEGORIES
from .pricing import build_pricing_warnings, get_model_display, pricing_for_display
from .sessions import split_session_by_day


def project_display_name(project_path):
    """Extract a short display name from a project path."""
    if not project_path:
        return "Unknown"
    p = project_path.replace("\\", "/")
    parts = p.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else project_path


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
            if _day_in > 0 and per_day_messages.get(_day, 0) >= settings.CACHE_EFF_MIN_MESSAGES:
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
        ps["sources"].add(sess.get("source", settings.SOURCE_LABEL))

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
            "source": sess.get("source", settings.SOURCE_LABEL),
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

    weekday_names = settings.LOCALE.get("weekdays", ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
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
        "locale": settings.LOCALE,
        "week_anchor": settings.WEEK_ANCHOR,
        "account": {
            "name": settings.DISPLAY_NAME or account.get("displayName", ""),
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
