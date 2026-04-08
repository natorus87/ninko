"""
Jira Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.jira")


async def check_jira_health() -> dict:
    """Health-Check für Jira API."""
    try:
        from .tools import _get_api_client

        client = await _get_api_client("")
        return {"status": "ok", "detail": "Jira API reachable"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="jira",
    display_name="Jira",
    description="Atlassian Jira Issue Tracking – Issues, Projekte, Sprints, Boards und Workflows.",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="JIRA_",
    required_secrets=["JIRA_API_KEY"],
    optional_secrets=[],
    routing_keywords=[
        "jira",
        "ticket",
        "issue",
        "bug",
        "story",
        "task",
        "sprint",
        "board",
        "project",
        "epic",
    ],
    api_prefix="/api/jira",
    dashboard_tab={
        "id": "jira",
        "label": "Jira",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/><rect x="4" y="7" width="4" height="3" rx="1"/><rect x="10" y="7" width="4" height="3" rx="1"/><rect x="4" y="14" width="4" height="3" rx="1"/><rect x="10" y="13" width="4" height="4" rx="1"/></svg>',
    },
    health_check=check_jira_health,
)
