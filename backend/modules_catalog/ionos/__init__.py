"""IONOS DNS Modul – Package Init."""

from modules.ionos.manifest import module_manifest
from modules.ionos.agent import IonosAgent
from modules.ionos.routes import router

agent = IonosAgent()

__all__ = ["module_manifest", "agent", "router"]
