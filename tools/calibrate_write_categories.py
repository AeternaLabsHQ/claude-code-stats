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


def iter_jsonl_blocks(projects_dir: Path):
    """Yield (category, payload_text) tuples from all assistant messages."""
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
                    content = obj.get("message", {}).get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        cat = categorize(block)
                        if cat is None:
                            continue
                        payload = block_payload(block)
                        if payload and len(payload) >= 8:
                            yield cat, payload
        except OSError:
            continue


def sample_blocks(projects_dir: Path, samples_per_category: int, seed: int = 42):
    """Reservoir-sample `samples_per_category` blocks per category."""
    rng = random.Random(seed)
    reservoirs = {cat: [] for cat in CATEGORIES}
    seen = {cat: 0 for cat in CATEGORIES}

    for cat, payload in iter_jsonl_blocks(projects_dir):
        seen[cat] += 1
        res = reservoirs[cat]
        if len(res) < samples_per_category:
            res.append(payload)
        else:
            j = rng.randint(0, seen[cat] - 1)
            if j < samples_per_category:
                res[j] = payload

    return reservoirs, seen


# Tokeniser backends


def make_tiktoken_counter():
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")

    def count(text: str) -> int:
        return len(enc.encode(text or ""))

    return count


def make_anthropic_counter(model: str):
    import anthropic
    client = anthropic.Anthropic()

    baseline = client.messages.count_tokens(
        model=model, messages=[{"role": "user", "content": "."}]
    ).input_tokens

    def count(text: str) -> int:
        if not text:
            return 0
        for attempt in range(3):
            try:
                resp = client.messages.count_tokens(
                    model=model,
                    messages=[{"role": "user", "content": text}],
                )
                return max(0, resp.input_tokens - baseline)
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        return 0

    return count


def calibrate(samples: dict, counter, label: str):
    """For each category, compute mean chars-per-token + dispersion."""
    results = {}
    for cat in CATEGORIES:
        payloads = samples.get(cat, [])
        per_block = []
        for p in payloads:
            chars = len(p)
            toks = counter(p)
            if toks <= 0:
                continue
            per_block.append((chars, toks, chars / toks))
        if not per_block:
            results[cat] = None
            continue

        ratios = [r for _, _, r in per_block]
        total_chars = sum(c for c, _, _ in per_block)
        total_toks = sum(t for _, t, _ in per_block)
        results[cat] = {
            "n": len(per_block),
            "chars_per_token_mean": statistics.mean(ratios),
            "chars_per_token_median": statistics.median(ratios),
            "chars_per_token_stdev": statistics.stdev(ratios) if len(ratios) > 1 else 0.0,
            "chars_per_token_weighted": total_chars / total_toks,
            "total_chars": total_chars,
            "total_tokens": total_toks,
        }
    return {"backend": label, "categories": results}


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects-dir", type=Path,
                    default=Path(__file__).parent.parent / "dot-claude" / "projects",
                    help="Path to a directory tree containing Claude Code session JSONLs.")
    ap.add_argument("--samples", type=int, default=50,
                    help="Samples per category (default 50). 5 categories = 5*N tokeniser calls.")
    ap.add_argument("--backend", choices=("tiktoken", "anthropic", "both"), default="tiktoken")
    ap.add_argument("--model", default="claude-haiku-4-5",
                    help="Anthropic model id for count_tokens (default: claude-haiku-4-5).")
    ap.add_argument("--out", type=Path, default=None,
                    help="Optional path to write the full calibration JSON.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not args.projects_dir.exists():
        print(f"ERROR: projects-dir does not exist: {args.projects_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Sampling {args.samples} blocks per category from {args.projects_dir} ...")
    samples, seen = sample_blocks(args.projects_dir, args.samples, seed=args.seed)
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
