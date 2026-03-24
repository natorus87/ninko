"""GLPI Modul – Package Init."""

from modules.glpi.manifest import module_manifest
from modules.glpi.agent import GlpiAgent
from modules.glpi.routes import router

agent = GlpiAgent()

__all__ = ["module_manifest", "agent", "router"]
