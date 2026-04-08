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
    except (ValueError, TypeError, KeyError, RuntimeError):
        logger.exception("Redmine health check failed")
        return {"status": "error", "detail": "Health check failed"}


module_manifest = ModuleManifest(
    name="redmine",
    display_name="Redmine",
    description="Redmine Projektmanagement – Tickets, Projekte, Benutzer, Time Entries und Workflows.",
    version="1.1.0",
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
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h8a1 1 0 0 1 1 1v4a5 5 0 0 1-10 0V7a1 1 0 0 1 1-1z"/><path d="M8 6l-2-2"/><path d="M16 6l2-2"/><path d="M5 10H3"/><path d="M21 10h-2"/><path d="M5 16l-2 2"/><path d="M19 18l-2-2"/><path d="M12 16v3"/></svg>',
    },
    health_check=check_redmine_health,
)
