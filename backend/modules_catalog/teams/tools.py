"""
Teams Tools – ermöglicht das Senden von Nachrichten aus anderen Agenten.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from .formatter import format_for_teams

logger = logging.getLogger("ninko.modules.teams.tools")

_LAST_CONV_KEY = "ninko:teams:last_conversation"


@tool
async def send_teams_message(message: str) -> str:
    """
    Sendet eine proaktive Teams-Nachricht an die zuletzt aktive Teams-Konversation.
    Nutze dieses Tool wenn der User eine Benachrichtigung via Microsoft Teams anfordert
    oder wenn ein Ergebnis proaktiv per Teams zugestellt werden soll.

    Args:
        message: Der zu sendende Text (Markdown erlaubt).
    """
    from core.redis_client import get_redis
    from .bot import get_teams_access_token

    import httpx

    # Letzte bekannte Konversation aus Redis laden
    redis = get_redis()
    raw = await redis.connection.get(_LAST_CONV_KEY)
    if not raw:
        return (
            "Fehler: Keine bekannte Teams-Konversation. "
            "Schreibe dem Bot zuerst in Teams, damit eine Zielkonversation gespeichert wird."
        )

    try:
        conv = json.loads(raw)
        service_url = conv["service_url"]
        conversation_id = conv["conversation_id"]
        reply_to_id = conv.get("activity_id")
    except (KeyError, json.JSONDecodeError):
        return "Fehler: Gespeicherte Teams-Konversation ist ungültig."

    token = await get_teams_access_token()
    if not token:
        return "Fehler: Kein Teams Access Token. Bitte App ID und Password in den Einstellungen prüfen."

    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "type": "message",
        "textFormat": "markdown",
        "text": format_for_teams(message),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201, 202):
            logger.info("Teams-Nachricht proaktiv gesendet an Konversation %s", conversation_id)
            return "✅ Teams-Nachricht erfolgreich gesendet."
        else:
            detail = resp.text[:200]
            logger.error("Teams sendMessage Fehler: %s %s", resp.status_code, detail)
            return f"Fehler beim Senden der Teams-Nachricht: HTTP {resp.status_code} – {detail}"
