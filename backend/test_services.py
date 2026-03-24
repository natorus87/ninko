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
    
    # Let's find WANCommonInterfaceConfig
    for key, srv in fc.services.items():
        if "WANCommonInterfaceConfig" in key:
            print("Service:", key)
            for action in srv.actions:
                print("  - Action:", action)
                
    # Also check WANDSLInterfaceConfig
    for key, srv in fc.services.items():
        if "WANDSLInterfaceConfig" in key:
            print("Service:", key)
            for action in srv.actions:
                print("  - Action:", action)

if __name__ == "__main__":
    asyncio.run(main())
