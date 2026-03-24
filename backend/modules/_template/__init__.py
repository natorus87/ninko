"""Template Modul – Package Init."""

from modules._template.manifest import module_manifest
from modules._template.agent import TemplateAgent
from modules._template.routes import router

# Kumio erwartet diese 3 Exporte pro Modul:
# 1. module_manifest (Metadaten & UI Infos)
# 2. agent (Der ausführende LLM-Worker)
# 3. router (Optional: API Endpunkte für das Frontend)

agent = TemplateAgent()

__all__ = ["module_manifest", "agent", "router"]
