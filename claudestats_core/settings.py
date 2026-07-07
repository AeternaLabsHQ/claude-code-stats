"""Laufzeit-Einstellungen des Kerns.

extract_stats.py (CLI) befuellt sie aus config.json; der Collector-Server
(anderes Repo) pro Tenant. Defaults sind so gewaehlt, dass der Kern ohne
configure()-Aufruf lauffaehig ist.

Vertrag fuer Mehrmandanten-Betrieb: Dieses Modul haelt modul-globalen,
mutablen Zustand und ist NICHT thread-safe. Ein Mehrmandanten-Server muss
entweder pro Tenant einen eigenen Worker-Prozess verwenden oder die
Tenant-Verarbeitung strikt seriell abarbeiten und vor jeder Tenant-Berechnung
configure() erneut aufrufen. configure() speichert Referenzen, keine
Kopien - Aufrufer muessen frische bzw. kopierte Objekte uebergeben
(insbesondere plan_history-Listen) und diese danach nicht mehr mutieren.
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
