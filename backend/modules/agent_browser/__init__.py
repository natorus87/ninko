"""
Agent Browser Modul – Initialisierung für ModuleRegistry.
"""

from modules.agent_browser.manifest import module_manifest
from modules.agent_browser.agent import AgentBrowserAgent
from modules.agent_browser.routes import router

agent = AgentBrowserAgent()

__all__ = ["module_manifest", "agent", "router"]
