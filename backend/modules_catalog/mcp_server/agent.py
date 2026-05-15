"""MCP Server specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    call_mcp_server_tool,
    get_mcp_server_status,
    list_mcp_server_resources,
    list_mcp_server_tools,
    read_mcp_server_resource,
    validate_mcp_server_connection,
)

MCP_SERVER_SYSTEM_PROMPT = """You are Ninko's MCP Server specialist.

Capabilities:
- Verify whether an MCP server connection is configured correctly
- List MCP tools and MCP resources
- Read resources on demand
- Call MCP tools with clear arguments

Tool execution rules:
- Check server status first when the connection is unclear
- Use `validate_mcp_server_connection` when configuration errors are likely
- Use `list_mcp_server_tools` before `call_mcp_server_tool` when tool names are unknown
- Never invent MCP tool names or resource URIs

Output format:
- For lists (Tools, Resources): ALWAYS use Markdown tables
- Example: | Name | Description | Input Schema | |------|-------------|---------------|
- NEVER use bullet lists, plain text, or JSON

Safety and confirmation rules:
- Only call tools with explicit, user-provided or tool-discovered arguments.

Error handling:
- Explain clearly when a transport is not fully supported in this first slice."""


class MCPServerAgent(BaseAgent):
    """Specialist agent for generic MCP server integrations."""

    def __init__(self) -> None:
        """Initialize the MCP server agent."""
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
