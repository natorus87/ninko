"""Security Core Modul – Package Init.

`agent` wird lazy instanziiert (PEP 562 `__getattr__`), nicht eager beim
Package-Import. Grund: BaseAgent.__init__() baut eine ChromaDB-Verbindung
auf (core.memory.get_memory()) — ein eager `agent = SecurityOrchestratorAgent()`
hier wuerde JEDEN Import eines beliebigen Submoduls (z.B. `modules.security.db`
in einem Unit-Test) an eine laufende ChromaDB-Instanz koppeln, da Python beim
Import eines Submoduls immer zuerst das Parent-Package-__init__.py ausfuehrt.
ModuleRegistry greift beim eigentlichen App-Start ohnehin erst dann auf
`.agent` zu, wenn Chroma/Redis bereits laufen — dort aendert sich nichts.
"""

from __future__ import annotations

from modules.security.adapters import register_all_adapters
from modules.security.manifest import module_manifest
from modules.security.routes import router

register_all_adapters()

__all__ = ["module_manifest", "agent", "router"]

_agent_instance = None


def __getattr__(name: str):
    """Lazy `agent`-Property. Beachte: `from modules.security.agent import X`
    bindet als Python-Nebenwirkung das SUBMODUL `agent.py` an das Attribut
    `modules.security.agent` — deshalb wird der `__dict__`-Eintrag danach
    explizit auf die Singleton-Instanz zurueckgesetzt, sonst wuerde jeder
    zweite Zugriff entweder das Submodul liefern oder (ueber diese Funktion)
    eine neue Instanz statt des Singletons."""
    global _agent_instance
    if name == "agent":
        if _agent_instance is None:
            import importlib

            # WICHTIG: `importlib.import_module()` statt `from modules.security
            # import agent` — Letzteres loest ueber den fromlist-Fastpath einen
            # getattr(modules.security, "agent") aus, was in DIESER Funktion
            # rekursiv wieder __getattr__("agent") aufrufen wuerde (RecursionError).
            agent_submodule = importlib.import_module("modules.security.agent")
            _agent_instance = agent_submodule.SecurityOrchestratorAgent()
        globals()["agent"] = _agent_instance
        return _agent_instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
