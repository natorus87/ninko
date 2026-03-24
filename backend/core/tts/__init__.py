"""
Ninko Core TTS – öffentliche API.

Zentrale Einstiegspunkte für alle Module:

    from core.tts import synthesize_reply, is_tts_available

    # Audio für eine Agent-Antwort erzeugen (nutzt Config-Defaults)
    wav_bytes = await synthesize_reply("Hallo, ich bin Ninko.")

    # Mit expliziter Stimme
    wav_bytes = await synthesize_reply("Hello", lang="en", voice="lessac-medium")
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ninko.core.tts")

# Lazy-initialisierter Service-Singleton
_service: object | None = None


def _get_service():
    """Gibt den PiperService zurück (lazy init, cached)."""
    global _service
    if _service is None:
        from core.config import get_settings
        from .piper_service import PiperService

        cfg = get_settings()
        _service = PiperService(piper_binary=cfg.PIPER_BINARY)
    return _service


def is_tts_available() -> bool:
    """
    Gibt True zurück wenn TTS aktiviert ist und das Piper-Binary vorhanden ist.
    Keine Exception – sicher zum Prüfen vor dem Einsatz.
    """
    try:
        from core.config import get_settings
        cfg = get_settings()
        if not cfg.TTS_ENABLED:
            return False
        _get_service()
        return True
    except Exception:
        return False


async def synthesize_reply(
    text: str,
    lang: str | None = None,
    voice: str | None = None,
) -> bytes:
    """
    Erzeugt WAV-Audio für eine Agent-Antwort.

    Nutzt die TTS-Konfiguration aus CoreSettings als Defaults.
    Wird von Bot-Modulen (Telegram, Teams) für automatische Voice-Antworten genutzt.

    Args:
        text: Zu sprechender Text.
        lang: Sprach-Code (z.B. "de"). None = TTS_DEFAULT_LANG aus Config.
        voice: Stimmenname (z.B. "thorsten-medium"). None = TTS_DEFAULT_VOICE aus Config.

    Returns:
        WAV-Audio als bytes.

    Raises:
        PiperError: Piper-Binary fehlt oder Synthese fehlgeschlagen.
        FileNotFoundError: Stimme nicht vorhanden im voices_dir.
        RuntimeError: TTS ist deaktiviert (TTS_ENABLED=false).
    """
    from core.config import get_settings
    from .voice_manager import VoiceManager

    cfg = get_settings()
    if not cfg.TTS_ENABLED:
        raise RuntimeError(
            "TTS ist deaktiviert (TTS_ENABLED=false). "
            "In der Konfiguration aktivieren."
        )

    vm = VoiceManager(voices_dir=cfg.VOICES_DIR)
    voice_path: Path = vm.get_voice_path(
        lang=lang or cfg.TTS_DEFAULT_LANG,
        voice=voice or cfg.TTS_DEFAULT_VOICE,
    )

    service = _get_service()
    return await service.synthesize(text=text, model_path=voice_path)


__all__ = ["synthesize_reply", "is_tts_available"]
