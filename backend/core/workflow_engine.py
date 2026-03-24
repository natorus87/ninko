"""
Ninko – Workflow Execution Engine.
Traversiert einen Workflow-DAG asynchron und schreibt Statusupdates nach Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

# Per-workflow asyncio locks prevent concurrent R-M-W races on run state
_run_update_locks: dict[str, asyncio.Lock] = {}

logger = logging.getLogger("ninko.workflow_engine")

REDIS_KEY_RUNS_PREFIX = "ninko:workflow:runs:"
REDIS_KEY_RUN_INDEX = "ninko:workflow:run_index"


class WorkflowEngine:
    """Asynchrone Workflow-Ausführungsmaschine."""

    def __init__(self, redis, orchestrator):
        self.redis = redis
        self.orchestrator = orchestrator

    async def execute(self, workflow: dict, run_id: str) -> None:
        """Führt einen Workflow aus und schreibt Statusupdates in Redis."""
        workflow_id = workflow["id"]

        # Run-Index für schnelle Lookup
        index_raw = await self.redis.connection.get(REDIS_KEY_RUN_INDEX)
        run_index = json.loads(index_raw) if index_raw else {}
        run_index[run_id] = workflow_id
        await self.redis.connection.set(REDIS_KEY_RUN_INDEX, json.dumps(run_index))

        # Nodes und Edges aufbauen
        nodes = {n["id"]: n for n in workflow.get("nodes", [])}
        edges = workflow.get("edges", [])

        # Ausgangsnode finden (trigger oder erster ohne eingehende Kanten)
        incoming = {e["target_id"] for e in edges}
        start_nodes = [n for nid, n in nodes.items() if nid not in incoming]

        # Globale Variablen
        variables = {v["name"]: v["value"] for v in workflow.get("variables", [])}

        # Step-Initialisierung
        step_map: dict[str, dict] = {}
        for node_id, node in nodes.items():
            step_map[node_id] = {
                "node_id": node_id,
                "node_type": node.get("type", ""),
                "node_label": node.get("label", node.get("type", "")),
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "output": None,
                "error": None,
            }

        await self._update_run(workflow_id, run_id, "running", list(step_map.values()), variables)

        error_occurred = False
        final_status = "succeeded"
        t_run_start = datetime.now(timezone.utc)

        try:
            # BFS-Traversal durch den DAG
            queue = [n["id"] for n in start_nodes]
            visited = set()

            while queue:
                node_id = queue.pop(0)
                if node_id in visited:
                    continue
                visited.add(node_id)

                node = nodes.get(node_id)
                if not node:
                    continue

                step = step_map[node_id]
                node_type = node.get("type", "")
                node_config = node.get("config", {})

                # Node starten
                t_start = datetime.now(timezone.utc)
                step["status"] = "running"
                step["started_at"] = t_start.isoformat()
                await self._update_run(workflow_id, run_id, "running", list(step_map.values()), variables)

                try:
                    output, next_label = await self._execute_node(node_type, node_config, variables)
                    t_end = datetime.now(timezone.utc)
                    duration = int((t_end - t_start).total_seconds() * 1000)

                    step["status"] = "succeeded"
                    step["finished_at"] = t_end.isoformat()
                    step["duration_ms"] = duration
                    step["output"] = str(output)[:500] if output else None

                except Exception as exc:
                    t_end = datetime.now(timezone.utc)
                    step["status"] = "failed"
                    step["finished_at"] = t_end.isoformat()
                    step["error"] = str(exc)[:300]
                    logger.error("Workflow-Step fehlgeschlagen: node=%s err=%s", node_id, exc)
                    error_occurred = True
                    final_status = "failed"
                    # Bei Fehler: abbrechen
                    await self._update_run(workflow_id, run_id, "failed", list(step_map.values()), variables, error=str(exc)[:300])
                    return

                await self._update_run(workflow_id, run_id, "running", list(step_map.values()), variables)

                # Nächste Nodes bestimmen
                for edge in edges:
                    if edge["source_id"] == node_id:
                        # Bei Conditions: nur den Pfad mit passendem Label nehmen
                        if next_label and edge.get("label") and edge["label"] != next_label:
                            step_map[edge["target_id"]]["status"] = "skipped"
                            continue
                        if edge["target_id"] not in visited:
                            queue.append(edge["target_id"])

        except Exception as exc:
            logger.error("Workflow-Ausführung fehlgeschlagen: %s", exc)
            final_status = "failed"

        finally:
            # Verbleibende pending Steps als skipped markieren
            for step in step_map.values():
                if step["status"] == "pending":
                    step["status"] = "skipped"

            run_duration_ms = int((datetime.now(timezone.utc) - t_run_start).total_seconds() * 1000)
            await self._update_run(workflow_id, run_id, final_status, list(step_map.values()), variables, duration_ms=run_duration_ms)
            logger.info("Workflow %s abgeschlossen: %s (run=%s, %.1fs)", workflow.get("name", ""), final_status, run_id, run_duration_ms / 1000)

    async def _execute_node(self, node_type: str, config: dict, variables: dict) -> tuple[Any, str | None]:
        """Führt einen einzelnen Node-Typ aus. Gibt (output, next_label) zurück."""

        if node_type == "trigger":
            return "Workflow gestartet", None

        elif node_type == "end":
            return config.get("status", "succeeded"), None

        elif node_type == "variable":
            name = config.get("name", "")
            value = self._interpolate(config.get("value", ""), variables)
            if name:
                variables[name] = value
            return f"Variable {name} = {value}", None

        elif node_type == "agent":
            agent_id = config.get("agent_id", "")
            prompt = self._interpolate(config.get("prompt", f"Führe Aufgabe aus (Agent: {agent_id})"), variables)
            if self.orchestrator:
                # session_id logisch für Workflow isolieren (history bleibt leer für Einzelschritt)
                response_text, module_used, _ = await self.orchestrator.route(message=prompt, chat_history=[])
                output = response_text
                variables["previous_output"] = output
                return output, None
            return f"Agent {agent_id} aufgerufen (kein Orchestrator)", None

        elif node_type == "condition":
            expr = config.get("expression", "")
            previous = variables.get("previous_output", "")
            # Einfache Auswertung: output.contains("x")
            match = re.match(r"output\.contains\(['\"](.+?)['\"]\)", expr)
            if match:
                result = match.group(1).lower() in previous.lower()
            else:
                # Fallback: immer true
                result = True
            label = config.get("true_label", "true") if result else config.get("false_label", "false")
            return f"Bedingung: {result}", label

        elif node_type == "loop":
            # Vereinfacht: direkt weiter
            var_name = config.get("variable", "items")
            items = variables.get(var_name, [])
            return f"Loop über {len(items) if isinstance(items, list) else '?'} Elemente", None

        else:
            return f"Unbekannter Node-Typ: {node_type}", None

    def _interpolate(self, template: str, variables: dict) -> str:
        """Ersetzt {variable_name} Platzhalter."""
        for key, value in variables.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    async def _update_run(self, workflow_id: str, run_id: str, status: str, steps: list, variables: dict, error: str | None = None, duration_ms: int | None = None) -> None:
        """Schreibt den aktuellen Run-Status nach Redis (mit Lock gegen Race Conditions)."""
        if workflow_id not in _run_update_locks:
            _run_update_locks[workflow_id] = asyncio.Lock()
        key = f"{REDIS_KEY_RUNS_PREFIX}{workflow_id}"
        now = datetime.now(timezone.utc).isoformat()

        async with _run_update_locks[workflow_id]:
            runs_raw = await self.redis.connection.get(key)
            runs = json.loads(runs_raw) if runs_raw else []

            run_idx = next((i for i, r in enumerate(runs) if r["id"] == run_id), None)
            if run_idx is not None:
                runs[run_idx]["status"] = status
                runs[run_idx]["steps"] = steps
                runs[run_idx]["variables"] = variables
                if error:
                    runs[run_idx]["error"] = error
                if status in ("succeeded", "failed"):
                    runs[run_idx]["finished_at"] = now
                    if duration_ms is not None:
                        runs[run_idx]["duration_ms"] = duration_ms
                await self.redis.connection.set(key, json.dumps(runs))
