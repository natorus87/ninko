import asyncio
from core.connections import ConnectionManager
from modules.pihole.manifest import check_pihole_health

async def main() -> object:
    print("Testing health check...")
    try:
        res = await check_pihole_health()
        print("Health check result:", res)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        print("Error during health check:", e)

if __name__ == "__main__":
    asyncio.run(main())
