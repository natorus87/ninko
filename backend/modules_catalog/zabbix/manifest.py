"""Zabbix module manifest."""

from pydantic import Literal

ModuleCategory = Literal[
    "monitoring", "network", "storage", "security", "communication"
]


class ModuleManifest:
    name = "zabbix"
    category: ModuleCategory = "monitoring"
    version = "1.0.0"
    description = {
        "de": "Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Graphs und Alerts",
        "en": "Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Graphs and Alerts",
    }
    routing_keywords = [
        "zabbix",
        "monitoring",
        "host",
        "item",
        "trigger",
        "alert",
        "graph",
    ]
    api_prefix = "zabbix"
    dashboard_tab = "zabbix"
    health_check = "check_zabbix_health"


module_manifest = ModuleManifest()


async def check_zabbix_health(connection_id: str = "") -> dict:
    """Health check for Zabbix API."""
    from modules_catalog.zabbix.tools import get_zabbix_status

    try:
        result = await get_zabbix_status(connection_id)
        return {"status": "healthy", "info": result}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
