"""Plan-vs-usage comparison, billing-cycle expansion, and tier recommendation."""
import calendar
from datetime import datetime, timedelta, timezone

from . import settings
from .limits import (PLAN_TIER_FACTORS, PRO_CAPACITY_USD_DEFAULT,
                     _normalize_tier_name, _compute_5h_windows, _compute_weekly_buckets,
                     _estimate_5h_window_cap_usd, _detect_5h_fingerprint_events,
                     _iso_to_ms, _dedupe_limit_events, _match_limit_events_to_windows,
                     _count_5h_hits)


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
    if not settings.PLAN_HISTORY:
        # No subscription configured (API-only user): nothing to compare
        # against, and the current-billing block below would crash on
        # PLAN_HISTORY[-1]. The caller treats None as "no plan section".
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    periods = []
    for ph in settings.PLAN_HISTORY:
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
    current_plan = settings.PLAN_HISTORY[-1]
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
    for ph in reversed(settings.PLAN_HISTORY):
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
        for ph in settings.PLAN_HISTORY:
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
        cycle_tier_by_window_idx, settings.PLAN_CAPACITY_OVERRIDE_PRO_USD,
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
