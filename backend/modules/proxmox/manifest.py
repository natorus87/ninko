"""
Proxmox Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("kumio.modules.proxmox")


async def check_proxmox_health() -> dict:
    """Health-Check für Proxmox-API-Verbindung über ConnectionManager."""
    try:
        from proxmoxer import ProxmoxAPI
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("proxmox")
        if not conn:
            # Fallback auf Env-Variablen
            host = os.environ.get("PROXMOX_HOST", "")
            if not host:
                return {"status": "ok", "detail": "Keine Verbindung konfiguriert (erwartet)"}
            # Env-basierter Health-Check
            user = os.environ.get("PROXMOX_USER", "root@pam")
            token_id = os.environ.get("PROXMOX_TOKEN_ID", "")
            verify_ssl = os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"
            vault = get_vault()
            token_secret = await vault.get_secret("PROXMOX_TOKEN_SECRET")
            if not token_secret:
                return {"status": "error", "detail": "PROXMOX_TOKEN_SECRET nicht im Vault"}
            proxmox = ProxmoxAPI(host, user=user, token_name=token_id, token_value=token_secret, verify_ssl=verify_ssl)
            version = proxmox.version.get()
            return {"status": "ok", "detail": f"Proxmox VE {version.get('version', '?')} erreichbar (Env)"}

        # Connection-basierter Health-Check
        vault = get_vault()
        host = conn.config.get("host", "")
        user = conn.config.get("user", "root@pam")
        token_id = conn.config.get("token_id", "")
        verify_ssl = conn.config.get("verify_ssl", "false").lower() == "true"

        if not token_id and "!" in user:
            token_id = user.split("!", 1)[1]
        base_user = user.split("!")[0]

        token_secret = None
        if "token_secret" in conn.vault_keys:
            token_secret = await vault.get_secret(conn.vault_keys["token_secret"])

        if not token_secret or not token_id:
            return {"status": "error", "detail": f"Keine Token-Credentials für '{conn.name}'"}

        host_addr = host.replace("https://", "").replace("http://", "").split(":")[0]
        proxmox = ProxmoxAPI(host_addr, port=8006, user=base_user, token_name=token_id, token_value=token_secret, verify_ssl=verify_ssl)

        # SSL-Fallback für Self-Signed Certs
        try:
            version = proxmox.version.get()
        except Exception as e:
            if verify_ssl and ("ssl" in str(e).lower() or "certificate" in str(e).lower()):
                proxmox = ProxmoxAPI(host_addr, port=8006, user=base_user, token_name=token_id, token_value=token_secret, verify_ssl=False)
                version = proxmox.version.get()
            else:
                raise

        return {"status": "ok", "detail": f"Proxmox VE {version.get('version', '?')} erreichbar ({conn.name})"}
    except Exception as e:
        return {"status": "error", "detail": f"Proxmox nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="proxmox",
    display_name="Proxmox",
    description="Proxmox VE Management – VMs, Container, Nodes, Snapshots",
    version="1.0.0",
    author="Kumio Team",
    enabled_by_default=True,
    env_prefix="PROXMOX_",
    required_secrets=["PROXMOX_TOKEN_SECRET"],
    optional_secrets=["PROXMOX_PASSWORD"],
    routing_keywords=[
        "vm", "virtuell", "proxmox", "node", "lxc", "container",
        "pve", "snapshot", "hängt", "aufgehangen", "entwicklungsumgebung",
    ],
    api_prefix="/api/proxmox",
    dashboard_tab={"id": "proxmox", "label": "Proxmox", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>'},
    health_check=check_proxmox_health,
)
