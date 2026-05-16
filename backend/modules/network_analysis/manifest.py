"""
Network Analysis Module – Manifest.
"""

from __future__ import annotations

import socket
from core.module_registry import ModuleManifest


async def check_network_analysis_health() -> dict:
    try:
        socket.gethostbyname("google.com")
        return {"status": "ok", "detail": "Network connectivity OK"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="network_analysis",
    display_name="Network Analysis",
    description=(
        "Network analysis: DNS lookup, WHOIS, traceroute, IP and host analysis, "
        "port scan, ping, server and website analysis, network info."
    ),
    version="1.0.1",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="NINKO_MODULE_NETWORK_ANALYSIS",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "netzwerkanalyse",
        "netzwerk-analyse",
        "dns lookup",
        "dns-abfrage",
        "whois",
        "traceroute",
        "trace route",
        "ip-adresse",
        "server-analyse",
        "website-analyse",
        "host analyse",
        "port scan",
        "ping",
        "network info",
    ],
    api_prefix="/api/network-analysis",
    dashboard_tab={
        "id": "network_analysis",
        "label": "Network Analysis",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    },
    health_check=check_network_analysis_health,
)
