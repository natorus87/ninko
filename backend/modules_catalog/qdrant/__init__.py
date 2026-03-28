"""
Qdrant Modul – Initialisierung für ModuleRegistry.
"""

from .manifest import module_manifest
from .agent import QdrantAgent
from .routes import router

agent = QdrantAgent()

__all__ = ["module_manifest", "agent", "router"]
