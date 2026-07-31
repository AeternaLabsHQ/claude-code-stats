"""claudestats_core - calibrated domain logic for claude-stats.

Stdlib-only, and driver-agnostic: any caller that feeds parsed session data
through absorb_file/finalize_sessions -> build_dashboard_data gets the same
computed output. extract_stats.py (the CLI) is the reference driver: file
discovery -> absorb_file/finalize_sessions -> build_dashboard_data ->
static HTML.
"""
from . import settings  # noqa: F401
from .aggregate import build_dashboard_data, project_display_name  # noqa: F401
from .pricing import (PRICING, build_pricing_warnings, calc_cost,  # noqa: F401
                      get_model_display)
from .sessions import (SessionFileMeta, absorb_file,  # noqa: F401
                       finalize_sessions)
