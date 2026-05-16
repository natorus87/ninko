"""MCP Server module manifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest
from agents.base_agent import _t


async def check_mcp_server_health(connection_id: str = "") -> dict:
    """Health check for the configured MCP server."""
    from .tools import get_mcp_server_status

    try:
        result = await get_mcp_server_status.ainvoke({"connection_id": connection_id})
        if isinstance(result, dict) and result.get("status") == "error":
            return {
                "status": "error",
                "detail": result.get("detail", _t("MCP-Fehler", "MCP error")),
            }
        return {
            "status": "ok",
            "detail": _t("MCP-Server erreichbar", "MCP server reachable"),
            "info": result,
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="mcp_server",
    display_name="MCP Server",
    description=(
        "Generic Model Context Protocol (MCP) integration: connect to arbitrary "
        "MCP servers, expose tools and resources via stdio."
    ),
    version="1.0.2",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="MCP_SERVER_",
    required_secrets=[],
    optional_secrets=["MCP_AUTH_TOKEN"],
    routing_keywords=[
        "mcp server",
        "model context protocol",
        "mcp tool",
        "mcp resource",
        "mcp stdio",
    ],
    api_prefix="/api/mcp-server",
    dashboard_tab={
        "id": "mcp_server",
        "label": "MCP Server",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="10" rx="2"/><path d="M9 12v2"/><path d="M15 12v2"/><rect x="3" y="14" width="18" height="8" rx="2"/><circle cx="8" cy="18" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="18" r="1" fill="currentColor" stroke="none"/><circle cx="16" cy="18" r="1" fill="currentColor" stroke="none"/></svg>',
    },
    health_check=check_mcp_server_health,
)
