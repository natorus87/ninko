"""OPNsense module — manifest with metadata and health check."""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.opnsense")


async def check_opnsense_health(connection_id: str = "") -> dict:
    """Health check for OPNsense via API."""
    import httpx
    from .tools import _get_opnsense_auth

    try:
        host, auth, verify = await _get_opnsense_auth(connection_id)
        async with httpx.AsyncClient(timeout=5.0, verify=verify) as client:
            resp = await client.get(f"https://{host}/api/core/system/status", auth=auth)
            if resp.status_code == 200:
                return {"status": "ok", "detail": f"OPNsense at {host} reachable"}
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except ValueError as exc:
        return {"status": "error", "detail": str(exc)}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="opnsense",
    display_name="OPNsense",
    description=(
        "OPNsense firewall management: firewall rules, NAT rules, port forwarding, "
        "packet filter, interfaces, gateways, DHCP, DNS, VPN (IPsec, OpenVPN, "
        "WireGuard), firewall logs. Create, modify, allow, block, or delete rules. "
        "Restart services and configure/set interfaces or DHCP."
    ),
    version="1.2.2",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="OPNSENSE_",
    required_secrets=["OPNSENSE_API_KEY", "OPNSENSE_API_SECRET"],
    optional_secrets=[],

    routing_keywords=[
        "opnsense", "firewall", "portforward", "port forward",
        "firewall regel", "firewall rule", "fw regel", "packet filter",
        "opnsense interface", "opnsense gateway",
        "opnsense dhcp", "opnsense dns", "opnsense vpn",
        "opnsense ipsec", "openvpn", "wireguard",
        "firewall blockieren", "firewall erlauben",
        "firewall logs", "firewall log",
        "nat regel", "nat rule",
        "firewall regel erstellen", "firewall regel löschen",
        "nat regel erstellen", "nat regel löschen",
        "firewall regel anlegen", "firewall regel entfernen",
        "nat regel anlegen", "nat regel entfernen",
        "dienst neustart", "dienst neustarten", "dienst neu starten",
        "service neustart", "service neustarten", "service neu starten",
        "interface setzen", "interface schalten", "interface aktivieren",
        "interface deaktivieren", "dhcp setzen", "dhcp aktivieren",
        "dhcp deaktivieren",
    ],

    api_prefix="/api/opnsense",

    dashboard_tab={
        "id": "opnsense",
        "label": "OPNsense",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
    },

    health_check=check_opnsense_health,
)
