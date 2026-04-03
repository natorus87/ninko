"""Synology Modul – Package Init."""

from .manifest import module_manifest
from .agent import SynologyAgent
from .routes import router

agent = SynologyAgent()

__all__ = ["module_manifest", "agent", "router"]
