import asyncio
from core.connections import ConnectionManager
from modules.pihole.tools import add_custom_dns_record

async def main() -> object:
    try:
        res = await add_custom_dns_record.ainvoke({"domain": "test.local", "ip": "1.2.3.4"})
        print("Success:", res)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        print("Error:", repr(e))

if __name__ == "__main__":
    asyncio.run(main())
