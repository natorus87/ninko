"""
Telegram Bot Modul für Ninko.
Erlaubt das Chatten mit dem Agenten via Telegram.
"""

from .manifest import module_manifest
from .agent import agent
from .routes import router

__all__ = ["module_manifest", "agent", "router"]
