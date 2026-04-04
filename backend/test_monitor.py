import asyncio
import os
import sys

sys.path.append("/app")
from core.connections import ConnectionManager
from core.vault import get_vault
from fritzconnection import FritzConnection

async def main() -> object:
    conn_data = await ConnectionManager.get_default_connection("fritzbox")
    if conn_data is None:
        print("SKIP: Keine FritzBox-Connection konfiguriert.")
        return

    vault = get_vault()
    pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
    if not pwd_key:
        print("SKIP: FritzBox-Connection hat keinen Password Vault-Key.")
        return

    pwd = await vault.get_secret(pwd_key)
    host = conn_data.config.get("host")
    if not host:
        print("SKIP: FritzBox-Connection ohne host.")
        return

    fc = FritzConnection(address=host, password=pwd, user=conn_data.config.get("user"))
    
    # Check OnlineMonitor
    try:
        mon = fc.call_action("WANCommonInterfaceConfig1", "X_AVM-DE_GetOnlineMonitor", SyncGroupIndex=0)
        print("OnlineMonitor output:", mon)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        print("OnlineMonitor error:", e)

if __name__ == "__main__":
    asyncio.run(main())
