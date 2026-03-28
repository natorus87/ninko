"""
OPNsense Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.opnsense")


async def check_opnsense_health(connection_id: str = "") -> dict:
    """Health-Check für OPNsense via API."""
    from core.connections import ConnectionManager
    import httpx

    try:
        conn_data = await ConnectionManager.get_connection("opnsense", connection_id)
        if not conn_data:
            conn_data = await ConnectionManager.get_default_connection("opnsense")

        if not conn_data:
            return {"status": "error", "detail": "Keine OPNsense-Verbindung konfiguriert."}

        host = conn_data.config.get("host", "")
        api_key = conn_data.config.get("api_key", "")
        api_secret = conn_data.config.get("api_secret", "")

        if not host:
            return {"status": "error", "detail": "Keine Host-Adresse konfiguriert."}

        from core.vault import get_vault
        vault = get_vault()
        secret_key = conn_data.vault_keys.get("OPNSENSE_API_SECRET")
        if secret_key:
            api_secret = await vault.get_secret(secret_key) or api_secret

        auth = (api_key, api_secret)
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"https://{host}/api/core/system/status", auth=auth, verify=False)
            if resp.status_code == 200:
                return {"status": "ok", "detail": f"OPNsense unter {host} erreichbar"}
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="opnsense",
    display_name="OPNsense",
    description="Management und Monitoring einer OPNsense Firewall via REST API.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="OPNSENSE_",
    required_secrets=["OPNSENSE_API_KEY", "OPNSENSE_API_SECRET"],
    optional_secrets=[],

    routing_keywords=[
        "opnsense", "firewall", "nat", "portforward", "port forward",
        " firewall regel", "fw regel", "packet filter", "pf",
        "wan", "lan", "opt", "interface", "gateway", "routing",
        "dhcp", "dns", "vpn", "ipsec", "openvpn", "wireguard",
        "blockieren", "erlauben", "regel", "rules", "filter"
    ],

    api_prefix="/api/opnsense",

    dashboard_tab={
        "id": "opnsense",
        "label": "OPNsense",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
    },

    health_check=check_opnsense_health,
)
