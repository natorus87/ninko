"""
Pi-hole Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.pihole")


async def check_pihole_health() -> dict:
    """Health-Check für Pi-hole-Verbindung."""
    try:
        from core.connections import ConnectionManager
        from modules.pihole.tools import get_pihole_summary

        # Prüfen ob überhaupt eine Default-Verbindung existiert
        conn = await ConnectionManager.get_default_connection("pihole")
        if not conn or not conn.config.get("url"):
            return {"status": "ok", "detail": "Kein Pi-hole konfiguriert (inaktiv)"}

        result = await get_pihole_summary.ainvoke({"connection_id": conn.id})
        status = result.get("status", "unknown")
        blocked = result.get("domains_blocked", 0)
        return {
            "status": "ok",
            "detail": f"Pi-hole {status}, {blocked:,} Domains blockiert",
        }
    except Exception as e:
        return {"status": "error", "detail": f"Pi-hole nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="pihole",
    display_name="Pi-hole",
    description="Pi-hole DNS-Server Management – Blocking, Queries, Domains, Statistiken",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="PIHOLE_",
    required_secrets=[],
    optional_secrets=["PIHOLE_PASSWORD"],
    routing_keywords=[
        "pihole", "pi-hole", "dns", "blocking", "blockiert",
        "domain", "whitelist", "blacklist", "adblock", "werbung",
        "query", "queries", "dns-anfrage", "auflösung",
        "blocklist", "blockliste", "gravity", "cname", "alias",
        "a-record", "a record", "dns-eintrag", "local dns",
        "dhcp", "lease", "cache", "flush", "leeren", "netzwerktabelle",
        "messages", "warnungen", "hinweise",
    ],
    api_prefix="/api/pihole",
    dashboard_tab={"id": "pihole", "label": "Pi-hole", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>'},
    health_check=check_pihole_health,
)
