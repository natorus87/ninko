"""Pi-hole module — manifest with metadata and health check."""

from __future__ import annotations

import json
import logging
import ast

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.pihole")


async def check_pihole_health() -> dict:
    """Health check for Pi-hole connection."""
    try:
        from core.connections import ConnectionManager
        from .tools import get_pihole_summary

        # Check if a default connection exists at all
        conn = await ConnectionManager.get_default_connection("pihole")
        if not conn or not conn.config.get("url"):
            return {"status": "ok", "detail": "No Pi-hole configured (inactive)"}

        result = await get_pihole_summary.ainvoke({"connection_id": conn.id})
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(result)
                    result = parsed
                except (ValueError, SyntaxError):
                    return {
                        "status": "error",
                        "detail": "Unexpected Pi-hole summary response: non-JSON string",
                    }
        if not isinstance(result, dict):
            return {
                "status": "error",
                "detail": f"Unexpected Pi-hole summary response type: {type(result).__name__}",
            }
        status = result.get("status", "unknown")
        blocked = result.get("domains_blocked", 0)
        return {
            "status": "ok",
            "detail": f"Pi-hole {status}, {blocked:,} domains blocked",
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"Pi-hole unreachable: {exc}"}
    except Exception as exc:
        return {"status": "error", "detail": f"Pi-hole health check failed: {exc}"}


module_manifest = ModuleManifest(
    name="pihole",
    display_name="Pi-hole",
    description=(
        "Pi-hole DNS server management: ad and tracker blocking, blocklists "
        "(Gravity), whitelist and blacklist domains, query log and domain "
        "statistics, custom DNS records (A, CNAME, local DNS), DHCP leases, "
        "cache flush, network table, system messages and warnings. Toggle, "
        "enable or disable DNS blocking."
    ),
    version="1.1.3",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="PIHOLE_",
    required_secrets=[],
    optional_secrets=["PIHOLE_PASSWORD"],
    routing_keywords=[
        "pihole", "pi-hole", "dns blocking", "blocking", "blockiert",
        "pihole domain", "whitelist", "blacklist", "adblock", "werbung",
        "query", "queries", "dns-anfrage", "auflösung",
        "blocklist", "blockliste", "gravity", "pihole cname", "alias",
        "a-record", "pihole a record", "dns-eintrag", "local dns",
        "dhcp", "lease", "cache", "flush", "leeren", "netzwerktabelle",
        "messages", "warnungen", "hinweise",
        "blocking umschalten", "blocking aktivieren", "blocking deaktivieren",
        "dns blocking aktivieren", "dns blocking deaktivieren",
    ],
    api_prefix="/api/pihole",
    dashboard_tab={"id": "pihole", "label": "Pi-hole", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>'},
    health_check=check_pihole_health,
)
