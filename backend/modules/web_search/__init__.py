"""
Web Search Modul – Initialisierung für ModuleRegistry.
"""

from modules.web_search.manifest import module_manifest
from modules.web_search.agent import WebSearchAgent
from modules.web_search.routes import router

agent = WebSearchAgent()

__all__ = ["module_manifest", "agent", "router"]
