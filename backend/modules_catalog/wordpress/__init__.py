"""WordPress Module — Package init."""

from .manifest import module_manifest
from .agent import WordPressAgent
from .routes import router

agent = WordPressAgent()

__all__ = ["module_manifest", "agent", "router"]
