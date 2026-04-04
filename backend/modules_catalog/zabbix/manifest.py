"""Zabbix module manifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_zabbix_health(connection_id: str = "") -> dict:
    """Health check for Zabbix API."""
    from .tools import get_zabbix_status

    try:
        result = await get_zabbix_status(connection_id)
        return {"status": "ok", "detail": "Zabbix reachable", "info": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="zabbix",
    display_name="Zabbix",
    description="Zabbix Monitoring – Hosts, Items, Trigger, Graphen und Alerts.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="ZABBIX_",
    required_secrets=["ZABBIX_API_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "zabbix",
        "monitoring",
        "trigger",
        "alert",
        "host metrics",
        "graph",
    ],
    api_prefix="/api/zabbix",
    dashboard_tab={
        "id": "zabbix",
        "label": "Zabbix",
        "icon": "📊",
    },
    health_check=check_zabbix_health,
)
