"""
Message Hub — Telegram Worker (Long-Polling).

Schlanker Long-Polling Worker, der den bestehenden Telegram-Bot
ergänzt (oder bei nicht-installiertem Telegram-Modul als Standalone läuft).

Routing: channel_id = Telegram Chat-ID (als String)

Hinweis: Falls das Telegram-Katalog-Modul installiert ist, übernimmt
dessen TelegramBot die komplette Verarbeitung. Dieser Worker prüft das
und delegiert oder startet eigenständig.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from ..worker_base import ChannelWorker

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("ninko.modules.message_hub.telegram_worker")

_LONG_POLL_TIMEOUT = 30   # Sekunden für Long-Poll
_MAX_BODY_LEN = 4000


class TelegramWorker(ChannelWorker):
    """
    Telegram Long-Polling Worker für den Message Hub.

    Läuft nur wenn:
    1. Das Telegram-Modul NICHT installiert ist (kein Konflikt), ODER
    2. Die aktive Route-Tabelle Telegram-Einträge hat, die nicht vom
       Telegram-Bot abgedeckt werden (separater connection_id).

    channel_id für Routing = str(chat_id)
    """

    channel_type = "telegram"

    def __init__(self, app: "FastAPI", bot_token: str) -> None:
        super().__init__(app)
        self._bot_token = bot_token
        self._offset = 0

    async def run_once(self) -> None:
        """Long-Polling Loop."""
        if not self._bot_token:
            logger.info("Telegram-Worker: Kein Bot-Token — warte 60s")
            await asyncio.sleep(60)
            return

        base_url = f"https://api.telegram.org/bot{self._bot_token}"
        async with httpx.AsyncClient(timeout=_LONG_POLL_TIMEOUT + 5.0) as client:
            while self.running:
                updates = await self._get_updates(client, base_url)
                for update in updates:
                    if not self.running:
                        break
                    await self._handle_update(update, client, base_url)

    async def _get_updates(self, client: httpx.AsyncClient, base_url: str) -> list[dict]:
        """Holt neue Updates via Long-Polling."""
        try:
            resp = await client.get(
                f"{base_url}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": _LONG_POLL_TIMEOUT,
                    "allowed_updates": ["message"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return []
            updates = data.get("result", [])
            if updates:
                self._offset = updates[-1]["update_id"] + 1
            return updates
        except httpx.TimeoutException:
            return []
        except Exception as exc:
            logger.warning("Telegram-Worker: Update-Fehler: %s", exc)
            raise

    async def _handle_update(
        self, update: dict, client: httpx.AsyncClient, base_url: str
    ) -> None:
        """Verarbeitet ein einzelnes Telegram-Update."""
        message = update.get("message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()
        if not text or not chat_id:
            return

        from_user = message.get("from", {})
        username = from_user.get("username") or from_user.get("first_name", "unknown")
        context_prefix = f"[Telegram Chat-ID: {chat_id} | User: @{username}]"

        if len(text) > _MAX_BODY_LEN:
            text = text[:_MAX_BODY_LEN] + "\n[…Nachricht gekürzt]"

        async def reply(response_text: str) -> None:
            # Auf 4000 Zeichen kürzen
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "\n…"
            try:
                await client.post(
                    f"{base_url}/sendMessage",
                    json={
                        "chat_id": int(chat_id),
                        "text": response_text,
                        "parse_mode": "Markdown",
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Telegram-Worker: Antwort konnte nicht gesendet werden: %s", exc
                )

        await self.dispatch(
            channel_id=chat_id,
            text=text,
            context_prefix=context_prefix,
            reply_fn=reply,
        )
