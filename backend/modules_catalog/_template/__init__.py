"""Template Modul – Package Init."""

from .manifest import module_manifest
from .agent import TemplateAgent
from .routes import router

# Ninko erwartet diese 3 Exporte pro Modul:
# 1. module_manifest (Metadaten & UI Infos)
# 2. agent (Der ausführende LLM-Worker)
# 3. router (Optional: API Endpunkte für das Frontend)

agent = TemplateAgent()

__all__ = ["module_manifest", "agent", "router"]
