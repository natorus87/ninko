"""
Checkmk Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.checkmk")


async def check_checkmk_health() -> dict:
    """Health-Check für Checkmk-Verbindung."""
    try:
        from core.connections import ConnectionManager
        from .tools import checkmk_get_hosts

        conn = await ConnectionManager.get_default_connection("checkmk")
        if not conn or not conn.config.get("url"):
            return {"status": "ok", "detail": "Kein Checkmk konfiguriert (inaktiv)"}

        result = await checkmk_get_hosts.ainvoke({"connection_id": conn.id})
        if isinstance(result, dict) and "error" in result:
            return {"status": "error", "detail": result["error"]}

        return {"status": "ok", "detail": "Checkmk erreichbar"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"Checkmk nicht erreichbar: {exc}"}


module_manifest = ModuleManifest(
    name="checkmk",
    display_name="Checkmk",
    description=(
        "Checkmk monitoring: hosts, services, alerts, status checks, problems, "
        "downtime, uptime and availability tracking. Critical, warning, ok, "
        "and pending states."
    ),
    version="1.1.2",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="CHECKMK_",
    required_secrets=["CHECKMK_API_PASSWORD", "CHECKMK_API_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "checkmk",
        "monitoring",
        "host",
        "hosts",
        "service",
        "services",
        "status",
        "alert",
        "alerts",
        "problem",
        "problems",
        "downtime",
        "monitor",
        "überwachung",
        "host status",
        "service status",
        "uptime",
        "availability",
        "check",
        "checks",
        "critical",
        "warning",
        "ok",
        "pending",
        "dow",
    ],
    api_prefix="/api/modules/checkmk",
    dashboard_tab={
        "id": "checkmk",
        "label": "Checkmk",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/><path d="M7 10l3 3 5-5"/></svg>',
    },
    health_check=check_checkmk_health,
)
