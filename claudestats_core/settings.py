"""Core runtime settings.

extract_stats.py (the CLI) populates these from config.json. Defaults are
chosen so the core works without ever calling configure().

Not thread-safe: this module holds mutable, module-global state. A caller
that needs to process more than one independent dataset in a single process
must either use a separate worker process per dataset, or process them
strictly serially and re-call configure() before each computation.
configure() stores references, not copies - callers must pass fresh or
already-copied objects (especially plan_history lists) and must not mutate
them afterward.
"""

from datetime import datetime

WEEK_ANCHOR = "mon"
PLAN_HISTORY = []
PLAN_CAPACITY_OVERRIDE_PRO_USD = None
ULTRA_NO_5H_FROM = "2026-10-30"
CACHE_EFF_MIN_MESSAGES = 3
SOURCE_LABEL = "current"
LOCALE = {}
DISPLAY_NAME = None

_KNOWN = {
    "WEEK_ANCHOR", "PLAN_HISTORY", "PLAN_CAPACITY_OVERRIDE_PRO_USD",
    "ULTRA_NO_5H_FROM", "CACHE_EFF_MIN_MESSAGES", "SOURCE_LABEL", "LOCALE", "DISPLAY_NAME",
}


def configure(**kwargs):
    """Set settings via lowercase keyword args; unknown names raise."""
    import sys
    mod = sys.modules[__name__]
    for key, value in kwargs.items():
        name = key.upper()
        if name not in _KNOWN:
            raise AttributeError(f"unknown setting: {key}")
        setattr(mod, name, value)


MISSING = object()  # "config key absent", distinct from an explicit null


def parse_ultra_cutoff(raw=MISSING, default="2026-10-30"):
    """Resolve the config value of ultra_no_5h_limit_from.

    MISSING (key absent) -> default; None -> None (account not verified,
    Ultra keeps the 5h limit); a parseable date -> normalized YYYY-MM-DD
    (so "2026-10-3" cannot break the string comparisons); anything else
    prints a WARNING and returns default.
    """
    if raw is MISSING:
        return default
    if raw is None:
        return None
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        print(f"  WARNING: invalid ultra_no_5h_limit_from {raw!r} "
              f"(expected YYYY-MM-DD or null); using default {default}")
        return default
