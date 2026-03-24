"""
Telegram Tools – ermöglicht das Senden von Nachrichten aus anderen Agenten.
"""

from __future__ import annotations

import logging

import httpx
from langchain_core.tools import tool

from .formatter import format_for_telegram

logger = logging.getLogger("kumio.modules.telegram.tools")


@tool
async def send_telegram_message(message: str, chat_id: str = "") -> str:
    """
    Sendet eine Telegram-Nachricht an einen Benutzer oder eine Gruppe.
    Nutze dieses Tool wenn der User eine Benachrichtigung via Telegram anfordert
    oder wenn ein Ergebnis proaktiv per Telegram zugestellt werden soll.

    Args:
        message: Der zu sendende Text (Markdown erlaubt).
        chat_id: Telegram Chat-ID (optional). Wenn nicht angegeben, wird die
                 Standard-Chat-ID aus den Telegram-Verbindungseinstellungen verwendet.
    """
    from core.connections import ConnectionManager
    from core.vault import get_vault

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        return "Fehler: Keine Telegram-Verbindung konfiguriert. Bitte zuerst in den Einstellungen einrichten."

    vault = get_vault()
    bot_token = ""
    if "TELEGRAM_BOT_TOKEN" in conn.vault_keys:
        bot_token = await vault.get_secret(conn.vault_keys["TELEGRAM_BOT_TOKEN"])

    if not bot_token:
        return "Fehler: Kein Telegram Bot Token konfiguriert."

    # Chat-ID: Parameter > Connection-Config
    target_chat_id = chat_id.strip() or conn.config.get("default_chat_id", "")
    if not target_chat_id:
        return (
            "Fehler: Keine Chat-ID angegeben und keine Standard-Chat-ID in den "
            "Telegram-Verbindungseinstellungen hinterlegt (Feld: 'default_chat_id')."
        )

    # Markdown → Telegram HTML konvertieren
    html_message = format_for_telegram(message)

    # Nachricht senden — mit HTML, Fallback auf plain text
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": target_chat_id, "text": html_message, "parse_mode": "HTML"},
        )

        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("Telegram-Nachricht gesendet an Chat %s", target_chat_id)
            return f"✅ Telegram-Nachricht erfolgreich gesendet an Chat {target_chat_id}."

        # HTML-Fehler → plain text Fallback
        if resp.status_code == 400:
            resp2 = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": target_chat_id, "text": message},
            )
            if resp2.status_code == 200 and resp2.json().get("ok"):
                logger.info("Telegram-Nachricht (plain) gesendet an Chat %s", target_chat_id)
                return f"✅ Telegram-Nachricht gesendet (ohne HTML-Formatierung) an Chat {target_chat_id}."

        detail = resp.json().get("description", resp.text[:150])
        logger.error("Telegram sendMessage Fehler: %s", detail)
        return f"Fehler beim Senden der Telegram-Nachricht: {detail}"
