#!/usr/bin/env python3
"""Byte-parity guard for shared CSS blocks across the page stylesheets.

The three page stylesheets carry blocks that must stay byte-identical
(design tokens, topbar). Each block is fenced by marker comments:

    /* VC-SHARED:<name>:START */
    ...block content...
    /* VC-SHARED:<name>:END */

This tool extracts every fenced block from every file in FILES and
compares the content byte-for-byte. Any drift, missing block, or
malformed marker pair is reported and exits non-zero.

Usage: python3 tools/check_css_tokens.py
"""
import difflib
import re
import sys
from pathlib import Path

FILES = [
    "templates/dashboard.css",
    "templates/project_detail.css",
    "templates/session_detail.css",
]

MARKER_RE = re.compile(r"/\* VC-SHARED:(?P<name>[a-z-]+):(?P<kind>START|END) \*/")


def extract_blocks(text, label):
    """Return {block_name: content} for all fenced blocks in *text*.

    Raises ValueError on nested, mismatched, or unclosed markers so a
    half-edited file can never silently pass.
    """
    blocks = {}
    open_name = None
    buf = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = MARKER_RE.search(line)
        if not m:
            if open_name is not None:
                buf.append(line)
            continue
        name, kind = m.group("name"), m.group("kind")
        if kind == "START":
            if open_name is not None:
                raise ValueError(
                    f"{label}:{lineno}: START of '{name}' inside open block '{open_name}'"
                )
            if name in blocks:
                raise ValueError(f"{label}:{lineno}: duplicate block '{name}'")
            open_name = name
            buf = []
        else:
            if open_name != name:
                raise ValueError(
                    f"{label}:{lineno}: END of '{name}' but open block is '{open_name}'"
                )
            blocks[name] = "\n".join(buf)
            open_name = None
    if open_name is not None:
        raise ValueError(f"{label}: block '{open_name}' never closed")
    return blocks


def compare(per_file):
    """Return a list of human-readable problems (empty = full parity).

    *per_file* maps file label -> {block_name: content}. Every block
    name that appears anywhere must appear in every file with
    byte-identical content.
    """
    problems = []
    all_names = sorted(set().union(*(set(b) for b in per_file.values())) if per_file else set())
    if not all_names:
        problems.append("no VC-SHARED blocks found in any file")
        return problems
    for name in all_names:
        variants = {}
        for label, blocks in per_file.items():
            if name not in blocks:
                problems.append(f"block '{name}' missing in {label}")
            else:
                variants.setdefault(blocks[name], []).append(label)
        if len(variants) > 1:
            (ref_content, ref_files), (other_content, other_files) = list(variants.items())[:2]
            diff = "\n".join(
                difflib.unified_diff(
                    ref_content.splitlines(),
                    other_content.splitlines(),
                    fromfile=f"{name} in {ref_files[0]}",
                    tofile=f"{name} in {other_files[0]}",
                    lineterm="",
                )
            )
            problems.append(f"block '{name}' drifted:\n{diff}")
    return problems


def main():
    root = Path(__file__).resolve().parent.parent
    per_file = {}
    for rel in FILES:
        path = root / rel
        if not path.exists():
            print(f"ERROR: {rel} not found", file=sys.stderr)
            return 1
        try:
            per_file[rel] = extract_blocks(path.read_text(encoding="utf-8"), rel)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    problems = compare(per_file)
    if problems:
        for p in problems:
            print(f"DRIFT: {p}", file=sys.stderr)
        return 1
    names = sorted(set().union(*(set(b) for b in per_file.values())))
    print(f"OK: blocks {names} identical across {len(FILES)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
