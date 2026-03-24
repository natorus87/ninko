import asyncio
import os
import sys

# Add /app to sys.path so we can import from core
sys.path.append("/app")

from core.connections import ConnectionManager
from core.vault import get_vault
from fritzconnection.lib.fritzhosts import FritzHosts
from fritzconnection import FritzConnection

async def main():
    conn_data = await ConnectionManager.get_default_connection("fritzbox")
    if not conn_data:
        print("No default connection found.")
        return
        
    vault = get_vault()
    pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
    pwd = await vault.get_secret(pwd_key)
    if not pwd:
        # Fallback for old style
        pwd = await vault.get_secret(f"FRITZBOX_{conn_data.id.upper()}_PASSWORD")
        
    fc = FritzConnection(address=conn_data.config.get("host"), password=pwd, user=conn_data.config.get("user"))
    fh = FritzHosts(fc)
    hosts = fh.get_hosts_info()
    if hosts:
        print(f"Total hosts: {len(hosts)}")
        print("First 3 hosts:")
        for h in hosts[:3]:
            print(h)
    else:
        print("No hosts returned.")

if __name__ == "__main__":
    asyncio.run(main())
