"""
Image Generation Module – Manifest.
KI-Bildgenerierung mit Together AI, OpenAI und Google.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("kumio.modules.image_gen")


async def check_image_gen_health() -> dict:
    """Health-Check für Bildgenerierung."""
    try:
        from core.image_provider import get_image_provider_config
        config = await get_image_provider_config()
        if config.get("backend") and config.get("api_key"):
            return {"status": "ok", "detail": f"Image Gen bereit ({config['backend']})"}
        return {"status": "warning", "detail": "Kein Provider konfiguriert"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="image_gen",
    display_name="Bildgenerierung",
    description="KI-Bildgenerierung – Bilder, Illustrationen, Logos mit Flux, DALL-E, Imagen",
    version="1.0.0",
    author="Kumio Team",
    enabled_by_default=True,
    env_prefix="IMAGE_GEN_",
    required_secrets=[],
    optional_secrets=["IMAGE_GEN_API_KEY"],
    routing_keywords=[
        "bild", "bild generieren", "bild erstellen", "bild machen",
        "image", "bildgenerierung", "illustration", "logo", "grafik",
        "bild zeichnen", "bild malen", "foto erstellen", "poster",
    ],
    api_prefix="/api/image-gen",
    dashboard_tab={"id": "image_gen", "label": "Bildgenerierung", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>'},
    health_check=check_image_gen_health,
)
