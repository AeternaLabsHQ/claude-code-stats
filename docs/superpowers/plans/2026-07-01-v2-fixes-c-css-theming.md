# Teilplan C: CSS/Theming-Fixes (v2-Release) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die im Pre-Release-Review gefundenen CSS/Theming-Defekte beheben: kaputte Legacy-Var-Farbsemantik (Finding 23), Token-Block-Drift (24), Heatmap-Legende (25), idleGapPanel (26), Topbar-Drift (27), Model-Badge-Drift (28), stale Fallback-Paletten (29) und totes CSS (38) - plus ein dauerhafter Parity-Guard als pytest.

**Architecture:** Die drei Seiten-Stylesheets (dashboard.css, project_detail.css, session_detail.css) bekommen zwei byte-identische Shared-Bloecke, markiert mit `/* VC-SHARED:<name>:START|END */`-Kommentaren: `tokens` (Design-Tokens + Body-Regeln + Legacy-Var-Remap + anon-blur) und `topbar` (Variant-C-Topbar). Ein neues Tool `tools/check_css_tokens.py` extrahiert die Bloecke und vergleicht byte-genau; `tests/test_css_token_parity.py` macht das zum pytest. Der Kernfix fuer Finding 23 ist, die Token-Selektoren von `.vc` auf `.vc, body.vc-page` zu erweitern, damit der Legacy-Var-Remap auf dem Body aufloest.

**Tech Stack:** Reines CSS + Python 3.12 (stdlib, kein neues Package). Smoke-Verifikation per Headless-Chromium aus dem Playwright-Cache (`~/.cache/ms-playwright/chromium-*/chrome-linux/chrome`, vorhanden: chromium-1217).

## Global Constraints

- `--vc-*`-Tokens duerfen NIEMALS auf `:root` definiert werden; erlaubt sind nur `.vc` und (neu) `body.vc-page`. custom.css-Overrides des Users setzen auf `.vc`-Ebene an und muessen weiter gewinnen (sie gewinnen, weil der Remap `var(--vc-*)`-Referenzen speichert, die erst am Nutzungsort aufgeloest werden).
- Keine Em-Dashes in neuen Kommentaren/Strings (User-Styleguide); normale Bindestriche verwenden.
- `python3 -m pytest tests/ -q` muss nach jedem Commit gruen sein (Baseline vor diesem Plan: 195 passed, 20 subtests).
- Nur die in den Tasks genannten Dateien anfassen. Keine Aenderungen an dashboard.js/session_detail.js/project_detail.js (gehoeren zu Teilplan B/D); keine Deploy-Skripte (update_dashboard.sh ist local-only).
- Arbeitsbranch: `feature/dashboard-rethink-v2`. Vor jedem Commit `git status` pruefen (parallele Sessions am selben Repo moeglich) und nur die eigenen Dateien stagen (`git add <pfad>...`, niemals `git add -A`).
- Token-Kanon (Werte sind in allen drei Dateien schon identisch, nur die Struktur driftet): light accent `#c2562f`, dark accent `#e27a51`, pos `#1f9d63`/`#34c77f`, neg `#d24b3e`/`#f0786b`, grid `#e7e9ee`/`#262b33`, panel `#ffffff`/`#181b21`, bg `#f5f6f8`/`#0e1014`, fg `#14161c`/`#eef0f4`, fg-2 `#5b6473`/`#a8afbb`, fg-3 `#6b7280`/`#6b7380`.

---

### Task 1: Parity-Guard (Checker-Tool + pytest, test-first)

**Files:**
- Create: `tools/check_css_tokens.py`
- Create: `tests/test_css_token_parity.py`
- Modify: `templates/dashboard.css` (nur 2 Marker-Kommentare)
- Modify: `templates/project_detail.css` (nur 2 Marker-Kommentare)
- Modify: `templates/session_detail.css` (nur 2 Marker-Kommentare)

**Interfaces:**
- Produces: `check_css_tokens.extract_blocks(text: str, label: str) -> dict[str, str]` (Blockname -> Blockinhalt ohne Markerzeilen), `check_css_tokens.compare(per_file: dict[str, dict[str, str]]) -> list[str]` (leere Liste = Paritaet), `check_css_tokens.main() -> int` (0 = ok, 1 = Drift/Fehler), Konstante `check_css_tokens.FILES` (Liste der drei CSS-Pfade relativ zum Repo-Root). Markerformat: `/* VC-SHARED:<name>:START */` ... `/* VC-SHARED:<name>:END */`, Name `[a-z-]+`.
- Consumes: nichts (erster Task).

- [ ] **Step 1: Checker-Tool schreiben**

Datei `tools/check_css_tokens.py` mit exakt diesem Inhalt anlegen:

```python
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
```

- [ ] **Step 2: Failing Test schreiben**

Datei `tests/test_css_token_parity.py` mit exakt diesem Inhalt anlegen. Der Parity-Test auf den echten Dateien ist bis zum Abschluss von Task 2 als `expectedFailure` markiert (dokumentiert den Ist-Drift, haelt die Suite aber gruen):

```python
"""Parity guard for the VC-SHARED CSS blocks (see tools/check_css_tokens.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_css_tokens as cct  # noqa: E402


def fence(name, body):
    return f"/* VC-SHARED:{name}:START */\n{body}\n/* VC-SHARED:{name}:END */\n"


class ExtractBlocksTest(unittest.TestCase):
    def test_extracts_single_block(self):
        text = "before\n" + fence("tokens", ".vc { --x: 1; }") + "after\n"
        self.assertEqual(cct.extract_blocks(text, "f"), {"tokens": ".vc { --x: 1; }"})

    def test_extracts_multiple_blocks(self):
        text = fence("tokens", "a") + "mid\n" + fence("topbar", "b")
        self.assertEqual(cct.extract_blocks(text, "f"), {"tokens": "a", "topbar": "b"})

    def test_unclosed_block_raises(self):
        with self.assertRaises(ValueError):
            cct.extract_blocks("/* VC-SHARED:tokens:START */\nx\n", "f")

    def test_mismatched_end_raises(self):
        text = "/* VC-SHARED:tokens:START */\nx\n/* VC-SHARED:topbar:END */\n"
        with self.assertRaises(ValueError):
            cct.extract_blocks(text, "f")

    def test_nested_start_raises(self):
        text = (
            "/* VC-SHARED:tokens:START */\n"
            "/* VC-SHARED:topbar:START */\n"
            "/* VC-SHARED:topbar:END */\n"
            "/* VC-SHARED:tokens:END */\n"
        )
        with self.assertRaises(ValueError):
            cct.extract_blocks(text, "f")


class CompareTest(unittest.TestCase):
    def test_identical_blocks_pass(self):
        per_file = {"a.css": {"tokens": "x"}, "b.css": {"tokens": "x"}}
        self.assertEqual(cct.compare(per_file), [])

    def test_drifted_block_reported_with_diff(self):
        per_file = {"a.css": {"tokens": "x"}, "b.css": {"tokens": "y"}}
        problems = cct.compare(per_file)
        self.assertEqual(len(problems), 1)
        self.assertIn("drifted", problems[0])
        self.assertIn("-x", problems[0])
        self.assertIn("+y", problems[0])

    def test_missing_block_reported(self):
        per_file = {"a.css": {"tokens": "x"}, "b.css": {}}
        problems = cct.compare(per_file)
        self.assertTrue(any("missing in b.css" in p for p in problems))

    def test_no_blocks_anywhere_is_a_problem(self):
        per_file = {"a.css": {}, "b.css": {}}
        self.assertTrue(cct.compare(per_file))


class RealFilesParityTest(unittest.TestCase):
    # TODO(Task 2): expectedFailure entfernen, sobald der tokens-Block
    # in allen drei Dateien kanonisiert ist.
    @unittest.expectedFailure
    def test_shared_blocks_identical(self):
        per_file = {}
        for rel in cct.FILES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            per_file[rel] = cct.extract_blocks(text, rel)
        self.assertEqual(cct.compare(per_file), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Marker um die bestehenden (gedrifteten) Praeambeln legen**

In allen drei Dateien nur zwei Kommentarzeilen einfuegen, KEINE Inhaltsaenderung:

1. `templates/dashboard.css`: Zeile `/* VC-SHARED:tokens:START */` direkt VOR die Kommentarzeile `/* ================================================================` (Zeile 2, Beginn des Token-Kommentars). Zeile `/* VC-SHARED:tokens:END */` direkt NACH der schliessenden Zeile `}` der Regel `body.anon-mode .anon-blur { ... }` (aktuell Zeile 186, die Regel beginnt bei `/* Anonymization blur */`).
2. `templates/project_detail.css`: START direkt VOR `/* ── Variant-C tokens — Modern SaaS (light + dark) ──────────────── */` (Zeile 2). END direkt NACH der Zeile `body.anon-mode .anon-blur { filter: blur(4px); user-select: none; }` (Zeile 62).
3. `templates/session_detail.css`: START direkt VOR `/* ── Variant-C tokens — Modern SaaS (light + dark) ──────────────── */` (Zeile 2). END direkt NACH der Zeile `body.anon-mode .anon-blur { filter: blur(4px); user-select: none; }` (Zeile 66).

WICHTIG: In project/session liegt der Legacy-Var-Remap (Zeilen 64-95 bzw. 68-99) NACH der anon-Zeile, in dashboard davor. Das ist Teil des Drifts; die Marker umschliessen jetzt bewusst unterschiedlich viel - Task 2 ersetzt den Inhalt sowieso komplett. Damit der Remap in project/session mit im Block liegt, dort den END-Marker stattdessen NACH der schliessenden `}` von `html.theme-light body.vc-page { ... }` des Remap-Abschnitts setzen (project: Zeile 95, session: Zeile 99).

- [ ] **Step 4: Tests laufen lassen und beide Ergebnisse verifizieren**

Run: `python3 -m pytest tests/test_css_token_parity.py -v`
Expected: alle ExtractBlocksTest/CompareTest PASS, `test_shared_blocks_identical` XFAIL (expected failure). Zusaetzlich direkt pruefen, dass der Checker den Ist-Drift sieht:

Run: `python3 tools/check_css_tokens.py; echo "exit=$?"`
Expected: mehrere `DRIFT:`-Zeilen (unified diff des tokens-Blocks) und `exit=1`.

Run: `python3 -m pytest tests/ -q`
Expected: `204 passed, ... 1 xfailed` (alle bestehenden 195 weiterhin gruen).

- [ ] **Step 5: Commit**

```bash
git status
git add tools/check_css_tokens.py tests/test_css_token_parity.py templates/dashboard.css templates/project_detail.css templates/session_detail.css
git commit -m "test(css): add VC-SHARED byte-parity guard for page stylesheets (xfail on current drift)"
```

---

### Task 2: Kanonischer tokens-Block in allen drei Dateien (Findings 23, 24, Basis fuer 25)

**Files:**
- Modify: `templates/dashboard.css` (Bereich zwischen den tokens-Markern)
- Modify: `templates/project_detail.css` (Bereich zwischen den tokens-Markern)
- Modify: `templates/session_detail.css` (Bereich zwischen den tokens-Markern + neuer page-lokaler Block danach)
- Modify: `tests/test_css_token_parity.py` (expectedFailure entfernen)

**Interfaces:**
- Consumes: Markerformat und Checker aus Task 1.
- Produces: Neues Shared-Token `--vc-accent-rgb` (light `194,86,47`, dark `226,122,81`) - wird von Task 4 (Heatmap-Legende) konsumiert. Tokens sind ab jetzt auch auf `body.vc-page` definiert (Finding-23-Fix). Seitenspezifische Flow-Tokens (`--vc-flow-bg`, `--vc-btn-flow-bg`, `--vc-node-icon`, `--vc-grid-line`) liegen in session_detail.css in einem eigenen Block NACH dem END-Marker.

- [ ] **Step 1: Kanonischen Block in dashboard.css einsetzen**

In `templates/dashboard.css` ALLES zwischen `/* VC-SHARED:tokens:START */` und `/* VC-SHARED:tokens:END */` (exklusive der Marker selbst) durch den folgenden Inhalt ersetzen. Das ersetzt die alte Langformat-Praeambel inkl. `font-feature-settings`/`color` im `.vc`-Block (beides kommt jetzt ueber die body-Regeln, die per Vererbung greifen; alle drei Seiten haben `body.vc-page`):

```css
/* ================================================================
   Variant-C tokens - Modern SaaS (light + dark).
   Dieser VC-SHARED:tokens-Block ist byte-identisch in dashboard.css,
   project_detail.css und session_detail.css; tools/check_css_tokens.py
   erzwingt die Paritaet als pytest. Aenderungen IMMER in allen drei
   Dateien gleichzeitig machen.
   Die Tokens liegen bewusst auf .vc UND body.vc-page, NICHT auf :root:
   - .vc bleibt der Scope fuer Komponenten und custom.css-Overrides
     (Overrides weiter auf .vc-Ebene ansetzen; sie gewinnen, weil der
     Legacy-Remap unten var(--vc-*)-Referenzen speichert, die erst am
     Nutzungsort aufgeloest werden).
   - body.vc-page braucht die Tokens, damit der Legacy-Var-Remap
     (--green/--red/--amber/... -> var(--vc-*)) nicht guaranteed-invalid
     aufloest; ohne sie rendert z.B. style="color:var(--green)" in
     normaler Textfarbe.
================================================================ */
.vc, body.vc-page {
  --vc-bg: #f5f6f8; --vc-panel: #ffffff;
  --vc-fg: #14161c; --vc-fg-2: #5b6473; --vc-fg-3: #6b7280;
  --vc-grid: #e7e9ee; --vc-grid-2: #e7e9ee;
  --vc-accent: #c2562f; --vc-accent-rgb: 194,86,47; --vc-accent-soft: rgba(194,86,47,.10);
  --vc-pos: #1f9d63; --vc-pos-soft: rgba(31,157,99,.12);
  --vc-neg: #d24b3e; --vc-neg-soft: rgba(210,75,62,.12);
  --vc-radius: 14px; --vc-radius-sm: 10px; --vc-radius-pill: 999px; --vc-radius-ctl: 9px;
  --vc-shadow: 0 1px 2px rgba(20,22,28,.04), 0 8px 20px -12px rgba(20,22,28,.14);
  --vc-font-mono: 'JetBrains Mono', ui-monospace, monospace;
  --vc-font-sans: 'Manrope', system-ui, sans-serif;
  --vc-fs-2xs: 13px;
  --vc-fs-xs:  14px;
  --vc-fs-sm:  14px;
  --vc-fs-md:  15px;
  --vc-fs-base:16px;
  --vc-fs-lg:  21px;
  --vc-fs-xl:  25px;
  --vc-fs-2xl: 30px;
}
.vc { font-family: var(--vc-font-sans); }
@media (prefers-color-scheme: dark) {
  html:not(.theme-light) .vc, html:not(.theme-light) body.vc-page {
    --vc-bg: #0e1014; --vc-panel: #181b21; --vc-grid: #262b33; --vc-grid-2: #262b33;
    --vc-fg: #eef0f4; --vc-fg-2: #a8afbb; --vc-fg-3: #6b7380;
    --vc-accent: #e27a51; --vc-accent-rgb: 226,122,81; --vc-accent-soft: rgba(226,122,81,.16);
    --vc-pos: #34c77f; --vc-pos-soft: rgba(52,199,127,.16);
    --vc-neg: #f0786b; --vc-neg-soft: rgba(240,120,107,.16);
    --vc-shadow: 0 1px 2px rgba(0,0,0,.30), 0 10px 26px -14px rgba(0,0,0,.55);
  }
}
html.theme-dark .vc, html.theme-dark body.vc-page {
  --vc-bg: #0e1014; --vc-panel: #181b21; --vc-grid: #262b33; --vc-grid-2: #262b33;
  --vc-fg: #eef0f4; --vc-fg-2: #a8afbb; --vc-fg-3: #6b7380;
  --vc-accent: #e27a51; --vc-accent-rgb: 226,122,81; --vc-accent-soft: rgba(226,122,81,.16);
  --vc-pos: #34c77f; --vc-pos-soft: rgba(52,199,127,.16);
  --vc-neg: #f0786b; --vc-neg-soft: rgba(240,120,107,.16);
  --vc-shadow: 0 1px 2px rgba(0,0,0,.30), 0 10px 26px -14px rgba(0,0,0,.55);
}
html.theme-light .vc, html.theme-light body.vc-page {
  --vc-bg: #f5f6f8; --vc-panel: #ffffff; --vc-grid: #e7e9ee; --vc-grid-2: #e7e9ee;
  --vc-fg: #14161c; --vc-fg-2: #5b6473; --vc-fg-3: #6b7280;
  --vc-accent: #c2562f; --vc-accent-rgb: 194,86,47; --vc-accent-soft: rgba(194,86,47,.10);
  --vc-pos: #1f9d63; --vc-pos-soft: rgba(31,157,99,.12);
  --vc-neg: #d24b3e; --vc-neg-soft: rgba(210,75,62,.12);
  --vc-shadow: 0 1px 2px rgba(20,22,28,.04), 0 8px 20px -12px rgba(20,22,28,.14);
}
.vc *, .vc *::before, .vc *::after { box-sizing: border-box; }
body.vc-page * { box-sizing: border-box; }
body.vc-page {
  background: var(--vc-bg, #f5f6f8) !important;
  color: var(--vc-fg, #14161c) !important;
  font-family: var(--vc-font-sans, 'Manrope', system-ui, sans-serif) !important;
  font-feature-settings: 'tnum' 1, 'zero' 1;
}
body.vc-page.theme-dark, html.theme-dark body.vc-page { background: #0e1014 !important; color: #eef0f4 !important; }
@media (prefers-color-scheme: dark) {
  html:not(.theme-light) body.vc-page { background: #0e1014 !important; color: #eef0f4 !important; }
}
html.theme-light body.vc-page { background: #f5f6f8 !important; color: #14161c !important; }

/* Legacy-Var-Remap: dynamisch gerendertes Markup nutzt inline var(--bg),
   var(--text), var(--accent), var(--green) usw.; hier werden die alten
   Namen auf die Variant-C-Tokens gemappt, damit light/dark ueberall
   greift. Referenz-Werte (var(--vc-*)) statt Literale, wo ein Token
   existiert - so gewinnen custom.css-Overrides am Nutzungsort. */
body.vc-page {
  --bg: #f5f6f8; --bg2: #ffffff; --bg3: #eef0f3; --border: #e7e9ee;
  --text: #14161c; --text2: #5b6473;
  --accent: var(--vc-accent); --accent2: #cf6b45;
  --green: var(--vc-pos); --orange: var(--vc-accent); --red: var(--vc-neg);
  --blue: var(--vc-fg-2); --purple: var(--vc-fg-2); --cyan: var(--vc-fg-2); --amber: var(--vc-accent);
}
@media (prefers-color-scheme: dark) {
  html:not(.theme-light) body.vc-page {
    --bg: #0e1014; --bg2: #181b21; --bg3: #1f242c; --border: #262b33;
    --text: #eef0f4; --text2: #a8afbb;
    --accent: var(--vc-accent); --accent2: #ec8b6a;
    --green: var(--vc-pos); --orange: var(--vc-accent); --red: var(--vc-neg);
    --blue: var(--vc-fg-2); --purple: var(--vc-fg-2); --cyan: var(--vc-fg-2); --amber: var(--vc-accent);
  }
}
html.theme-dark body.vc-page {
  --bg: #0e1014; --bg2: #181b21; --bg3: #1f242c; --border: #262b33;
  --text: #eef0f4; --text2: #a8afbb;
  --accent: var(--vc-accent); --accent2: #ec8b6a;
  --green: var(--vc-pos); --orange: var(--vc-accent); --red: var(--vc-neg);
  --blue: var(--vc-fg-2); --purple: var(--vc-fg-2); --cyan: var(--vc-fg-2); --amber: var(--vc-accent);
}
html.theme-light body.vc-page {
  --bg: #f5f6f8; --bg2: #ffffff; --bg3: #eef0f3; --border: #e7e9ee;
  --text: #14161c; --text2: #5b6473;
  --accent: var(--vc-accent); --accent2: #cf6b45;
  --green: var(--vc-pos); --orange: var(--vc-accent); --red: var(--vc-neg);
  --blue: var(--vc-fg-2); --purple: var(--vc-fg-2); --cyan: var(--vc-fg-2); --amber: var(--vc-accent);
}

/* Anonymization blur */
body.anon-mode .anon-blur { filter: blur(4px); user-select: none; }
```

- [ ] **Step 2: Denselben Block in project_detail.css einsetzen**

In `templates/project_detail.css` ALLES zwischen den tokens-Markern durch EXAKT denselben Inhalt aus Step 1 ersetzen (byte-identisch kopieren, nicht abtippen).

- [ ] **Step 3: Denselben Block in session_detail.css einsetzen + Flow-Tokens auslagern**

In `templates/session_detail.css` ALLES zwischen den tokens-Markern durch EXAKT denselben Inhalt aus Step 1 ersetzen. Direkt NACH der Zeile `/* VC-SHARED:tokens:END */` diesen page-lokalen Block einfuegen (das sind die vier Flow-Tokens, die bisher mitten im Shared-Block lagen; Werte sind var()-Referenzen und folgen daher weiterhin light/dark):

```css

/* Session-detail page-local tokens (Flow-Canvas). Bewusst ausserhalb
   des VC-SHARED-Blocks: nur diese Seite kennt sie. */
.vc {
  --vc-flow-bg: var(--vc-bg);
  --vc-btn-flow-bg: var(--vc-panel);
  --vc-node-icon: var(--vc-fg-2);
  --vc-grid-line: var(--vc-grid);
}
```

- [ ] **Step 4: expectedFailure entfernen**

In `tests/test_css_token_parity.py` die zwei Zeilen

```python
    # TODO(Task 2): expectedFailure entfernen, sobald der tokens-Block
    # in allen drei Dateien kanonisiert ist.
    @unittest.expectedFailure
```

ersatzlos loeschen (der Test `test_shared_blocks_identical` laeuft ab jetzt scharf).

- [ ] **Step 5: Parity-Test und Gesamtsuite gruen verifizieren**

Run: `python3 tools/check_css_tokens.py && python3 -m pytest tests/ -q`
Expected: `OK: blocks ['tokens'] identical across 3 files` und pytest komplett gruen (kein xfail mehr).

- [ ] **Step 6: Chromium-Smoke fuer Finding 23 (der Kern-Beweis)**

Dieser Probe-Lauf reproduziert exakt den Negativ-Test aus dem Review (dort ergab `color:var(--green)` rgb(20,22,28) = Textfarbe). Nach dem Fix muss gruen herauskommen:

```bash
CHROME=$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
T=$(mktemp -d)
python3 - "$T" <<'EOF'
import pathlib, sys
tmp = sys.argv[1]
for css_file, tag in [("templates/dashboard.css", "dash"),
                      ("templates/project_detail.css", "proj"),
                      ("templates/session_detail.css", "sess")]:
    css = pathlib.Path(css_file).read_text(encoding="utf-8")
    for theme, htmlcls in [("light", "theme-light"), ("dark", "theme-dark")]:
        html = f"""<!doctype html><html class="{htmlcls}"><head><style>{css}</style></head>
<body class="vc-page"><div class="container vc">
<span id="p1" style="color:var(--green)">x</span>
<span id="p2" style="color:var(--red)">x</span>
<span id="p3" style="color:var(--amber)">x</span></div>
<div id="out"></div>
<script>const c=i=>getComputedStyle(document.getElementById(i)).color;
document.getElementById('out').textContent=`{tag}-{theme} G=${{c('p1')}} R=${{c('p2')}} A=${{c('p3')}}`;</script>
</body></html>"""
        pathlib.Path(tmp, f"{tag}-{theme}.html").write_text(html, encoding="utf-8")
EOF
for f in "$T"/*.html; do
  "$CHROME" --headless=new --no-sandbox --disable-gpu --dump-dom "file://$f" 2>/dev/null | grep -o 'id="out">[^<]*'
done
```

Expected (alle 6 Zeilen, Reihenfolge nach Dateiname):
```
id="out">dash-dark G=rgb(52, 199, 127) R=rgb(240, 120, 107) A=rgb(226, 122, 81)
id="out">dash-light G=rgb(31, 157, 99) R=rgb(210, 75, 62) A=rgb(194, 86, 47)
id="out">proj-dark G=rgb(52, 199, 127) R=rgb(240, 120, 107) A=rgb(226, 122, 81)
id="out">proj-light G=rgb(31, 157, 99) R=rgb(210, 75, 62) A=rgb(194, 86, 47)
id="out">sess-dark G=rgb(52, 199, 127) R=rgb(240, 120, 107) A=rgb(226, 122, 81)
id="out">sess-light G=rgb(31, 157, 99) R=rgb(210, 75, 62) A=rgb(194, 86, 47)
```

- [ ] **Step 7: Commit**

```bash
git status
git add templates/dashboard.css templates/project_detail.css templates/session_detail.css tests/test_css_token_parity.py
git commit -m "fix(css): canonical shared token block on .vc AND body.vc-page (repairs legacy var remap, adds --vc-accent-rgb)"
```

---

### Task 3: Topbar vereinheitlichen (Finding 27, inkl. .vc-live-Entfernung aus 38)

**Files:**
- Modify: `templates/dashboard.css` (Topbar-Block durch Shared-Block ersetzen)
- Modify: `templates/project_detail.css` (Topbar-Block ersetzen, .vc-tab-h angleichen)
- Modify: `templates/session_detail.css` (Topbar-Block ersetzen, tote .vc-tab-h-Regeln entfernen)
- Modify: `templates/project_detail.html` (Topbar-Markup: .vc-top-inner-Wrapper)
- Modify: `templates/session_detail.html` (Topbar-Markup: .vc-top-inner-Wrapper)

**Interfaces:**
- Consumes: Markerformat/Checker aus Task 1 (neuer Blockname `topbar` in allen drei Dateien; der Parity-Test deckt ihn automatisch mit ab, weil compare() alle Blocknamen prueft).
- Produces: Einheitliches Topbar-Markup `div.vc.vc-top > div.vc-top-inner > (left | center/spacer | right)` auf allen drei Seiten. Kanon-Look = Dashboard (Pill-Brand-Mark 9px, Sans 11.5px). `.vc-back` wandert mit in den Shared-Block (Dashboard nutzt ihn nicht, harmlos).

- [ ] **Step 1: Toten .vc-tab-h-Block in session_detail.css verifizieren**

Run: `grep -n "vc-tab-h" templates/session_detail.html templates/session_detail.js`
Expected: keine Treffer (die Session-Seite baut ihren Header ueber `.header h1`, nicht ueber vc-tab-h).

- [ ] **Step 2: Shared topbar-Block definieren und in dashboard.css einsetzen**

In `templates/dashboard.css` den kompletten Bereich vom Kommentar `/* ── Variant-C top bar ─────────────────────────────────────────── */` (inkl. der zwei Erklaerungszeilen danach) bis einschliesslich der schliessenden `}` des Media-Query-Blocks

```css
@media (max-width: 960px) {
  .vc-top-inner { grid-template-columns: 1fr; gap: 8px; }
  .vc-top-center, .vc-top-right { justify-self: stretch; flex-wrap: wrap; }
}
```

(aktuell Zeilen 188-256, enthaelt .vc-top bis .vc-utc inkl. der toten Regeln `.vc-live`/`.vc-live-dot`) durch folgenden Block ersetzen. Die alten `.vc-live`/`.vc-live-dot`-Regeln entfallen dabei ersatzlos (Finding 38, Nutzung per Grep in Step 5 verifiziert):

```css
/* VC-SHARED:topbar:START */
/* Variant-C top bar - byte-identisch auf allen drei Seiten
   (tools/check_css_tokens.py). Markup ueberall:
   div.vc.vc-top > div.vc-top-inner > (left | center oder spacer | right).
   Dashboard-Look ist der Kanon; .vc-back/.vc-kv/.vc-checkbox existieren
   nicht auf jeder Seite, die Regeln sind dort schlicht unbenutzt. */
.vc-top {
  background: var(--vc-panel);
  border-bottom: 1px solid var(--vc-grid);
  font-family: var(--vc-font-sans);
  font-size: 11.5px;
  color: var(--vc-fg-2);
  max-width: 1400px;
  margin: 0 auto;
}
.vc-top-inner {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
}
.vc-top-left { display: flex; align-items: center; gap: 10px; }
.vc-brand-mark {
  display: inline-block;
  width: 9px;
  height: 9px;
  background: var(--vc-accent);
  border-radius: var(--vc-radius-pill);
}
.vc-brand-name { font-weight: 700; letter-spacing: 0.08em; color: var(--vc-fg); }
.vc-version { color: var(--vc-fg-3); font-size: var(--vc-fs-2xs); }
.vc-back { color: var(--vc-accent); text-decoration: none; letter-spacing: 0.14em; text-transform: uppercase; font-size: var(--vc-fs-2xs); }
.vc-back:hover { text-decoration: underline; }
.vc-top-center { display: flex; gap: 24px; justify-self: center; }
.vc-kv { display: inline-flex; gap: 6px; align-items: baseline; }
.vc-k { color: var(--vc-fg-3); letter-spacing: 0.08em; font-size: 10px; text-transform: uppercase; }
.vc-v { color: var(--vc-fg); font-weight: 500; font-variant-numeric: tabular-nums; }
.vc-top-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.vc-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--vc-font-sans);
  font-size: 10px;
  color: var(--vc-fg-3);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  user-select: none;
}
.vc-checkbox input { accent-color: var(--vc-accent); cursor: pointer; }
.vc-icon-btn {
  background: var(--vc-panel);
  border: 1px solid var(--vc-grid);
  border-radius: var(--vc-radius-pill);
  color: var(--vc-fg-2);
  font-family: var(--vc-font-sans);
  font-size: 11.5px;
  padding: 5px 11px;
  cursor: pointer;
  line-height: 1;
}
.vc-icon-btn:hover { color: var(--vc-fg); }
.vc-f2-hint { font-family: var(--vc-font-sans); color: var(--vc-fg-3); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
.vc-utc { color: var(--vc-fg-3); font-variant-numeric: tabular-nums; }
@media (max-width: 960px) {
  .vc-top-inner { grid-template-columns: 1fr; gap: 8px; }
  .vc-top-center, .vc-top-right { justify-self: stretch; flex-wrap: wrap; }
}
/* VC-SHARED:topbar:END */
```

- [ ] **Step 3: Topbar-Block in project_detail.css ersetzen**

In `templates/project_detail.css` den Bereich vom Kommentar `/* Variant-C top bar (mini) for detail pages. ... */` bis einschliesslich der Zeile `.vc-tab-h-meta { font-size: var(--vc-fs-xs); color: var(--vc-fg-3); }` (aktuell Zeilen 240-291) ersetzen durch: (a) EXAKT den Shared-topbar-Block aus Step 2 (byte-identisch kopieren), gefolgt von (b) diesem page-lokalen Tab-Header-Block (Typografie an den Dashboard-Kanon angeglichen: 19px bold sans; padding bleibt page-spezifisch `16px 0 8px`, weil der .container hier schon den Seitenabstand traegt):

```css

/* Tab header (page-local: padding folgt dem .container-Innenabstand,
   Typografie folgt dem Dashboard-Kanon aus dashboard.css .vc-tab-h-title) */
.vc-tab-h {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 16px 0 8px;
  font-family: var(--vc-font-mono);
}
.vc-tab-h-title {
  font-family: var(--vc-font-sans);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--vc-fg);
  white-space: nowrap;
}
.vc-tab-h-rule { display: none; }
.vc-tab-h-meta {
  font-family: var(--vc-font-sans);
  font-size: var(--vc-fs-2xs);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--vc-fg-3);
  white-space: nowrap;
}
```

- [ ] **Step 4: Topbar-Block in session_detail.css ersetzen**

In `templates/session_detail.css` den Bereich vom Kommentar `/* Variant-C top bar (mini, for detail page). ... */` bis einschliesslich der Zeile `.vc-tab-h-meta { font-size: var(--vc-fs-xs); color: var(--vc-fg-3); }` (aktuell Zeilen 101-130) durch EXAKT den Shared-topbar-Block aus Step 2 ersetzen. Die `.vc-tab-h`/`.vc-tab-h-title`/`.vc-tab-h-rule`/`.vc-tab-h-meta`-Regeln entfallen hier ersatzlos (in Step 1 als unbenutzt verifiziert).

- [ ] **Step 5: .vc-live-Entfernung verifizieren**

Run: `grep -rn "vc-live" templates/ && echo "NOCH TREFFER" || echo "sauber"`
Expected: `sauber` (weder CSS-Regel noch Markup/JS-Nutzung uebrig; `vc-livepulse` in dashboard.css ist ein Keyframe-Name mit anderem Präfix und zaehlt nicht - falls grep ihn matcht, ist das der einzige erlaubte Treffer; dann stattdessen pruefen: `grep -rn "vc-live[^p]" templates/` muss leer sein).

- [ ] **Step 6: Topbar-Markup in project_detail.html wrappen**

In `templates/project_detail.html` den Block (aktuell Zeilen 16-27)

```html
<div class="vc vc-top">
  <div class="vc-top-left">
    <span class="vc-brand-mark"></span>
    <span class="vc-brand-name">CLAUDE.STATS</span>
    <a href="../index.html" class="vc-back">&larr; DASHBOARD</a>
  </div>
  <div></div>
  <div class="vc-top-right">
    <button class="vc-icon-btn" id="vcThemeToggle" title="Toggle theme">&#9737;</button>
    <span class="vc-utc" id="vcUtcTime">--:--:-- UTC</span>
  </div>
</div>
```

ersetzen durch:

```html
<div class="vc vc-top">
  <div class="vc-top-inner">
    <div class="vc-top-left">
      <span class="vc-brand-mark"></span>
      <span class="vc-brand-name">CLAUDE.STATS</span>
      <a href="../index.html" class="vc-back">&larr; DASHBOARD</a>
    </div>
    <div></div>
    <div class="vc-top-right">
      <button class="vc-icon-btn" id="vcThemeToggle" title="Toggle theme">&#9737;</button>
      <span class="vc-utc" id="vcUtcTime">--:--:-- UTC</span>
    </div>
  </div>
</div>
```

- [ ] **Step 7: Topbar-Markup in session_detail.html wrappen**

In `templates/session_detail.html` denselben Umbau (aktuell Zeilen 19-30; identische Struktur wie in Step 6, gleicher Wrapper `<div class="vc-top-inner">` um die drei Kind-Divs).

- [ ] **Step 8: Parity + Layout-Smoke**

Run: `python3 tools/check_css_tokens.py && python3 -m pytest tests/ -q`
Expected: `OK: blocks ['tokens', 'topbar'] identical across 3 files`, Suite gruen.

Layout-Probe (Topbar muss auf den Detail-Seiten weiter dreispaltig rendern, d.h. left und right stehen auf einer Zeile):

```bash
CHROME=$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
T=$(mktemp -d)
python3 - "$T" <<'EOF'
import pathlib, sys, re
tmp = sys.argv[1]
css = pathlib.Path("templates/session_detail.css").read_text(encoding="utf-8")
topbar = re.search(r'<div class="vc vc-top">.*?</div>\s*</div>\s*</div>', pathlib.Path("templates/session_detail.html").read_text(encoding="utf-8"), re.S).group(0)
html = f"""<!doctype html><html><head><style>{css}</style></head><body class="vc-page">{topbar}
<div id="out"></div><script>
const l=document.querySelector('.vc-top-left').getBoundingClientRect();
const r=document.querySelector('.vc-top-right').getBoundingClientRect();
document.getElementById('out').textContent='SAME_ROW='+(Math.abs(l.top-r.top)<2)+' GRID='+getComputedStyle(document.querySelector('.vc-top-inner')).display;
</script></body></html>"""
pathlib.Path(tmp, "topbar.html").write_text(html, encoding="utf-8")
EOF
"$CHROME" --headless=new --no-sandbox --disable-gpu --window-size=1300,800 --dump-dom "file://$T/topbar.html" 2>/dev/null | grep -o 'id="out">[^<]*'
```

Expected: `id="out">SAME_ROW=true GRID=grid`

- [ ] **Step 9: Commit**

```bash
git status
git add templates/dashboard.css templates/project_detail.css templates/session_detail.css templates/project_detail.html templates/session_detail.html
git commit -m "fix(css): unify VC topbar across pages as VC-SHARED block, drop dead .vc-live and stale .vc-tab-h rules"
```

---

### Task 4: Heatmap-Legende an Live-Accent koppeln (Finding 25)

**Files:**
- Modify: `templates/dashboard.css:399-409` (Zeilennummern von vor Task 2; per Inhalt suchen)

**Interfaces:**
- Consumes: `--vc-accent-rgb` aus Task 2.
- Produces: nichts Neues. Hinweis fuer Teilplan B/D (NICHT hier umsetzen): `_vcAccentRgb()` in dashboard.js koennte kuenftig `getComputedStyle(...).getPropertyValue('--vc-accent-rgb')` lesen statt Hex zu parsen; im Abschlussbericht notieren.

- [ ] **Step 1: Legendenfarbe auf Token umstellen**

In `templates/dashboard.css` in der Regel `.vc .vc-heatmap-legend .cell { ... }` die Zeile

```css
  background: rgba(176, 74, 47, var(--legend-opacity, 0.5));
```

ersetzen durch:

```css
  background: rgba(var(--vc-accent-rgb), var(--legend-opacity, 0.5));
```

Die fuenf `[data-i="..."]`-Regeln darunter bleiben unveraendert.

- [ ] **Step 2: Chromium-Probe (Legende == Live-Accent in beiden Themes)**

```bash
CHROME=$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
T=$(mktemp -d)
python3 - "$T" <<'EOF'
import pathlib, sys
tmp = sys.argv[1]
css = pathlib.Path("templates/dashboard.css").read_text(encoding="utf-8")
for theme, cls in [("light", "theme-light"), ("dark", "theme-dark")]:
    html = f"""<!doctype html><html class="{cls}"><head><style>{css}</style></head>
<body class="vc-page"><div class="vc"><div class="vc-heatmap-legend">
<span class="cell" data-i="0.95"></span></div></div><div id="out"></div>
<script>document.getElementById('out').textContent='{theme} LEGEND='+getComputedStyle(document.querySelector('.vc-heatmap-legend .cell')).backgroundColor;</script>
</body></html>"""
    pathlib.Path(tmp, f"legend-{theme}.html").write_text(html, encoding="utf-8")
EOF
for f in "$T"/legend-*.html; do
  "$CHROME" --headless=new --no-sandbox --disable-gpu --dump-dom "file://$f" 2>/dev/null | grep -o 'id="out">[^<]*'
done
```

Expected:
```
id="out">dark LEGEND=rgba(226, 122, 81, 0.95)
id="out">light LEGEND=rgba(194, 86, 47, 0.95)
```

- [ ] **Step 3: Verifizieren, dass das alte Accent aus dem .vc-Scope verschwunden ist**

Run: `grep -n "176, 74, 47\|176,74,47" templates/dashboard.css`
Expected: keine Treffer mehr (der einzige weitere Kandidat `rgba(176, 74, 47, 0.08)` in `.model-pricing-notice` Zeile ~1602 gehoert zu Task 8... falls er hier schon auffaellt: NICHT anfassen, Task 8 behandelt ihn).
Hinweis: Wenn `.model-pricing-notice` noch matcht, ist das an dieser Stelle OK und erwartet; nur die Legenden-Zeile muss weg sein.

- [ ] **Step 4: pytest + Commit**

```bash
python3 -m pytest tests/ -q
git status
git add templates/dashboard.css
git commit -m "fix(css): heatmap legend follows live accent via --vc-accent-rgb"
```

---

### Task 5: idleGapPanel in den Token-Scope holen (Finding 26)

**Files:**
- Modify: `templates/session_detail.html:39`
- Modify: `templates/session_detail.css` (Zeile mit `.igp-bar`)

**Interfaces:**
- Consumes: Token-Block aus Task 2 (auf `body.vc-page` sind die Tokens jetzt auch ohne `.vc` verfuegbar; die Klasse kommt trotzdem dazu, damit custom.css-Overrides auf `.vc`-Ebene das Panel erreichen).
- Produces: nichts fuer andere Tasks.

- [ ] **Step 1: Klasse setzen**

In `templates/session_detail.html` die Zeile

```html
<div id="idleGapPanel"></div>
```

ersetzen durch:

```html
<div id="idleGapPanel" class="vc"></div>
```

- [ ] **Step 2: Stale Fallback entfernen**

In `templates/session_detail.css` die Zeile

```css
.igp-bar { color: var(--vc-accent, #b04a2f); letter-spacing: -1px; white-space: nowrap; }
```

ersetzen durch:

```css
.igp-bar { color: var(--vc-accent); letter-spacing: -1px; white-space: nowrap; }
```

- [ ] **Step 3: Chromium-Probe**

```bash
CHROME=$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
T=$(mktemp -d)
python3 - "$T" <<'EOF'
import pathlib, sys
tmp = sys.argv[1]
css = pathlib.Path("templates/session_detail.css").read_text(encoding="utf-8")
for theme, cls in [("light", "theme-light"), ("dark", "theme-dark")]:
    html = f"""<!doctype html><html class="{cls}"><head><style>{css}</style></head>
<body class="vc-page"><div id="idleGapPanel" class="vc"><div class="idle-gap-panel">
<span class="igp-bar">####</span></div></div><div id="out"></div>
<script>document.getElementById('out').textContent='{theme} BAR='+getComputedStyle(document.querySelector('.igp-bar')).color;</script>
</body></html>"""
    pathlib.Path(tmp, f"igp-{theme}.html").write_text(html, encoding="utf-8")
EOF
for f in "$T"/igp-*.html; do
  "$CHROME" --headless=new --no-sandbox --disable-gpu --dump-dom "file://$f" 2>/dev/null | grep -o 'id="out">[^<]*'
done
```

Expected:
```
id="out">dark BAR=rgb(226, 122, 81)
id="out">light BAR=rgb(194, 86, 47)
```

(Vorher waere beides `rgb(176, 74, 47)` gewesen.)

- [ ] **Step 4: pytest + Commit**

```bash
python3 -m pytest tests/ -q
git status
git add templates/session_detail.html templates/session_detail.css
git commit -m "fix(css): idleGapPanel joins .vc scope, bar color follows theme accent"
```

---

### Task 6: Model-Badge-Semantik angleichen (Finding 28)

**Files:**
- Modify: `templates/session_detail.css` (zwei Zeilen entfernen)

**Interfaces:**
- Consumes/Produces: nichts; rein visueller Angleich an dashboard.css/project_detail.css (alle Modelle accent-soft + accent).

- [ ] **Step 1: Abweichende Badge-Regeln entfernen**

In `templates/session_detail.css` diese zwei Zeilen ersatzlos loeschen (die Basisregel `.vc .model-badge { ... }` direkt darueber liefert bereits accent-soft/accent fuer alle Modelle):

```css
.vc .model-badge.opus { color: var(--vc-accent) !important; background: var(--vc-accent-soft) !important; }
.vc .model-badge.sonnet, .vc .model-badge.haiku { color: var(--vc-fg-2) !important; background: var(--vc-grid-2) !important; }
```

- [ ] **Step 2: Verifizieren**

Run: `grep -n "model-badge" templates/session_detail.css`
Expected: nur noch die `.vc .model-badge { ... }`-Basisregel im .vc-Bereich plus die drei Legacy-Zeilen im `:root`-Fallback-Teil (`.model-badge.opus/.sonnet/.haiku { background:rgba(...) }`, Zeilen ~281-284; die bleiben als Nicht-.vc-Fallback unangetastet).

- [ ] **Step 3: pytest + Commit**

```bash
python3 -m pytest tests/ -q
git status
git add templates/session_detail.css
git commit -m "fix(css): session model badges match dashboard accent treatment for all models"
```

---

### Task 7: Stale Fallback-Paletten in den Komponenten-CSS ersetzen (Finding 29)

**Files:**
- Modify: `templates/components/session_filters.css`
- Modify: `templates/components/session_table.css`

**Interfaces:**
- Consumes: Token-Kanon aus den Global Constraints.
- Produces: nichts; Fallbacks sind nur aktiv, wenn eine Komponente ausserhalb des Token-Scopes mountet - genau dann sollen sie das aktuelle Light-Theme zeigen statt eines Geister-Themes (gruen-teal bzw. warm-paper).

- [ ] **Step 1: Mapping per Skript anwenden**

```bash
python3 - <<'EOF'
import pathlib
MAP = {
    # session_filters.css: alte Dark-Theme-Reste
    "#2c8": "#c2562f",
    "#1d1d1d": "#ffffff",
    "#2a2a2a": "#ffffff",
    "#3a3a3a": "#e7e9ee",
    "#e6e6e6": "#14161c",
    "#111": "#f5f6f8",
    "var(--vc-accent-soft, #333)": "var(--vc-accent-soft, rgba(194,86,47,.10))",
    "var(--vc-fg-3, #999)": "var(--vc-fg-3, #6b7280)",
    "var(--vc-accent, #999)": "var(--vc-accent, #c2562f)",
    "var(--vc-neg, #e55)": "var(--vc-neg, #d24b3e)",
    # beide Dateien: alte Warm-Paper-Reste
    "#b04a2f": "#c2562f",
    "rgba(176,74,47,0.12)": "rgba(194,86,47,.10)",
    "rgba(176,74,47,0.08)": "rgba(194,86,47,.10)",
    "rgba(176,74,47,0.06)": "rgba(194,86,47,.10)",
    "#b8b2a3": "#e7e9ee",
    "#e2dccb": "#e7e9ee",
    "#fbfaf6": "#ffffff",
    "#f4f1ec": "#f5f6f8",
    "#4d4a42": "#5b6473",
    "#918a7a": "#6b7280",
    "#1c1a17": "#14161c",
    "var(--vc-fg-3, #666)": "var(--vc-fg-3, #6b7280)",
    "var(--vc-panel, transparent)": "var(--vc-panel, #ffffff)",
    "var(--vc-shadow, 0 8px 24px rgba(0,0,0,0.12))":
        "var(--vc-shadow, 0 1px 2px rgba(20,22,28,.04), 0 8px 20px -12px rgba(20,22,28,.14))",
}
for rel in ["templates/components/session_filters.css",
            "templates/components/session_table.css"]:
    p = pathlib.Path(rel)
    text = p.read_text(encoding="utf-8")
    for old, new in MAP.items():
        text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
    print("rewritten:", rel)
EOF
```

- [ ] **Step 2: Verifizieren, dass keine alten Literale uebrig sind**

Run: `grep -nE "#2c8|#1d1d1d|#2a2a2a|#3a3a3a|#e6e6e6|#b04a2f|176,74,47|#b8b2a3|#e2dccb|#fbfaf6|#f4f1ec|#4d4a42|#918a7a|#1c1a17" templates/components/session_filters.css templates/components/session_table.css`
Expected: keine Treffer.

Run: `grep -c "var(--vc-" templates/components/session_filters.css templates/components/session_table.css`
Expected: Zaehler unveraendert gegenueber vorher (nur Fallback-Werte ersetzt, keine Token-Referenz entfernt; Vorher-Werte in Step 1 per `git stash`-freiem Vergleich: `git diff --stat` zeigt nur Zeilen-Aenderungen, keine Regel-Loeschungen).

- [ ] **Step 3: pytest + Commit**

```bash
python3 -m pytest tests/ -q
git status
git add templates/components/session_filters.css templates/components/session_table.css
git commit -m "fix(css): component fallback colors follow current Modern SaaS light palette"
```

---

### Task 8: Totes CSS entfernen + Legacy-:root-Paritaet (Finding 38, Rest von 24e)

**Files:**
- Modify: `templates/dashboard.css`
- Modify: `templates/components/session_filters.css` (eine Zeile)

**Interfaces:**
- Consumes: nichts.
- Produces: nichts; reine Entfernung. JEDE Loeschung erst nach dem zugehoerigen Grep-Beweis (JS baut viel Markup als innerHTML-Strings, deshalb wird immer ueber HTML UND JS gegrept).

- [ ] **Step 1: Beweis-Greps fuer alle Loeschkandidaten**

```bash
cd "$(git rev-parse --show-toplevel)"
for c in badge-model tag-source badge-ctx cell-cost cell-err cell-link plan-comparison insight-card vc-page-tab; do
  printf '%-16s' "$c"
  grep -rn "$c" templates/*.html templates/*.js templates/components/*.js >/dev/null 2>&1 && echo "TREFFER -> NICHT LOESCHEN" || echo "tot"
done
grep -rnoE "\b(progress-bar|progress-track|progress-fill)\b" templates/*.html templates/*.js templates/components/*.js | sort -u
grep -rn "chat-btn" templates/*.html templates/*.js templates/components/*.js | grep -v "st-chat-btn"
grep -rn "stat-card\|config-card" templates/dashboard.html templates/dashboard.js templates/components/*.js
grep -rn '"est"\|'"'"'est'"'"'\|class="[^"]*\best\b' templates/*.html templates/*.js templates/components/*.js
grep -rn -- "--pink" templates/
```

Expected:
- alle neun Klassen der ersten Schleife: `tot`
- progress-Zeile: KEINE Treffer fuer die exakten Tokens progress-bar/progress-track/progress-fill (nur zusammengesetzte wie `progress-bar-outer`, `progress-bar-fill`, `flow-progress-bar` existieren, und die matcht der `\b...\b`-Ausdruck auf das Kernwort... falls doch Zeilen erscheinen: pruefen, dass JEDER Treffer Teil eines laengeren Klassennamens mit Suffix ist wie `progress-bar-outer`; nur dann fortfahren)
- chat-btn ohne st-chat-btn: keine Treffer
- stat-card/config-card in Dashboard-Dateien und Komponenten: keine Treffer (stat-card existiert nur in session_detail.js, das dashboard.css nicht laedt)
- est: keine Treffer
- --pink: nur die Definitionszeile in templates/dashboard.css

Falls IRGENDEIN Kandidat unerwartet Treffer hat: diesen Block NICHT loeschen und die Abweichung im Task-Report an den Orchestrator melden.

- [ ] **Step 2: Bloecke in dashboard.css entfernen**

Folgende Bereiche ersatzlos loeschen (per Inhalt lokalisieren, Zeilennummern haben sich durch Task 2/3 verschoben):

1. Den kompletten Block vom Kommentar `/* ── Table badges / cell affordances (ported from saas.css) ──────────` bis einschliesslich der Zeile `.vc .data-table .est { color: var(--vc-accent); font-size: 10px; }` (enthaelt .badge-model, .tag-source, .badge-ctx mit den Fremdfarben #7c5cff/#8a6dff, .cell-cost, .cell-err, .cell-link, .chat-btn, .est).
2. Den Block vom Kommentar `/* Progress / cycle bar */` bis einschliesslich der schliessenden `}` der Regel `.vc .progress-fill, .vc .progress-bar > div, .vc .progress-track > div { ... }`.
3. Den Block vom Kommentar `/* Plan comparison bars */` bis einschliesslich der Zeile `.vc .plan-comparison .bar-val { ... }`.
4. Im Legacy-Teil den kompletten `.plan-comparison`-Block: von der Zeile `.plan-comparison { background:var(--bg2); ... }` bis einschliesslich `.plan-comparison .bar-val { min-width:80px; text-align:right; font-size:13px; font-weight:600; }`.
5. Im `@media (max-width:640px)`-Block die zwei Zeilen `.plan-comparison .bar-label { width:100px; font-size:12px; }` und `.plan-comparison .bar-val { min-width:60px; font-size:12px; }`.
6. Den Block von `.vc .stat-card,` (Beginn der Sammelregel `.vc .stat-card, .vc .insight-card, .vc .config-card { ... }`) bis einschliesslich der schliessenden `}` von `.vc .stat-card .label, .vc .insight-card .label { ... }`. Die Regel `.vc .misc-stat-grid, .vc .config-grid { font-family: var(--vc-font-mono); }` direkt davor BLEIBT.
7. In den zwei Button-Selektoren `​.vc button:not(.vc-tab):not(.vc-range-btn):not(.vc-icon-btn):not(.vc-page-tab):not([data-sub])` (Regel + zugehoerige :hover-Regel) jeweils das Fragment `:not(.vc-page-tab)` entfernen (die Klasse existiert nirgends; No-op-Bereinigung).

- [ ] **Step 3: Legacy-:root-Paritaet in dashboard.css**

Im Legacy-`:root`-Block (beginnt mit Kommentar `Legacy theme below`):
- Zeile `  --pink: #ec4899;` ersatzlos loeschen.
- Nach der Zeile `  --cyan: #06b6d4;` die Zeile `  --amber: #f59e0b;` einfuegen (Paritaet mit den Legacy-:root-Bloecken von project_detail.css/session_detail.css, die --amber schon haben; `.model-pricing-notice` nutzt var(--amber) und bekommt damit auch ausserhalb von body.vc-page einen Wert).

- [ ] **Step 4: Doppelte .vc-idle-aggregate-Deklaration zusammenfuehren**

In `templates/dashboard.css` die BEIDEN aufeinanderfolgenden Vorkommen (erste Regel `display:flex; align-items:center; gap:10px; ...`, danach `.vc-k`/`.vc-v`-Regeln, dann die zweite Regel `{ flex-direction: column; align-items: flex-start; gap: 6px; }`) so zusammenfuehren, dass genau EINE Basisregel uebrig bleibt:

```css
.vc .vc-idle-aggregate,
#idleGapAggregateCard.vc-idle-aggregate {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
  padding: 12px 16px; margin-bottom: 22px;
  border: 1px solid var(--vc-grid); border-radius: var(--vc-radius-sm);
  background: var(--vc-accent-soft);
  font-family: var(--vc-font-mono); font-size: 12.5px; color: var(--vc-fg-2);
  font-variant-numeric: tabular-nums;
}
.vc .vc-idle-aggregate .vc-k {
  text-transform: uppercase; letter-spacing: 0.1em; font-size: 10px; color: var(--vc-fg-3);
}
.vc .vc-idle-aggregate .vc-v,
.vc .vc-idle-aggregate b { color: var(--vc-fg); }
.vc .vc-idle-aggregate .vc-idle-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
```

Die separate zweite `{ flex-direction: column; ... }`-Regel entfaellt dabei.

- [ ] **Step 5: Leere Regel in session_filters.css entfernen**

In `templates/components/session_filters.css` die Zeile `.sf-panel-host {}` ersatzlos loeschen (nur die leere CSS-Regel; falls session_filters.js die Klasse als DOM-Hook nutzt, ist das unabhaengig von der leeren Regel - JS NICHT anfassen).

- [ ] **Step 6: Nachweis-Greps + Parity + pytest**

```bash
grep -nE "badge-model|tag-source|badge-ctx|cell-cost|cell-err|cell-link|plan-comparison|insight-card|vc-page-tab|--pink|\.vc \.progress-bar|\.vc \.stat-card" templates/dashboard.css
python3 tools/check_css_tokens.py
python3 -m pytest tests/ -q
```

Expected: erster Grep leer; Checker `OK: blocks ['tokens', 'topbar'] identical across 3 files`; Suite gruen.

- [ ] **Step 7: Commit**

```bash
git status
git add templates/dashboard.css templates/components/session_filters.css
git commit -m "refactor(css): remove dead rule blocks (badges, progress trio, plan-comparison, stat cards), align legacy :root vars"
```

---

### Task 9: Abschlussverifikation (kein eigener Code)

**Files:**
- Keine Aenderungen; nur Verifikation.

**Interfaces:**
- Consumes: alles Vorherige.
- Produces: Abschlussbericht an den Orchestrator.

- [ ] **Step 1: Gesamtsuite + Checker**

Run: `python3 tools/check_css_tokens.py && python3 -m pytest tests/ -q`
Expected: Checker OK (beide Bloecke), pytest komplett gruen (Baseline 195 + die neuen Parity-Tests, 0 xfail).

- [ ] **Step 2: Voller Chromium-Smoke (alle drei Dateien, light + dark)**

Die Probe aus Task 2 Step 6 erneut ausfuehren (identischer Codeblock). Expected: identische 6 Zeilen wie dort.

- [ ] **Step 3: Em-Dash-Check der eigenen Aenderungen**

Run: `git diff main...HEAD -- templates/*.css templates/components/*.css tools/check_css_tokens.py tests/test_css_token_parity.py | grep "^+" | grep -c $'—' || true`
Expected: `0` (Box-Drawing-Zeichen `─` in alten Kommentaren sind KEINE Em-Dashes und zaehlen nicht; der Grep prueft nur U+2014).

- [ ] **Step 4: Diff-Review + Statusbericht**

Run: `git status && git log --oneline -10 && git diff HEAD~8 --stat`
Expected: Arbeitsverzeichnis sauber (bis auf Fremddateien anderer Teilplaene), 8 Commits aus diesem Plan (Task 1 bis Task 8), nur die Plan-Dateien betroffen. Im Abschlussbericht an den Orchestrator notieren: (a) Hinweis fuer Teilplan B/D, dass `_vcAccentRgb()` in dashboard.js jetzt `--vc-accent-rgb` lesen koennte, (b) etwaige Grep-Abweichungen aus Task 8 Step 1.

---

## Self-Review (durchgefuehrt vom Plan-Autor)

1. **Spec coverage:** Finding 23 -> Task 2 (Selektor-Erweiterung + Probe). Finding 24 -> Task 1+2 (Marker, Kanon, Flow-Token-Auslagerung, font-feature/color-Konsolidierung, !important-Body-Regeln); 24e (--pink/--amber) -> Task 8 Step 3. Finding 25 -> Task 2 (--vc-accent-rgb) + Task 4. Finding 26 -> Task 5. Finding 27 -> Task 3. Finding 28 -> Task 6. Finding 29 -> Task 7. Finding 38 -> Task 3 (.vc-live, .vc-tab-h in session), Task 8 (Rest inkl. .sf-panel-host, .vc-idle-aggregate-Merge). Parity-Guard (TDD zuerst rot) -> Task 1. Keine Luecken gefunden.
2. **Placeholder scan:** Keine TBD/TODO-Platzhalter ausser dem beabsichtigten `TODO(Task 2)`-Kommentar, der in Task 2 Step 4 explizit wieder entfernt wird. Alle Code-Steps enthalten vollstaendigen Code.
3. **Type consistency:** Markerformat `/* VC-SHARED:<name>:START|END */` ueberall identisch; Funktionsnamen `extract_blocks`/`compare`/`main` konsistent zwischen Tool, Test und Task-Texten; `--vc-accent-rgb`-Schreibweise (`194,86,47` ohne Leerzeichen nach Komma in der Definition, Chromium normalisiert computed zu `rgba(194, 86, 47, ...)` mit Leerzeichen - in den Expected-Outputs so beruecksichtigt).

Bekannte Risiken (bewusst akzeptiert, im Abschlussbericht erwaehnen):
- Detail-Seiten-Topbar wechselt sichtbar auf den Dashboard-Look (Pill-Mark, Sans statt Mono, Icon-Button ohne Accent-Hover) - das ist der gewollte Kanon, aber ein sichtbarer Unterschied zum bisherigen Detail-Look.
- `.vc { font-feature-settings }`/`color` entfallen zugunsten der body-Vererbung; ein .vc-Element ausserhalb von body.vc-page gaebe es theoretisch nicht mehr korrekt gestylt - alle drei Seiten tragen body.vc-page, verifiziert.
- Fallback-Vereinheitlichung in Task 7 aendert nichts Sichtbares, solange die Komponenten im Token-Scope mounten (tun sie auf beiden Einsatzseiten, verifiziert in der Review-Phase).
