"""
Voice Manager – verwaltet lokale Piper-Stimmen.

Scannt das Voices-Verzeichnis bei jedem Aufruf dynamisch (kein Cache) →
neue Stimmen werden sofort gefunden ohne Neustart.

Erwartete Verzeichnisstruktur:
  <voices_dir>/<lang>/<voice_name>/<model>.onnx
  <voices_dir>/<lang>/<voice_name>/<model>.onnx.json

Beispiel:
  voices/de/thorsten-medium/de_DE-thorsten-medium.onnx
  voices/de/thorsten-medium/de_DE-thorsten-medium.onnx.json
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("ninko.core.tts.voices")

_VOICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_VOICE_DOWNLOAD_EXCEPTIONS = (
    httpx.HTTPError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _safe_voice_path(voices_dir: Path, lang: str, voice: str) -> Path:
    """Baut einen sicheren Pfad zu <voices_dir>/<lang>/<voice>.

    Wirft ValueError bei ungültigen Namen oder Path-Traversal-Versuchen.
    """
    if not isinstance(lang, str) or not _VOICE_NAME_RE.match(lang):
        raise ValueError(f"ungültiger Sprachcode: {lang!r}")
    if not isinstance(voice, str) or not _VOICE_NAME_RE.match(voice):
        raise ValueError(f"ungültiger Stimmenname: {voice!r}")
    base = Path(voices_dir).resolve()
    target = (base / lang / voice).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Pfad außerhalb von voices_dir: {target}")
    return target


_HUGGINGFACE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_HUGGINGFACE_TREE_API = "https://huggingface.co/api/models/rhasspy/piper-voices/tree/main"
_CATALOG_CACHE_TTL_SECONDS = 600.0

_catalog_cache_data: list[dict[str, str]] = []
_catalog_cache_ts: float = 0.0


@dataclass
class VoiceInfo:
    name: str
    lang: str
    quality: str
    path: Path
    config_path: Path


class VoiceManager:
    """
    Verwaltet lokale Piper-Stimmen und kann neue Stimmen von HuggingFace laden.
    """

    def __init__(self, voices_dir: str | Path = "./voices") -> None:
        self.voices_dir = Path(voices_dir)

    def list_languages(self) -> list[str]:
        """Gibt alle verfügbaren Sprachen zurück."""
        if not self.voices_dir.exists():
            return []
        return sorted(d.name for d in self.voices_dir.iterdir() if d.is_dir())

    def list_voices(self, lang: str) -> list[VoiceInfo]:
        """Gibt alle verfügbaren Stimmen für eine Sprache zurück."""
        lang_dir = self.voices_dir / lang
        if not lang_dir.exists():
            return []

        voices = []
        for voice_dir in sorted(lang_dir.iterdir()):
            if not voice_dir.is_dir():
                continue
            for onnx_file in voice_dir.glob("*.onnx"):
                config_file = onnx_file.with_suffix(".onnx.json")
                if not config_file.exists():
                    continue
                # Qualität aus Dateiname ableiten (z.B. de_DE-thorsten-medium → "medium")
                parts = onnx_file.stem.split("-")
                quality = parts[-1] if len(parts) >= 2 else "unknown"
                voices.append(
                    VoiceInfo(
                        name=voice_dir.name,
                        lang=lang,
                        quality=quality,
                        path=onnx_file,
                        config_path=config_file,
                    )
                )
        return voices

    def get_voice_path(self, lang: str, voice: str) -> Path:
        """
        Gibt den Pfad zur .onnx-Datei zurück.
        Sucht in <voices_dir>/<lang>/<voice>/<model>.onnx

        Raises:
            FileNotFoundError: Stimme nicht gefunden oder .onnx.json fehlt.
            ValueError: ungültiger Sprach- oder Stimmenname.
        """
        voice_dir = _safe_voice_path(self.voices_dir, lang, voice)
        if not voice_dir.exists():
            available = self.list_languages()
            raise FileNotFoundError(
                f"Stimme '{lang}/{voice}' nicht gefunden in {self.voices_dir}.\n"
                f"Verfügbare Sprachen: {available}\n"
                "Stimmen herunterladen mit: scripts/download_voices.sh"
            )

        for onnx_file in sorted(voice_dir.glob("*.onnx")):
            config_file = onnx_file.with_suffix(".onnx.json")
            if config_file.exists():
                return onnx_file

        raise FileNotFoundError(
            f"Keine .onnx-Datei (mit .onnx.json) in {voice_dir} gefunden."
        )

    async def download_voice(self, lang: str, voice: str) -> bool:
        """
        Lädt eine Stimme von HuggingFace herunter.

        HuggingFace-Struktur (rhasspy/piper-voices):
            <lang_short>/<lang_code>/<speaker>/<quality>/<model>.onnx
        Beispiel: de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx

        Der voice-Parameter enthält Speaker und Quality zusammen, z.B. "thorsten-medium".
        Die Methode leitet Speaker und Quality daraus ab.

        Args:
            lang: Sprach-Code (z.B. "de").
            voice: Stimmenname als "<speaker>-<quality>" (z.B. "thorsten-medium").

        Returns:
            True wenn erfolgreich heruntergeladen.
        """
        voice_dir = _safe_voice_path(self.voices_dir, lang, voice)
        voice_dir.mkdir(parents=True, exist_ok=True)

        lang_short = lang[:2].lower()
        lang_upper = lang_short.upper()
        lang_code = f"{lang_short}_{lang_upper}"  # z.B. "de_DE"

        # Speaker und Quality aus voice-Name ableiten (z.B. "thorsten-medium" → "thorsten", "medium")
        parts = voice.rsplit("-", 1)
        speaker = parts[0] if len(parts) == 2 else voice
        quality = parts[1] if len(parts) == 2 else "medium"
        file_stem = f"{lang_code}-{voice}"

        # Kanonischer HF-Pfad
        hf_path = f"{lang_short}/{lang_code}/{speaker}/{quality}/{file_stem}"

        onnx_url = f"{_HUGGINGFACE_BASE}/{hf_path}.onnx"
        json_url = f"{_HUGGINGFACE_BASE}/{hf_path}.onnx.json"

        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                r = await client.get(onnx_url)
                if r.status_code != 200:
                    logger.error(
                        "Download fehlgeschlagen (HTTP %s): %s", r.status_code, onnx_url
                    )
                    return False

                (voice_dir / f"{file_stem}.onnx").write_bytes(r.content)
                logger.info("Heruntergeladen: %s (%d KB)", onnx_url, len(r.content) // 1024)

                r2 = await client.get(json_url)
                if r2.status_code == 200:
                    (voice_dir / f"{file_stem}.onnx.json").write_bytes(r2.content)
                    logger.info("Heruntergeladen: %s", json_url)

            return True

        except _VOICE_DOWNLOAD_EXCEPTIONS as exc:
            logger.error("Download fehlgeschlagen für '%s/%s': %s", lang, voice, exc)
            return False

    async def fetch_voice_catalog(self, lang: str | None = None) -> list[dict[str, str]]:
        """
        Lädt den verfügbaren Stimmen-Katalog aus HuggingFace.

        Returns eine Liste mit Einträgen:
            {"lang": "de", "voice": "thorsten-medium", "quality": "medium"}
        """
        normalized_lang = (lang or "").strip().lower()
        catalog = await self._fetch_catalog_cached()
        if not normalized_lang:
            return catalog
        return [entry for entry in catalog if entry.get("lang") == normalized_lang]

    async def _fetch_catalog_cached(self) -> list[dict[str, str]]:
        """Liest den HF-Katalog mit TTL-Cache."""
        global _catalog_cache_data, _catalog_cache_ts
        now = time.monotonic()
        if _catalog_cache_data and (now - _catalog_cache_ts) < _CATALOG_CACHE_TTL_SECONDS:
            return _catalog_cache_data

        catalog = await self._fetch_catalog_from_hf()
        if catalog:
            _catalog_cache_data = catalog
            _catalog_cache_ts = now
        return catalog

    async def _fetch_catalog_from_hf(self) -> list[dict[str, str]]:
        """
        Holt die Dateibaum-Liste aus HF und extrahiert Stimmen aus *.onnx-Pfaden.
        Erwarteter Pfad:
            <lang_short>/<lang_code>/<speaker>/<quality>/<lang_code-speaker-quality>.onnx
        """
        url = f"{_HUGGINGFACE_TREE_API}?recursive=true"
        catalog: dict[tuple[str, str], dict[str, str]] = {}

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
        except _VOICE_DOWNLOAD_EXCEPTIONS as exc:
            logger.warning("Konnte HF-Stimmenkatalog nicht laden: %s", exc)
            return []

        if not isinstance(payload, list):
            logger.warning("Unerwartetes HF-Katalogformat: %s", type(payload).__name__)
            return []

        for item in payload:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", ""))
            if not path.endswith(".onnx"):
                continue
            parts = path.split("/")
            if len(parts) < 5:
                continue

            lang_short = parts[0].strip().lower()
            speaker = parts[2].strip().lower()
            quality = parts[3].strip().lower()
            if not lang_short or not speaker or not quality:
                continue

            voice_name = f"{speaker}-{quality}"
            key = (lang_short, voice_name)
            catalog[key] = {"lang": lang_short, "voice": voice_name, "quality": quality}

        return sorted(catalog.values(), key=lambda x: (x["lang"], x["voice"]))
