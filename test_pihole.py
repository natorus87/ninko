import asyncio
import httpx
from modules.pihole.tools import _get_pihole_config, _authenticate

async def test():
    cfg = await _get_pihole_config()
    url = cfg["url"]
    pwd = cfg["password"]
    print("Base URL:", url)
    print("Password length:", len(pwd))
    
    sid = await _authenticate(url, pwd)
    print("SID string representation:", repr(sid))
    
    async with httpx.AsyncClient() as c:
        r1 = await c.get(f"{url}/api/stats/summary", headers={"Authorization": f"Bearer {sid}"})
        print("Bearer status:", r1.status_code)
        
        r2 = await c.get(f"{url}/api/stats/summary", headers={"sid": sid})
        print("sid header status:", r2.status_code)

asyncio.run(test())
