"""
Image Generation Provider Factory.

Unterstützte Provider:
- together_ai: Together AI (Flux, SDXL, etc.)
- openai: OpenAI DALL-E 2/3
- google: Google Imagen 3/4

Konfiguration in Redis: kumio:settings:image_provider
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("kumio.core.image_provider")

REDIS_KEY = "kumio:settings:image_provider"
IMAGES_DIR = Path("data/images")

# ── Default Config ───────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "backend": "",
    "api_key": "",
    "model": "",
}


def _ensure_images_dir() -> Path:
    """Stellt sicher, dass das Images-Verzeichnis existiert."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGES_DIR


# ── Provider Config laden/speichern ──────────────────────────────────────────

async def get_image_provider_config() -> dict[str, Any]:
    """Lädt die Image-Provider-Konfiguration aus Redis."""
    from core.redis_client import get_redis
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY)
    if raw:
        import json
        try:
            return json.loads(raw)
        except Exception:
            pass
    # Fallback: Env-Vars
    return {
        "backend": os.environ.get("IMAGE_GEN_BACKEND", ""),
        "api_key": os.environ.get("IMAGE_GEN_API_KEY", ""),
        "model": os.environ.get("IMAGE_GEN_MODEL", ""),
    }


async def save_image_provider_config(config: dict[str, Any]) -> None:
    """Speichert die Image-Provider-Konfiguration in Redis."""
    import json
    from core.redis_client import get_redis
    redis = get_redis()
    await redis.connection.set(REDIS_KEY, json.dumps(config))
    # Env-Vars setzen für Kompatibilität
    if config.get("backend"):
        os.environ["IMAGE_GEN_BACKEND"] = config["backend"]
    if config.get("model"):
        os.environ["IMAGE_GEN_MODEL"] = config["model"]


# ── Provider-Implementierungen ───────────────────────────────────────────────

async def _generate_together(prompt: str, api_key: str, model: str, size: str) -> tuple[bytes, str]:
    """Together AI – OpenAI-kompatibel."""
    model = model or "black-forest-labs/FLUX.1-schnell-Free"
    # Together AI nutzt die OpenAI-kompatible /v1/images/generations API
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.together.xyz/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "steps": 4,
                "n": 1,
                "response_format": "b64_json",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Together AI Error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64), "png"


async def _generate_openai(prompt: str, api_key: str, model: str, size: str) -> tuple[bytes, str]:
    """OpenAI DALL-E 2/3."""
    model = model or "dall-e-3"
    size = size or "1024x1024"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": size,
                "response_format": "b64_json",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI Error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64), "png"


async def _generate_google(prompt: str, api_key: str, model: str, size: str) -> tuple[bytes, str]:
    """Google Imagen 3/4 via Gemini API."""
    model = model or "imagen-3.0-generate-002"
    async with httpx.AsyncClient(timeout=120) as client:
        # Google Gemini API for image generation
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "1:1",
                },
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Google Imagen Error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        b64 = data["predictions"][0]["bytesBase64Encoded"]
        return base64.b64decode(b64), "png"


# ── Hauptfunktion ────────────────────────────────────────────────────────────

async def generate_image(
    prompt: str,
    size: str = "1024x1024",
    connection_id: str = "",
) -> dict[str, Any]:
    """
    Generiert ein Bild mit dem konfigurierten Image-Provider.

    Args:
        prompt: Bildbeschreibung / Prompt.
        size: Bildgröße (z.B. "1024x1024"). Manche Provider ignorieren das.
        connection_id: (Platzhalter für zukünftige Multi-Connection).

    Returns:
        Dict mit image_id, url, prompt, backend, model.
    """
    config = await get_image_provider_config()
    backend = config.get("backend", "")
    api_key = config.get("api_key", "")
    model = config.get("model", "")

    if not backend:
        raise ValueError(
            "Kein Image-Generation-Provider konfiguriert. "
            "Bitte in den Einstellungen unter 'Bildgenerierung' einen Provider einrichten "
            "(Together AI, OpenAI oder Google)."
        )
    if not api_key:
        raise ValueError(
            f"Kein API-Key für '{backend}' hinterlegt. "
            "Bitte in den Einstellungen den API-Key eingeben."
        )

    # Provider aufrufen
    if backend == "together_ai":
        image_bytes, ext = await _generate_together(prompt, api_key, model, size)
    elif backend == "openai":
        image_bytes, ext = await _generate_openai(prompt, api_key, model, size)
    elif backend == "google":
        image_bytes, ext = await _generate_google(prompt, api_key, model, size)
    else:
        raise ValueError(f"Unbekannter Image-Provider: '{backend}'. Unterstützt: together_ai, openai, google.")

    # Bild speichern
    img_dir = _ensure_images_dir()
    image_id = str(uuid.uuid4())[:12]
    filename = f"{image_id}.{ext}"
    filepath = img_dir / filename
    filepath.write_bytes(image_bytes)

    logger.info("Bild generiert: %s (%d KB, Provider: %s, Modell: %s)", filename, len(image_bytes) // 1024, backend, model)

    return {
        "image_id": image_id,
        "filename": filename,
        "url": f"/api/images/{filename}",
        "prompt": prompt,
        "backend": backend,
        "model": model or "(default)",
        "size_bytes": len(image_bytes),
    }
