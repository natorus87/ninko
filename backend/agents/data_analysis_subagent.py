"""
DataAnalysisSubagent – Read-only Subagent für datenintensive Aufgaben.

Dieser Agent arbeitet in einem isolierten Context und gibt nur kompakte
Zusammenfassungen zurück. Er absorbiert große Datenmengen, damit der
Orchestrator nur ~300 Tokens statt ~15.000 erhält.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from typing import Any, TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from agents.base_agent import _t
from core.llm_factory import get_llm, get_llm_generation
from core import status_bus

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = logging.getLogger("ninko.agents.data_analysis_subagent")

# Timeout für den Subagent (5 Minuten)
_DEFAULT_SUBAGENT_TIMEOUT = 300

# Max. Output-Tokens für Summary (verhindert Context-Overflow)
_MAX_SUMMARY_TOKENS = 500

# Module-level dict für aktive Subagents (für Retry/Error Recovery)
_active_subagents: dict[str, "DataAnalysisSubagent"] = {}


# Error-Typen für Retry-Logik
class ErrorType:
    RETRYABLE = "retryable"
    PERMANENT = "permanent"
    PARTIAL = "partial"


class StepInfo:
    """Information über einen einzelnen Schritt (Tool-Call)."""

    def __init__(
        self,
        step_id: str,
        tool_name: str,
        args: dict,
        status: str = "running",
        result: Any = None,
        error: str | None = None,
        error_type: str | None = None,
        duration_ms: float = 0.0,
    ):
        self.step_id = step_id
        self.tool_name = tool_name
        self.args = args
        self.status = status  # running, done, error
        self.result = result
        self.error = error
        self.error_type = error_type
        self.duration_ms = duration_ms

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "args": self.args,
            "status": self.status,
            "result": self.result if self.status == "done" else None,
            "error": self.error,
            "error_type": self.error_type,
            "duration_ms": self.duration_ms,
        }


class DataAnalysisSubagent:
    """
    Generischer Subagent für datenintensive Aufgaben.

    - Eigener isolierter Context (belastet Orchestrator nicht)
    - Nur read-only Tools (list_*, search_*, get_*, check_*)
    - Gibt kompakte Summary zurück, keine Rohdaten
    - WebSocket Step-Streaming für Live-Visualisierung
    - Retry-Mechanismus für fehlgeschlagene Schritte
    """

    def __init__(self, module: str, tools: list["BaseTool"], session_id: str = ""):
        self.module = module
        self.tools = tools
        self.session_id = session_id
        self._llm = get_llm()
        self._llm_generation = get_llm_generation()
        self._failed_steps: dict[str, StepInfo] = {}
        self._completed_steps: list[StepInfo] = []
        self._current_steps: dict[str, StepInfo] = {}

        # ReAct-Agent erstellen
        self._agent = create_react_agent(model=self._llm, tools=self.tools)

        logger.info(
            "DataAnalysisSubagent für Modul '%s' initialisiert (%d Tools).",
            module,
            len(tools),
        )

    def _get_system_prompt(self, task: str, sub_tasks: list[str] | None = None) -> str:
        """Erzeugt den System-Prompt für den Data Analysis Subagent."""
        sub_tasks_str = ""
        if sub_tasks:
            sub_tasks_str = f"""
## Aufgaben-Unterteilung
Diese Anfrage wurde in {len(sub_tasks)} Teilaufgaben unterteilt:
"""
            for i, st in enumerate(sub_tasks, 1):
                sub_tasks_str += f"{i}. {st}\n"

        return f"""# Data Analysis Subagent

Du analysierst große Datenmengen für das Modul "{self.module}".

## Ursprüngliche Anfrage
{task}
{sub_tasks_str}
## Strategie

1. **Verstehe die Anfrage:** Welche Filter, Gruppierung, Sortierung werden benötigt?
2. **Iterativ abfragen:** Nutze limit-Parameter, nicht alles auf einmal
3. **Lokal aggregieren:** Zähle, gruppiere, sortiere in deinem eigenen Context
4. **Kompakt zusammenfassen:**
   - Statistiken (total, Verteilung nach Status/Assignee/etc.)
   - Top-N Items (nach Relevanz/Alter/Priorität) – max 10-20 Items
   - Insights (Auffälligkeiten, Trends)
   - NIEMALS vollständige Listen (> 100 Ergebnisse: aggregiere statt aufzulisten)

## Wichtige Regeln

- Gib NUR die Zusammenfassung zurück, keine Rohdaten
- Max {_MAX_SUMMARY_TOKENS} Tokens Output
- Wenn > 100 Ergebnisse: aggregiere statt aufzulisten
- Nutze Tools effizient – iterativ mit Limits
- Priorisiere aktuelle/kritische Daten
- Gruppiere nach relevanten Dimensionen (Status, Assignee, Priorität, Zeit)

## Output-Format

Strukturierte Zusammenfassung in natürlicher Sprache mit:
- Gesamtzahl
- Verteilung (z.B. "Offen: 47, In Bearbeitung: 23")
- Top-N wenn relevant
- Auffälligkeiten/Trends
"""

    async def _emit_step(
        self,
        step_type: str,
        step_id: str,
        title: str,
        description: str = "",
        status: str = "running",
        details: dict | None = None,
        error: str | None = None,
        error_type: str | None = None,
        suggested_retry: bool = False,
    ) -> None:
        """Emitiert einen Step-Event über SSE (status_bus)."""
        if not self.session_id:
            return

        event: dict = {
            "type": "subagent_step",
            "step_type": step_type,
            "step_id": step_id,
            "title": title,
            "description": description,
            "status": status,
            "module": self.module,
        }
        if details:
            event["details"] = details
        if error:
            event["error"] = error
            event["error_type"] = error_type
            event["suggested_retry"] = suggested_retry

        # Strukturiertes Event über SSE (erreichbar während aktivem Chat-Request)
        await status_bus.emit_event(self.session_id, event)

        # Speichere im Redis für nachträgliche Abfrage (als JSON, nicht str())
        try:
            from core.redis_client import get_redis

            redis = get_redis()
            key = f"ninko:subagent:steps:{self.session_id}"
            await redis.connection.lpush(key, _json.dumps(event))
            await redis.connection.ltrim(key, 0, 99)  # Max 100 Steps
            await redis.connection.expire(key, 3600)  # 1h TTL
        except Exception as exc:
            logger.debug("Step-Event konnte nicht in Redis persistiert werden: %s", exc)

    async def _run_with_step_tracking(
        self,
        messages: list,
        config: dict,
    ) -> tuple[str, list[StepInfo]]:
        """
        Führt den Agenten aus und trackt alle Tool-Calls als Steps.

        Returns:
            tuple: (final_response, completed_steps)
        """
        step_counter = 0
        completed_steps: list[StepInfo] = []

        try:
            from langchain_core.callbacks import AsyncCallbackHandler

            class StepTrackingHandler(AsyncCallbackHandler):
                def __init__(self, subagent: DataAnalysisSubagent):
                    self.subagent = subagent
                    self.start_times: dict[str, float] = {}

                async def on_tool_start(
                    self, serialized: dict, input_str: str, *, run_id: str, **kwargs
                ) -> None:
                    nonlocal step_counter
                    step_counter += 1
                    tool_name = serialized.get("name", "unknown")
                    step_id = f"step_{step_counter}_{tool_name}"
                    self.start_times[str(run_id)] = time.time()

                    try:
                        args = _json.loads(input_str) if input_str else {}
                    except Exception:
                        args = {"input": input_str}

                    step_info = StepInfo(
                        step_id=step_id,
                        tool_name=tool_name,
                        args=args,
                        status="running",
                    )
                    # Keyed by run_id für zuverlässiges Lookup in on_tool_end/error
                    self.subagent._current_steps[str(run_id)] = step_info

                    await self.subagent._emit_step(
                        step_type="step_start",
                        step_id=step_id,
                        title=tool_name,
                        description=str(args)[:200],
                        status="running",
                    )

                async def on_tool_end(
                    self, output: Any, *, run_id: str, **kwargs
                ) -> None:
                    step_info = self.subagent._current_steps.pop(str(run_id), None)
                    if not step_info:
                        return

                    elapsed = (
                        time.time() - self.start_times.get(str(run_id), time.time())
                    ) * 1000
                    step_info.duration_ms = elapsed
                    step_info.status = "done"

                    result_size = 0
                    try:
                        result_str = (
                            _json.dumps(output)
                            if not isinstance(output, str)
                            else output
                        )
                        result_size = len(result_str)
                    except Exception as exc:
                        logger.debug("Output-Größe konnte nicht ermittelt werden: %s", exc)

                    await self.subagent._emit_step(
                        step_type="step_done",
                        step_id=step_info.step_id,
                        title=step_info.tool_name,
                        status="done",
                        details={
                            "result_size": result_size,
                            "duration_ms": round(elapsed, 1),
                        },
                    )

                    completed_steps.append(step_info)
                    self.subagent._completed_steps.append(step_info)

                async def on_tool_error(
                    self, error: Exception, *, run_id: str, **kwargs
                ) -> None:
                    step_info = self.subagent._current_steps.pop(str(run_id), None)
                    if not step_info:
                        return

                    elapsed = (
                        time.time() - self.start_times.get(str(run_id), time.time())
                    ) * 1000
                    step_info.duration_ms = elapsed
                    step_info.status = "error"
                    step_info.error = str(error)

                    error_type = ErrorType.PERMANENT
                    suggested_retry = False
                    if isinstance(
                        error, (TimeoutError, ConnectionError, asyncio.TimeoutError)
                    ):
                        error_type = ErrorType.RETRYABLE
                        suggested_retry = True
                    elif (
                        isinstance(error, ValueError)
                        and "rate" in str(error).lower()
                    ):
                        error_type = ErrorType.RETRYABLE
                        suggested_retry = True

                    step_info.error_type = error_type

                    await self.subagent._emit_step(
                        step_type="step_error",
                        step_id=step_info.step_id,
                        title=step_info.tool_name,
                        status="error",
                        error=str(error),
                        error_type=error_type,
                        suggested_retry=suggested_retry,
                    )

                    self.subagent._failed_steps[step_info.step_id] = step_info

            handler = StepTrackingHandler(self)
            config["callbacks"] = [handler]

            # Agent ausführen
            result = await asyncio.wait_for(
                self._agent.ainvoke({"messages": messages}, config=config),
                timeout=_DEFAULT_SUBAGENT_TIMEOUT,
            )

            # Extrahiere finale Antwort
            all_messages = result.get("messages", [])
            ai_messages = [
                m for m in all_messages if isinstance(m, AIMessage) and m.content
            ]

            if ai_messages:
                # Letzte AI-Nachricht
                raw_response = ai_messages[-1].content
                if isinstance(raw_response, list):
                    # Multimodale Inhalte extrahieren
                    text_parts = [
                        item.get("text", str(item))
                        for item in raw_response
                        if isinstance(item, dict)
                    ]
                    raw_response = "".join(text_parts)
                return str(raw_response), completed_steps
            else:
                return "", completed_steps

        except asyncio.TimeoutError:
            logger.warning(
                "DataAnalysisSubagent Timeout nach %ds", _DEFAULT_SUBAGENT_TIMEOUT
            )
            return _t(
                de="Zeitüberschreitung bei der Datenanalyse. Die Abfrage dauerte zu lange.",
                en="Timeout during data analysis. The query took too long.",
            ), completed_steps
        except Exception as e:
            logger.error("DataAnalysisSubagent Fehler: %s", e, exc_info=True)
            return _t(
                de=f"Fehler bei der Datenanalyse: {e}",
                en=f"Error during data analysis: {e}",
            ), completed_steps

    async def invoke(
        self,
        task: str,
        chat_history: list[dict] | None = None,
        sub_tasks: list[str] | None = None,
    ) -> tuple[str, bool]:
        """
        Führt die datenintensive Analyse aus.

        Args:
            task: Die ursprüngliche User-Anfrage
            chat_history: Optional Chat-History für Kontext
            sub_tasks: Optionale Liste von Teilaufgaben

        Returns:
            tuple: (summary, did_compact) – kompakte Zusammenfassung
        """
        # LLM neu initialisieren wenn Provider gewechselt wurde
        current_gen = get_llm_generation()
        if current_gen != self._llm_generation:
            self._llm = get_llm()
            self._agent = create_react_agent(model=self._llm, tools=self.tools)
            self._llm_generation = current_gen

        # System-Prompt erstellen
        system_prompt = self._get_system_prompt(task, sub_tasks)

        # Nachrichten aufbauen
        messages: list = [SystemMessage(content=system_prompt)]

        # Chat-History hinzufügen (nur letzte 3 Nachrichten für Kontext)
        if chat_history:
            for msg in chat_history[-3:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        # Aktuelle Aufgabe
        messages.append(HumanMessage(content=task))

        # Config für Execution
        run_config = {"recursion_limit": 10000}

        # Ausführen mit Step-Tracking
        await self._emit_step(
            step_type="subagent_start",
            step_id="subagent_init",
            title=_t(
                de=f"Analysiere {self.module} Daten…",
                en=f"Analyzing {self.module} data…",
            ),
            status="running",
        )

        response, completed_steps = await self._run_with_step_tracking(
            messages, run_config
        )

        await self._emit_step(
            step_type="subagent_done",
            step_id="subagent_init",
            title=_t(
                de="Analyse abgeschlossen",
                en="Analysis completed",
            ),
            status="done",
            details={
                "steps_completed": len(completed_steps),
                "steps_failed": len(self._failed_steps),
            },
        )

        # did_compact ist immer True (das ist der Zweck des Subagents)
        return response, True

    async def retry_step(self, step_id: str) -> dict:
        """
        Versucht einen fehlgeschlagenen Step erneut auszuführen.

        Args:
            step_id: ID des fehlgeschlagenen Steps

        Returns:
            dict: Status der Retry-Operation
        """
        if step_id not in self._failed_steps:
            return {
                "status": "error",
                "error": "Step not found or already completed",
            }

        step_info = self._failed_steps[step_id]
        tool_name = step_info.tool_name
        args = step_info.args

        # Finde das passende Tool
        target_tool = None
        for tool in self.tools:
            if tool.name == tool_name:
                target_tool = tool
                break

        if not target_tool:
            return {
                "status": "error",
                "error": f"Tool '{tool_name}' not found",
            }

        # Emit step_start für Retry
        await self._emit_step(
            step_type="step_start",
            step_id=f"{step_id}_retry",
            title=f"{tool_name} (retry)",
            status="running",
        )

        try:
            start_time = time.time()
            result = await target_tool.ainvoke(args)
            elapsed = (time.time() - start_time) * 1000

            # Erfolg
            del self._failed_steps[step_id]

            await self._emit_step(
                step_type="step_done",
                step_id=f"{step_id}_retry",
                title=f"{tool_name} (retry)",
                status="done",
                details={
                    "duration_ms": round(elapsed, 1),
                    "result_size": len(str(result)),
                },
            )

            return {"status": "success", "result": result}

        except Exception as e:
            error_type = ErrorType.RETRYABLE
            suggested_retry = True

            if isinstance(e, (ValueError, KeyError, TypeError)):
                error_type = ErrorType.PERMANENT
                suggested_retry = False

            await self._emit_step(
                step_type="step_error",
                step_id=f"{step_id}_retry",
                title=f"{tool_name} (retry)",
                status="error",
                error=str(e),
                error_type=error_type,
                suggested_retry=suggested_retry,
            )

            return {
                "status": "error",
                "error": str(e),
                "suggested_retry": suggested_retry,
            }

    def get_step_status(self) -> dict:
        """Gibt den aktuellen Status aller Steps zurück."""
        return {
            "completed": [s.to_dict() for s in self._completed_steps],
            "failed": {k: v.to_dict() for k, v in self._failed_steps.items()},
            "current": {k: v.to_dict() for k, v in self._current_steps.items()},
        }


def _get_or_create_subagent(
    session_id: str,
    module: str,
    tools: list["BaseTool"],
) -> DataAnalysisSubagent:
    """Gibt einen bestehenden Subagent zurück oder erstellt einen neuen."""
    key = f"{session_id}:{module}"
    if key not in _active_subagents:
        _active_subagents[key] = DataAnalysisSubagent(
            module=module,
            tools=tools,
            session_id=session_id,
        )
    return _active_subagents[key]


def _cleanup_subagent(session_id: str, module: str) -> None:
    """Entfernt einen Subagent aus dem aktiven Cache."""
    key = f"{session_id}:{module}"
    _active_subagents.pop(key, None)


def get_subagent_for_session(
    session_id: str, module: str
) -> DataAnalysisSubagent | None:
    """Gibt den aktiven Subagent für eine Session/Modul-Kombination zurück."""
    key = f"{session_id}:{module}"
    return _active_subagents.get(key)


def list_active_subagents() -> dict[str, str]:
    """Listet alle aktiven Subagents auf (für Monitoring)."""
    return {key: agent.module for key, agent in _active_subagents.items()}
