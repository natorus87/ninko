"""
TTS API – Stimmen-Verwaltung und Sprach-Synthese.

Endpunkte:
    GET  /api/tts/voices              – Installierte Stimmen auflisten
    GET  /api/tts/voices/catalog      – HuggingFace-Katalog + Installed-Status
    GET  /api/tts/piper/version       – Lokale und neueste Piper-Version
    POST /api/tts/synthesize          – Text zu WAV-Audio synthetisieren
    POST /api/tts/voices/download     – Stimme von HuggingFace herunterladen
    DELETE /api/tts/voices/{lang}/{voice} – Installierte Stimme löschen
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.config import get_settings

logger = logging.getLogger("ninko.api.tts")
router = APIRouter(prefix="/api/tts", tags=["TTS"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class VoiceEntry(BaseModel):
    name: str
    lang: str
    quality: str


class VoiceCatalogEntry(BaseModel):
    name: str
    lang: str
    quality: str
    installed: bool


class SynthesizeRequest(BaseModel):
    text: str
    lang: str | None = None
    voice: str | None = None


class DownloadRequest(BaseModel):
    lang: str
    voice: str


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _get_voice_manager() -> "VoiceManager":
    from core.tts.voice_manager import VoiceManager
    cfg = get_settings()
    return VoiceManager(voices_dir=cfg.VOICES_DIR)


def _parse_version_tuple(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", value or "")
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


# ─── Routen ───────────────────────────────────────────────────────────────────

@router.get("/voices", response_model=list[VoiceEntry])
async def list_voices() -> list[VoiceEntry]:
    """
    Alle lokal installierten Piper-Stimmen auflisten.
    Scannt das Voices-Verzeichnis live – kein Neustart nötig nach Download.
    """
    vm = _get_voice_manager()
    result: list[VoiceEntry] = []
    for lang in vm.list_languages():
        for voice in vm.list_voices(lang):
            result.append(VoiceEntry(name=voice.name, lang=voice.lang, quality=voice.quality))
    return result


@router.get("/voices/catalog", response_model=list[VoiceCatalogEntry])
async def list_voice_catalog(lang: str | None = None) -> list[VoiceCatalogEntry]:
    """
    Listet den verfügbaren HuggingFace-Katalog inkl. Installed-Status.
    Optionaler Sprachfilter über Query-Parameter `lang` (z.B. ?lang=de).
    """
    vm = _get_voice_manager()
    normalized_lang = (lang or "").strip().lower() or None

    installed_by_lang: dict[str, set[str]] = {}
    langs = [normalized_lang] if normalized_lang else vm.list_languages()
    for language in langs:
        if not language:
            continue
        installed_by_lang[language] = {voice.name for voice in vm.list_voices(language)}

    remote_catalog = await vm.fetch_voice_catalog(normalized_lang)
    return [
        VoiceCatalogEntry(
            name=entry["voice"],
            lang=entry["lang"],
            quality=entry["quality"],
            installed=entry["voice"] in installed_by_lang.get(entry["lang"], set()),
        )
        for entry in remote_catalog
    ]


@router.get("/piper/version")
async def get_piper_version() -> dict:
    """
    Gibt lokale Piper-Version und das aktuellste GitHub-Release zurück.
    """
    cfg = get_settings()
    binary = cfg.PIPER_BINARY

    local_version = ""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        local_version = output.splitlines()[0].strip() if output else ""
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, TypeError) as exc:
        logger.warning("Konnte lokale Piper-Version nicht lesen: %s", exc)

    latest_tag = ""
    latest_version = ""
    github_error = ""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get("https://api.github.com/repos/rhasspy/piper/releases/latest")
            resp.raise_for_status()
            payload = resp.json()
        latest_tag = str(payload.get("tag_name", "")).strip()
        latest_version = latest_tag.lstrip("v")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        github_error = str(exc)
        logger.warning("Konnte neuestes Piper-Release nicht lesen: %s", exc)

    local_normalized = local_version.lstrip("v")
    update_available = bool(
        local_normalized
        and latest_version
        and _parse_version_tuple(latest_version) > _parse_version_tuple(local_normalized)
    )

    return {
        "binary": binary,
        "local_version": local_version,
        "latest_tag": latest_tag,
        "latest_version": latest_version,
        "update_available": update_available,
        "github_error": github_error,
    }


@router.post("/synthesize")
async def synthesize(body: SynthesizeRequest) -> Response:
    """
    Synthetisiert einen Text zu WAV-Audio und gibt die Bytes zurück.
    Nutzt die konfigurierten Default-Werte wenn lang/voice fehlen.
    """
    from core.tts import synthesize_reply, is_tts_available
    from core.tts.piper_service import PiperError

    if not is_tts_available():
        raise HTTPException(
            status_code=503,
            detail="TTS ist deaktiviert oder Piper-Binary nicht gefunden. "
                   "TTS_ENABLED=true setzen und Piper installieren.",
        )

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text darf nicht leer sein.")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Text zu lang (max. 2000 Zeichen).")

    try:
        wav_bytes = await synthesize_reply(
            text=text,
            lang=body.lang or None,
            voice=body.voice or None,
        )
    except PiperError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=tts.wav"},
    )


@router.post("/voices/download")
async def download_voice(body: DownloadRequest) -> dict:
    """
    Lädt eine Piper-Stimme von HuggingFace (rhasspy/piper-voices) herunter.
    Die Stimme ist sofort nach dem Download verfügbar (kein Neustart nötig).
    """
    vm = _get_voice_manager()

    lang = body.lang.strip().lower()
    voice = body.voice.strip().lower()

    if not lang or not voice:
        raise HTTPException(status_code=400, detail="lang und voice sind Pflichtfelder.")

    # Bereits installiert?
    existing = vm.list_voices(lang)
    if any(v.name == voice for v in existing):
        return {"status": "already_installed", "lang": lang, "voice": voice}

    logger.info("Starte Stimmen-Download: %s/%s", lang, voice)
    success = await vm.download_voice(lang=lang, voice=voice)

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"Download fehlgeschlagen für '{lang}/{voice}'. "
                   "Bitte Stimmenname prüfen (Format: <speaker>-<quality>, z.B. thorsten-medium).",
        )

    logger.info("Stimme erfolgreich installiert: %s/%s", lang, voice)
    return {"status": "installed", "lang": lang, "voice": voice}


@router.delete("/voices/{lang}/{voice}")
async def delete_voice(lang: str, voice: str) -> dict:
    """
    Löscht eine installierte Piper-Stimme aus dem Voices-Verzeichnis.
    """
    cfg = get_settings()
    voice_dir = Path(cfg.VOICES_DIR) / lang / voice

    if not voice_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Stimme '{lang}/{voice}' nicht gefunden.",
        )

    try:
        shutil.rmtree(voice_dir)
        logger.info("Stimme gelöscht: %s/%s", lang, voice)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Löschen fehlgeschlagen: {exc}")

    return {"status": "deleted", "lang": lang, "voice": voice}
