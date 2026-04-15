"""
Scripting MVP Module.
Persistente Python-Skripte mit sicherer Ausführung.
"""

from __future__ import annotations

from modules.scripting.manifest import module_manifest
from modules.scripting.routes import router

__all__ = ["module_manifest", "router"]
