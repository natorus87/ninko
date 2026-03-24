"""
Audio-Konvertierungshelfer – alle Konvertierungen via ffmpeg subprocess.

Nutzt keine Python-Audio-Libraries, nur ffmpeg als externen Prozess.
ffmpeg ist bereits im Ninko-Docker-Image vorhanden (backend/Dockerfile).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile

logger = logging.getLogger("ninko.core.tts.audio")

_FFMPEG_TIMEOUT = 30  # Sekunden


def _check_ffmpeg() -> None:
    """Prüft ob ffmpeg im PATH vorhanden ist."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg nicht im PATH gefunden. "
            "Bitte ffmpeg installieren (apt-get install ffmpeg)."
        )


async def _convert(
    input_bytes: bytes,
    in_ext: str,
    out_ext: str,
    extra_args: list[str],
) -> bytes:
    """
    Generische ffmpeg-Konvertierung via Temp-Dateien.

    Args:
        input_bytes: Eingabe-Audio als bytes.
        in_ext: Dateiendung der Eingabe (z.B. ".wav").
        out_ext: Dateiendung der Ausgabe (z.B. ".ogg").
        extra_args: Zusätzliche ffmpeg-Argumente (Codec, Bitrate, …).

    Returns:
        Konvertiertes Audio als bytes.

    Raises:
        RuntimeError: ffmpeg fehlt oder Konvertierung fehlgeschlagen.
    """
    _check_ffmpeg()

    tmp_in: str | None = None
    tmp_out: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=in_ext, delete=False) as f:
            f.write(input_bytes)
            tmp_in = f.name

        with tempfile.NamedTemporaryFile(suffix=out_ext, delete=False) as f:
            tmp_out = f.name

        cmd = ["ffmpeg", "-y", "-i", tmp_in] + extra_args + [tmp_out]
        logger.debug("ffmpeg: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_FFMPEG_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"ffmpeg Timeout nach {_FFMPEG_TIMEOUT}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"ffmpeg Fehler (exit {proc.returncode}): {err[-300:]}"
            )

        with open(tmp_out, "rb") as f:
            result = f.read()

        logger.debug(
            "Audio-Konvertierung %s→%s: %d Bytes", in_ext, out_ext, len(result)
        )
        return result

    finally:
        for p in (tmp_in, tmp_out):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


async def wav_to_ogg(wav_bytes: bytes) -> bytes:
    """
    Konvertiert WAV-Audio zu OGG/Opus (für Telegram sendVoice).
    Telegram erwartet OGG-Container mit Opus-Codec.
    """
    return await _convert(
        wav_bytes,
        ".wav",
        ".ogg",
        ["-c:a", "libopus", "-b:a", "64k"],
    )


async def wav_to_mp3(wav_bytes: bytes) -> bytes:
    """
    Konvertiert WAV-Audio zu MP3 (für Teams-Attachment).
    """
    return await _convert(
        wav_bytes,
        ".wav",
        ".mp3",
        ["-c:a", "libmp3lame", "-q:a", "4"],
    )


async def ogg_to_wav(ogg_bytes: bytes) -> bytes:
    """
    Konvertiert OGG/Opus zu WAV (für STT-Input).
    Gibt Mono-16kHz-WAV zurück – optimal für Whisper.
    """
    return await _convert(
        ogg_bytes,
        ".ogg",
        ".wav",
        ["-ar", "16000", "-ac", "1"],
    )
