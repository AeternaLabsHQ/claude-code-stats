"""claudestats_core - kalibrierte Domaenenlogik von claude-stats.

Stdlib-rein. Zwei Driver konsumieren dieses Package:
- extract_stats.py (CLI): Datei-Discovery -> absorb_file/finalize_sessions
  -> build_dashboard_data -> statisches HTML
- Collector-Server (eigenes Repo): DB-Export -> dieselbe Kette -> Tenant-JSON
"""
from . import settings  # noqa: F401
from .aggregate import build_dashboard_data, project_display_name  # noqa: F401
from .pricing import (PRICING, build_pricing_warnings, calc_cost,  # noqa: F401
                      get_model_display)
from .sessions import (SessionFileMeta, absorb_file,  # noqa: F401
                       finalize_sessions)
