"""
Teams Bot Helper – OAuth Token Handling & Messaging.

Voice-Reply: Wenn eine eingehende Audio-Anlage erkannt wird und voice_reply in der
Connection-Konfiguration aktiviert ist, antwortet der Bot mit einem MP3-Anhang.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
import httpx

from core.vault import get_vault
from fastapi import FastAPI

from .formatter import format_for_teams

logger = logging.getLogger("ninko.modules.teams.bot")

# Redis-Key für die letzte bekannte Teams-Konversation (für proaktive Nachrichten)
_LAST_CONV_KEY = "ninko:teams:last_conversation"


async def get_teams_credentials(connection_id: str = "") -> tuple[str | None, str | None]:
    """Holt App ID und Password aus dem Vault."""
    from core.connections import ConnectionManager

    if connection_id:
        conn = await ConnectionManager.get_connection("teams", connection_id)
    else:
        conn = await ConnectionManager.get_default_connection("teams")

    if not conn:
        return None, None

    vault = get_vault()
    app_id = None
    app_password = None

    if "MICROSOFT_APP_ID" in conn.vault_keys:
        app_id = await vault.get_secret(conn.vault_keys["MICROSOFT_APP_ID"])
    if "MICROSOFT_APP_PASSWORD" in conn.vault_keys:
        app_password = await vault.get_secret(conn.vault_keys["MICROSOFT_APP_PASSWORD"])

    return app_id, app_password


async def get_teams_access_token(connection_id: str = "") -> str | None:
    """Holt einen OAuth2 Bearer Token vom Microsoft Bot Framework."""
    app_id, app_password = await get_teams_credentials(connection_id)

    if not app_id or not app_password:
        return None

    token_url = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": app_id,
        "client_secret": app_password,
        "scope": "https://api.botframework.com/.default",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            logger.error("Fehler bei Token-Beschaffung: %s %s", resp.status_code, resp.text)
            return None


async def send_teams_message(
    service_url: str,
    conversation_id: str,
    reply_to_id: str | None,
    text: str,
    apply_format: bool = True,
) -> bool:
    """Sendet eine Antwortnachricht via Microsoft Bot Framework."""
    token = await get_teams_access_token()
    if not token:
        logger.error("Kann keine Teams-Nachricht senden: Kein Access Token.")
        return False

    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    if reply_to_id:
        url += f"/{reply_to_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Markdown formatieren (Tabellen → ASCII)
    formatted_text = format_for_teams(text) if apply_format else text

    payload: dict[str, Any] = {
        "type": "message",
        "textFormat": "markdown",
        "text": formatted_text,
    }
    if reply_to_id:
        payload["replyToId"] = reply_to_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201, 202):
            return True
        else:
            logger.error(
                "Fehler beim Senden der Teams-Nachricht: HTTP %s %s",
                resp.status_code,
                resp.text,
            )
            return False


async def send_teams_voice_reply(
    service_url: str,
    conversation_id: str,
    reply_to_id: str | None,
    mp3_bytes: bytes,
    caption: str = "",
) -> bool:
    """
    Sendet eine MP3-Audiodatei als Attachment in einer Teams-Nachricht.
    Nutzt inline Base64-Daten (kein öffentlicher Upload-Server nötig).

    Args:
        service_url: Teams Bot Framework Service URL.
        conversation_id: Teams Konversations-ID.
        reply_to_id: Activity ID zum Antworten (optional).
        mp3_bytes: MP3-Audio als bytes.
        caption: Optionaler Begleittext (z.B. "Sprachantwort").
    """
    token = await get_teams_access_token()
    if not token:
        logger.error("Kann keine Teams-Voice-Antwort senden: Kein Access Token.")
        return False

    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    if reply_to_id:
        url += f"/{reply_to_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    b64_audio = base64.b64encode(mp3_bytes).decode("ascii")
    payload: dict[str, Any] = {
        "type": "message",
        "text": caption,
        "attachments": [
            {
                "contentType": "audio/mp3",
                "contentUrl": f"data:audio/mpeg;base64,{b64_audio}",
                "name": "antwort.mp3",
            }
        ],
    }
    if reply_to_id:
        payload["replyToId"] = reply_to_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201, 202):
            logger.info(
                "Teams Voice-Reply gesendet: %d KB MP3", len(mp3_bytes) // 1024
            )
            return True
        else:
            logger.error(
                "Fehler beim Senden der Teams-Voice-Antwort: HTTP %s %s",
                resp.status_code,
                resp.text[:200],
            )
            return False


async def _transcribe_teams_attachment(
    attachment: dict[str, Any],
) -> tuple[str | None, float, str]:
    """
    Versucht, eine Teams-Audio-Anlage herunterzuladen und zu transkribieren.

    Returns:
        (text, avg_confidence, detected_language)
    """
    import os
    content_url = attachment.get("contentUrl", "")
    name = attachment.get("name", "audio.ogg")
    if not content_url:
        return None, -2.0, os.getenv("WHISPER_LANGUAGE", "de")
    try:
        from api.routes_transcription import transcribe_bytes_extended

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(content_url)
            r.raise_for_status()
            audio_bytes = r.content

        text, confidence, detected_lang = await transcribe_bytes_extended(audio_bytes, name)
        return (text or None), confidence, detected_lang
    except Exception as exc:
        logger.warning("Transkription des Teams-Audio-Anhangs fehlgeschlagen: %s", exc)
        return None, -2.0, os.getenv("WHISPER_LANGUAGE", "de")


async def handle_teams_turn(app: FastAPI, activity: dict[str, Any]) -> None:
    """Verarbeitet eine eingehende Message Activity von Teams, ruft den Agent auf und sendet die Antwort."""
    import json
    import os
    import re
    from core.redis_client import get_redis

    text = activity.get("text", "")
    is_voice = False
    detected_lang: str = os.getenv("WHISPER_LANGUAGE", "de")
    low_confidence = False

    # Audio-Anhang transkribieren falls kein Text vorhanden
    if not text:
        for att in activity.get("attachments", []):
            ct = att.get("contentType", "")
            if ct.startswith("audio/") or ct.startswith("application/octet-stream"):
                transcribed, confidence, detected_lang = await _transcribe_teams_attachment(att)
                if transcribed:
                    text = transcribed
                    is_voice = True
                    # Konfidenz-Check
                    from core.config import get_settings as _get_cfg
                    _cfg = _get_cfg()
                    if confidence < _cfg.STT_CONFIDENCE_THRESHOLD:
                        low_confidence = True
                        logger.info(
                            "STT Konfidenz niedrig (%.2f): '%s'", confidence, text[:60]
                        )
                    break

    if not text:
        return

    # Bot-Mentions strippen (Teams sendet z.B. "<at>Ninko</at> Hallo")
    clean_text = re.sub(r"<[^>]+>", "", text).strip()

    service_url = activity.get("serviceUrl", "")
    conv_id = activity.get("conversation", {}).get("id", "")
    activity_id = activity.get("id", "")

    # Absender-Identifikation (für Allowlist und Logging)
    sender = activity.get("from", {})
    sender_id = sender.get("id", "")
    sender_name = sender.get("name", "Unbekannt")

    if not service_url or not conv_id:
        logger.error("serviceUrl oder conversation.id fehlt im Teams-Payload.")
        return

    # ── Allowlist-Check ───────────────────────────────────────────────────────
    from core.connections import ConnectionManager
    conn = await ConnectionManager.get_default_connection("teams")
    if conn:
        allowed_raw = conn.config.get("allowed_user_ids", "")
        if allowed_raw:
            allowed_ids = {s.strip() for s in str(allowed_raw).split(",") if s.strip()}
            if sender_id not in allowed_ids:
                logger.warning(
                    "Teams: Zugriff verweigert für Nutzer '%s' (ID: %s)",
                    sender_name,
                    sender_id,
                )
                return

    # Voice-Reply-Konfiguration aus Connection lesen
    voice_reply = False
    voice_reply_text_too = True  # Teams-Empfehlung: Text immer mitschicken
    voice_lang: str | None = None
    voice_name: str | None = None
    if conn:
        voice_reply = str(conn.config.get("voice_reply", "false")).lower() in ("true", "1", "yes")
        voice_reply_text_too = str(conn.config.get("voice_reply_text_too", "true")).lower() in ("true", "1", "yes")
        voice_lang = conn.config.get("voice_lang") or None
        voice_name = conn.config.get("voice_name") or None

    logger.info("Teams Nachricht von '%s' (%s): %s…", sender_name, sender_id, clean_text[:60])

    session_id = f"teams_{conv_id}"

    # ── Letzte Konversation in Redis speichern (für proaktive Nachrichten) ────
    redis = get_redis()
    await redis.connection.set(
        _LAST_CONV_KEY,
        json.dumps({"service_url": service_url, "conversation_id": conv_id, "activity_id": activity_id}),
        ex=86400,  # 24h TTL
    )

    # ── Reset-Befehle ─────────────────────────────────────────────────────────
    if clean_text.lower() in ("/start", "/clear", "/reset"):
        await redis.clear_chat_history(session_id)
        await send_teams_message(
            service_url, conv_id, activity_id,
            "♻️ Chat-Verlauf geleert. Wie kann ich helfen?",
            apply_format=False,
        )
        return

    # ── Bei niedriger Konfidenz: Rückfrage statt Verarbeitung ────────────────
    if low_confidence:
        await send_teams_message(
            service_url, conv_id, activity_id,
            f"🎙️ Ich habe verstanden:\n> *{clean_text}*\n\nIst das korrekt? (Antworte mit Ja oder schicke den Text nochmal.)",
            apply_format=False,
        )
        return

    # ── Sofortige Bestätigung senden ──────────────────────────────────────────
    await send_teams_message(
        service_url, conv_id, activity_id,
        "🔄 Ich arbeite an deiner Anfrage…",
        apply_format=False,
    )

    try:
        orchestrator = app.state.orchestrator
        history = await redis.get_chat_history(session_id)

        # Ggf. erkannte Sprache als Kontext mitgeben
        lang_hint = ""
        if os.getenv("WHISPER_LANGUAGE", "de") == "auto" and detected_lang and detected_lang != "de":
            lang_hint = f"[Erkannte Sprache: {detected_lang}] "
        routed_text = f"{lang_hint}{clean_text}"

        response_text, module_used, _ = await orchestrator.route(
            message=routed_text,
            chat_history=history,
            session_id=session_id,
        )

        # History speichern
        await redis.store_chat_message(session_id=session_id, role="user", content=clean_text)
        await redis.store_chat_message(session_id=session_id, role="assistant", content=response_text)

        # ── Voice-Reply ────────────────────────────────────────────────────────
        if is_voice and voice_reply:
            await _send_teams_voice_reply(service_url, conv_id, activity_id, response_text,
                                          lang=voice_lang, voice=voice_name)
            if not voice_reply_text_too:
                return

        # ── Text-Antwort ───────────────────────────────────────────────────────
        final_text = response_text
        if module_used and module_used != "Ninko":
            final_text += f"\n\n*(via {module_used})*"

        await send_teams_message(service_url, conv_id, activity_id, final_text)

    except Exception as e:
        logger.exception("Interner Fehler in handle_teams_turn: %s", e)
        err_type = type(e).__name__
        await send_teams_message(
            service_url, conv_id, activity_id,
            f"❌ Interner Fehler ({err_type}):\n{str(e)[:300]}\n\nBitte versuche es erneut.",
            apply_format=False,
        )


async def _send_teams_voice_reply(
    service_url: str,
    conv_id: str,
    activity_id: str,
    text: str,
    lang: str | None = None,
    voice: str | None = None,
) -> None:
    """
    Synthetisiert Text mit Piper TTS und sendet ihn als Teams MP3-Attachment.
    Fehler werden geloggt aber nicht propagiert (Best-Effort).
    """
    try:
        from core.tts import synthesize_reply
        from core.tts.audio_utils import wav_to_mp3

        wav_bytes = await synthesize_reply(text, lang=lang, voice=voice)
        mp3_bytes = await wav_to_mp3(wav_bytes)
        await send_teams_voice_reply(
            service_url, conv_id, activity_id,
            mp3_bytes,
            caption="🔊 Sprachantwort",
        )
    except Exception as exc:
        logger.error("Teams Voice-Reply Fehler: %s", exc)
