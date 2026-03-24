import asyncio
import os
import sys

sys.path.append("/app")
from core.connections import ConnectionManager
from core.vault import get_vault
from fritzconnection.lib.fritzstatus import FritzStatus
from fritzconnection import FritzConnection

async def main():
    conn_data = await ConnectionManager.get_default_connection("fritzbox")
    vault = get_vault()
    pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
    pwd = await vault.get_secret(pwd_key)
    fc = FritzConnection(address=conn_data.config.get("host"), password=pwd, user=conn_data.config.get("user"))
    
    fs = FritzStatus(fc)
    print("is_connected:", fs.is_connected)
    print("is_linked:", fs.is_linked)
    print("external_ip:", getattr(fs, 'external_ip', None))
    print("external_ipv6:", getattr(fs, 'external_ipv6', None))
    print("uptime:", getattr(fs, 'uptime', None))

if __name__ == "__main__":
    asyncio.run(main())
