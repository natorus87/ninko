"""
Proxmox module — Manifest with metadata and health check.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.proxmox")


def _warn_if_insecure_verify(source: str, verify_ssl: bool) -> None:
    if not verify_ssl:
        logger.warning(
            "Proxmox SSL verification disabled for %s (verify_ssl=false). "
            "This is insecure and should only be used in development environments.",
            source,
        )


async def check_proxmox_health() -> dict:
    """Health check for Proxmox API connection via ConnectionManager."""
    try:
        from proxmoxer import ProxmoxAPI
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("proxmox")
        if not conn:
            # Fallback to env variables
            host = os.environ.get("PROXMOX_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            # Env-based health check
            user = os.environ.get("PROXMOX_USER", "root@pam")
            token_id = os.environ.get("PROXMOX_TOKEN_ID", "")
            verify_ssl = os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"
            _warn_if_insecure_verify("env configuration", verify_ssl)
            vault = get_vault()
            token_secret = await vault.get_secret("PROXMOX_TOKEN_SECRET")
            if not token_secret:
                return {"status": "error", "detail": "PROXMOX_TOKEN_SECRET not found in Vault"}
            proxmox = ProxmoxAPI(
                host,
                user=user,
                token_name=token_id,
                token_value=token_secret,
                verify_ssl=verify_ssl,
            )
            version = proxmox.version.get()
            return {
                "status": "ok",
                "detail": f"Proxmox VE {version.get('version', '?')} reachable (Env)",
            }

        # Connection-based health check
        vault = get_vault()
        host = conn.config.get("host", "")
        user = conn.config.get("user", "root@pam")
        token_id = conn.config.get("token_id", "")
        verify_ssl = conn.config.get("verify_ssl", "false").lower() == "true"
        _warn_if_insecure_verify(f"connection '{conn.name}'", verify_ssl)

        if not token_id and "!" in user:
            token_id = user.split("!", 1)[1]
        base_user = user.split("!")[0]

        token_secret = None
        if "token_secret" in conn.vault_keys:
            token_secret = await vault.get_secret(conn.vault_keys["token_secret"])

        if not token_secret or not token_id:
            return {"status": "error", "detail": f"No token credentials for '{conn.name}'"}

        host_addr = host.replace("https://", "").replace("http://", "").split(":")[0]
        proxmox = ProxmoxAPI(
            host_addr,
            port=8006,
            user=base_user,
            token_name=token_id,
            token_value=token_secret,
            verify_ssl=verify_ssl,
        )
        version = proxmox.version.get()

        return {
            "status": "ok",
            "detail": f"Proxmox VE {version.get('version', '?')} reachable ({conn.name})",
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"Proxmox not reachable: {exc}"}


module_manifest = ModuleManifest(
    name="proxmox",
    display_name="Proxmox",
    description=(
        "Proxmox VE / PVE virtualization: virtual machines (VMs), LXC containers, "
        "cluster nodes, snapshots, backups, and VM/LXC power management "
        "(start, stop, reboot/restart/neustart, reset). Diagnose hung or stuck "
        "VMs and dev environments."
    ),
    version="1.1.8",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="PROXMOX_",
    required_secrets=["PROXMOX_TOKEN_SECRET"],
    optional_secrets=["PROXMOX_PASSWORD"],
    routing_keywords=[
        "vm", "virtuell", "proxmox", "promox", "proxmox status",
        "proxmox node", "pve", "pve node", "lxc", "virtual machine",
        "snapshot", "hängt", "aufgehangen", "entwicklungsumgebung",
        "neustart", "neustarten", "neu starten", "restart", "reboot",
        "start vm", "stop vm", "vm starten", "vm stoppen",
        "starte vm", "stoppe vm", "vm herunterfahren",
        "vm reset", "vm zurücksetzen", "vm zuruecksetzen",
        "container starten", "starte container", "container stoppen",
        "stoppe container", "container herunterfahren",
        "container neustart", "container neustarten", "container neu starten",
    ],
    api_prefix="/api/proxmox",
    dashboard_tab={
        "id": "proxmox",
        "label": "Proxmox",
        "icon": (
            '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" '
            'rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" '
            'rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6">'
            '</line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>'
        ),
    },
    health_check=check_proxmox_health,
)
