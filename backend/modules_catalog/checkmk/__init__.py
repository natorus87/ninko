"""Checkmk Modul – Package Init."""

from .manifest import module_manifest
from .agent import CheckmkAgent
from .routes import router

agent = CheckmkAgent()

__all__ = ["module_manifest", "agent", "router"]
