"""Pi-hole Modul – Package Init."""

from modules.pihole.manifest import module_manifest
from modules.pihole.agent import PiholeAgent
from modules.pihole.routes import router

agent = PiholeAgent()

__all__ = ["module_manifest", "agent", "router"]
