"""
Redmine Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.redmine")


async def check_redmine_health() -> dict:
    """Health-Check für Redmine API."""
    try:
        from .tools import _get_api_client

        client = await _get_api_client("")
        return {"status": "ok", "detail": "Redmine API reachable"}
    except Exception:
        logger.exception("Redmine health check failed")
        return {"status": "error", "detail": "Health check failed"}


module_manifest = ModuleManifest(
    name="redmine",
    display_name="Redmine",
    description="Redmine Projektmanagement – Tickets, Projekte, Benutzer, Time Entries und Workflows.",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="REDMINE_",
    required_secrets=["REDMINE_API_KEY"],
    optional_secrets=[],
    routing_keywords=[
        "redmine",
        "ticket",
        "issue",
        "projekt",
        "project",
        "task",
        "aufgabe",
        "bug",
        "milestone",
        "time entry",
        "zeit",
        "zeiterfassung",
        "hrm",
        "resource planning",
        "attendance",
        "leave management",
        "reporting",
        "report",
        "alphanodes",
    ],
    api_prefix="/api/redmine",
    dashboard_tab={
        "id": "redmine",
        "label": "Redmine",
        "icon": "🔴",
    },
    health_check=check_redmine_health,
)
