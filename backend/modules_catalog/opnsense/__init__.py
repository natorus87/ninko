"""OPNsense Modul – Package Init."""

from modules.opnsense.manifest import module_manifest
from modules.opnsense.agent import OPNsenseAgent
from modules.opnsense.routes import router

agent = OPNsenseAgent()

__all__ = ["module_manifest", "agent", "router"]
