"""
Teams Tools — enables sending messages from other agents.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from agents.base_agent import _t
from .formatter import format_for_teams

logger = logging.getLogger("ninko.modules.teams.tools")

_LAST_CONV_KEY = "ninko:teams:last_conversation"


@tool
async def send_teams_message(message: str) -> str:
    """
    Send a proactive Teams message to the last active Teams conversation.
    Use this tool when the user requests a notification via Microsoft Teams
    or when a result should be proactively delivered via Teams.

    Args:
        message: The text to send (Markdown allowed).
    """
    from core.redis_client import get_redis
    from .bot import get_teams_access_token

    import httpx

    # Load last known conversation from Redis
    redis = get_redis()
    raw = await redis.connection.get(_LAST_CONV_KEY)
    if not raw:
        return _t(
            "Fehler: Keine bekannte Teams-Konversation. "
            "Schreibe dem Bot zuerst in Teams, damit eine Zielkonversation gespeichert wird.",
            "Error: No known Teams conversation. "
            "Write to the bot in Teams first so that a target conversation is saved.",
        )

    try:
        conv = json.loads(raw)
        service_url = conv["service_url"]
        conversation_id = conv["conversation_id"]
        reply_to_id = conv.get("activity_id")
    except (KeyError, json.JSONDecodeError):
        return _t(
            "Fehler: Gespeicherte Teams-Konversation ist ungültig.",
            "Error: Stored Teams conversation is invalid.",
        )

    token = await get_teams_access_token()
    if not token:
        return _t(
            "Fehler: Kein Teams Access Token. Bitte App ID und Password in den Einstellungen prüfen.",
            "Error: No Teams Access Token. Please check App ID and Password in settings.",
        )

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
            logger.info("Teams message sent proactively to conversation %s", conversation_id)
            return _t(
                "✅ Teams-Nachricht erfolgreich gesendet.",
                "✅ Teams message sent successfully.",
            )
        else:
            detail = resp.text[:200]
            logger.error("Teams sendMessage error: %s %s", resp.status_code, detail)
            return _t(
                f"Fehler beim Senden der Teams-Nachricht: HTTP {resp.status_code} – {detail}",
                f"Error sending Teams message: HTTP {resp.status_code} – {detail}",
            )
