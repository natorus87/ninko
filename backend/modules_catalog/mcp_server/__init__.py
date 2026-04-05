"""MCP Server module package."""

from .agent import MCPServerAgent
from .manifest import module_manifest
from .routes import router

agent = MCPServerAgent()

__all__ = ["module_manifest", "agent", "router"]
