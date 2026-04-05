"""MCP Server specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent, _t

from .tools import (
    call_mcp_server_tool,
    get_mcp_server_status,
    list_mcp_server_resources,
    list_mcp_server_tools,
    read_mcp_server_resource,
    validate_mcp_server_connection,
)

MCP_SERVER_SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos MCP-Server-Spezialist.

Deine Aufgaben:
- Prüfe, ob eine MCP-Server-Verbindung korrekt konfiguriert ist
- Liste MCP-Tools und MCP-Resources auf
- Lies Resources gezielt aus
- Rufe MCP-Tools mit klaren Argumenten auf

Arbeitsweise:
- Prüfe zuerst den Serverstatus, wenn die Verbindung unklar ist
- Nutze validate_mcp_server_connection, wenn Konfigurationsfehler wahrscheinlich sind
- Nutze list_mcp_server_tools vor call_mcp_server_tool, wenn Toolnamen noch nicht bekannt sind
- Erkläre klar, wenn ein Transport im ersten Slice noch nicht vollständig unterstützt wird
- Erfinde keine MCP-Toolnamen oder Resource-URIs""",
    en="""You are Ninko's MCP Server specialist.

Your job:
- Verify whether an MCP server connection is configured correctly
- List MCP tools and MCP resources
- Read resources on demand
- Call MCP tools with clear arguments

Behavior:
- Check server status first when the connection is unclear
- Use list_mcp_server_tools before call_mcp_server_tool when tool names are unknown
- Explain clearly when a transport is not fully supported in this first slice
- Never invent MCP tool names or resource URIs""",
)


class MCPServerAgent(BaseAgent):
    """Specialist agent for generic MCP server integrations."""

    def __init__(self) -> None:
        super().__init__(
            name="mcp_server",
            system_prompt=MCP_SERVER_SYSTEM_PROMPT,
            tools=[
                get_mcp_server_status,
                validate_mcp_server_connection,
                list_mcp_server_tools,
                list_mcp_server_resources,
                read_mcp_server_resource,
                call_mcp_server_tool,
            ],
        )
