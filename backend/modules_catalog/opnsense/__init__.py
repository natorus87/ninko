"""OPNsense Modul – Package Init."""

from .manifest import module_manifest
from .agent import OPNsenseAgent
from .routes import router

agent = OPNsenseAgent()

__all__ = ["module_manifest", "agent", "router"]
