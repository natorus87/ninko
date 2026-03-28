"""Checkmk Modul – Package Init."""

from modules.checkmk.manifest import module_manifest
from modules.checkmk.agent import CheckmkAgent
from modules.checkmk.routes import router

agent = CheckmkAgent()

__all__ = ["module_manifest", "agent", "router"]
