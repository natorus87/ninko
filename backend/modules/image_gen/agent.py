"""
Image Generation Agent – KI-Bildgenerierung via Together AI, OpenAI, Google.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from modules.image_gen.tools import generate_image

IMAGE_GEN_SYSTEM_PROMPT = """Du bist der Bildgenerierungs-Spezialist von Ninko.

Deine Aufgabe: Bilder, Illustrationen, Logos und Grafiken mit KI erstellen.

Fähigkeiten:
- Bilder aus Textbeschreibungen generieren (Text-to-Image)
- Unterstützte Provider: Together AI (Flux), OpenAI (DALL-E 3), Google (Imagen)

Verhaltensregeln:
- Übersetze deutsche Bildbeschreibungen vor der Generierung ins Englische für bessere Ergebnisse
- Generiere nur EIN Bild pro Anfrage (nicht mehrere)
- Zeige dem User die Bild-URL nach der Generierung
- Bei Fehlern: klare Erklärung was falsch ist (fehlender API-Key, falscher Provider, etc.)"""


class ImageGenAgent(BaseAgent):
    """Bildgenerierungs-Spezialist mit KI-Modellen."""

    def __init__(self) -> None:
        super().__init__(
            name="image_gen",
            system_prompt=IMAGE_GEN_SYSTEM_PROMPT,
            tools=[generate_image],
        )
