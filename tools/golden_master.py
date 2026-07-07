#!/usr/bin/env python3
"""Golden-Master-Harness v2 fuer die Kern-Extraktion.

v1 verglich zwei Pipeline-Laeufe ueber lebende Daten - unbrauchbar, weil
~/.claude waehrend der Laeufe durch aktive Sessions waechst. v2 friert die
Eingabe ein: `baseline` snapshottet alle nicht-sudo-Quellen nach
.golden/input/ und laesst die Pipeline mit HOME-Override +
CLAUDE_STATS_CONFIG gegen den Snapshot laufen; `check` laeuft gegen
DENSELBEN Snapshot und vergleicht byte-genau.

Bewusst NICHT im Golden-Korpus: die sudo-Quelle (cortex:dori) - ohne sudo
nicht einfrierbar; der sudo-Lesepfad ist Driver-Code und bleibt vom
Refactor unberuehrt.

ACHTUNG: .golden/ enthaelt echte Session-Daten (Prompts, Pfade) und ist
gitignored. Nie committen.

build_plan_analysis() haengt von datetime.now() ab (Billing-Zyklen bis
"heute"). Baseline und Check muessen deshalb am selben UTC-Tag laufen
(Exit 2 sonst); bei Tageswechsel Baseline von einem gruenen Commit-Stand
neu erzeugen (Snapshot wird dabei mit rsync --delete aufgefrischt).
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / ".golden"
INPUT_DIR = GOLDEN_DIR / "input"
FAKE_HOME = INPUT_DIR / "home"
GALATEA_SNAP = INPUT_DIR / "galatea-claude"
LAPTOP_DORI_SNAP = INPUT_DIR / "laptop-dori"
GOLDEN_CONFIG = GOLDEN_DIR / "config.json"
BASELINE = GOLDEN_DIR / "baseline.json"
BASELINE_META = GOLDEN_DIR / "baseline_meta.json"
CURRENT = GOLDEN_DIR / "current.json"
DATA = ROOT / "public" / "dashboard_data.json"

VOLATILE_TOP_LEVEL_KEYS = ("generated_at",)

REAL_HOME = Path(os.path.expanduser("~"))

# (Quelle, Ziel, rsync-Extra-Args). Excludes: grosse Verzeichnisse, die kein
# load_*-Loader inhaltlich braucht - Fehlen ist deterministisch.
SNAPSHOT_RSYNC = [
    (REAL_HOME / ".claude", FAKE_HOME / ".claude",
     ["--exclude=/remote/", "--exclude=/paste-cache/", "--exclude=/backups/",
      "--exclude=/cache/", "--exclude=/shell-snapshots/",
      "--exclude=/plugins/cache/"]),
    (REAL_HOME / "projects/_migration-backup/.claude-windows",
     FAKE_HOME / "projects/_migration-backup/.claude-windows", []),
    (Path("/home/andie/galatea-claude/.claude"), GALATEA_SNAP / ".claude", []),
    (Path("/home/dori/projects/_claude"), LAPTOP_DORI_SNAP / "_claude", []),
]
SNAPSHOT_FILES = [
    (REAL_HOME / ".claude.json", FAKE_HOME / ".claude.json"),
    (REAL_HOME / "projects/_migration-backup/.claude-windows.json",
     FAKE_HOME / "projects/_migration-backup/.claude-windows.json"),
    (Path("/home/andie/galatea-claude/.claude.json"),
     GALATEA_SNAP / ".claude.json"),
]


def _rsync(src, dst, extra):
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["rsync", "-a", "--delete", *extra,
                        f"{src}/", f"{dst}/"])
    if r.returncode != 0:
        sys.exit(f"rsync failed for {src} (rc={r.returncode})")


def _build_snapshot():
    for src, dst, extra in SNAPSHOT_RSYNC:
        if src.exists():
            _rsync(src, dst, extra)
    for src, dst in SNAPSHOT_FILES:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _write_golden_config():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["additional_sources"] = [
        {"label": "galatea:andie",
         "claude_dir": str(GALATEA_SNAP / ".claude"),
         "dot_claude_json": str(GALATEA_SNAP / ".claude.json")},
        {"label": "laptop:dori",
         "claude_dir": str(LAPTOP_DORI_SNAP / "_claude")},
    ]
    GOLDEN_CONFIG.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _run_pipeline():
    env = dict(os.environ, HOME=str(FAKE_HOME),
               CLAUDE_STATS_CONFIG=str(GOLDEN_CONFIG))
    r = subprocess.run([sys.executable, str(ROOT / "extract_stats.py")],
                       cwd=ROOT, env=env)
    if r.returncode != 0:
        sys.exit(f"extract_stats.py failed (rc={r.returncode})")


def _normalized() -> str:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for key in VOLATILE_TOP_LEVEL_KEYS:
        data.pop(key, None)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cmd_baseline():
    GOLDEN_DIR.mkdir(exist_ok=True)
    print("Snapshot der Eingabe-Quellen (rsync)...")
    _build_snapshot()
    _write_golden_config()
    _run_pipeline()
    BASELINE.write_text(_normalized(), encoding="utf-8")
    BASELINE_META.write_text(
        json.dumps({"utc_day": _today(), "harness": "v2-snapshot"}),
        encoding="utf-8",
    )
    print(f"Baseline geschrieben: {BASELINE}")


def cmd_check():
    if not BASELINE.exists():
        sys.exit("Keine Baseline. Erst: python3 tools/golden_master.py baseline")
    if not FAKE_HOME.exists():
        sys.exit("Kein Eingabe-Snapshot (.golden/input/). Baseline neu erzeugen.")
    meta = json.loads(BASELINE_META.read_text(encoding="utf-8"))
    if meta.get("utc_day") != _today():
        sys.exit(2)
    _run_pipeline()
    current = _normalized()
    if current == BASELINE.read_text(encoding="utf-8"):
        print("GOLDEN MASTER: OK (byte-identisch)")
        return
    CURRENT.write_text(current, encoding="utf-8")
    print("GOLDEN MASTER: DIFF!")
    print(f"  diff {BASELINE} {CURRENT} | head -50")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("baseline", "check"):
        sys.exit("Usage: golden_master.py baseline|check")
    {"baseline": cmd_baseline, "check": cmd_check}[sys.argv[1]]()
