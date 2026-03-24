import asyncio
import os
import sys

sys.path.append("/app")
from core.connections import ConnectionManager
from core.vault import get_vault
from fritzconnection import FritzConnection

async def main():
    conn_data = await ConnectionManager.get_default_connection("fritzbox")
    vault = get_vault()
    pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
    pwd = await vault.get_secret(pwd_key)
    fc = FritzConnection(address=conn_data.config.get("host"), password=pwd, user=conn_data.config.get("user"))
    
    # Check OnlineMonitor
    try:
        mon = fc.call_action("WANCommonInterfaceConfig1", "X_AVM-DE_GetOnlineMonitor", SyncGroupIndex=0)
        print("OnlineMonitor output:", mon)
    except Exception as e:
        print("OnlineMonitor error:", e)

if __name__ == "__main__":
    asyncio.run(main())
