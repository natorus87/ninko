import asyncio
import logging
import os
import sys

sys.path.append("/app")
from core.connections import ConnectionManager
from core.vault import get_vault
from fritzconnection import FritzConnection

logger = logging.getLogger(__name__)


async def main() -> object:
    conn_data = await ConnectionManager.get_default_connection("fritzbox")
    if conn_data is None:
        logger.debug("SKIP: Keine FritzBox-Connection konfiguriert.")
        return

    vault = get_vault()
    pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get(
        "FRITZBOX_PASSWORD"
    )
    if not pwd_key:
        logger.debug("SKIP: FritzBox-Connection hat keinen Password Vault-Key.")
        return

    pwd = await vault.get_secret(pwd_key)
    host = conn_data.config.get("host")
    if not host:
        logger.debug("SKIP: FritzBox-Connection ohne host.")
        return

    fc = FritzConnection(address=host, password=pwd, user=conn_data.config.get("user"))

    # Let's find WANCommonInterfaceConfig
    for key, srv in fc.services.items():
        if "WANCommonInterfaceConfig" in key:
            logger.debug("Service: %s", key)
            for action in srv.actions:
                logger.debug("  - Action: %s", action)

    # Also check WANDSLInterfaceConfig
    for key, srv in fc.services.items():
        if "WANDSLInterfaceConfig" in key:
            logger.debug("Service: %s", key)
            for action in srv.actions:
                logger.debug("  - Action: %s", action)


if __name__ == "__main__":
    asyncio.run(main())
