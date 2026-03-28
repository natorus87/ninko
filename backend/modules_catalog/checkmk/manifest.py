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
    except Exception as e:
        return {"status": "error", "detail": f"Checkmk nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="checkmk",
    display_name="Checkmk",
    description="Checkmk Monitoring – Hosts, Services, Status, Alerts und Probleme.",
    version="1.0.0",
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
        "icon": "🖥️",
    },
    health_check=check_checkmk_health,
)
