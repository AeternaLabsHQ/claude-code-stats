"""Per-model USD pricing tables and cost calculation."""
import re

# ── Pricing (USD per 1M tokens) ───────────────────────────────────────────
PRICING = {
    # Fable 5 (flagship tier, above Opus)
    "claude-fable-5": {
        "input": 10.00, "output": 50.00,
        "cache_read": 1.00, "cache_write_5m": 12.50, "cache_write_1h": 20.00,
        "display": "Fable 5"
    },
    # Sonnet 5 — standard pricing. An introductory $2/$10 rate applied through
    # 2026-08-31; standard rates below took effect 2026-09-01.
    "claude-sonnet-5": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 5"
    },
    # Claude 4.8
    "claude-opus-4-8": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.8"
    },
    # Claude 4.7
    "claude-opus-4-7": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.7"
    },
    # Claude 4.6
    "claude-opus-4-6": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.6"
    },
    "claude-sonnet-4-6": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4.6"
    },
    # Claude 4.5
    "claude-opus-4-5-20251101": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.5"
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4.5"
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.00, "output": 5.00,
        "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00,
        "display": "Haiku 4.5"
    },
    # Claude 4.1
    "claude-opus-4-1-20250805": {
        "input": 15.00, "output": 75.00,
        "cache_read": 1.50, "cache_write_5m": 18.75, "cache_write_1h": 30.00,
        "display": "Opus 4.1"
    },
    # Claude 4.0
    "claude-opus-4-20250514": {
        "input": 15.00, "output": 75.00,
        "cache_read": 1.50, "cache_write_5m": 18.75, "cache_write_1h": 30.00,
        "display": "Opus 4"
    },
    "claude-sonnet-4-20250514": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4"
    },
    # Claude 3.7
    "claude-sonnet-3-7-20250219": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 3.7"
    },
    # Claude 3.5
    "claude-haiku-3-5-20241022": {
        "input": 0.80, "output": 4.00,
        "cache_read": 0.08, "cache_write_5m": 1.00, "cache_write_1h": 1.60,
        "display": "Haiku 3.5"
    },
    # Claude 3
    "claude-3-opus-20240229": {
        "input": 15.00, "output": 75.00,
        "cache_read": 1.50, "cache_write_5m": 18.75, "cache_write_1h": 30.00,
        "display": "Opus 3"
    },
    "claude-3-haiku-20240307": {
        "input": 0.25, "output": 1.25,
        "cache_read": 0.03, "cache_write_5m": 0.30, "cache_write_1h": 0.50,
        "display": "Haiku 3"
    },
}

# Fallback for unknown models (use mid-range pricing)
DEFAULT_PRICING = {
    "input": 3.00, "output": 15.00,
    "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
    "display": "Unknown"
}


def _version(maj, minor):
    """Render a version string, dropping a ".0" minor.

    Anthropic names a ".0" model bare-major ("Opus 4", never "Opus 4.0"), and
    the curated table follows suit, so a "-0" alias (claude-opus-4-0) must
    collapse onto the bare-major display rather than splitting off as "Opus 4.0".
    """
    return f"{maj}.{minor}" if minor and minor != "0" else maj


def derive_model_display(model_id):
    """Derive a human-friendly display name from a raw Claude model id.

    Handles both naming conventions seen in the data:
      - newer (family first):  claude-<family>-<maj>[-<min>][-<YYYYMMDD>]
                               e.g. claude-opus-4-8, claude-opus-4-20250514
      - older (version first): claude-<maj>[-<min>]-<family>[-<YYYYMMDD>]
                               e.g. claude-3-opus, claude-3-5-haiku

    Renders "<Family> <maj>[.<min>]" with a Title-cased family, strips a
    trailing 8-digit date stamp and a trailing variant marker like "[1m]"
    (1M-context enablement), and degrades gracefully (cleaned raw form, or the
    raw value) when it cannot parse. Never raises. This lets a brand-new model
    be named correctly without touching the PRICING table.
    """
    if not isinstance(model_id, str):
        return str(model_id)

    raw = model_id.strip()
    if not raw:
        return model_id

    # Synthetic / non-model markers like "<synthetic>" -> "Synthetic".
    m = re.fullmatch(r"<\s*([^<>]+?)\s*>", raw)
    if m:
        return m.group(1).strip().title()

    # Drop trailing variant markers like "[1m]" (the 1M-context build) so a
    # variant collapses onto its base model instead of splitting off as a
    # mangled, separately-priced phantom. Repeats to absorb stacked markers.
    raw = re.sub(r"(?:\s*\[[^\]]*\]\s*)+$", "", raw).strip()

    s = raw.lower()
    if s.startswith("claude-"):
        body = s[len("claude-"):]
        body = re.sub(r"-\d{8}$", "", body)  # drop a trailing date stamp

        # Convention A (newer): family then version -> opus-4-8, opus-4
        m = re.fullmatch(r"([a-z]+)-(\d+)(?:-(\d+))?", body)
        if not m:
            # Convention B (older): version then family -> 3-opus, 3-5-haiku
            m = re.fullmatch(r"(\d+)(?:-(\d+))?-([a-z]+)", body)
            if m:
                maj, minor, family = m.group(1), m.group(2), m.group(3)
                return f"{family.title()} {_version(maj, minor)}"
        else:
            family, maj, minor = m.group(1), m.group(2), m.group(3)
            return f"{family.title()} {_version(maj, minor)}"

    # Unparseable: clean the raw id but never crash.
    cleaned = re.sub(r"-\d{8}$", "", raw)
    cleaned = re.sub(r"^claude-", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("-", " ").strip()
    return cleaned.title() if cleaned else model_id


def get_model_display(model_id):
    if model_id in PRICING:
        return PRICING[model_id]["display"]
    # Unknown model: derive a name from the id rather than collapsing to
    # "Unknown", so a newly-shipped model is identifiable in the dashboard.
    return derive_model_display(model_id)


def pricing_for_display(display_name):
    """Resolve a display name back to its PRICING entry, or DEFAULT_PRICING.

    Used by the cost-by-type / cache-savings aggregations, which key on the
    display name. An unmatched display (a genuinely unknown model) falls back to
    DEFAULT_PRICING instead of mispricing it at the first table entry's rates.
    """
    for entry in PRICING.values():
        if entry["display"] == display_name:
            return entry
    return DEFAULT_PRICING


def resolve_pricing(model_id):
    """Resolve a raw model id to its PRICING entry, or DEFAULT_PRICING.

    Single source of truth for per-model rates, tolerant of variant id forms
    that are not literal table keys: the "[1m]" 1M-context suffix, date stamps,
    and dated/undated mismatches (the table mixes both). It first tries an exact
    key, then matches on the derived display name so every variant of a known
    model lands on that model's rates. Used by calc_cost(), and mirrored by the
    display-keyed cost_by_type aggregation, so all cost paths agree.
    """
    if model_id in PRICING:
        return PRICING[model_id]
    return pricing_for_display(get_model_display(model_id))


def build_pricing_warnings(model_ids):
    """From the raw model ids seen in the data, list the Claude models whose
    cost is only an estimate because they resolve to DEFAULT_PRICING.

    Returns a de-duplicated, display-sorted list of {model_id, display}. Gated
    on resolve_pricing() (not literal table membership) so it agrees with the
    actual cost computation: a variant of a known model (a "[1m]" or dated form)
    is priced correctly and is NOT flagged. De-duplicated on display, so the
    several id forms of one unknown model produce a single warning. Internal
    markers like "<synthetic>", the "unknown" default, and non-Claude ids are
    left alone.
    """
    seen = {}
    # Sort the candidate ids so the surfaced model_id is deterministic (callers
    # pass a set) and the canonical base id wins over its dated/"[1m]" siblings
    # (e.g. "claude-opus-5-0" sorts before "...-20990101" and "...[1m]").
    candidates = sorted(
        mid for mid in model_ids
        if isinstance(mid, str) and mid.startswith("claude-")
    )
    for mid in candidates:
        if resolve_pricing(mid) is not DEFAULT_PRICING:
            continue  # priced via an exact or variant match of a known model
        display = get_model_display(mid)
        if display in seen:
            continue
        seen[display] = {"model_id": mid, "display": display}
    return sorted(seen.values(), key=lambda w: w["display"])


def calc_cost(model_id, usage):
    """Calculate cost for a single API call based on usage tokens.

    Cache writes are priced per TTL: 5m writes at 1.25x input
    (cache_write_5m), 1h writes at 2x input (cache_write_1h). Transcripts
    without the usage.cache_creation breakdown fall back to pricing all
    cache creation tokens at the 5m rate, matching Claude Code's own cost
    calculation."""
    p = resolve_pricing(model_id)

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    cache_info = usage.get("cache_creation") or {}
    # 1h tokens are a subset of cache_creation; clamp defensively so a
    # malformed transcript can never yield negative 5m tokens.
    cache_1h = min(cache_info.get("ephemeral_1h_input_tokens", 0), cache_creation)
    cache_5m = cache_creation - cache_1h

    cost = (
        input_tokens * p["input"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
        + cache_read * p["cache_read"] / 1_000_000
        + cache_5m * p["cache_write_5m"] / 1_000_000
        + cache_1h * p["cache_write_1h"] / 1_000_000
    )
    return cost
