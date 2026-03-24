import asyncio
from agents.orchestrator import OrchestratorAgent
from core.module_registry import ModuleRegistry

async def main():
    registry = ModuleRegistry()
    registry.discover_and_load()
    agent = OrchestratorAgent(registry)
    
    msg = "füge in pihole folgenden a-record hinzu: ninko.conbro.local ipadresse: 10.11.14.6"
    target = agent._detect_module(msg)
    print("Detected module for msg:", target)

    msg_2 = "kannst du einen local dns eintrag in pi-hole machen?"
    target_2 = agent._detect_module(msg_2)
    print("Detected module for msg 2:", target_2)

if __name__ == "__main__":
    asyncio.run(main())
