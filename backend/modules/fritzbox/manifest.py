import logging
from fritzconnection import FritzConnection
from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.fritzbox")

async def check_fritzbox_health(connection_id: str = "") -> dict:
    """Verifies the FritzBox connection using TR-064."""
    from core.connections import ConnectionManager
    import asyncio
    
    # Needs to be wrapped in asyncio.to_thread because fritzconnection is sync
    try:
        conn_data = await ConnectionManager.get_connection("fritzbox", connection_id)
        if not conn_data:
             # Fallback to default
             conn_data = await ConnectionManager.get_default_connection("fritzbox")
        
        if not conn_data:
             return {"status": "error", "detail": "Keine FritzBox-Verbindung konfiguriert."}
            
        host = conn_data.config.get("host", conn_data.config.get("FRITZBOX_HOST", "192.168.178.1"))
        user = conn_data.config.get("user", conn_data.config.get("FRITZBOX_USER", ""))
        # Password comes from Vault
        from core.vault import get_vault
        vault = get_vault()
        pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
        pwd = await vault.get_secret(pwd_key) if pwd_key else ""

        def _check():
            fc = FritzConnection(address=host, user=user, password=pwd, timeout=5)
            # Only connect and try a generic call to verify authentication
            return fc.call_action("DeviceInfo1", "GetInfo")
            
        await asyncio.to_thread(_check)
        return {"status": "ok", "detail": f"Verbunden mit FritzBox {host}"}
        
    except Exception as e:
        logger.error("FritzBox Healthcheck fehlgeschlagen: %s", e)
        return {"status": "error", "detail": str(e)}

module_manifest = ModuleManifest(
    name="fritzbox",
    display_name="FritzBox",
    description="Integration und Steuerung von AVM FritzBox Routern via TR-064 und AHA",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="FRITZBOX_",
    required_secrets=["FRITZBOX_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "fritzbox", "router", "wlan", "wifi", "smart home", "aha", "tr-064",
        "dect", "telefonie", "anrufe", "netzwerk", "bandbreite", "dsl", "wan",
        "ip", "externe ip", "internet", "ipadresse", "ip-adresse", "fritz!box", "fritz"
    ],
    api_prefix="/api/fritzbox",
    dashboard_tab={"id": "fritzbox", "label": "FritzBox", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="16" height="12" rx="2" ry="2"></rect><path d="M4 14h16"></path><path d="M8 8v-4"></path><path d="M16 8v-4"></path><circle cx="8" cy="17" r="1.5"></circle><circle cx="16" cy="17" r="1.5"></circle></svg>'},
    health_check=check_fritzbox_health,
)
