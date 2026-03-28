"""Pi-hole Modul – Package Init."""

from .manifest import module_manifest
from .agent import PiholeAgent
from .routes import router

agent = PiholeAgent()

__all__ = ["module_manifest", "agent", "router"]
