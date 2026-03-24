"""
Piper TTS Service – startet Piper als Subprocess und gibt WAV-Audio zurück.

Jeder synthesize()-Aufruf startet einen eigenen Subprocess und nutzt
eigene Temp-Dateien → thread-safe, kein Shared State.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger("ninko.core.tts.piper")

_SYNTHESIZE_TIMEOUT = 30  # Sekunden


class PiperError(RuntimeError):
    """Wird geworfen wenn Piper-Binary fehlt oder Synthese fehlschlägt."""


class PiperService:
    """
    Wrapper für das Piper TTS-Binary.
    Prüft beim Erstellen ob das Binary vorhanden ist.
    """

    def __init__(self, piper_binary: str = "piper"):
        self.piper_binary = piper_binary
        self._check_binary()

    def _check_binary(self) -> None:
        """Prüft ob das Piper-Binary vorhanden ist."""
        if os.path.isabs(self.piper_binary):
            if not os.path.isfile(self.piper_binary):
                raise PiperError(
                    f"Piper-Binary nicht gefunden: {self.piper_binary}\n"
                    "Bitte PIPER_BINARY auf den korrekten Pfad setzen oder "
                    "piper im PATH bereitstellen (https://github.com/rhasspy/piper/releases)."
                )
        elif shutil.which(self.piper_binary) is None:
            raise PiperError(
                f"Piper-Binary '{self.piper_binary}' nicht im PATH gefunden.\n"
                "Installationsanleitung: https://github.com/rhasspy/piper/releases\n"
                "Oder PIPER_BINARY=/absoluter/pfad/piper in der Konfiguration setzen."
            )
        logger.info(
            "Piper-Binary gefunden: %s",
            shutil.which(self.piper_binary) or self.piper_binary,
        )

    async def synthesize(self, text: str, model_path: Path | str) -> bytes:
        """
        Synthetisiert Text zu WAV-Audio-Bytes.

        Startet Piper als Subprocess mit stdin-Text und --output_file.
        Jeder Aufruf ist isoliert (eigene Temp-Datei, eigener Prozess).

        Args:
            text: Zu sprechender Text (UTF-8).
            model_path: Pfad zur Piper .onnx-Modelldatei.

        Returns:
            WAV-Audio als bytes.

        Raises:
            PiperError: Binary fehlt, Modell fehlt, Timeout oder Fehler-Exit.
        """
        model_path = Path(model_path)
        if not model_path.exists():
            raise PiperError(f"Piper-Modell nicht gefunden: {model_path}")

        tmp_out: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_out = f.name

            cmd = [
                self.piper_binary,
                "--model", str(model_path),
                "--output_file", tmp_out,
            ]

            logger.debug("Starte Piper: %s", " ".join(cmd))

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                _, stderr = await asyncio.wait_for(
                    proc.communicate(input=text.encode("utf-8")),
                    timeout=_SYNTHESIZE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise PiperError(
                    f"Piper Timeout nach {_SYNTHESIZE_TIMEOUT}s – Text zu lang?"
                )

            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace").strip()
                raise PiperError(f"Piper Fehler (exit {proc.returncode}): {err[:300]}")

            with open(tmp_out, "rb") as f:
                wav_bytes = f.read()

            if not wav_bytes:
                raise PiperError("Piper hat leere Audio-Ausgabe erzeugt.")

            logger.debug("Piper Synthese erfolgreich: %d Bytes WAV", len(wav_bytes))
            return wav_bytes

        finally:
            if tmp_out and os.path.exists(tmp_out):
                try:
                    os.unlink(tmp_out)
                except OSError:
                    pass
