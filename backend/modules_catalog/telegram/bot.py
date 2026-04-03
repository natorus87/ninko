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
    text = re.sub(r"\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?", "", text)
    text = re.sub(r"(?:Telegram\s+)?Chat-?ID[:\s]+\d+", "", text)

    # Remove "via module" footer
    text = re.sub(r"\n\n_via [^_\n]+_\s*$", "", text)

    # HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Markdown formatting
    text = re.sub(r"```[\s\S]*?```", "", text)          # Code blocks
    text = re.sub(r"`([^`]+)`", r"\1", text)             # Inline code
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text) # Bold/Italic
    text = re.sub(r"_([^_\n]+)_", r"\1", text)           # Underscore italic
    text = re.sub(r"~~([^~]+)~~", r"\1", text)           # Strikethrough
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # Headings
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # Links

    # Remove emojis
    text = re.sub(
        "["
        "\U0001F300-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002600-\U000027BF"
        "\U0001F1E0-\U0001F1FF"
        "\u2000-\u206F"
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
    text = re.sub(r'\*\*Schritt\s+\d+\s*[–-]\s*\w+:\*\*\s*\n?', '', text)
    # Step 1 – module: (plain)
    text = re.sub(r'(?m)^Schritt\s+\d+\s*[–-]\s*\w+:\s*\n?', '', text)
    # Telegram send confirmation (sent separately by the Telegram module)
    text = re.sub(r'✅\s*Telegram-?\s*Nachricht\s+.*?(?:gesendet|erfolgreich)[^\n]*\n?', '', text, flags=re.IGNORECASE)
    # Normalize multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class TelegramBot:
    def __init__(self, app: FastAPI):
        self.app = app
        self.running = False
        self.task: asyncio.Task | None = None
        self.offset = 0
        # Tracks sessions that were cleared while a request was in flight
        self._cleared_sessions: set[str] = set()

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

    async def start(self) -> None:
        """Start the polling loop as a background task."""
        if self.running:
            return

        token = await self.get_token()
        if not token:
            logger.warning("Telegram bot token missing. Polling start aborted.")
            return

        self.running = True
        self.task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram bot polling started.")

    async def stop(self) -> None:
        """Stop the polling loop."""
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
        logger.info("Telegram bot polling stopped.")

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
                        "allowed_updates": ["message"],
                    }

                    resp = await poll_client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            updates = data.get("result", [])
                            for update in updates:
                                self.offset = update["update_id"] + 1
                                # Process each update as an independent task
                                asyncio.create_task(
                                    self.handle_update(update, token)
                                )
                        else:
                            logger.error("Telegram API Error: %s", data.get("description"))
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
            except Exception as e:
                logger.exception("Error in Telegram polling loop: %s", e)
                await asyncio.sleep(10)

    async def _send(
        self,
        token: str,
        chat_id: int,
        text: str,
        parse_mode: str = "",
    ) -> bool:
        """
        Send a message. Tries parse_mode first, falls back to plain text on error.
        Returns True on success.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

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
                    resp2 = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=plain_payload,
                    )
                    return resp2.status_code == 200 and resp2.json().get("ok")

                logger.warning("sendMessage error: %s %s", resp.status_code, resp.text[:100])
                return False
        except Exception as exc:
            logger.error("_send error: %s", exc)
            return False

    async def _react(self, token: str, chat_id: int, message_id: int, emoji: str = "👍") -> None:
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
        except Exception:
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
                    except Exception:
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
            text, confidence, detected_lang = await transcribe_bytes_extended(audio_bytes, filename)
            return (text or None), confidence, detected_lang
        except Exception as exc:
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
        except Exception as exc:
            logger.error("_send_voice error: %s", exc)
            return False

    async def _send_photo(self, token: str, chat_id: int, image_path: str, caption: str = "") -> bool:
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
                logger.warning("Image file not found: %s (tried: %s)", filename, [str(c) for c in candidates])
                return False

            image_bytes = img_file.read_bytes()
            ext = img_file.suffix.lower()
            mime_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
            mime = mime_types.get(ext, "image/png")

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"},
                    files={"photo": (img_file.name, image_bytes, mime)},
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.warning("sendPhoto Fehler: %s %s", resp.status_code, resp.text[:200])
                return False
        except Exception as exc:
            logger.error("_send_photo error: %s", exc)
            return False

    async def handle_update(self, update: dict[str, Any], token: str) -> None:
        """Process a single Telegram update."""
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
                text, confidence, detected_lang = await self._transcribe_voice(file_id, token)
                if not text:
                    await self._send(token, chat_id, "❌ Transcription failed. Please send as text.")
                    return
                # Confidence check
                import core.config as _cfg_mod
                _cfg = _cfg_mod.get_settings()
                if confidence < _cfg.STT_CONFIDENCE_THRESHOLD:
                    low_confidence = True
                    logger.info(
                        "STT Konfidenz niedrig (%.2f < %.2f): '%s'",
                        confidence, _cfg.STT_CONFIDENCE_THRESHOLD, text[:60],
                    )

        if not chat_id or not text:
            return

        # Allowlist check: only permit allowed chat IDs
        from core.connections import ConnectionManager
        conn = await ConnectionManager.get_default_connection("telegram")
        if conn:
            allowed_raw = conn.config.get("allowed_chat_ids", "")
            if allowed_raw:
                allowed_ids = {s.strip() for s in str(allowed_raw).split(",") if s.strip()}
                if str(chat_id) not in allowed_ids:
                    logger.warning(
                        "Telegram: Access denied for chat ID %s (not in allowlist)", chat_id
                    )
                    return

        # Read voice-reply configuration from connection
        voice_reply = False
        voice_reply_text_too = False
        voice_lang: str | None = None
        voice_name: str | None = None
        if conn:
            voice_reply = str(conn.config.get("voice_reply", "false")).lower() in ("true", "1", "yes")
            voice_reply_text_too = str(conn.config.get("voice_reply_text_too", "false")).lower() in ("true", "1", "yes")
            voice_lang = conn.config.get("voice_lang") or None
            voice_name = conn.config.get("voice_name") or None

        logger.info("Telegram message from chat %s: %s…", chat_id, text[:60])

        # Intercept commands without orchestrator
        cmd = text.strip().lower().split("@")[0]  # /clear@botname → /clear

        if cmd == "/chatid":
            await self._send(token, chat_id, f"🆔 Deine Telegram Chat-ID: <code>{chat_id}</code>", parse_mode="HTML")
            return

        if cmd in ("/start", "/clear", "/reset"):
            session_id_local = f"telegram_{chat_id}"
            try:
                redis = get_redis()
                await redis.clear_chat_history(session_id_local)
                # Race-condition protection: in-flight requests should not write back history
                self._cleared_sessions.add(session_id_local)
                await self._send(token, chat_id, "♻️ Chat history cleared. How can I help?")
            except Exception as exc:
                logger.error("Error clearing chat history for %s: %s", chat_id, exc)
                await self._send(token, chat_id, f"❌ Error clearing history: {exc}")
            return

        # ── Low confidence: ask for confirmation instead of processing ─────────
        if low_confidence:
            await self._send(
                token, chat_id,
                _t(
                    f'🎙️ Ich habe verstanden:\n<i>"{text}"</i>\n\nIst das korrekt? (Antworte mit Ja oder schicke den Text nochmal.)',
                    f'🎙️ I understood:\n<i>"{text}"</i>\n\nIs this correct? (Reply with yes or send the text again.)',
                ),
                parse_mode="HTML",
            )
            return

        # ── React to the message + silent typing indicator ────────────────────
        if message_id:
            await self._react(token, chat_id, message_id, "⚡")
        typing_task = asyncio.create_task(self._keep_typing(token, chat_id))

        try:
            from core.safeguard import is_bot_confirmation, SAFEGUARD_PENDING_KEY

            orchestrator = self.app.state.orchestrator
            redis = get_redis()
            session_id = f"telegram_{chat_id}"

            # ── Safeguard check ────────────────────────────────────────────────
            safeguard = getattr(self.app.state, "safeguard", None)
            pending_key = SAFEGUARD_PENDING_KEY.format(session_id=session_id)
            pending_raw = await redis.connection.get(pending_key)

            if pending_raw and is_bot_confirmation(text):
                # User confirmed — execute the stored action
                text = pending_raw.decode() if isinstance(pending_raw, bytes) else pending_raw
                await redis.connection.delete(pending_key)
                logger.info("Safeguard: Telegram user confirmed pending action for %s.", session_id)
            elif safeguard:
                sg_result = await safeguard.check(text)
                if sg_result.requires_confirmation:
                    await redis.connection.set(pending_key, text, ex=300)
                    await self._send(
                        token, chat_id,
                        _t(
                            f"⚠️ <b>Bestätigung erforderlich</b>\n\n"
                            f"<b>Kategorie:</b> {sg_result.category.value}\n"
                            f"<b>Begründung:</b> {sg_result.rationale}\n\n"
                            f"Antworte mit <b>ja</b> um fortzufahren, oder schicke eine andere Nachricht um abzubrechen.",
                            f"⚠️ <b>Confirmation required</b>\n\n"
                            f"<b>Category:</b> {sg_result.category.value}\n"
                            f"<b>Reason:</b> {sg_result.rationale}\n\n"
                            f"Reply with <b>yes</b> to continue, or send another message to cancel.",
                        ),
                        parse_mode="HTML",
                    )
                    return

            history = await redis.get_chat_history(session_id)

            # Chat-ID + detected language as context hint
            lang_hint = ""
            if os.getenv("WHISPER_LANGUAGE", "de") == "auto" and detected_lang and detected_lang != "de":
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
                logger.info("History save for %s skipped (session was cleared).", session_id)
            else:
                if did_compact:
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content="Conversation history has been compressed.",
                    )
                await redis.store_chat_message(session_id=session_id, role="user", content=text)
                await redis.store_chat_message(session_id=session_id, role="assistant", content=response_text)

            # ── Context compression: inform user ──────────────────────────────
            if did_compact:
                await self._send(
                    token, chat_id,
                    "🗜️ <i>Conversation history has been compressed — older details have been summarized.</i>",
                    parse_mode="HTML",
                )

            # ── Voice-Reply: always voice for voice inputs, no text ────────────
            if is_voice:
                await self._send_voice_reply(token, chat_id, response_text,
                                             lang=voice_lang, voice=voice_name)
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
            # 1. [KUMIO_IMAGE:url] marker
            m = re.search(r'\[KUMIO_IMAGE:(/api/images/[^\]]+)\]', final_text)
            if not m:
                # 2. /api/images/ URL irgendwo im Text
                m = re.search(r'(/api/images/[\w\-]+\.\w+)', final_text)
            if m:
                image_path = m.group(1)
                logger.info("Image path detected in text: %s", image_path)
            elif re.search(r'[Bb]ild\s+(?:erfolgreich\s+)?generiert|[Bb]ild\s+erstellt|generate_image', response_text, re.IGNORECASE):
                # 3. Tool was called but LLM omitted URL → use most recent image
                #    IMPORTANT: use response_text (raw) not final_text (filtered)
                try:
                    from pathlib import Path
                    img_dir = Path("/app/data/images")
                    if img_dir.exists():
                        imgs = sorted(img_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                        if imgs:
                            age_seconds = __import__("time").time() - imgs[0].stat().st_mtime
                            if age_seconds < 300:  # Only images less than 5 minutes old
                                image_path = f"/api/images/{imgs[0].name}"
                                logger.info("Image URL missing in response, using newest image (%ds old): %s", age_seconds, image_path)
                except Exception as e:
                    logger.debug("Error searching for newest image: %s", e)

            if image_path:
                # Text without markers/URL for caption
                caption = re.sub(r'\[KUMIO_IMAGE:[^\]]+\]\s*\n?', '', final_text).strip()
                caption = re.sub(r'/api/images/[\w\-]+\.\w+\s*\n?', '', caption).strip()
                caption = format_for_telegram(caption)[:1024]  # Telegram caption limit
                try:
                    await self._send_photo(token, chat_id, image_path, caption)
                except Exception as img_err:
                    logger.warning("Image send failed, falling back to text: %s", img_err)
                    fallback = format_for_telegram(final_text)
                    await self._send(token, chat_id, fallback, parse_mode="HTML")
                return

            final_text = format_for_telegram(final_text)

            # Send response in chunks (Telegram limit: 4096 characters)
            chunks = [final_text[i : i + _MAX_MSG_LEN] for i in range(0, len(final_text), _MAX_MSG_LEN)]
            for chunk in chunks:
                await self._send(token, chat_id, chunk, parse_mode="HTML")

        except Exception as exc:
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
            )
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def _send_voice_reply(
        self, token: str, chat_id: int, text: str,
        lang: str | None = None, voice: str | None = None,
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
                logger.warning("Voice-Reply: cleaned text empty, sending text fallback.")
                await self._send(token, chat_id, text)
                return

            if not is_tts_available():
                logger.warning("Voice-Reply: TTS not available, sending text fallback.")
                await self._send(token, chat_id, format_for_telegram(text), parse_mode="HTML")
                return

            wav_bytes = await synthesize_reply(clean_text, lang=lang, voice=voice)
            ogg_bytes = await wav_to_ogg(wav_bytes)
            ok = await self._send_voice(token, chat_id, ogg_bytes)
            if ok:
                logger.info(
                    "Voice-Reply sent to chat %s: %d KB OGG", chat_id, len(ogg_bytes) // 1024
                )
            else:
                logger.warning("Voice-Reply sendVoice failed for chat %s", chat_id)
        except Exception as exc:
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
