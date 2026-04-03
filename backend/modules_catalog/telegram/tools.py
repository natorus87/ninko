"""
Telegram Tools — enables sending messages from other agents.
"""

from __future__ import annotations

import logging

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from .formatter import format_for_telegram

logger = logging.getLogger("ninko.modules.telegram.tools")


@tool
async def send_telegram_message(message: str, chat_id: str = "") -> str:
    """
    Sends a Telegram message to a user or group.
    Use this tool when the user requests a notification via Telegram
    or when a result should be proactively delivered via Telegram.

    Args:
        message: The text to send (Markdown allowed).
        chat_id: Telegram chat ID (optional). If not provided, the
                 default chat ID from Telegram connection settings is used.
    """
    from core.connections import ConnectionManager
    from core.vault import get_vault

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        return _t(
            "Fehler: Keine Telegram-Verbindung konfiguriert. Bitte zuerst in den Einstellungen einrichten.",
            "Error: No Telegram connection configured. Please set one up in settings first.",
        )

    vault = get_vault()
    bot_token = ""
    if "TELEGRAM_BOT_TOKEN" in conn.vault_keys:
        bot_token = await vault.get_secret(conn.vault_keys["TELEGRAM_BOT_TOKEN"])

    if not bot_token:
        return _t(
            "Fehler: Kein Telegram Bot Token konfiguriert.",
            "Error: No Telegram Bot Token configured.",
        )

    # Chat-ID: parameter > connection config
    target_chat_id = chat_id.strip() or conn.config.get("default_chat_id", "")
    if not target_chat_id:
        return _t(
            "Fehler: Keine Chat-ID angegeben und keine Standard-Chat-ID in den "
            "Telegram-Verbindungseinstellungen hinterlegt (Feld: 'default_chat_id').",
            "Error: No chat ID provided and no default chat ID configured in "
            "Telegram connection settings (field: 'default_chat_id').",
        )

    # Convert Markdown → Telegram HTML
    html_message = format_for_telegram(message)

    # Send message — with HTML, fallback to plain text
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": target_chat_id, "text": html_message, "parse_mode": "HTML"},
        )

        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("Telegram message sent to chat %s", target_chat_id)
            return _t(
                f"✅ Telegram-Nachricht erfolgreich gesendet an Chat {target_chat_id}.",
                f"✅ Telegram message sent successfully to chat {target_chat_id}.",
            )

        # HTML error → plain text fallback
        if resp.status_code == 400:
            resp2 = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": target_chat_id, "text": message},
            )
            if resp2.status_code == 200 and resp2.json().get("ok"):
                logger.info("Telegram message (plain) sent to chat %s", target_chat_id)
                return _t(
                    f"✅ Telegram-Nachricht gesendet (ohne HTML-Formatierung) an Chat {target_chat_id}.",
                    f"✅ Telegram message sent (without HTML formatting) to chat {target_chat_id}.",
                )

        detail = resp.json().get("description", resp.text[:150])
        logger.error("Telegram sendMessage error: %s", detail)
        return _t(
            f"Fehler beim Senden der Telegram-Nachricht: {detail}",
            f"Error sending Telegram message: {detail}",
        )
