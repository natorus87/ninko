"""
Telegram Long-Polling Bot for Ninko.
Connects to the Telegram API, receives messages and forwards them to the orchestrator.

Voice-Reply: When an incoming voice message is detected and voice_reply is enabled
in the connection config, the bot replies with a voice message (OGG/Opus).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import secrets
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from core.redis_client import get_redis
from agents.base_agent import _t
from agents.middleware.postprocess import _strip_agent_meta_chatter
from .formatter import format_chunks_for_telegram, format_for_telegram


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
_CALLBACK_TTL = 300
_CALLBACK_KEY = "ninko:telegram:callback:{session_id}:{request_id}"


def _telegram_image_roots() -> list[Path]:
    """Return image-provider roots in the same precedence order as generation."""
    candidates: list[Path] = []
    configured = (os.getenv("NINKO_IMAGES_DIR") or "").strip()
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path("/app/data/images"),
            Path("data/images"),
            Path(tempfile.gettempdir()) / "ninko-images",
        ]
    )
    roots: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots


# Trace-event phases considered internal wiring (safeguard/routing/context/pipeline
# bookkeeping) — mirrors the web frontend's debug-mode phase filter so the live
# preview only surfaces phases a user would find meaningful (agent/tool/llm).
_INTERNAL_TRACE_PHASES = frozenset({"safeguard", "routing", "context", "pipeline", "request"})

# Recoverable errors around Telegram API calls. httpx errors inherit from
# neither OSError nor asyncio.TimeoutError — without httpx.HTTPError here a
# plain network blip would escape the handlers (and kill the poll loop).
_RECOVERABLE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    asyncio.TimeoutError,
    httpx.HTTPError,
)


def _telegram_commands() -> list[dict[str, str]]:
    """Native Telegram command menu."""
    return [
        {"command": "start", "description": "Start bot and clear chat history"},
        {"command": "help", "description": "Show commands and examples"},
        {"command": "status", "description": "Show bot/session status"},
        {"command": "chatid", "description": "Show this chat ID"},
        {"command": "pair", "description": "Create or approve a pairing code"},
        {"command": "clear", "description": "Clear chat history"},
        {"command": "reset", "description": "Reset conversation memory"},
    ]


def _strip_pipeline_headers(text: str) -> str:
    """Remove transport-only markers from pipeline responses."""
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
    text = re.sub(r"\n\n_via [^_\n]+_\s*$", "", text)
    # Normalize multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_final_response(text: str) -> str:
    """Apply all Telegram-specific response cleanup before final delivery.

    ``_strip_agent_meta_chatter`` (tool-plan/retry narration removal) lives in
    agents.middleware.postprocess, shared with the core chat response
    pipeline — see ResponseExtractionMiddleware.post_process.
    """
    return _strip_agent_meta_chatter(_strip_pipeline_headers(text))


def _safe_stream_preview(text: str) -> str:
    """Return only user-facing partial text for Telegram live edits."""
    preview = _plain_preview_text(text).strip()
    if not preview:
        return ""
    return preview[-3900:]


def _plain_preview_text(text: str) -> str:
    """Keep live Telegram edits readable before the final HTML rendering pass."""
    text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`"), text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return _clean_final_response(text)


def _telegram_error_message(exc: BaseException) -> str:
    """Build a concise, actionable Telegram error without leaking internals."""
    err_type = type(exc).__name__
    lower = f"{err_type} {exc}".lower()

    if any(
        marker in lower
        for marker in (
            "apiconnectionerror",
            "connecterror",
            "connection error",
            "connection refused",
            "all connection attempts failed",
        )
    ):
        return _t(
            "❌ Der KI-Backend-Endpunkt ist aktuell nicht erreichbar. Bitte prüfe den aktiven LLM-Provider in den Ninko-Einstellungen und versuche es erneut.",
            "❌ The AI backend endpoint is currently unreachable. Please check the active LLM provider in Ninko settings and try again.",
        )

    if "timeout" in lower:
        return _t(
            "❌ Die Ausführung hat zu lange gedauert. Bitte versuche es erneut oder stelle die Anfrage enger.",
            "❌ Execution timed out. Please try again or narrow the request.",
        )

    return _t(
        f"❌ Fehler bei der Ausführung ({err_type}). Bitte versuche es erneut.",
        f"❌ Error during execution ({err_type}). Please try again.",
    )


class TelegramBot:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.running = False
        self.task: asyncio.Task | None = None
        self.offset = 0
        # Incremented by /clear so requests can detect stale history snapshots.
        self._session_generations: dict[str, int] = {}
        # Track background tasks to prevent memory leaks
        self._background_tasks: set[asyncio.Task] = set()
        self._pairing_ttl = 3600  # 1 hour
        # Shared HTTP client (lazy; avoids a TLS handshake per API call)
        self._http: httpx.AsyncClient | None = None

    async def _get_connection_config(self) -> dict[str, Any]:
        """Get Telegram connection config with defaults."""
        from core.connections import ConnectionManager

        conn = await ConnectionManager.get_default_connection("telegram")
        if conn:
            return conn.config
        return {}

    async def _is_user_authorized(
        self,
        user_id: int,
        chat_id: int,
        is_group: bool = False,
        config: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Check if user is authorized based on DM policy and allowlists.
        Returns (authorized, reason).
        """
        if config is None:
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

        logger.info(
            "Telegram pairing approved for user %s (approved by %s).",
            user_id,
            admin_user_id if admin_user_id is not None else "dashboard",
        )
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

    @staticmethod
    def _callback_key(session_id: str, request_id: str) -> str:
        return _CALLBACK_KEY.format(session_id=session_id, request_id=request_id)

    async def _create_confirmation(
        self,
        session_id: str,
        user_id: int,
        kind: str,
        payload: str = "",
    ) -> str:
        """Persist a confirmation bound to one request and Telegram user."""
        request_id = secrets.token_urlsafe(8)
        value = json.dumps(
            {"user_id": user_id, "kind": kind, "payload": payload},
            ensure_ascii=False,
        )
        redis = get_redis()
        await redis.connection.setex(
            self._callback_key(session_id, request_id),
            _CALLBACK_TTL,
            value,
        )
        return request_id

    async def _consume_confirmation(
        self,
        session_id: str,
        request_id: str,
        user_id: int,
        expected_kind: str,
    ) -> dict[str, Any] | None:
        """Consume a matching confirmation without cross-user invalidation."""
        if not request_id or not user_id:
            return None

        redis = get_redis()
        key = self._callback_key(session_id, request_id)
        current = await redis.connection.get(key)
        if not current:
            return None
        current_text = current.decode() if isinstance(current, bytes) else current
        try:
            info = json.loads(current_text)
        except (TypeError, ValueError):
            return None
        if info.get("user_id") != user_id or info.get("kind") != expected_kind:
            return None

        try:
            consumed = await redis.connection.execute_command("GETDEL", key)
        except Exception:
            consumed = await redis.connection.get(key)
            if consumed:
                await redis.connection.delete(key)
        if not consumed:
            return None
        consumed_text = consumed.decode() if isinstance(consumed, bytes) else consumed
        if consumed_text != current_text:
            return None
        return info

    async def _clear_pending_message_confirmation(
        self,
        session_id: str,
        request_id: str,
    ) -> None:
        """Delete the text-confirmation alias only when it targets this request."""
        from core.safeguard import SAFEGUARD_PENDING_KEY

        redis = get_redis()
        pending_key = SAFEGUARD_PENDING_KEY.format(session_id=session_id)
        pending = await redis.connection.get(pending_key)
        if not pending:
            return
        pending_text = pending.decode() if isinstance(pending, bytes) else pending
        try:
            info = json.loads(pending_text)
        except (TypeError, ValueError):
            return
        if info.get("request_id") == request_id:
            await redis.connection.delete(pending_key)

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Yield the shared HTTP client (created lazily, closed in stop()).

        Long-running calls override the 10s default via per-request timeouts.
        """
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=10.0)
        yield self._http

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

        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

        logger.info("Telegram bot polling stopped.")

    async def _register_commands(self, token: str) -> None:
        """
        Register native Telegram bot commands in the menu (OpenClaw-style).
        Commands appear in the Telegram command menu for easy access.
        """
        commands = _telegram_commands()

        try:
            async with self._client() as client:
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

        # Startup delay: random 0-5s to desynchronize multiple pods during
        # K8s rolling updates and reduce 409 Conflict collisions.
        import random as _random

        await asyncio.sleep(_random.uniform(0, 5))

        while self.running:
            token = await self.get_token()
            if not token:
                logger.error("Telegram token lost during polling.")
                await asyncio.sleep(10)
                continue

            try:
                async with self._client() as poll_client:
                    url = f"https://api.telegram.org/bot{token}/getUpdates"
                    params: dict[str, Any] = {
                        "offset": self.offset,
                        "timeout": timeout_s,
                        "allowed_updates": json.dumps(["message", "callback_query"]),
                    }

                    resp = await poll_client.get(
                        url, params=params, timeout=timeout_s + 5.0
                    )
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
                    elif resp.status_code == 409:
                        logger.warning(
                            "Telegram HTTP 409 Conflict: Multiple long-polling instances "
                            "use the same bot token. Check for duplicate pods (K8s rolling "
                            "update overlap) or another bot instance running elsewhere. "
                            "Retrying in 30s."
                        )
                        await asyncio.sleep(30)
                    else:
                        logger.warning(
                            "Telegram HTTP Error %s: Unexpected status from getUpdates. "
                            "Retrying in 10s.",
                            resp.status_code,
                        )
                        await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                continue  # Normal for long-polling with no new messages
            except _RECOVERABLE_ERRORS as e:
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
            async with self._client() as client:
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
        except _RECOVERABLE_ERRORS as exc:
            logger.error("_send error: %s", exc)
            return False

    async def _send_formatted_chunks(
        self,
        token: str,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        preview_message_id: int | None = None,
    ) -> bool:
        """Send raw text as independently formatted Telegram-safe chunks."""
        chunks = format_chunks_for_telegram(text, _MAX_MSG_LEN)
        all_sent = True
        for index, chunk in enumerate(chunks):
            if index == 0 and preview_message_id:
                sent = await self._edit_message(
                    token,
                    chat_id,
                    preview_message_id,
                    chunk,
                    parse_mode="HTML",
                )
                if not sent:
                    await self._delete_message(
                        token,
                        chat_id,
                        preview_message_id,
                    )
                    sent = await self._send(
                        token,
                        chat_id,
                        chunk,
                        parse_mode="HTML",
                        reply_to_message_id=reply_to_message_id,
                    )
            else:
                sent = await self._send(
                    token,
                    chat_id,
                    chunk,
                    parse_mode="HTML",
                    reply_to_message_id=(
                        reply_to_message_id if index == 0 else None
                    ),
                )
            all_sent = sent and all_sent
        return all_sent

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
            async with self._client() as client:
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
        except _RECOVERABLE_ERRORS as exc:
            logger.error("_send_with_keyboard error: %s", exc)
            return False

    async def _dismiss_confirmation_message(
        self,
        token: str,
        chat_id: int,
        message_id: int | None,
        *,
        accepted: bool,
    ) -> None:
        """Delete a consumed confirmation, falling back to a terminal edit."""
        if not message_id:
            return

        terminal_text = (
            _t("✅ Bestätigt – wird ausgeführt …", "✅ Confirmed – executing …")
            if accepted
            else _t("❌ Aktion abgebrochen.", "❌ Action cancelled.")
        )
        try:
            async with self._client() as client:
                if await self._delete_message(
                    token,
                    chat_id,
                    message_id,
                    client=client,
                ):
                    return

                response = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageText",
                    json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": terminal_text,
                        "reply_markup": {"inline_keyboard": []},
                    },
                )
                if response.status_code != 200 or not response.json().get("ok"):
                    logger.warning(
                        "Terminal confirmation edit failed: %s %s",
                        response.status_code,
                        response.text[:160],
                    )
        except _RECOVERABLE_ERRORS as exc:
            logger.warning(
                "Telegram confirmation could not be dismissed: %s",
                exc,
            )

    async def _delete_message(
        self,
        token: str,
        chat_id: int,
        message_id: int | None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> bool:
        """Delete one bot message and report Telegram API failures."""
        if not message_id:
            return False
        try:
            if client is None:
                async with self._client() as shared_client:
                    return await self._delete_message(
                        token,
                        chat_id,
                        message_id,
                        client=shared_client,
                    )
            response = await client.post(
                f"https://api.telegram.org/bot{token}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
            )
            if response.status_code == 200 and response.json().get("ok"):
                return True
            logger.warning(
                "deleteMessage failed: %s %s",
                response.status_code,
                response.text[:160],
            )
        except _RECOVERABLE_ERRORS as exc:
            logger.warning("deleteMessage failed: %s", exc)
        return False

    async def _send_tool_confirmation(
        self,
        token: str,
        chat_id: int,
        session_id: str,
        user_id: int,
        info: dict[str, Any],
    ) -> None:
        """Render a tool-level safeguard sentinel as a Telegram confirmation."""
        import html

        request_id = await self._create_confirmation(
            session_id,
            user_id,
            "tool",
            str(info.get("approval_id") or ""),
        )
        category = html.escape(str(info.get("category", "UNKNOWN")))
        rationale = html.escape(str(info.get("rationale", "")))
        tool_name = html.escape(str(info.get("tool_name", "unbekannt")))
        await self._send_with_keyboard(
            token,
            chat_id,
            _t(
                f"⚠️ <b>Tool-Bestätigung erforderlich</b>\n\n"
                f"<b>Tool:</b> <code>{tool_name}</code>\n"
                f"<b>Kategorie:</b> {category}\n"
                f"<b>Begründung:</b> {rationale}\n\n"
                f"Möchtest du fortfahren?",
                f"⚠️ <b>Tool confirmation required</b>\n\n"
                f"<b>Tool:</b> <code>{tool_name}</code>\n"
                f"<b>Category:</b> {category}\n"
                f"<b>Reason:</b> {rationale}\n\n"
                f"Do you want to continue?",
            ),
            [
                [
                    {
                        "text": _t("✅ Ja", "✅ Yes"),
                        "callback_data": f"tool_yes:{request_id}",
                    },
                    {
                        "text": _t("❌ Nein", "❌ No"),
                        "callback_data": f"tool_no:{request_id}",
                    },
                ]
            ],
        )

    async def _react(
        self, token: str, chat_id: int, message_id: int, emoji: str = "👍"
    ) -> None:
        """Set an emoji reaction on a message (best-effort, no error propagation)."""
        try:
            async with self._client() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/setMessageReaction",
                    json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "reaction": [{"type": "emoji", "emoji": emoji}],
                    },
                )
        except _RECOVERABLE_ERRORS:
            pass

    async def _keep_typing(self, token: str, chat_id: int) -> None:
        """Send a 'typing' action every 4s until the task is cancelled."""
        try:
            async with self._client() as client:
                while True:
                    try:
                        await client.post(
                            f"https://api.telegram.org/bot{token}/sendChatAction",
                            json={"chat_id": chat_id, "action": "typing"},
                        )
                    except _RECOVERABLE_ERRORS:
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

            async with self._client() as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{token}/getFile",
                    params={"file_id": file_id},
                    timeout=30.0,
                )
                r.raise_for_status()
                file_path = r.json().get("result", {}).get("file_path", "")
                if not file_path:
                    return None, -2.0, "de"

                r2 = await client.get(
                    f"https://api.telegram.org/file/bot{token}/{file_path}",
                    timeout=30.0,
                )
                r2.raise_for_status()
                audio_bytes = r2.content

            filename = file_path.rsplit("/", 1)[-1]
            text, confidence, detected_lang = await transcribe_bytes_extended(
                audio_bytes, filename
            )
            return (text or None), confidence, detected_lang
        except _RECOVERABLE_ERRORS as exc:
            logger.error("Error transcribing Telegram voice message: %s", exc)
            return None, -2.0, "de"

    async def _send_voice(self, token: str, chat_id: int, ogg_bytes: bytes) -> bool:
        """
        Send a voice message via Telegram sendVoice API.
        Expects OGG/Opus bytes (Telegram requirement for voice messages).
        """
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendVoice",
                    data={"chat_id": str(chat_id)},
                    files={"voice": ("voice.ogg", ogg_bytes, "audio/ogg")},
                    timeout=30.0,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning(
                    "sendVoice Fehler: %s %s", resp.status_code, resp.text[:100]
                )
                return False
        except _RECOVERABLE_ERRORS as exc:
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
            match = re.fullmatch(
                r"/api/images/([A-Za-z0-9][A-Za-z0-9_.-]*\.(?:png|jpe?g|webp|gif))",
                image_path,
                flags=re.IGNORECASE,
            )
            if not match:
                logger.warning("Rejected unsafe Telegram image path: %s", image_path)
                return False

            filename = match.group(1)
            img_file: Path | None = None
            for image_root in _telegram_image_roots():
                candidate = (image_root / filename).resolve()
                if candidate.is_relative_to(image_root) and candidate.is_file():
                    img_file = candidate
                    break
            if img_file is None:
                logger.warning(
                    "Image file not found below configured roots %s: %s",
                    _telegram_image_roots(),
                    filename,
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

            async with self._client() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={
                        "chat_id": str(chat_id),
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    files={"photo": (img_file.name, image_bytes, mime)},
                    timeout=30.0,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning(
                    "sendPhoto Fehler: %s %s", resp.status_code, resp.text[:200]
                )
                return False
        except _RECOVERABLE_ERRORS as exc:
            logger.error("_send_photo error: %s", exc)
            return False

    async def _send_photo_bytes(
        self,
        token: str,
        chat_id: int,
        image_bytes: bytes,
        mime: str,
        caption: str = "",
    ) -> bool:
        """Send raw image bytes as a photo via Telegram."""
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={
                        "chat_id": str(chat_id),
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    files={"photo": ("chart", image_bytes, mime)},
                    timeout=30.0,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning(
                    "sendPhoto (bytes) Fehler: %s %s", resp.status_code, resp.text[:200]
                )
                return False
        except _RECOVERABLE_ERRORS as exc:
            logger.error("_send_photo_bytes error: %s", exc)
            return False

    async def _send_preview_message(
        self, token: str, chat_id: int, reply_to_message_id: int | None = None
    ) -> int | None:
        """
        Send a preview message for streaming (OpenClaw-style).
        Returns the message_id for editing.
        """
        try:
            async with self._client() as client:
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

            async with self._client() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageText",
                    json=payload,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True

                if resp.status_code == 400:
                    try:
                        description = str(resp.json().get("description") or "")
                    except (TypeError, ValueError):
                        description = resp.text
                    if "message is not modified" in description.lower():
                        return True
                    if parse_mode:
                        plain_payload = dict(payload)
                        plain_payload.pop("parse_mode", None)
                        plain_response = await client.post(
                            f"https://api.telegram.org/bot{token}/editMessageText",
                            json=plain_payload,
                        )
                        if (
                            plain_response.status_code == 200
                            and plain_response.json().get("ok")
                        ):
                            return True
                logger.warning(
                    "editMessageText failed: %s %s",
                    resp.status_code,
                    resp.text[:160],
                )
        except Exception as exc:
            logger.debug("Edit message failed: %s", exc)
        return False

    async def _route_with_live_preview(
        self,
        orchestrator: Any,
        token: str,
        chat_id: int,
        message_id: int | None,
        contextualized_text: str,
        history: list[dict[str, Any]],
        session_id: str,
        confirmed: bool = False,
    ) -> tuple[str, str | None, bool, dict, int | None]:
        """Run the orchestrator and edit a Telegram preview with streamed tokens."""
        preview_msg_id = await self._send_preview_message(
            token,
            chat_id,
            reply_to_message_id=message_id,
        )
        if not preview_msg_id:
            response_text, module_used, did_compact, route_meta = await orchestrator.route(
                message=contextualized_text,
                chat_history=history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=True,
            )
            return response_text, module_used, did_compact, route_meta, None

        token_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=500)
        from core import status_bus

        status_queue = status_bus.get_queue(session_id)
        while not status_queue.empty():
            try:
                status_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        async def _token_callback(chunk: str) -> None:
            try:
                token_queue.put_nowait(chunk)
            except asyncio.QueueFull:
                pass

        route_task = asyncio.create_task(
            orchestrator.route(
                message=contextualized_text,
                chat_history=history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=True,
                token_callback=_token_callback,
            )
        )

        buffer = ""
        latest_status = ""
        last_sent_preview = ""
        last_edit_at = 0.0
        last_sent_len = 0

        try:
            while not route_task.done() or not token_queue.empty():
                try:
                    chunk = await asyncio.wait_for(token_queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    chunk = None

                if chunk:
                    buffer += chunk

                while not status_queue.empty():
                    try:
                        event = status_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "status":
                        latest_status = str(event.get("text") or "").strip()
                    elif event.get("type") == "trace_event":
                        # Most of the actual run only emits trace_event (tool/agent/llm
                        # phases), not the older plain "status" events — without this
                        # branch the live preview never updates during a real run.
                        phase = str(event.get("phase") or "")
                        label = str(event.get("label") or "").strip()
                        if label and phase not in _INTERNAL_TRACE_PHASES:
                            latest_status = label

                now = asyncio.get_running_loop().time()
                enough_text = len(buffer) - last_sent_len >= 24
                enough_time = now - last_edit_at >= 1.2
                route_finished = route_task.done() and token_queue.empty()
                preview = ""
                if buffer:
                    preview = _safe_stream_preview(buffer)
                    if not route_finished:
                        preview = f"{preview} ..." if preview else ""
                if not preview and latest_status:
                    preview = f"⏳ {latest_status}"

                status_changed = bool(preview and preview != last_sent_preview)
                if preview and (
                    route_finished
                    or (preview.startswith("⏳") and status_changed and enough_time)
                    or (buffer and enough_text and enough_time and status_changed)
                    or (not buffer and status_changed and enough_time)
                ):
                    await self._edit_message(
                        token,
                        chat_id,
                        preview_msg_id,
                        preview,
                    )
                    last_edit_at = now
                    last_sent_len = len(buffer)
                    last_sent_preview = preview

            response_text, module_used, did_compact, route_meta = await route_task
            return response_text, module_used, did_compact, route_meta, preview_msg_id
        except asyncio.CancelledError:
            route_task.cancel()
            await asyncio.gather(route_task, return_exceptions=True)
            raise
        except Exception:
            route_task.cancel()
            await asyncio.gather(route_task, return_exceptions=True)
            raise
        finally:
            status_bus.cleanup(session_id)

    async def _handle_callback_query(
        self, callback_query: dict[str, Any], token: str
    ) -> None:
        """Handle safeguard confirmation button clicks (confirm_yes / confirm_no)."""
        from agents.base_agent import _TOOL_SAFEGUARD_SENTINEL

        callback_data = str(callback_query.get("data", ""))
        callback_msg = callback_query.get("message", {})
        chat_id = callback_msg.get("chat", {}).get("id")
        callback_user_id = callback_query.get("from", {}).get("id")

        if not chat_id or not callback_user_id:
            return

        action, separator, request_id = callback_data.partition(":")
        if not separator:
            logger.info("Ignoring legacy Telegram callback without request binding.")
            return

        expected_kind = {
            "confirm_yes": "message",
            "confirm_no": "message",
            "tool_yes": "tool",
            "tool_no": "tool",
        }.get(action)
        if not expected_kind:
            return

        redis = get_redis()
        session_id = f"telegram_{chat_id}"
        confirmation = await self._consume_confirmation(
            session_id,
            request_id,
            callback_user_id,
            expected_kind,
        )

        # Acknowledge immediately (removes spinner on the button)
        try:
            async with self._client() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                    json={"callback_query_id": callback_query.get("id")},
                )
        except Exception as _cb_exc:
            logger.debug("answerCallbackQuery fehlgeschlagen (best-effort): %s", _cb_exc)

        if not confirmation:
            logger.info(
                "Safeguard: stale or unauthorized Telegram confirm button for %s.",
                session_id,
            )
            return

        # Remove the consumed confirmation completely. If Telegram refuses
        # deletion, replace it with a terminal, button-free status message.
        await self._dismiss_confirmation_message(
            token,
            chat_id,
            callback_msg.get("message_id"),
            accepted=action in {"confirm_yes", "tool_yes"},
        )

        if action == "confirm_yes":
            original_text = str(confirmation.get("payload") or "")
            await self._clear_pending_message_confirmation(session_id, request_id)

            logger.info(
                "Safeguard: Telegram user %s confirmed via button for %s.",
                callback_user_id,
                session_id,
            )

            typing_task = self._track_task(
                asyncio.create_task(self._keep_typing(token, chat_id))
            )
            try:
                orchestrator = self.app.state.orchestrator
                history = await redis.get_chat_history(session_id)
                contextualized_text = f"[Telegram Chat-ID: {chat_id}]\n{original_text}"
                config = await self._get_connection_config()
                streaming_enabled = str(
                    config.get("streaming", "false")
                ).lower() in ("true", "1", "yes")
                preview_message_id: int | None = None
                if streaming_enabled:
                    (
                        response_text,
                        _,
                        did_compact,
                        route_meta,
                        preview_message_id,
                    ) = await self._route_with_live_preview(
                        orchestrator=orchestrator,
                        token=token,
                        chat_id=chat_id,
                        message_id=None,
                        contextualized_text=contextualized_text,
                        history=history,
                        session_id=session_id,
                        confirmed=True,
                    )
                else:
                    response_text, _, did_compact, route_meta = (
                        await orchestrator.route(
                            message=contextualized_text,
                            chat_history=history,
                            session_id=session_id,
                            confirmed=True,
                        )
                    )
                if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
                    await self._delete_message(
                        token,
                        chat_id,
                        preview_message_id,
                    )
                    info = json.loads(response_text[len(_TOOL_SAFEGUARD_SENTINEL) :])
                    await self._send_tool_confirmation(
                        token,
                        chat_id,
                        session_id,
                        callback_user_id,
                        info,
                    )
                    return
                await redis.store_chat_message(
                    session_id=session_id, role="user", content=original_text
                )
                await redis.store_chat_message(
                    session_id=session_id, role="assistant", content=response_text
                )
                if did_compact:
                    summary = (route_meta or {}).get("compaction_summary")
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content=summary or "Conversation history has been compressed.",
                    )
                await self._send_formatted_chunks(
                    token,
                    chat_id,
                    _clean_final_response(response_text),
                    preview_message_id=preview_message_id,
                )
            except Exception as exc:
                logger.error(
                    "Callback confirm_yes error for %s: %s", session_id, exc, exc_info=True
                )
                await self._send(
                    token,
                    chat_id,
                    _telegram_error_message(exc),
                )
            finally:
                typing_task.cancel()

        elif action == "confirm_no":
            await self._clear_pending_message_confirmation(session_id, request_id)
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
        elif action == "tool_yes":
            typing_task = self._track_task(
                asyncio.create_task(self._keep_typing(token, chat_id))
            )
            try:
                orchestrator = self.app.state.orchestrator
                config = await self._get_connection_config()
                streaming_enabled = str(
                    config.get("streaming", "false")
                ).lower() in ("true", "1", "yes")
                preview_message_id = (
                    await self._send_preview_message(token, chat_id)
                    if streaming_enabled
                    else None
                )
                response_text, did_compact = await orchestrator.resume_tool_execution(
                    session_id,
                    expected_approval_id=str(confirmation.get("payload") or ""),
                )
                if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
                    await self._delete_message(
                        token,
                        chat_id,
                        preview_message_id,
                    )
                    info = json.loads(response_text[len(_TOOL_SAFEGUARD_SENTINEL) :])
                    await self._send_tool_confirmation(
                        token,
                        chat_id,
                        session_id,
                        callback_user_id,
                        info,
                    )
                    return
                await redis.store_chat_message(
                    session_id=session_id, role="assistant", content=response_text
                )
                if did_compact:
                    # resume_tool_execution returns no route_meta, so there is
                    # no compaction summary to include here.
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content="Conversation history has been compressed.",
                    )
                await self._send_formatted_chunks(
                    token,
                    chat_id,
                    _clean_final_response(response_text),
                    preview_message_id=preview_message_id,
                )
            except Exception as exc:
                logger.error(
                    "Callback confirm_tool_yes error for %s: %s",
                    session_id,
                    exc,
                    exc_info=True,
                )
                await self._send(
                    token,
                    chat_id,
                    _telegram_error_message(exc),
                )
            finally:
                typing_task.cancel()

        elif action == "tool_no":
            from agents.base_agent import discard_pending_safeguard

            discarded = await discard_pending_safeguard(
                session_id,
                redis=redis,
                expected_approval_id=str(confirmation.get("payload") or ""),
            )
            await self._send(
                token,
                chat_id,
                _t("❌ Aktion abgebrochen.", "❌ Action cancelled.")
                if discarded
                else _t(
                    "Diese Tool-Bestätigung ist nicht mehr gültig.",
                    "This tool confirmation is no longer valid.",
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

        command_parts = text.strip().split(maxsplit=1)
        cmd = command_parts[0].lower().split("@")[0] if command_parts else ""
        cmd_args = command_parts[1].strip() if len(command_parts) > 1 else ""

        user = msg.get("from", {})
        user_id = user.get("id")
        if not isinstance(user_id, int):
            logger.warning("Telegram message without a valid sender user ID ignored.")
            return
        is_group = msg.get("chat", {}).get("type") in ["group", "supergroup"]

        # Fetch the connection once per update; auth check, /status and the
        # voice-reply settings below all read from the same config.
        from core.connections import ConnectionManager

        conn = await ConnectionManager.get_default_connection("telegram")
        config: dict[str, Any] = conn.config if conn else {}

        authorized, reason = await self._is_user_authorized(
            user_id, chat_id, is_group, config=config
        )

        if cmd == "/chatid":
            await self._send(
                token,
                chat_id,
                f"🆔 Deine Telegram Chat-ID: <code>{chat_id}</code>",
                parse_mode="HTML",
            )
            return

        if cmd == "/help":
            commands = "\n".join(
                f"/{item['command']} - {item['description']}"
                for item in _telegram_commands()
            )
            await self._send(
                token,
                chat_id,
                _t(
                    "🤖 <b>Ninko Telegram</b>\n\n"
                    f"{commands}\n\n"
                    "<b>Beispiele:</b>\n"
                    "• Wie ist der Status von Kubernetes?\n"
                    "• Zeige failing Pods\n"
                    "• Restarte VM 104 in Proxmox",
                    "🤖 <b>Ninko Telegram</b>\n\n"
                    f"{commands}\n\n"
                    "<b>Examples:</b>\n"
                    "• What is the Kubernetes status?\n"
                    "• Show failing pods\n"
                    "• Restart VM 104 in Proxmox",
                ),
                parse_mode="HTML",
            )
            return

        if cmd == "/status":
            streaming = str(config.get("streaming", "false")).lower() in (
                "true",
                "1",
                "yes",
            )
            voice_reply = str(config.get("voice_reply", "false")).lower() in (
                "true",
                "1",
                "yes",
            )
            await self._send(
                token,
                chat_id,
                _t(
                    "📊 <b>Telegram Status</b>\n\n"
                    f"Bot: {'läuft' if self.running else 'gestoppt'}\n"
                    f"Chat-ID: <code>{chat_id}</code>\n"
                    f"User-ID: <code>{user_id}</code>\n"
                    f"Autorisierung: {reason}\n"
                    f"Streaming: {'an' if streaming else 'aus'}\n"
                    f"Voice Reply: {'an' if voice_reply else 'aus'}",
                    "📊 <b>Telegram Status</b>\n\n"
                    f"Bot: {'running' if self.running else 'stopped'}\n"
                    f"Chat ID: <code>{chat_id}</code>\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Authorization: {reason}\n"
                    f"Streaming: {'on' if streaming else 'off'}\n"
                    f"Voice reply: {'on' if voice_reply else 'off'}",
                ),
                parse_mode="HTML",
            )
            return

        if cmd == "/pair":
            if cmd_args and user_id:
                # Approval requires an already authorized user — otherwise an
                # unauthorized user could approve their own pairing code.
                if not authorized:
                    await self._send(
                        token,
                        chat_id,
                        _t(
                            "🔒 Nur bereits autorisierte Benutzer können Pairing-Codes "
                            "bestätigen. Bitte lass den Code von einem Admin im "
                            "Ninko-Dashboard bestätigen.",
                            "🔒 Only already authorized users can approve pairing "
                            "codes. Please ask an admin to approve the code in the "
                            "Ninko dashboard.",
                        ),
                    )
                    return
                code = cmd_args.split()[0].upper()
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
            elif authorized:
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

        # Legacy allowlist check (chat-based, for backward compatibility).
        # Only reached for unauthorized group chats — unauthorized DMs were
        # rejected above. Without a configured chat allowlist, unauthorized
        # group messages are ignored (silently, to avoid group spam).
        if not authorized:
            allowed_raw = config.get("allowed_chat_ids", "")
            allowed_ids = {
                s.strip() for s in str(allowed_raw).split(",") if s.strip()
            }
            if str(chat_id) not in allowed_ids:
                logger.warning(
                    "Telegram: unauthorized message from user %s in group chat %s "
                    "ignored (%s).",
                    user_id,
                    chat_id,
                    "not in allowed_chat_ids" if allowed_ids else "no allowed_chat_ids configured",
                )
                return

        # Read voice-reply configuration from connection
        voice_reply = str(config.get("voice_reply", "false")).lower() in (
            "true",
            "1",
            "yes",
        )
        voice_reply_text_too = str(
            config.get("voice_reply_text_too", "false")
        ).lower() in ("true", "1", "yes")
        voice_lang = config.get("voice_lang") or None
        voice_name = config.get("voice_name") or None

        logger.info("Telegram message from chat %s: %s…", chat_id, text[:60])

        if cmd in ("/start", "/clear", "/reset"):
            session_id_local = f"telegram_{chat_id}"
            try:
                redis = get_redis()
                await redis.clear_chat_history(session_id_local)
                self._session_generations[session_id_local] = (
                    self._session_generations.get(session_id_local, 0) + 1
                )
                await self._send(
                    token, chat_id, "♻️ Chat history cleared. How can I help?"
                )
            except _RECOVERABLE_ERRORS as exc:
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

        session_id = f"telegram_{chat_id}"
        request_generation = self._session_generations.get(session_id, 0)
        try:
            from core.safeguard import is_bot_confirmation, SAFEGUARD_PENDING_KEY
            from agents.base_agent import _TOOL_SAFEGUARD_SENTINEL

            orchestrator = self.app.state.orchestrator
            redis = get_redis()

            # ── Safeguard check ────────────────────────────────────────────────
            safeguard = getattr(self.app.state, "safeguard", None)
            pending_key = SAFEGUARD_PENDING_KEY.format(session_id=session_id)
            pending_raw = await redis.connection.get(pending_key)
            confirmed = False

            # Callback queries are handled in _handle_callback_query (dispatched from
            # handle_update before this code path is reached).

            if pending_raw and is_bot_confirmation(text):
                # User confirmed via text (legacy support)
                pending_text = (
                    pending_raw.decode()
                    if isinstance(pending_raw, bytes)
                    else pending_raw
                )
                try:
                    pending_info = json.loads(pending_text)
                except (TypeError, ValueError):
                    pending_info = None
                if isinstance(pending_info, dict) and pending_info.get("text"):
                    if pending_info.get("user_id") != user_id:
                        return
                    text = str(pending_info["text"])
                    callback_request_id = str(
                        pending_info.get("request_id") or ""
                    )
                    if callback_request_id:
                        await redis.connection.delete(
                            self._callback_key(session_id, callback_request_id)
                        )
                else:
                    text = pending_text
                await redis.connection.delete(pending_key)
                logger.info(
                    "Safeguard: Telegram user confirmed pending action for %s.",
                    session_id,
                )
                confirmed = True
            elif safeguard:
                sg_result = await safeguard.check(
                    text,
                    agent_id="telegram",
                    session_id=session_id,
                )
                if sg_result.requires_confirmation:
                    request_id = await self._create_confirmation(
                        session_id,
                        user_id,
                        "message",
                        text,
                    )
                    await redis.connection.set(
                        pending_key,
                        json.dumps(
                            {
                                "text": text,
                                "request_id": request_id,
                                "user_id": user_id,
                            },
                            ensure_ascii=False,
                        ),
                        ex=_CALLBACK_TTL,
                    )
                    import html

                    category = html.escape(str(sg_result.category.value))
                    rationale = html.escape(str(sg_result.rationale))
                    await self._send_with_keyboard(
                        token,
                        chat_id,
                        _t(
                            f"⚠️ <b>Bestätigung erforderlich</b>\n\n"
                            f"<b>Kategorie:</b> {category}\n"
                            f"<b>Begründung:</b> {rationale}\n\n"
                            f"Möchtest du fortfahren?",
                            f"⚠️ <b>Confirmation required</b>\n\n"
                            f"<b>Category:</b> {category}\n"
                            f"<b>Reason:</b> {rationale}\n\n"
                            f"Do you want to continue?",
                            fr=f"⚠️ <b>Confirmation requise</b>\n\n<b>Catégorie:</b> {category}\n<b>Raison:</b> {rationale}\n\nVoulez-vous continuer?",
                            es=f"⚠️ <b>Confirmación requerida</b>\n\n<b>Categoría:</b> {category}\n<b>Razón:</b> {rationale}\n\n¿Quieres continuar?",
                            it=f"⚠️ <b>Conferma richiesta</b>\n\n<b>Categoria:</b> {category}\n<b>Motivo:</b> {rationale}\n\nVuoi continuare?",
                            nl=f"⚠️ <b>Bevestiging vereist</b>\n\n<b>Categorie:</b> {category}\n<b>Reden:</b> {rationale}\n\nWil je doorgaan?",
                            pl=f"⚠️ <b>Wymagane potwierdzenie</b>\n\n<b>Kategoria:</b> {category}\n<b>Powód:</b> {rationale}\n\nCzy chcesz kontynuować?",
                            pt=f"⚠️ <b>Confirmação necessária</b>\n\n<b>Categoria:</b> {category}\n<b>Motivo:</b> {rationale}\n\nQuer continuar?",
                            ja=f"⚠️ <b>確認が必要</b>\n\n<b>カテゴリ:</b> {category}\n<b>理由:</b> {rationale}\n\n続行しますか？",
                            zh=f"⚠️ <b>需要确认</b>\n\n<b>类别:</b> {category}\n<b>原因:</b> {rationale}\n\n是否继续？",
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
                                    "callback_data": f"confirm_yes:{request_id}",
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
                                    "callback_data": f"confirm_no:{request_id}",
                                },
                            ]
                        ],
                    )
                    return

            history = await redis.get_chat_history(session_id)
            streaming_enabled = str(config.get("streaming", "false")).lower() in (
                "true",
                "1",
                "yes",
            )
            if streaming_enabled:
                logger.debug("Telegram streaming preview enabled for chat %s.", chat_id)

            # Chat-ID + detected language as context hint
            lang_hint = ""
            if (
                os.getenv("WHISPER_LANGUAGE", "de") == "auto"
                and detected_lang
                and detected_lang != "de"
            ):
                lang_hint = f"[Erkannte Sprache: {detected_lang}] "
            contextualized_text = f"[Telegram Chat-ID: {chat_id}]\n{lang_hint}{text}"

            preview_msg_id: int | None = None
            if streaming_enabled and not is_voice:
                (
                    response_text,
                    module_used,
                    did_compact,
                    route_meta,
                    preview_msg_id,
                ) = await self._route_with_live_preview(
                    orchestrator=orchestrator,
                    token=token,
                    chat_id=chat_id,
                    message_id=message_id,
                    contextualized_text=contextualized_text,
                    history=history,
                    session_id=session_id,
                    confirmed=confirmed,
                )
            else:
                response_text, module_used, did_compact, route_meta = await orchestrator.route(
                    message=contextualized_text,
                    chat_history=history,
                    session_id=session_id,
                    confirmed=confirmed,
                )

            if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
                await self._delete_message(token, chat_id, preview_msg_id)
                info = json.loads(response_text[len(_TOOL_SAFEGUARD_SENTINEL) :])
                await self._send_tool_confirmation(
                    token,
                    chat_id,
                    session_id,
                    user_id,
                    info,
                )
                return

            # Save history only if no /clear happened after this request started.
            if self._session_generations.get(session_id, 0) != request_generation:
                logger.info(
                    "History save for %s skipped (session was cleared).", session_id
                )
            else:
                if did_compact:
                    summary = (route_meta or {}).get("compaction_summary")
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content=summary or "Conversation history has been compressed.",
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

            # ── Voice-Reply according to connection settings ─────────────────
            if is_voice:
                if voice_reply:
                    await self._send_voice_reply(
                        token,
                        chat_id,
                        response_text,
                        lang=voice_lang,
                        voice=voice_name,
                    )
                if voice_reply_text_too or not voice_reply:
                    await self._send_formatted_chunks(
                        token,
                        chat_id,
                        _clean_final_response(response_text),
                        reply_to_message_id=message_id,
                    )
                return

            # ── Telegram module already sent directly → don't send again ───────
            # The Telegram agent is now a transparent transport: it may either
            # call send_telegram_message (then message is already delivered and
            # we suppress) or call delegate_to_orchestrator and return the
            # delegated answer verbatim (then we MUST forward it normally).
            # Heuristic: only suppress if the response is purely a send-
            # confirmation marker. Errors are always forwarded.
            if module_used == "telegram":
                lower = response_text.strip().lower()
                is_error = any(
                    lower.startswith(p) for p in ("fehler", "error", "❌")
                )
                # Send-confirmation strings produced by send_telegram_message
                send_confirm_markers = (
                    "telegram-nachricht erfolgreich gesendet",
                    "telegram-nachricht gesendet",
                    "telegram message sent successfully",
                    "telegram message sent",
                )
                is_send_confirm = (
                    not is_error
                    and len(response_text) < 300
                    and any(m in lower for m in send_confirm_markers)
                )
                if is_send_confirm:
                    logger.debug(
                        "Telegram module sent directly for chat %s — suppressing duplicate.",
                        chat_id,
                    )
                    return

            # ── Text response (for text inputs only) ──────────────────────────
            final_text = _clean_final_response(response_text)

            # ── Image generation: detect marker, URL, or phrase ────────────
            image_path = None
            data_url = None
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
            if image_path is None:
                # 3. data URL (data:image/...;base64,...) from DataViz
                dm = re.search(
                    r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)",
                    response_text,
                )
                if dm:
                    data_url = dm
            if image_path is None and data_url is None and re.search(
                r"[Bb]ild\s+(?:erfolgreich\s+)?generiert|[Bb]ild\s+erstellt|generate_image",
                response_text,
                re.IGNORECASE,
            ):
                # 3. Tool was called but LLM omitted URL → use most recent image
                #    IMPORTANT: use response_text (raw) not final_text (filtered)
                try:
                    imgs = sorted(
                        (
                            image
                            for img_dir in _telegram_image_roots()
                            if img_dir.exists()
                            for image in img_dir.glob("*.png")
                        ),
                        key=lambda path: path.stat().st_mtime,
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
                except _RECOVERABLE_ERRORS as e:
                    logger.debug("Error searching for newest image: %s", e)

            if image_path:
                # Text without markers/URL for caption
                caption = re.sub(
                    r"\[(?:NINKO_IMAGE|KUMIO_IMAGE):[^\]]+\]\s*\n?", "", final_text
                ).strip()
                caption = re.sub(r"/api/images/[\w\-]+\.\w+\s*\n?", "", caption).strip()
                caption = format_for_telegram(caption)[:1024]  # Telegram caption limit
                sent = await self._send_photo(token, chat_id, image_path, caption)
                if not sent:
                    logger.warning("Image send failed, falling back to text.")
                    await self._send_formatted_chunks(
                        token,
                        chat_id,
                        final_text,
                        reply_to_message_id=message_id,
                    )
                return
            if data_url:
                caption = re.sub(
                    r"data:image/(?:png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+",
                    "",
                    final_text,
                ).strip()
                caption = format_for_telegram(caption)[:1024]
                try:
                    img_bytes = base64.b64decode(data_url.group(2))
                    mime = f"image/{data_url.group(1)}".replace("jpg", "jpeg")
                    sent = await self._send_photo_bytes(
                        token, chat_id, img_bytes, mime, caption
                    )
                    if not sent:
                        await self._send_formatted_chunks(
                            token,
                            chat_id,
                            final_text,
                            reply_to_message_id=message_id,
                        )
                except Exception as exc:
                    logger.warning("Data URL image send failed: %s", exc)
                    await self._send_formatted_chunks(
                        token,
                        chat_id,
                        final_text,
                        reply_to_message_id=message_id,
                    )
                return

            await self._send_formatted_chunks(
                token,
                chat_id,
                final_text,
                reply_to_message_id=message_id,
                preview_message_id=preview_msg_id,
            )

        except Exception as exc:
            logger.exception("Error in Telegram orchestrator processing: %s", exc)
            await self._send(
                token,
                chat_id,
                _telegram_error_message(exc),
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
                await self._send_formatted_chunks(token, chat_id, text)
                return

            if not is_tts_available():
                logger.warning("Voice-Reply: TTS not available, sending text fallback.")
                await self._send_formatted_chunks(token, chat_id, text)
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
        except _RECOVERABLE_ERRORS as exc:
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
