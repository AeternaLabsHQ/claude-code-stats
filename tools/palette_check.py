#!/usr/bin/env python3
"""Gate checks for the chart palette tokens in templates/dashboard.css.

Python twin of the data-viz validator math: OKLab Delta E (x100), the
Machado-Oliveira-Fernandes (2009) severity-1.0 protan/deutan simulation
in linear RGB, and WCAG contrast. Reads the tokens straight out of the
CSS (never a copied list) so drift is what gets tested.

Block markers expected in the CSS:
    /* PALETTE:base:light */       existing token block (accent, pos, neg, panel)
    /* PALETTE:base:dark-media */  same tokens under prefers-color-scheme
    /* PALETTE:base:dark */        same tokens under html.theme-dark
    /* PALETTE:base:light-forced */ same tokens under html.theme-light
    /* PALETTE:default:<variant> */ chart tokens (cat, model, series)
    /* PALETTE:cvd:<variant> */     colorblind overrides (chart tokens + pos/neg)

Usage: python3 tools/palette_check.py   (exit 1 on any failed gate)
"""
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "templates" / "dashboard.css"

MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
}

NORMAL_FLOOR = 15.0     # OKLab Delta E x100, unsimulated
CVD_FLOOR = 8.0         # min(protan, deutan) Delta E x100, colorblind palette only
MARK_CONTRAST = 3.0     # WCAG vs panel for series marks
TEXT_CONTRAST = 4.5     # WCAG vs panel for pos/neg (used as text)
RAMP_END_CONTRAST = 2.0 # palest ramp step vs panel
RAMP_MIN_DL = 0.055     # design gate is 0.06; 0.055 absorbs rounding in the delivered steps

FAMILIES = ("opus", "sonnet", "haiku", "fable")
MARK_RE = re.compile(r"/\* PALETTE:(?P<pal>[a-z]+):(?P<var>[a-z-]+) \*/")
DECL_RE = re.compile(r"(--vc-[a-z0-9-]+)\s*:\s*([^;]+);")


# -- color math (keep in lockstep with the JS validator) -----------------------
def hex2lin(h):
    h = h.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"not a 6-digit hex color: {h!r}")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def oklab_from_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def simulate(h, kind):
    r, g, b = hex2lin(h)
    M = MACHADO[kind]
    clamp = lambda c: max(0.0, min(1.0, c))
    return [clamp(M[i][0] * r + M[i][1] * g + M[i][2] * b) for i in range(3)]


def delta_e(h1, h2, kind=None):
    a = oklab_from_lin(simulate(h1, kind) if kind else hex2lin(h1))
    b = oklab_from_lin(simulate(h2, kind) if kind else hex2lin(h2))
    return 100 * math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def cvd_delta(h1, h2):
    return min(delta_e(h1, h2, "protan"), delta_e(h1, h2, "deutan"))


def rel_lum(h):
    r, g, b = hex2lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def okl(h):
    return oklab_from_lin(hex2lin(h))[0]


# -- CSS parsing -----------------------------------------------------------------
def load_blocks(css_text):
    """Return {(palette, variant): {token: value}} for every marked block."""
    blocks = {}
    for m in MARK_RE.finditer(css_text):
        start = css_text.index("{", m.end())
        depth, i = 0, start
        while i < len(css_text):
            if css_text[i] == "{":
                depth += 1
            elif css_text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = css_text[start:i]
        blocks[(m.group("pal"), m.group("var"))] = {k: v.strip() for k, v in DECL_RE.findall(body)}
    return blocks


def load_palettes(css_text):
    """Resolve the effective token set per (palette, mode).

    'default' = base + default chart tokens; 'cvd' = that plus the cvd
    overrides (cvd blocks may redefine --vc-pos/--vc-neg).
    """
    blocks = load_blocks(css_text)
    out = {}
    for mode in ("light", "dark"):
        base = dict(blocks[("base", mode)])
        default = dict(base)
        default.update(blocks[("default", mode)])
        cvd = dict(default)
        cvd.update(blocks[("cvd", mode)])
        out[("default", mode)] = default
        out[("cvd", mode)] = cvd
    out["_blocks"] = blocks
    return out


# -- gates -----------------------------------------------------------------------
def check_key_symmetry(blocks):
    """Light and dark blocks of an override palette must carry the same keys.

    For cvd this is a cascade guard, not just tidiness: the light selector
    (html.palette-cvd .vc) carries no theme class, so it also matches in dark
    mode, where it has the same specificity as html.theme-dark .vc and is
    declared later in the file. A key present only in cvd:light therefore
    wins in dark mode too - exactly how the colorblind light accent used to
    leak into the dark theme. For default it is a completeness check: its
    .vc selector is the weakest of the three and cannot leak, but both modes
    must still define the full chart token set.

    base is exempt: its .vc block legitimately carries theme-invariant
    structural tokens (radius, font, font sizes) that the theme variants
    never redeclare.
    """
    problems = []
    for pal in ("default", "cvd"):
        ka, kb = (pal, "light"), (pal, "dark")
        if ka not in blocks or kb not in blocks:
            continue  # a missing block is reported by the variant pairing in run_gates
        light_only = sorted(set(blocks[ka]) - set(blocks[kb]))
        dark_only = sorted(set(blocks[kb]) - set(blocks[ka]))
        if light_only or dark_only:
            problems.append(
                f"{pal}: light/dark key sets differ, a light-only key also applies "
                f"in dark mode (light-only: {', '.join(light_only) or 'none'}; "
                f"dark-only: {', '.join(dark_only) or 'none'})")
    return problems


def check_accent_invariant(palettes):
    """--vc-accent and --vc-cat-1 are the same color in every palette/mode.

    Slot 1 of the categorical palette is the brand accent; charts and UI
    chrome are supposed to agree on it. A mismatch means one of the two was
    restepped without the other.
    """
    problems = []
    for key, t in palettes.items():
        if key == "_blocks":
            continue
        pal, mode = key
        accent, cat1 = t["--vc-accent"], t["--vc-cat-1"]
        if accent.lower() != cat1.lower():
            problems.append(f"{pal}/{mode}: accent must equal cat-1 ({accent} vs {cat1})")
    return problems


def run_gates(palettes):
    problems = []
    blocks = palettes["_blocks"]

    # 0. The media-query and class variants of every block must agree.
    for pal in ("base", "default", "cvd"):
        for a, b in (("dark", "dark-media"), ("light", "light-forced")):
            ka, kb = (pal, a), (pal, b)
            if ka not in blocks or kb not in blocks:
                problems.append(f"{pal}: missing block {a if ka not in blocks else b}")
                continue
            # base carries theme-invariant structural tokens (radius, font,
            # font-size) on the master .vc block that the theme variants
            # never redeclare, so only compare keys present on both sides;
            # default/cvd chart-token blocks must be complete, so union.
            keys = (set(blocks[ka]) & set(blocks[kb])) if pal == "base" else (set(blocks[ka]) | set(blocks[kb]))
            for k in sorted(keys):
                if blocks[ka].get(k) != blocks[kb].get(k):
                    va = blocks[ka].get(k, "(missing)")
                    vb = blocks[kb].get(k, "(missing)")
                    problems.append(f"{pal}/{a} vs {b}: {k} differs ({va} vs {vb})")
    problems += check_key_symmetry(blocks)
    problems += check_accent_invariant(palettes)

    for key, t in palettes.items():
        if key == "_blocks":
            continue
        pal, mode = key
        tag = f"{pal}/{mode}"
        panel = t["--vc-panel"]
        accent = t["--vc-accent"]
        cat = [t[f"--vc-cat-{i}"] for i in range(1, 9)]
        fam1 = {f: t[f"--vc-model-{f}-1"] for f in FAMILIES}

        # 1. categorical: contrast, adjacent + wrap distinctness
        for i, h in enumerate(cat, 1):
            c = contrast(h, panel)
            if c < MARK_CONTRAST:
                problems.append(f"{tag}: --vc-cat-{i} {h} contrast {c:.2f} < {MARK_CONTRAST}")
        for i in range(8):
            j = (i + 1) % 8
            d = delta_e(cat[i], cat[j])
            if d < NORMAL_FLOOR:
                problems.append(f"{tag}: cat-{i+1}/cat-{j+1} normal dE {d:.1f} < {NORMAL_FLOOR}")
            if pal == "cvd":
                d = cvd_delta(cat[i], cat[j])
                if d < CVD_FLOOR:
                    problems.append(f"{tag}: cat-{i+1}/cat-{j+1} CVD dE {d:.1f} < {CVD_FLOOR}")
        for n in ("n1", "n2"):
            c = contrast(t[f"--vc-cat-{n}"], panel)
            if c < MARK_CONTRAST:
                problems.append(f"{tag}: --vc-cat-{n} contrast {c:.2f} < {MARK_CONTRAST}")

        # 2. families: all pairs of step-1 colors
        fams = list(FAMILIES)
        for a in range(4):
            c = contrast(fam1[fams[a]], panel)
            if c < MARK_CONTRAST:
                problems.append(f"{tag}: model {fams[a]}-1 contrast {c:.2f} < {MARK_CONTRAST}")
            for b in range(a + 1, 4):
                d = delta_e(fam1[fams[a]], fam1[fams[b]])
                if d < NORMAL_FLOOR:
                    problems.append(f"{tag}: {fams[a]}/{fams[b]} normal dE {d:.1f} < {NORMAL_FLOOR}")
                if pal == "cvd":
                    d = cvd_delta(fam1[fams[a]], fam1[fams[b]])
                    if d < CVD_FLOOR:
                        problems.append(f"{tag}: {fams[a]}/{fams[b]} CVD dE {d:.1f} < {CVD_FLOOR}")

        # 3. ramps: monotone L (lighter in light mode, darker in dark mode), step gaps
        for f in FAMILIES:
            steps = [t[f"--vc-model-{f}-{s}"] for s in range(1, 5)]
            ls = [okl(h) for h in steps]
            for s in range(3):
                dl = ls[s + 1] - ls[s]
                if mode == "dark":
                    dl = -dl
                if dl < RAMP_MIN_DL:
                    problems.append(f"{tag}: {f} ramp step {s+1}->{s+2} dL {dl:.3f} < {RAMP_MIN_DL}")
            c = contrast(steps[3], panel)
            if c < RAMP_END_CONTRAST:
                problems.append(f"{tag}: {f}-4 contrast {c:.2f} < {RAMP_END_CONTRAST}")
        c = contrast(t["--vc-model-unknown"], panel)
        if c < MARK_CONTRAST:
            problems.append(f"{tag}: --vc-model-unknown contrast {c:.2f} < {MARK_CONTRAST}")

        # 4. status: text contrast, distinct from each other and from the accent
        pos, neg = t["--vc-pos"], t["--vc-neg"]
        for name, h in (("pos", pos), ("neg", neg)):
            c = contrast(h, panel)
            if c < TEXT_CONTRAST:
                problems.append(f"{tag}: --vc-{name} text contrast {c:.2f} < {TEXT_CONTRAST}")
        for a, b, label in ((pos, neg, "pos/neg"), (pos, accent, "pos/accent"), (neg, accent, "neg/accent")):
            d = delta_e(a, b)
            if d < NORMAL_FLOOR:
                problems.append(f"{tag}: {label} normal dE {d:.1f} < {NORMAL_FLOOR}")
            if pal == "cvd":
                d = cvd_delta(a, b)
                if d < CVD_FLOOR:
                    problems.append(f"{tag}: {label} CVD dE {d:.1f} < {CVD_FLOOR}")

        # 5. neutral series
        s1, s2 = t["--vc-series-1"], t["--vc-series-2"]
        c = contrast(s2, panel)
        if c < MARK_CONTRAST:
            problems.append(f"{tag}: --vc-series-2 contrast {c:.2f} < {MARK_CONTRAST}")
        for a, b, label in ((s1, s2, "series-1/series-2"), (s2, accent, "series-2/accent")):
            d = delta_e(a, b)
            if d < NORMAL_FLOOR:
                problems.append(f"{tag}: {label} normal dE {d:.1f} < {NORMAL_FLOOR}")
    return problems


def main():
    palettes = load_palettes(CSS.read_text(encoding="utf-8"))
    problems = run_gates(palettes)
    for p in problems:
        print("FAIL", p)
    print("palette_check:", "OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
