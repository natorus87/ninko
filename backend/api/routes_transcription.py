"""
Transkriptions-Endpunkt – konvertiert Audio zu Text.

Provider (STT_PROVIDER env):
  whisper          – lokales faster-whisper (Standard)
  openai_compatible – externe OpenAI-kompatible API (/v1/audio/transcriptions)

Whisper-Konfiguration:
  WHISPER_MODEL_SIZE  – tiny | base | small | medium | large-v3  (default: base)
  WHISPER_DEVICE      – cpu | cuda                               (default: cpu)
  WHISPER_COMPUTE_TYPE– int8 | float16 | float32                 (default: int8)
  WHISPER_LANGUAGE    – de | en | auto | …                       (default: de)

OpenAI-kompatibler Provider:
  STT_API_URL  – Base-URL (z.B. https://api.groq.com/openai/v1)
  STT_API_KEY  – API-Key
  STT_MODEL    – Modell (z.B. whisper-large-v3)
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from core.auth import resolve_request_auth_async
from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transcription", tags=["transcription"])

# Rate Limiting: Max 3 parallele Transkriptionen (CPU/GPU-intensiv)
_TRANSCRIPTION_SEMAPHORE = asyncio.Semaphore(3)

# ── Whisper-Modell-Cache (lazy, thread-safe) ──────────────────────────────────
_whisper_model: Any = None
_whisper_lock = threading.Lock()


async def _require_authenticated(request: Request) -> None:
    """Blockiert CPU/GPU-intensive STT-Endpunkte für anonyme Requests."""
    auth_ctx = await resolve_request_auth_async(request)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Authentication required.")


def _load_whisper_model() -> Any:
    """Lädt das Whisper-Modell beim ersten Aufruf (thread-safe, gecacht)."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper ist nicht installiert. "
                "Bitte 'faster-whisper' in requirements.txt hinzufügen."
            ) from exc

        model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

        logger.info(
            "Lade Whisper-Modell '%s' auf %s (compute_type=%s) …",
            model_size,
            device,
            compute_type,
        )
        _whisper_model = WhisperModel(
            model_size, device=device, compute_type=compute_type
        )
        logger.info("Whisper-Modell '%s' bereit.", model_size)
        return _whisper_model


def invalidate_whisper_cache() -> None:
    """Setzt den Whisper-Modell-Cache zurück (nach Einstellungsänderung)."""
    global _whisper_model
    with _whisper_lock:
        _whisper_model = None
    logger.info("Whisper-Modell-Cache invalidiert.")


# ── Schemas ───────────────────────────────────────────────────────────────────


class TranscriptionResponse(BaseModel):
    text: str
    language: str


class WhisperBenchmarkResult(BaseModel):
    model_size: str
    text: str
    language: str
    avg_confidence: float
    duration_ms: int


class WhisperBenchmarkResponse(BaseModel):
    results: list[WhisperBenchmarkResult]
    recommended_model: str


def _parse_csv_set(raw: str) -> set[str]:
    return {x.strip().lower() for x in (raw or "").split(",") if x.strip()}


def _validate_upload_meta(
    *,
    filename: str,
    content_type: str,
    byte_len: int,
) -> None:
    cfg = get_settings()
    max_bytes = int(cfg.TRANSCRIPTION_MAX_UPLOAD_BYTES)
    if byte_len <= 0:
        raise HTTPException(status_code=400, detail="Leere Audio-Datei empfangen.")
    if byte_len > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Audio-Datei zu groß ({byte_len} Bytes). Maximum: {max_bytes} Bytes."
            ),
        )

    ext = Path(filename).suffix.lower()
    allowed_ext = _parse_csv_set(cfg.TRANSCRIPTION_ALLOWED_EXTENSIONS)
    if ext not in allowed_ext:
        raise HTTPException(
            status_code=415,
            detail=f"Dateiendung '{ext or '<none>'}' nicht erlaubt.",
        )

    allowed_mime = _parse_csv_set(cfg.TRANSCRIPTION_ALLOWED_MIME)
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and ctype not in allowed_mime:
        raise HTTPException(
            status_code=415,
            detail=f"MIME-Type '{ctype}' nicht erlaubt.",
        )


# ── Provider-Implementierungen ────────────────────────────────────────────────


async def _transcribe_whisper(tmp_path: str) -> tuple[str, float, str]:
    """Transkribiert mit lokalem faster-whisper. Gibt (text, avg_conf, lang) zurück."""
    import asyncio

    language = os.getenv("WHISPER_LANGUAGE", "de")

    def do_transcribe() -> tuple[str, float, str]:
        model = _load_whisper_model()
        lang_arg: str | None = language if language != "auto" else None
        segments_gen, info = model.transcribe(tmp_path, language=lang_arg)
        segments = list(segments_gen)
        text = " ".join(s.text.strip() for s in segments).strip()
        avg_conf = (
            sum(s.avg_logprob for s in segments) / len(segments) if segments else -2.0
        )
        return text, avg_conf, info.language

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, do_transcribe)


async def _transcribe_whisper_with_model(
    tmp_path: str, model_size: str
) -> tuple[str, float, str]:
    """Transkribiert mit explizitem Whisper-Modell (ohne globalen Cache)."""
    import asyncio
    from faster_whisper import WhisperModel  # type: ignore

    language = os.getenv("WHISPER_LANGUAGE", "de")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    def do_transcribe() -> tuple[str, float, str]:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        lang_arg: str | None = language if language != "auto" else None
        segments_gen, info = model.transcribe(tmp_path, language=lang_arg)
        segments = list(segments_gen)
        text = " ".join(s.text.strip() for s in segments).strip()
        avg_conf = (
            sum(s.avg_logprob for s in segments) / len(segments) if segments else -2.0
        )
        return text, avg_conf, info.language

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, do_transcribe)


async def _transcribe_openai_compatible(
    tmp_path: str, filename: str
) -> tuple[str, float, str]:
    """Transkribiert über externe OpenAI-kompatible API."""
    import httpx

    base_url = os.getenv("STT_API_URL", "").rstrip("/")
    api_key = os.getenv("STT_API_KEY", "")
    model = os.getenv("STT_MODEL", "whisper-large-v3")
    language = os.getenv("WHISPER_LANGUAGE", "de")

    if not base_url:
        raise RuntimeError("STT_API_URL ist nicht konfiguriert.")

    endpoint = f"{base_url}/audio/transcriptions"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    ext = Path(filename).suffix.lower() or ".webm"
    mime = (
        "audio/webm"
        if ext == ".webm"
        else "audio/ogg"
        if ext == ".ogg"
        else "audio/mpeg"
    )

    with open(tmp_path, "rb") as f:
        audio_data = f.read()

    files = {"file": (filename, audio_data, mime)}
    data: dict[str, str] = {"model": model, "response_format": "json"}
    if language and language != "auto":
        data["language"] = language

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(endpoint, headers=headers, files=files, data=data)
        if resp.status_code != 200:
            raise RuntimeError(f"STT-API Fehler {resp.status_code}: {resp.text[:200]}")
        result = resp.json()

    text = result.get("text", "").strip()
    detected_lang = result.get("language", language or "unknown")
    return text, 0.0, detected_lang


# ── Endpunkt ──────────────────────────────────────────────────────────────────


@router.post("/", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request, file: UploadFile = File(...)
) -> TranscriptionResponse:
    """
    Transkribiert eine hochgeladene Audio-Datei zu Text.
    Wird vom Chat-Dashboard (Mikrofon-Button) und den Bot-Modulen genutzt.
    """
    await _require_authenticated(request)
    content = await file.read()
    filename = file.filename or "audio.webm"
    _validate_upload_meta(
        filename=filename,
        content_type=file.content_type or "",
        byte_len=len(content),
    )
    ext = Path(filename).suffix.lower() or ".ogg"

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        provider = os.getenv("STT_PROVIDER", "whisper")

        # Rate Limiting: Semaphore für CPU/GPU-intensive Transkription
        async with _TRANSCRIPTION_SEMAPHORE:
            if provider == "openai_compatible":
                text, _, detected_lang = await _transcribe_openai_compatible(
                    tmp_path, filename
                )
            else:
                text, _, detected_lang = await _transcribe_whisper(tmp_path)

        if not text:
            raise HTTPException(
                status_code=422,
                detail="Keine Sprache erkannt – Aufnahme zu kurz oder zu leise?",
            )

        logger.info("Transkription [%s/%s]: %.80s…", provider, detected_lang, text)
        return TranscriptionResponse(text=text, language=detected_lang)

    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Transkriptionsfehler: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Transkription fehlgeschlagen: {exc}"
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/whisper/benchmark", response_model=WhisperBenchmarkResponse)
async def benchmark_whisper_models(
    request: Request,
    file: UploadFile = File(...),
    models: str = "base,small",
) -> WhisperBenchmarkResponse:
    """
    Vergleicht mehrere Whisper-Modelle auf derselben Audio-Datei.
    Standardmäßig: base vs small.
    """
    await _require_authenticated(request)
    content = await file.read()
    filename = file.filename or "audio.webm"
    _validate_upload_meta(
        filename=filename,
        content_type=file.content_type or "",
        byte_len=len(content),
    )
    ext = Path(filename).suffix.lower() or ".ogg"

    requested = [m.strip().lower() for m in models.split(",") if m.strip()]
    seen: set[str] = set()
    ordered_models = []
    for model_name in requested:
        if model_name in seen:
            continue
        seen.add(model_name)
        ordered_models.append(model_name)
    if not ordered_models:
        raise HTTPException(status_code=400, detail="Mindestens ein Modell angeben.")

    allowed = {"tiny", "base", "small", "medium", "large-v3"}
    invalid = [m for m in ordered_models if m not in allowed]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Modelle: {', '.join(invalid)}. Erlaubt: {', '.join(sorted(allowed))}",
        )

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        results: list[WhisperBenchmarkResult] = []
        for model_name in ordered_models:
            start = time.perf_counter()
            text, avg_conf, detected_lang = await _transcribe_whisper_with_model(
                tmp_path, model_name
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                WhisperBenchmarkResult(
                    model_size=model_name,
                    text=text,
                    language=detected_lang,
                    avg_confidence=avg_conf,
                    duration_ms=duration_ms,
                )
            )

        # Höhere avg_logprob ist besser (weniger negativ), bei Gleichstand schnelleres Modell.
        best = sorted(
            results, key=lambda r: (r.avg_confidence, -r.duration_ms), reverse=True
        )[0]
        return WhisperBenchmarkResponse(
            results=results, recommended_model=best.model_size
        )

    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.error("Whisper-Benchmark Dienst nicht verfügbar: %s", exc)
        raise HTTPException(status_code=503, detail="Transcription service unavailable.") from exc
    except (ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Whisper-Benchmark fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail="Benchmark failed.") from exc
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Hilfsfunktionen für Bot-Module ────────────────────────────────────────────


async def transcribe_bytes(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """
    Hilfsfunktion für Bot-Module (Telegram, Teams):
    Transkribiert rohe Audio-Bytes und gibt den Text zurück.
    """
    text, _, _ = await transcribe_bytes_extended(audio_bytes, filename)
    return text


async def transcribe_bytes_extended(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
) -> tuple[str, float, str]:
    """
    Erweiterte Transkriptions-Hilfsfunktion für Bot-Module.

    Returns:
        (text, avg_confidence, detected_language)
    """
    _validate_upload_meta(
        filename=filename,
        content_type="",
        byte_len=len(audio_bytes),
    )
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        provider = os.getenv("STT_PROVIDER", "whisper")

        if provider == "openai_compatible":
            text, avg_conf, detected_lang = await _transcribe_openai_compatible(
                tmp_path, filename
            )
        else:
            text, avg_conf, detected_lang = await _transcribe_whisper(tmp_path)

        # ── STT Spellcheck (optional) ──────────────────────────────────────────
        if text and os.getenv("STT_SPELLCHECK", "false").lower() in ("true", "1"):
            text = await _llm_spellcheck(text)

        return text, avg_conf, detected_lang

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def _llm_spellcheck(text: str) -> str:
    """
    Optionaler LLM-Pass zur Rechtschreibkorrektur nach STT.
    Wird nur aufgerufen wenn STT_SPELLCHECK=true.
    """
    try:
        from core.llm_factory import get_llm

        llm = get_llm()
        prompt = (
            f"Korrigiere Rechtschreib- und Grammatikfehler in diesem transkribierten Text. "
            f"Ändere den Inhalt und die Bedeutung nicht. Gib NUR den korrigierten Text aus, "
            f"ohne Erklärungen:\n\n{text}"
        )
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        corrected = (
            result.content.strip()
            if hasattr(result, "content")
            else str(result).strip()
        )
        if corrected:
            logger.debug("STT Spellcheck: '%s' → '%s'", text[:60], corrected[:60])
            return corrected
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.warning("STT Spellcheck fehlgeschlagen: %s", exc)
    return text
