import asyncio
import logging
import sys

sys.path.append("/app")
from core.connections import ConnectionManager
from core.vault import get_vault
from fritzconnection.lib.fritzstatus import FritzStatus
from fritzconnection import FritzConnection

logger = logging.getLogger(__name__)


async def main() -> object:
    conn_data = await ConnectionManager.get_default_connection("fritzbox")
    vault = get_vault()
    pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get(
        "FRITZBOX_PASSWORD"
    )
    pwd = await vault.get_secret(pwd_key)
    fc = FritzConnection(
        address=conn_data.config.get("host"),
        password=pwd,
        user=conn_data.config.get("user"),
    )

    fs = FritzStatus(fc)
    logger.debug("is_connected: %s", fs.is_connected)
    logger.debug("is_linked: %s", fs.is_linked)
    logger.debug("external_ip: %s", getattr(fs, "external_ip", None))
    logger.debug("external_ipv6: %s", getattr(fs, "external_ipv6", None))
    logger.debug("uptime: %s", getattr(fs, "uptime", None))


if __name__ == "__main__":
    asyncio.run(main())
