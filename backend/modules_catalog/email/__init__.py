from modules.email.manifest import module_manifest
from modules.email.agent import EmailAgent
from modules.email.routes import router

agent = EmailAgent()

__all__ = ["module_manifest", "agent", "router"]
