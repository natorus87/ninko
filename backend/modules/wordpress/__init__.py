"""WordPress Modul – Package Init."""

from modules.wordpress.manifest import module_manifest
from modules.wordpress.agent import WordPressAgent
from modules.wordpress.routes import router

agent = WordPressAgent()

__all__ = ["module_manifest", "agent", "router"]
