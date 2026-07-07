"""Cache-flush, idle-gap, and 1M-context-window anomaly detection."""
import statistics

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
