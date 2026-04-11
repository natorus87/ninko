import asyncio
import logging
from core.connections import ConnectionManager
from modules.pihole.manifest import check_pihole_health

logger = logging.getLogger(__name__)


async def main() -> object:
    logger.debug("Testing health check...")
    try:
        res = await check_pihole_health()
        logger.debug("Health check result: %s", res)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.warning("Error during health check: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
