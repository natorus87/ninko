"""CodeLab Modul – Package Init."""

from modules.codelab.manifest import module_manifest
from modules.codelab.agent import CodelabAgent
from modules.codelab.routes import router

agent = CodelabAgent()

__all__ = ["module_manifest", "agent", "router"]
