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

WEEK_ANCHOR = "mon"
PLAN_HISTORY = []
PLAN_CAPACITY_OVERRIDE_PRO_USD = None
CACHE_EFF_MIN_MESSAGES = 3
SOURCE_LABEL = "current"
LOCALE = {}
DISPLAY_NAME = None

_KNOWN = {
    "WEEK_ANCHOR", "PLAN_HISTORY", "PLAN_CAPACITY_OVERRIDE_PRO_USD",
    "CACHE_EFF_MIN_MESSAGES", "SOURCE_LABEL", "LOCALE", "DISPLAY_NAME",
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
