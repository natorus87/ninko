"""Scanner-Adapter-Registrierung.

Jeder Adapter registriert sich hier explizit — kein Auto-Discovery ueber
Filesystem-Scans, damit niemals ein unbeabsichtigt im Verzeichnis liegender
Adapter automatisch aktiv wird (siehe Auftrag: "Kein Fallback auf freien
Modus" / "Unbekannte Scanner duerfen niemals automatisch ausgefuehrt werden").
"""

from __future__ import annotations

from ..scanner_registry import get_scanner_registry
from .trivy import TRIVY_DEFINITION, TrivyAdapter


def register_all_adapters() -> None:
    registry = get_scanner_registry()
    if not registry.is_registered(TRIVY_DEFINITION.id):
        registry.register(TRIVY_DEFINITION, TrivyAdapter())
