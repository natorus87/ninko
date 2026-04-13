"""
Telegram Long-Polling Bot for Ninko.
Connects to the Telegram API, receives messages and forwards them to the orchestrator.

Voice-Reply: When an incoming voice message is detected and voice_reply is enabled
in the connection config, the bot replies with a voice message (OGG/Opus).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI

from core.redis_client import get_redis
from agents.base_agent import _t
from .formatter import format_for_telegram


def _clean_for_tts(text: str) -> str:
    """Clean text before TTS synthesis: remove emojis, Markdown, tables, HTML."""
    # Remove table rows (lines with ≥ 2 pipes)
    lines = [ln for ln in text.split("\n") if ln.count("|") < 2]
    text = "\n".join(lines)

    # Remove context prefixes and chat ID references
    text = re.sub(
        r"\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?", "", text
    )
    text = re.sub(r"(?:Telegram\s+)?Chat-?ID[:\s]+\d+", "", text)

    # Remove "via module" footer
    text = re.sub(r"\n\n_via [^_\n]+_\s*$", "", text)

    # HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Markdown formatting
    text = re.sub(r"```[\s\S]*?```", "", text)  # Code blocks
    text = re.sub(r"`([^`]+)`", r"\1", text)  # Inline code
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)  # Bold/Italic
    text = re.sub(r"_([^_\n]+)_", r"\1", text)  # Underscore italic
    text = re.sub(r"~~([^~]+)~~", r"\1", text)  # Strikethrough
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # Headings
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # Links

    # Remove emojis
    text = re.sub(
        "["
        "\U0001f300-\U0001f9ff"
        "\U0001fa00-\U0001faff"
        "\U00002600-\U000027bf"
        "\U0001f1e0-\U0001f1ff"
        "\u2000-\u206f"
        "✅❌🔄🎙️📊🚀💡⚠️ℹ️"
        "]+",
        "",
        text,
    )

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


logger = logging.getLogger("ninko.modules.telegram.bot")

# Maximum message length (Telegram limit: 4096)
_MAX_MSG_LEN = 4000


def _strip_pipeline_headers(text: str) -> str:
    """Remove 'Step N – module:' headers and Telegram send confirmations from pipeline responses."""
    # **Step 1 – module:** (Markdown bold)
    text = re.sub(r"\*\*Schritt\s+\d+\s*[–-]\s*\w+:\*\*\s*\n?", "", text)
    # Step 1 – module: (plain)
    text = re.sub(r"(?m)^Schritt\s+\d+\s*[–-]\s*\w+:\s*\n?", "", text)
    # Telegram send confirmation (sent separately by the Telegram module)
    text = re.sub(
        r"✅\s*Telegram-?\s*Nachricht\s+.*?(?:gesendet|erfolgreich)[^\n]*\n?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Normalize multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class TelegramBot:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.running = False
        self.task: asyncio.Task | None = None
        self.offset = 0
        # Tracks sessions that were cleared while a request was in flight
        self._cleared_sessions: set[str] = set()
        # Track background tasks to prevent memory leaks
        self._background_tasks: set[asyncio.Task] = set()
        self._pairing_ttl = 3600  # 1 hour

    async def _get_connection_config(self) -> dict[str, Any]:
        """Get Telegram connection config with defaults."""
        from core.connections import ConnectionManager

        conn = await ConnectionManager.get_default_connection("telegram")
        if conn:
            return conn.config
        return {}

    async def _is_user_authorized(
        self, user_id: int, chat_id: int, is_group: bool = False
    ) -> tuple[bool, str]:
        """
        Check if user is authorized based on DM policy and allowlists.
        Returns (authorized, reason).
        """
        config = await self._get_connection_config()

        # DM Policy: pairing | allowlist | open | disabled
        dm_policy = config.get("dm_policy", "pairing")

        if dm_policy == "disabled":
            return False, "DMs are disabled"

        if dm_policy == "open":
            return True, "open policy"

        # Get allowlist (numeric user IDs)
        allow_from = config.get("allow_from", [])
        if isinstance(allow_from, str):
            allow_from = [s.strip() for s in allow_from.split(",") if s.strip()]

        # Check if user is in allowlist
        if str(user_id) in allow_from:
            return True, "allowlist"

        # For pairing policy, check if user has a valid pairing
        if dm_policy == "pairing":
            redis = get_redis()
            paired_key = f"ninko:telegram:paired_users:{user_id}"
            is_paired = await redis.connection.get(paired_key)
            if is_paired:
                return True, "paired"
            return False, "pairing required - use /pair"

        return False, "not in allowlist"

    async def _generate_pairing_code(self, user_id: int) -> str:
        """Generate a pairing code for user authorization."""
        import secrets
        import string

        # Generate 6-character code
        code = "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6)
        )

        redis = get_redis()
        pairing_key = f"ninko:telegram:pairing:{code}"

        # Store with TTL
        await redis.connection.setex(pairing_key, self._pairing_ttl, str(user_id))

        return code

    async def _approve_pairing(
        self, code: str, admin_user_id: int | None = None
    ) -> bool:
        """Approve a pairing request by code."""
        redis = get_redis()
        pairing_key = f"ninko:telegram:pairing:{code}"

        user_id = await redis.connection.get(pairing_key)
        if not user_id:
            return False

        # Mark user as paired (permanent)
        paired_key = f"ninko:telegram:paired_users:{user_id}"
        await redis.connection.set(paired_key, "1")

        # Delete pairing code
        await redis.connection.delete(pairing_key)

        return True

    async def get_token(self) -> str | None:
        """Load the current Telegram bot token from the ConnectionManager."""
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("telegram")
        if not conn:
            return None

        vault = get_vault()
        if "TELEGRAM_BOT_TOKEN" in conn.vault_keys:
            return await vault.get_secret(conn.vault_keys["TELEGRAM_BOT_TOKEN"])

        return None

    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        """Track a background task to prevent memory leaks."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def start(self) -> None:
        """Start the polling loop as a background task."""
        if self.running:
            return

        token = await self.get_token()
        if not token:
            logger.warning("Telegram bot token missing. Polling start aborted.")
            return

        # Register native Telegram commands in menu
        await self._register_commands(token)

        self.running = True
        self.task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram bot polling started.")

    async def stop(self) -> None:
        """Stop the polling loop and cancel all background tasks."""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None

        # Cancel all tracked background tasks
        if self._background_tasks:
            for task in list(self._background_tasks):
                task.cancel()
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        logger.info("Telegram bot polling stopped.")

    async def _register_commands(self, token: str) -> None:
        """
        Register native Telegram bot commands in the menu (OpenClaw-style).
        Commands appear in the Telegram command menu for easy access.
        """
        commands = [
            {"command": "start", "description": "Start the bot / clear chat history"},
            {"command": "clear", "description": "Clear chat history and reset"},
            {"command": "reset", "description": "Reset conversation memory"},
            {"command": "chatid", "description": "Show your Telegram Chat ID"},
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"https://api.telegram.org/bot{token}/setMyCommands"
                resp = await client.post(url, json={"commands": commands})
                if resp.status_code == 200 and resp.json().get("ok"):
                    logger.info(
                        "Telegram commands registered: %s",
                        [c["command"] for c in commands],
                    )
                else:
                    logger.warning("Failed to register commands: %s", resp.text)
        except Exception as exc:
            logger.warning("Could not register Telegram commands: %s", exc)

    async def _poll_loop(self) -> None:
        """Main long-polling loop."""
        timeout_s = 30

        while self.running:
            token = await self.get_token()
            if not token:
                logger.error("Telegram token lost during polling.")
                await asyncio.sleep(10)
                continue

            try:
                async with httpx.AsyncClient(timeout=timeout_s + 5.0) as poll_client:
                    url = f"https://api.telegram.org/bot{token}/getUpdates"
                    params: dict[str, Any] = {
                        "offset": self.offset,
                        "timeout": timeout_s,
                        "allowed_updates": ["message", "callback_query"],
                    }

                    resp = await poll_client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            updates = data.get("result", [])
                            for update in updates:
                                self.offset = update["update_id"] + 1
                                # Process each update as an independent tracked task
                                self._track_task(
                                    asyncio.create_task(
                                        self.handle_update(update, token)
                                    )
                                )
                        else:
                            logger.error(
                                "Telegram API Error: %s", data.get("description")
                            )
                            await asyncio.sleep(5)
                    elif resp.status_code == 401:
                        logger.error("Telegram Unauthorized. Stopping polling.")
                        self.running = False
                        break
                    else:
                        logger.warning("Telegram HTTP Error: %s", resp.status_code)
                        await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                continue  # Normal for long-polling with no new messages
            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                asyncio.TimeoutError,
            ) as e:
                logger.exception("Error in Telegram polling loop: %s", e)
                await asyncio.sleep(10)

    async def _send(
        self,
        token: str,
        chat_id: int,
        text: str,
        parse_mode: str = "",
        reply_to_message_id: int | None = None,
    ) -> bool:
        """
        Send a message. Tries parse_mode first, falls back to plain text on error.
        Supports reply threading via reply_to_message_id (OpenClaw-style).
        Returns True on success.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True

                # Markdown parse error → fallback to plain text
                if parse_mode and resp.status_code == 400:
                    logger.debug("Markdown parsing failed, sending plain text.")
                    plain_payload = {"chat_id": chat_id, "text": text}
                    if reply_to_message_id:
                        plain_payload["reply_to_message_id"] = reply_to_message_id
                    resp2 = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=plain_payload,
                    )
                    return resp2.status_code == 200 and resp2.json().get("ok")

                logger.warning(
                    "sendMessage error: %s %s", resp.status_code, resp.text[:100]
                )
                return False
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.error("_send error: %s", exc)
            return False

    async def _send_with_keyboard(
        self,
        token: str,
        chat_id: int,
        text: str,
        buttons: list[list[dict[str, str]]],
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Send a message with inline keyboard buttons.
        buttons: e.g. [[{"text": "Ja", "callback_data": "confirm_yes"}, {"text": "Nein", "callback_data": "confirm_no"}]]
        Returns True on success.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": {"inline_keyboard": buttons},
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning(
                    "sendMessage with keyboard error: %s %s",
                    resp.status_code,
                    resp.text[:100],
                )
                return False
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.error("_send_with_keyboard error: %s", exc)
            return False

    async def _react(
        self, token: str, chat_id: int, message_id: int, emoji: str = "👍"
    ) -> None:
        """Set an emoji reaction on a message (best-effort, no error propagation)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/setMessageReaction",
                    json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "reaction": [{"type": "emoji", "emoji": emoji}],
                    },
                )
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ):
            pass

    async def _keep_typing(self, token: str, chat_id: int) -> None:
        """Send a 'typing' action every 4s until the task is cancelled."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                while True:
                    try:
                        await client.post(
                            f"https://api.telegram.org/bot{token}/sendChatAction",
                            json={"chat_id": chat_id, "action": "typing"},
                        )
                    except (
                        RuntimeError,
                        ValueError,
                        TypeError,
                        KeyError,
                        OSError,
                        asyncio.TimeoutError,
                    ):
                        pass
                    await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _transcribe_voice(
        self, file_id: str, token: str
    ) -> tuple[str | None, float, str]:
        """
        Download a Telegram voice file and transcribe it.

        Returns:
            (text, avg_confidence, detected_language)
            text is None on error.
        """
        try:
            from api.routes_transcription import transcribe_bytes_extended

            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{token}/getFile",
                    params={"file_id": file_id},
                )
                r.raise_for_status()
                file_path = r.json().get("result", {}).get("file_path", "")
                if not file_path:
                    return None, -2.0, "de"

                r2 = await client.get(
                    f"https://api.telegram.org/file/bot{token}/{file_path}",
                )
                r2.raise_for_status()
                audio_bytes = r2.content

            filename = file_path.rsplit("/", 1)[-1]
            text, confidence, detected_lang = await transcribe_bytes_extended(
                audio_bytes, filename
            )
            return (text or None), confidence, detected_lang
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.error("Error transcribing Telegram voice message: %s", exc)
            return None, -2.0, "de"

    async def _send_voice(self, token: str, chat_id: int, ogg_bytes: bytes) -> bool:
        """
        Send a voice message via Telegram sendVoice API.
        Expects OGG/Opus bytes (Telegram requirement for voice messages).
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendVoice",
                    data={"chat_id": str(chat_id)},
                    files={"voice": ("voice.ogg", ogg_bytes, "audio/ogg")},
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning(
                    "sendVoice Fehler: %s %s", resp.status_code, resp.text[:100]
                )
                return False
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.error("_send_voice error: %s", exc)
            return False

    async def _send_photo(
        self, token: str, chat_id: int, image_path: str, caption: str = ""
    ) -> bool:
        """
        Send a generated image as a photo via Telegram sendPhoto API.
        Loads the image locally and sends it as multipart/form-data.
        """
        try:
            from pathlib import Path

            # URL path → filesystem path: /api/images/xxx.png → /app/data/images/xxx.png
            filename = image_path.rsplit("/", 1)[-1]
            candidates = [
                Path("/app/data/images") / filename,
                Path("data/images") / filename,
                Path(image_path.lstrip("/")),  # Fallback
            ]
            img_file = None
            for c in candidates:
                if c.exists():
                    img_file = c
                    break
            if not img_file:
                logger.warning(
                    "Image file not found: %s (tried: %s)",
                    filename,
                    [str(c) for c in candidates],
                )
                return False

            image_bytes = img_file.read_bytes()
            ext = img_file.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }
            mime = mime_types.get(ext, "image/png")

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={
                        "chat_id": str(chat_id),
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    files={"photo": (img_file.name, image_bytes, mime)},
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning(
                    "sendPhoto Fehler: %s %s", resp.status_code, resp.text[:200]
                )
                return False
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.error("_send_photo error: %s", exc)
            return False

    async def _send_preview_message(
        self, token: str, chat_id: int, reply_to_message_id: int | None = None
    ) -> int | None:
        """
        Send a preview message for streaming (OpenClaw-style).
        Returns the message_id for editing.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": "💭...",
                }
                if reply_to_message_id:
                    payload["reply_to_message_id"] = reply_to_message_id

                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        return data["result"].get("message_id")
        except Exception as exc:
            logger.debug("Preview message failed: %s", exc)
        return None

    async def _edit_message(
        self,
        token: str,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "",
    ) -> bool:
        """Edit an existing message (for streaming updates)."""
        try:
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:4096],  # Telegram limit
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageText",
                    json=payload,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True

                # If edit fails (e.g., message too long), send as new message
                if resp.status_code == 400:
                    return await self._send(token, chat_id, text, parse_mode)
        except Exception as exc:
            logger.debug("Edit message failed: %s", exc)
        return False

    async def _handle_callback_query(
        self, callback_query: dict[str, Any], token: str
    ) -> None:
        """Handle safeguard confirmation button clicks (confirm_yes / confirm_no)."""
        from core.safeguard import SAFEGUARD_PENDING_KEY

        callback_data = callback_query.get("data", "")
        callback_msg = callback_query.get("message", {})
        chat_id = callback_msg.get("chat", {}).get("id")

        if not chat_id:
            return

        # Acknowledge immediately (removes spinner on the button)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                    json={"callback_query_id": callback_query.get("id")},
                )
        except Exception as _cb_exc:
            logger.debug("answerCallbackQuery fehlgeschlagen (best-effort): %s", _cb_exc)

        redis = get_redis()
        session_id = f"telegram_{chat_id}"
        pending_key = SAFEGUARD_PENDING_KEY.format(session_id=session_id)
        pending_raw = await redis.connection.get(pending_key)

        if callback_data == "confirm_yes":
            if not pending_raw:
                await self._send(
                    token,
                    chat_id,
                    _t(
                        "Keine ausstehende Aktion.",
                        "No pending action.",
                        fr="Aucune action en attente.",
                        es="No hay acción pendiente.",
                        it="Nessuna azione in sospeso.",
                        nl="Geen openstaande actie.",
                        pl="Brak oczekującej akcji.",
                        pt="Nenhuma ação pendente.",
                        ja="保留中のアクションはありません。",
                        zh="没有待处理的操作。",
                    ),
                )
                return

            original_text = (
                pending_raw.decode() if isinstance(pending_raw, bytes) else pending_raw
            )
            await redis.connection.delete(pending_key)
            logger.info(
                "Safeguard: Telegram user confirmed via button for %s.", session_id
            )

            typing_task = self._track_task(
                asyncio.create_task(self._keep_typing(token, chat_id))
            )
            try:
                orchestrator = self.app.state.orchestrator
                history = await redis.get_chat_history(session_id)
                contextualized_text = f"[Telegram Chat-ID: {chat_id}]\n{original_text}"
                response_text, _, did_compact = await orchestrator.route(
                    message=contextualized_text,
                    chat_history=history,
                    session_id=session_id,
                    confirmed=True,
                )
                await redis.store_chat_message(
                    session_id=session_id, role="user", content=original_text
                )
                await redis.store_chat_message(
                    session_id=session_id, role="assistant", content=response_text
                )
                if did_compact:
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content="Conversation history has been compressed.",
                    )
                await self._send(token, chat_id, response_text, parse_mode="HTML")
            except Exception as exc:
                logger.error(
                    "Callback confirm_yes error for %s: %s", session_id, exc, exc_info=True
                )
                await self._send(
                    token,
                    chat_id,
                    _t(
                        "❌ Fehler bei der Ausführung.",
                        "❌ Error during execution.",
                        fr="❌ Erreur lors de l'exécution.",
                        es="❌ Error durante la ejecución.",
                        it="❌ Errore durante l'esecuzione.",
                        nl="❌ Fout bij uitvoering.",
                        pl="❌ Błąd podczas wykonywania.",
                        pt="❌ Erro durante a execução.",
                        ja="❌ 実行中にエラーが発生しました。",
                        zh="❌ 执行时出错。",
                    ),
                )
            finally:
                typing_task.cancel()

        elif callback_data == "confirm_no":
            await redis.connection.delete(pending_key)
            await self._send(
                token,
                chat_id,
                _t(
                    "❌ Aktion abgebrochen.",
                    "❌ Action cancelled.",
                    fr="❌ Action annulée.",
                    es="❌ Acción cancelada.",
                    it="❌ Azione annullata.",
                    nl="❌ Actie geannuleerd.",
                    pl="❌ Działanie anulowane.",
                    pt="❌ Ação cancelada.",
                    ja="❌ アクションがキャンセルされました。",
                    zh="❌ 操作已取消。",
                ),
            )
        # Unknown callback_data: ignore silently

    async def handle_update(self, update: dict[str, Any], token: str) -> None:
        """Process a single Telegram update."""
        # ── Callback query (inline button click) ──────────────────────────────
        if update.get("callback_query"):
            await self._handle_callback_query(update["callback_query"], token)
            return

        msg = update.get("message")
        if not msg:
            return

        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")
        text = msg.get("text")
        is_voice = False
        detected_lang: str = os.getenv("WHISPER_LANGUAGE", "de")
        low_confidence = False

        # Transcribe voice messages (no status text, silent typing indicator only)
        voice = msg.get("voice") or msg.get("audio")
        if not text and voice:
            file_id = voice.get("file_id")
            if file_id:
                is_voice = True
                text, confidence, detected_lang = await self._transcribe_voice(
                    file_id, token
                )
                if not text:
                    await self._send(
                        token, chat_id, "❌ Transcription failed. Please send as text."
                    )
                    return
                # Confidence check
                import core.config as _cfg_mod

                _cfg = _cfg_mod.get_settings()
                if confidence < _cfg.STT_CONFIDENCE_THRESHOLD:
                    low_confidence = True
                    logger.info(
                        "STT Konfidenz niedrig (%.2f < %.2f): '%s'",
                        confidence,
                        _cfg.STT_CONFIDENCE_THRESHOLD,
                        text[:60],
                    )

        if not chat_id or not text:
            return

        cmd = text.strip().lower().split("@")[0]  # /clear@botname → /clear

        user = msg.get("from", {})
        user_id = user.get("id")
        username = user.get("username", "")
        is_group = msg.get("chat", {}).get("type") in ["group", "supergroup"]

        authorized, reason = await self._is_user_authorized(user_id, chat_id, is_group)

        if cmd == "/chatid":
            await self._send(
                token,
                chat_id,
                f"🆔 Deine Telegram Chat-ID: <code>{chat_id}</code>",
                parse_mode="HTML",
            )
            return

        if cmd == "/pair":
            if authorized:
                await self._send(
                    token,
                    chat_id,
                    _t(
                        "✅ Du bist bereits autorisiert.",
                        "✅ You are already authorized.",
                    ),
                )
            else:
                code = await self._generate_pairing_code(user_id)
                await self._send(
                    token,
                    chat_id,
                    _t(
                        f"🔐 Pairing-Code: <code>{code}</code>\n\nGib diesen Code im Ninko Dashboard ein oder sende ihn einem Admin.",
                        f"🔐 Pairing Code: <code>{code}</code>\n\nEnter this code in the Ninko Dashboard or send it to an admin.",
                    ),
                    parse_mode="HTML",
                )
            return

        if cmd.startswith("/pair ") and user_id:
            # Admin approval: /pair CODE
            parts = text.strip().split()
            if len(parts) == 2:
                code = parts[1].upper()
                success = await self._approve_pairing(code, user_id)
                if success:
                    await self._send(
                        token,
                        chat_id,
                        _t(
                            "✅ Pairing erfolgreich! Der Benutzer ist jetzt autorisiert.",
                            "✅ Pairing successful! The user is now authorized.",
                        ),
                    )
                else:
                    await self._send(
                        token,
                        chat_id,
                        _t(
                            "❌ Ungültiger oder abgelaufener Pairing-Code.",
                            "❌ Invalid or expired pairing code.",
                        ),
                    )
            return

        if not authorized and not is_group:
            await self._send(
                token,
                chat_id,
                _t(
                    f"🔒 Zugriff verweigert: {reason}\n\nVerwende /pair um einen Pairing-Code zu generieren.",
                    f"🔒 Access denied: {reason}\n\nUse /pair to generate a pairing code.",
                ),
            )
            return

        # Legacy allowlist check (chat-based, for backward compatibility)
        from core.connections import ConnectionManager

        conn = await ConnectionManager.get_default_connection("telegram")
        if conn:
            allowed_raw = conn.config.get("allowed_chat_ids", "")
            if allowed_raw:
                allowed_ids = {
                    s.strip() for s in str(allowed_raw).split(",") if s.strip()
                }
                if str(chat_id) not in allowed_ids:
                    logger.warning(
                        "Telegram: Access denied for chat ID %s (not in allowlist)",
                        chat_id,
                    )
                    return

        # Read voice-reply configuration from connection
        voice_reply = False
        voice_reply_text_too = False
        voice_lang: str | None = None
        voice_name: str | None = None
        if conn:
            voice_reply = str(conn.config.get("voice_reply", "false")).lower() in (
                "true",
                "1",
                "yes",
            )
            voice_reply_text_too = str(
                conn.config.get("voice_reply_text_too", "false")
            ).lower() in ("true", "1", "yes")
            voice_lang = conn.config.get("voice_lang") or None
            voice_name = conn.config.get("voice_name") or None

        logger.info("Telegram message from chat %s: %s…", chat_id, text[:60])

        if cmd in ("/start", "/clear", "/reset"):
            session_id_local = f"telegram_{chat_id}"
            try:
                redis = get_redis()
                await redis.clear_chat_history(session_id_local)
                # Race-condition protection: in-flight requests should not write back history
                self._cleared_sessions.add(session_id_local)
                await self._send(
                    token, chat_id, "♻️ Chat history cleared. How can I help?"
                )
            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                asyncio.TimeoutError,
            ) as exc:
                logger.error("Error clearing chat history for %s: %s", chat_id, exc)
                await self._send(token, chat_id, f"❌ Error clearing history: {exc}")
            return

        # ── Low confidence: ask for confirmation instead of processing ─────────
        if low_confidence:
            await self._send(
                token,
                chat_id,
                _t(
                    f'🎙️ Ich habe verstanden:\n<i>"{text}"</i>\n\nIst das korrekt? (Antworte mit Ja oder schicke den Text nochmal.)',
                    f'🎙️ I understood:\n<i>"{text}"</i>\n\nIs this correct? (Reply with yes or send the text again.)',
                ),
                parse_mode="HTML",
            )
            return

        # ── Ack reaction: immediate "👀" feedback, then "⚡" while working ────
        if message_id:
            await self._react(token, chat_id, message_id, "👀")  # Acknowledge
        typing_task = self._track_task(
            asyncio.create_task(self._keep_typing(token, chat_id))
        )

        try:
            from core.safeguard import is_bot_confirmation, SAFEGUARD_PENDING_KEY

            orchestrator = self.app.state.orchestrator
            redis = get_redis()
            session_id = f"telegram_{chat_id}"

            # ── Safeguard check ────────────────────────────────────────────────
            safeguard = getattr(self.app.state, "safeguard", None)
            pending_key = SAFEGUARD_PENDING_KEY.format(session_id=session_id)
            pending_raw = await redis.connection.get(pending_key)

            # Callback queries are handled in _handle_callback_query (dispatched from
            # handle_update before this code path is reached).

            if pending_raw and is_bot_confirmation(text):
                # User confirmed via text (legacy support)
                text = (
                    pending_raw.decode()
                    if isinstance(pending_raw, bytes)
                    else pending_raw
                )
                await redis.connection.delete(pending_key)
                logger.info(
                    "Safeguard: Telegram user confirmed pending action for %s.",
                    session_id,
                )
            elif safeguard:
                sg_result = await safeguard.check(text)
                if sg_result.requires_confirmation:
                    await redis.connection.set(pending_key, text, ex=300)
                    await self._send_with_keyboard(
                        token,
                        chat_id,
                        _t(
                            f"⚠️ <b>Bestätigung erforderlich</b>\n\n"
                            f"<b>Kategorie:</b> {sg_result.category.value}\n"
                            f"<b>Begründung:</b> {sg_result.rationale}\n\n"
                            f"Möchtest du fortfahren?",
                            f"⚠️ <b>Confirmation required</b>\n\n"
                            f"<b>Category:</b> {sg_result.category.value}\n"
                            f"<b>Reason:</b> {sg_result.rationale}\n\n"
                            f"Do you want to continue?",
                            fr=f"⚠️ <b>Confirmation requise</b>\n\n<b>Catégorie:</b> {sg_result.category.value}\n<b>Raison:</b> {sg_result.rationale}\n\nVoulez-vous continuer?",
                            es=f"⚠️ <b>Confirmación requerida</b>\n\n<b>Categoría:</b> {sg_result.category.value}\n<b>Razón:</b> {sg_result.rationale}\n\n¿Quieres continuar?",
                            it=f"⚠️ <b>Conferma richiesta</b>\n\n<b>Categoria:</b> {sg_result.category.value}\n<b>Motivo:</b> {sg_result.rationale}\n\nVuoi continuare?",
                            nl=f"⚠️ <b>Bevestiging vereist</b>\n\n<b>Categorie:</b> {sg_result.category.value}\n<b>Reden:</b> {sg_result.rationale}\n\nWil je doorgaan?",
                            pl=f"⚠️ <b>Wymagane potwierdzenie</b>\n\n<b>Kategoria:</b> {sg_result.category.value}\n<b>Powód:</b> {sg_result.rationale}\n\nCzy chcesz kontynuować?",
                            pt=f"⚠️ <b>Confirmação necessária</b>\n\n<b>Categoria:</b> {sg_result.category.value}\n<b>Motivo:</b> {sg_result.rationale}\n\nQuer continuar?",
                            ja=f"⚠️ <b>確認が必要</b>\n\n<b>カテゴリ:</b> {sg_result.category.value}\n<b>理由:</b> {sg_result.rationale}\n\n続行しますか？",
                            zh=f"⚠️ <b>需要确认</b>\n\n<b>类别:</b> {sg_result.category.value}\n<b>原因:</b> {sg_result.rationale}\n\n是否继续？",
                        ),
                        [
                            [
                                {
                                    "text": _t(
                                        "✅ Ja",
                                        "✅ Yes",
                                        "✅ Oui",
                                        "✅ Sí",
                                        "✅ Sì",
                                        "✅ Ja",
                                        "✅ Tak",
                                        "✅ Sim",
                                        "✅ はい",
                                        "✅ 是",
                                    ),
                                    "callback_data": "confirm_yes",
                                },
                                {
                                    "text": _t(
                                        "❌ Nein",
                                        "❌ No",
                                        "❌ Non",
                                        "❌ No",
                                        "❌ No",
                                        "❌ Nee",
                                        "❌ Nie",
                                        "❌ Não",
                                        "❌ いいえ",
                                        "❌ 否",
                                    ),
                                    "callback_data": "confirm_no",
                                },
                            ]
                        ],
                    )
                    return

            history = await redis.get_chat_history(session_id)

            # Chat-ID + detected language as context hint
            lang_hint = ""
            if (
                os.getenv("WHISPER_LANGUAGE", "de") == "auto"
                and detected_lang
                and detected_lang != "de"
            ):
                lang_hint = f"[Erkannte Sprache: {detected_lang}] "
            contextualized_text = f"[Telegram Chat-ID: {chat_id}]\n{lang_hint}{text}"

            response_text, module_used, did_compact = await orchestrator.route(
                message=contextualized_text,
                chat_history=history,
                session_id=session_id,
            )

            # Save history — skip if session was cleared in the meantime
            if session_id in self._cleared_sessions:
                self._cleared_sessions.discard(session_id)
                logger.info(
                    "History save for %s skipped (session was cleared).", session_id
                )
            else:
                if did_compact:
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content="Conversation history has been compressed.",
                    )
                await redis.store_chat_message(
                    session_id=session_id, role="user", content=text
                )
                await redis.store_chat_message(
                    session_id=session_id, role="assistant", content=response_text
                )

            # ── Context compression: inform user ──────────────────────────────
            if did_compact:
                await self._send(
                    token,
                    chat_id,
                    "🗜️ <i>Conversation history has been compressed — older details have been summarized.</i>",
                    parse_mode="HTML",
                    reply_to_message_id=message_id,
                )

            # ── Voice-Reply: always voice for voice inputs, no text ────────────
            if is_voice:
                await self._send_voice_reply(
                    token, chat_id, response_text, lang=voice_lang, voice=voice_name
                )
                return

            # ── Telegram module already sent directly → don't send again ───────
            # The module calls send_telegram_message → message already delivered.
            # Exception: error messages are always sent back.
            if module_used == "telegram" and not any(
                response_text.lower().startswith(p) for p in ("fehler", "error")
            ):
                logger.debug(
                    "Telegram module already sent for chat %s — suppressing bot response.",
                    chat_id,
                )
                return

            # ── Text response (for text inputs only) ──────────────────────────
            final_text = _strip_pipeline_headers(response_text)
            if module_used:
                final_text += f"\n\n_via {module_used}_"

            # ── Image generation: detect marker, URL, or phrase ────────────
            image_path = None
            # 1. [NINKO_IMAGE:url] marker (backward-compat: KUMIO_IMAGE)
            m = re.search(
                r"\[(?:NINKO_IMAGE|KUMIO_IMAGE):(/api/images/[^\]]+)\]", final_text
            )
            if not m:
                # 2. /api/images/ URL irgendwo im Text
                m = re.search(r"(/api/images/[\w\-]+\.\w+)", final_text)
            if m:
                image_path = m.group(1)
                logger.info("Image path detected in text: %s", image_path)
            elif re.search(
                r"[Bb]ild\s+(?:erfolgreich\s+)?generiert|[Bb]ild\s+erstellt|generate_image",
                response_text,
                re.IGNORECASE,
            ):
                # 3. Tool was called but LLM omitted URL → use most recent image
                #    IMPORTANT: use response_text (raw) not final_text (filtered)
                try:
                    from pathlib import Path

                    img_dir = Path("/app/data/images")
                    if img_dir.exists():
                        imgs = sorted(
                            img_dir.glob("*.png"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                        if imgs:
                            age_seconds = (
                                __import__("time").time() - imgs[0].stat().st_mtime
                            )
                            if age_seconds < 300:  # Only images less than 5 minutes old
                                image_path = f"/api/images/{imgs[0].name}"
                                logger.info(
                                    "Image URL missing in response, using newest image (%ds old): %s",
                                    age_seconds,
                                    image_path,
                                )
                except (
                    RuntimeError,
                    ValueError,
                    TypeError,
                    KeyError,
                    OSError,
                    asyncio.TimeoutError,
                ) as e:
                    logger.debug("Error searching for newest image: %s", e)

            if image_path:
                # Text without markers/URL for caption
                caption = re.sub(
                    r"\[(?:NINKO_IMAGE|KUMIO_IMAGE):[^\]]+\]\s*\n?", "", final_text
                ).strip()
                caption = re.sub(r"/api/images/[\w\-]+\.\w+\s*\n?", "", caption).strip()
                caption = format_for_telegram(caption)[:1024]  # Telegram caption limit
                try:
                    await self._send_photo(token, chat_id, image_path, caption)
                except (
                    RuntimeError,
                    ValueError,
                    TypeError,
                    KeyError,
                    OSError,
                    asyncio.TimeoutError,
                ) as exc:
                    logger.warning(
                        "Image send failed, falling back to text: %s", img_err
                    )
                    fallback = format_for_telegram(final_text)
                    await self._send(
                        token,
                        chat_id,
                        fallback,
                        parse_mode="HTML",
                        reply_to_message_id=message_id,
                    )
                return

            final_text = format_for_telegram(final_text)

            # Check if streaming is enabled (OpenClaw-style)
            streaming_enabled = str(
                conn.config.get("streaming", "false") if conn else "false"
            ).lower() in ("true", "1", "yes")

            if streaming_enabled and len(final_text) <= 4000:
                # Send preview then edit with final response
                preview_msg_id = await self._send_preview_message(
                    token, chat_id, reply_to_message_id=message_id
                )
                if preview_msg_id:
                    await self._edit_message(
                        token, chat_id, preview_msg_id, final_text, parse_mode="HTML"
                    )
                else:
                    # Fallback to normal send
                    await self._send(
                        token,
                        chat_id,
                        final_text,
                        parse_mode="HTML",
                        reply_to_message_id=message_id,
                    )
            else:
                # Send response in chunks (Telegram limit: 4096 characters)
                chunks = [
                    final_text[i : i + _MAX_MSG_LEN]
                    for i in range(0, len(final_text), _MAX_MSG_LEN)
                ]
                for idx, chunk in enumerate(chunks):
                    await self._send(
                        token,
                        chat_id,
                        chunk,
                        parse_mode="HTML",
                        reply_to_message_id=message_id if idx == 0 else None,
                    )

        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.exception("Error in Telegram orchestrator processing: %s", exc)
            # Descriptive error message instead of generic text
            err_type = type(exc).__name__
            await self._send(
                token,
                chat_id,
                _t(
                    f"❌ Fehler bei der Verarbeitung ({err_type}):\n{str(exc)[:300]}\n\nBitte versuche es erneut.",
                    f"❌ Error during processing ({err_type}):\n{str(exc)[:300]}\n\nPlease try again.",
                ),
                reply_to_message_id=message_id,
            )
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def _send_voice_reply(
        self,
        token: str,
        chat_id: int,
        text: str,
        lang: str | None = None,
        voice: str | None = None,
    ) -> None:
        """
        Synthesize text with Piper TTS and send it as a Telegram voice message.
        Converts WAV → OGG/Opus for the Telegram sendVoice API.
        Errors are logged but not propagated (best-effort).
        """
        try:
            from core.tts import synthesize_reply, is_tts_available
            from core.tts.audio_utils import wav_to_ogg

            clean_text = _clean_for_tts(text)
            if not clean_text:
                logger.warning(
                    "Voice-Reply: cleaned text empty, sending text fallback."
                )
                await self._send(token, chat_id, text)
                return

            if not is_tts_available():
                logger.warning("Voice-Reply: TTS not available, sending text fallback.")
                await self._send(
                    token, chat_id, format_for_telegram(text), parse_mode="HTML"
                )
                return

            wav_bytes = await synthesize_reply(clean_text, lang=lang, voice=voice)
            ogg_bytes = await wav_to_ogg(wav_bytes)
            ok = await self._send_voice(token, chat_id, ogg_bytes)
            if ok:
                logger.info(
                    "Voice-Reply sent to chat %s: %d KB OGG",
                    chat_id,
                    len(ogg_bytes) // 1024,
                )
            else:
                logger.warning("Voice-Reply sendVoice failed for chat %s", chat_id)
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            logger.error("Voice-Reply error for chat %s: %s", chat_id, exc)


# ── Globaler Bot-State ────────────────────────────────────────────────────────
_global_bot: TelegramBot | None = None


def get_telegram_bot() -> TelegramBot | None:
    return _global_bot


def init_telegram_bot(app: FastAPI) -> TelegramBot:
    global _global_bot
    if _global_bot is None:
        _global_bot = TelegramBot(app)
    return _global_bot
