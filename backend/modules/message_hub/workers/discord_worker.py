"""
Message Hub — Discord Worker (REST Long-Polling).

Da discord.py/websockets nicht als Core-Dependency vorhanden ist,
wird die Discord REST API alle POLL_INTERVAL Sekunden abgefragt.
Neue Nachrichten (seit letzter bekannter Message-ID) werden verarbeitet.

Routing: channel_id = Discord Channel-ID (als String)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from ..worker_base import ChannelWorker

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("ninko.modules.message_hub.discord_worker")

_DISCORD_API = "https://discord.com/api/v10"
_POLL_INTERVAL = 10  # Sekunden zwischen Polls
_BATCH_SIZE = 10     # Max. Nachrichten pro Poll


class DiscordWorker(ChannelWorker):
    """
    Discord REST-Polling Worker.

    Überwacht alle Discord-Channels, für die es aktive Routing-Einträge gibt.
    Speichert die letzte bekannte Message-ID pro Channel (In-Memory).
    """

    channel_type = "discord"

    def __init__(self, app: "FastAPI") -> None:
        super().__init__(app)
        # channel_id → letzte bekannte message_id
        self._last_message_ids: dict[str, str] = {}

    async def run_once(self) -> None:
        """Polling-Loop: Prüft alle aktiven Discord-Channels auf neue Nachrichten."""
        bot_token = await self._get_bot_token()
        if not bot_token:
            self.configured = False
            logger.info("Discord-Worker: Kein Bot-Token konfiguriert — warte 60s")
            await asyncio.sleep(60)
            return
        self.configured = True

        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            while self.running:
                await self._poll_all_channels(client)
                await asyncio.sleep(_POLL_INTERVAL)

    async def _poll_all_channels(self, client: httpx.AsyncClient) -> None:
        """Holt aktive Discord-Routes und pollt jeden Channel."""
        from ..db import list_routes

        routes = await list_routes("discord")
        active = [r for r in routes if r.enabled]

        for route in active:
            if not self.running:
                break
            try:
                await self._poll_channel(client, route.channel_id)
            except Exception as exc:
                logger.warning(
                    "Discord-Worker: Fehler beim Polln von Channel %s: %s",
                    route.channel_id,
                    exc,
                )

    async def _poll_channel(self, client: httpx.AsyncClient, channel_id: str) -> None:
        """Pollt einen einzelnen Discord-Channel auf neue Nachrichten."""
        params: dict[str, str | int] = {"limit": _BATCH_SIZE}
        last_id = self._last_message_ids.get(channel_id)
        if last_id:
            params["after"] = last_id

        url = f"{_DISCORD_API}/channels/{channel_id}/messages"
        resp = await client.get(url, params=params)

        if resp.status_code == 401:
            logger.error("Discord-Worker: Ungültiger Bot-Token (401)")
            raise ValueError("Ungültiger Discord Bot-Token")
        if resp.status_code == 403:
            logger.warning(
                "Discord-Worker: Kein Zugriff auf Channel %s (403)", channel_id
            )
            return
        if resp.status_code == 404:
            logger.warning(
                "Discord-Worker: Channel %s nicht gefunden (404)", channel_id
            )
            return
        resp.raise_for_status()

        messages = resp.json()
        if not messages:
            return

        # Discord gibt Nachrichten in umgekehrter Reihenfolge zurück (neueste zuerst)
        messages_sorted = sorted(messages, key=lambda m: m["id"])
        newest_id = messages_sorted[-1]["id"]

        # Beim ersten Poll (kein last_id gespeichert): nur Cursor setzen, nicht dispatchen.
        # Verhindert Flut alter Nachrichten nach Worker-Neustart.
        if last_id is None:
            self._last_message_ids[channel_id] = newest_id
            return

        # Neueste ID merken
        self._last_message_ids[channel_id] = newest_id

        for msg in messages_sorted:
            # Bot-eigene Nachrichten ignorieren (infinite loop vermeiden)
            if msg.get("author", {}).get("bot"):
                continue
            await self._handle_message(msg, channel_id, client)

    async def _handle_message(
        self,
        msg: dict,
        channel_id: str,
        client: httpx.AsyncClient,
    ) -> None:
        """Dispatched eine Discord-Nachricht an den Orchestrator."""
        content = msg.get("content", "").strip()
        if not content:
            return

        author = msg.get("author", {})
        username = author.get("username", "unknown")
        user_id = author.get("id", "")
        context_prefix = f"[Discord Channel: {channel_id} | User: {username} ({user_id})]"

        async def reply(response_text: str) -> None:
            """Sendet die Antwort als Discord-Nachricht."""
            # Auf 2000 Zeichen kürzen (Discord-Limit)
            if len(response_text) > 1990:
                response_text = response_text[:1990] + "\n…"
            try:
                await client.post(
                    f"{_DISCORD_API}/channels/{channel_id}/messages",
                    json={"content": response_text},
                )
            except Exception as exc:
                logger.warning("Discord-Worker: Antwort konnte nicht gesendet werden: %s", exc)

        await self.dispatch(
            channel_id=channel_id,
            text=content,
            context_prefix=context_prefix,
            reply_fn=reply,
        )

    async def _get_bot_token(self) -> str:
        """Lädt den Discord Bot-Token aus der Connection."""
        try:
            from core.connections import ConnectionManager
            from core.vault import get_vault

            conn = await ConnectionManager.get_default_connection("discord")
            if not conn:
                return ""
            vault = get_vault()
            token_key = conn.vault_keys.get("DISCORD_BOT_TOKEN")
            if token_key:
                return await vault.get_secret(token_key)
            return conn.config.get("bot_token", "")
        except Exception as exc:
            logger.warning("Discord-Worker: Token konnte nicht geladen werden: %s", exc)
            return ""
