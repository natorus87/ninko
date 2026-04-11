import asyncio
import logging
from agents.orchestrator import OrchestratorAgent
from core.module_registry import ModuleRegistry

logger = logging.getLogger(__name__)


async def main() -> object:
    registry = ModuleRegistry()
    registry.discover_and_load()
    agent = OrchestratorAgent(registry)

    msg = "füge in pihole folgenden a-record hinzu: ninko.conbro.local ipadresse: 10.11.14.6"
    target = agent._detect_module(msg)
    logger.debug("Detected module for msg: %s", target)

    msg_2 = "kannst du einen local dns eintrag in pi-hole machen?"
    target_2 = agent._detect_module(msg_2)
    logger.debug("Detected module for msg 2: %s", target_2)


if __name__ == "__main__":
    asyncio.run(main())
