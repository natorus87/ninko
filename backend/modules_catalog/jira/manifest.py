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
    except Exception as e:
        return {"status": "error", "detail": str(e)}


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
        "icon": "📋",
    },
    health_check=check_jira_health,
)
