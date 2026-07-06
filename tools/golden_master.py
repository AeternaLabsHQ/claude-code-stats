#!/usr/bin/env python3
"""Golden-Master-Harness fuer die Kern-Extraktion.

Friert das normalisierte public/dashboard_data.json als Referenz ein und
vergleicht spaetere Laeufe byte-genau dagegen. Das ist der
Nicht-Regressions-Beweis fuer jeden Refactor-Schritt.

ACHTUNG: .golden/ enthaelt echte Session-Daten (Prompts, Pfade) und ist
gitignored. Nie committen.

build_plan_analysis() haengt von datetime.now() ab (Billing-Zyklen bis
"heute"). Baseline und Check muessen deshalb am selben UTC-Tag laufen;
bei Tageswechsel Baseline von einem gruenen Commit-Stand neu erzeugen.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / ".golden"
BASELINE = GOLDEN_DIR / "baseline.json"
BASELINE_META = GOLDEN_DIR / "baseline_meta.json"
CURRENT = GOLDEN_DIR / "current.json"
DATA = ROOT / "public" / "dashboard_data.json"

VOLATILE_TOP_LEVEL_KEYS = ("generated_at",)


def _run_pipeline():
    r = subprocess.run([sys.executable, str(ROOT / "extract_stats.py")], cwd=ROOT)
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
    _run_pipeline()
    BASELINE.write_text(_normalized(), encoding="utf-8")
    BASELINE_META.write_text(
        json.dumps({"utc_day": _today()}), encoding="utf-8"
    )
    print(f"Baseline geschrieben: {BASELINE}")


def cmd_check():
    if not BASELINE.exists():
        sys.exit("Keine Baseline. Erst: python3 tools/golden_master.py baseline")
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
