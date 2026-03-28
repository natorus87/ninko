"""
Template Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.template")


async def check_template_health() -> dict:
    """Health-Check für die Ziel-API."""
    try:
        # TODO: Implementiere echten Health-Check (z.B. GET /api/status)
        return {"status": "ok", "detail": "Template Service erreichbar"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="template",
    display_name="Template Modul",
    description="Eine Vorlage zum Erstellen neuer Ninko Module.",
    version="1.0.0",
    author="Dein Name",
    enabled_by_default=False,  # Standardmäßig deaktiviert
    env_prefix="TEMPLATE_",    # Präfix für Env-Variablen

    # Secrets: Endungen _KEY, _TOKEN, _PASSWORD, _SECRET werden im Vault gespeichert
    required_secrets=["TEMPLATE_API_KEY"],
    optional_secrets=[],

    # WICHTIG: Keywords für den AI-Orchestrator Routing.
    # Kurze Akronyme (< 4 chars) nutzen strikte \b Wort-Grenzen.
    # Lange Keywords nutzen dynamisches Subspace-Matching (Sonderzeichen werden ignoriert).
    # Halte Keywords eindeutig — Überlappung mit anderen Modulen löst Tier-4 Pipeline aus.
    routing_keywords=[
        "beispiel", "template", "muster", "vorlage",
    ],

    # API Basis-Pfad (muss mit routes.py übereinstimmen)
    api_prefix="/api/template",

    # Dashboard-Tab (Icon: Emoji oder inline SVG mit currentColor)
    dashboard_tab={
        "id": "template",
        "label": "Template",
        "icon": "🧩",
    },

    health_check=check_template_health,
)
