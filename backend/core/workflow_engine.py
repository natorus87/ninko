"""
Ninko – Workflow Execution Engine.
Traversiert einen Workflow-DAG asynchron und schreibt Statusupdates nach Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

# Per-workflow asyncio locks prevent concurrent R-M-W races on run state
_run_update_locks: dict[str, asyncio.Lock] = {}

logger = logging.getLogger("ninko.workflow_engine")

_WORKFLOW_EXCEPTIONS = (
    TypeError,
    ValueError,
    KeyError,
    RuntimeError,
    asyncio.TimeoutError,
    json.JSONDecodeError,
    re.error,
)

REDIS_KEY_WORKFLOWS = "ninko:workflows"
REDIS_KEY_RUNS_PREFIX = "ninko:workflow:runs:"
REDIS_KEY_RUN_INDEX = "ninko:workflow:run_index"
MAX_RUNS_PER_WORKFLOW = 50
MAX_NODE_RETRIES = 5
MAX_PARALLEL_TASKS = 12


def _compare(a, op: str, b) -> bool:
    """Numerischer/String-Vergleich für Condition-Expressions."""
    if op == "==":
        return a == b
    if op in ("!=", "!=="):
        return a != b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    return False


def _tenant_key(base: str, tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return f"{base}:{t or 'default'}"


def _tenant_from_scoped_workflow_id(workflow_id: str) -> str:
    if "::" in workflow_id:
        return workflow_id.split("::", 1)[0].strip().lower() or "default"
    return "default"


class WorkflowEngine:
    """Asynchrone Workflow-Ausführungsmaschine."""

    def __init__(self, redis, orchestrator) -> None:
        self.redis = redis
        self.orchestrator = orchestrator

    async def execute(
        self,
        workflow: dict,
        run_id: str,
        *,
        triggered_by: str = "manual",
        parent_run_id: str | None = None,
    ) -> None:
        """Führt einen Workflow aus und schreibt Statusupdates in Redis."""
        workflow_id = workflow["id"]
        workflow_name = workflow.get("name", "")
        workflow_version = int(workflow.get("version", 1) or 1)
        tenant_id = _tenant_from_scoped_workflow_id(workflow_id)

        # Run-Index für schnelle Lookup
        run_index_key = _tenant_key(REDIS_KEY_RUN_INDEX, tenant_id)
        index_raw = await self.redis.connection.get(run_index_key)
        run_index = json.loads(index_raw) if index_raw else {}
        run_index[run_id] = workflow_id
        await self.redis.connection.set(run_index_key, json.dumps(run_index))

        # Run-Eintrag sicherstellen (für Subflow-Run ohne API-Create)
        await self._ensure_run_entry(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            run_id=run_id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            triggered_by=triggered_by,
            parent_run_id=parent_run_id,
        )

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
                "attempts": 0,
            }

        await self._update_run(
            tenant_id,
            workflow_id,
            run_id,
            "running",
            list(step_map.values()),
            variables,
        )

        final_status = "succeeded"
        t_run_start = datetime.now(timezone.utc)

        try:
            # BFS-Traversal durch den DAG
            queue = [n["id"] for n in start_nodes]
            visited = set()

            while queue:
                # Parallel Execution: alle aktuell wartenden Nodes zeitgleich starten
                batch_ids = [nid for nid in queue if nid not in visited]
                queue = []
                if not batch_ids:
                    continue

                async def _run_node(node_id: str) -> tuple[str, str | None]:
                    visited.add(node_id)
                    node = nodes.get(node_id)
                    if not node:
                        return node_id, None

                    step = step_map[node_id]
                    node_type = node.get("type", "")
                    node_config = node.get("config", {})

                    t_start = datetime.now(timezone.utc)
                    step["status"] = "running"
                    step["started_at"] = t_start.isoformat()

                    try:
                        output, next_label, attempts = await self._execute_with_retries(
                            node_type=node_type,
                            config=node_config,
                            variables=variables,
                            tenant_id=tenant_id,
                            parent_run_id=run_id,
                        )
                        t_end = datetime.now(timezone.utc)
                        duration = int((t_end - t_start).total_seconds() * 1000)

                        step["status"] = "succeeded"
                        step["finished_at"] = t_end.isoformat()
                        step["duration_ms"] = duration
                        step["output"] = str(output)[:500] if output else None
                        step["attempts"] = attempts
                        return node_id, next_label

                    except _WORKFLOW_EXCEPTIONS as exc:
                        t_end = datetime.now(timezone.utc)
                        step["status"] = "failed"
                        step["finished_at"] = t_end.isoformat()
                        step["error"] = str(exc)[:300]
                        logger.error(
                            "Workflow-Step fehlgeschlagen: node=%s err=%s", node_id, exc
                        )
                        raise

                # Batch ausführen
                results = await asyncio.gather(
                    *[_run_node(node_id) for node_id in batch_ids],
                    return_exceptions=True,
                )

                await self._update_run(
                    tenant_id,
                    workflow_id,
                    run_id,
                    "running",
                    list(step_map.values()),
                    variables,
                )

                # Fehler prüfen
                for item in results:
                    if isinstance(item, Exception):
                        final_status = "failed"
                        await self._update_run(
                            tenant_id,
                            workflow_id,
                            run_id,
                            "failed",
                            list(step_map.values()),
                            variables,
                            error=str(item)[:300],
                        )
                        return

                # Kanten traversieren
                for node_id, next_label in results:
                    for edge in edges:
                        if edge["source_id"] != node_id:
                            continue
                        # Bei Conditions: nur den Pfad mit passendem Label nehmen
                        if (
                            next_label
                            and edge.get("label")
                            and edge["label"] != next_label
                        ):
                            target = edge["target_id"]
                            if target in step_map and step_map[target]["status"] == "pending":
                                step_map[target]["status"] = "skipped"
                            continue
                        target_id = edge["target_id"]
                        if target_id not in visited:
                            queue.append(target_id)

        except _WORKFLOW_EXCEPTIONS as exc:
            logger.error("Workflow-Ausführung fehlgeschlagen: %s", exc)
            final_status = "failed"

        finally:
            # Verbleibende pending Steps als skipped markieren
            for step in step_map.values():
                if step["status"] == "pending":
                    step["status"] = "skipped"

            run_duration_ms = int(
                (datetime.now(timezone.utc) - t_run_start).total_seconds() * 1000
            )
            await self._update_run(
                tenant_id,
                workflow_id,
                run_id,
                final_status,
                list(step_map.values()),
                variables,
                duration_ms=run_duration_ms,
            )
            logger.info(
                "Workflow %s abgeschlossen: %s (run=%s, %.1fs)",
                workflow_name,
                final_status,
                run_id,
                run_duration_ms / 1000,
            )

    async def _execute_with_retries(
        self,
        *,
        node_type: str,
        config: dict,
        variables: dict,
        tenant_id: str,
        parent_run_id: str,
    ) -> tuple[Any, str | None, int]:
        retries = min(max(0, int(config.get("retries", 0) or 0)), MAX_NODE_RETRIES)
        retry_delay_ms = max(0, int(config.get("retry_delay_ms", 0) or 0))
        attempts = 0
        last_exc: Exception | None = None

        for attempt in range(1, retries + 2):
            attempts = attempt
            try:
                output, next_label = await self._execute_node(
                    node_type=node_type,
                    config=config,
                    variables=variables,
                    tenant_id=tenant_id,
                    parent_run_id=parent_run_id,
                )
                return output, next_label, attempts
            except _WORKFLOW_EXCEPTIONS as exc:
                last_exc = exc
                if attempt > retries:
                    break
                if retry_delay_ms > 0:
                    await asyncio.sleep(retry_delay_ms / 1000.0)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Node-Ausführung ohne Ergebnis fehlgeschlagen.")

    async def _execute_node(
        self,
        *,
        node_type: str,
        config: dict,
        variables: dict,
        tenant_id: str,
        parent_run_id: str,
    ) -> tuple[Any, str | None]:
        """Führt einen einzelnen Node-Typ aus. Gibt (output, next_label) zurück."""

        if node_type == "trigger":
            return "Workflow gestartet", None

        if node_type == "end":
            return config.get("status", "succeeded"), None

        if node_type == "variable":
            name = config.get("name", "")
            value = self._interpolate(config.get("value", ""), variables)
            if name:
                variables[name] = value
            return f"Variable {name} = {value}", None

        if node_type == "agent":
            agent_id = config.get("agent_id", "")
            prompt = self._interpolate(
                config.get("prompt", f"Führe Aufgabe aus (Agent: {agent_id})"),
                variables,
            )
            if self.orchestrator:
                response_text, _, _ = await self.orchestrator.route(
                    message=prompt,
                    chat_history=[],
                )
                variables["previous_output"] = response_text
                return response_text, None
            return f"Agent {agent_id} aufgerufen (kein Orchestrator)", None

        if node_type == "parallel":
            prompts_raw = config.get("prompts", [])
            prompts = prompts_raw if isinstance(prompts_raw, list) else []
            prompts = prompts[:MAX_PARALLEL_TASKS]
            if not prompts:
                return "Parallel: keine Prompts konfiguriert", None

            async def _run_prompt(p: Any) -> str:
                prompt = self._interpolate(str(p), variables)
                if self.orchestrator:
                    resp, _, _ = await self.orchestrator.route(
                        message=prompt,
                        chat_history=[],
                    )
                    return resp
                return prompt

            results = await asyncio.gather(
                *[_run_prompt(prompt) for prompt in prompts],
                return_exceptions=True,
            )
            outputs: list[str] = []
            for res in results:
                if isinstance(res, Exception):
                    raise RuntimeError(str(res))
                outputs.append(str(res))

            joined = "\n".join(f"[{i}] {r}" for i, r in enumerate(outputs))
            variables["parallel_results"] = outputs
            variables["previous_output"] = joined
            return f"Parallel: {len(outputs)} Aufgaben abgeschlossen", None

        if node_type == "subflow":
            sub_workflow_public_id = str(config.get("workflow_id", "")).strip()
            if not sub_workflow_public_id:
                raise ValueError("subflow.workflow_id fehlt")

            workflows_raw = await self.redis.connection.get(
                _tenant_key(REDIS_KEY_WORKFLOWS, tenant_id)
            )
            workflows = json.loads(workflows_raw) if workflows_raw else []
            scoped_sub_id = f"{tenant_id}::{sub_workflow_public_id}"
            sub_wf = next((w for w in workflows if w.get("id") == scoped_sub_id), None)
            if not sub_wf:
                raise ValueError(f"Sub-Workflow '{sub_workflow_public_id}' nicht gefunden")

            sub_run_id = str(uuid.uuid4())
            sub_engine = WorkflowEngine(self.redis, self.orchestrator)
            await sub_engine.execute(
                sub_wf,
                sub_run_id,
                triggered_by="subflow",
                parent_run_id=parent_run_id,
            )
            variables["previous_output"] = f"Subflow {sub_workflow_public_id} abgeschlossen"
            variables["subflow_run_id"] = sub_run_id
            return f"Subflow '{sub_workflow_public_id}' ausgeführt", None

        if node_type == "condition":
            expr = config.get("expression", "")
            previous = variables.get("previous_output", "")
            result = self._evaluate_condition(expr, previous, variables)
            label = (
                config.get("true_label", "true")
                if result
                else config.get("false_label", "false")
            )
            return f"Bedingung: {result}", label

        if node_type == "loop":
            mode = config.get("mode", "foreach")
            var_name = config.get("variable", "items")
            prompt_template = config.get("prompt", "Verarbeite: {loop_item}")
            max_iter = min(int(config.get("max_iterations", 10) or 10), 50)
            condition = config.get("condition", "")

            raw = variables.get(var_name, "[]")
            if isinstance(raw, list):
                items = raw
            else:
                try:
                    items = json.loads(str(raw))
                    if not isinstance(items, list):
                        items = [str(items)]
                except (json.JSONDecodeError, TypeError, ValueError):
                    items = [i.strip() for i in str(raw).split(",") if i.strip()]

            iter_results: list[str] = []

            if mode == "foreach":
                for i, item in enumerate(items[:max_iter]):
                    variables["loop_item"] = str(item)
                    variables["loop_index"] = str(i)
                    prompt = self._interpolate(prompt_template, variables)
                    if self.orchestrator:
                        resp, _, _ = await self.orchestrator.route(
                            message=prompt,
                            chat_history=[],
                        )
                        iter_results.append(f"[{i}] {resp}")
                        variables["previous_output"] = resp
                    else:
                        iter_results.append(f"[{i}] {item}")

            elif mode == "while":
                for i in range(max_iter):
                    variables["loop_index"] = str(i)
                    if condition and not self._evaluate_condition(
                        condition,
                        variables.get("previous_output", ""),
                        variables,
                    ):
                        break
                    prompt = self._interpolate(prompt_template, variables)
                    if self.orchestrator:
                        resp, _, _ = await self.orchestrator.route(
                            message=prompt,
                            chat_history=[],
                        )
                        iter_results.append(f"[{i}] {resp}")
                        variables["previous_output"] = resp
                    else:
                        break

            variables["loop_results"] = "\n".join(iter_results)
            return f"Loop: {len(iter_results)} Iterationen abgeschlossen", None

        return f"Unbekannter Node-Typ: {node_type}", None

    def _evaluate_condition(self, expr: str, previous: str, variables: dict) -> bool:
        """Wertet eine Condition-Expression aus. Gibt True/False zurück."""
        expr = expr.strip()

        m = re.match(r"output\.contains\(['\"](.+?)['\"]\)", expr)
        if m:
            return m.group(1).lower() in previous.lower()

        m = re.match(r"output\.startswith\(['\"](.+?)['\"]\)", expr)
        if m:
            return previous.lower().startswith(m.group(1).lower())

        m = re.match(r"output\.endswith\(['\"](.+?)['\"]\)", expr)
        if m:
            return previous.lower().endswith(m.group(1).lower())

        m = re.match(r"output\.matches\(['\"](.+?)['\"]\)", expr)
        if m:
            try:
                return bool(re.search(m.group(1), previous))
            except re.error:
                return False

        m = re.match(r"len\(output\)\s*([><=!]+)\s*(\d+)", expr)
        if m:
            op, val = m.group(1), int(m.group(2))
            return _compare(len(previous), op, val)

        m = re.match(r"variable\.(\w+)\s*([><=!]+)\s*['\"]?([^'\"]+?)['\"]?$", expr)
        if m:
            var_val = variables.get(m.group(1), "")
            op = m.group(2)
            rhs = m.group(3)
            try:
                return _compare(float(var_val), op, float(rhs))
            except ValueError:
                if op == "==":
                    return str(var_val) == rhs
                if op in ("!=", "!=="):
                    return str(var_val) != rhs
                return False

        logger.debug("Unbekannte Condition-Expression '%s' → fallback true", expr)
        return True

    def _interpolate(self, template: str, variables: dict) -> str:
        """Ersetzt {variable_name} Platzhalter."""
        for key, value in variables.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    async def _ensure_run_entry(
        self,
        *,
        tenant_id: str,
        workflow_id: str,
        run_id: str,
        workflow_name: str,
        workflow_version: int,
        triggered_by: str,
        parent_run_id: str | None,
    ) -> None:
        key = f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{workflow_id}"
        runs_raw = await self.redis.connection.get(key)
        runs = json.loads(runs_raw) if runs_raw else []
        if any(r.get("id") == run_id for r in runs):
            return
        now = datetime.now(timezone.utc).isoformat()
        runs.append(
            {
                "id": run_id,
                "workflow_id": workflow_id.split("::", 1)[1] if "::" in workflow_id else workflow_id,
                "workflow_name": workflow_name,
                "workflow_version": workflow_version,
                "status": "running",
                "started_at": now,
                "finished_at": None,
                "duration_ms": None,
                "steps": [],
                "variables": {},
                "error": None,
                "triggered_by": triggered_by,
                "parent_run_id": parent_run_id,
            }
        )
        if len(runs) > MAX_RUNS_PER_WORKFLOW:
            runs = runs[-MAX_RUNS_PER_WORKFLOW:]
        await self.redis.connection.set(key, json.dumps(runs))

    async def _update_run(
        self,
        tenant_id: str,
        workflow_id: str,
        run_id: str,
        status: str,
        steps: list,
        variables: dict,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Schreibt den aktuellen Run-Status nach Redis (mit Lock gegen Race Conditions)."""
        lock_key = f"{tenant_id}:{workflow_id}"
        if lock_key not in _run_update_locks:
            _run_update_locks[lock_key] = asyncio.Lock()
        key = f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{workflow_id}"
        now = datetime.now(timezone.utc).isoformat()

        async with _run_update_locks[lock_key]:
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
