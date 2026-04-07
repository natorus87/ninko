"""
Image Generation Module – KI-Bildgenerierung.
"""

from __future__ import annotations

from modules.image_gen.manifest import module_manifest
from modules.image_gen.agent import ImageGenAgent

agent = ImageGenAgent()

__all__ = ["module_manifest", "agent"]
