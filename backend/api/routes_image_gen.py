"""
Image Generation – FastAPI Routes.
Serving generierter Bilder + Provider-Konfiguration.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.auth import ROLE_ADMIN, resolve_request_auth_async
from core.image_provider import (
    generate_image,
    get_image_provider_config,
    save_image_provider_config,
    IMAGES_DIR,
)

logger = logging.getLogger("ninko.api.routes_image_gen")

router = APIRouter(tags=["Image Generation"])


async def _require_authenticated(request: Request) -> None:
    auth_ctx = await resolve_request_auth_async(request)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Authentication required.")


async def _assert_admin(request: Request) -> None:
    auth_ctx = await resolve_request_auth_async(request)
    if not auth_ctx or str(auth_ctx.get("role")) != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required.")


# ── Image Serving ────────────────────────────────────────────────────────────

@router.get("/api/images/{filename}")
async def serve_image(filename: str) -> FileResponse:
    """Liefert ein generiertes Bild aus."""
    # Sicherheitscheck: kein Path Traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")

    filepath = IMAGES_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")

    # MIME-Type bestimmen
    ext = filepath.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_types.get(ext, "image/png")

    return FileResponse(
        path=str(filepath),
        media_type=media_type,
        filename=filename,
    )


# ── Provider Settings ───────────────────────────────────────────────────────

class ImageProviderConfig(BaseModel):
    backend: str = ""
    api_key: str = ""
    model: str = ""


class ImageGenerateRequest(BaseModel):
    prompt: str
    size: str = "1024x1024"


@router.get("/api/settings/image-provider")
async def get_image_provider(request: Request) -> dict:
    """Holt die aktuelle Image-Provider-Konfiguration."""
    await _assert_admin(request)
    config = await get_image_provider_config()
    # API-Key maskieren
    if config.get("api_key"):
        key = config["api_key"]
        config["api_key_masked"] = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"
        config["api_key"] = ""
    return config


@router.put("/api/settings/image-provider")
async def update_image_provider(
    request: Request, data: ImageProviderConfig
) -> dict[str, str]:
    """Aktualisiert die Image-Provider-Konfiguration."""
    await _assert_admin(request)
    current = await get_image_provider_config()

    # Merge: leere Felder überschreiben nicht
    config = {
        "backend": data.backend or current.get("backend", ""),
        "api_key": data.api_key if data.api_key else current.get("api_key", ""),
        "model": data.model or current.get("model", ""),
    }

    await save_image_provider_config(config)
    logger.info("Image-Provider konfiguriert: %s (Modell: %s)", config["backend"], config["model"])
    return {"status": "ok", "backend": config["backend"], "model": config["model"]}


@router.post("/api/images/generate")
async def generate_image_asset(request: Request, body: ImageGenerateRequest) -> dict:
    """
    Generiert ein Bild direkt über die konfigurierte Image-Provider-Pipeline.
    """
    await _require_authenticated(request)
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt darf nicht leer sein.")
    try:
        result = await generate_image(prompt=prompt, size=body.size or "1024x1024")
        return {
            "status": "ok",
            "image_id": result.get("image_id", ""),
            "filename": result.get("filename", ""),
            "url": result.get("url", ""),
            "backend": result.get("backend", ""),
            "model": result.get("model", ""),
            "size_bytes": result.get("size_bytes", 0),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
