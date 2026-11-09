"""Experiment-ID helpers: normalize the IDs Claude Code latches into
transcripts and bucket reply behaviour per (model, ID, day).

Buckets are plain dicts of numbers and string-keyed histograms so they
survive the JSON round trip of the scan cache without any rehydration."""
import math

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
