"""build_plan_analysis must not crash for API-only users without a plan."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es
import claudestats_core.settings as core_settings


def test_empty_plan_history_returns_none():
    saved = es.PLAN_HISTORY
    saved_core = core_settings.PLAN_HISTORY
    es.PLAN_HISTORY = []
    core_settings.PLAN_HISTORY = []
    try:
        assert es.build_plan_analysis([], []) is None
    finally:
        es.PLAN_HISTORY = saved
        core_settings.PLAN_HISTORY = saved_core
