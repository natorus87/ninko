"""Docker Modul – Package Init."""

from .manifest import module_manifest
from .agent import DockerAgent
from .routes import router

agent = DockerAgent()

__all__ = ["module_manifest", "agent", "router"]
