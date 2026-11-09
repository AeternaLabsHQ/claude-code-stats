"""Experiment-ID helpers: normalize the IDs Claude Code latches into
transcripts and bucket reply behaviour per (model, ID, day).

Buckets are plain dicts of numbers and string-keyed histograms so they
survive the JSON round trip of the scan cache without any rehydration."""
import math
from datetime import date, datetime, timedelta, timezone

MIN_REPLIES = 200
REL_CHANGE = 0.40
MIN_CHANGED_METRICS = 2
BASELINE_PAD_DAYS = 14
HIST_STEPS = 8  # histogram bins per doubling


def normalize_atis(raw) -> str:
    """Canonical experiment ID: "" for none, segment 1 of a `v1.` value,
    otherwise the raw string stripped."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if raw.startswith("v1."):
        return raw.split(".")[1].strip()
    return raw


def hist_bin(v: float) -> str:
    """Log-scale histogram bin key; "0" for non-positive values."""
    if v <= 0:
        return "0"
    return str(math.floor(math.log2(v) * HIST_STEPS) + 1)


def hist_median(hist: dict):
    """Approximate median of a {bin: count} histogram, or None if empty."""
    items = sorted((int(b), n) for b, n in hist.items() if n > 0)
    total = sum(n for _, n in items)
    if total <= 0:
        return None
    half = total / 2
    seen = 0
    for b, n in items:
        seen += n
        if seen >= half:
            return 2 ** ((b - 0.5) / HIST_STEPS) if b >= 1 else 0.0
    return None


def new_bucket() -> dict:
    return {"replies": 0, "multi_tool": 0, "tool_replies": 0,
            "text_before": 0, "output_tokens": 0, "cost": 0.0,
            "bash_cmds": 0, "out_hist": {}, "bash_hist": {}}


def _bump(hist: dict, key: str, n: int = 1) -> None:
    hist[key] = hist.get(key, 0) + n


def add_reply(bucket: dict, content_blocks: list, output_tokens: int,
              cost: float) -> None:
    """Count one main-thread reply into a bucket."""
    blocks = [b for b in (content_blocks or []) if isinstance(b, dict)]
    tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
    bucket["replies"] += 1
    bucket["output_tokens"] += output_tokens
    bucket["cost"] += cost
    if len(tool_uses) >= 2:
        bucket["multi_tool"] += 1
    if tool_uses:
        bucket["tool_replies"] += 1
    for b in blocks:
        if b.get("type") == "tool_use":
            break
        if b.get("type") == "text" and str(b.get("text") or "").strip():
            bucket["text_before"] += 1
            break
    _bump(bucket["out_hist"], hist_bin(output_tokens))
    for b in tool_uses:
        if b.get("name") == "Bash":
            inp = b.get("input")
            cmd = inp.get("command") if isinstance(inp, dict) else ""
            bucket["bash_cmds"] += 1
            _bump(bucket["bash_hist"],
                  hist_bin(len(cmd) if isinstance(cmd, str) else 0))


def merge_bucket(dst: dict, src: dict) -> None:
    """Add src into dst: sums numbers and histogram counts."""
    for k, v in src.items():
        if isinstance(v, dict):
            h = dst.setdefault(k, {})
            for b, n in v.items():
                _bump(h, b, n)
        else:
            dst[k] = dst.get(k, 0) + v


# ── Summary ────────────────────────────────────────────────────────────────

_BEHAVIOUR_METRICS = ("multi_tool_share", "text_before_share",
                      "median_bash_chars", "median_output_tokens")


def _split_key(key: str):
    model, _, atis = key.rpartition("|")
    return model, atis


def _round(v, nd):
    return None if v is None else round(v, nd)


def _metrics(b: dict) -> dict:
    """Behaviour metrics of a (merged) bucket, unrounded."""
    n = b.get("replies", 0)
    tool = b.get("tool_replies", 0)
    return {
        "multi_tool_share": b.get("multi_tool", 0) / n if n else 0.0,
        "text_before_share": b.get("text_before", 0) / tool if tool else None,
        "median_bash_chars": hist_median(b.get("bash_hist", {})),
        "median_output_tokens": hist_median(b.get("out_hist", {})),
        "cost_per_reply": b.get("cost", 0.0) / n if n else 0.0,
    }


def _rounded_metrics(m: dict) -> dict:
    return {"multi_tool_share": _round(m["multi_tool_share"], 4),
            "text_before_share": _round(m["text_before_share"], 4),
            "median_bash_chars": _round(m["median_bash_chars"], 1),
            "median_output_tokens": _round(m["median_output_tokens"], 1),
            "cost_per_reply": _round(m["cost_per_reply"], 6)}


def _verdict(replies, base_replies, changes) -> str:
    if replies < MIN_REPLIES or base_replies < MIN_REPLIES:
        return "insufficient"
    n = sum(1 for c in changes.values()
            if c is not None and abs(c) >= REL_CHANGE)
    return "changed" if n >= MIN_CHANGED_METRICS else "no_effect"


def session_experiment_ids(sess: dict) -> list:
    """Sorted non-empty experiment IDs seen in a session."""
    exp = sess.get("experiments") if isinstance(sess, dict) else None
    if not isinstance(exp, dict):
        return []
    return sorted({a for a in (_split_key(k)[1] for k in exp) if a})


def _current_slots(dot_claude) -> list:
    """Newest cache slot per model for the current org (never raises)."""
    if not isinstance(dot_claude, dict):
        return []
    slots = dot_claude.get("clientDataCacheSlots")
    if not isinstance(slots, dict):
        return []
    acct = dot_claude.get("oauthAccount")
    org = acct.get("organizationUuid") if isinstance(acct, dict) else None
    best = {}
    for slot in slots.values():
        if not isinstance(slot, dict):
            continue
        model, at = slot.get("model"), slot.get("at")
        if (not isinstance(model, str) or not model
                or isinstance(at, bool) or not isinstance(at, (int, float))):
            continue
        if org and slot.get("org") != org:
            continue
        if model.endswith("[1m]"):
            model = model[:-4]
        if model not in best or at > best[model]["at"]:
            data = slot.get("data")
            atis = data.get("atis") if isinstance(data, dict) else None
            best[model] = {"at": at, "entrypoint": slot.get("entrypoint") or "",
                           "id": normalize_atis(atis)}
    out = []
    for model in sorted(best):
        s = best[model]
        try:
            iso = datetime.fromtimestamp(
                s["at"] / 1000, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            continue
        out.append({"model": model, "entrypoint": s["entrypoint"],
                    "id": s["id"], "at": iso})
    return out


def _parse_day(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def build_experiment_summary(sessions: dict, dot_claude: dict) -> dict:
    """Per-ID behaviour summary against a time-matched same-model baseline
    (ID "" buckets within +-BASELINE_PAD_DAYS of the ID's days)."""
    exp_buckets = {}    # (atis, model) -> {day: merged bucket}
    base_buckets = {}   # model -> {day: merged bucket}
    id_info = {}        # atis -> {"sessions": set, "days": {day: {src: n}}}
    for sid, sess in (sessions or {}).items():
        exp = sess.get("experiments") if isinstance(sess, dict) else None
        if not isinstance(exp, dict):
            continue
        src = sess.get("source") or "unknown"
        for key, by_day in exp.items():
            model, atis = _split_key(key)
            if not isinstance(by_day, dict):
                continue
            for dstr, b in by_day.items():
                if _parse_day(dstr) is None or not b.get("replies"):
                    continue
                target = (base_buckets.setdefault(model, {}) if not atis
                          else exp_buckets.setdefault((atis, model), {}))
                merge_bucket(target.setdefault(dstr, new_bucket()), b)
                if atis:
                    info = id_info.setdefault(
                        atis, {"sessions": set(), "days": {}})
                    info["sessions"].add(sid)
                    cell = info["days"].setdefault(dstr, {})
                    cell[src] = cell.get(src, 0) + b["replies"]

    ids = []
    for atis, info in id_info.items():
        days = {d: dict(sorted(v.items()))
                for d, v in sorted(info["days"].items())}
        models = []
        for (a, model), by_day in exp_buckets.items():
            if a != atis:
                continue
            total = new_bucket()
            for b in by_day.values():
                merge_bucket(total, b)
            first = _parse_day(min(by_day))
            last = _parse_day(max(by_day))
            lo = (first - timedelta(days=BASELINE_PAD_DAYS)).isoformat()
            hi = (last + timedelta(days=BASELINE_PAD_DAYS)).isoformat()
            base = new_bucket()
            for d, b in base_buckets.get(model, {}).items():
                if lo <= d <= hi:
                    merge_bucket(base, b)
            m, bm = _metrics(total), _metrics(base)
            changes = {}
            for k in _BEHAVIOUR_METRICS:
                if m[k] is None or not bm[k] or bm[k] <= 0:
                    changes[k] = None
                else:
                    changes[k] = (m[k] - bm[k]) / bm[k]
            models.append({
                "model": model, "replies": total["replies"],
                "metrics": _rounded_metrics(m),
                "baseline": {"replies": base["replies"], "from": lo,
                             "to": hi, "metrics": _rounded_metrics(bm)},
                "changes": {k: _round(v, 4) for k, v in changes.items()},
                "verdict": _verdict(total["replies"], base["replies"],
                                    changes),
            })
        models.sort(key=lambda r: (-r["replies"], r["model"]))
        ids.append({
            "id": atis, "short": atis[:3],
            "first_day": min(days), "last_day": max(days),
            "sources": sorted({s for v in days.values() for s in v}),
            "sessions": len(info["sessions"]),
            "days": days, "models": models,
        })
    ids.sort(key=lambda e: (e["first_day"], e["id"]), reverse=True)
    return {
        "has_data": bool(ids),
        "thresholds": {"min_replies": MIN_REPLIES, "rel_change": REL_CHANGE,
                       "min_changed_metrics": MIN_CHANGED_METRICS,
                       "baseline_pad_days": BASELINE_PAD_DAYS},
        "current": _current_slots(dot_claude),
        "ids": ids,
    }
