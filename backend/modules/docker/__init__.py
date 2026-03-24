"""Docker Modul – Package Init."""

from modules.docker.manifest import module_manifest
from modules.docker.agent import DockerAgent
from modules.docker.routes import router

agent = DockerAgent()

__all__ = ["module_manifest", "agent", "router"]
