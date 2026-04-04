import asyncio
import sys

import httpx

sys.path.append("/app")
sys.path.append("/app/backend")

_get_pihole_config = None
_authenticate = None

for module_path in (
    "modules.pihole.tools",
    "modules_catalog.pihole.tools",
    "backend.modules_catalog.pihole.tools",
):
    try:
        module = __import__(module_path, fromlist=["_get_pihole_config", "_authenticate"])
        _get_pihole_config = getattr(module, "_get_pihole_config", None)
        _authenticate = getattr(module, "_authenticate", None)
        if _get_pihole_config and _authenticate:
            break
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError):
        continue

async def test():
    if _get_pihole_config is None or _authenticate is None:
        print("SKIP: Pi-hole Modulpfad nicht importierbar.")
        return
    try:
        cfg = await _get_pihole_config()
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        print(f"SKIP: Pi-hole Konfiguration fehlt ({exc})")
        return

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
