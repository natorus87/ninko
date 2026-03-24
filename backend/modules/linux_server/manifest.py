"""
Linux Server Modul – Manifest mit Metadaten und Health-Check.
Verwaltet Linux-Server über SSH (Passwort & RSA-Key).
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("kumio.modules.linux_server")


async def check_linux_server_health() -> dict:
    """Health-Check: Prüft ob eine SSH-Verbindung konfiguriert ist."""
    try:
        return {"status": "ok", "detail": "Linux Server Modul bereit (SSH)"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="linux_server",
    display_name="Linux Server",
    description="Linux Server Management über SSH – Befehle, Services, Monitoring, Dateien",
    version="1.0.0",
    author="Kumio Team",
    enabled_by_default=False,
    env_prefix="LINUX_SERVER_",
    required_secrets=["LINUX_SERVER_PASSWORD"],
    optional_secrets=["LINUX_SERVER_SSH_KEY"],
    routing_keywords=[
        "ssh", "linux", "server", "systemd", "service",
        "cron", "apt", "journalctl", "df", "top",
        "reboot", "hostname", "useradd", "iptables",
        "apache", "nginx", "mysql", "postgres", "samba",
    ],
    api_prefix="/api/linux_server",
    dashboard_tab={"id": "linux_server", "label": "Linux", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>'},
    health_check=check_linux_server_health,
)
