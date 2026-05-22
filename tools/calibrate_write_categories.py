#!/usr/bin/env python3
"""Calibrate the char-count heuristic used by extract_stats.write_categories.

extract_stats.py splits each assistant message's output_tokens across write
categories (screen_text / thinking / file_writes / bash_commands / tool_inputs)
by char-weight. Prose has roughly 4 chars/token, JSON has roughly 2.5 — so the
heuristic systematically over-weights text and under-weights JSON-y buckets.

This script samples N blocks per category from your JSONL session files,
tokenises them with a real tokenizer (Anthropic count_tokens or tiktoken),
computes the mean chars-per-token ratio per category, and prints multiplicative
correction factors you can apply to the heuristic.

Two backends:
  - anthropic   exact (Claude tokenizer); free API; needs ANTHROPIC_API_KEY;
                ~ N*5 API calls (default 250); slow.
  - tiktoken    local proxy (GPT-4 cl100k_base); no network; fast; close but
                not exact for Claude.
  - both        run both, side-by-side.

ANTHROPIC_API_KEY can be exported in the shell or placed in a project-root
`.env` file (KEY=VALUE per line; see `.env.example`). The .env file is
git-ignored.

Usage:
  python tools/calibrate_write_categories.py
  python tools/calibrate_write_categories.py --backend both --samples 80
  python tools/calibrate_write_categories.py --backend anthropic --model claude-haiku-4-5

Output: a table per backend + a JSON dump (--out path).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path


def _load_dotenv():
    """Load KEY=VALUE pairs from project-root .env into os.environ (no override).

    Tiny built-in loader so the script stays dependency-free. Handles
    surrounding single/double quotes and `#` comments; ignores blank lines.
    Existing environment variables win over .env values.
    """
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv()

CATEGORIES = ("screen_text", "thinking", "file_writes", "bash_commands", "tool_inputs")
FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def categorize(block):
    """Match extract_stats._block_category but without the narration split."""
    if not isinstance(block, dict):
        return None
    t = block.get("type")
    if t == "text":
        return "screen_text"
    if t == "thinking":
        return "thinking"
    if t == "tool_use":
        name = block.get("name") or ""
        if name in FILE_WRITE_TOOLS:
            return "file_writes"
        if name == "Bash":
            return "bash_commands"
        return "tool_inputs"
    return None


def block_payload(block):
    """Return the (chars, text) the model emitted for this block.

    For text/thinking: the body string.
    For tool_use: "name " + compact JSON of input — matches what extract_stats
    counts as the char-weight.
    """
    t = block.get("type")
    if t == "text":
        s = block.get("text") or ""
        return s
    if t == "thinking":
        s = block.get("thinking") or ""
        return s
    if t == "tool_use":
        name = block.get("name") or ""
        inp = block.get("input")
        try:
            payload = json.dumps(inp, ensure_ascii=False, separators=(",", ":")) if inp is not None else ""
        except (TypeError, ValueError):
            payload = str(inp) if inp is not None else ""
        return f"{name} {payload}"
    return ""


def resolve_sources(projects_dir_overrides=None):
    """Return a list of (label, projects_dir Path) tuples to scan.

    Mirrors extract_stats.py's source resolution so the calibration sees the
    same data the dashboard does:
    - reads ../config.json if present (primary ~/.claude + migration source +
      additional_sources)
    - sudo-only sources are skipped with a warning since this script runs as
      the invoking user
    - if projects_dir_overrides is non-empty, it bypasses config entirely
      and uses only those paths.
    Sources whose projects_dir does not exist are silently dropped.
    """
    sources = []

    if projects_dir_overrides:
        for p in projects_dir_overrides:
            sources.append(("override", Path(p).expanduser()))
        return [(lbl, p) for lbl, p in sources if p.exists()]

    # Primary: ~/.claude/projects (matches extract_stats default)
    primary = Path("~/.claude/projects").expanduser()
    if primary.exists():
        sources.append(("local", primary))

    # config.json (optional — script still runs without it)
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cfg = {}

        # Migration source
        mig = cfg.get("migration", {})
        if mig.get("enabled") and mig.get("dir"):
            mig_root = Path(mig["dir"]).expanduser()
            mig_pd = mig_root / mig.get("claude_dir_name", ".claude-windows") / "projects"
            if mig_pd.exists():
                sources.append((mig.get("label", "migration"), mig_pd))

        # additional_sources
        for src in cfg.get("additional_sources", []):
            label = src.get("label") or "additional"
            if src.get("sudo_user"):
                print(f"  skipping sudo-only source: {label} (requires sudo as {src['sudo_user']})",
                      file=sys.stderr)
                continue
            claude_dir = src.get("claude_dir")
            if not claude_dir:
                continue
            pd = Path(claude_dir).expanduser() / "projects"
            if pd.exists():
                sources.append((label, pd))

    # Last-resort fallback: the in-repo dot-claude fixture (developer setup).
    if not sources:
        fixture = Path(__file__).parent.parent / "dot-claude" / "projects"
        if fixture.exists():
            sources.append(("fixture", fixture))

    return sources


def iter_jsonl_blocks(sources):
    """Yield (category, payload_text, model, source_label) tuples from all
    assistant messages across every (label, projects_dir) source.

    The model is the value of `message.model` on the assistant message that
    contained the block — important when tokenising with Anthropic's API,
    because different model families use different tokenisers (Opus 4.7
    introduced a new tokenizer that produces noticeably more tokens than
    earlier model families for the same input string).
    """
    for label, projects_dir in sources:
        for path in projects_dir.rglob("*.jsonl"):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if obj.get("type") != "assistant":
                            continue
                        msg = obj.get("message", {})
                        content = msg.get("content")
                        model = msg.get("model") or ""
                        if not isinstance(content, list):
                            continue
                        for block in content:
                            cat = categorize(block)
                            if cat is None:
                                continue
                            payload = block_payload(block)
                            if payload and len(payload) >= 8:
                                yield cat, payload, model, label
            except OSError:
                continue


def sample_blocks(sources, samples_per_category: int, seed: int = 42):
    """Reservoir-sample `samples_per_category` {payload, model, source} blocks per category."""
    rng = random.Random(seed)
    reservoirs = {cat: [] for cat in CATEGORIES}
    seen = {cat: 0 for cat in CATEGORIES}

    for cat, payload, model, source in iter_jsonl_blocks(sources):
        seen[cat] += 1
        res = reservoirs[cat]
        entry = {"payload": payload, "model": model, "source": source}
        if len(res) < samples_per_category:
            res.append(entry)
        else:
            j = rng.randint(0, seen[cat] - 1)
            if j < samples_per_category:
                res[j] = entry

    return reservoirs, seen


# Tokeniser backends. Both counters accept (text, model) so calibrate() can
# pass the per-block model uniformly; tiktoken ignores it.


def make_tiktoken_counter():
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")

    def count(text: str, model: str = "") -> int:  # model ignored
        return len(enc.encode(text or ""))

    return count


def make_anthropic_counter(default_model: str):
    """Build a counter that tokenises with each block's own model when present.

    Caches per-model baselines (overhead of an "empty" message) and tracks
    models that fail (e.g., retired versions), falling back to default_model
    for those — a single warning is printed per failed model.
    """
    import anthropic
    client = anthropic.Anthropic()

    baselines: dict = {}
    bad_models: set = set()

    def _baseline(model: str) -> int:
        if model not in baselines:
            try:
                baselines[model] = client.messages.count_tokens(
                    model=model, messages=[{"role": "user", "content": "."}]
                ).input_tokens
            except Exception:
                bad_models.add(model)
                # Fall back to default model's baseline
                if default_model not in baselines:
                    baselines[default_model] = client.messages.count_tokens(
                        model=default_model, messages=[{"role": "user", "content": "."}]
                    ).input_tokens
                baselines[model] = baselines[default_model]
        return baselines[model]

    def count(text: str, model: str = "") -> int:
        if not text:
            return 0
        m = model or default_model
        if m in bad_models:
            m = default_model
        base = _baseline(m)
        # _baseline() may have just discovered m is bad — re-check before counting.
        if m in bad_models:
            m = default_model
            base = _baseline(m)
        for attempt in range(3):
            try:
                resp = client.messages.count_tokens(
                    model=m,
                    messages=[{"role": "user", "content": text}],
                )
                return max(0, resp.input_tokens - base)
            except Exception as e:
                # Model-not-found / retired: degrade to default and warn once
                if m != default_model and m not in bad_models:
                    bad_models.add(m)
                    print(f"  warn: count_tokens rejected model={m!r} ({e.__class__.__name__}); falling back to {default_model}", file=sys.stderr)
                    m = default_model
                    base = _baseline(m)
                    continue
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        return 0

    return count


def calibrate(samples: dict, counter, label: str):
    """For each category, compute mean chars-per-token + dispersion.

    Also produces a per-model summary aggregating across all categories,
    so families with different tokenisers (e.g., Opus 4.7) show up
    individually.
    """
    results = {}
    per_model_totals: dict = {}  # model -> {"chars": int, "tokens": int, "n": int}

    for cat in CATEGORIES:
        entries = samples.get(cat, [])
        per_block = []
        for entry in entries:
            payload = entry["payload"]
            model = entry.get("model") or ""
            chars = len(payload)
            toks = counter(payload, model)
            if toks <= 0:
                continue
            per_block.append((chars, toks))
            agg = per_model_totals.setdefault(model or "(unknown)",
                                              {"chars": 0, "tokens": 0, "n": 0})
            agg["chars"] += chars
            agg["tokens"] += toks
            agg["n"] += 1
        if not per_block:
            results[cat] = None
            continue

        ratios = [c / t for c, t in per_block]
        total_chars = sum(c for c, _ in per_block)
        total_toks = sum(t for _, t in per_block)
        results[cat] = {
            "n": len(per_block),
            "chars_per_token_mean": statistics.mean(ratios),
            "chars_per_token_median": statistics.median(ratios),
            "chars_per_token_stdev": statistics.stdev(ratios) if len(ratios) > 1 else 0.0,
            "chars_per_token_weighted": total_chars / total_toks,
            "total_chars": total_chars,
            "total_tokens": total_toks,
        }

    per_model = []
    for model, v in sorted(per_model_totals.items(), key=lambda kv: -kv[1]["n"]):
        if v["tokens"] <= 0:
            continue
        per_model.append({
            "model": model,
            "n": v["n"],
            "total_chars": v["chars"],
            "total_tokens": v["tokens"],
            "chars_per_token_weighted": v["chars"] / v["tokens"],
        })

    return {"backend": label, "categories": results, "per_model": per_model}


def print_table(calib):
    print(f"\n=== {calib['backend']} ===")
    print(f"{'category':<18} {'n':>4} {'mean':>7} {'median':>7} {'stdev':>7} {'weighted':>9}")
    cats = calib["categories"]
    base = cats.get("screen_text") or next((v for v in cats.values() if v), None)
    base_w = base["chars_per_token_weighted"] if base else 1.0
    for cat in CATEGORIES:
        v = cats.get(cat)
        if v is None:
            print(f"  {cat:<16} (no samples)")
            continue
        print(f"  {cat:<16} {v['n']:>4} {v['chars_per_token_mean']:>7.2f} "
              f"{v['chars_per_token_median']:>7.2f} {v['chars_per_token_stdev']:>7.2f} "
              f"{v['chars_per_token_weighted']:>9.2f}")
    print("\nCorrection multipliers (vs screen_text=1.0, weighted):")
    for cat in CATEGORIES:
        v = cats.get(cat)
        if v is None:
            continue
        ratio = base_w / v["chars_per_token_weighted"]
        print(f"  {cat:<16} {ratio:>5.3f}x  "
              f"({'over-weighted' if ratio < 1 else 'under-weighted' if ratio > 1 else 'baseline'} by char-heuristic)")

    per_model = calib.get("per_model") or []
    if per_model:
        print(f"\nPer-model chars/token (aggregated across categories):")
        print(f"  {'model':<36} {'n':>5} {'chars':>10} {'tokens':>10} {'chars/tok':>10}")
        # Anchor relative comparison to the model with most samples
        anchor = per_model[0]["chars_per_token_weighted"] if per_model else 1.0
        for pm in per_model:
            rel = anchor / pm["chars_per_token_weighted"] if pm["chars_per_token_weighted"] else 0
            tag = "" if abs(rel - 1) < 0.02 else (f"  ({(rel-1)*100:+.1f}% vs anchor)" if rel != 0 else "")
            print(f"  {pm['model']:<36} {pm['n']:>5} {pm['total_chars']:>10,} "
                  f"{pm['total_tokens']:>10,} {pm['chars_per_token_weighted']:>10.2f}{tag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects-dir", type=Path, action="append", default=None,
                    help="Path to a directory tree containing Claude Code session "
                         "JSONLs. May be repeated. If omitted, the script reads "
                         "config.json (migration + additional_sources, sudo "
                         "sources skipped) and falls back to ~/.claude/projects.")
    ap.add_argument("--samples", type=int, default=50,
                    help="Samples per category (default 50). 5 categories = 5*N tokeniser calls.")
    ap.add_argument("--backend", choices=("tiktoken", "anthropic", "both"), default="tiktoken")
    ap.add_argument("--model", default="claude-haiku-4-5",
                    help="Anthropic model id used as fallback when the JSONL block "
                         "carries no model field or its model is retired (default: "
                         "claude-haiku-4-5). Anthropic backend ALWAYS prefers the "
                         "per-block model from the JSONL — important because "
                         "different model families (esp. Opus 4.7) use different "
                         "tokenisers and report different token counts for the "
                         "same input.")
    ap.add_argument("--out", type=Path, default=None,
                    help="Optional path to write the full calibration JSON.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    sources = resolve_sources(args.projects_dir)
    if not sources:
        print("ERROR: no JSONL source directories found. Pass --projects-dir explicitly "
              "or check config.json.", file=sys.stderr)
        sys.exit(1)

    print(f"Sampling {args.samples} blocks per category from {len(sources)} source(s):")
    for label, pd in sources:
        print(f"  {label:<24} {pd}")
    samples, seen = sample_blocks(sources, args.samples, seed=args.seed)
    print()
    for cat in CATEGORIES:
        print(f"  {cat:<22} {len(samples[cat]):>4} sampled  ({seen[cat]:,} seen)")

    outputs = []
    if args.backend in ("tiktoken", "both"):
        print("\nRunning tiktoken (cl100k_base) ...")
        counter = make_tiktoken_counter()
        calib = calibrate(samples, counter, "tiktoken (cl100k_base)")
        print_table(calib)
        outputs.append(calib)

    if args.backend in ("anthropic", "both"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("\nWARNING: ANTHROPIC_API_KEY not set; skipping Anthropic backend.", file=sys.stderr)
        else:
            print(f"\nRunning Anthropic count_tokens (model={args.model}) ...")
            print(f"  {args.samples * 5} API calls expected.")
            counter = make_anthropic_counter(args.model)
            calib = calibrate(samples, counter, f"anthropic count_tokens ({args.model})")
            print_table(calib)
            outputs.append(calib)

    if args.out:
        args.out.write_text(json.dumps(outputs, indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
