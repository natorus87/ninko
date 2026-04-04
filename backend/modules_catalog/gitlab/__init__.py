"""GitLab module exports."""

from modules_catalog.gitlab.manifest import module_manifest
from modules_catalog.gitlab.agent import agent
from modules_catalog.gitlab.routes import router

__all__ = ["module_manifest", "agent", "router"]
