from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .bot import get_telegram_bot
from schemas.connection import ConnectionUpdate

router = APIRouter()


@router.get("/status")
async def get_bot_status() -> dict[str, Any]:
    """Prüft den Status des Telegram Long-Polling-Bots."""
    bot = get_telegram_bot()
    if not bot:
        return {"running": False, "error": "Bot-Instanz nicht initialisiert."}

    result: dict[str, Any] = {"running": bot.running}

    try:
        token = await bot.get_token()
        if token:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                if resp.status_code == 200:
                    me = resp.json().get("result", {})
                    result["username"] = me.get("username")
                    result["first_name"] = me.get("first_name")
    except Exception:
        pass

    # Default-Chat-ID und Allowlist aus Connection-Config für das Dashboard
    try:
        from core.connections import ConnectionManager
        conn = await ConnectionManager.get_default_connection("telegram")
        if conn:
            result["default_chat_id"] = conn.config.get("default_chat_id", "")
            raw = conn.config.get("allowed_chat_ids", "")
            result["allowed_ids"] = [s.strip() for s in str(raw).split(",") if s.strip()] if raw else []
    except Exception:
        result["allowed_ids"] = []

    return result


@router.post("/start")
async def start_bot(request: Request) -> dict[str, Any]:
    """Startet das Polling manuell."""
    bot = get_telegram_bot()
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram Bot nicht bereit")

    if bot.running:
        return {"status": "already_running"}

    await bot.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_bot() -> dict[str, Any]:
    """Stoppt das Polling manuell."""
    bot = get_telegram_bot()
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram Bot nicht bereit")

    await bot.stop()
    return {"status": "stopped"}


class SendMessageRequest(BaseModel):
    message: str
    chat_id: str = ""


class AllowedIdsRequest(BaseModel):
    ids: list[str]


@router.get("/allowed-ids")
async def get_allowed_ids() -> dict[str, Any]:
    """Gibt die aktuelle Allowlist der erlaubten Chat-IDs zurück."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        return {"allowed_ids": [], "connection_id": None}

    raw = conn.config.get("allowed_chat_ids", "")
    ids = [s.strip() for s in str(raw).split(",") if s.strip()] if raw else []
    return {"allowed_ids": ids, "connection_id": conn.id}


class DefaultChatIdRequest(BaseModel):
    default_chat_id: str


@router.post("/default-chat-id")
async def set_default_chat_id(body: DefaultChatIdRequest) -> dict[str, Any]:
    """Setzt die Standard-Chat-ID für ausgehende Telegram-Nachrichten."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="Keine Telegram-Verbindung konfiguriert. Bitte zuerst Bot-Token einrichten.",
        )

    updated_config = dict(conn.config)
    updated_config["default_chat_id"] = body.default_chat_id.strip()

    await ConnectionManager.update_connection(
        "telegram",
        conn.id,
        ConnectionUpdate(config=updated_config),
    )

    return {"ok": True, "default_chat_id": updated_config["default_chat_id"]}


@router.post("/allowed-ids")
async def set_allowed_ids(body: AllowedIdsRequest) -> dict[str, Any]:
    """Aktualisiert die Allowlist der erlaubten Chat-IDs."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="Keine Telegram-Verbindung konfiguriert. Bitte zuerst Bot-Token einrichten.",
        )

    # IDs bereinigen, deduplizieren, Reihenfolge beibehalten
    clean_ids = list(dict.fromkeys(s.strip() for s in body.ids if s.strip()))

    # Config aktualisieren (bestehende Felder beibehalten)
    updated_config = dict(conn.config)
    updated_config["allowed_chat_ids"] = ",".join(clean_ids)

    await ConnectionManager.update_connection(
        "telegram",
        conn.id,
        ConnectionUpdate(config=updated_config),
    )

    return {"ok": True, "allowed_ids": clean_ids}


class VoiceReplyConfig(BaseModel):
    voice_reply: bool = False
    voice_reply_text_too: bool = False
    voice_lang: str = ""
    voice_name: str = ""


@router.get("/voice-reply")
async def get_voice_reply_config() -> dict:
    """Voice-Reply-Konfiguration aus der Telegram-Connection abrufen."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        return {"voice_reply": False, "voice_reply_text_too": False, "voice_lang": "", "voice_name": ""}

    cfg = conn.config
    return {
        "voice_reply": str(cfg.get("voice_reply", "false")).lower() in ("true", "1", "yes"),
        "voice_reply_text_too": str(cfg.get("voice_reply_text_too", "false")).lower() in ("true", "1", "yes"),
        "voice_lang": cfg.get("voice_lang", ""),
        "voice_name": cfg.get("voice_name", ""),
    }


@router.post("/voice-reply")
async def set_voice_reply_config(body: VoiceReplyConfig) -> dict:
    """Voice-Reply-Konfiguration in der Telegram-Connection speichern."""
    from core.connections import ConnectionManager

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="Keine Telegram-Verbindung konfiguriert. Bitte zuerst Bot-Token einrichten.",
        )

    updated_config = dict(conn.config)
    updated_config["voice_reply"] = str(body.voice_reply).lower()
    updated_config["voice_reply_text_too"] = str(body.voice_reply_text_too).lower()
    updated_config["voice_lang"] = body.voice_lang.strip()
    updated_config["voice_name"] = body.voice_name.strip()

    await ConnectionManager.update_connection(
        "telegram", conn.id, ConnectionUpdate(config=updated_config),
    )
    return {"ok": True, **body.model_dump()}


@router.post("/send")
async def send_message(body: SendMessageRequest) -> dict[str, Any]:
    """Sendet eine Nachricht direkt über den Bot (für das Dashboard)."""
    bot = get_telegram_bot()
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram Bot nicht bereit")

    token = await bot.get_token()
    if not token:
        raise HTTPException(status_code=400, detail="Kein Bot-Token konfiguriert")

    # Chat-ID: Parameter > Connection-Config
    chat_id = body.chat_id.strip()
    if not chat_id:
        try:
            from core.connections import ConnectionManager
            conn = await ConnectionManager.get_default_connection("telegram")
            if conn:
                chat_id = conn.config.get("default_chat_id", "")
        except Exception:
            pass

    if not chat_id:
        raise HTTPException(
            status_code=400,
            detail="Keine Chat-ID angegeben und keine Standard-Chat-ID konfiguriert.",
        )

    ok = await bot._send(token, int(chat_id), body.message, parse_mode="Markdown")
    if ok:
        return {"ok": True}
    raise HTTPException(status_code=500, detail="Nachricht konnte nicht gesendet werden.")
