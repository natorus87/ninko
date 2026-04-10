"""
OCR service with two provider modes:
- python (pytesseract)
- llm_vision (OpenAI-compatible vision API)
"""

from __future__ import annotations

import base64
import io
import logging
import os

import httpx

from core.config import get_settings

logger = logging.getLogger("ninko.core.ocr")


def _normalize_mime(mime_type: str, filename: str = "") -> str:
    mime = (mime_type or "").strip().lower()
    if mime:
        return mime
    ext = os.path.splitext(filename.lower())[1]
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(ext, "application/octet-stream")


def _prepare_vision_base_url(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if not base:
        return base
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _extract_openai_message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    txt = str(item.get("text", "")).strip()
                    if txt:
                        parts.append(txt)
        return "\n".join(parts).strip()
    return ""


async def _ocr_python(image_bytes: bytes, language: str) -> str:
    try:
        from PIL import Image, UnidentifiedImageError  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Python OCR nicht verfügbar: bitte `pytesseract` + `Pillow` installieren."
        ) from exc

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            text = pytesseract.image_to_string(img, lang=language or "deu+eng")
        return (text or "").strip()
    except (UnidentifiedImageError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Python OCR fehlgeschlagen: {exc}") from exc


async def _ocr_llm_vision(
    image_bytes: bytes,
    mime_type: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
) -> str:
    if not base_url:
        raise RuntimeError("OCR_VISION_API_URL ist nicht gesetzt.")
    if not model:
        raise RuntimeError("OCR_VISION_MODEL ist nicht gesetzt.")
    if not api_key:
        raise RuntimeError("OCR_VISION_API_KEY ist nicht gesetzt.")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"
    endpoint = f"{_prepare_vision_base_url(base_url)}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.0,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Vision-API Anfrage fehlgeschlagen: {exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"Vision-API Fehler {resp.status_code}: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError("Vision-API lieferte ungültiges JSON.") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, TypeError, IndexError) as exc:
        raise RuntimeError("Ungültige Vision-API Antwortstruktur.") from exc
    text = _extract_openai_message_text(content)
    return text.strip()


async def extract_text_from_image_bytes(
    image_bytes: bytes,
    *,
    mime_type: str = "",
    filename: str = "",
) -> dict:
    """Run OCR and return normalized result payload."""
    cfg = get_settings()
    provider = (cfg.OCR_PROVIDER or "python").strip().lower()
    mime = _normalize_mime(mime_type, filename)

    if provider == "llm_vision":
        text = await _ocr_llm_vision(
            image_bytes,
            mime,
            base_url=cfg.OCR_VISION_API_URL,
            api_key=cfg.OCR_VISION_API_KEY,
            model=cfg.OCR_VISION_MODEL,
            prompt=cfg.OCR_VISION_PROMPT,
        )
        return {
            "provider": "llm_vision",
            "model": cfg.OCR_VISION_MODEL,
            "engine": "openai_compatible",
            "text": text,
        }

    text = await _ocr_python(image_bytes, cfg.OCR_LANGUAGE)
    return {
        "provider": "python",
        "engine": cfg.OCR_PYTHON_ENGINE,
        "language": cfg.OCR_LANGUAGE,
        "text": text,
    }
