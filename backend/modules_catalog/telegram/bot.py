"""
Telegram Long-Polling-Bot für Ninko.
Verbindet sich mit der Telegram API, empfängt Nachrichten und leitet sie an den Orchestrator weiter.

Voice-Reply: Wenn eine eingehende Sprachnachricht erkannt wird und voice_reply in der
Connection-Konfiguration aktiviert ist, antwortet der Bot mit einer Sprachnachricht (OGG/Opus).
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
from .formatter import format_for_telegram


def _clean_for_tts(text: str) -> str:
    """Bereinigt Text vor der TTS-Synthese: entfernt Emojis, Markdown, Tabellen, HTML."""
    # Tabellenzeilen entfernen (Zeilen mit ≥ 2 Pipes)
    lines = [ln for ln in text.split("\n") if ln.count("|") < 2]
    text = "\n".join(lines)

    # Kontext-Präfixe und Chat-ID-Referenzen entfernen
    text = re.sub(r"\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?", "", text)
    text = re.sub(r"(?:Telegram\s+)?Chat-?ID[:\s]+\d+", "", text)

    # "via modul"-Fußzeile entfernen
    text = re.sub(r"\n\n_via [^_\n]+_\s*$", "", text)

    # HTML-Tags
    text = re.sub(r"<[^>]+>", "", text)

    # Markdown-Formatierung
    text = re.sub(r"```[\s\S]*?```", "", text)          # Code-Blöcke
    text = re.sub(r"`([^`]+)`", r"\1", text)             # Inline-Code
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text) # Bold/Italic
    text = re.sub(r"_([^_\n]+)_", r"\1", text)           # Kursiv Underscore
    text = re.sub(r"~~([^~]+)~~", r"\1", text)           # Durchgestrichen
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # Überschriften
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # Links

    # Emojis entfernen
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

    # Whitespace normalisieren
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

logger = logging.getLogger("ninko.modules.telegram.bot")

# Maximale Nachrichtenlänge (Telegram-Limit: 4096)
_MAX_MSG_LEN = 4000


def _strip_pipeline_headers(text: str) -> str:
    """Entfernt 'Schritt N – modul:' Header und Telegram-Send-Bestätigungen aus Pipeline-Antworten."""
    # **Schritt 1 – modul:** (Markdown bold)
    text = re.sub(r'\*\*Schritt\s+\d+\s*[–-]\s*\w+:\*\*\s*\n?', '', text)
    # Schritt 1 – modul: (plain)
    text = re.sub(r'(?m)^Schritt\s+\d+\s*[–-]\s*\w+:\s*\n?', '', text)
    # Telegram-Send-Bestätigung (wird vom Telegram-Modul separat gesendet)
    text = re.sub(r'✅\s*Telegram-?\s*Nachricht\s+.*?(?:gesendet|erfolgreich)[^\n]*\n?', '', text, flags=re.IGNORECASE)
    # Mehrfache Leerzeilen normalisieren
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
        """Lädt das aktuelle Telegram Bot Token aus dem ConnectionManager."""
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
        """Startet die Polling-Schleife als Background-Task."""
        if self.running:
            return

        token = await self.get_token()
        if not token:
            logger.warning("Telegram Bot Token fehlt. Polling-Start abgebrochen.")
            return

        self.running = True
        self.task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram Bot Polling gestartet.")

    async def stop(self) -> None:
        """Stoppt die Polling-Schleife."""
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
        logger.info("Telegram Bot Polling gestoppt.")

    async def _poll_loop(self) -> None:
        """Hauptschleife für Long-Polling."""
        timeout_s = 30

        while self.running:
            token = await self.get_token()
            if not token:
                logger.error("Telegram Token während Polling verloren.")
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
                                # Jedes Update als unabhängigen Task verarbeiten
                                asyncio.create_task(
                                    self.handle_update(update, token)
                                )
                        else:
                            logger.error("Telegram API Error: %s", data.get("description"))
                            await asyncio.sleep(5)
                    elif resp.status_code == 401:
                        logger.error("Telegram Unauthorized. Stoppe Polling.")
                        self.running = False
                        break
                    else:
                        logger.warning("Telegram HTTP Error: %s", resp.status_code)
                        await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                continue  # Normal bei Long-Polling ohne neue Nachrichten
            except Exception as e:
                logger.exception("Fehler in Telegram Polling-Loop: %s", e)
                await asyncio.sleep(10)

    async def _send(
        self,
        token: str,
        chat_id: int,
        text: str,
        parse_mode: str = "",
    ) -> bool:
        """
        Sendet eine Nachricht. Versucht zuerst mit parse_mode, fällt bei Fehler auf
        plain text zurück. Gibt True zurück wenn erfolgreich.
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

                # Markdown-Parse-Fehler → Fallback auf plain text
                if parse_mode and resp.status_code == 400:
                    logger.debug("Markdown-Parsing fehlgeschlagen, sende plain text.")
                    plain_payload = {"chat_id": chat_id, "text": text}
                    resp2 = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=plain_payload,
                    )
                    return resp2.status_code == 200 and resp2.json().get("ok")

                logger.warning("sendMessage Fehler: %s %s", resp.status_code, resp.text[:100])
                return False
        except Exception as exc:
            logger.error("_send Fehler: %s", exc)
            return False

    async def _react(self, token: str, chat_id: int, message_id: int, emoji: str = "👍") -> None:
        """Setzt eine Emoji-Reaktion auf eine Nachricht (Best-Effort, kein Fehler nach oben)."""
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
        """Sendet alle 4s eine 'typing'-Aktion bis der Task gecancelt wird."""
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
        Lädt eine Telegram-Voice-Datei herunter und transkribiert sie.

        Returns:
            (text, avg_confidence, detected_language)
            text ist None bei Fehler.
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
            logger.error("Fehler beim Transkribieren der Telegram-Voice-Nachricht: %s", exc)
            return None, -2.0, "de"

    async def _send_voice(self, token: str, chat_id: int, ogg_bytes: bytes) -> bool:
        """
        Sendet eine Sprachnachricht via Telegram sendVoice API.
        Erwartet OGG/Opus-Bytes (Telegram-Anforderung für Voice-Messages).
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
            logger.error("_send_voice Fehler: %s", exc)
            return False

    async def _send_photo(self, token: str, chat_id: int, image_path: str, caption: str = "") -> bool:
        """
        Sendet ein generiertes Bild als Foto via Telegram sendPhoto API.
        Lädt das Bild lokal und sendet es als multipart/form-data.
        """
        try:
            from pathlib import Path
            # URL-Pfad → Dateisystem-Pfad: /api/images/xxx.png → /app/data/images/xxx.png
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
                logger.warning("Bild-Datei nicht gefunden: %s (versucht: %s)", filename, [str(c) for c in candidates])
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
            logger.error("_send_photo Fehler: %s", exc)
            return False

    async def handle_update(self, update: dict[str, Any], token: str) -> None:
        """Verarbeitet ein einzelnes Telegram-Update."""
        msg = update.get("message")
        if not msg:
            return

        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")
        text = msg.get("text")
        is_voice = False
        detected_lang: str = os.getenv("WHISPER_LANGUAGE", "de")
        low_confidence = False

        # Voice-Nachrichten transkribieren (kein Status-Text, nur stiller Typing-Indikator)
        voice = msg.get("voice") or msg.get("audio")
        if not text and voice:
            file_id = voice.get("file_id")
            if file_id:
                is_voice = True
                text, confidence, detected_lang = await self._transcribe_voice(file_id, token)
                if not text:
                    await self._send(token, chat_id, "❌ Transkription fehlgeschlagen. Bitte als Text senden.")
                    return
                # Konfidenz-Check
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

        # Allowlist-Check: nur erlaubte Chat-IDs zulassen
        from core.connections import ConnectionManager
        conn = await ConnectionManager.get_default_connection("telegram")
        if conn:
            allowed_raw = conn.config.get("allowed_chat_ids", "")
            if allowed_raw:
                allowed_ids = {s.strip() for s in str(allowed_raw).split(",") if s.strip()}
                if str(chat_id) not in allowed_ids:
                    logger.warning(
                        "Telegram: Zugriff verweigert für Chat-ID %s (nicht in Allowlist)", chat_id
                    )
                    return

        # Voice-Reply-Konfiguration aus Connection lesen
        voice_reply = False
        voice_reply_text_too = False
        voice_lang: str | None = None
        voice_name: str | None = None
        if conn:
            voice_reply = str(conn.config.get("voice_reply", "false")).lower() in ("true", "1", "yes")
            voice_reply_text_too = str(conn.config.get("voice_reply_text_too", "false")).lower() in ("true", "1", "yes")
            voice_lang = conn.config.get("voice_lang") or None
            voice_name = conn.config.get("voice_name") or None

        logger.info("Telegram Nachricht von Chat %s: %s…", chat_id, text[:60])

        # Befehle ohne Orchestrator abfangen
        cmd = text.strip().lower().split("@")[0]  # /clear@botname → /clear

        if cmd == "/chatid":
            await self._send(token, chat_id, f"🆔 Deine Telegram Chat-ID: <code>{chat_id}</code>", parse_mode="HTML")
            return

        if cmd in ("/start", "/clear", "/reset"):
            session_id_local = f"telegram_{chat_id}"
            try:
                redis = get_redis()
                await redis.clear_chat_history(session_id_local)
                # Race-condition-Schutz: in-flight Requests sollen History nicht zurückschreiben
                self._cleared_sessions.add(session_id_local)
                await self._send(token, chat_id, "♻️ Chat-Verlauf geleert. Wie kann ich helfen?")
            except Exception as exc:
                logger.error("Fehler beim Löschen der Chat-History für %s: %s", chat_id, exc)
                await self._send(token, chat_id, f"❌ Fehler beim Löschen des Verlaufs: {exc}")
            return

        # ── Bei niedriger Konfidenz: Rückfrage statt Verarbeitung ─────────────
        if low_confidence:
            await self._send(
                token, chat_id,
                f'🎙️ Ich habe verstanden:\n<i>"{text}"</i>\n\nIst das korrekt? (Antworte mit Ja oder schicke den Text nochmal.)',
                parse_mode="HTML",
            )
            return

        # ── Reaktion auf die Nachricht + stiller Typing-Indikator ─────────────
        if message_id:
            await self._react(token, chat_id, message_id, "⚡")
        typing_task = asyncio.create_task(self._keep_typing(token, chat_id))

        try:
            from core.safeguard import is_bot_confirmation, SAFEGUARD_PENDING_KEY

            orchestrator = self.app.state.orchestrator
            redis = get_redis()
            session_id = f"telegram_{chat_id}"

            # ── Safeguard-Check ────────────────────────────────────────────────
            safeguard = getattr(self.app.state, "safeguard", None)
            pending_key = SAFEGUARD_PENDING_KEY.format(session_id=session_id)
            pending_raw = await redis.connection.get(pending_key)

            if pending_raw and is_bot_confirmation(text):
                # User hat bestätigt — gespeicherte Aktion ausführen
                text = pending_raw.decode() if isinstance(pending_raw, bytes) else pending_raw
                await redis.connection.delete(pending_key)
                logger.info("Safeguard: Telegram-User bestätigte pending Aktion für %s.", session_id)
            elif safeguard:
                sg_result = await safeguard.check(text)
                if sg_result.requires_confirmation:
                    await redis.connection.set(pending_key, text, ex=300)
                    await self._send(
                        token, chat_id,
                        f"⚠️ <b>Bestätigung erforderlich</b>\n\n"
                        f"<b>Kategorie:</b> {sg_result.category.value}\n"
                        f"<b>Begründung:</b> {sg_result.rationale}\n\n"
                        f"Antworte mit <b>ja</b> um fortzufahren, oder schicke eine andere Nachricht um abzubrechen.",
                        parse_mode="HTML",
                    )
                    return

            history = await redis.get_chat_history(session_id)

            # Chat-ID + ggf. erkannte Sprache als Kontext mitgeben
            lang_hint = ""
            if os.getenv("WHISPER_LANGUAGE", "de") == "auto" and detected_lang and detected_lang != "de":
                lang_hint = f"[Erkannte Sprache: {detected_lang}] "
            contextualized_text = f"[Telegram Chat-ID: {chat_id}]\n{lang_hint}{text}"

            response_text, module_used, did_compact = await orchestrator.route(
                message=contextualized_text,
                chat_history=history,
                session_id=session_id,
            )

            # History speichern – überspringen wenn Session inzwischen geclearet wurde
            if session_id in self._cleared_sessions:
                self._cleared_sessions.discard(session_id)
                logger.info("History-Speicherung für %s übersprungen (Session wurde geclearet).", session_id)
            else:
                if did_compact:
                    await redis.store_chat_message(
                        session_id=session_id,
                        role="system_compaction",
                        content="Der Gesprächsverlauf wurde komprimiert.",
                    )
                await redis.store_chat_message(session_id=session_id, role="user", content=text)
                await redis.store_chat_message(session_id=session_id, role="assistant", content=response_text)

            # ── Kontext-Komprimierung: User informieren ────────────────────────
            if did_compact:
                await self._send(
                    token, chat_id,
                    "🗜️ <i>Gesprächsverlauf wurde komprimiert – ältere Details wurden zusammengefasst.</i>",
                    parse_mode="HTML",
                )

            # ── Voice-Reply: bei Sprachnachricht immer Voice, kein Text ───────
            if is_voice:
                await self._send_voice_reply(token, chat_id, response_text,
                                             lang=voice_lang, voice=voice_name)
                return

            # ── Telegram-Modul hat bereits direkt gesendet → nicht nochmal senden ──
            # Das Modul ruft send_telegram_message auf → Nachricht bereits zugestellt.
            # Ausnahme: Fehlermeldungen immer zurücksenden.
            if module_used == "telegram" and not any(
                response_text.lower().startswith(p) for p in ("fehler", "error")
            ):
                logger.debug(
                    "Telegram-Modul hat bereits gesendet für Chat %s – Bot-Antwort unterdrückt.",
                    chat_id,
                )
                return

            # ── Text-Antwort (nur für Text-Eingaben) ───────────────────────────
            final_text = _strip_pipeline_headers(response_text)
            if module_used:
                final_text += f"\n\n_via {module_used}_"

            # ── Bild-Generierung: Marker, URL, oder Phrase erkennen ────────
            image_path = None
            # 1. [KUMIO_IMAGE:url] Marker
            m = re.search(r'\[KUMIO_IMAGE:(/api/images/[^\]]+)\]', final_text)
            if not m:
                # 2. /api/images/ URL irgendwo im Text
                m = re.search(r'(/api/images/[\w\-]+\.\w+)', final_text)
            if m:
                image_path = m.group(1)
                logger.info("Bild-Pfad erkannt im Text: %s", image_path)
            elif re.search(r'[Bb]ild\s+(?:erfolgreich\s+)?generiert|[Bb]ild\s+erstellt|generate_image', response_text, re.IGNORECASE):
                # 3. Tool wurde aufgerufen aber LLM hat URL weggelassen → neuestes Bild nehmen
                #    WICHTIG: response_text (roh) statt final_text (gefiltert) nutzen
                try:
                    from pathlib import Path
                    img_dir = Path("/app/data/images")
                    if img_dir.exists():
                        imgs = sorted(img_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                        if imgs:
                            age_seconds = __import__("time").time() - imgs[0].stat().st_mtime
                            if age_seconds < 300:  # Nur Bilder < 5 Minuten alt
                                image_path = f"/api/images/{imgs[0].name}"
                                logger.info("Bild-URL fehlt in Response, nutze neuestes Bild (%ds alt): %s", age_seconds, image_path)
                except Exception as e:
                    logger.debug("Fehler beim Suchen des neuesten Bildes: %s", e)

            if image_path:
                # Text ohne Marker/URL für Caption
                caption = re.sub(r'\[KUMIO_IMAGE:[^\]]+\]\s*\n?', '', final_text).strip()
                caption = re.sub(r'/api/images/[\w\-]+\.\w+\s*\n?', '', caption).strip()
                caption = format_for_telegram(caption)[:1024]  # Telegram caption limit
                try:
                    await self._send_photo(token, chat_id, image_path, caption)
                except Exception as img_err:
                    logger.warning("Bild-Sendung fehlgeschlagen, fallback auf Text: %s", img_err)
                    fallback = format_for_telegram(final_text)
                    await self._send(token, chat_id, fallback, parse_mode="HTML")
                return

            final_text = format_for_telegram(final_text)

            # Antwort in Chunks senden (Telegram-Limit 4096 Zeichen)
            chunks = [final_text[i : i + _MAX_MSG_LEN] for i in range(0, len(final_text), _MAX_MSG_LEN)]
            for chunk in chunks:
                await self._send(token, chat_id, chunk, parse_mode="HTML")

        except Exception as exc:
            logger.exception("Fehler bei Telegram-Orchestrator-Verarbeitung: %s", exc)
            # Sprechende Fehlermeldung statt generischem Text
            err_type = type(exc).__name__
            await self._send(
                token,
                chat_id,
                f"❌ Fehler bei der Verarbeitung ({err_type}):\n{str(exc)[:300]}\n\nBitte versuche es erneut.",
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
        Synthetisiert Text mit Piper TTS und sendet ihn als Telegram-Sprachnachricht.
        Konvertiert WAV → OGG/Opus für das Telegram sendVoice API.
        Fehler werden geloggt aber nicht nach oben propagiert (Best-Effort).
        """
        try:
            from core.tts import synthesize_reply, is_tts_available
            from core.tts.audio_utils import wav_to_ogg

            clean_text = _clean_for_tts(text)
            if not clean_text:
                logger.warning("Voice-Reply: bereinigter Text leer, sende Text-Fallback.")
                await self._send(token, chat_id, text)
                return

            if not is_tts_available():
                logger.warning("Voice-Reply: TTS nicht verfügbar, sende Text-Fallback.")
                await self._send(token, chat_id, format_for_telegram(text), parse_mode="HTML")
                return

            wav_bytes = await synthesize_reply(clean_text, lang=lang, voice=voice)
            ogg_bytes = await wav_to_ogg(wav_bytes)
            ok = await self._send_voice(token, chat_id, ogg_bytes)
            if ok:
                logger.info(
                    "Voice-Reply gesendet an Chat %s: %d KB OGG", chat_id, len(ogg_bytes) // 1024
                )
            else:
                logger.warning("Voice-Reply sendVoice fehlgeschlagen für Chat %s", chat_id)
        except Exception as exc:
            logger.error("Voice-Reply Fehler für Chat %s: %s", chat_id, exc)


# ── Globaler Bot-State ────────────────────────────────────────────────────────
_global_bot: TelegramBot | None = None


def get_telegram_bot() -> TelegramBot | None:
    return _global_bot


def init_telegram_bot(app: FastAPI) -> TelegramBot:
    global _global_bot
    if _global_bot is None:
        _global_bot = TelegramBot(app)
    return _global_bot
