import asyncio
import os
import sys

sys.path.append("/app")
from modules.fritzbox.tools import get_fritz_wan_status, get_fritz_bandwidth

async def main():
    wan = await get_fritz_wan_status.ainvoke({"connection_id": ""})
    print("WAN Status Tool Output:", wan)
    
    bw = await get_fritz_bandwidth.ainvoke({"connection_id": ""})
    print("BW Tool Output:", bw)

if __name__ == "__main__":
    asyncio.run(main())
