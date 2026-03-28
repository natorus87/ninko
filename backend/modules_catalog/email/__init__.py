from .manifest import module_manifest
from .agent import EmailAgent
from .routes import router

agent = EmailAgent()

__all__ = ["module_manifest", "agent", "router"]
