"""
Message Hub — Zentraler Hub-Singleton.

Verwaltet alle Channel-Worker und deren Lifecycle.
Wird beim App-Start gestartet und bei Shutdown gestoppt.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .schemas import WorkerStatus, HubStatus

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("ninko.modules.message_hub.hub")

_hub_instance: "MessageHub | None" = None


def get_message_hub() -> "MessageHub | None":
    return _hub_instance


def init_message_hub(app: "FastAPI") -> "MessageHub":
    """Erstellt und registriert die globale MessageHub-Instanz. Von main.py aufgerufen."""
    global _hub_instance
    _hub_instance = MessageHub(app)
    return _hub_instance


class MessageHub:
    """
    Zentraler Manager für alle Message-Hub-Channel-Worker.

    Startet Email-, Discord- und Telegram-Worker parallel.
    Jeder Worker hat seinen eigenen Exponential-Backoff-Supervisor.
    """

    def __init__(self, app: "FastAPI") -> None:
        self.app = app
        self._workers: list = []

    async def start(self) -> None:
        """Startet alle konfigurierten Channel-Worker."""
        self._workers.clear()

        # ── Email Worker ──────────────────────────────────────────────
        try:
            from .workers.email_worker import EmailWorker

            email_worker = EmailWorker(self.app)
            await email_worker.start()
            self._workers.append(email_worker)
            logger.info("Message Hub: Email-Worker gestartet")
        except Exception as exc:
            logger.warning("Message Hub: Email-Worker konnte nicht gestartet werden: %s", exc)

        # ── Discord Worker ────────────────────────────────────────────
        try:
            from .workers.discord_worker import DiscordWorker

            discord_worker = DiscordWorker(self.app)
            await discord_worker.start()
            self._workers.append(discord_worker)
            logger.info("Message Hub: Discord-Worker gestartet")
        except Exception as exc:
            logger.warning(
                "Message Hub: Discord-Worker konnte nicht gestartet werden: %s", exc
            )

        # ── Telegram Worker ───────────────────────────────────────────
        # Nur starten wenn das Telegram-Katalog-Modul NICHT aktiv ist
        # (vermeidet doppeltes Polling mit demselben Token)
        if not self._telegram_module_active():
            try:
                token = await self._get_telegram_token()
                if token:
                    from .workers.telegram_worker import TelegramWorker

                    tg_worker = TelegramWorker(self.app, token)
                    await tg_worker.start()
                    self._workers.append(tg_worker)
                    logger.info("Message Hub: Telegram-Worker gestartet")
                else:
                    logger.info(
                        "Message Hub: Telegram-Token nicht konfiguriert — Worker übersprungen"
                    )
            except Exception as exc:
                logger.warning(
                    "Message Hub: Telegram-Worker konnte nicht gestartet werden: %s", exc
                )
        else:
            logger.info(
                "Message Hub: Telegram-Modul aktiv — Telegram-Worker wird nicht doppelt gestartet"
            )

        logger.info(
            "Message Hub bereit. %d Worker aktiv.", len(self._workers)
        )

    async def stop(self) -> None:
        """Stoppt alle Worker graceful."""
        for worker in self._workers:
            try:
                await worker.stop()
            except Exception as exc:
                logger.warning("Message Hub: Worker-Stop-Fehler: %s", exc)
        self._workers.clear()
        logger.info("Message Hub gestoppt.")

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    def get_status(self) -> HubStatus:
        """Gibt den aktuellen Status aller Worker zurück."""
        worker_statuses = [WorkerStatus(**w.status()) for w in self._workers]
        return HubStatus(
            workers=worker_statuses,
            route_count=0,   # wird async befüllt in routes.py
            active_route_count=0,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _telegram_module_active() -> bool:
        """Prüft ob das Telegram-Katalog-Modul installiert und aktiv ist."""
        try:
            import importlib

            tg = importlib.import_module("plugins.telegram.bot")
            return tg is not None
        except ModuleNotFoundError:
            try:
                import importlib

                tg = importlib.import_module("modules.telegram.bot")
                return tg is not None
            except ModuleNotFoundError:
                return False

    @staticmethod
    async def _get_telegram_token() -> str:
        """Lädt Telegram-Token aus ConnectionManager."""
        try:
            from core.connections import ConnectionManager
            from core.vault import get_vault

            conn = await ConnectionManager.get_default_connection("telegram")
            if not conn:
                return ""
            vault = get_vault()
            token_key = conn.vault_keys.get("TELEGRAM_BOT_TOKEN")
            if token_key:
                return await vault.get_secret(token_key)
            return ""
        except Exception as exc:
            logger.debug("Message Hub: Telegram-Token konnte nicht geladen werden: %s", exc)
            return ""
