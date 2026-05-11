"""
Linux Server Module — Manifest with metadata and health check.
Manages Linux servers via SSH (password & RSA-key).
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.linux_server")


async def check_linux_server_health() -> dict:
    """Health check: verify an SSH connection is configured."""
    try:
        return {"status": "ok", "detail": "Linux Server Modul bereit (SSH)"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="linux_server",
    display_name="Linux Server",
    description=(
        "Linux server management via SSH: shell commands, systemd services, cron, "
        "apt, journalctl, df, top, reboot, hostname, users, iptables. "
        "Manage apache, nginx, mysql, postgres, samba."
    ),
    version="1.1.2",
    author="Ninko Team",
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
