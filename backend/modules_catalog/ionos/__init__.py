"""IONOS DNS Modul – Package Init."""

from .manifest import module_manifest
from .agent import IonosAgent
from .routes import router

agent = IonosAgent()

__all__ = ["module_manifest", "agent", "router"]
