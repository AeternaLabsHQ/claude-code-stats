"""Experiment-ID helpers: normalize the IDs Claude Code latches into
transcripts and bucket reply behaviour per (model, ID, day).

Buckets are plain dicts of numbers and string-keyed histograms so they
survive the JSON round trip of the scan cache without any rehydration."""
import json
import math
import re
from datetime import date, datetime, timedelta, timezone

from .expstats import compare, median_stat, ratio_stat, values_median_stat

MIN_REPLIES = 200
REL_CHANGE = 0.40
MIN_CHANGED_METRICS = 2
BASELINE_PAD_DAYS = 14
HIST_STEPS = 32  # histogram bins per doubling
MIN_SUPPORT = 30  # events a behaviour metric needs before its change counts
MIN_SESSIONS = 5  # sessions each side needs before a verdict
ALPHA = 0.05  # significance level a behaviour change must reach
THINK_MIN_REPLIES = 20  # thinking-table cells need this many reported replies
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max", "unknown")
LATE_CUTOFF_DAYS = 7  # replies later than this after session start are not bucketed
ACTIVE_GAP_MS = 30 * 60 * 1000  # longer gaps between replies are idle time
CORRECTION_MAX_CHARS = 160  # longer prompts are never counted as corrections
DEFAULT_CORRECTION_WORDS = [
    "nein", "no", "falsch", "wrong", "nochmal", "again", "revert",
    "rückgängig", "undo", "stimmt nicht", "funktioniert nicht",
    "doesn't work"]
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def normalize_atis(raw) -> str:
    """Canonical experiment ID: "" for none, segment 1 of a `v1.` value,
    otherwise the raw string stripped."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if raw.startswith("v1."):
        return raw.split(".")[1].strip()
    return raw


def _part(v) -> str:
    """Key component: the string itself, "" for anything else."""
    return v.replace("|", "/") if isinstance(v, str) else ""


def bucket_key(model, atis, entrypoint, effort) -> str:
    """Bucket key "model|atis|entrypoint|effort"; missing parts are blank."""
    return "|".join((_part(model), _part(atis), _part(entrypoint),
                     _part(effort)))


def split_key(key: str) -> tuple:
    """(model, atis, entrypoint, effort) of a bucket key. A legacy two-part
    "model|atis" key yields blank entrypoint and effort."""
    parts = key.split("|", 3)
    parts += [""] * (4 - len(parts))
    return tuple(parts)


def is_interactive(entrypoint: str) -> bool:
    """Whether an entrypoint is a person at a terminal or desktop app
    rather than an SDK-driven run."""
    return not entrypoint.startswith("sdk")


def is_correction(text: str, words: list) -> bool:
    """Short prompt containing a correction word on word boundaries."""
    text = (text or "").strip()
    if not text or len(text) > CORRECTION_MAX_CHARS:
        return False
    return any(
        re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text,
                  re.IGNORECASE)
        for w in words if w)


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
            "bash_cmds": 0, "out_hist": {}, "bash_hist": {},
            "tool_calls": 0, "prompts": 0, "corrections": 0,
            "interrupts": 0, "rejected": 0, "tool_errors": 0,
            "repeat_calls": 0, "edit_calls": 0, "re_edits": 0,
            "active_ms": 0, "think_replies": 0, "think_tokens": 0,
            "think_hist": {}}


def _bump(hist: dict, key: str, n: int = 1) -> None:
    hist[key] = hist.get(key, 0) + n


def _call_key(block: dict) -> str:
    try:
        inp = json.dumps(block.get("input"), sort_keys=True, default=str)
    except (TypeError, ValueError):
        inp = repr(block.get("input"))
    return str(block.get("name")) + inp


def add_reply(bucket: dict, content_blocks: list, output_tokens: int,
              cost: float, thinking_tokens=None, active_ms: int = 0,
              seen_calls=None, seen_paths=None) -> None:
    """Count one main-thread reply into a bucket.

    thinking_tokens: reported thinking tokens, None when the log has none
    (such replies stay out of the thinking counts). seen_calls / seen_paths:
    per-file sets of earlier tool calls and edited paths, enabling the
    repeat-call and re-edit counts."""
    blocks = [b for b in (content_blocks or []) if isinstance(b, dict)]
    tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
    bucket["replies"] += 1
    bucket["output_tokens"] += output_tokens
    bucket["cost"] += cost
    if len(tool_uses) >= 2:
        bucket["multi_tool"] += 1
    if tool_uses:
        bucket["tool_replies"] += 1
    if tool_uses:
        # Once per reply: some non-blank text precedes the first tool call.
        for b in blocks:
            if b.get("type") == "tool_use":
                break
            if b.get("type") == "text" and str(b.get("text") or "").strip():
                bucket["text_before"] += 1
                break
    _bump(bucket["out_hist"], hist_bin(output_tokens))
    bucket["tool_calls"] += len(tool_uses)
    bucket["active_ms"] += active_ms
    if isinstance(thinking_tokens, int) and not isinstance(
            thinking_tokens, bool):
        bucket["think_replies"] += 1
        bucket["think_tokens"] += thinking_tokens
        _bump(bucket["think_hist"], hist_bin(thinking_tokens))
    if seen_calls is not None:
        for b in tool_uses:
            ck = _call_key(b)
            if ck in seen_calls:
                bucket["repeat_calls"] += 1
            seen_calls.add(ck)
    if seen_paths is not None:
        for b in tool_uses:
            if b.get("name") not in EDIT_TOOLS:
                continue
            bucket["edit_calls"] += 1
            inp = b.get("input")
            path = (inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(inp, dict) else None)
            if isinstance(path, str) and path:
                if path in seen_paths:
                    bucket["re_edits"] += 1
                seen_paths.add(path)
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


def _field(name):
    return lambda b: b.get(name, 0)


def _active_min(b):
    return b.get("active_ms", 0) / 60000


# Display order. stat: ("ratio", numerator, denominator), ("median", hist)
# or ("session", fn of a session's merged bucket). Groups behaviour,
# context and quality are effort-standardized per row: both sides are
# weighted to the ID side's mix of that row's denominator over the effort
# levels where both sides have one. The session group uses every
# interactive reply, unweighted.
METRICS = [
    {"key": "multi_tool_share", "group": "behaviour", "kind": "share",
     "stat": ("ratio", "multi_tool", "replies")},
    {"key": "text_before_share", "group": "behaviour", "kind": "share",
     "stat": ("ratio", "text_before", "tool_replies")},
    {"key": "median_bash_chars", "group": "behaviour", "kind": "int",
     "stat": ("median", "bash_hist")},
    {"key": "median_output_tokens", "group": "behaviour", "kind": "int",
     "stat": ("median", "out_hist")},
    {"key": "cost_per_reply", "group": "context", "kind": "usd",
     "stat": ("ratio", "cost", "replies")},
    {"key": "session_cost", "group": "session", "kind": "usd",
     "stat": ("session", _field("cost"))},
    {"key": "session_replies", "group": "session", "kind": "int",
     "stat": ("session", _field("replies"))},
    {"key": "session_prompts", "group": "session", "kind": "int",
     "stat": ("session", _field("prompts"))},
    {"key": "session_tool_calls", "group": "session", "kind": "int",
     "stat": ("session", _field("tool_calls"))},
    {"key": "session_active_min", "group": "session", "kind": "int",
     "stat": ("session", _active_min)},
    {"key": "cost_per_prompt", "group": "session", "kind": "usd",
     "stat": ("ratio", "cost", "prompts")},
    {"key": "tool_error_rate", "group": "quality", "kind": "rate",
     "stat": ("ratio", "tool_errors", "tool_calls")},
    {"key": "repeat_call_rate", "group": "quality", "kind": "rate",
     "stat": ("ratio", "repeat_calls", "tool_calls")},
    {"key": "rejected_rate", "group": "quality", "kind": "rate",
     "stat": ("ratio", "rejected", "tool_calls")},
    {"key": "interrupt_rate", "group": "quality", "kind": "rate",
     "stat": ("ratio", "interrupts", "prompts")},
    {"key": "correction_rate", "group": "quality", "kind": "rate",
     "stat": ("ratio", "corrections", "prompts")},
    {"key": "re_edit_rate", "group": "quality", "kind": "rate",
     "stat": ("ratio", "re_edits", "edit_calls")},
]

_DECIMALS = {"share": 4, "rate": 4, "int": 1, "usd": 6}
_SUPPORT_KEYS = ("multi_tool", "tool_replies", "text_before", "bash_cmds")


def _round(v, nd):
    return None if v is None else round(v, nd)


def _round_p(p):
    return None if p is None else float(f"{p:.3g}")


def _supported(k: str, s: dict, bs: dict) -> bool:
    """Whether behaviour metric k has enough events on the ID side (s) and
    the baseline side (bs) for its change to mean anything."""
    if k == "multi_tool_share":
        return max(s["multi_tool"], bs["multi_tool"]) >= MIN_SUPPORT
    if k == "text_before_share":
        return (min(s["tool_replies"], bs["tool_replies"]) >= MIN_SUPPORT
                and max(s["text_before"], bs["text_before"]) >= MIN_SUPPORT)
    if k == "median_bash_chars":
        return min(s["bash_cmds"], bs["bash_cmds"]) >= MIN_SUPPORT
    return True  # median_output_tokens: the MIN_REPLIES gate is enough


def _merged(buckets: list) -> dict:
    """One bucket for a list of buckets; a single one is returned as is
    (callers only read it), several are merged into a fresh bucket."""
    if len(buckets) == 1:
        return buckets[0]
    out = new_bucket()
    for b in buckets:
        merge_bucket(out, b)
    return out


def _mix(units: list) -> dict:
    """Replies per effort stratum over all units."""
    out = {}
    for u in units:
        for s, b in u.items():
            out[s] = out.get(s, 0) + b.get("replies", 0)
    return dict(sorted(out.items()))


def _support_totals(units: list) -> dict:
    out = {k: 0 for k in _SUPPORT_KEYS}
    for u in units:
        for b in u.values():
            for k in _SUPPORT_KEYS:
                out[k] += b.get(k, 0)
    return out


def _ratio_units(units: list, num: str, den: str) -> list:
    return [{s: (b.get(num, 0), b.get(den, 0)) for s, b in u.items()}
            for u in units]


def _hist_units(units: list, field: str) -> list:
    return [{s: b.get(field) or {} for s, b in u.items()} for u in units]


def _hist_size(hist) -> int:
    return sum(n for n in (hist or {}).values() if n > 0)


def _row_weights(id_units: list, base_units: list, size) -> dict:
    """Weights of a standardized row: the ID side's share of the row's
    denominator (size of a bucket) per effort stratum, over the strata
    where both sides have a non-zero denominator."""
    id_x, base_x = {}, {}
    for units, acc in ((id_units, id_x), (base_units, base_x)):
        for u in units:
            for s, b in u.items():
                acc[s] = acc.get(s, 0) + size(b)
    strata = [s for s in id_x if id_x[s] > 0 and base_x.get(s, 0) > 0]
    total = sum(id_x[s] for s in strata)
    return {s: id_x[s] / total for s in sorted(strata)}


def _restrict(units: list, strata) -> list:
    return [{s: u[s] for s in strata if s in u} for u in units]


def _metric_row(m: dict, id_side: dict, base_side: dict) -> dict:
    """One comparison row. A side is {"all": units, "totals": merged
    bucket per unit}. Standardized rows apply the same per-row weights to
    both sides, so the ID side's estimate is its pooled value over the
    strata the row keeps."""
    stat = m["stat"]
    id_r = base_r = None
    if stat[0] == "session":
        a = values_median_stat([stat[1](t) for t in id_side["totals"]])
        b = values_median_stat([stat[1](t) for t in base_side["totals"]])
        cmp, n, base_n = compare(a, b, "median"), a["n"], b["n"]
    elif stat[0] == "ratio" and m["group"] == "session":
        a = ratio_stat(_ratio_units(id_side["all"], stat[1], stat[2]))
        b = ratio_stat(_ratio_units(base_side["all"], stat[1], stat[2]))
        cmp, n, base_n = compare(a, b, "ratio"), int(a["x"]), int(b["x"])
    elif stat[0] == "ratio":
        den = stat[2]
        w = _row_weights(id_side["all"], base_side["all"],
                         lambda bk: bk.get(den, 0))
        id_r = _restrict(id_side["all"], w)
        base_r = _restrict(base_side["all"], w)
        a = ratio_stat(_ratio_units(id_r, stat[1], den), w)
        b = ratio_stat(_ratio_units(base_r, stat[1], den), w)
        cmp, n, base_n = compare(a, b, "ratio"), int(a["x"]), int(b["x"])
    else:
        field = stat[1]
        w = _row_weights(id_side["all"], base_side["all"],
                         lambda bk: _hist_size(bk.get(field)))
        id_r = _restrict(id_side["all"], w)
        base_r = _restrict(base_side["all"], w)
        a = median_stat(_hist_units(id_r, field), w, steps=HIST_STEPS)
        b = median_stat(_hist_units(base_r, field), w, steps=HIST_STEPS)
        cmp, n, base_n = compare(a, b, "median"), a["n"], b["n"]
    nd = _DECIMALS[m["kind"]]
    row = {"key": m["key"], "group": m["group"], "kind": m["kind"],
           "base": _round(b["est"], nd), "value": _round(a["est"], nd),
           "change": _round(cmp["change"], 4), "lo": _round(cmp["lo"], 4),
           "hi": _round(cmp["hi"], 4), "p": _round_p(cmp["p"]),
           "n": n, "base_n": base_n, "comparable": False}
    if m["group"] == "behaviour":
        # Judged only with enough events in the strata the row kept, and
        # a non-zero baseline (a move away from zero has no relative
        # change).
        row["comparable"] = (row["value"] is not None
                             and row["base"] is not None
                             and row["base"] > 0
                             and _supported(m["key"],
                                            _support_totals(id_r),
                                            _support_totals(base_r)))
    return row


def _verdict(rows: list, id_replies: int, base_replies: int,
             id_sessions: int, base_sessions: int):
    """(verdict, reason). Judged on the rounded row values, so the card
    and its highlighted rows always agree."""
    if id_replies < MIN_REPLIES or base_replies < MIN_REPLIES:
        return "insufficient", "few_replies"
    if id_sessions < MIN_SESSIONS or base_sessions < MIN_SESSIONS:
        return "insufficient", "few_sessions"
    judged = [r for r in rows if r["group"] == "behaviour" and r["comparable"]]
    if len(judged) < MIN_CHANGED_METRICS:
        return "insufficient", "few_metrics"
    moved = sum(1 for r in judged
                if r["change"] is not None and abs(r["change"]) >= REL_CHANGE
                and r["p"] is not None and r["p"] < ALPHA)
    return ("changed" if moved >= MIN_CHANGED_METRICS else "no_effect"), None


def _short_ids(ids) -> dict:
    """Shortest prefix (at least 3 chars) no other ID starts with; the
    full ID when it is itself a prefix of another."""
    ids = list(ids)
    out = {}
    for a in ids:
        others = [o for o in ids if o != a]
        out[a] = a
        for n in range(3, len(a) + 1):
            if not any(o.startswith(a[:n]) for o in others):
                out[a] = a[:n]
                break
    return out


def _day_of_ms(v):
    """UTC day of an epoch-ms timestamp, None for anything else."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date(
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def session_experiment_ids(sess: dict) -> list:
    """Sorted non-empty experiment IDs seen in a session."""
    exp = sess.get("experiments") if isinstance(sess, dict) else None
    if not isinstance(exp, dict):
        return []
    return sorted({a for a in (split_key(k)[1] for k in exp) if a})


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




def _collect(sessions: dict) -> dict:
    """One pass over all sessions: the per-ID timeline (every reply) and
    the interactive per-session units both sides of a card are built from.
    Bucket lists are merged lazily, stored buckets are never mutated."""
    acc = {
        "id_info": {},     # atis -> {"sessions": set, "days": {day: {src: n}}}
        "span": {},        # model -> [first day, last day], any bucket
        "id_units": {},    # (atis, model) -> {sid: {stratum: [bucket]}}
        "id_first": {},    # (atis, model) -> {sid: first day}
        "id_range": {},    # (atis, model) -> [first day, last day]
        "id_eps": {},      # (atis, model) -> {entrypoint: replies}
        "base": {},        # model -> {sid: {day: {stratum: [bucket]}}}
        "base_eps": {},    # model -> {day: {entrypoint: replies}}
        "base_sdk": {},    # model -> {day: replies}
        "id_late": {},     # (atis, model) -> late replies
        "base_late": {},   # model -> {sid: late replies}
        "starts": {},      # sid -> UTC day of exp_start_ms or None
        "think": {},       # (atis, model, stratum) -> [replies, tokens, hist]
    }
    for sid, sess in (sessions or {}).items():
        exp = sess.get("experiments") if isinstance(sess, dict) else None
        if not isinstance(exp, dict):
            continue
        src = sess.get("source") or "unknown"
        acc["starts"][sid] = _day_of_ms(sess.get("exp_start_ms"))
        for key, by_day in exp.items():
            if not isinstance(key, str) or not isinstance(by_day, dict):
                continue
            model, atis, ep, effort = split_key(key)
            inter = is_interactive(ep)
            stratum = effort or "unknown"
            for dstr, b in by_day.items():
                if (not isinstance(b, dict) or _parse_day(dstr) is None
                        or not b.get("replies")):
                    continue
                n = b["replies"]
                span = acc["span"].setdefault(model, [dstr, dstr])
                span[0] = min(span[0], dstr)
                span[1] = max(span[1], dstr)
                if inter and b.get("think_replies"):
                    t = acc["think"].setdefault(
                        (atis, model, stratum), [0, 0, {}])
                    t[0] += b["think_replies"]
                    t[1] += b.get("think_tokens", 0)
                    for hb, hn in (b.get("think_hist") or {}).items():
                        _bump(t[2], hb, hn)
                if atis:
                    info = acc["id_info"].setdefault(
                        atis, {"sessions": set(), "days": {}})
                    info["sessions"].add(sid)
                    cell = info["days"].setdefault(dstr, {})
                    cell[src] = cell.get(src, 0) + n
                    if not inter:
                        continue
                    k = (atis, model)
                    acc["id_units"].setdefault(k, {}).setdefault(
                        sid, {}).setdefault(stratum, []).append(b)
                    first = acc["id_first"].setdefault(k, {})
                    if sid not in first or dstr < first[sid]:
                        first[sid] = dstr
                    rng = acc["id_range"].setdefault(k, [dstr, dstr])
                    rng[0] = min(rng[0], dstr)
                    rng[1] = max(rng[1], dstr)
                    eps = acc["id_eps"].setdefault(k, {})
                    eps[ep] = eps.get(ep, 0) + n
                elif inter:
                    acc["base"].setdefault(model, {}).setdefault(
                        sid, {}).setdefault(dstr, {}).setdefault(
                        stratum, []).append(b)
                    eps = acc["base_eps"].setdefault(model, {}).setdefault(
                        dstr, {})
                    eps[ep] = eps.get(ep, 0) + n
                else:
                    sdk = acc["base_sdk"].setdefault(model, {})
                    sdk[dstr] = sdk.get(dstr, 0) + n
        late = sess.get("experiments_late")
        if not isinstance(late, dict):
            continue
        for key, n in late.items():
            if (not isinstance(key, str) or isinstance(n, bool)
                    or not isinstance(n, int) or n <= 0):
                continue
            model, atis, ep, _ = split_key(key)
            if not is_interactive(ep):
                continue
            if atis:
                acc["id_late"][(atis, model)] = (
                    acc["id_late"].get((atis, model), 0) + n)
            else:
                per = acc["base_late"].setdefault(model, {})
                per[sid] = per.get(sid, 0) + n
    return acc


def _side(units: list) -> dict:
    return {"all": units,
            "totals": [_merged(list(u.values())) for u in units]}


def _card(acc: dict, atis: str, model: str) -> dict:
    """Comparison card of one ID and model against the interactive,
    effort-standardized baseline of the same model."""
    k = (atis, model)
    by_sid = acc["id_units"][k]
    sids = sorted(by_sid)
    id_units = [{s: _merged(bs) for s, bs in by_sid[sid].items()}
                for sid in sids]
    first_day, last_day = acc["id_range"][k]
    # Padded window, clamped to the days this model has data at all
    # (any ID), so it never reaches before the logs or into the future.
    span = acc["span"][model]
    lo = max(span[0], (_parse_day(first_day) - timedelta(
        days=BASELINE_PAD_DAYS)).isoformat())
    hi = min(span[1], (_parse_day(last_day) + timedelta(
        days=BASELINE_PAD_DAYS)).isoformat())

    base_sids, base_units = [], []
    for sid, days in acc["base"].get(model, {}).items():
        strata = {}
        for d, cell in days.items():
            if lo <= d <= hi:
                for s, bs in cell.items():
                    strata.setdefault(s, []).extend(bs)
        if strata:
            base_sids.append(sid)
            base_units.append({s: _merged(bs) for s, bs in strata.items()})
    base_eps, base_sdk = {}, 0
    for d, eps in acc["base_eps"].get(model, {}).items():
        if lo <= d <= hi:
            for ep, n in eps.items():
                base_eps[ep] = base_eps.get(ep, 0) + n
    for d, n in acc["base_sdk"].get(model, {}).items():
        if lo <= d <= hi:
            base_sdk += n

    # Common support: effort strata with replies on both sides. It gates
    # the verdict (replies, sessions) and gives unmatched_replies; each
    # standardized row picks its own strata and weights (_row_weights).
    id_mix, base_mix = _mix(id_units), _mix(base_units)
    common = [s for s in id_mix if id_mix[s] > 0 and base_mix.get(s, 0) > 0]
    id_common = sum(id_mix[s] for s in common)
    base_common = sum(base_mix[s] for s in common)
    id_side, base_side = _side(id_units), _side(base_units)
    rows = [_metric_row(m, id_side, base_side) for m in METRICS]
    verdict, reason = _verdict(
        rows, id_common, base_common,
        sum(1 for u in id_units if any(s in u for s in common)),
        sum(1 for u in base_units if any(s in u for s in common)))

    starts = [acc["starts"].get(sid) or acc["id_first"][k][sid]
              for sid in sids]
    base_late = acc["base_late"].get(model, {})
    replies = sum(id_mix.values())
    return {
        "model": model, "replies": replies, "sessions": len(sids),
        "first_day": first_day, "last_day": last_day,
        "session_start_from": min(starts), "session_start_to": max(starts),
        "entrypoints": dict(sorted(acc["id_eps"][k].items())),
        "base_entrypoints": dict(sorted(base_eps.items())),
        "base_sdk_replies": base_sdk,
        "effort_mix": id_mix, "base_effort_mix": base_mix,
        "unmatched_replies": replies - id_common,
        "late_replies": acc["id_late"].get(k, 0),
        "base_late_replies": sum(base_late.get(sid, 0) for sid in base_sids),
        "baseline": {"replies": sum(base_mix.values()),
                     "sessions": len(base_sids), "from": lo, "to": hi},
        "rows": rows, "verdict": verdict, "reason": reason,
    }


def _thinking(acc: dict, ids: list) -> list:
    """Thinking tokens per model, ID and effort level (interactive, all
    days). Models are those with at least one card; cells below
    THINK_MIN_REPLIES reported replies, empty rows and empty models are
    left out. Rows: no ID first, then IDs newest first."""
    models = sorted({m for (_, m) in acc["id_units"]})
    order = [("", "")] + [(e["id"], e["short"]) for e in ids]
    out = []
    for model in models:
        rows = []
        for atis, short in order:
            cells = {}
            for stratum in EFFORT_ORDER:
                t = acc["think"].get((atis, model, stratum))
                if not t or t[0] < THINK_MIN_REPLIES:
                    continue
                med = hist_median(t[2])
                if med is None:  # counts without a histogram: unusable
                    continue
                cells[stratum] = {
                    "replies": t[0],
                    "median": round(med, 1),
                    "mean": round(t[1] / t[0], 1)}
            if cells:
                rows.append({"id": atis, "short": short, "cells": cells})
        if rows:
            out.append({"model": model, "rows": rows})
    return out


def build_experiment_summary(sessions: dict, dot_claude: dict) -> dict:
    """Per-ID behaviour against a same-model baseline (ID "" replies within
    +-BASELINE_PAD_DAYS of the ID's days). Both sides are interactive only,
    the baseline is standardized to the ID side's effort mix, and every
    p-value and CI treats the session as the statistical unit."""
    acc = _collect(sessions)
    shorts = _short_ids(acc["id_info"])
    ids = []
    for atis, info in acc["id_info"].items():
        days = {d: dict(sorted(v.items()))
                for d, v in sorted(info["days"].items())}
        models = [_card(acc, a, model) for (a, model) in acc["id_units"]
                  if a == atis]
        models.sort(key=lambda r: (-r["replies"], r["model"]))
        ids.append({
            "id": atis, "short": shorts[atis],
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
                       "baseline_pad_days": BASELINE_PAD_DAYS,
                       "min_support": MIN_SUPPORT,
                       "min_sessions": MIN_SESSIONS, "alpha": ALPHA,
                       "late_cutoff_days": LATE_CUTOFF_DAYS,
                       "active_gap_min": ACTIVE_GAP_MS // 60000,
                       "correction_max_chars": CORRECTION_MAX_CHARS},
        "current": _current_slots(dot_claude),
        "ids": ids,
        "thinking": _thinking(acc, ids),
    }
