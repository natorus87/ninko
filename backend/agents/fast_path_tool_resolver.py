"""
Modul-agnostischer Tool-Resolver für deterministische Fast-Paths.

Ermöglicht dem Orchestrator, ein konkretes Tool-Callable aus einem
registrierten Modul-Agenten zu beziehen, ohne das Modul-Modul direkt
zu importieren. Dadurch bleibt die Architektur "Immutable Core +
auto-discovering Modules" erhalten: der Core kennt nur Tool-Namen,
nicht die konkrete Modul-Implementierung.
"""

from __future__ import annotations

from typing import Any

from core.module_registry import ModuleRegistry

_RESOLVER_EXCEPTIONS = (AttributeError, TypeError, ValueError, RuntimeError)


def try_get_module_tool(
    registry: ModuleRegistry | None,
    module_id: str,
    tool_name: str,
) -> Any | None:
    """Liefert das Tool-Callable eines registrierten Moduls oder None.

    Args:
        registry: Die ModuleRegistry (z.B. self.registry des Orchestrators).
        module_id: Technischer Modul-Name (z.B. "fritzbox", "proxmox").
        tool_name: Tool-Name (z.B. "get_fritz_devices").

    Returns:
        Das LangChain-BaseTool-Objekt, oder None wenn das Modul nicht
        geladen, der Agent nicht registriert oder das Tool darin nicht
        vorhanden ist.
    """
    if registry is None:
        return None
    try:
        agent = registry.get_agent(module_id)
    except _RESOLVER_EXCEPTIONS:
        return None
    if agent is None:
        return None
    try:
        tools = agent.tools
    except _RESOLVER_EXCEPTIONS:
        return None
    for t in tools or ():
        if getattr(t, "name", None) == tool_name:
            return t
    return None
