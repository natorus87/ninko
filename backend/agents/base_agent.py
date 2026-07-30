"""
Ninko BaseAgent – Abstrakte Basis für alle Agenten.
Nutzt LangGraph für Tool-Calling und Conversation-Management.
"""

from __future__ import annotations

import asyncio
import atexit as _atexit
import hashlib
import json
import logging
import re
import secrets
import time
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from core.safeguard import SafeguardMiddleware

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from core.llm_factory import get_llm, get_model_context_window, get_llm_generation
from core.memory import get_memory
from core.context_manager import get_context_manager
from core import status_bus
from core.agent_events import (
    emit_agent_event,
    get_agent_run_id,
    tenant_id_from_session,
)
from core.agent_protocol import TOOL_APPROVAL_SENTINEL
from core.events import ToolEvent, emit_tool_event
from core.redaction import mask_dict, redact_text
from core.tool_error_handling import wrap_tools_with_sanitizer, sanitize_tool_output
from core.tool_registry import get_tool_status_label, get_tool_registry
from schemas.execution import AgentEvent, AgentEventType

from agents.middleware import (
    MiddlewareRegistry,
    MiddlewareContext,
    LLMProviderMiddleware,
    SoulInjectionMiddleware,
    LanguageMiddleware,
    DatetimeMiddleware,
    CompactionSummaryMiddleware,
    RAGMiddleware,
    KnowledgeGraphMiddleware,
    SkillsMiddleware,
    MessageBuilderMiddleware,
    AgentExecutionMiddleware,
    ResponseExtractionMiddleware,
    ToolCompletionValidationMiddleware,
    MemoryStorageMiddleware,
)

logger = logging.getLogger("ninko.agents.base")

# LLM-Provider-Exceptions als recoverable hinzufügen (optionale Imports,
# damit das Modul auch ohne openai/httpx geladen werden kann).
_LLM_PROVIDER_EXCEPTIONS: tuple[type[BaseException], ...] = ()
try:
    from openai import APIConnectionError as _OpenAIConnectionError
    from openai import APIError as _OpenAIAPIError
    from openai import APITimeoutError as _OpenAITimeoutError
    from openai import AuthenticationError as _OpenAIAuthError
    from openai import RateLimitError as _OpenAIRateLimit
    _LLM_PROVIDER_EXCEPTIONS = (
        _OpenAIConnectionError,
        _OpenAIAPIError,
        _OpenAITimeoutError,
        _OpenAIAuthError,
        _OpenAIRateLimit,
    )
except ImportError:
    pass
try:
    import httpx as _httpx
    _LLM_PROVIDER_EXCEPTIONS = _LLM_PROVIDER_EXCEPTIONS + (
        _httpx.HTTPError,
        _httpx.RequestError,
    )
except ImportError:
    pass

_BASE_AGENT_RECOVERABLE_EXCEPTIONS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    RuntimeError,
    OSError,
    json.JSONDecodeError,
    asyncio.TimeoutError,
) + _LLM_PROVIDER_EXCEPTIONS


def _tool_display_name(tool: Any) -> str:
    """Return a stable name for LangChain tools and plain callable tools."""
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
    return str(name or tool.__class__.__name__)


def _tool_description(tool: Any) -> str:
    description = getattr(tool, "description", None) or getattr(tool, "__doc__", "")
    return str(description or "")


def _get_language() -> str:
    """Gibt den konfigurierten Sprach-Code zurück (gecacht, Fallback: 'de')."""
    try:
        from core.config import get_settings

        return get_settings().LANGUAGE
    except (ImportError, AttributeError):
        return "de"


def _t(
    de: str,
    en: str,
    fr: str = "",
    es: str = "",
    it: str = "",
    nl: str = "",
    pl: str = "",
    pt: str = "",
    ja: str = "",
    zh: str = "",
) -> str:
    """
    Returns text in the correct language based on LANGUAGE setting.
    Supports: de, en, fr, es, it, nl, pl, pt, ja, zh
    If a language is not provided, falls back to English.
    """
    lang = _get_language()
    translations = {
        "de": de,
        "en": en,
        "fr": fr or en,
        "es": es or en,
        "it": it or en,
        "nl": nl or en,
        "pl": pl or en,
        "pt": pt or en,
        "ja": ja or en,
        "zh": zh or en,
    }
    return translations.get(lang, en)


class _StatusEmitter(AsyncCallbackHandler):
    """Emittiert Tool-Start-Events als Status-Updates und Audit-Events."""

    _MAX_PENDING = 500  # Obergrenze für nicht-abgeschlossene Tool-Calls

    def __init__(self, session_id: str, agent_name: str) -> None:
        self.session_id = session_id
        self.agent_name = agent_name
        self._tool_start_times: dict[str, float] = {}
        self._tool_args: dict[str, dict] = {}  # run_id → args, für on_tool_end

    def _cleanup_run(self, run_id: str) -> None:
        """Entfernt alle Einträge für einen Run-ID aus den Tracking-Dicts."""
        self._tool_start_times.pop(run_id, None)
        self._tool_args.pop(run_id, None)

    def _evict_oldest_if_full(self) -> None:
        """Entfernt den ältesten Eintrag wenn die Obergrenze erreicht ist."""
        if len(self._tool_args) >= self._MAX_PENDING:
            oldest = next(iter(self._tool_args))
            self._cleanup_run(oldest)

    def _is_readonly_tool(self, tool_name: str) -> bool:
        registry_result = get_tool_registry().is_readonly(
            tool_name,
            self.agent_name,
        )
        if registry_result is not None:
            return registry_result
        readonly_prefixes = (
            "get_", "list_", "search_", "fetch_", "check_", "load_",
            "perform_web_search", "recall_memory", "get_available_languages",
        )
        return any(tool_name.startswith(prefix) for prefix in readonly_prefixes)

    @staticmethod
    def _safe_error(error: BaseException | str | None) -> str | None:
        if error is None:
            return None
        sanitized = sanitize_tool_output(str(error))
        return redact_text(str(sanitized), limit=400)

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:  # type: ignore[override]
        tool_name = serialized.get("name", "")
        run_id = str(kwargs.get("run_id", ""))

        self._evict_oldest_if_full()
        self._tool_start_times[run_id] = time.monotonic()
        try:
            self._tool_args[run_id] = json.loads(input_str) if input_str else {}
        except (json.JSONDecodeError, TypeError):
            self._tool_args[run_id] = (
                {"_raw": str(input_str)[:200]} if input_str else {}
            )

        # Nur strukturiertes Event – kein redundantes status-Emit mehr,
        # da das Frontend den label aus dem tool_start-Event selbst anzeigt
        label = get_tool_status_label(tool_name)
        # Args vor Emit sanitisieren (verhindert Secret-Leakage im Event-Stream)
        raw_args = self._tool_args.get(run_id, {})
        safe_args = mask_dict(
            json.loads(sanitize_tool_output(json.dumps(raw_args)))
        )
        await status_bus.emit_event(
            self.session_id,
            {
                "type": "tool_start",
                "tool_name": tool_name,
                "label": label,
                "run_id": run_id,
                "agent": self.agent_name,
                "args": safe_args,
            },
        )
        if run_id:
            parent_run_id = (
                get_agent_run_id()
                or str(kwargs.get("parent_run_id", ""))
                or None
            )
            await emit_agent_event(
                AgentEvent(
                    type=AgentEventType.TOOL_CALL,
                    tenant_id=tenant_id_from_session(self.session_id),
                    session_id=self.session_id,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    agent_id=self.agent_name,
                    data={
                        "tool_name": tool_name,
                        "args": safe_args,
                    },
                )
            )

    async def on_tool_end(self, output: Any, **kwargs) -> None:  # type: ignore[override]
        tool_name = kwargs.get("name", "")
        run_id = str(kwargs.get("run_id", ""))

        # Dauer berechnen
        start_time = self._tool_start_times.pop(run_id, None)
        duration_ms = 0.0
        if start_time:
            duration_ms = (time.monotonic() - start_time) * 1000

        # Output analysieren
        result_str = ""
        error_str = None
        if hasattr(output, "content"):
            result_str = str(output.content) if output.content else ""
            if hasattr(output, "status") and output.status == "error":
                error_str = result_str
        else:
            result_str = str(output) if output else ""

        result_size = len(result_str)

        result_preview = ""
        if result_str:
            result_preview = redact_text(result_str, limit=400)[:400]
        safe_error = self._safe_error(error_str)

        # Args aus on_tool_start holen
        args = self._tool_args.pop(run_id, {})
        self._tool_start_times.pop(run_id, None)
        safe_args = mask_dict(args)
        is_readonly = self._is_readonly_tool(tool_name)

        # Event emittieren (non-blocking)
        try:
            event = ToolEvent(
                agent_name=self.agent_name,
                tool_name=tool_name,
                args=safe_args,
                session_id=self.session_id,
                duration_ms=round(duration_ms, 2),
                result_size=result_size,
                error=safe_error,
                is_readonly=is_readonly,
            )
            _evt_task = asyncio.create_task(emit_tool_event(event))
            _evt_task.add_done_callback(_log_bg_task_exception)
        except Exception as exc:
            logger.debug("Audit-Event fehlgeschlagen (non-critical): %s", exc)

        await status_bus.emit_event(
            self.session_id,
            {
                "type": "tool_end",
                "tool_name": tool_name,
                "run_id": run_id,
                "agent": self.agent_name,
                "duration_ms": round(duration_ms, 2),
                "result_size": result_size,
                "error": bool(error_str),
                "preview": result_preview,
            },
        )
        if run_id:
            parent_run_id = (
                get_agent_run_id()
                or str(kwargs.get("parent_run_id", ""))
                or None
            )
            await emit_agent_event(
                AgentEvent(
                    type=AgentEventType.TOOL_RESULT,
                    tenant_id=tenant_id_from_session(self.session_id),
                    session_id=self.session_id,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    agent_id=self.agent_name,
                    data={
                        "tool_name": tool_name,
                        "duration_ms": round(duration_ms, 2),
                        "result_size": result_size,
                        "error": safe_error,
                        "preview": result_preview,
                    },
                )
            )

    async def on_tool_error(self, error: BaseException, **kwargs) -> None:  # type: ignore[override]
        """Emit a sanitized terminal event and release per-tool tracking state."""
        run_id = str(kwargs.get("run_id", ""))
        if not run_id:
            return

        tool_name = str(kwargs.get("name", ""))
        start_time = self._tool_start_times.pop(run_id, None)
        duration_ms = (
            (time.monotonic() - start_time) * 1000
            if start_time is not None
            else 0.0
        )
        safe_args = mask_dict(self._tool_args.pop(run_id, {}))
        safe_error = self._safe_error(error) or "Tool execution failed."
        is_readonly = self._is_readonly_tool(tool_name)

        try:
            event = ToolEvent(
                agent_name=self.agent_name,
                tool_name=tool_name,
                args=safe_args,
                session_id=self.session_id,
                duration_ms=round(duration_ms, 2),
                error=safe_error,
                is_readonly=is_readonly,
            )
            event_task = asyncio.create_task(emit_tool_event(event))
            event_task.add_done_callback(_log_bg_task_exception)
        except Exception as exc:
            logger.debug("Audit-Fehler-Event fehlgeschlagen (non-critical): %s", exc)

        await status_bus.emit_event(
            self.session_id,
            {
                "type": "tool_end",
                "tool_name": tool_name,
                "run_id": run_id,
                "agent": self.agent_name,
                "duration_ms": round(duration_ms, 2),
                "result_size": 0,
                "error": True,
                "preview": safe_error,
            },
        )
        await emit_agent_event(
            AgentEvent(
                type=AgentEventType.TOOL_RESULT,
                tenant_id=tenant_id_from_session(self.session_id),
                session_id=self.session_id,
                run_id=run_id,
                parent_run_id=(
                    get_agent_run_id()
                    or str(kwargs.get("parent_run_id", ""))
                    or None
                ),
                agent_id=self.agent_name,
                data={
                    "tool_name": tool_name,
                    "duration_ms": round(duration_ms, 2),
                    "result_size": 0,
                    "error": safe_error,
                    "preview": safe_error,
                },
            )
        )

    async def on_llm_start(self, serialized: dict, messages: list, **kwargs) -> None:  # type: ignore[override]
        await status_bus.emit_trace(
            self.session_id,
            phase="llm",
            label="LLM-Aufruf gestartet",
            detail=f"Agent: {self.agent_name}",
            data={"agent": self.agent_name, "message_batches": len(messages or [])},
            status="running",
        )
        await status_bus.emit(
            self.session_id,
            _t(
                de="Denke nach…",
                en="Thinking…",
                fr="Réfléchis…",
                es="Pensando…",
                it="Pensando…",
                nl="Denken…",
                pl="Myślę…",
                pt="Pensando…",
                ja="考え中…",
                zh="思考中…",
            ),
        )

    async def on_llm_end(self, response: Any, **kwargs) -> None:  # type: ignore[override]
        """Token-Usage tracken + Reasoning-Text ans Frontend senden."""
        # ── Token-Tracking ──────────────────────────────────────────────────
        usage_payload: dict[str, int] = {}
        try:
            usage = getattr(response, "usage_metadata", None)
            if usage and isinstance(usage, dict):
                prompt_tokens = usage.get("input_tokens", 0) or usage.get(
                    "prompt_tokens", 0
                )
                completion_tokens = usage.get("output_tokens", 0) or usage.get(
                    "completion_tokens", 0
                )
                if prompt_tokens > 0 or completion_tokens > 0:
                    usage_payload = {
                        "prompt_tokens": int(prompt_tokens),
                        "completion_tokens": int(completion_tokens),
                    }
                    from core.metrics import record_llm_tokens

                    _tok_task = asyncio.create_task(
                        record_llm_tokens(
                            agent_name=self.agent_name,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                        )
                    )
                    _tok_task.add_done_callback(_log_bg_task_exception)
        except Exception as _tok_exc:
            logger.warning("Token-Tracking fehlgeschlagen (ignoriert): %s", _tok_exc)

        await status_bus.emit_trace(
            self.session_id,
            phase="llm",
            label="LLM-Aufruf abgeschlossen",
            detail=f"Agent: {self.agent_name}",
            data={"agent": self.agent_name, **usage_payload},
            status="done",
        )

        # ── Reasoning-Text extrahieren – NUR bei Zwischenschritten mit Tool-Calls ──
        # Bei der finalen Antwort (kein Tool-Call) NICHT emittieren,
        # sonst landet der Antworttext im Thinking-Step statt in der Chat-Bubble.
        try:
            text: str = ""
            has_tool_calls: bool = False
            generations = getattr(response, "generations", None)
            if generations:
                gen = generations[0][0] if generations[0] else None
                if gen is not None:
                    msg = getattr(gen, "message", None)
                    if msg is not None:
                        # Prüfen ob Tool-Calls vorhanden (= Zwischenschritt)
                        tool_calls = getattr(msg, "tool_calls", None) or []
                        additional_kw = getattr(msg, "additional_kwargs", {}) or {}
                        has_tool_calls = bool(tool_calls) or bool(
                            additional_kw.get("tool_calls")
                        )
                        # Reasoning-Text extrahieren (nur wenn vorhanden)
                        content = getattr(msg, "content", "")
                        if isinstance(content, str):
                            text = content.strip()
                        elif isinstance(content, list):
                            # Anthropic / strukturiertes Format
                            text = " ".join(
                                c.get("text", "")
                                for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            ).strip()
                    if not text:
                        text = (getattr(gen, "text", "") or "").strip()

            # Nur emittieren wenn es ein Zwischenschritt ist (LLM ruft Tools auf)
            if text and has_tool_calls:
                await status_bus.emit_event(
                    self.session_id,
                    {"type": "thinking_content", "text": text[:600]},
                )
        except Exception as exc:
            logger.debug("Thinking-Content-Event konnte nicht emittiert werden: %s", exc)


_DEFAULT_AGENT_TIMEOUT_SECONDS = 1800
# Ab dieser Tool-Anzahl wird JIT Tool Injection aktiviert
_DEFAULT_JIT_THRESHOLD = 6
# Max. Tools nach JIT-Filterung (Kontext-Sparsamkeit)
_DEFAULT_JIT_MAX_TOOLS = 8

# Strong references to background tasks to prevent premature GC
_background_tasks: set[asyncio.Task] = set()


def _log_bg_task_exception(task: asyncio.Task) -> None:
    """Done-Callback: loggt Exceptions aus Fire-and-Forget Background-Tasks."""
    try:
        exc = task.exception()
        if exc is not None:
            logger.warning(
                "Background-Task '%s' fehlgeschlagen: %s: %s",
                task.get_name(),
                type(exc).__name__,
                exc,
            )
    except (asyncio.CancelledError, asyncio.InvalidStateError):
        pass


def _cleanup_agent_state() -> None:
    """Räumt globale Agent-States bei Prozess-Exit auf."""
    for task in _background_tasks:
        if not task.done():
            task.cancel()
    _background_tasks.clear()
    _memorize_cooldowns.clear()
    logger.info("Agent global state cleanup done.")


_atexit.register(_cleanup_agent_state)


# Auto-Memorize Cooldown: (agent_name, session_id) → letzter Zeitstempel (monotonic)
_memorize_cooldowns: dict[tuple[str, str], float] = {}
_DEFAULT_MEMORIZE_COOLDOWN_SECS = 60.0  # Max 1 Auto-Memorize pro Minute pro Agent
# Agenten die kein Auto-Memorize brauchen (Background-Loops)
_MEMORIZE_EXCLUDED_AGENTS = {"monitor", "scheduler"}
_MEMORIZE_STOP_WORDS = {
    "NICHTS",
    "NOTHING",
    "RIEN",
    "NADA",
    "NULLA",
    "NIETS",
    "NIC",
    "何もない",
    "没有",
}

# ── Tool-level Safeguard (global, gesetzt von main.py via set_global_safeguard) ──
# Sentinel-String der in routes_chat.py erkannt wird wenn ein Tool-Call Bestätigung braucht
_TOOL_SAFEGUARD_SENTINEL = TOOL_APPROVAL_SENTINEL

# Paused safeguard agents: session_id → (sg_agent, thread_config)
# Hält den unterbrochenen LangGraph-Agenten für den Resume-Aufruf am Leben.
_paused_sg_agents: dict[str, tuple[Any, dict]] = {}
_paused_sg_agents_ts: dict[
    str, float
] = {}  # session_id → Erstellungszeitpunkt (monotonic)
_authorized_sg_tool_calls: dict[str, set[str]] = {}
# Schutz gegen race zwischen resume_safeguard_tool und cleanup_paused_agents:
# Cleanup läuft als periodischer Background-Task und könnte pausierte Agents
# entfernen, während der User gerade den Confirm-Button klickt.
_paused_sg_agents_lock = asyncio.Lock()
_PAUSED_SG_AGENT_TTL_SECS: float = (
    300.0  # Gleicher TTL wie Redis-Key ninko:safeguard_tool_pending
)

# Session-spezifische Locks verhindern parallele Safeguard-Runs/Resumes
_safeguard_session_locks: dict[str, asyncio.Lock] = {}
_safeguard_session_locks_ts: dict[
    str, float
] = {}  # session_id → Erstellungszeitpunkt (monotonic)
_SAFEGUARD_LOCK_TTL_SECS: float = 86400.0  # 24h
_MAX_SAFEGUARD_LOCKS = 1000  # Obergrenze für gleichzeitige Session-Locks
_SAFEGUARD_OVERFLOW_LOCKS = 64
_safeguard_overflow_locks: dict[int, asyncio.Lock] = {}

_global_safeguard: "SafeguardMiddleware | None" = None


async def discard_pending_safeguard(
    session_id: str,
    *,
    redis: Any = None,
    expected_approval_id: str | None = None,
) -> bool:
    """Discard paused safeguard state for a non-interactive execution path."""
    if not session_id:
        return False

    if redis is None:
        from core.redis_client import get_redis

        redis = get_redis()

    async with _paused_sg_agents_lock, _get_safeguard_session_lock(session_id):
        pending_key = f"ninko:safeguard_tool_pending:{session_id}"
        if expected_approval_id is not None:
            try:
                deleted = await redis.connection.eval(
                    """
                    local current = redis.call('GET', KEYS[1])
                    if not current then return 0 end
                    local ok, pending = pcall(cjson.decode, current)
                    if not ok or pending['approval_id'] ~= ARGV[1] then
                        return 0
                    end
                    return redis.call('DEL', KEYS[1])
                    """,
                    1,
                    pending_key,
                    expected_approval_id,
                )
            except _BASE_AGENT_RECOVERABLE_EXCEPTIONS:
                return False
            if not expected_approval_id or not deleted:
                return False
        else:
            try:
                await redis.connection.delete(pending_key)
            except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
                logger.debug(
                    "[Safeguard] Pending-Key Cleanup fehlgeschlagen (Session: %s): %s",
                    session_id,
                    exc,
                )
        _paused_sg_agents.pop(session_id, None)
        _paused_sg_agents_ts.pop(session_id, None)
        _authorized_sg_tool_calls.pop(session_id, None)
    return True


def _tool_call_signature(tool_name: str, tool_args: dict) -> str:
    raw = json.dumps(
        {"tool_name": tool_name, "tool_args": tool_args},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _tool_args_preview(tool_args: dict, *, limit: int = 500) -> str:
    if not tool_args:
        return ""
    raw = json.dumps(tool_args, sort_keys=True, ensure_ascii=False, default=str)
    return redact_text(raw, limit=limit)


def set_global_safeguard(sg: "SafeguardMiddleware") -> None:
    """Setzt die globale Safeguard-Instanz (wird von main.py aufgerufen)."""
    global _global_safeguard
    _global_safeguard = sg
    logger.info("Globale Safeguard-Instanz registriert.")


def _get_safeguard_session_lock(session_id: str) -> asyncio.Lock:
    """Gibt den Lock für eine Session zurück (lazy init, TTL 24h).

    Hält die Anzahl gespeicherter Session-Locks begrenzt. Aktive Locks werden
    nicht entfernt; wenn alle Slots belegt sind, fällt die Session auf einen
    deterministischen Overflow-Lock zurück.
    """
    import time

    now = time.monotonic()

    expired = []
    for sid, ts in _safeguard_session_locks_ts.items():
        lock = _safeguard_session_locks.get(sid)
        if lock is not None and now - ts > _SAFEGUARD_LOCK_TTL_SECS and not lock.locked():
            expired.append(sid)
    for sid in expired:
        _safeguard_session_locks.pop(sid, None)
        _safeguard_session_locks_ts.pop(sid, None)

    existing = _safeguard_session_locks.get(session_id)
    if existing is not None:
        _safeguard_session_locks_ts[session_id] = now
        return existing

    while len(_safeguard_session_locks) >= _MAX_SAFEGUARD_LOCKS:
        evictable = [
            (sid, ts)
            for sid, ts in _safeguard_session_locks_ts.items()
            if not _safeguard_session_locks[sid].locked()
        ]
        if not evictable:
            stripe = abs(hash(session_id)) % _SAFEGUARD_OVERFLOW_LOCKS
            lock = _safeguard_overflow_locks.get(stripe)
            if lock is None:
                lock = asyncio.Lock()
                _safeguard_overflow_locks[stripe] = lock
            logger.warning(
                "Safeguard session lock cap reached (%d); using overflow lock stripe %d.",
                _MAX_SAFEGUARD_LOCKS,
                stripe,
            )
            return lock
        oldest_sid = min(evictable, key=lambda item: item[1])[0]
        _safeguard_session_locks.pop(oldest_sid, None)
        _safeguard_session_locks_ts.pop(oldest_sid, None)

    # Reihenfolge: erst Lock holen/erstellen, dann Timestamp setzen.
    # Sonst hat _safeguard_session_locks_ts einen Eintrag, der auf einen
    # Lock zeigt, der gleich wieder evicted wurde.
    lock = _safeguard_session_locks.setdefault(session_id, asyncio.Lock())
    _safeguard_session_locks_ts[session_id] = now
    return lock


def _get_agent_timeout_seconds() -> int:
    """Lädt den Agent-Timeout aus der Config mit robustem Fallback."""
    try:
        from core.config import get_settings

        timeout = int(get_settings().AGENT_TIMEOUT_SECONDS)
        return timeout if timeout > 0 else _DEFAULT_AGENT_TIMEOUT_SECONDS
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_AGENT_TIMEOUT_SECONDS


def _get_jit_threshold() -> int:
    """JIT-Schwelle aus zentraler Config laden (Fallback auf Default)."""
    try:
        from core.config import get_settings

        value = int(get_settings().AGENT_JIT_THRESHOLD)
        return max(1, value)
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_JIT_THRESHOLD


def _get_jit_max_tools() -> int:
    """Maximale Anzahl JIT-Tools aus zentraler Config laden (Fallback auf Default)."""
    try:
        from core.config import get_settings

        value = int(get_settings().AGENT_JIT_MAX_TOOLS)
        return max(1, value)
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_JIT_MAX_TOOLS


def _get_memorize_cooldown_secs() -> float:
    """Auto-Memorize-Cooldown aus zentraler Config laden (Fallback auf Default)."""
    try:
        from core.config import get_settings

        value = float(get_settings().AGENT_MEMORIZE_COOLDOWN_SECS)
        return max(0.0, value)
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_MEMORIZE_COOLDOWN_SECS


def _extract_text(content: str | list) -> str:
    """Extrahiert reinen Text aus AIMessage/ToolMessage.content.

    LangChain liefert für multimodale Inhalte eine Liste von Dicts
    ({ "type": "text", "text": "..." } oder { "type": "image_url", ... }).
    Alle anderen Typen werden via str() konvertiert.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Entfernt <think>...</think> Blöcke aus Thinking-Model-Antworten.

    Qwen3.5, DeepSeek-R1 und ähnliche Modelle generieren interne
    Überlegungen in <think>-Tags, die nicht an den User weitergegeben werden sollen.
    """
    return _RE_THINK.sub("", text).strip()


class BaseAgent:
    """
    Abstrakte Basis – alle Agenten erben hiervon.
    Kapselt LLM-Aufruf, Tool-Binding und Context-Management.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tools = list(tools or [])

        self._llm = get_llm()
        self._llm_generation = get_llm_generation()
        self._memory = get_memory()
        self._context_mgr = get_context_manager()
        self._last_compaction_summary: str | None = None

        # Outbound Secret Sanitization auf alle Tools anwenden
        wrap_tools_with_sanitizer(self.tools)

        # LangGraph ReAct Agent erstellen
        self._agent = create_react_agent(
            model=self._llm,
            tools=self.tools,
        )

        logger.info(
            "Agent '%s' initialisiert mit %d Tools.",
            self.name,
            len(self.tools),
        )

        # Middleware-Registry für strukturierte Invoke-Pipeline
        self._middleware = self._build_middleware_registry()

    def register_tool(self, tool: BaseTool) -> None:
        """
        Backward-compatible tool registration for marketplace plugins.

        Some installable plugins instantiate the agent first and append tools
        afterwards. Keep that working by sanitizing the tool and rebuilding the
        internal LangGraph agent.
        """
        self.tools.append(tool)
        wrap_tools_with_sanitizer([tool])
        self._agent = create_react_agent(
            model=self._llm,
            tools=self.tools,
        )

    def _build_middleware_registry(self) -> MiddlewareRegistry:
        registry = MiddlewareRegistry()

        def _get_lang():
            return _get_language()

        def _get_tz():
            try:
                from core.config import get_settings as _gs

                return _gs().TIMEZONE
            except (ImportError, AttributeError):
                return "Europe/Berlin"

        def _get_soul_manager():
            from core.soul_manager import get_soul_manager

            return get_soul_manager()

        def _get_skills_manager():
            from core.skills_manager import get_skills_manager

            return get_skills_manager()

        registry.add(
            LLMProviderMiddleware(get_llm, get_llm_generation, create_react_agent)
        )
        registry.add(SoulInjectionMiddleware(_get_soul_manager))
        registry.add(LanguageMiddleware(_get_lang))
        registry.add(DatetimeMiddleware(_get_tz))
        registry.add(CompactionSummaryMiddleware())
        registry.add(RAGMiddleware(self._memory))
        registry.add(KnowledgeGraphMiddleware())
        registry.add(SkillsMiddleware(_get_skills_manager))
        registry.add(MessageBuilderMiddleware())
        registry.add(
            AgentExecutionMiddleware(
                safeguard=_global_safeguard,
                get_safeguard_session_lock=_get_safeguard_session_lock
                if _global_safeguard
                else None,
                run_with_safeguard=self._run_with_safeguard
                if _global_safeguard
                else None,
                paused_agents=_paused_sg_agents,
                paused_agents_ts=_paused_sg_agents_ts,
                paused_ttl_secs=_PAUSED_SG_AGENT_TTL_SECS,
                callbacks_factory=lambda sid, name: _StatusEmitter(sid, name),
            )
        )
        registry.add(ResponseExtractionMiddleware())
        registry.add(ToolCompletionValidationMiddleware())
        registry.add(
            MemoryStorageMiddleware(
                auto_memorize_fn=self._auto_memorize,
                excluded_agents=_MEMORIZE_EXCLUDED_AGENTS,
                cooldowns=_memorize_cooldowns,
                background_tasks=_background_tasks,
            )
        )

        return registry

    def _select_tools_for_request(self, message: str) -> list[Any]:
        """
        JIT Tool Injection (OpenClaw-Prinzip):
        Gibt nur die für diese Anfrage relevanten Tools zurück.
        Reduziert Kontext-Overhead bei Agenten mit vielen Tools.
        """
        jit_threshold = _get_jit_threshold()
        jit_max_tools = _get_jit_max_tools()

        if len(self.tools) <= jit_threshold:
            return self.tools

        msg_lower = message.lower()
        # Wörter mit mind. 2 Zeichen extrahieren (IT-Fachbegriffe wie IP, VM, K8s, HA, DNS)
        words = [
            w.strip(".,!?:;")
            for w in msg_lower.replace("-", " ").split()
            if len(w.strip(".,!?:;")) >= 2
        ]

        scored: list[tuple[int, Any]] = []
        for t in self.tools:
            searchable = f"{_tool_display_name(t)} {_tool_description(t)}".lower()
            score = sum(1 for w in words if w in searchable)
            scored.append((score, t))

        # Tools mit mindestens 1 Treffer
        relevant = [t for s, t in scored if s > 0]

        # Fallback: keine Treffer → Obergrenze statt alle Tools
        if len(relevant) == 0:
            logger.debug(
                "JIT Tool Injection: Agent '%s' – keine Treffer, "
                "beschränke auf %d Tools (Kontext-Sparsamkeit).",
                self.name,
                jit_max_tools,
            )
            return self.tools[:jit_max_tools]

        # Sortiert nach Score, max. JIT-Max-Tools
        top = sorted(scored, key=lambda x: x[0], reverse=True)
        selected = [t for _, t in top[:jit_max_tools]]
        logger.debug(
            "JIT Tool Injection: Agent '%s' %d → %d Tools.",
            self.name,
            len(self.tools),
            len(selected),
        )
        return selected

    async def _dynamic_prompt_appendix(self) -> str:
        """Erzeugt dynamischen Kontext (z.B. Connections), der an den System-Prompt gehängt wird."""
        if self.name in ("orchestrator", "monitor", "scheduler"):
            return ""

        try:
            from core.connections import ConnectionManager

            conns = await ConnectionManager.list_connections(self.name)
            if not conns:
                return ""

            info = "AVAILABLE CONNECTIONS FOR THIS MODULE:\n"
            for c in conns:
                d = " [DEFAULT]" if c.is_default else ""
                info += f"- connection_id: '{c.id}' | Name: '{c.name}' | Env: '{c.environment}'{d}\n"

            info += (
                "\nIMPORTANT: ALWAYS use the appropriate 'connection_id' for tools! "
                "If the user does not specify an environment, use the default connection."
            )
            return info
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as e:
            logger.warning("Fehler beim Laden der Connections für Prompt: %s", e)
            return ""

    async def invoke(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
        confirmed: bool = False,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, bool]:
        history = chat_history or []

        # Context-Window kalibrieren + Komprimierung/Trimming
        model_window = await get_model_context_window()
        self._context_mgr.update_from_model_window(model_window)

        did_compact = False
        if self._context_mgr.should_reset(history):
            await status_bus.emit_trace(
                session_id,
                phase="context",
                label="Kontext-Komprimierung gestartet",
                detail="Der Gesprächsverlauf überschreitet das aktuelle Kontextbudget.",
                data={"history_messages": len(history)},
                status="running",
            )
            await status_bus.emit(
                session_id, _t("Kontext wird komprimiert…", "Compacting context…")
            )
            (
                trimmed_history,
                did_compact,
            ) = await self._context_mgr.compact_messages_async(history, self._llm)
            self._last_compaction_summary = self._context_mgr.get_last_summary()
            await status_bus.emit_trace(
                session_id,
                phase="context",
                label="Kontext komprimiert",
                data={
                    "history_messages_before": len(history),
                    "history_messages_after": len(trimmed_history),
                },
            )
        else:
            history = self._context_mgr.trim_large_messages(history)
            trimmed_history = self._context_mgr.trim_messages(
                messages=history,
                system_prompt=self.system_prompt,
            )
            self._last_compaction_summary = None
            if len(trimmed_history) != len(history):
                await status_bus.emit_trace(
                    session_id,
                    phase="context",
                    label="Kontext gekürzt",
                    data={
                        "history_messages_before": len(history),
                        "history_messages_after": len(trimmed_history),
                    },
                )

        # Dynamischen Zusatz für den System Prompt
        appendix = await self._dynamic_prompt_appendix()
        final_system_prompt = self.system_prompt
        if appendix:
            final_system_prompt += f"\n\n{appendix}"

        # JIT Tool Injection
        active_tools = self._select_tools_for_request(message)
        jit_agent = (
            create_react_agent(model=self._llm, tools=active_tools)
            if len(active_tools) != len(self.tools)
            else self._agent
        )
        if len(active_tools) != len(self.tools):
            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Tool-Auswahl reduziert",
                detail=f"JIT Tool Injection für Agent '{self.name}'",
                data={
                    "agent": self.name,
                    "total_tools": len(self.tools),
                    "active_tools": [_tool_display_name(tool) for tool in active_tools],
                },
            )
        else:
            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Agent vorbereitet",
                detail=f"Agent '{self.name}' erhält {len(active_tools)} Tool(s).",
                data={"agent": self.name, "active_tool_count": len(active_tools)},
            )

        # Middleware-Kontext aufbauen
        ctx = MiddlewareContext(
            message=message,
            chat_history=history,
            session_id=session_id,
            confirmed=confirmed,
            agent_name=self.name,
            system_prompt=self.system_prompt,
            final_system_prompt=final_system_prompt,
            trimmed_history=trimmed_history,
            active_tools=active_tools,
            llm=self._llm,
            agent=self._agent,
            jit_agent=jit_agent,
            extra={"language": _get_language()},
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )

        # Pre-Processing Pipeline
        pre_result = await self._middleware.run_pre(ctx)
        if pre_result and pre_result.short_circuit:
            # Prefer MiddlewareResult.response if explicitly set; fall back to
            # ctx.early_return_response for middleware that writes there directly.
            short_circuit_response = pre_result.response or ctx.early_return_response
            return short_circuit_response, did_compact

        # LLM Call
        await self._middleware.run_post(ctx)

        # Response oder Early Return
        if ctx.early_return:
            return ctx.response, did_compact

        return ctx.response, did_compact

    def get_last_compaction_summary(self) -> str | None:
        return self._last_compaction_summary

    def _extract_result_response(self, result: dict) -> str:
        """Extrahiert den Antwort-Text aus einem LangGraph-Ergebnis-Dict."""
        all_messages = result.get("messages", [])
        ai_messages = [
            m for m in all_messages if isinstance(m, AIMessage) and m.content
        ]

        if ai_messages:
            raw = _extract_text(ai_messages[-1].content)
            response = _strip_thinking(raw)
            if response:
                return response
            # Thinking-only: Fallback auf ToolMessages
        tool_messages = [
            m for m in all_messages if isinstance(m, ToolMessage) and m.content
        ]
        if tool_messages:
            return _extract_text(tool_messages[-1].content)
        return _t("Keine Antwort generiert.", "No response generated.")

    async def _sg_loop(
        self,
        sg_agent: Any,
        thread_config: dict,
        input_data: dict | None,
        session_id: str,
        confirmed: bool = False,
    ) -> "dict | str":
        """
        Kern-Schleife für den Safeguard-Interrupt-Mechanismus.

        Führt den Agenten aus und pausiert vor jedem Tool-Call. Gibt das
        LangGraph-Ergebnis-Dict zurück wenn die Ausführung abgeschlossen ist,
        oder einen Sentinel-String wenn ein Tool-Call Bestätigung benötigt.

        Bestätigte Tool-Calls werden über eine signierte Pending-Autorisierung
        scoped freigegeben; weitere Tool-Calls im gleichen Loop werden erneut
        geprüft.
        """
        AGENT_TIMEOUT = _get_agent_timeout_seconds()
        iterations = 0
        max_iterations = 50
        message_confirmation_consumed = False

        while True:
            iterations += 1
            if iterations > max_iterations:
                logger.error(
                    "[Safeguard] Iterationsgrenze (%d) erreicht – breche Loop ab "
                    "(Agent: %s, Session: %s)",
                    max_iterations,
                    self.name,
                    session_id,
                )
                return {
                    "messages": [
                        AIMessage(
                            content="[Safeguard] Iterationsgrenze erreicht. "
                            "Bitte reduziere die Anzahl der Tool-Calls oder teile die Aufgabe auf."
                        )
                    ]
                }
            result = await asyncio.wait_for(
                sg_agent.ainvoke(input_data, config=thread_config),
                timeout=AGENT_TIMEOUT,
            )
            input_data = None  # Folge-Iterationen = Resume vom Checkpoint

            # Prüfen ob der Graph vor einem Tool-Call pausiert ist
            state = sg_agent.get_state(thread_config)
            if not (state.next and "tools" in state.next):
                # Ausführung abgeschlossen
                return result

            # Paused — pending Tool-Calls aus dem State lesen
            all_msgs = state.values.get("messages", [])
            ai_with_tools = [
                m
                for m in all_msgs
                if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
            ]
            if not ai_with_tools:
                # Sollte nicht vorkommen, aber sicher resumieren
                continue

            last_ai = ai_with_tools[-1]

            # Alle pending Tool-Calls prüfen (Parallel-Tool-Calls möglich)
            dangerous_call = None
            for tool_call in last_ai.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})
                tool_signature = _tool_call_signature(tool_name, tool_args)

                if _global_safeguard is None or not _global_safeguard.enabled:
                    logger.warning(
                        "[Safeguard] Instanz während Lauf verloren/deaktiviert "
                        "(Agent: %s, Session: %s) – setze Ausführung ohne erneuten Check fort.",
                        self.name,
                        session_id,
                    )
                    dangerous_call = None
                    break

                authorized = _authorized_sg_tool_calls.setdefault(session_id, set())
                iter_confirmed = tool_signature in authorized
                if confirmed and not iter_confirmed:
                    try:
                        from core.redis_client import get_redis as _get_redis_scoped

                        _redis_scoped = _get_redis_scoped()
                        _pending_raw = await _redis_scoped.connection.get(
                            f"ninko:safeguard_tool_pending:{session_id}"
                        )
                        if _pending_raw:
                            _pending = json.loads(_pending_raw)
                            if _pending.get("tool_signature") == tool_signature:
                                authorized.add(tool_signature)
                                iter_confirmed = True
                    except Exception:
                        iter_confirmed = False

                sg_result = await _global_safeguard.check_tool_call(
                    tool_name,
                    tool_args,
                    agent_id=self.name,
                    session_id=session_id,
                    confirmed=iter_confirmed,
                )
                if sg_result.auto_decided and sg_result.auto_decision == "deny":
                    logger.warning(
                        "[Safeguard] Auto-Mode verweigert Tool-Call '%s' "
                        "(Agent: '%s', Session: '%s'): %s",
                        tool_name,
                        self.name,
                        session_id,
                        sg_result.rationale,
                    )
                    return {
                        "messages": [
                            AIMessage(
                                content=_t(
                                    "SafeGuard Auto-Mode hat die Tool-Ausführung abgelehnt.\n\n"
                                    f"Kategorie: {sg_result.category.value}\n"
                                    f"Begründung: {sg_result.rationale}",
                                    "SafeGuard Auto-Mode denied the tool execution.\n\n"
                                    f"Category: {sg_result.category.value}\n"
                                    f"Reason: {sg_result.rationale}",
                                )
                            )
                        ]
                    }
                if sg_result.requires_confirmation:
                    if confirmed and not iter_confirmed and not message_confirmation_consumed:
                        message_confirmation_consumed = True
                        authorized.add(tool_signature)
                        logger.info(
                            "[Safeguard] Tool-Call '%s' durch zuvor bestätigte "
                            "User-Message einmalig autorisiert (Agent: '%s', Session: '%s').",
                            tool_name,
                            self.name,
                            session_id,
                        )
                        continue
                    dangerous_call = (
                        tool_name,
                        tool_args,
                        tool_signature,
                        sg_result,
                    )
                    break  # Ersten gefährlichen Call als Confirmation-Request nehmen

            if dangerous_call is None:
                # Alle Tools sind SAFE → sofort resumieren (transparent)
                _authorized_sg_tool_calls.pop(session_id, None)
                continue

            tool_name, tool_args, tool_signature, sg_result = dangerous_call

            # Pausiert: Zustand im Modul-Dict speichern + in Redis vermerken
            import time as _time_mod

            from core.redis_client import get_redis

            redis = get_redis()
            approval_id = secrets.token_urlsafe(16)
            await redis.connection.setex(
                f"ninko:safeguard_tool_pending:{session_id}",
                300,
                json.dumps(
                    {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_args_preview": _tool_args_preview(tool_args),
                        "tool_signature": tool_signature,
                        "approval_id": approval_id,
                        "agent": self.name,
                        "category": sg_result.category.value,
                        "rationale": sg_result.rationale,
                    }
                ),
            )
            _paused_sg_agents[session_id] = (sg_agent, thread_config)
            _paused_sg_agents_ts[session_id] = _time_mod.monotonic()

            logger.info(
                "[Safeguard] Tool-Call '%s' pausiert (Agent: '%s', Session: '%s').",
                tool_name,
                self.name,
                session_id,
            )
            return f"{_TOOL_SAFEGUARD_SENTINEL}" + json.dumps(
                {
                    "tool_name": tool_name,
                    "tool_args_preview": _tool_args_preview(tool_args),
                    "tool_signature": tool_signature,
                    "approval_id": approval_id,
                    "category": sg_result.category.value,
                    "rationale": sg_result.rationale,
                }
            )
    async def _run_with_safeguard(
        self,
        messages: list,
        active_tools: list,
        run_config: dict,
        session_id: str,
        confirmed: bool = False,
    ) -> "dict | str":
        """
        Führt den Agenten mit aktivem Safeguard-Interrupt aus.

        Erstellt einen temporären Agenten mit MemorySaver + interrupt_before=["tools"].
        """
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        sg_agent = create_react_agent(
            model=self._llm,
            tools=active_tools,
            checkpointer=checkpointer,
            interrupt_before=["tools"],
        )
        thread_config = {**run_config, "configurable": {"thread_id": session_id}}
        return await self._sg_loop(
            sg_agent, thread_config, {"messages": messages}, session_id,
            confirmed=confirmed,
        )

    async def resume_safeguard_tool(
        self,
        session_id: str,
        *,
        expected_approval_id: str | None = None,
    ) -> tuple[str, bool]:
        """
        Setzt die Ausführung nach Safeguard-Bestätigung durch den User fort.
        Holt den pausierten Agenten aus _paused_sg_agents und resumiert den Graph.
        """
        async def _cleanup_pending_state() -> None:
            _paused_sg_agents.pop(session_id, None)
            _paused_sg_agents_ts.pop(session_id, None)
            _authorized_sg_tool_calls.pop(session_id, None)
            try:
                from core.redis_client import get_redis

                redis = get_redis()
                await redis.connection.delete(
                    f"ninko:safeguard_tool_pending:{session_id}"
                )
            except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
                logger.debug(
                    "[Safeguard] Pending-Key Cleanup fehlgeschlagen (Session: %s): %s",
                    session_id,
                    exc,
                )

        async with _paused_sg_agents_lock, _get_safeguard_session_lock(session_id):
            # Beide Locks halten: _paused_sg_agents_lock schützt vor
            # cleanup_paused_agents (global, per-session-agnostisch), das
            # per-session-Lock serialisiert Resumes derselben Session.
            if session_id not in _paused_sg_agents:
                logger.warning(
                    "[Safeguard] Resume angefragt, aber kein pausierter Agent für Session '%s'.",
                    session_id,
                )
                return _t(
                    "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                    "Error: No pending tool call for this session.",
                ), False

            # Nicht poppen bevor Resume erfolgreich ist — sonst State-Verlust bei Fehlern.
            paused = _paused_sg_agents.get(session_id)
            if paused is None:
                return _t(
                    "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                    "Error: No pending tool call for this session.",
                ), False
            if expected_approval_id is not None:
                try:
                    from core.redis_client import get_redis

                    redis = get_redis()
                    pending_raw = await redis.connection.get(
                        f"ninko:safeguard_tool_pending:{session_id}"
                    )
                    pending = json.loads(pending_raw) if pending_raw else {}
                except _BASE_AGENT_RECOVERABLE_EXCEPTIONS:
                    pending = {}
                if (
                    not expected_approval_id
                    or pending.get("approval_id") != expected_approval_id
                ):
                    logger.warning(
                        "[Safeguard] Veraltete Tool-Bestätigung für Session '%s' abgelehnt.",
                        session_id,
                    )
                    return _t(
                        "Fehler: Diese Tool-Bestätigung ist nicht mehr gültig.",
                        "Error: This tool confirmation is no longer valid.",
                    ), False
            sg_agent, thread_config = paused
            try:
                # Resume nach User-Bestätigung: alle Tool-Calls in dieser
                # Session sind bereits autorisiert. confirmed=True verhindert
                # weitere Tool-Level-Confirms (z.B. für Workflow-Tools).
                result = await self._sg_loop(
                    sg_agent, thread_config, None, session_id, confirmed=True
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Agent '%s' Timeout beim Resume (Session: %s).",
                    self.name,
                    session_id,
                )
                await _cleanup_pending_state()
                return _t(
                    "Die Ausführung hat zu lange gedauert und wurde abgebrochen.",
                    "Execution timed out and was aborted.",
                ), False
            except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
                logger.error(
                    "Agent '%s' Fehler beim Resume: %s", self.name, exc, exc_info=True
                )
                await _cleanup_pending_state()
                return _t(
                    "Fehler: Resume fehlgeschlagen. Bitte erneut bestätigen oder Anfrage wiederholen.",
                    "Error: Resume failed. Please confirm again or retry the request.",
                ), False

            # Weiterer Sentinel? (nächster gefährlicher Tool-Call)
            if isinstance(result, str):
                return result, False

            # Erfolg: pausierten Zustand + Pending-Key aufräumen
            await _cleanup_pending_state()
            return self._extract_result_response(result), False

    async def store_incident(
        self,
        summary: str,
        details: str,
        severity: str = "info",
    ) -> str:
        """Speichert einen Incident im Semantic Memory."""
        return await self._memory.store_incident(
            module=self.name,
            summary=summary,
            details=details,
            severity=severity,
        )

    async def _auto_memorize(self, user_msg: str, ai_response: str) -> None:
        """
        Extrahiert und speichert dauerhaft relevante Fakten aus dem Gespräch.
        Läuft als Hintergrund-Task, blockiert nie die Antwortzeit.
        Nutzt Auto-Importance für besseres Memory-Ranking.
        """
        try:
            prompt = (
                "Extract ONLY permanently relevant facts from this conversation "
                "(e.g. user names, IPs, preferences, decisions, solved problems, learned configurations). "
                'Respond ONLY with JSON: {"fact": "...", "importance": 0.5}\n'
                "importance: 1.0 = critical (system outage, core config), "
                "0.5 = normal (preferences, learned patterns), "
                "0.2 = trivial (temporary info). "
                'If NOTHING permanently noteworthy: {"fact": "NOTHING", "importance": 0.0}\n\n'
                f"User: {user_msg}\nAssistant: {ai_response[:800]}"
            )
            result = await self._llm.ainvoke([HumanMessage(content=prompt)])
            content = (
                result.content.strip()
                if hasattr(result, "content")
                else str(result).strip()
            )

            # JSON-Parsing mit Fallback
            fact_text = ""
            importance = 0.5  # Default
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    fact_text = parsed.get("fact", "").strip()
                    importance = float(parsed.get("importance", 0.5))
            except json.JSONDecodeError:
                # Kein JSON: nur übernehmen, wenn es ein knapper, sauberer Fakt ist.
                # Sonst landet LLM-Rohtext (Erklärungen, think-Blöcke, Markdown)
                # im permanenten Memory und verschmutzt recall_memory.
                stripped = content.strip().strip('*_ \n"\'')
                if len(stripped) <= 200 and "\n" not in stripped:
                    fact_text = stripped

            # Validierung und Speicherung
            if (
                fact_text
                and fact_text.strip("*_ \n\"'").upper() not in _MEMORIZE_STOP_WORDS
            ):
                await self._memory.store(
                    content=fact_text,
                    category="agent_memory",
                    metadata={"agent": self.name, "source": "auto"},
                    importance=importance,
                )
                logger.debug(
                    "Auto-Memory gespeichert für Agent '%s' (importance=%.2f): %s…",
                    self.name,
                    importance,
                    fact_text[:80],
                )
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
            logger.debug("Auto-Memorize fehlgeschlagen (ignoriert): %s", exc)
