"""
Ninko Context Manager – Token-Budget-Verwaltung und automatischer Reset.
Verhindert Context-Overflow und Prompt-Injection-Eskalation.
"""

from __future__ import annotations

import logging
from typing import Any, Tuple

import tiktoken
from langchain_core.messages import HumanMessage

from core.config import get_settings

logger = logging.getLogger("ninko.context")


class ContextManager:
    """
    Verwaltet das Token-Budget für LLM-Aufrufe.
    Kürzt automatisch die Chat-History wenn das Budget überschritten wird.

    Das History-Budget wird gegen das tatsächliche Modell-Kontext-Fenster
    kalibriert: 25% des Fensters für die Chat-History, der Rest für
    System-Prompt, Tool-Calls und Output.
    """

    # Anteil des Kontext-Fensters der der Chat-History zugewiesen wird
    _HISTORY_FRACTION = 0.25

    def __init__(self) -> None:
        self._settings = get_settings()
        self._reset_threshold = self._settings.CONTEXT_RESET_THRESHOLD

        # MAX_CONTEXT_TOKENS aus Config als initiales Limit (wird ggf. nach
        # erster Modell-Abfrage überschrieben via update_from_model_window())
        self._max_tokens = self._settings.MAX_CONTEXT_TOKENS
        self._threshold_tokens = int(self._max_tokens * self._reset_threshold)

        # Fallback-Tokenizer (tiktoken cl100k_base für Approximation)
        try:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._encoder = None
            logger.warning(
                "tiktoken konnte nicht geladen werden – "
                "Fallback auf Zeichen-basierte Schätzung."
            )

        logger.info(
            "Context Manager: max_tokens=%d, reset_threshold=%.0f%% (%d tokens)",
            self._max_tokens,
            self._reset_threshold * 100,
            self._threshold_tokens,
        )

    def update_from_model_window(self, model_context_window: int) -> None:
        """
        Kalibriert das History-Budget anhand des echten Modell-Fensters.
        Wird nach der LM Studio API-Abfrage beim ersten Agent-Aufruf aufgerufen.
        History bekommt _HISTORY_FRACTION des Fensters minus MAX_OUTPUT_TOKENS.
        """
        output_budget = self._settings.MAX_OUTPUT_TOKENS
        available = model_context_window - output_budget
        history_budget = max(4096, int(available * self._HISTORY_FRACTION))

        if history_budget != self._max_tokens:
            self._max_tokens = history_budget
            self._threshold_tokens = int(history_budget * self._reset_threshold)
            logger.info(
                "Context-Window kalibriert: Modell=%d Tokens → "
                "History-Budget=%d Tokens (Threshold=%d, %.0f%%)",
                model_context_window,
                self._max_tokens,
                self._threshold_tokens,
                self._reset_threshold * 100,
            )

    def count_tokens(self, text: str) -> int:
        """Zählt die Tokens eines Textes."""
        if self._encoder:
            return len(self._encoder.encode(text))
        # Fallback: ~4 Zeichen pro Token
        return len(text) // 4

    def count_messages_tokens(self, messages: list[dict]) -> int:
        """Zählt die Gesamttokens einer Nachrichtenliste."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self.count_tokens(content)
            # Overhead pro Nachricht (~4 Tokens für Role etc.)
            total += 4
        return total

    def trim_large_messages(
        self,
        messages: list[dict],
        max_chars: int = 3000,
        keep_recent: int = 4,
    ) -> list[dict]:
        """
        opencode-Prinzip (Pruning):
        Kürzt Inhalte einzelner Nachrichten die zu lang sind,
        aber behält die letzten `keep_recent` Nachrichten vollständig.
        Bewahrt den Gesprächsfluss — nur der Inhalt wird gestutzt,
        nicht die Nachricht selbst entfernt.
        """
        if len(messages) <= keep_recent:
            return messages

        result = []
        cutoff = len(messages) - keep_recent

        for i, msg in enumerate(messages):
            if i >= cutoff:
                # Letzte N Nachrichten immer vollständig behalten
                result.append(msg)
                continue

            content = msg.get("content", "")
            if len(content) > max_chars:
                stub = content[:max_chars]
                removed = len(content) - max_chars
                truncated = {
                    **msg,
                    "content": f"{stub}\n[…{removed} Zeichen gekürzt]",
                }
                result.append(truncated)
                logger.debug(
                    "trim_large_messages: Nachricht %d von %d auf %d Zeichen gestutzt.",
                    i + 1, len(messages), max_chars,
                )
            else:
                result.append(msg)

        return result

    def trim_messages(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> list[dict]:
        """
        Kürzt die Nachrichtenliste wenn das Token-Budget
        den Reset-Threshold überschreitet.

        Behält:
        1. System-Prompt (immer)
        2. Die neuesten Nachrichten die ins Budget passen
        """
        system_tokens = self.count_tokens(system_prompt) + 4
        available_tokens = self._threshold_tokens - system_tokens

        if available_tokens <= 0:
            logger.warning(
                "System-Prompt allein überschreitet das Budget (%d > %d)!",
                system_tokens,
                self._threshold_tokens,
            )
            return messages[-2:] if len(messages) > 2 else messages

        # Von hinten nach vorne Nachrichten aufnehmen
        trimmed: list[dict] = []
        running_total = 0

        for msg in reversed(messages):
            msg_tokens = self.count_tokens(msg.get("content", "")) + 4
            if running_total + msg_tokens > available_tokens:
                break
            trimmed.insert(0, msg)
            running_total += msg_tokens

        if len(trimmed) < len(messages):
            logger.info(
                "Context gekürzt: %d → %d Nachrichten (%d → %d Tokens)",
                len(messages),
                len(trimmed),
                self.count_messages_tokens(messages),
                running_total,
            )

        return trimmed

    def should_reset(self, messages: list[dict]) -> bool:
        """Prüft ob der Context zurückgesetzt werden sollte."""
        total = self.count_messages_tokens(messages)
        return total >= self._threshold_tokens

    async def compact_messages_async(
        self,
        messages: list[dict],
        llm: Any,
        keep_recent: int = 6,
    ) -> Tuple[list[dict], bool]:
        """
        Kontext-Komprimierung (OpenClaw-Prinzip):
        Fasst ältere Nachrichten per LLM zusammen statt sie einfach zu verwerfen.
        Die letzten `keep_recent` Nachrichten bleiben immer vollständig erhalten.

        Gibt (komprimierte_messages, wurde_komprimiert) zurück.
        `wurde_komprimiert` ist True wenn eine echte LLM-Summary erstellt wurde.
        """
        total_tokens = self.count_messages_tokens(messages)

        # Nur komprimieren wenn über Threshold
        if total_tokens < self._threshold_tokens:
            return messages, False

        # Zu wenige Nachrichten – normales Trimming reicht
        if len(messages) < keep_recent + 2:
            return self.trim_messages(messages), False

        # Einzelne zu lange Nachrichten vorher stutzen (opencode Pruning-Prinzip)
        messages = self.trim_large_messages(messages, keep_recent=keep_recent)

        recent = messages[-keep_recent:]
        old = messages[:-keep_recent]

        # Prüfen ob es sich lohnt (mind. 200 Tokens zum Komprimieren)
        old_tokens = self.count_messages_tokens(old)
        if old_tokens < 200:
            return self.trim_messages(messages), False

        try:
            summary_input = "\n".join(
                f"{'User' if m.get('role') == 'user' else 'Assistent'}: {m.get('content', '')[:400]}"
                for m in old
            )
            prompt = (
                "Du fasst einen Gesprächsverlauf zusammen, damit er als kompakter Kontext "
                "für das weitere Gespräch dienen kann.\n\n"
                "Gib eine strukturierte Zusammenfassung in 5-8 Sätzen. Fokussiere dabei auf:\n"
                "1. Was wurde bisher getan und erreicht?\n"
                "2. Woran wird gerade gearbeitet?\n"
                "3. Welche konkreten Werte wurden genannt "
                "(IPs, Hostnamen, IDs, Konfigurationen, Tool-Ergebnisse)?\n"
                "4. Welche Entscheidungen oder Einschränkungen hat der User geäußert?\n"
                "5. Was steht noch aus oder wurde explizit gewünscht?\n\n"
                "Antworte NUR mit der Zusammenfassung, ohne Einleitung oder Kommentar.\n\n"
                f"Gesprächsverlauf:\n{summary_input}"
            )
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            summary_text = (
                result.content.strip()
                if hasattr(result, "content")
                else str(result).strip()
            )

            compacted = [
                {
                    "role": "system",
                    "content": f"[Zusammenfassung früherer Gesprächsverlauf]: {summary_text}",
                },
                *recent,
            ]
            logger.info(
                "Kontext komprimiert: %d → %d Nachrichten (%d → ~%d Tokens)",
                len(messages),
                len(compacted),
                total_tokens,
                self.count_messages_tokens(compacted),
            )
            return compacted, True

        except Exception as exc:
            logger.warning(
                "Kontext-Komprimierung fehlgeschlagen, trimme stattdessen: %s", exc
            )
            return self.trim_messages(messages), False

    def get_budget_info(self, messages: list[dict]) -> dict:
        """Gibt Informationen über das aktuelle Token-Budget zurück."""
        used = self.count_messages_tokens(messages)
        return {
            "used_tokens": used,
            "max_tokens": self._max_tokens,
            "threshold_tokens": self._threshold_tokens,
            "usage_percent": round(used / self._max_tokens * 100, 1),
            "should_reset": used >= self._threshold_tokens,
        }


# Singleton
_context_mgr: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """Gibt die globale ContextManager-Instanz zurück (lazy init)."""
    global _context_mgr
    if _context_mgr is None:
        _context_mgr = ContextManager()
    return _context_mgr
