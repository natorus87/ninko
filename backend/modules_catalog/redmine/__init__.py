"""Redmine Modul – Package Init."""

from .manifest import module_manifest
from .agent import RedmineAgent
from .routes import router

agent = RedmineAgent()

__all__ = ["module_manifest", "agent", "router"]
