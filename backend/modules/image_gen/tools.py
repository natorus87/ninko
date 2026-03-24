"""
Image Generation Module – Werkzeug für KI-Bildgenerierung.
Unterstützt Together AI (Flux), OpenAI (DALL-E) und Google (Imagen).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.image_gen.tools")


@tool
async def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Generiert ein Bild mit einem KI-Bildgenerierungsmodell.
    Nutze dieses Tool wenn der User ein Bild, eine Illustration, ein Logo,
    ein Foto oder eine Grafik erstellen möchte.
    Gibt die URL des generierten Bildes zurück.

    Args:
        prompt: Detaillierte Beschreibung des gewünschten Bildes auf Englisch
                (bessere Ergebnisse bei englischen Prompts).
        size: Bildgröße, z.B. "1024x1024", "1024x1792", "1792x1024".
              Standard: "1024x1024".
    """
    from core.image_provider import generate_image as _gen

    try:
        result = await _gen(prompt=prompt, size=size)
        url = result["url"]
        # [KUMIO_IMAGE:...] wird vom Telegram-Bot und der Web-UI erkannt
        # und als Bild angezeigt (nicht als Text-URL)
        return (
            f"✅ Bild generiert!\n"
            f"[KUMIO_IMAGE:{url}]\n"
            f"Prompt: {prompt}\n"
            f"Provider: {result['backend']} ({result['model']})"
        )
    except ValueError as e:
        # Konfigurationsfehler – dem User klar sagen was fehlt
        return f"⚠️ Bildgenerierung nicht konfiguriert: {e}"
    except Exception as e:
        logger.error("Bildgenerierung fehlgeschlagen: %s", e, exc_info=True)
        return f"❌ Bildgenerierung fehlgeschlagen: {str(e)[:300]}"
