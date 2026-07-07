import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_configure_sets_known_setting():
    from claudestats_core import settings
    saved = settings.WEEK_ANCHOR
    try:
        settings.configure(week_anchor="wed")
        assert settings.WEEK_ANCHOR == "wed"
    finally:
        settings.WEEK_ANCHOR = saved


def test_configure_rejects_unknown_setting():
    from claudestats_core import settings
    with pytest.raises(AttributeError):
        settings.configure(does_not_exist=1)


def test_core_imports_without_config_json(tmp_path):
    """Der Kern muss ohne config.json und ohne extract_stats importierbar
    sein - sonst ist er als Library (Collector-Repo!) unbrauchbar."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    r = subprocess.run(
        [sys.executable, "-c",
         "import claudestats_core, sys;"
         "assert 'extract_stats' not in sys.modules"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_public_api_surface():
    """Der Name-Vertrag, gegen den das Collector-Repo programmiert."""
    import claudestats_core as core
    for name in ("settings", "SessionFileMeta", "absorb_file",
                 "finalize_sessions", "build_dashboard_data", "calc_cost",
                 "get_model_display", "PRICING", "build_pricing_warnings"):
        assert hasattr(core, name), f"public API missing: {name}"


def test_config_env_seam_honored(tmp_path):
    """CLAUDE_STATS_CONFIG muss die Config-Quelle fuer extract_stats.CONFIG
    umleiten koennen - das ist der Seam, den hermetische Laeufe (Golden
    Master, Server-Driver) benutzen. Importieren von extract_stats fuehrt
    nur den Modul-Top aus (Config/Locale-Laden); die eigentlichen Loader
    sind lazy, daher ist dieser Test schnell."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"language": "en", "source_label": "seam-test"}),
        encoding="utf-8",
    )
    env = dict(os.environ, CLAUDE_STATS_CONFIG=str(config_path))
    r = subprocess.run(
        [sys.executable, "-c",
         "import extract_stats; print(extract_stats.SOURCE_LABEL)"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    last_line = r.stdout.strip().splitlines()[-1]
    assert last_line == "seam-test"
