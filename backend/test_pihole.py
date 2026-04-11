import asyncio
import logging
import sys

sys.path.append("/app")

logger = logging.getLogger(__name__)

add_custom_dns_record = None

for module_path in (
    "modules.pihole.tools",
    "modules_catalog.pihole.tools",
    "backend.modules_catalog.pihole.tools",
):
    try:
        module = __import__(module_path, fromlist=["add_custom_dns_record"])
        add_custom_dns_record = getattr(module, "add_custom_dns_record", None)
        if add_custom_dns_record:
            break
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError):
        continue


async def main() -> object:
    if add_custom_dns_record is None:
        logger.debug("SKIP: Pi-hole Modulpfad nicht importierbar.")
        return
    try:
        res = await add_custom_dns_record.ainvoke(
            {"domain": "test.local", "ip": "1.2.3.4"}
        )
        logger.debug("Success: %s", res)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.warning("Error: %s", repr(exc))


if __name__ == "__main__":
    asyncio.run(main())
