"""GLPI module — package init."""

from .manifest import module_manifest
from .agent import GlpiAgent
from .routes import router

agent = GlpiAgent()

__all__ = ["module_manifest", "agent", "router"]
