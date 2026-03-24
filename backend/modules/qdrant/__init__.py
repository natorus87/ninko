"""
Qdrant Modul – Initialisierung für ModuleRegistry.
"""

from modules.qdrant.manifest import module_manifest
from modules.qdrant.agent import QdrantAgent
from modules.qdrant.routes import router

agent = QdrantAgent()

__all__ = ["module_manifest", "agent", "router"]
