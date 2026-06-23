"""FritzBox module exports."""

from .agent import FritzBoxAgent
from .manifest import module_manifest
from .routes import router

__all__ = ["module_manifest", "agent", "router"]

agent = FritzBoxAgent()
