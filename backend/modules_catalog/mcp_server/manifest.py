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
    description="Generic Model Context Protocol integration for arbitrary MCP servers.",
    version="1.0.0",
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
        "icon": "🔌",
    },
    health_check=check_mcp_server_health,
)
