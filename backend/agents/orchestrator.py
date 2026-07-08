"""
Ninko Orchestrator Agent – LLM-Native Function Calling Routing.

Modul-Routing via Native Function Calling im Conversational-Modell.
Kein separates Router-Modell, kein Keyword-Routing, keine Evidence-Layer.
"""

from __future__ import annotations

import asyncio
import hashlib
import json as _json
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

import numpy as np


# ── Intent-Detection-Patterns ───────────────────────────────────────────────
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base_agent import BaseAgent, _t
from agents.fast_path_tool_resolver import try_get_module_tool
from agents.core_tools import (
    execute_cli_command,
    create_custom_agent,
    update_custom_agent,
    install_skill,
    create_dag_workflow,
    create_linear_workflow,
    execute_workflow,
    remember_fact,
    recall_memory,
    forget_fact,
    confirm_forget,
    call_module_agent,
    run_pipeline,
    run_parallel_pipeline,
    wait,
    create_scheduled_task,
    list_scheduled_tasks,
    delete_scheduled_task,
    run_agent_job,
    get_agent_job_result,
)
from agents.alert_tools import (
    check_alert_state,
    record_alert,
    resolve_alert,
)
from agents.script_tools import run_script_tool, list_script_tools
from core import status_bus
from core.config import get_settings
from core.llm_factory import get_llm, get_embeddings
from core.redis_client import get_redis

if TYPE_CHECKING:
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.orchestrator")


def _log_background_task_exception(task: asyncio.Task) -> None:
    """Loggt Exceptions aus fire-and-forget Tasks."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.warning("persist_evidence_trace fehlgeschlagen: %s", exc)


async def _should_safeguard_auto_confirm(session_id: str) -> bool:
    """Gibt True zurück, wenn der Safeguard-Auto-Modus für die Session aktiv ist.

    Vereinheitlicht die Auto-Confirm-Logik über alle Pipeline-Pfade, damit
    deterministisch geplante und LLM-dispatched Pipelines konsistent laufen.
    """
    from agents.base_agent import _global_safeguard

    if _global_safeguard is None or not _global_safeguard.enabled:
        return True
    try:
        profile = await _global_safeguard.resolve_profile(session_id=session_id)
    except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
        logger.debug("Safeguard-Profil konnte nicht geladen werden: %s", exc)
        return False
    return bool(getattr(profile, "auto_mode", False)) if profile is not None else False


_ORCH_RECOVERABLE_EXCEPTIONS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    RuntimeError,
    asyncio.TimeoutError,
    _json.JSONDecodeError,
)

# ── LLM-Timeouts (Orchestrator-eigene Konstanten) ────────────────────────────
_LLM_ROUTING_TIMEOUT: float = 10.0

# ── Intent-Detection-Patterns (Tier-1/3, kein Routing-Concern) ───────────────

_AGENT_CREATE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\berstell(?:e|en|t)?\b.{0,40}\bagent(?:en)?\b", re.IGNORECASE),
    re.compile(r"\bleg(?:e|en|t)?\b.{0,40}\bagent(?:en)?\b.{0,20}\ban\b", re.IGNORECASE),
    re.compile(r"\bbau(?:e|en|t)?\b.{0,40}\bagent(?:en)?\b", re.IGNORECASE),
    re.compile(r"\bcreate\b.{0,40}\bagent\b", re.IGNORECASE),
    re.compile(r"\bbuild\b.{0,40}\bagent\b", re.IGNORECASE),
    re.compile(r"\bmake\b.{0,40}\bagent\b", re.IGNORECASE),
)

_AGENT_HOWTO_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(
        r"\bwie\b.{0,30}\b(agent|agenten)\b.{0,20}\b(erstell|anleg|bau)\w*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwie\b.{0,30}\b(erstell|anleg|bau)\w*\b.{0,30}\b(agent|agenten)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\b.{0,20}\b(to\b.{0,10})?(create|build|make)\b.{0,30}\bagent\b",
        re.IGNORECASE,
    ),
    re.compile(r"\banleitung\b.{0,40}\bagent\b", re.IGNORECASE),
)

_WORKFLOW_CREATE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\berstell(?:e|en|t)?\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bleg(?:e|en|t)?\b.{0,40}\bworkflow\b.{0,20}\ban\b", re.IGNORECASE),
    re.compile(r"\bbau(?:e|en|t)?\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bcreate\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bbuild\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bautomatisier\w*\b.{0,40}\b(ablauf|prozess|workflow)\b", re.IGNORECASE),
)

_WORKFLOW_HOWTO_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bwie\b.{0,30}\bworkflow\b.{0,20}\b(erstell|anleg|bau)\w*", re.IGNORECASE),
    re.compile(
        r"\bhow\b.{0,20}\b(to\b.{0,10})?(create|build|make)\b.{0,30}\bworkflow\b",
        re.IGNORECASE,
    ),
    re.compile(r"\banleitung\b.{0,40}\bworkflow\b", re.IGNORECASE),
)


# ── Routing-Konstanten (aus core/router.py) ───────────────────────────────────

_UTILITY_MODULES: frozenset[str] = frozenset(
    {"web_search", "image_gen", "telegram", "email", "teams"}
)


class KeywordRouter:
    """Minimal compatibility router for legacy helper paths.

    The primary router is Function Calling. These methods keep older telemetry,
    force/fallback helpers and tests from depending on the removed core.router.
    """

    def __init__(self, routing_map: dict[str, str] | None = None) -> None:
        self._routing_map = routing_map or {}

    def update_routing_map(self, routing_map: dict[str, str]) -> None:
        self._routing_map = routing_map or {}

    @staticmethod
    def strip_bot_context(message: str) -> str:
        return message

    def get_scores(self, text: str) -> dict[str, int]:
        lowered = text.casefold()
        scores: dict[str, int] = {}
        for keyword, module in self._routing_map.items():
            if keyword and self._keyword_matches(lowered, keyword):
                scores[module] = scores.get(module, 0) + 1
        return scores

    @staticmethod
    def _keyword_matches(lowered_text: str, keyword: str) -> bool:
        """Match routing keywords without letting short aliases hit inside words."""
        normalized = keyword.strip().casefold()
        if not normalized:
            return False
        if len(normalized) <= 3 and re.fullmatch(r"[\w+-]+", normalized, re.UNICODE):
            return bool(
                re.search(
                    rf"(?<![\w+-]){re.escape(normalized)}(?![\w+-])",
                    lowered_text,
                    re.UNICODE,
                )
            )
        return normalized in lowered_text

    @staticmethod
    def has_confident_top_module(top_score: int, second_score: int) -> bool:
        return top_score > 0 and top_score >= second_score + 2

    def has_multistep_indicators(self, message: str, current_scores: dict[str, int]) -> bool:
        lowered = message.lower()
        has_sequence_marker = any(
            marker in lowered for marker in (" und dann ", " danach ", " anschließend ", " then ")
        )
        if not has_sequence_marker:
            return False

        qualified_modules = [
            module
            for module, score in current_scores.items()
            if score >= 2 or (module in _UTILITY_MODULES and score >= 1)
        ]
        return len(qualified_modules) >= 2

    def detect_module(
        self,
        message: str,
        chat_history: list[dict] | None = None,
    ) -> tuple[str | None, bool, float | None]:
        scores = self.get_scores(message)
        if not scores:
            return None, False, None
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_module, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0
        is_compound = self.has_multistep_indicators(message, scores)
        if self.has_confident_top_module(top_score, second_score) or len(ranked) == 1:
            return top_module, is_compound, min(1.0, top_score / max(1, top_score + second_score))
        return None, is_compound, None


# ── Intent-Detection-Patterns (Tier-1/3, kein Routing-Concern) ───────────────
async def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Generiert ein Bild mit einem KI-Bildgenerierungsmodell.
    Nutze dieses Tool wenn der User ein Bild, eine Illustration, ein Logo,
    ein Foto oder eine Grafik erstellen möchte.
    """
    from modules.image_gen.tools import generate_image as _gen

    return await _gen(prompt=prompt, size=size)


SYSTEM_PROMPT = """Du bist Ninko – ein intelligenter IT-Operations-Assistent.

Du bist der zentrale Ansprechpartner. Du entscheidest selbst, wie du eine Anfrage bearbeitest:

ENTSCHEIDUNGS-LOGIK:
1. Ist die Anfrage eindeutig einem Modul zugeordnet (Kubernetes, Pi-hole, HomeAssistant etc.)?
   → `call_module_agent("<modul>", "<vollständige Aufgabe>")` aufrufen.
   → Bei kurzen Folgefragen ohne neues Ziel ("wie viele?", "zeige Details", "und jetzt?")
     bleibe beim Modul/Thema der letzten Antwort, außer der User nennt explizit ein anderes Modul.
2. Erfordert die Anfrage mehrere Module nacheinander?
   → `run_pipeline([{"module":"...", "task":"..."}])` — Ergebnisse werden automatisch weitergegeben.
   → Für PARALLELE Ausführung: `run_parallel_pipeline(groups=[[{...}, {...}], [{...}]])` —
     Steps in einer Gruppe laufen gleichzeitig, Gruppen nacheinander.
   → Alternativ: `run_pipeline` mit `"depends_on": []` für parallele Steps
     (z.B. `[{"module":"kubernetes","task":"..."}, {"module":"pihole","task":"...","depends_on":[]}, {"module":"glpi","task":"...","depends_on":[0,1]}]`).
3. Braucht der User ein spezialisiertes KI-Profil das kein Modul abdeckt?
   → `create_custom_agent` aufrufen. WICHTIG: Vor dem Erstellen Use-Case klären (Zweck, Module,
     Output, Kritikalität). System-Prompt strukturiert aufbauen: ## Aufgaben / ## Arbeitsweise /
     ## Kritische Aktionen / ## Eskalation. Destruktive Aktionen immer gatten.
   → Mit `update_custom_agent` einen bestehenden Agenten verbessern wenn der User das möchte.
   → Soll ein Agent EINMALIG eine Aufgabe ausführen: `run_agent_job(agent_id_or_name, prompt)` —
     läuft im Hintergrund; Ergebnis später mit `get_agent_job_result(job_id)` abrufen.
     Für WIEDERKEHRENDE Ausführung stattdessen `create_scheduled_task` mit agent_id.
4. Braucht der User einen Workflow?
   → Einfache lineare Abfolge: `create_linear_workflow` SOFORT aufrufen.
   → Conditions, Loops oder Branching: `create_dag_workflow` aufrufen — NIEMALS nur erklären wie es geht.
5. Kann ich es direkt aus meinem Wissen beantworten?
   → Direkte Antwort ohne Tools.

WEITERE FÄHIGKEITEN:
- `execute_cli_command`: Lokale Systeminformationen (uptime, ping, df, etc.) — proaktiv nutzen bei Host/Container-Fragen.
- `generate_image`: Bilder, Illustrationen, Logos — Prompt auf Englisch, detailliert beschreiben.
- `execute_workflow`: Bestehende Workflows ausführen wenn explizit gefordert.
- `install_skill`: Prozedurales Domänenwissen speichern (Vorgehensweisen, Best Practices).
- `remember_fact` / `recall_memory` / `forget_fact` / `confirm_forget`: Langzeitgedächtnis.
  Bei Vergessen: erst `forget_fact` (Vorschau), dann `confirm_forget` mit bestätigten IDs.

VERFÜGBARE MODULE: Siehe VERFÜGBARE MODULE weiter unten — nutze `call_module_agent` mit exaktem Modulnamen.

WICHTIG: `call_module_agent` für EINZELNE Modul-Aufrufe. `run_pipeline` wenn Ergebnisse zwischen Modulen fließen müssen (sequenziell oder mit depends_on für Parallelisierung). `run_parallel_pipeline` wenn mehrere Module GLEICHZEITIG abgefragt werden sollen und die Ergebnisse danach zusammenfließen. Multi-Modul-Anfragen mit explizit sequentiellem Intent (z.B. "restart X und schick dann Telegram-Nachricht") werden automatisch als Tier-4-Pipeline erkannt und benötigen KEIN manuelles `run_pipeline` im ReAct-Loop — vermeide Doppel-Routing.

BILD-TAGS: Wenn ein Tool-Ergebnis `[NINKO_IMAGE:url]` enthält, übernimm diesen Tag EXAKT und UNVERÄNDERT in deine Antwort. Ersetze ihn NIEMALS durch einen Markdown-Link, eine URL oder ein Emoji. Der Tag muss wörtlich `[NINKO_IMAGE:https://...]` im Antworttext erscheinen.

Verhalte dich professionell, proaktiv und sicherheitsbewusst."""


class OrchestratorAgent(BaseAgent):
    """
    Der Orchestrator kennt keine Modul-Namen hardcodiert.
    Er arbeitet ausschließlich mit der ModuleRegistry.
    Er besitzt ein Set von Core-Tools (z.B. CLI-Ausführung, Agent/Workflow Management).
    """

    def __init__(self, registry: ModuleRegistry) -> None:
        tools = [
            execute_cli_command,
            create_custom_agent,
            update_custom_agent,
            install_skill,
            create_dag_workflow,
            create_linear_workflow,
            execute_workflow,
            remember_fact,
            recall_memory,
            forget_fact,
            confirm_forget,
            call_module_agent,
            run_pipeline,
            run_parallel_pipeline,
            generate_image,
            check_alert_state,
            record_alert,
            resolve_alert,
            wait,
        ]

        if get_settings().SCRIPT_TOOLS_ENABLED:
            tools.extend([run_script_tool, list_script_tools])

        tools.extend([create_scheduled_task, list_scheduled_tasks, delete_scheduled_task])
        tools.extend([run_agent_job, get_agent_job_result])

        super().__init__(
            name="orchestrator",
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
        )
        self.registry = registry
        self._routing_map: dict[str, str] = {}
        self._routing_dirty = True
        self._router: KeywordRouter = KeywordRouter({})
        self._refresh_routing_map()

    def _build_module_tools_schema(self) -> list[dict]:
        """JSON Tool-Defs aus Modul-Manifesten für Function Calling."""
        tools: list[dict] = []
        for manifest in self.registry.list_modules():
            tools.append({
                "type": "function",
                "function": {
                    "name": manifest.name,
                    "description": manifest.description or "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The user's request, possibly clarified or focused by the conversational context",
                            }
                        },
                        "required": ["query"],
                    },
                },
            })
        return tools

    @staticmethod
    def _recent_routing_context(chat_history: list[dict] | None, limit: int = 6) -> str:
        """Kompakter Verlauf für kontextabhängige Function-Calling-Entscheidungen."""
        if not chat_history:
            return ""
        lines: list[str] = []
        for item in chat_history[-limit:]:
            role = str(item.get("role", "")).lower()
            if role not in {"user", "assistant", "system_compaction"}:
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            label = "summary" if role == "system_compaction" else role
            lines.append(f"{label}: {content[:800]}")
        return "\n".join(lines)

    async def _get_routing_mode(self) -> tuple[bool, str]:
        """Liest den Runtime-Routing-Modus aus Redis mit Env-Fallback."""
        settings = get_settings()
        enabled = settings.LLM_ENABLE_FUNCTION_CALLING
        tool_choice = settings.LLM_TOOL_CHOICE
        try:
            redis = get_redis()
            raw = await redis.connection.get("ninko:settings:routing_mode")
            if raw:
                data = _json.loads(raw)
                enabled = bool(data.get("function_calling_enabled", enabled))
                candidate = str(data.get("tool_choice", tool_choice))
                if candidate in {"auto", "required", "none"}:
                    tool_choice = candidate
        except Exception as exc:
            logger.debug("Routing mode Redis lookup failed, using settings: %s", exc)
        return enabled, tool_choice

    # ── Tool-Call Cache (Exact + Semantic) ─────────────────────────────────────

    _TOOL_CALL_CACHE_PREFIX = "ninko:toolcall:"
    _EXACT_CACHE_TTL = 86400  # 24h
    _SEMANTIC_CACHE_TTL = 604800  # 7 days
    _SEMANTIC_THRESHOLD = 0.92
    # ZSET-Index (key → Zeitstempel) begrenzt die Zahl der Semantic-Cache-Einträge,
    # damit der Lookup nicht über einen unbegrenzt wachsenden Keyspace scannt.
    _SEMANTIC_INDEX_KEY = "ninko:toolcall:sem_index"
    _SEMANTIC_CACHE_MAX_ENTRIES = 500

    @staticmethod
    def _normalize_query_for_cache(query: str) -> str:
        """Normalisierte Query für Exact-Cache-Key (sha256)."""
        normalized = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", query.lower())).strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def _route_cache_exact_get(self, query: str) -> list[str] | None:
        """Exact-Cache Lookup (sha256). Returns module names list or None."""
        try:
            redis = get_redis()
            key = f"{self._TOOL_CALL_CACHE_PREFIX}exact:{self._normalize_query_for_cache(query)}"
            raw = await redis.connection.get(key)
            if raw:
                data = _json.loads(raw)
                return data.get("module_names")
        except Exception as exc:
            logger.debug("Exact cache miss: %s", exc)
        return None

    async def _route_cache_exact_set(self, query: str, module_names: list[str]) -> None:
        """Speichert Modul-Namen im Exact-Cache (24h TTL)."""
        try:
            redis = get_redis()
            key = f"{self._TOOL_CALL_CACHE_PREFIX}exact:{self._normalize_query_for_cache(query)}"
            payload = _json.dumps({
                "module_names": module_names,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            await redis.connection.set(key, payload, ex=self._EXACT_CACHE_TTL)
        except Exception as exc:
            logger.debug("Exact cache set failed: %s", exc)

    async def _route_cache_semantic_get(self, query: str) -> list[str] | None:
        """Semantic-Cache Lookup (cos > 0.92). Returns module names or None."""
        try:
            redis_client = get_redis()
            embeddings = get_embeddings()
            query_vec = embeddings.embed_query(query)
            # Kandidaten aus dem größenbegrenzten Index (neueste zuerst), statt über
            # alle sem:*-Keys zu scannen → beschränkt die Kosten pro Miss.
            all_keys = await redis_client.connection.zrevrange(
                self._SEMANTIC_INDEX_KEY, 0, self._SEMANTIC_CACHE_MAX_ENTRIES - 1
            )
            if not all_keys:
                return None
            module_vecs = {}
            module_payloads = {}
            raw_values = await redis_client.connection.mget(all_keys)
            stale_keys: list[str] = []
            for key, raw in zip(all_keys, raw_values, strict=False):
                if raw:
                    data = _json.loads(raw)
                    vec = data.get("embedding", [])
                    if vec:
                        module_vecs[key] = np.array(vec, dtype=np.float32)
                        module_payloads[key] = data
                else:
                    # Payload per TTL abgelaufen → verwaisten Index-Eintrag entfernen.
                    stale_keys.append(key)
            if stale_keys:
                await redis_client.connection.zrem(self._SEMANTIC_INDEX_KEY, *stale_keys)
            if not module_vecs:
                return None
            q_vec = np.array(query_vec, dtype=np.float32)
            norm_q = np.linalg.norm(q_vec)
            best_key, best_score = None, 0.0
            for key, mod_vec in module_vecs.items():
                norm_mod = np.linalg.norm(mod_vec)
                if norm_q > 0 and norm_mod > 0:
                    score = float(np.dot(q_vec, mod_vec) / (norm_q * norm_mod))
                    if score > best_score:
                        best_score, best_key = score, key
            if best_key and best_score >= self._SEMANTIC_THRESHOLD:
                return module_payloads.get(best_key, {}).get("module_names")
        except Exception as exc:
            logger.debug("Semantic cache miss: %s", exc)
        return None

    async def _route_cache_semantic_set(self, query: str, module_names: list[str]) -> None:
        """Speichert Modul-Namen im Semantic-Cache (7d TTL) mit Embedding."""
        try:
            embeddings = get_embeddings()
            query_vec = embeddings.embed_query(query)
            redis = get_redis()
            now = datetime.now(timezone.utc)
            sem_key = f"{self._TOOL_CALL_CACHE_PREFIX}sem:{hashlib.sha256(query.encode()).hexdigest()}"
            payload = _json.dumps({
                "module_names": module_names,
                "embedding": [float(v) for v in query_vec],
                "ts": now.isoformat(),
            })
            await redis.connection.set(sem_key, payload, ex=self._SEMANTIC_CACHE_TTL)
            # Index pflegen (Score = Zeitstempel) und auf Max-Größe trimmen: die
            # ältesten Einträge samt Payload entfernen, damit der Cache nicht wächst.
            await redis.connection.zadd(self._SEMANTIC_INDEX_KEY, {sem_key: now.timestamp()})
            overflow = await redis.connection.zcard(self._SEMANTIC_INDEX_KEY) - self._SEMANTIC_CACHE_MAX_ENTRIES
            if overflow > 0:
                oldest = await redis.connection.zrange(self._SEMANTIC_INDEX_KEY, 0, overflow - 1)
                if oldest:
                    await redis.connection.zrem(self._SEMANTIC_INDEX_KEY, *oldest)
                    await redis.connection.delete(*oldest)
        except Exception as exc:
            logger.debug("Semantic cache set failed: %s", exc)

    # ── Tool-Call Extraction & Dispatch ────────────────────────────────────────

    def _extract_tool_calls(self, response: AIMessage) -> list[dict]:
        """Extrahiert tool_use-Blöcke aus dem LLM Response."""
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return []
        result = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                result.append({"name": tc.get("name", ""), "arguments": tc.get("args", tc.get("arguments", {}))})
            elif hasattr(tc, "name"):
                args = getattr(tc, "args", {}) or getattr(tc, "arguments", {})
                result.append({"name": tc.name, "arguments": args if isinstance(args, dict) else {}})
        return result

    async def _dispatch_tool_call(
        self,
        tool_call: dict,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, str | None, bool, str | None]:
        """Führt einen einzelnen tool_call aus."""
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("arguments", {})
        query = tool_args.get("query", message)

        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="Modul aus Routing-Entscheidung ausgewählt",
            detail=tool_name,
            data={"module": tool_name, "arguments": tool_args},
        )

        result = await self._invoke_module_agent(
            tool_name,
            message=query,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            status_message=_t(
                de=f"Modul '{tool_name}' wird ausgeführt…",
                en=f"Executing module '{tool_name}'…",
            ),
            log_prefix="FunctionCalling",
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )
        return result

    async def _dispatch_tool_calls(
        self,
        tool_calls: list[dict],
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, str | None, bool, str | None]:
        """Führt mehrere tool_calls sequenziell aus (Pipeline-Sequenz)."""
        if len(tool_calls) == 1:
            return await self._dispatch_tool_call(
                tool_calls[0],
                message,
                chat_history,
                session_id,
                confirmed,
                wants_stream,
                token_callback,
                cancellation_check,
            )

        steps = []
        for tc in tool_calls:
            steps.append({
                "module": tc.get("name", ""),
                "task": tc.get("arguments", {}).get("query", message),
            })

        await status_bus.emit_trace(
            session_id,
            phase="pipeline",
            label="Mehrschritt-Pipeline geplant",
            detail=f"{len(steps)} Schritt(e)",
            data={"steps": steps},
            status="running",
        )
        await status_bus.emit(
            session_id,
            _t(de="Pipelines werden ausgeführt…", en="Executing pipeline…"),
        )
        try:
            from core.pipeline_engine import (
                PipelineStatus,
                PipelineStep,
                StepStatus,
                get_pipeline_engine,
            )
            engine = get_pipeline_engine()
            typed_steps = [PipelineStep.from_dict(s) for s in steps]
            auto_confirm = confirmed or await _should_safeguard_auto_confirm(session_id)
            result = await engine.execute(
                typed_steps,
                session_id=session_id,
                auto_confirm=auto_confirm,
                skip_on_error=False,
            )
            status = result.status
            if status == PipelineStatus.FAILED:
                logger.warning(
                    "Pipeline failed during routing: %s",
                    type(result.error).__name__,
                )
                safe_lines = []
                for step in result.steps:
                    if step.status == StepStatus.COMPLETED:
                        safe_lines.append(f"**{step.module}:**\n{step.result}")
                    elif step.status == StepStatus.FAILED:
                        safe_lines.append(
                            f"**{step.module} – Fehler:**\n"
                            "Interner Schrittfehler. Details wurden aus Sicherheitsgründen ausgeblendet."
                        )
                safe_markdown = "\n\n".join(safe_lines)
                return (
                    "Pipeline fehlgeschlagen: Ein interner Schritt konnte nicht abgeschlossen werden."
                    f"\n\n{safe_markdown}"
                ), None, False, None
            markdown = result.to_markdown()
            return (
                markdown if markdown else _t("Pipeline abgeschlossen.", "Pipeline completed."),
                None,
                False,
                None,
            )
        except Exception as exc:
            logger.error(
                "Pipeline execution failed: %s",
                type(exc).__name__,
                exc_info=False,
            )
            return _t(
                "Pipeline-Fehler: Bei der Verarbeitung ist ein interner Fehler aufgetreten.",
                "Pipeline error: An internal error occurred while processing the request.",
            ), None, False, None

    # ── LLM Function Calling Route ──────────────────────────────────────────────

    async def _llm_route_with_function_calling(
        self,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
        _meta_factory: Callable[[], dict] | None = None,
    ) -> tuple[str, str | None, bool, dict]:
        """Führt LLM-Native Function Calling Routing durch."""
        if _meta_factory is None:

            def _meta_factory(summary=None, *, tier=None, confidence=None):
                return {
                    "compaction_summary": summary,
                    "routing_confidence": confidence,
                    "tier_used": tier if tier is not None else 2,
                }
        function_calling_enabled, tool_choice = await self._get_routing_mode()
        if not function_calling_enabled or tool_choice == "none":
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Function-Calling-Routing deaktiviert",
                detail="Fallback auf ReAct-Orchestrator",
                data={"function_calling_enabled": function_calling_enabled, "tool_choice": tool_choice},
            )
            return await self._fallback_to_react_loop(
                message, chat_history, session_id, confirmed, wants_stream, token_callback, cancellation_check,
                _meta_factory=_meta_factory,
            )

        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="Function-Calling-Routing gestartet",
            data={"tool_choice": tool_choice},
            status="running",
        )
        await status_bus.emit(
            session_id,
            _t(de="Analysiere Routing…", en="Analyzing routing…"),
        )

        routing_context = self._recent_routing_context(chat_history)
        cache_text = f"{routing_context}\nCURRENT: {message}" if routing_context else message

        if hit_names := await self._route_cache_exact_get(cache_text):
            hit = [{"name": name, "arguments": {"query": message}} for name in hit_names]
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Routing-Cache getroffen",
                detail="Exact Cache",
                data={"tool_calls": hit},
            )
            response, module_used, did_compact, summary = await self._dispatch_tool_calls(
                hit, message, chat_history, session_id, confirmed, wants_stream, token_callback, cancellation_check
            )
            return response, module_used, did_compact, _meta_factory(summary, tier=3, confidence=1.0)
        if hit_names := await self._route_cache_semantic_get(cache_text):
            hit = [{"name": name, "arguments": {"query": message}} for name in hit_names]
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Routing-Cache getroffen",
                detail="Semantic Cache",
                data={"tool_calls": hit},
            )
            response, module_used, did_compact, summary = await self._dispatch_tool_calls(
                hit, message, chat_history, session_id, confirmed, wants_stream, token_callback, cancellation_check
            )
            return response, module_used, did_compact, _meta_factory(summary, tier=3, confidence=1.0)

        tools = self._build_module_tools_schema()
        if not tools:
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Keine Modul-Tool-Schemas verfügbar",
                detail="Fallback auf ReAct-Orchestrator",
            )
            return await self._fallback_to_react_loop(
                message, chat_history, session_id, confirmed, wants_stream, token_callback, cancellation_check,
                _meta_factory=_meta_factory,
            )

        llm = get_llm()
        system_msg = SystemMessage(
            content=(
                SYSTEM_PROMPT
                + "\n\n"
                + "ROUTING-KONTEXT: Nutze den aktuellen Gesprächsverlauf für Folgefragen. "
                + "Wenn die neue Nachricht kein neues Ziel nennt, route auf dasselbe Modul/Thema wie die letzte relevante Antwort."
                + "\n\n"
                + (await self._dynamic_prompt_appendix())
            )
        )
        messages = [system_msg]
        if routing_context:
            messages.append(SystemMessage(content=f"AKTUELLER GESPRÄCHSKONTEXT:\n{routing_context}"))
        messages.append(HumanMessage(content=message))

        try:
            llm_kwargs: dict[str, Any] = {"tools": tools}
            if tool_choice in {"auto", "required"}:
                llm_kwargs["tool_choice"] = tool_choice
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Routing-LLM wird aufgerufen",
                detail=f"{len(tools)} Modul-Schema(s) verfügbar",
                data={"tool_choice": llm_kwargs.get("tool_choice", "provider_default"), "tool_count": len(tools)},
                status="running",
            )
            response: AIMessage = await llm.ainvoke(
                messages,
                **llm_kwargs,
            )
        except Exception as exc:
            logger.warning("Function Calling LLM call failed: %s — falling back to ReAct", exc)
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Routing-LLM fehlgeschlagen",
                detail=type(exc).__name__,
                status="error",
            )
            return await self._fallback_to_react_loop(
                message, chat_history, session_id, confirmed, wants_stream, token_callback, cancellation_check,
                _meta_factory=_meta_factory,
            )

        tool_calls = self._extract_tool_calls(response)
        if not tool_calls:
            text = getattr(response, "content", "") or ""
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Routing-LLM antwortet direkt",
                detail="Keine Modul-Tool-Calls erzeugt.",
                data={"response_length": len(str(text or ""))},
            )
            return (
                str(text) if text else _t("Keine Antwort.", "No response."),
                None,
                False,
                _meta_factory(tier=2, confidence=0.0),
            )

        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="Routing-LLM hat Tool-Call(s) gewählt",
            detail=f"{len(tool_calls)} Tool-Call(s)",
            data={"tool_calls": tool_calls},
        )
        module_names = [tc["name"] for tc in tool_calls if tc.get("name")]
        if module_names:
            await self._route_cache_exact_set(cache_text, module_names)
            await self._route_cache_semantic_set(cache_text, module_names)

        response_text, module_used, did_compact, summary = await self._dispatch_tool_calls(
            tool_calls, message, chat_history, session_id, confirmed, wants_stream, token_callback, cancellation_check
        )
        return response_text, module_used, did_compact, _meta_factory(summary, tier=2)

    async def _smoke_test_function_calling(self) -> dict:
        """Testet ob das aktuelle LLM Function Calling unterstützt."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "ping",
                        "description": "Test tool that responds with pong.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "Text to echo back."}
                            },
                            "required": ["text"],
                        },
                    },
                }
            ]
            llm = get_llm()
            system_msg = SystemMessage(
                content="You are a test assistant. Use the ping tool if the user says ping."
            )
            messages = [system_msg, HumanMessage(content="ping")]
            _, tool_choice = await self._get_routing_mode()
            llm_kwargs: dict[str, Any] = {"tools": tools}
            if tool_choice in {"auto", "required"}:
                llm_kwargs["tool_choice"] = tool_choice
            response = await llm.ainvoke(messages, **llm_kwargs)
            has_tool_call = hasattr(response, "tool_calls") and bool(response.tool_calls)
            return {
                "supported": has_tool_call,
                "response_type": type(response).__name__,
                "has_tool_calls": has_tool_call,
            }
        except Exception as exc:
            return {
                "supported": False,
                "error": str(exc)[:200],
                "recommendation": "Disable Function Calling and use Embedding routing",
            }

    async def _fallback_to_react_loop(
        self,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
        _meta_factory: Callable[[], dict] | None = None,
    ) -> tuple[str, str | None, bool, dict]:
        """Fallback auf ReAct-Loop wenn Function Calling deaktiviert oder fehlschlägt."""
        if _meta_factory is None:

            def _meta_factory(summary=None, *, tier=None, confidence=None):
                return {
                    "compaction_summary": summary,
                    "routing_confidence": confidence,
                    "tier_used": tier if tier is not None else 4,
                }
        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="ReAct-Fallback gestartet",
            detail="Orchestrator beantwortet oder delegiert über seine Tools.",
            data={"agent": self.name},
            status="running",
        )
        try:
            response, did_compact = await self.invoke(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=wants_stream,
                token_callback=token_callback,
                cancellation_check=cancellation_check,
            )
        except Exception as exc:
            logger.error(
                "ReAct fallback failed: %s",
                type(exc).__name__,
                exc_info=True,
            )
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="ReAct-Fallback fehlgeschlagen",
                detail=type(exc).__name__,
                data={"agent": self.name},
                status="error",
            )
            return (
                _t(
                    "Ich kann die Anfrage gerade nicht ausführen, weil der KI-Backend-Aufruf fehlgeschlagen ist. Bitte prüfe den aktiven LLM-Provider und versuche es erneut.",
                    "I cannot execute the request right now because the AI backend call failed. Please check the active LLM provider and try again.",
                ),
                None,
                False,
                _meta_factory(tier=4),
            )
        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="ReAct-Fallback abgeschlossen",
            data={"agent": self.name, "compacted": did_compact, "response_length": len(response or "")},
        )
        return response, None, did_compact, _meta_factory(tier=4)

    async def _dynamic_prompt_appendix(self) -> str:
        """Fügt eine Übersicht aller verfügbaren Module und konfigurierten Verbindungen an."""
        parts: list[str] = []

        # 1. Immer: verfügbare Module auflisten (für call_module_agent / run_pipeline)
        modules = self.registry.list_modules()
        if modules:
            mod_lines = [f"- {m.name} ({m.display_name})" for m in modules]
            parts.append(
                "VERFÜGBARE MODULE (nutze diese Namen für call_module_agent und run_pipeline):\n"
                + "\n".join(mod_lines)
            )

        # 2. Optional: konfigurierte Verbindungen
        try:
            from core.connections import ConnectionManager

            conn_lines: list[str] = []
            for manifest in modules:
                conns = await ConnectionManager.list_connections(manifest.name)
                for c in conns:
                    d = " [DEFAULT]" if c.is_default else ""
                    conn_lines.append(
                        f"- Modul: '{manifest.name}' | connection_id: '{c.id}' "
                        f"| Name: '{c.name}' | Env: '{c.environment}'{d}"
                    )
            if conn_lines:
                parts.append(
                    "KONFIGURIERTE VERBINDUNGEN:\n"
                    + "\n".join(conn_lines)
                    + "\n\nVergewissere dich bei Aktionen immer, in welcher Umgebung/welchem Cluster "
                    "der User eingreifen will, falls die Frage ungenau ist (z.B. 'prod' vs 'staging')."
                )
        except _ORCH_RECOVERABLE_EXCEPTIONS as e:
            logger.warning("Konnte globale Connections für Orchestrator nicht laden: %s", e)

        # 3. Registrierte dynamische Agenten aus dem Pool
        try:
            from core.agent_pool import get_agent_pool

            pool = get_agent_pool()
            agent_lines: list[str] = []
            for agent_id, meta in pool._meta.items():
                if not meta.get("enabled", True):
                    continue
                name = meta.get("name", agent_id)
                desc = meta.get("description", "")
                desc_str = f" – {desc}" if desc else ""
                agent_lines.append(f"- {name} (ID: {agent_id}){desc_str}")
            if agent_lines:
                parts.append(
                    "REGISTRIERTE CUSTOM-AGENTEN (via DynamicAgentPool):\n"
                    + "\n".join(agent_lines)
                    + "\n\nDiese Agenten können über Tier-3-Routing automatisch eingesetzt werden."
                )
            else:
                parts.append(
                    "REGISTRIERTE CUSTOM-AGENTEN: Noch keine Custom-Agenten vorhanden. "
                    "Verwende `create_custom_agent`, um einen neuen Agenten anzulegen."
                )
        except _ORCH_RECOVERABLE_EXCEPTIONS as e:
            logger.warning("Konnte Agent-Pool für Orchestrator nicht laden: %s", e)

        if get_settings().SCRIPT_TOOLS_ENABLED:
            try:
                from agents.script_tools import get_available_script_tools
                from core.auth import get_current_tenant_id

                tenant_id = get_current_tenant_id() or "default"
                script_tools = await get_available_script_tools(tenant_id)
                if script_tools:
                    tool_lines = [
                        f"- {t['name']}: {t.get('description', '')}" for t in script_tools
                    ]
                    parts.append(
                        "SCRIPT-TOOLS (verfügbare Automatisierungen):\n"
                        + "\n".join(tool_lines)
                        + "\n\nNutze `run_script_tool` mit dem Tool-Namen um diese auszuführen."
                    )
            except _ORCH_RECOVERABLE_EXCEPTIONS as e:
                logger.debug("Konnte Script-Tools nicht laden: %s", e)

        return "\n\n".join(parts)

    def _invalidate_routing_cache(self) -> None:
        """Markiert die Routing-Map als veraltet (nach Modul-Änderungen aufrufen)."""
        self._routing_dirty = True

    def _refresh_routing_map(self) -> None:
        """Routing-Map aus der Registry aktualisieren (nur wenn dirty)."""
        if not self._routing_dirty:
            return
        self._routing_map = self.registry.get_routing_map()
        self._router.update_routing_map(self._routing_map)
        self._routing_dirty = False
        logger.info(
            "Routing-Map aktualisiert: %d Keywords → %d Module",
            len(self._routing_map),
            len(set(self._routing_map.values())),
        )

    def _get_readonly_tools_for_module(self, module: str) -> list:
        from core.safeguard import _TOOL_READONLY

        module_agent = self.registry.get_agent(module)
        if not module_agent:
            return []
        return [t for t in module_agent.tools if t.name in _TOOL_READONLY]

    @staticmethod
    def _wants_agent_creation(message: str) -> bool:
        """Erkennt explizite Agent-Erstellung vs. bloße How-to-Fragen."""
        msg = message.strip()
        if not msg:
            return False
        if any(p.search(msg) for p in _AGENT_HOWTO_PATTERNS):
            return False
        return any(p.search(msg) for p in _AGENT_CREATE_PATTERNS)

    @staticmethod
    def _wants_workflow_creation(message: str) -> bool:
        """Erkennt explizite Workflow-Erstellung vs. reine How-to-Fragen."""
        msg = message.strip()
        if not msg:
            return False
        if any(p.search(msg) for p in _WORKFLOW_HOWTO_PATTERNS):
            return False
        return any(p.search(msg) for p in _WORKFLOW_CREATE_PATTERNS)

    @staticmethod
    def _fallback_workflow_spec(message: str) -> dict:
        """
        Robuster Fallback für Workflow-Erstellung, wenn die LLM-JSON-Spec
        nicht zuverlässig geparst werden kann.
        """
        msg = (message or "").strip()
        lower = msg.lower()

        is_proxmox = "proxmox" in lower
        wants_telegram = "telegram" in lower

        if is_proxmox and wants_telegram:
            return {
                "name": "proxmox_cluster_monitor",
                "description": "Überwacht den Proxmox-Cluster und sendet bei Problemen eine Telegram-Benachrichtigung.",
                "steps": [
                    "[module:proxmox] Prüfe den Proxmox-Cluster auf Node-Status, Storage-Gesundheit und kritische VM-Zustände.",
                    "Fasse die Prüfergebnisse in 'OK' oder 'PROBLEM' zusammen und liste konkrete Auffälligkeiten auf.",
                    "[module:telegram] Wenn der Status 'PROBLEM' ist, sende eine Warnmeldung mit den Auffälligkeiten aus dem vorherigen Ergebnis; bei 'OK' sende keine Nachricht.",
                    "Gib eine kurze Abschlussmeldung mit den durchgeführten Prüfungen und dem Endstatus zurück.",
                ],
            }

        base_name = re.sub(r"[^a-z0-9]+", "_", lower)[:48].strip("_") or "workflow_auto"
        return {
            "name": f"{base_name}_monitor",
            "description": "Automatisch erzeugter Monitoring-Workflow auf Basis der Benutzeranfrage.",
            "steps": [
                "Analysiere die Anfrage und identifiziere die zu prüfenden Systeme und Services.",
                "Führe die relevanten Prüfungen aus und sammle alle Ergebnisse strukturiert.",
                "Bewerte die Ergebnisse und markiere den Gesamtstatus als 'OK' oder 'PROBLEM'.",
                "Wenn der Gesamtstatus 'PROBLEM' ist, sende eine passende Benachrichtigung; sonst nur den positiven Status zurückmelden.",
            ],
        }

    async def _auto_create_custom_agent(self, message: str, session_id: str) -> tuple[str, bool]:
        """Erstellt bei explizitem User-Wunsch deterministisch einen Custom-Agenten.

        Verhindert den Fall, dass der ReAct-Loop nur eine Anleitung ausgibt,
        obwohl der User einen echten Create-Call erwartet.
        """
        await status_bus.emit(
            session_id,
            _t(
                de="Erstelle Custom-Agent…",
                en="Creating custom agent…",
                fr="Création de l'agent personnalisé…",
                es="Creando agente personalizado…",
                it="Creazione agente personalizzato…",
                nl="Aangepaste agent aan het maken…",
                pl="Tworzenie agenta niestandardowego…",
                pt="Criando agente personalizado…",
                ja="カスタムエージェント作成中…",
                zh="正在创建自定义代理…",
            ),
        )

        from core.llm_factory import get_llm
        from core.agent_pool import get_agent_pool

        modules = self.registry.list_modules()
        module_names = [m.name for m in modules]
        module_line = (
            ", ".join(module_names) if module_names else "kubernetes, linux_server, docker"
        )

        prompt = f"""Du bist ein Agent-Builder für Ninko. Analysiere die User-Anfrage und erzeuge eine vollständige Agent-Spezifikation.

USER-ANFRAGE:
{message}

VERFÜGBARE MODULE:
{module_line}

=== BEISPIELE FÜR GUTE AGENTEN ===

Beispiel 1 - Kubernetes Monitoring:
{{
  "name": "k8s-failing-pod-restarter",
  "description": "Überwacht Kubernetes Cluster auf failing Pods und restartet Deployments/StatefulSets bei Bedarf",
  "system_prompt": "# K8s Failing Pod Restarter\\n\\nDu bist ein Kubernetes-Überwachungsagent.\\n\\n## Aufgaben\\n1. Prüfe auf failing Pods (Error, CrashLoopBackOff, Evicted)\\n2. Identifiziere Deployment/StatefulSet\\n3. Führe Rollout-Restart durch\\n4. Dokumentiere Aktionen\\n\\n## Arbeitsweise\\n- Nutze call_module_agent('kubernetes', 'Prüfe failing Pods...')\\n- Gruppiere Pods nach Deployment\\n- Prüfe Logs vor Restart\\n\\n## Kritische Aktionen (Bestätigung nötig)\\n- Restart von >3 Deployments gleichzeitig\\n- Löschen von Ressourcen\\n\\n## Eskalation\\n→ Wenn >10 Pods failing oder 3x Restart erfolglos, an Ninko zurückgeben"
}}

Beispiel 2 - GLPI Ticket Bearbeitung:
{{
  "name": "glpi-ticket-assistant",
  "description": "Bearbeitet GLPI Tickets automatisch: antwortet, setzt Beobachter, ändert Status",
  "system_prompt": "# GLPI Ticket Assistant\\n\\nDu automatisierst GLPI Ticket-Workflows.\\n\\n## Aufgaben\\n1. Suche neue Tickets (Status=1)\\n2. Füge Beobachter hinzu\\n3. Schreibe professionelle Antworten\\n4. Aktualisiere Status\\n\\n## Arbeitsweise\\n- Nutze call_module_agent('glpi', 'Suche Tickets...')\\n- Für User-Infos: call_module_agent('glpi', 'Suche Benutzer...')\\n- Füge Followups mit Lösungsvorschlägen hinzu\\n\\n## Kritische Aktionen (Bestätigung nötig)\\n- Schließen von Tickets ohne Lösung\\n- Löschen von Tickets\\n\\n## Eskalation\\n→ Bei komplexen technischen Problemen an Ninko zurückgeben"
}}

Beispiel 3 - Docker Container Manager:
{{
  "name": "docker-container-manager",
  "description": "Verwaltet Docker Container: prüft Status, restartet, bereinigt",
  "system_prompt": "# Docker Container Manager\\n\\nDu verwaltest Docker Container und Images.\\n\\n## Aufgaben\\n1. Liste Container mit Status\\n2. Prüfe auf exited/restarting Container\\n3. Restarte bei Bedarf\\n4. Bereinige ungenutzte Images\\n\\n## Arbeitsweise\\n- Nutze call_module_agent('docker', 'Liste Container...')\\n- Nutze call_module_agent('docker', 'Prüfe Logs...')\\n\\n## Kritische Aktionen (Bestätigung nötig)\\n- Stoppen von Produktiv-Containern\\n- Löschen von Volumes\\n- Prune-Operationen\\n\\n## Eskalation\\n→ Bei Persistenz-Problemen oder Datenverlust-Risiko an Ninko zurückgeben"
}}

=== DEINE AUFGABE ===

Analysiere die User-Anfrage oben und erzeuge ein JSON mit diesen Feldern:
- "name": 2-5 Wörter, snake_case, kein "Agent" im Namen
- "description": 1 Satz, konkrete Aufgaben
- "system_prompt": Strukturiert mit ## Aufgaben, ## Arbeitsweise, ## Kritische Aktionen, ## Eskalation

WICHTIG:
1. Das System-Prompt MUSS call_module_agent() Aufrufe enthalten für relevante Module
2. Kritische Aktionen müssen explizit erwähnt werden
3. Die Eskalations-Bedingung muss klar sein
4. Mindestens 500 Zeichen für system_prompt

ANTWORTE NUR MIT JSON, keine Erklärungen davor oder danach:

{{
  "name": "...",
  "description": "...",
  "system_prompt": "..."
}}"""

        try:
            llm = get_llm()
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=12.0,
            )
            raw = response.content if hasattr(response, "content") else str(response)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                raise ValueError("Kein JSON-Objekt in der LLM-Antwort gefunden.")
            spec = _json.loads(m.group(0))
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning("Auto-Create-Agent: Spec-Generierung fehlgeschlagen: %s", exc)
            return _t(
                de="Fehler: Die Agent-Spezifikation konnte nicht erzeugt werden. "
                "Mögliche Ursachen:\n"
                "• Die Beschreibung ist zu unklar\n"
                "• Es fehlen Angaben zu den zu nutzenden Modulen\n"
                "• Es fehlen konkrete Aufgaben oder Ziele\n\n"
                "Bitte beschreibe:\n"
                "1. WAS soll der Agent tun? (konkrete Aufgaben)\n"
                "2. WELCHE Module soll er nutzen? (z.B. kubernetes, docker, glpi)\n"
                "3. WIE soll er sich verhalten? (autonom, nur melden, immer bestätigen lassen)",
                en="Error: Failed to generate the agent specification. "
                "Possible causes:\n"
                "• Description is too unclear\n"
                "• Missing information about which modules to use\n"
                "• Missing concrete tasks or goals\n\n"
                "Please describe:\n"
                "1. WHAT should the agent do? (concrete tasks)\n"
                "2. WHICH modules should it use? (e.g. kubernetes, docker, glpi)\n"
                "3. HOW should it behave? (autonomous, report only, always ask for confirmation)",
                fr="Erreur: Échec de la génération de la spécification de l'agent. "
                "Causes possibles:\n"
                "• La description est trop vague\n"
                "• Informations manquantes sur les modules à utiliser\n"
                "• Tâches ou objectifs concrets manquants\n\n"
                "Veuillez décrire:\n"
                "1. CE QUE l'agent doit faire? (tâches concrètes)\n"
                "2. QUELS modules doit-il utiliser? (ex. kubernetes, docker, glpi)\n"
                "3. COMMENT doit-il se comporter? (autonome, rapport seulement, toujours demander confirmation)",
                es="Error: No se pudo generar la especificación del agente. "
                "Causas posibles:\n"
                "• La descripción es demasiado poco clara\n"
                "• Falta información sobre qué módulos usar\n"
                "• Faltan tareas u objetivos concretos\n\n"
                "Por favor describe:\n"
                "1. QUÉ debe hacer el agente? (tareas concretas)\n"
                "2. QUÉ módulos debe usar? (ej. kubernetes, docker, glpi)\n"
                "3. CÓMO debe comportarse? (autónomo, solo informar, siempre pedir confirmación)",
                it="Errore: Impossibile generare la specifica dell'agente. "
                "Cause possibili:\n"
                "• La descrizione è troppo poco chiara\n"
                "• Mancano informazioni su quali moduli usare\n"
                "• Mancano compiti o obiettivi concreti\n\n"
                "Per favore descrivi:\n"
                "1. COSA dovrebbe fare l'agente? (compiti concreti)\n"
                "2. QUALI moduli dovrebbe usare? (es. kubernetes, docker, glpi)\n"
                "3. COME dovrebbe comportarsi? (autonomo, solo rapporto, chiedi sempre conferma)",
                nl="Fout: De agentspecificatie kon niet worden gegenereerd. "
                "Mogelijke oorzaken:\n"
                "• Beschrijving is te onduidelijk\n"
                "• Ontbrekende informatie over welke modules te gebruiken\n"
                "• Ontbrekende concrete taken of doelen\n\n"
                "Beschrijf alstublieft:\n"
                "1. WAT moet de agent doen? (concrete taken)\n"
                "2. WELKE modules moet hij gebruiken? (bijv. kubernetes, docker, glpi)\n"
                "3. HOE moet hij zich gedragen? (autonoom, alleen rapporteren, altijd om bevestiging vragen)",
                pl="Błąd: Nie udało się wygenerować specyfikacji agenta. "
                "Możliwe przyczyny:\n"
                "• Opis jest zbyt niejasny\n"
                "• Brak informacji o modułach do użycia\n"
                "• Brak konkretnych zadań lub celów\n\n"
                "Opisz proszę:\n"
                "1. CO powinien robić agent? (konkretne zadania)\n"
                "2. JAKIE moduły powinien używać? (np. kubernetes, docker, glpi)\n"
                "3. JAK powinien się zachowywać? (autonomiczny, tylko raport, zawsze proś o potwierdzenie)",
                pt="Erro: Falha ao gerar a especificação do agente. "
                "Causas possíveis:\n"
                "• A descrição é muito pouco clara\n"
                "• Falta informação sobre quais módulos usar\n"
                "• Faltam tarefas ou objetivos concretos\n\n"
                "Por favor descreva:\n"
                "1. O QUE o agente deve fazer? (tarefas concretas)\n"
                "2. QUAIS módulos deve usar? (ex. kubernetes, docker, glpi)\n"
                "3. COMO deve se comportar? (autônomo, apenas relatar, sempre pedir confirmação)",
                ja="エラー：エージェント仕様を生成できませんでした。"
                "可能な原因：\n"
                "• 説明が不明確すぎます\n"
                "• 使用するモジュールに関する情報が不足しています\n"
                "• 具体的なタスクや目標が不足しています\n\n"
                "説明してください：\n"
                "1. エージェントは何をすべきですか？（具体的なタスク）\n"
                "2. どのモジュールを使用すべきですか？（例：kubernetes、docker、glpi）\n"
                "3. どのように振る舞うべきですか？（自律的、報告のみ、常に確認を求める）",
                zh="错误：无法生成代理规范。"
                "可能的原因：\n"
                "• 描述不够清楚\n"
                "• 缺少关于使用哪些模块的信息\n"
                "• 缺少具体的任务或目标\n\n"
                "请描述：\n"
                "1. 代理应该做什么？（具体任务）\n"
                "2. 应该使用哪些模块？（例如 kubernetes、docker、glpi）\n"
                "3. 应该如何表现？（自主、仅报告、始终要求确认）",
            ), False

        name = str(spec.get("name", "")).strip()[:80]
        description = str(spec.get("description", "")).strip()[:400]
        system_prompt = str(spec.get("system_prompt", "")).strip()

        # Validierung mit detaillierten Fehlermeldungen
        validation_errors = []

        if not name:
            validation_errors.append(
                _t(
                    de="Name fehlt",
                    en="Name missing",
                    fr="Nom manquant",
                    es="Nombre faltante",
                    it="Nome mancante",
                    nl="Naam ontbreekt",
                    pl="Brak nazwy",
                    pt="Nome faltando",
                    ja="名前がありません",
                    zh="缺少名称",
                )
            )
        elif len(name) < 3:
            validation_errors.append(
                _t(
                    de="Name zu kurz (min. 3 Zeichen)",
                    en="Name too short (min. 3 chars)",
                    fr="Nom trop court (min. 3 caractères)",
                    es="Nombre demasiado corto (mín. 3 caracteres)",
                    it="Nome troppo breve (min. 3 caratteri)",
                    nl="Naam te kort (min. 3 tekens)",
                    pl="Nazwa za krótka (min. 3 znaki)",
                    pt="Nome muito curto (mín. 3 caracteres)",
                    ja="名前が短すぎます（最小3文字）",
                    zh="名称太短（最少3个字符）",
                )
            )
        elif "agent" in name.lower() and len(name.split()) > 1:
            # Warnung aber nicht blockieren
            name = name.lower().replace("agent", "").strip(" -_")

        if not system_prompt:
            validation_errors.append(
                _t(
                    de="System-Prompt fehlt",
                    en="System prompt missing",
                    fr="Prompt système manquant",
                    es="Prompt de sistema faltante",
                    it="Prompt di sistema mancante",
                    nl="Systeemprompt ontbreekt",
                    pl="Brak promptu systemowego",
                    pt="Prompt de sistema faltando",
                    ja="システムプロンプトがありません",
                    zh="缺少系统提示",
                )
            )
        elif len(system_prompt) < 300:
            validation_errors.append(
                _t(
                    de=f"System-Prompt zu kurz ({len(system_prompt)} Zeichen, min. 300)",
                    en=f"System prompt too short ({len(system_prompt)} chars, min. 300)",
                    fr=f"Prompt système trop court ({len(system_prompt)} caractères, min. 300)",
                    es=f"Prompt de sistema demasiado corto ({len(system_prompt)} caracteres, mín. 300)",
                    it=f"Prompt di sistema troppo breve ({len(system_prompt)} caratteri, min. 300)",
                    nl=f"Systeemprompt te kort ({len(system_prompt)} tekens, min. 300)",
                    pl=f"Prompt systemowy za krótki ({len(system_prompt)} znaków, min. 300)",
                    pt=f"Prompt de sistema muito curto ({len(system_prompt)} caracteres, mín. 300)",
                    ja=f"システムプロンプトが短すぎます（{len(system_prompt)}文字、最小300文字）",
                    zh=f"系统提示太短（{len(system_prompt)}个字符，最少300个）",
                )
            )
        elif "##" not in system_prompt:
            validation_errors.append(
                _t(
                    de="System-Prompt muss ## Abschnitte enthalten",
                    en="System prompt must contain ## sections",
                    fr="Le prompt système doit contenir des sections ##",
                    es="El prompt de sistema debe contener secciones ##",
                    it="Il prompt di sistema deve contenere sezioni ##",
                    nl="Systeemprompt moet ## secties bevatten",
                    pl="Prompt systemowy musi zawierać sekcje ##",
                    pt="Prompt de sistema deve conter seções ##",
                    ja="システムプロンプトには##セクションが必要です",
                    zh="系统提示必须包含##章节",
                )
            )
        elif "call_module_agent" not in system_prompt:
            validation_errors.append(
                _t(
                    de="System-Prompt sollte call_module_agent() Aufrufe enthalten",
                    en="System prompt should contain call_module_agent() calls",
                    fr="Le prompt système devrait contenir des appels call_module_agent()",
                    es="El prompt de sistema debería contener llamadas call_module_agent()",
                    it="Il prompt di sistema dovrebbe contenere chiamate call_module_agent()",
                    nl="Systeemprompt zou call_module_agent() oproepen moeten bevatten",
                    pl="Prompt systemowy powinien zawierać wywołania call_module_agent()",
                    pt="Prompt de sistema deve conter chamadas call_module_agent()",
                    ja="システムプロンプトにはcall_module_agent()呼び出しを含める必要があります",
                    zh="系统提示应包含call_module_agent()调用",
                )
            )

        if not description:
            validation_errors.append(
                _t(
                    de="Beschreibung fehlt",
                    en="Description missing",
                    fr="Description manquante",
                    es="Descripción faltante",
                    it="Descrizione mancante",
                    nl="Beschrijving ontbreekt",
                    pl="Brak opisu",
                    pt="Descrição faltando",
                    ja="説明がありません",
                    zh="缺少描述",
                )
            )
        elif len(description) < 20:
            validation_errors.append(
                _t(
                    de="Beschreibung zu kurz (min. 20 Zeichen)",
                    en="Description too short (min. 20 chars)",
                    fr="Description trop courte (min. 20 caractères)",
                    es="Descripción demasiado corta (mín. 20 caracteres)",
                    it="Descrizione troppo breve (min. 20 caratteri)",
                    nl="Beschrijving te kort (min. 20 tekens)",
                    pl="Opis za krótki (min. 20 znaków)",
                    pt="Descrição muito curta (mín. 20 caracteres)",
                    ja="説明が短すぎます（最小20文字）",
                    zh="描述太短（最少20个字符）",
                )
            )

        if validation_errors:
            error_msg = "; ".join(validation_errors)
            logger.warning("Agent-Validierung fehlgeschlagen: %s", error_msg)
            return _t(
                de=f"Fehler: Die Agent-Spezifikation hat folgende Probleme: {error_msg}. "
                "Bitte beschreibe den Use-Case detaillierter.",
                en=f"Error: Agent specification has these issues: {error_msg}. "
                "Please describe the use case in more detail.",
                fr=f"Erreur: La spécification de l'agent a ces problèmes: {error_msg}. "
                "Veuillez décrire le cas d'utilisation plus en détail.",
                es=f"Error: La especificación del agente tiene estos problemas: {error_msg}. "
                "Por favor, describe el caso de uso con más detalle.",
                it=f"Errore: La specifica dell'agente ha questi problemi: {error_msg}. "
                "Per favore descrivi il caso d'uso in modo più dettagliato.",
                nl=f"Fout: De agentspecificatie heeft deze problemen: {error_msg}. "
                "Beschrijf het gebruiksscenario gedetailleerder.",
                pl=f"Błąd: Specyfikacja agenta ma te problemy: {error_msg}. "
                "Opisz przypadek użycia bardziej szczegółowo.",
                pt=f"Erro: A especificação do agente tem estes problemas: {error_msg}. "
                "Por favor, descreva o caso de uso com mais detalhes.",
                ja=f"エラー：エージェント仕様にこれらの問題があります：{error_msg}。"
                "ユースケースをより詳しく説明してください。",
                zh=f"错误：代理规范存在这些问题：{error_msg}。请更详细地描述用例。",
            ), False

        pool = get_agent_pool()

        # Prüfen ob Agent mit gleichem Namen bereits existiert
        existing = [a for a in pool.list_agents() if a.get("name", "").lower().replace(" ", "-") == name.lower().replace(" ", "-")]
        if existing:
            # Füge Zahl hinzu um Eindeutigkeit zu garantieren
            import time

            name = f"{name}-{int(time.time()) % 1000}"

        agent_id, _ = await pool.register(
            name=name, system_prompt=system_prompt, description=description
        )
        logger.info("Auto-Create-Agent erfolgreich: '%s' (%s)", name, agent_id)

        return _t(
            de=f"✅ Agent '{name}' wurde erstellt.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Beschreibung: {description or '-'}\n\n"
            f"Du kannst ihn jetzt im Agenten-Editor anpassen oder direkt verwenden.",
            en=f"✅ Agent '{name}' was created.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Description: {description or '-'}\n\n"
            f"You can now refine it in the agent editor or use it directly.",
            fr=f"✅ Agent '{name}' a été créé.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Description: {description or '-'}\n\n"
            f"Vous pouvez maintenant l'affiner dans l'éditeur d'agents ou l'utiliser directement.",
            es=f"✅ El agente '{name}' ha sido creado.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Descripción: {description or '-'}\n\n"
            f"Ahora puedes refinearlo en el editor de agentes o usarlo directamente.",
            it=f"✅ L'agente '{name}' è stato creato.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Descrizione: {description or '-'}\n\n"
            f"Ora puoi perfezionarlo nell'editor degli agenti o usarlo direttamente.",
            nl=f"✅ Agent '{name}' is aangemaakt.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Beschrijving: {description or '-'}\n\n"
            f"Je kunt hem nu in de agent-editor aanpassen of direct gebruiken.",
            pl=f"✅ Agent '{name}' został utworzony.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Opis: {description or '-'}\n\n"
            f"Możesz go teraz dostosować w edytorze agentów lub użyć bezpośrednio.",
            pt=f"✅ Agente '{name}' foi criado.\n\n"
            f"- ID: `{agent_id}`\n"
            f"- Descrição: {description or '-'}\n\n"
            f"Você pode refiná-lo no editor de agentes ou usá-lo diretamente.",
            ja=f"✅ エージェント '{name}' が作成されました。\n\n"
            f"- ID: `{agent_id}`\n"
            f"- 説明: {description or '-'}\n\n"
            f"エージェントエディターで調整するか、直接使用できます。",
            zh=f"✅ 代理 '{name}' 已创建。\n\n"
            f"- ID: `{agent_id}`\n"
            f"- 描述: {description or '-'}\n\n"
            f"您现在可以在代理编辑器中对其进行调整或直接使用。",
        ), False

    async def _auto_create_workflow(self, message: str, session_id: str) -> tuple[str, bool]:
        """Erstellt bei explizitem User-Wunsch deterministisch einen Workflow."""
        await status_bus.emit(
            session_id,
            _t(
                de="Erstelle Workflow…",
                en="Creating workflow…",
                fr="Création du workflow…",
                es="Creando workflow…",
                it="Creazione workflow…",
                nl="Workflow aan het maken…",
                pl="Tworzenie workflow…",
                pt="Criando workflow…",
                ja="ワークフロー作成中…",
                zh="正在创建工作流…",
            ),
        )
        from core.llm_factory import get_llm

        prompt = f"""Du bist ein Workflow-Builder für Ninko.
Erzeuge aus der User-Anfrage ein JSON für create_linear_workflow.

USER-ANFRAGE:
{message}

ANFORDERUNGEN:
- Gib NUR ein JSON-Objekt zurück.
- Felder: "name", "description", "steps"
- name: kurz und eindeutig
- description: 1 Satz
- steps: Liste aus 2 bis 6 klaren, sequentiellen Schritten
- Jeder Step ist eine konkrete Handlungsanweisung für den Orchestrator.
- Kein Markdown, keine Kommentare.

JSON-SCHEMA:
{{
  "name": "string",
  "description": "string",
  "steps": ["step 1", "step 2", "step 3"]
}}"""

        try:
            llm = get_llm()
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=18.0,
            )
            raw = response.content if hasattr(response, "content") else str(response)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                raise ValueError("Kein JSON-Objekt in der LLM-Antwort gefunden.")
            spec = _json.loads(m.group(0))
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning("Auto-Create-Workflow: Spec-Generierung fehlgeschlagen: %s", exc)
            spec = self._fallback_workflow_spec(message)
            await status_bus.emit(
                session_id,
                _t(
                    de="Workflow-Spezifikation per Fallback erzeugt.",
                    en="Workflow specification generated via fallback.",
                    fr="Spécification du workflow générée via fallback.",
                    es="Especificación del workflow generada mediante fallback.",
                    it="Specifica workflow generata tramite fallback.",
                    nl="Workflow-specificatie via fallback gegenereerd.",
                    pl="Specyfikacja workflow wygenerowana przez fallback.",
                    pt="Especificação do workflow gerada via fallback.",
                    ja="フォールバックでワークフロー仕様を生成しました。",
                    zh="已通过回退机制生成工作流规范。",
                ),
            )

        name = str(spec.get("name", "")).strip()[:120]
        description = str(spec.get("description", "")).strip()[:500]
        steps_raw = spec.get("steps", [])
        steps = [
            str(s).strip()
            for s in (steps_raw if isinstance(steps_raw, list) else [])
            if str(s).strip()
        ]

        if not name or len(steps) < 2:
            fallback = self._fallback_workflow_spec(message)
            name = str(fallback.get("name", "")).strip()[:120]
            description = str(fallback.get("description", "")).strip()[:500]
            steps = [str(s).strip() for s in fallback.get("steps", []) if str(s).strip()][:6]

        if not name or len(steps) < 2:
            return _t(
                de="Fehler: Für den Workflow konnte keine gültige Spezifikation erzeugt werden.",
                en="Error: Could not produce a valid workflow specification.",
                fr="Erreur : Impossible de produire une spécification de workflow valide.",
                es="Error: No se pudo generar una especificación de workflow válida.",
                it="Errore: impossibile produrre una specifica workflow valida.",
                nl="Fout: Kon geen geldige workflow-specificatie genereren.",
                pl="Błąd: Nie udało się wygenerować poprawnej specyfikacji workflow.",
                pt="Erro: Não foi possível gerar uma especificação de workflow válida.",
                ja="エラー：有効なワークフロー仕様を生成できませんでした。",
                zh="错误：无法生成有效的工作流规范。",
            ), False
        if len(steps) > 6:
            steps = steps[:6]

        try:
            result = await create_linear_workflow.ainvoke(
                {
                    "name": name,
                    "description": description,
                    "steps": steps,
                }
            )
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.error(
                "Auto-Create-Workflow: create_linear_workflow fehlgeschlagen: %s",
                exc,
                exc_info=True,
            )
            return _t(
                de="Fehler: Workflow konnte nicht erstellt werden.",
                en="Error: Workflow could not be created.",
                fr="Erreur : Le workflow n'a pas pu être créé.",
                es="Error: El workflow no pudo ser creado.",
                it="Errore: Il workflow non ha potuto essere creato.",
                nl="Fout: Workflow kon niet worden aangemaakt.",
                pl="Błąd: Workflow nie mógł zostać utworzony.",
                pt="Erro: O workflow não pôde ser criado.",
                ja="エラー：ワークフローを作成できませんでした。",
                zh="错误：无法创建工作流。",
            ), False

        return str(result), False

    def invalidate_routing_map(self) -> None:
        """Markiert die Routing-Map als veraltet (nach Modul-Änderungen aufrufen)."""
        self._routing_dirty = True

    # ──────────────────────────────────────────────────────────────────────
    # Routing – Thin Wrapper (Implementierung: core.router.KeywordRouter)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_bot_context(message: str) -> str:
        return KeywordRouter.strip_bot_context(message)

    def _get_module_scores(self, text: str) -> dict[str, int]:
        router = getattr(self, "_router", None)
        if router is None:
            router = KeywordRouter(getattr(self, "_routing_map", {}))
            self._router = router
        return router.get_scores(text)

    def _has_multistep_indicators(
        self,
        message: str,
        current_scores: dict[str, int],
    ) -> bool:
        router = getattr(self, "_router", None)
        if router is None:
            router = KeywordRouter(getattr(self, "_routing_map", {}))
            self._router = router
        return router.has_multistep_indicators(message, current_scores)

    @staticmethod
    def _has_confident_top_module(top_score: int, second_score: int) -> bool:
        return KeywordRouter.has_confident_top_module(top_score, second_score)

    async def resume_tool_execution(self, session_id: str) -> tuple[str, bool]:
        """
        Setzt einen pausierten Tool-Call nach Safeguard-Bestätigung fort.

        Liest den wartenden Agent-Namen aus dem Redis-Key, sucht die Instanz
        und delegiert an agent.resume_safeguard_tool(session_id).
        """
        from core.redis_client import get_redis

        redis = get_redis()
        pending_raw = await redis.connection.get(f"ninko:safeguard_tool_pending:{session_id}")
        if not pending_raw:
            return _t(
                de="Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                en="Error: No pending tool call for this session.",
                fr="Erreur : Aucun appel d'outil en attente pour cette session.",
                es="Error: No hay llamada de herramienta pendiente para esta sesión.",
                it="Errore: Nessuna chiamata di strumento in attesa per questa sessione.",
                nl="Fout: Geen openstaande tool-aanroep voor deze sessie.",
                pl="Błąd: Brak oczekującego wywołania narzędzia dla tej sesji.",
                pt="Erro: Nenhuma chamada de ferramenta pendente para esta sessão.",
                ja="エラー：このセッションには保留中のツール呼び出しがありません。",
                zh="错误：此会话没有待处理的工具调用。",
            ), False

        try:
            pending = _json.loads(pending_raw)
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning("Safeguard pending-payload unlesbar: %s", exc)
            pending = {}

        agent_name = pending.get("agent", "orchestrator")

        # Richtige Agent-Instanz finden
        if agent_name in ("orchestrator", self.name):
            agent = self
        else:
            agent = self.registry.get_agent(agent_name)
            if agent is None:
                try:
                    from core.agent_pool import get_agent_pool

                    pool = get_agent_pool()
                    pool_agent, _ = pool.get_agent_by_id(agent_name)
                    agent = pool_agent
                except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
                    logger.debug("Agent-Pool Lookup fehlgeschlagen für '%s': %s", agent_name, exc)
                    agent = None

        if agent is None:
            return _t(
                de=f"Fehler: Agent '{agent_name}' nicht gefunden.",
                en=f"Error: Agent '{agent_name}' not found.",
                fr=f"Erreur : Agent '{agent_name}' non trouvé.",
                es=f"Error: Agente '{agent_name}' no encontrado.",
                it=f"Errore: Agente '{agent_name}' non trovato.",
                nl=f"Fout: Agent '{agent_name}' niet gevonden.",
                pl=f"Błąd: Agent '{agent_name}' nie znaleziony.",
                pt=f"Erro: Agente '{agent_name}' não encontrado.",
                ja=f"エラー：エージェント '{agent_name}' が見つかりません。",
                zh=f"错误：找不到代理 '{agent_name}'。",
            ), False

        return await agent.resume_safeguard_tool(session_id)

    def _module_display_name(self, module_name: str) -> str:
        """Liefert den sichtbaren Namen eines Moduls für Status-/Fehlermeldungen."""
        manifests = {m.name: m for m in self.registry.list_modules()}
        return manifests.get(
            module_name, type("", (), {"display_name": module_name})()
        ).display_name

    async def _invoke_module_agent(
        self,
        module_name: str,
        *,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        status_message: str,
        log_prefix: str,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, str | None, bool, str | None]:
        """Führt einen Modul-Agenten mit einheitlichem Status-/Fehlerhandling aus.

        Returns:
            (response, module_name, did_compact, compaction_summary_or_None)
        """
        agent = self.registry.get_agent(module_name)
        if agent is None:
            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Modul-Agent nicht verfügbar",
                detail=module_name,
                data={"module": module_name},
                status="error",
            )
            return (
                _t(
                    de=f"Fehler: Modul '{module_name}' ist nicht verfügbar oder nicht aktiviert.",
                    en=f"Error: Module '{module_name}' is not available or not enabled.",
                    fr=f"Erreur : Le module '{module_name}' n'est pas disponible ou n'est pas activé.",
                    es=f"Error: El módulo '{module_name}' no está disponible o no está activado.",
                    it=f"Errore: Il modulo '{module_name}' non è disponibile o non è attivato.",
                    nl=f"Fout: Module '{module_name}' is niet beschikbaar of niet geactiveerd.",
                    pl=f"Błąd: Moduł '{module_name}' nie jest dostępny lub nie jest włączony.",
                    pt=f"Erro: Módulo '{module_name}' não disponível ou não ativado.",
                    ja=f"エラー：モジュール '{module_name}' が利用できないか、有効になっていません。",
                    zh=f"错误：模块 '{module_name}' 不可用或未启用。",
                ),
                module_name,
                False,
                None,
            )

        await status_bus.emit_trace(
            session_id,
            phase="agent",
            label="Modul-Agent wird aufgerufen",
            detail=module_name,
            data={"module": module_name, "message_length": len(message or "")},
            status="running",
        )
        await status_bus.emit(session_id, status_message)
        logger.info("%s '%s': %s…", log_prefix, module_name, message[:80])
        try:
            response, did_compact = await agent.invoke(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=wants_stream,
                token_callback=token_callback,
                cancellation_check=cancellation_check,
            )
            summary: str | None = None
            if did_compact and hasattr(agent, "get_last_compaction_summary"):
                summary = agent.get_last_compaction_summary()
            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Modul-Agent abgeschlossen",
                detail=module_name,
                data={"module": module_name, "compacted": did_compact, "response_length": len(response or "")},
            )
            return response, module_name, did_compact, summary
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.error(
                "%s '%s' Fehler: %s",
                log_prefix,
                module_name,
                exc,
                exc_info=True,
            )
            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Modul-Agent fehlgeschlagen",
                detail=f"{module_name}: {type(exc).__name__}",
                data={"module": module_name},
                status="error",
            )
            return (
                _t(
                    de=f"Fehler: Modul '{module_name}' hat einen Fehler gemeldet: {exc}.",
                    en=f"Error: Module '{module_name}' reported an error: {exc}.",
                    fr=f"Erreur : Le module '{module_name}' a signalé une erreur : {exc}.",
                    es=f"Error: El módulo '{module_name}' reportó un error: {exc}.",
                    it=f"Errore: Il modulo '{module_name}' ha segnalato un errore: {exc}.",
                    nl=f"Fout: Module '{module_name}' heeft een fout gerapporteerd: {exc}.",
                    pl=f"Błąd: Moduł '{module_name}' zgłosił błąd: {exc}.",
                    pt=f"Erro: Módulo '{module_name}' relatou um erro: {exc}.",
                    ja=f"エラー：モジュール '{module_name}' がエラーを報告しました: {exc}。",
                    zh=f"错误：模块 '{module_name}' 报告了错误: {exc}。",
                ),
                module_name,
                False,
                None,
            )

    async def _route_forced_target(
        self,
        force_module: str,
        *,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, str | None, bool, str | None]:
        """Direktes Routing an Modul oder Custom-Agent anhand force_module."""
        # Special-case: orchestrator ist kein Modul im Registry-Sinne.
        if force_module.strip().lower() == "orchestrator":
            # Deterministic fallback for explicit script-tool execution requests:
            # avoids brittle LLM tool-selection for this critical path.
            if get_settings().SCRIPT_TOOLS_ENABLED:
                from core.auth import get_current_tenant_id
                from agents.script_tools import execute_script_tool

                tool_name = self._extract_script_tool_name(message)
                if tool_name:
                    # Gate execution behind explicit user confirmation to prevent
                    # bypassing the normal safeguard/interrupt flow.
                    if not confirmed:
                        return (
                            _t(
                                de=f"Soll das Script-Tool '{tool_name}' ausgeführt werden? Bitte bestätige die Ausführung.",
                                en=f"Execute script tool '{tool_name}'? Please confirm to proceed.",
                                fr=f"Exécuter le script tool '{tool_name}' ? Veuillez confirmer.",
                                es=f"¿Ejecutar el script tool '{tool_name}'? Por favor confirma.",
                                it=f"Eseguire il script tool '{tool_name}'? Conferma per procedere.",
                                nl=f"Script-tool '{tool_name}' uitvoeren? Bevestig om door te gaan.",
                                pl=f"Uruchomić script tool '{tool_name}'? Potwierdź, aby kontynuować.",
                                pt=f"Executar script tool '{tool_name}'? Confirme para continuar.",
                                ja=f"スクリプトツール '{tool_name}' を実行しますか？確認してください。",
                                zh=f"执行脚本工具 '{tool_name}'？请确认以继续。",
                            ),
                            "orchestrator",
                            False,
                            None,
                        )
                    tenant_id = get_current_tenant_id() or "default"
                    result = await execute_script_tool(
                        tenant_id=tenant_id,
                        tool_name=tool_name,
                        input_data=None,
                        invoked_by="orchestrator",
                    )
                    if result.get("status") == "succeeded":
                        return (
                            (result.get("stdout") or "").strip()
                            or _t(
                                "Script-Tool erfolgreich ausgeführt (keine Ausgabe).",
                                "Script tool executed successfully (no output).",
                            ),
                            "orchestrator",
                            False,
                            None,
                        )
                    err = result.get("stderr") or result.get("error") or "Unknown error"
                    return (
                        _t(
                            f"Fehler beim Ausführen des Script-Tools '{tool_name}': {err}",
                            f"Error executing script tool '{tool_name}': {err}",
                        ),
                        "orchestrator",
                        False,
                        None,
                    )

            response, did_compact = await self.invoke(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=wants_stream,
                token_callback=token_callback,
                cancellation_check=cancellation_check,
            )
            return response, "orchestrator", did_compact, None

        agent = self.registry.get_agent(force_module)
        if agent is None:
            try:
                from core.agent_pool import get_agent_pool

                pool = get_agent_pool()
                pool_agent, pool_name = pool.get_agent_by_id(force_module)
                if pool_agent is not None:
                    await status_bus.emit(
                        session_id,
                        _t(
                            de=f"Rufe Agent '{pool_name}' direkt auf…",
                            en=f"Calling agent '{pool_name}' directly…",
                            fr=f"Appel de l'agent '{pool_name}' directement…",
                            es=f"Llamando al agente '{pool_name}' directamente…",
                            it=f"Chiamando l'agente '{pool_name}' direttamente…",
                            nl=f"Agent '{pool_name}' direct aanroepen…",
                            pl=f"Wywołuję agenta '{pool_name}' bezpośrednio…",
                            pt=f"Chamando agente '{pool_name}' diretamente…",
                            ja=f"エージェント '{pool_name}' を直接呼び出し中…",
                            zh=f"正在直接调用代理 '{pool_name}'…",
                        ),
                    )
                    logger.info(
                        "Direktes Routing an Custom-Agent '%s' (id=%s): %s…",
                        pool_name,
                        force_module,
                        message[:80],
                    )
                    try:
                        response, did_compact = await pool_agent.invoke(
                            message=message,
                            chat_history=chat_history,
                            session_id=session_id,
                            confirmed=confirmed,
                            wants_stream=wants_stream,
                            token_callback=token_callback,
                            cancellation_check=cancellation_check,
                        )
                        return response, force_module, did_compact, None
                    except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
                        logger.error(
                            "Direktes Routing Custom-Agent '%s' Fehler: %s",
                            force_module,
                            exc,
                            exc_info=True,
                        )
                        return (
                            _t(
                                f"Fehler: Agent '{pool_name}' hat einen Fehler gemeldet: {exc}.",
                                f"Error: Agent '{pool_name}' reported an error: {exc}.",
                            ),
                            force_module,
                            False,
                            None,
                        )
            except _ORCH_RECOVERABLE_EXCEPTIONS as pool_exc:
                logger.warning(
                    "Custom-Agent '%s' aus Pool konnte nicht geladen werden: %s",
                    force_module,
                    pool_exc,
                )

        display = self._module_display_name(force_module)
        return await self._invoke_module_agent(
            force_module,
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            status_message=_t(
                de=f"Rufe {display} direkt auf…",
                en=f"Calling {display} directly…",
                fr=f"Appel de {display} directement…",
                es=f"Llamando a {display} directamente…",
                it=f"Chiamando {display} direttamente…",
                nl=f"{display} direct aanroepen…",
                pl=f"Wywołuję {display} bezpośrednio…",
                pt=f"Chamando {display} diretamente…",
                ja=f"{display} を直接呼び出し中…",
                zh=f"正在直接调用 {display}…",
            ),
            log_prefix="Direktes Routing an Modul",
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )

    @staticmethod
    def _extract_script_tool_name(message: str) -> str | None:
        """Extrahiert den Tool-Namen nur bei expliziter run_script_tool-Syntax.

        Absichtlich eng gehalten: generische Backtick- oder „tool <name>"-Muster
        würden normalen erklärenden Text fälschlicherweise als Ausführungsbefehl
        interpretieren und unbeabsichtigte Ausführung triggern.
        """
        text = str(message or "")
        m = re.search(r"\brun_script_tool\s+([a-z0-9_-]{3,})\b", text, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        return None

    @staticmethod
    def _wants_fritzbox_tasmota_discovery(message: str) -> bool:
        lower = message.lower()
        return (
            "fritz" in lower
            and "tasmota" in lower
            and any(
                token in lower
                for token in ("find", "finden", "finde", "such", "suche", "liste", "list")
            )
        )

    async def _try_fritzbox_tasmota_fast_path(
        self,
        message: str,
        session_id: str,
    ) -> tuple[str, str | None, bool, str | None] | None:
        """Handle explicit FRITZ!Box Tasmota discovery without LLM routing."""
        if not self._wants_fritzbox_tasmota_discovery(message):
            return None

        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="FRITZ!Box-Tasmota-Erkennung",
            detail="Deterministischer Read-only-Fast-Path",
            data={"module": "fritzbox"},
        )
        await status_bus.emit(
            session_id,
            _t(
                de="Frage FRITZ!Box-Geräteliste ab…",
                en="Querying FRITZ!Box device list…",
            ),
        )

        get_fritz_devices = try_get_module_tool(self.registry, "fritzbox", "get_fritz_devices")
        if get_fritz_devices is None:
            return None

        try:
            devices = await get_fritz_devices.ainvoke({"connection_id": ""})
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.debug("FRITZ!Box Fast-Pfad fehlgeschlagen: %s", exc)
            return None
        if not isinstance(devices, list):
            return (
                _t(
                    de="FRITZ!Box hat keine verwertbare Geräteliste zurückgegeben.",
                    en="FRITZ!Box did not return a usable device list.",
                ),
                "fritzbox",
                False,
                None,
            )

        if devices and isinstance(devices[0], dict) and devices[0].get("error"):
            return (
                _t(
                    de=f"FRITZ!Box-Fehler: {devices[0]['error']}",
                    en=f"FRITZ!Box error: {devices[0]['error']}",
                ),
                "fritzbox",
                False,
                None,
            )

        matches = [
            d
            for d in devices
            if isinstance(d, dict)
            and "tasmota"
            in " ".join(str(d.get(k, "")) for k in ("name", "ip", "mac", "interface")).lower()
        ]
        if not matches:
            return (
                _t(
                    de=f"Keine Tasmota-Geräte in der FRITZ!Box-Geräteliste gefunden ({len(devices)} Geräte geprüft).",
                    en=f"No Tasmota devices found in the FRITZ!Box device list ({len(devices)} devices checked).",
                ),
                "fritzbox",
                False,
                None,
            )

        rows = ["| Name | IP | MAC | Status |", "|---|---|---|---|"]
        for d in matches:
            rows.append(
                "| {name} | {ip} | {mac} | {status} |".format(
                    name=str(d.get("name") or "-"),
                    ip=str(d.get("ip") or "-"),
                    mac=str(d.get("mac") or "-"),
                    status=str(d.get("status") or "-"),
                )
            )
        return (
            _t(
                de=f"Gefundene Tasmota-Geräte: {len(matches)}\n\n" + "\n".join(rows),
                en=f"Found Tasmota devices: {len(matches)}\n\n" + "\n".join(rows),
            ),
            "fritzbox",
            False,
            None,
        )

    async def route(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
        confirmed: bool = False,
        force_module: str | None = None,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, str | None, bool, dict]:
        """
        LLM-Native Function Calling Routing (primär) mit 4-Tier-Fallback.

        Primärpfad: LLM mit Tool-Schema → tool_use-Blöcke → Dispatch.
        Fallback: 4-Tier-Routing (Keyword + Embedding + ReAct).

        Returns:
            tuple[str, str | None, bool, dict]:
                (Antwort, Modul oder None, did_compact, routing_meta)
                routing_meta enthält:
                  - compaction_summary: str | None
                  - routing_confidence: float | None
                  - tier_used: int
        """
        tier_used = 2
        routing_confidence: float | None = None
        status_bus.set_session_id(session_id)
        await status_bus.emit_trace(
            session_id,
            phase="request",
            label="Orchestrator gestartet",
            data={
                "force_module": force_module,
                "confirmed": confirmed,
                "history_messages": len(chat_history or []),
            },
            status="running",
        )
        await status_bus.emit(
            session_id,
            _t(
                de="Analysiere deine Anfrage…",
                en="Analyzing your request…",
            ),
        )

        self._refresh_routing_map()

        def _build_meta(
            summary: str | None = None,
            *,
            tier: int | None = None,
            confidence: float | None = None,
        ) -> dict:
            return {
                "compaction_summary": summary,
                "routing_confidence": confidence if confidence is not None else routing_confidence,
                "tier_used": tier if tier is not None else tier_used,
            }

        # ── Deterministische Fast-Paths (kein LLM-Routing nötig) ────────────
        if force_module:
            tier_used = 0
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Direktes Ziel vorgegeben",
                detail=force_module,
                data={"force_module": force_module},
            )
            response, module_used, did_compact, summary = await self._route_forced_target(
                force_module,
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=wants_stream,
                token_callback=token_callback,
                cancellation_check=cancellation_check,
            )
            return response, module_used, did_compact, _build_meta(summary, tier=0, confidence=1.0)

        if self._wants_agent_creation(message):
            logger.info("Explizite Agent-Erstellungs-Intention → Auto-Create-Fast-Path.")
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Agent-Erstellung erkannt",
                detail="Deterministischer Fast-Path",
            )
            response, did_compact = await self._auto_create_custom_agent(message, session_id)
            tier_used = 1
            routing_confidence = 1.0
            return response, "orchestrator", did_compact, _build_meta(tier=1, confidence=1.0)

        if self._wants_workflow_creation(message):
            logger.info("Explizite Workflow-Erstellungs-Intention → Auto-Create-Fast-Path.")
            await status_bus.emit_trace(
                session_id,
                phase="routing",
                label="Workflow-Erstellung erkannt",
                detail="Deterministischer Fast-Path",
            )
            response, did_compact = await self._auto_create_workflow(message, session_id)
            tier_used = 1
            routing_confidence = 1.0
            return response, "orchestrator", did_compact, _build_meta(tier=1, confidence=1.0)

        fast_path = await self._try_fritzbox_tasmota_fast_path(message, session_id)
        if fast_path is not None:
            tier_used = 1
            routing_confidence = 1.0
            response, module_used, did_compact, summary = fast_path
            return response, module_used, did_compact, _build_meta(summary, tier=1, confidence=1.0)

        status_fast_path = await self._try_infra_status_fast_path(
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )
        if status_fast_path is not None:
            tier_used = 1
            routing_confidence = 1.0
            response, module_used, did_compact, summary = status_fast_path
            return response, module_used, did_compact, _build_meta(summary, tier=1, confidence=1.0)

        # ── LLM-Native Function Calling Routing (primär) ────────────────────
        function_calling_enabled, _ = await self._get_routing_mode()
        if function_calling_enabled:
            return await self._llm_route_with_function_calling(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
                wants_stream=wants_stream,
                token_callback=token_callback,
                cancellation_check=cancellation_check,
                _meta_factory=_build_meta,
            )

        # ── Fallback: ReAct-Loop ────────────────────────────────────────────────
        return await self._fallback_to_react_loop(
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
            _meta_factory=_build_meta,
        )

    async def _try_infra_status_fast_path(
        self,
        *,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, str | None, bool, str | None] | None:
        """Route simple infra status questions without LLM routing."""
        text = (message or "").casefold()
        has_status_intent = any(
            token in text
            for token in (
                "status",
                "health",
                "gesund",
                "zustand",
                "overview",
                "übersicht",
                "uebersicht",
            )
        )
        if not has_status_intent:
            return None

        target_module = ""
        if any(token in text for token in ("proxmox", "pve")):
            target_module = "proxmox"
        elif any(token in text for token in ("kubernetes", "k8s", "cluster")):
            target_module = "kubernetes"

        if not target_module:
            return None

        await status_bus.emit_trace(
            session_id,
            phase="routing",
            label="Infrastruktur-Status erkannt",
            detail=target_module,
            data={"module": target_module},
        )
        return await self._invoke_module_agent(
            target_module,
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            status_message=_t(
                de=f"Prüfe den Status von {self._module_display_name(target_module)}…",
                en=f"Checking {self._module_display_name(target_module)} status…",
            ),
            log_prefix="Status-Fast-Path an Modul",
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )


# ── Globaler Singleton (gesetzt von main.py) ─────────────────────────────────
_global_orchestrator: "OrchestratorAgent | None" = None


def get_orchestrator() -> "OrchestratorAgent | None":
    """Gibt die globale Orchestrator-Instanz zurück (nach App-Start verfügbar)."""
    return _global_orchestrator


def set_orchestrator(orchestrator: "OrchestratorAgent") -> None:
    """Wird von main.py nach Erstellung des Orchestrators aufgerufen."""
    global _global_orchestrator
    _global_orchestrator = orchestrator
