"""
Webhooks und API-Endpoints für Microsoft Teams Bot Framework.
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from .bot import handle_teams_turn, _LAST_CONV_KEY
from schemas.connection import ConnectionUpdate

router = APIRouter()


@router.post("/messages")
async def messages_webhook(request: Request) -> dict[str, Any]:
    """
    Webhook Endpoint für Microsoft Teams.
    Gibt sofort 200 zurück – Verarbeitung erfolgt als Background-Task.
    """
    try:
        activity = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if activity.get("type") == "message":
        app = request.app
        asyncio.create_task(handle_teams_turn(app, activity))

    return {"status": "ok"}


@router.get("/status")
async def get_teams_status() -> dict[str, Any]:
    """Gibt Konfigurations- und Verbindungsstatus zurück."""
    from core.connections import ConnectionManager
    from core.redis_client import get_redis

    result: dict[str, Any] = {"configured": False}

    try:
        conn = await ConnectionManager.get_default_connection("teams")
        if conn:
            result["configured"] = bool(conn.vault_keys.get("MICROSOFT_APP_ID"))
            raw = conn.config.get("allowed_user_ids", "")
            result["allowed_ids"] = [s.strip() for s in str(raw).split(",") if s.strip()] if raw else []
        else:
            result["allowed_ids"] = []
    except Exception:
        result["allowed_ids"] = []

    # Letzte bekannte Konversation
    try:
        redis = get_redis()
        raw_conv = await redis.connection.get(_LAST_CONV_KEY)
        if raw_conv:
            conv = json.loads(raw_conv)
            result["last_conversation_id"] = conv.get("conversation_id", "")
        else:
            result["last_conversation_id"] = ""
    except Exception:
        result["last_conversation_id"] = ""

    return result


class AllowedIdsRequest(BaseModel):
    ids: list[str]


@router.get("/allowed-ids")
async def get_allowed_ids() -> dict[str, Any]:
    """Gibt die aktuelle Allowlist der erlaubten Teams-Nutzer-IDs zurück."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("teams")
    if not conn:
        return {"allowed_ids": [], "connection_id": None}

    raw = conn.config.get("allowed_user_ids", "")
    ids = [s.strip() for s in str(raw).split(",") if s.strip()] if raw else []
    return {"allowed_ids": ids, "connection_id": conn.id}


@router.post("/allowed-ids")
async def set_allowed_ids(body: AllowedIdsRequest) -> dict[str, Any]:
    """Aktualisiert die Allowlist der erlaubten Teams-Nutzer-IDs."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("teams")
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="Keine Teams-Verbindung konfiguriert. Bitte zuerst App ID und Password einrichten.",
        )

    # IDs bereinigen und deduplizieren
    clean_ids = list(dict.fromkeys(s.strip() for s in body.ids if s.strip()))

    updated_config = dict(conn.config)
    updated_config["allowed_user_ids"] = ",".join(clean_ids)

    await ConnectionManager.update_connection(
        "teams",
        conn.id,
        ConnectionUpdate(config=updated_config),
    )

    return {"ok": True, "allowed_ids": clean_ids}


class VoiceReplyConfig(BaseModel):
    voice_reply: bool = False
    voice_reply_text_too: bool = True
    voice_lang: str = ""
    voice_name: str = ""


@router.get("/voice-reply")
async def get_voice_reply_config() -> dict:
    """Voice-Reply-Konfiguration aus der Teams-Connection abrufen."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("teams")
    if not conn:
        return {"voice_reply": False, "voice_reply_text_too": True, "voice_lang": "", "voice_name": ""}

    cfg = conn.config
    return {
        "voice_reply": str(cfg.get("voice_reply", "false")).lower() in ("true", "1", "yes"),
        "voice_reply_text_too": str(cfg.get("voice_reply_text_too", "true")).lower() in ("true", "1", "yes"),
        "voice_lang": cfg.get("voice_lang", ""),
        "voice_name": cfg.get("voice_name", ""),
    }


@router.post("/voice-reply")
async def set_voice_reply_config(body: VoiceReplyConfig) -> dict:
    """Voice-Reply-Konfiguration in der Teams-Connection speichern."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("teams")
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="Keine Teams-Verbindung konfiguriert. Bitte zuerst App ID und Password einrichten.",
        )

    updated_config = dict(conn.config)
    updated_config["voice_reply"] = str(body.voice_reply).lower()
    updated_config["voice_reply_text_too"] = str(body.voice_reply_text_too).lower()
    updated_config["voice_lang"] = body.voice_lang.strip()
    updated_config["voice_name"] = body.voice_name.strip()

    await ConnectionManager.update_connection(
        "teams", conn.id, ConnectionUpdate(config=updated_config),
    )
    return {"ok": True, **body.model_dump()}
