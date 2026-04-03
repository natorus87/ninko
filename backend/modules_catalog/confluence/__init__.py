"""Confluence Modul – Package Init."""

from .manifest import module_manifest
from .agent import ConfluenceAgent
from .routes import router

agent = ConfluenceAgent()

__all__ = ["module_manifest", "agent", "router"]
