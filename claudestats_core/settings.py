"""Laufzeit-Einstellungen des Kerns.

extract_stats.py (CLI) befuellt sie aus config.json; der Collector-Server
(anderes Repo) pro Tenant. Defaults sind so gewaehlt, dass der Kern ohne
configure()-Aufruf lauffaehig ist.
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
    """Setzt Einstellungen per lowercase-Keyword; unbekannte Namen -> Fehler."""
    import sys
    mod = sys.modules[__name__]
    for key, value in kwargs.items():
        name = key.upper()
        if name not in _KNOWN:
            raise AttributeError(f"unknown setting: {key}")
        setattr(mod, name, value)
