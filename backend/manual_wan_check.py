import asyncio
import logging
import sys

sys.path.append("/app")
from modules.fritzbox.tools import get_fritz_wan_status, get_fritz_bandwidth

logger = logging.getLogger(__name__)


async def main() -> object:
    wan = await get_fritz_wan_status.ainvoke({"connection_id": ""})
    logger.debug("WAN Status Tool Output: %s", wan)

    bw = await get_fritz_bandwidth.ainvoke({"connection_id": ""})
    logger.debug("BW Tool Output: %s", bw)


if __name__ == "__main__":
    asyncio.run(main())
