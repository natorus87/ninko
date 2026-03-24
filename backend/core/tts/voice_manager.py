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
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("ninko.core.tts.voices")

_HUGGINGFACE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


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

    def __init__(self, voices_dir: str | Path = "./voices"):
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
        """
        voice_dir = self.voices_dir / lang / voice
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
        voice_dir = self.voices_dir / lang / voice
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

        except Exception as exc:
            logger.error("Download fehlgeschlagen für '%s/%s': %s", lang, voice, exc)
            return False
