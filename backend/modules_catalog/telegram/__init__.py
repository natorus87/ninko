"""
Telegram Bot module for Ninko.
Allows chatting with the agent via Telegram.
"""

from .manifest import module_manifest
from .agent import agent
from .routes import router

__all__ = ["module_manifest", "agent", "router"]
