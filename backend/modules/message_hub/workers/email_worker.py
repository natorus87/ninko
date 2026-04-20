"""
Message Hub — Email Worker (IMAP IDLE).

Öffnet eine persistente IMAP-Verbindung zum Postfach und wartet mit
IDLE auf neue Nachrichten. Ist IDLE nicht verfügbar, wird alle 60s
manuell gepollt (NOOP + SEARCH UNSEEN).

Neue Mails werden per Routing-Tabelle an die zugehörige Ninko-Session
weitergeleitet.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import re
import time
from email.header import decode_header as _decode_header
from typing import TYPE_CHECKING

from ..worker_base import ChannelWorker

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("ninko.modules.message_hub.email_worker")

_IDLE_TIMEOUT = 25 * 60   # 25 Minuten (IMAP-Server trennen nach 30 min)
_POLL_INTERVAL = 60       # Polling-Fallback wenn kein IDLE
_MAX_BODY_LEN = 4000      # Maximale Textlänge an den Orchestrator


def _decode_mime_header(value: str) -> str:
    """Dekodiert MIME encoded-words (=?utf-8?...?=) zu normalem String."""
    parts = _decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_text_body(msg: email.message.Message) -> str:
    """Extrahiert den plain-text Body aus einer E-Mail."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset("utf-8")
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset("utf-8")
            return payload.decode(charset, errors="replace")
    return ""


def _clean_body(text: str) -> str:
    """Entfernt überschüssige Leerzeilen und kürzt auf _MAX_BODY_LEN."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > _MAX_BODY_LEN:
        text = text[:_MAX_BODY_LEN] + "\n[…Nachricht gekürzt]"
    return text


class EmailWorker(ChannelWorker):
    """
    IMAP-IDLE Worker für eingehende E-Mails.

    Pro IMAP-Verbindung (ConnectionManager) wird ein Worker gestartet.
    Die channel_id für den Routing-Lookup ist die Absender-E-Mail-Adresse.
    """

    channel_type = "email"

    def __init__(self, app: "FastAPI", connection_id: str = "") -> None:
        super().__init__(app)
        self.connection_id = connection_id

    async def run_once(self) -> None:
        """
        Verbindet zu IMAP, wartet auf neue Nachrichten via IDLE oder Polling.
        Läuft bis self.running == False oder ein Fehler auftritt.
        """
        ctx = await self._load_imap_config()
        if not ctx:
            self.configured = False
            logger.info("Email-Worker: Keine IMAP-Verbindung konfiguriert — warte 60s")
            await asyncio.sleep(60)
            return
        self.configured = True

        mail: imaplib.IMAP4_SSL | None = None
        try:
            mail = await asyncio.to_thread(self._connect_imap, ctx)
            has_idle = await asyncio.to_thread(self._check_idle_support, mail)
            logger.info(
                "Email-Worker verbunden mit %s (IDLE=%s)", ctx["imap_server"], has_idle
            )
            # Bereits ungelesene Mails direkt beim Start verarbeiten
            await self._process_unseen(mail, ctx)

            while self.running:
                if has_idle:
                    await asyncio.to_thread(self._idle_wait, mail)
                    # Mindestverzögerung: verhindert Busy-Loop wenn IDLE sofort zurückkehrt
                    await asyncio.sleep(1)
                else:
                    await asyncio.sleep(_POLL_INTERVAL)

                if not self.running:
                    break
                await self._process_unseen(mail, ctx)
        finally:
            if mail is not None:
                try:
                    await asyncio.to_thread(mail.logout)
                except Exception:
                    pass

    # ── IMAP Helpers ──────────────────────────────────────────────────

    async def _load_imap_config(self) -> dict | None:
        """Lädt IMAP-Konfiguration aus dem Email-Modul."""
        try:
            from core.connections import ConnectionManager
            from core.vault import get_vault

            vault = get_vault()
            if self.connection_id:
                conn = await ConnectionManager.get_connection("email", self.connection_id)
            else:
                conn = await ConnectionManager.get_default_connection("email")

            if not conn:
                return None

            cfg = conn.config
            auth_type = cfg.get("auth_type", "basic")
            password = ""

            if auth_type == "basic":
                secret_key = (
                    conn.vault_keys.get("EMAIL_SECRET")
                    or conn.vault_keys.get("EMAIL_PASSWORD")
                    or conn.vault_keys.get("password")
                )
                if secret_key:
                    password = await vault.get_secret(secret_key)
            # MSAL/OAuth2 wird hier nicht unterstützt (kein Token-Refresh im Background-Worker)

            username = (
                cfg.get("username", "")
                or cfg.get("email_address", "")
            )

            return {
                "imap_server": cfg.get("imap_server", ""),
                "imap_port": int(cfg.get("imap_port", 993)),
                "username": username,
                "password": password,
                "mailbox": cfg.get("mailbox", "INBOX"),
                "auth_type": auth_type,
            }
        except Exception as exc:
            logger.warning("Email-Worker: Konfiguration konnte nicht geladen werden: %s", exc)
            return None

    @staticmethod
    def _connect_imap(ctx: dict) -> imaplib.IMAP4_SSL:
        mail = imaplib.IMAP4_SSL(ctx["imap_server"], ctx["imap_port"])
        mail.login(ctx["username"], ctx["password"])
        mail.select(ctx["mailbox"])
        return mail

    @staticmethod
    def _check_idle_support(mail: imaplib.IMAP4_SSL) -> bool:
        try:
            caps = mail.capability()
            return b"IDLE" in (caps[1][0] if caps[0] == "OK" else b"")
        except Exception:
            return False

    @staticmethod
    def _idle_wait(mail: imaplib.IMAP4_SSL) -> None:
        """Sendet IDLE-Kommando und wartet auf Ereignis oder Timeout."""
        # Raw IDLE: send + warten auf untagged response
        tag = mail._new_tag().decode()
        mail.send(f"{tag} IDLE\r\n".encode())
        # Antwort "+" abwarten (Server bereit)
        mail.readline()
        # Auf "*" warten (neues Event) oder Timeout nach 25 Minuten
        mail.socket().settimeout(_IDLE_TIMEOUT)
        try:
            mail.readline()  # blockiert bis Ereignis oder Timeout
        except Exception:
            pass
        # IDLE beenden
        mail.socket().settimeout(None)
        mail.send(b"DONE\r\n")
        try:
            mail.readline()  # OK / NO response
        except Exception:
            pass

    async def _process_unseen(self, mail: imaplib.IMAP4_SSL, ctx: dict) -> None:
        """Holt alle UNSEEN-Nachrichten und dispatched sie."""
        try:
            uids = await asyncio.to_thread(self._fetch_unseen_uids, mail)
            for uid in uids:
                if not self.running:
                    break
                raw = await asyncio.to_thread(self._fetch_raw, mail, uid)
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                sender = msg.get("From", "")
                # Absender-Adresse extrahieren
                match = re.search(r"<([^>]+)>", sender)
                sender_addr = match.group(1) if match else sender.strip()

                subject = _decode_mime_header(msg.get("Subject", "(kein Betreff)"))
                body = _clean_body(_extract_text_body(msg))

                context_prefix = f"[Email von: {sender_addr} | Betreff: {subject}]"
                logger.debug(
                    "Email-Worker: neue Mail von %s, Betreff=%s", sender_addr, subject
                )
                await self.dispatch(
                    channel_id=sender_addr,
                    text=body or subject,
                    context_prefix=context_prefix,
                )
                # Als gelesen markieren
                await asyncio.to_thread(
                    lambda u=uid: mail.store(u, "+FLAGS", "\\Seen")
                )
        except Exception as exc:
            logger.error("Email-Worker: Fehler beim Verarbeiten: %s", exc, exc_info=True)
            raise

    @staticmethod
    def _fetch_unseen_uids(mail: imaplib.IMAP4_SSL) -> list[bytes]:
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            return []
        uid_bytes = data[0]
        if not uid_bytes:
            return []
        return uid_bytes.split()

    @staticmethod
    def _fetch_raw(mail: imaplib.IMAP4_SSL, uid: bytes) -> bytes | None:
        status, data = mail.fetch(uid, "(RFC822)")
        if status != "OK" or not data:
            return None
        for item in data:
            if isinstance(item, tuple):
                return item[1]
        return None
