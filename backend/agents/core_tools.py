"""
Core Tools for Ninko Agents.
These tools provide fundamental system capabilities rather than domain-specific modular functions.
"""

import asyncio
import logging
from langchain_core.tools import tool
from core.task_registry import get_task_registry
from core.tool_permissions import (
    PermissionDeniedError,
    validate_cli_command,
    validate_tool_permission,
)

# Strong references to background tasks to prevent premature GC
_background_tasks: set[asyncio.Task] = set()
_BG_TASKS_MAX = 1000  # Obergrenze für gleichzeitige Workflow-Tasks

# Exportliste für externe Importe
__all__ = [
    "execute_cli_command",
    "create_custom_agent",
    "update_custom_agent",
    "create_dag_workflow",
    "create_linear_workflow",
    "execute_workflow",
    "create_task",
    "get_task",
    "list_tasks",
    "stop_task",
    "task_output",
    "call_module_agent",
    "run_pipeline",
    "run_parallel_pipeline",
    "install_skill",
    "remember_fact",
    "recall_memory",
    "forget_fact",
    "confirm_forget",
    "speak",
    "configure_routing",
    "get_routing_info",
    "wait",
    "generate_pdf_report",
]

_CORE_TOOL_EXCEPTIONS = (
    ValueError,
    TypeError,
    KeyError,
    RuntimeError,
    OSError,
    asyncio.TimeoutError,
)
_CORE_IMPORT_EXCEPTIONS = (ImportError, AttributeError, RuntimeError)


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
    """Gibt die entsprechende Übersetzung zurück basierend auf der LANGUAGE-Einstellung."""
    try:
        from core.config import get_settings

        lang = get_settings().LANGUAGE
        trans = {
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
        return trans.get(lang, en)
    except _CORE_IMPORT_EXCEPTIONS:
        return de


# Whitelist of allowed executables for execute_cli_command
_ALLOWED_COMMANDS = {
    "uptime",
    "ping",
    "df",
    "free",
    "ps",
    "uname",
    "hostname",
    "netstat",
    "ss",
    "ip",
    "dig",
    "nslookup",
    "traceroute",
    "cat",
    "ls",
    "echo",
    "date",
    "who",
    "w",
    "systemctl",
    "journalctl",
    "dmesg",
    "curl",
    "wget",
    "nmap",
}

logger = logging.getLogger("ninko.agents.core_tools")


def _truncate_output(text: str, max_chars: int = 0, max_lines: int = 0) -> str:
    """
    Kürzt Tool-Output auf max_lines Zeilen ODER max_chars Zeichen (was zuerst greift).
    Fügt am Ende einen Hinweis ein dass mehr Daten vorhanden sind.
    Analog zu opencode's Truncate.output() Prinzip.
    """
    from core.config import get_settings

    settings = get_settings()
    if max_chars <= 0:
        max_chars = settings.TOOL_MAX_OUTPUT_CHARS
    if max_lines <= 0:
        max_lines = settings.TOOL_MAX_OUTPUT_LINES

    lines = text.splitlines()
    total_lines = len(lines)
    total_chars = len(text)

    if total_lines <= max_lines and total_chars <= max_chars:
        return text

    # Zeilen-Limit anwenden
    truncated_by_lines = False
    if total_lines > max_lines:
        lines = lines[:max_lines]
        truncated_by_lines = True

    preview = "\n".join(lines)

    # Zeichen-Limit auf den Zeilen-Stub anwenden
    if len(preview) > max_chars:
        preview = preview[:max_chars]

    removed_lines = total_lines - len(lines) if truncated_by_lines else 0
    removed_chars = total_chars - len(preview)

    hint_parts = []
    if truncated_by_lines and removed_lines > 0:
        hint_parts.append(_t(f"{removed_lines} Zeilen", f"{removed_lines} lines"))
    if removed_chars > 0:
        hint_parts.append(_t(f"{removed_chars} Zeichen", f"{removed_chars} chars"))
    hint = _t(" und ", " and ").join(hint_parts) if hint_parts else _t("Daten", "data")

    return f"{preview}\n\n" + _t(
        f"[…{hint} gekürzt – frage nach einem spezifischen Teil wenn du mehr benötigst]",
        f"[…{hint} truncated – ask for a specific part if you need more]",
    )


@tool
async def execute_cli_command(command: str) -> str:
    """
    Führt einen Shell-Befehl lokal im System (innerhalb des Containers) aus.
    Verwende dieses Tool für generische Systemabfragen wie 'uptime', 'ping', 'df -h' etc.
    Ergebnis ist die Kombination aus Standardausgabe (STDOUT) und Fehlerausgabe (STDERR).
    Ein Timeout von 30 Sekunden ist aktiv.
    """
    logger.info("Führe lokales CLI-Kommando aus: %s", command)
    try:
        try:
            args = validate_cli_command(command, _ALLOWED_COMMANDS)
        except PermissionDeniedError as e:
            return _t(
                f"Fehler: {e}",
                f"Error: {e}",
            )

        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            # 30 seconds timeout to prevent hanging commands
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            process.kill()
            logger.warning("CLI-Kommando '%s' Timeout nach 30 Sekunden", command)
            return _t(
                f"Fehler: Das Kommando '{args[0]}' hat ein Timeout nach 30 Sekunden verursacht und wurde abgebrochen.",
                f"Error: Command '{args[0]}' timed out after 30 seconds and was aborted.",
                f"Erreur : Le commande '{args[0]}' a expiré après 30 secondes et a été abandonnée.",
                f"Error: El comando '{args[0]}' agotó el tiempo después de 30 segundos y fue abortado.",
                f"Errore: Il comando '{args[0]}' ha superato il timeout dopo 30 secondi ed è stato interrotto.",
                f"Fout: Opdracht '{args[0]}' heeft een time-out van 30 seconden overschreden en is afgebroken.",
                f"Błąd: Polecenie '{args[0]}' przekroczyło limit czasu 30 sekund i zostało przerwane.",
                f"Erro: O comando '{args[0]}' expirou após 30 segundos e foi abortado.",
                f"エラー: コマンド '{args[0]}' は30秒後にタイムアウトし、中断されました。",
                f"错误: 命令 '{args[0]}' 在30秒后超时并被中止。",
            )

        out_str = stdout.decode("utf-8", errors="replace").strip() if stdout else ""
        err_str = stderr.decode("utf-8", errors="replace").strip() if stderr else ""

        result = []
        if out_str:
            result.append(out_str)
        if err_str:
            result.append(f"STDERR:\n{err_str}")

        if not result:
            return _t(
                f"Das Kommando '{command}' wurde erfolgreich ausgeführt (Exit Code {process.returncode}), hat aber keine Ausgabe produziert.",
                f"Command '{command}' executed successfully (exit code {process.returncode}) but produced no output.",
            )

        raw_output = "\n".join(result)
        return _truncate_output(raw_output)

    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler bei CLI-Kommando '%s': %s", command, exc)
        return _t(
            f"Fehler bei der Ausführung von '{command}': {exc}",
            f"Error executing '{command}': {exc}",
        )


@tool
async def create_task(command: str, description: str = "") -> dict:
    """
    Startet ein lokales CLI-Kommando als Hintergrund-Task und gibt die Task-Metadaten zurück.
    Nutze dieses Tool für längere Diagnose- oder Monitoring-Kommandos, die nicht blockierend
    im aktuellen Agent-Lauf ausgeführt werden sollen.
    """
    try:
        decision = validate_tool_permission("create_task")
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason)
        args = validate_cli_command(command, _ALLOWED_COMMANDS)
        registry = get_task_registry()
        task = await registry.create_cli_task(command=command, description=description)
        await registry.start_cli_task(task["id"], args)
        return task
    except (PermissionDeniedError, ValueError, RuntimeError, OSError) as exc:
        logger.error("create_task fehlgeschlagen: %s", exc)
        return {"status": "error", "detail": str(exc)}


@tool
async def get_task(task_id: str) -> dict:
    """
    Gibt Status und Metadaten eines zuvor gestarteten Hintergrund-Tasks zurück.
    """
    registry = get_task_registry()
    task = await registry.get_task(task_id)
    if not task:
        return {"status": "error", "detail": f"Task '{task_id}' nicht gefunden."}
    return task


@tool
async def list_tasks() -> list[dict]:
    """
    Listet alle bekannten Hintergrund-Tasks mit Status und Kurzmetadaten auf.
    """
    registry = get_task_registry()
    return await registry.list_tasks()


@tool
async def stop_task(task_id: str) -> dict:
    """
    Stoppt einen laufenden Hintergrund-Task. Verwende dieses Tool, wenn ein
    Diagnose- oder Hintergrundjob nicht weiterlaufen soll.
    """
    try:
        decision = validate_tool_permission("stop_task")
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason)
        registry = get_task_registry()
        return await registry.stop_task(task_id)
    except (PermissionDeniedError, ValueError, RuntimeError, OSError) as exc:
        logger.error("stop_task fehlgeschlagen: %s", exc)
        return {"status": "error", "detail": str(exc)}


@tool
async def task_output(task_id: str) -> str:
    """
    Gibt die bisherige Ausgabe eines Hintergrund-Tasks zurück.
    """
    try:
        registry = get_task_registry()
        return _truncate_output(await registry.task_output(task_id))
    except (ValueError, RuntimeError, OSError) as exc:
        logger.error("task_output fehlgeschlagen: %s", exc)
        return _t(
            f"Fehler beim Laden der Task-Ausgabe: {exc}",
            f"Error loading task output: {exc}",
        )


@tool
async def create_custom_agent(
    name: str, system_prompt: str, description: str = ""
) -> str:
    """
    Erstellt einen neuen spezialisierten Agenten im Ninko Agent-Pool.

    Wann verwenden:
    - Der User braucht ein wiederverwendbares KI-Profil für eine spezifische Domäne
    - Kein vorhandenes Modul deckt die Aufgabe ab
    - Eine Persona mit spezifischem Fachwissen/Verhalten gewünscht

    Qualitäts-Anforderungen für system_prompt:
    - Klar beschriebene Aufgaben (bullet points)
    - Arbeitsweise und Verhalten definiert
    - Eskalationsregel enthalten ("→ an Ninko zurückgeben")
    - Destruktive Aktionen gegattet ("immer bestätigen lassen")
    - Module die genutzt werden via call_module_agent erwähnt
    - Scope explizit begrenzt (was der Agent NICHT macht)

    name: Kurzer, funktionsbeschreibender Name (max 5 Wörter, z.B. "K8s-Log-Analyst")
    system_prompt: Vollständiger Deutsch-Prompt nach obigem Schema
    description: Ein klarer Satz was dieser Agent konkret macht

    Gibt die ID des neu erstellten Agenten zurück.
    """
    from core.agent_pool import get_agent_pool

    pool = get_agent_pool()
    agent_id, _ = await pool.register(
        name=name, system_prompt=system_prompt, description=description
    )
    logger.info(
        "Custom Agent via Tool erstellt und im Pool registriert: %s (%s)",
        name,
        agent_id,
    )

    return _t(
        f"Agent '{name}' (ID: {agent_id}) wurde erfolgreich erstellt und ist sofort im Agenten-Pool verfügbar.",
        f"Agent '{name}' (ID: {agent_id}) was successfully created and is immediately available in the agent pool.",
    )


@tool
async def update_custom_agent(
    agent_id: str, system_prompt: str = "", description: str = ""
) -> str:
    """
    Aktualisiert einen bestehenden Custom-Agenten im Agenten-Pool.

    Wann verwenden:
    - Agent soll verbessert oder erweitert werden
    - System-Prompt muss korrigiert/optimiert werden
    - Beschreibung soll präzisiert werden

    agent_id: Die ID des zu aktualisierenden Agenten (aus der Agenten-Liste)
    system_prompt: Neuer System-Prompt (leer = unverändert)
    description: Neue Beschreibung (leer = unverändert)

    Gibt Erfolgs- oder Fehlermeldung zurück.
    """
    from core.agent_pool import get_agent_pool

    pool = get_agent_pool()
    updated = await pool.update_agent(
        agent_id,
        system_prompt=system_prompt or None,
        description=description or None,
    )

    if updated:
        logger.info("Custom Agent via Tool aktualisiert: %s", agent_id)
        return _t(
            f"Agent (ID: {agent_id}) wurde erfolgreich aktualisiert.",
            f"Agent (ID: {agent_id}) was successfully updated.",
        )
    return _t(
        f"Fehler: Agent mit ID '{agent_id}' nicht gefunden.",
        f"Error: Agent with ID '{agent_id}' not found.",
        f"Erreur : Agent avec l'ID '{agent_id}' non trouvé.",
        f"Error: Agente con ID '{agent_id}' no encontrado.",
        f"Errore: Agente con ID '{agent_id}' non trovato.",
        f"Fout: Agent met ID '{agent_id}' niet gevonden.",
        f"Błąd: Agent o ID '{agent_id}' nie został znaleziony.",
        f"Erro: Agente com ID '{agent_id}' não encontrado.",
        f"エラー: ID '{agent_id}' のエージェントが見つかりません。",
        f"错误: 找不到ID为 '{agent_id}' 的代理。",
    )


@tool
async def create_dag_workflow(
    name: str, description: str, nodes: list[dict], edges: list[dict]
) -> str:
    """
    Erstellt einen Workflow mit beliebiger DAG-Struktur — inkl. Conditions, Loops und Branching.
    Nutze dieses Tool wenn der Workflow mehr als lineare Schritte benötigt (Bedingungen, Schleifen, Fehler-Handler).
    Für einfache lineare Workflows nutze create_linear_workflow.

    nodes: Liste von Node-Dicts mit:
      - id: eindeutige Kurzkennung (z.B. "start", "check", "cond1")
      - type: "trigger" | "agent" | "condition" | "loop" | "variable" | "end"
      - label: Anzeigename
      - config: typ-spezifische Konfiguration:
          trigger: {"mode": "manual"|"cron", "cron": "0 8 * * *"}
          agent:   {"agent_id": "orchestrator", "prompt": "Aufgabe mit {previous_output}"}
          condition: {"expression": "output.contains(\\"error\\")", "true_label": "true", "false_label": "false"}
          loop:    {"mode": "foreach", "variable": "items", "prompt": "Verarbeite: {loop_item}", "max_iterations": "10"}
          variable: {"name": "myVar", "value": "wert"}
          end:     {"status": "succeeded"|"failed"}

    edges: Liste von Edge-Dicts mit:
      - source_id: ID des Quell-Nodes
      - target_id: ID des Ziel-Nodes
      - label: leer ("") oder Condition-Branch-Label ("true"/"false")

    Vollständiges Beispiel — K8s Health Check mit Alert bei Fehler:
      nodes=[
        {"id": "start", "type": "trigger", "label": "Start", "config": {"mode": "manual"}},
        {"id": "check", "type": "agent",     "label": "Pods prüfen", "config": {"agent_id": "orchestrator", "prompt": "Prüfe alle Pods auf Fehler"}},
        {"id": "cond",  "type": "condition", "label": "Fehler?",    "config": {"expression": "output.contains(\\"error\\")", "true_label": "true", "false_label": "false"}},
        {"id": "alert", "type": "agent",     "label": "Alert",      "config": {"agent_id": "orchestrator", "prompt": "Sende Telegram-Alert: {previous_output}"}},
        {"id": "ok",    "type": "end",       "label": "OK",         "config": {"status": "succeeded"}},
        {"id": "done",  "type": "end",       "label": "Fertig",     "config": {"status": "succeeded"}}
      ],
      edges=[
        {"source_id": "start", "target_id": "check",  "label": ""},
        {"source_id": "check",  "target_id": "cond",   "label": ""},
        {"source_id": "cond",   "target_id": "alert",  "label": "true"},
        {"source_id": "cond",   "target_id": "ok",     "label": "false"},
        {"source_id": "alert",  "target_id": "done",   "label": ""}
      ]
    """
    import json
    import uuid
    from datetime import datetime, timezone
    from core.redis_client import get_redis

    if not nodes:
        return _t(
            "Fehler: Keine Nodes angegeben.",
            "Error: No nodes provided.",
            "Erreur : Aucun nœud spécifié.",
            "Error: No se proporcionaron nodos.",
            "Errore: Nessun nodo specificato.",
            "Fout: Geen knooppunten opgegeven.",
            "Błąd: Nie podano węzłów.",
            "Erro: Nenhum nó especificado.",
            "エラー: ノードが指定されていません。",
            "错误: 未指定节点。",
        )

    # UUIDs vergeben und Positionen auto-berechnen (einfaches Layer-Layout)
    id_map: dict[str, str] = {}
    for n in nodes:
        short_id = str(n.get("id", "")).strip()
        if not short_id:
            short_id = str(uuid.uuid4())[:8]
        full_id = str(uuid.uuid4())[:8]
        id_map[short_id] = full_id

    # Nodes mit neuen IDs und Positionen aufbauen
    x_base, y_base, y_step = 120, 100, 160
    built_nodes = []
    for i, n in enumerate(nodes):
        short_id = str(n.get("id", "")).strip()
        full_id = id_map.get(short_id, str(uuid.uuid4())[:8])
        built_nodes.append(
            {
                "id": full_id,
                "type": n.get("type", "agent"),
                "label": n.get("label", n.get("type", "Node")),
                "config": n.get("config", {}),
                "position": {"x": x_base, "y": y_base + i * y_step},
            }
        )

    # Edges mit gemappten IDs aufbauen
    built_edges = []
    for e in edges:
        src = id_map.get(str(e.get("source_id", "")), "")
        tgt = id_map.get(str(e.get("target_id", "")), "")
        if src and tgt:
            built_edges.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "source_id": src,
                    "target_id": tgt,
                    "label": e.get("label", ""),
                }
            )

    redis = get_redis()
    raw = await redis.connection.get("ninko:workflows")
    workflows = json.loads(raw) if raw else []

    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    new_wf = {
        "id": wf_id,
        "name": name,
        "description": description,
        "nodes": built_nodes,
        "edges": built_edges,
        "variables": [],
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }

    workflows.append(new_wf)
    await redis.connection.set("ninko:workflows", json.dumps(workflows))
    logger.info(
        "DAG-Workflow via Tool erstellt: %s (%s, %d nodes, %d edges)",
        name,
        wf_id,
        len(built_nodes),
        len(built_edges),
    )

    return _t(
        f"Workflow '{name}' (ID: {wf_id}) mit {len(built_nodes)} Nodes und {len(built_edges)} Edges wurde erfolgreich erstellt.",
        f"Workflow '{name}' (ID: {wf_id}) with {len(built_nodes)} nodes and {len(built_edges)} edges was successfully created.",
    )


@tool
async def create_linear_workflow(name: str, description: str, steps: list[str]) -> str:
    """
    Erstellt einen neuen, automatisierten Workflow im System.
    Nutze dieses Tool IMMER, wenn der User einen Workflow fordert!
    'steps' ist eine Liste von Text-Anweisungen, die nacheinander ausgeführt werden.
    Beispiel: ["Mache einen Ping auf 1.1.1.1", "Schreibe das Ergebnis in eine Datei"]
    Gibt die ID des neuen Workflows zurück.
    """
    import json
    import uuid
    from datetime import datetime, timezone
    from core.redis_client import get_redis

    # 1. Trigger Node (Start)
    trigger_id = str(uuid.uuid4())[:8]
    nodes = [
        {
            "id": trigger_id,
            "type": "trigger",
            "label": "Start",
            "config": {"mode": "manual"},
            "position": {"x": 100, "y": 100},
        }
    ]
    edges = []

    # 2. Agent Nodes & Edges
    prev_id = trigger_id
    y_pos = 250
    for i, step_prompt in enumerate(steps):
        node_id = str(uuid.uuid4())[:8]
        nodes.append(
            {
                "id": node_id,
                "type": "agent",
                "label": f"Step {i + 1}",
                "config": {"agent_id": "orchestrator", "prompt": step_prompt},
                "position": {"x": 100, "y": y_pos},
            }
        )
        edges.append(
            {
                "id": str(uuid.uuid4())[:8],
                "source_id": prev_id,
                "target_id": node_id,
                "label": "",
            }
        )
        prev_id = node_id
        y_pos += 150

    redis = get_redis()
    raw = await redis.connection.get("ninko:workflows")
    workflows = json.loads(raw) if raw else []

    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    new_wf = {
        "id": wf_id,
        "name": name,
        "description": description,
        "nodes": nodes,
        "edges": edges,
        "variables": [],
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }

    workflows.append(new_wf)
    await redis.connection.set("ninko:workflows", json.dumps(workflows))
    logger.info("Linearer Workflow via Tool erstellt: %s (%s)", name, wf_id)

    return _t(
        f"Workflow '{name}' (ID: {wf_id}) wurde erfolgreich erstellt.",
        f"Workflow '{name}' (ID: {wf_id}) was successfully created.",
    )


@tool
async def execute_workflow(workflow_name_or_id: str) -> str:
    """
    Startet einen existierenden Workflow und wartet auf dessen Abschluss (Polling).
    Das Ergebnis dieses Tools ist ein detaillierter Step-by-Step Execution Trace (Markdown)
    der dem User zeigt, was genau passiert ist (als 'Thinking Brackets' Ersatz).
    """
    import json
    import uuid
    import asyncio
    from datetime import datetime, timezone
    from core.redis_client import get_redis

    redis = get_redis()
    raw = await redis.connection.get("ninko:workflows")
    workflows = json.loads(raw) if raw else []

    wf = next(
        (
            w
            for w in workflows
            if w["id"] == workflow_name_or_id
            or w["name"].lower() == workflow_name_or_id.lower()
        ),
        None,
    )
    if not wf:
        return _t(
            f"Fehler: Workflow '{workflow_name_or_id}' nicht gefunden.",
            f"Error: Workflow '{workflow_name_or_id}' not found.",
            f"Erreur : Workflow '{workflow_name_or_id}' non trouvé.",
            f"Error: Flujo de trabajo '{workflow_name_or_id}' no encontrado.",
            f"Errore: Flusso di lavoro '{workflow_name_or_id}' non trovato.",
            f"Fout: Werkstroom '{workflow_name_or_id}' niet gevonden.",
            f"Błąd: Przepływ pracy '{workflow_name_or_id}' nie został znaleziony.",
            f"Erro: Fluxo de trabalho '{workflow_name_or_id}' não encontrado.",
            f"エラー: ワークフロー '{workflow_name_or_id}' が見つかりません。",
            f"错误: 找不到工作流 '{workflow_name_or_id}'。",
        )

    wf_id = wf["id"]
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    from schemas.workflows import WorkflowRun

    run_obj = WorkflowRun(
        id=run_id,
        workflow_id=wf_id,
        workflow_name=wf.get("name", ""),
        status="running",
        started_at=now,
        steps=[],
        triggered_by="AI_Agent",
    )

    runs_key = f"ninko:workflow:runs:{wf_id}"
    runs_raw = await redis.connection.get(runs_key)
    runs = json.loads(runs_raw) if runs_raw else []
    runs.append(run_obj.model_dump())
    if len(runs) > 50:
        runs = runs[-50:]
    await redis.connection.set(runs_key, json.dumps(runs))

    # Engine asynchron im Hintergrund starten
    try:
        from core.workflow_engine import WorkflowEngine
        from agents.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if orchestrator is None:
            return _t(
                "Fehler: Orchestrator noch nicht initialisiert.",
                "Error: Orchestrator not yet initialized.",
                "Erreur : Orchestrateur pas encore initialisé.",
                "Error: Orquestador aún no inicializado.",
                "Errore: Orchestrator non ancora inizializzato.",
                "Fout: Orchestrator nog niet geïnitialiseerd.",
                "Błąd: Orchestrator jeszcze nie został zainicjowany.",
                "Erro: Orquestrador ainda não inicializado.",
                "エラー: オーケストレーターがまだ初期化されていません。",
                "错误: 编排器尚未初始化。",
            )
        engine = WorkflowEngine(redis, orchestrator)
        # Bounds-Check: ältesten Task canceln wenn Limit überschritten
        if len(_background_tasks) >= _BG_TASKS_MAX:
            _oldest = next(iter(_background_tasks), None)
            if _oldest is not None:
                logger.warning(
                    "Workflow-Task-Limit (%d) erreicht — ältesten Task gecancelt.", _BG_TASKS_MAX
                )
                _oldest.cancel()
        _task = asyncio.create_task(engine.execute(wf, run_id))
        _background_tasks.add(_task)
        _task.add_done_callback(_background_tasks.discard)
    except _CORE_IMPORT_EXCEPTIONS as exc:
        return _t(
            f"Kritischer Fehler beim Starten des Workflows: {exc}",
            f"Critical error starting workflow: {exc}",
            f"Erreur critique lors du démarrage du workflow : {exc}",
            f"Error crítico al iniciar el flujo de trabajo: {exc}",
            f"Errore critico nell'avvio del flusso di lavoro: {exc}",
            f"Kritieke fout bij het starten van de werkstroom: {exc}",
            f"Krytyczny błąd podczas uruchamiania przepływu pracy: {exc}",
            f"Erro crítico ao iniciar o fluxo de trabalho: {exc}",
            f"ワークフローの開始中に重大なエラーが発生しました: {exc}",
            f"启动工作流时发生严重错误: {exc}",
        )

    # Poll variables
    max_retries = 120  # 2 Minutes timeout

    for _ in range(max_retries):
        await asyncio.sleep(1.0)
        current_runs_raw = await redis.connection.get(runs_key)
        if not current_runs_raw:
            continue

        current_runs = json.loads(current_runs_raw)
        current_run = next((r for r in current_runs if r["id"] == run_id), None)

        if current_run and current_run.get("status") in ("succeeded", "failed"):
            # Build execution trace
            trace = f"<details>\n  <summary>🧠 Workflow Execution Trace: {wf.get('name')} ({current_run.get('status')})</summary>\n\n"
            trace += _t(
                f"- **Dauer gesamt:** {current_run.get('duration_ms', 'unbekannt')} ms\n",
                f"- **Total duration:** {current_run.get('duration_ms', 'unknown')} ms\n",
            )
            if current_run.get("error"):
                trace += _t(
                    f"- **Fehler:** {current_run.get('error')}\n",
                    f"- **Error:** {current_run.get('error')}\n",
                )
            trace += _t("### Details pro Schritt:\n", "### Step details:\n")

            for step in current_run.get("steps", []):
                sym = (
                    "✅"
                    if step.get("status") == "succeeded"
                    else "❌"
                    if step.get("status") == "failed"
                    else "⏳"
                    if step.get("status") == "pending"
                    else "⏭️"
                )
                trace += _t(
                    f"\n- {sym} **{step.get('node_label')}** ({step.get('node_type')}) [Dauer: {step.get('duration_ms', 0)} ms]\n",
                    f"\n- {sym} **{step.get('node_label')}** ({step.get('node_type')}) [Duration: {step.get('duration_ms', 0)} ms]\n",
                )

                output = step.get("output")
                if output:
                    # Prevent breaking details tag formatting
                    safe_out = output.replace("\n", "\n> ")
                    trace += f"> Output:\n> {safe_out}\n"

            trace += "\n</details>"
            return trace

    return _t(
        f"Warnung: Das Timeout (2 Minuten) für den Workflow '{wf.get('name')}' wurde erreicht. Er läuft möglicherweise noch im Hintergrund.",
        f"Warning: The timeout (2 minutes) for workflow '{wf.get('name')}' was reached. It may still be running in the background.",
    )


@tool
async def call_module_agent(module_name: str, task: str) -> str:
    """
    Ruft einen spezialisierten Modul-Agenten auf und gibt dessen Antwort zurück.
    Nutze dieses Tool für modulübergreifende Aufgaben oder wenn du einen Teilschritt
    an ein spezialisiertes Modul delegieren willst.

    Die aktuell verfügbaren Modul-Namen sind im System-Prompt unter VERFÜGBARE MODULE aufgelistet.

    Args:
        module_name: Name des Moduls (z.B. 'web_search', 'kubernetes', 'telegram')
        task: Die vollständige Aufgabenbeschreibung für den Modul-Agenten.
              Füge alle nötigen Details hinzu (Zieladresse, Kontext, Ergebnisse etc.).
    """
    from agents.orchestrator import get_orchestrator
    from core import status_bus

    orchestrator = get_orchestrator()
    if orchestrator is None:
        return _t(
            "Fehler: Orchestrator noch nicht initialisiert.",
            "Error: Orchestrator not yet initialized.",
            "Erreur : Orchestrateur pas encore initialisé.",
            "Error: Orquestador aún no inicializado.",
            "Errore: Orchestrator non ancora inizializzato.",
            "Fout: Orchestrator nog niet geïnitialiseerd.",
            "Błąd: Orchestrator jeszcze nie został zainicjowany.",
            "Erro: Orquestrador ainda não inicializado.",
            "エラー: オーケストレーターがまだ初期化されていません。",
            "错误: 编排器尚未初始化。",
        )

    agent = orchestrator.registry.get_agent(module_name)
    if agent is None:
        available = [m.name for m in orchestrator.registry.list_modules()]
        return _t(
            f"Fehler: Modul '{module_name}' nicht gefunden oder nicht aktiv. "
            f"Verfügbare Module: {', '.join(available)}",
            f"Error: Module '{module_name}' not found or not active. "
            f"Available modules: {', '.join(available)}",
            f"Erreur : Module '{module_name}' non trouvé ou pas actif. "
            f"Modules disponibles : {', '.join(available)}",
            f"Error: Módulo '{module_name}' no encontrado o no activo. "
            f"Módulos disponibles : {', '.join(available)}",
            f"Errore: Modulo '{module_name}' non trovato o non attivo. "
            f"Moduli disponibili : {', '.join(available)}",
            f"Fout: Module '{module_name}' niet gevonden of niet actief. "
            f"Beschikbare modules : {', '.join(available)}",
            f"Błąd: Moduł '{module_name}' nie został znaleziony lub nie jest aktywny. "
            f"Dostępne moduły : {', '.join(available)}",
            f"Erro: Módulo '{module_name}' não encontrado ou não ativo. "
            f"Módulos disponíveis : {', '.join(available)}",
            f"エラー: モジュール '{module_name}' が見つからないかアクティブではありません。 "
            f"利用可能なモジュール: {', '.join(available)}",
            f"错误: 找不到模块 '{module_name}' 或模块未激活。 "
            f"可用模块: {', '.join(available)}",
        )

    session_id = status_bus.get_session_id()
    logger.info("call_module_agent: delegiere an '%s': %s…", module_name, task[:80])
    try:
        result, _ = await agent.invoke(
            message=task, chat_history=None, session_id=session_id
        )
        return result
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("call_module_agent Fehler bei '%s': %s", module_name, exc)
        return _t(
            f"Fehler im Modul '{module_name}': {exc}",
            f"Error in module '{module_name}': {exc}",
            f"Erreur dans le module '{module_name}': {exc}",
            f"Error en el módulo '{module_name}': {exc}",
            f"Errore nel modulo '{module_name}': {exc}",
            f"Fout in module '{module_name}': {exc}",
            f"Błąd w module '{module_name}': {exc}",
            f"Erro no módulo '{module_name}': {exc}",
            f"モジュール '{module_name}' でエラーが発生しました: {exc}",
            f"模块 '{module_name}' 发生错误: {exc}",
        )


def _build_execution_groups(steps: list[dict]) -> list[list[int]]:
    """
    Topologische Sortierung der Pipeline-Steps anhand von ``depends_on``.

    Gibt eine Liste von Gruppen zurück. Steps innerhalb einer Gruppe haben
    keine gegenseitigen Abhängigkeiten und können parallel ausgeführt werden.
    Gruppen selbst werden sequenziell abgearbeitet.

    Ohne ``depends_on``-Felder → rein sequenziell (eine Gruppe pro Step).
    """
    n = len(steps)
    if n == 0:
        return []

    # Prüfen ob irgendein Step depends_on hat
    has_deps = any("depends_on" in s for s in steps)
    if not has_deps:
        # Rein sequenziell – rückwärtskompatibel
        return [[i] for i in range(n)]

    # Abhängigkeitsgraph aufbauen
    in_degree = [0] * n
    dependents: list[list[int]] = [[] for _ in range(n)]

    for i, step in enumerate(steps):
        deps = step.get("depends_on")
        if deps is None:
            # Ohne depends_on → hängt vom vorherigen Step ab (sequenziell)
            if i > 0:
                deps = [i - 1]
            else:
                deps = []
        for d in deps:
            if 0 <= d < n and d != i:
                in_degree[i] += 1
                dependents[d].append(i)

    # Kahn's Algorithmus – Gruppen-basiert (BFS level-order)
    groups: list[list[int]] = []
    ready = [i for i in range(n) if in_degree[i] == 0]

    visited = 0
    while ready:
        groups.append(ready)
        visited += len(ready)
        next_ready: list[int] = []
        for idx in ready:
            for dep in dependents[idx]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    next_ready.append(dep)
        ready = next_ready

    if visited < n:
        # Zyklus erkannt – Fallback auf sequenziell
        logger.warning("Pipeline depends_on enthält Zyklen – Fallback auf sequenziell.")
        return [[i] for i in range(n)]

    return groups


@tool
async def run_pipeline(steps: list[dict]) -> str:
    """
    Führt eine deterministische Abfolge von Modul-Tasks aus (Deterministisches Piping).
    Jeder Schritt erhält das Ergebnis des vorherigen automatisch als Kontext.
    NUTZE DIESES TOOL für alle mehrstufigen Aufgaben die mehrere Module erfordern –
    es ist ZUVERLÄSSIGER als mehrere call_module_agent-Aufrufe in Folge.

    'steps' ist eine Liste von Dictionaries mit:
    - 'module': Name des Moduls (z.B. 'web_search', 'email', 'kubernetes', 'glpi')
    - 'task': Aufgabenbeschreibung für dieses Modul (ohne Kontext – der wird automatisch übergeben)
    - 'depends_on': (Optional) Liste von Step-Indizes (0-basiert) auf die dieser Step wartet.
       Steps ohne gemeinsame Abhängigkeiten laufen PARALLEL via asyncio.gather().
       Ohne depends_on → sequenziell wie bisher (rückwärtskompatibel).

    Beispiele:
    - Sequenziell (wie bisher): steps=[
        {"module": "web_search", "task": "Recherchiere aktuelle Infos über X"},
        {"module": "email", "task": "Sende die Recherche-Ergebnisse an user@example.com als HTML-Email"}
      ]
    - Parallel (K8s + Pi-hole gleichzeitig, dann GLPI mit beiden Ergebnissen): steps=[
        {"module": "kubernetes", "task": "Prüfe alle Pods auf Fehler"},
        {"module": "pihole", "task": "Lade DNS-Fehler-Log", "depends_on": []},
        {"module": "glpi", "task": "Erstelle Incident mit K8s+DNS-Fehlern", "depends_on": [0, 1]}
      ]
    """
    from agents.orchestrator import get_orchestrator
    from core import status_bus

    orchestrator = get_orchestrator()
    if orchestrator is None:
        return _t(
            "Fehler: Orchestrator noch nicht initialisiert.",
            "Error: Orchestrator not yet initialized.",
            "Erreur : Orchestrateur pas encore initialisé.",
            "Error: Orquestador aún no inicializado.",
            "Errore: Orchestrator non ancora inizializzato.",
            "Fout: Orchestrator nog niet geïnitialiseerd.",
            "Błąd: Orchestrator jeszcze nie został zainicjowany.",
            "Erro: Orquestrador ainda não inicializado.",
            "エラー: オーケストレーターがまだ初期化されていません。",
            "错误: 编排器尚未初始化。",
        )

    if not steps:
        return _t(
            "Fehler: Keine Schritte angegeben.",
            "Error: No steps provided.",
            "Erreur : Aucune étape spécifiée.",
            "Error: No se proporcionaron pasos.",
            "Errore: Nessun passaggio specificato.",
            "Fout: Geen stappen opgegeven.",
            "Błąd: Nie podano kroków.",
            "Erro: Nenhuma etapa especificada.",
            "エラー: ステップが指定されていません。",
            "错误: 未指定步骤。",
        )

    session_id = status_bus.get_session_id()
    step_results: dict[int, str] = {}  # idx → result
    results_ordered: list[str] = []
    aborted = False

    # Display-Namen der Module für Status-Updates voraufladen
    manifests = {m.name: m for m in orchestrator.registry.list_modules()}

    # Fehler-Erkennung
    _err_prefixes = (
        "Fehler",
        "Die Anfrage hat zu lange gedauert",
        "Entschuldigung, es ist ein Fehler",
        "Error",
        "The request took too long",
        "Sorry, an error occurred",
    )

    # Topologische Gruppen berechnen
    groups = _build_execution_groups(steps)
    is_parallel = any(len(g) > 1 for g in groups)
    if is_parallel:
        logger.info(
            "Pipeline mit parallelen Gruppen: %s",
            [[steps[i].get("module") for i in g] for g in groups],
        )

    async def _execute_step(i: int) -> tuple[int, str]:
        """Führt einen einzelnen Pipeline-Step aus und gibt (index, result) zurück."""
        step = steps[i]
        module = step.get("module", "").strip()
        task = step.get("task", "").strip()

        if not module or not task:
            return i, _t(
                f"⚠️ Schritt {i + 1}: Übersprungen (module oder task fehlt).",
                f"⚠️ Step {i + 1}: Skipped (module or task missing).",
            )

        # Kontext aus depends_on-Steps zusammenführen
        full_task = task
        deps = step.get("depends_on")
        if deps is not None:
            # Explizite Abhängigkeiten – Ergebnisse aller Dependencies zusammenführen
            dep_contexts = []
            for d in deps:
                if d in step_results:
                    dep_module = steps[d].get("module", f"Step {d + 1}")
                    dep_contexts.append(f"[{dep_module}]: {step_results[d]}")
            if dep_contexts:
                merged = "\n\n".join(dep_contexts)
                full_task = (
                    task
                    + "\n\n"
                    + _t(
                        f"Verwende folgende Ergebnisse als Kontext:\n{merged}",
                        f"Use the following results as context:\n{merged}",
                    )
                )
        elif i > 0 and i - 1 in step_results:
            # Kein depends_on → sequenziell, Kontext vom vorherigen Step
            prev_module = steps[i - 1].get(
                "module", _t("vorheriger Schritt", "previous step")
            )
            full_task = (
                task
                + "\n\n"
                + _t(
                    f"Verwende folgende Ergebnisse aus '{prev_module}' als Inhalt:\n{step_results[i - 1]}",
                    f"Use the following results from '{prev_module}' as content:\n{step_results[i - 1]}",
                )
            )

        agent = orchestrator.registry.get_agent(module)
        if agent is None:
            available = [m.name for m in orchestrator.registry.list_modules()]
            return i, _t(
                f"Fehler: Modul '{module}' nicht gefunden. "
                f"Verfügbar: {', '.join(available)}",
                f"Error: Module '{module}' not found. "
                f"Available: {', '.join(available)}",
                f"Erreur : Module '{module}' non trouvé. "
                f"Disponible : {', '.join(available)}",
                f"Error: Módulo '{module}' no encontrado. "
                f"Disponible : {', '.join(available)}",
                f"Errore: Modulo '{module}' non trovato. "
                f"Disponibile : {', '.join(available)}",
                f"Fout: Module '{module}' niet gevonden. "
                f"Beschikbaar : {', '.join(available)}",
                f"Błąd: Moduł '{module}' nie został znaleziony. "
                f"Dostępne : {', '.join(available)}",
                f"Erro: Módulo '{module}' não encontrado. "
                f"Disponível : {', '.join(available)}",
                f"エラー: モジュール '{module}' が見つかりません。 "
                f"利用可能: {', '.join(available)}",
                f"错误: 找不到模块 '{module}'。 可用: {', '.join(available)}",
            )

        # Status-Update
        display = manifests[module].display_name if module in manifests else module
        await status_bus.emit(
            session_id,
            _t(
                f"Rufe {display} auf… ({i + 1}/{len(steps)})",
                f"Calling {display}… ({i + 1}/{len(steps)})",
            ),
        )

        logger.info(
            "Pipeline Schritt %d/%d – delegiere an '%s': %s…",
            i + 1,
            len(steps),
            module,
            task[:80],
        )
        try:
            # Pipeline sub-steps: auto-confirm only if safeguard is disabled or profile is in auto mode.
            # Strict profiles still require per-tool confirmation for destructive operations.
            from agents.base_agent import _global_safeguard

            pipeline_confirmed = (
                _global_safeguard is None
                or not _global_safeguard.enabled
                or getattr(
                    await _global_safeguard.resolve_profile(session_id=session_id),
                    "auto_mode",
                    False,
                )
            )
            result, _ = await agent.invoke(
                message=full_task,
                chat_history=None,
                session_id=session_id,
                confirmed=pipeline_confirmed,
            )
        except _CORE_TOOL_EXCEPTIONS as exc:
            logger.error("Pipeline Schritt %d ('%s') Fehler: %s", i + 1, module, exc)
            result = _t(
                f"Fehler in Modul '{module}': {exc}",
                f"Error in module '{module}': {exc}",
                f"Erreur dans le module '{module}': {exc}",
                f"Error en el módulo '{module}': {exc}",
                f"Errore nel modulo '{module}': {exc}",
                f"Fout in module '{module}': {exc}",
                f"Błąd w module '{module}': {exc}",
                f"Erro no módulo '{module}': {exc}",
                f"モジュール '{module}' でエラーが発生しました: {exc}",
                f"模块 '{module}' 发生错误: {exc}",
            )
        return i, result

    # Gruppen sequenziell abarbeiten, Steps innerhalb einer Gruppe parallel
    for group in groups:
        if aborted:
            break

        if len(group) == 1:
            # Einzelner Step – direkt ausführen
            idx, result = await _execute_step(group[0])
            step_results[idx] = result
            module = steps[idx].get("module", "?")
            results_ordered.append(
                _t(
                    f"**Schritt {idx + 1} – {module}:**\n{result}",
                    f"**Step {idx + 1} – {module}:**\n{result}",
                )
            )
            if any(result.startswith(p) for p in _err_prefixes):
                remaining = sum(len(g) for g in groups[groups.index(group) + 1 :])
                if remaining > 0:
                    results_ordered.append(
                        _t(
                            f"⚠️ Pipeline abgebrochen nach Schritt {idx + 1} – "
                            f"{remaining} weiterer Schritt(e) übersprungen.",
                            f"⚠️ Pipeline aborted after step {idx + 1} – "
                            f"{remaining} remaining step(s) skipped.",
                        )
                    )
                aborted = True
        else:
            # Parallele Ausführung via asyncio.gather
            parallel_label = ", ".join(steps[i].get("module", "?") for i in group)
            await status_bus.emit(
                session_id,
                _t(
                    f"Starte parallel: {parallel_label}",
                    f"Starting in parallel: {parallel_label}",
                ),
            )
            gather_results = await asyncio.gather(
                *[_execute_step(idx) for idx in group],
                return_exceptions=True,
            )
            for item in gather_results:
                if isinstance(item, BaseException):
                    logger.error("Pipeline paralleler Step Fehler: %s", item)
                    continue
                idx, result = item
                step_results[idx] = result
                module = steps[idx].get("module", "?")
                results_ordered.append(
                    _t(
                        f"**Schritt {idx + 1} – {module}:**\n{result}",
                        f"**Step {idx + 1} – {module}:**\n{result}",
                    )
                )
                if any(result.startswith(p) for p in _err_prefixes):
                    aborted = True

            if aborted:
                remaining = sum(len(g) for g in groups[groups.index(group) + 1 :])
                if remaining > 0:
                    results_ordered.append(
                        _t(
                            f"⚠️ Pipeline abgebrochen – "
                            f"{remaining} weiterer Schritt(e) übersprungen.",
                            f"⚠️ Pipeline aborted – "
                            f"{remaining} remaining step(s) skipped.",
                        )
                    )

    return "\n\n".join(results_ordered)


@tool
async def run_parallel_pipeline(groups: list[list[dict]]) -> str:
    """
    Führt Gruppen von Modul-Tasks parallel aus (Fan-out / Fan-in Pattern).
    Steps innerhalb einer Gruppe laufen gleichzeitig via asyncio.gather().
    Gruppen werden sequenziell ausgeführt – die Ergebnisse von Gruppe N
    werden als Kontext an alle Steps in Gruppe N+1 übergeben.

    Jeder Step ist ein Dictionary mit:
    - 'module': Name des Moduls (z.B. 'kubernetes', 'pihole', 'glpi')
    - 'task': Aufgabenbeschreibung für dieses Modul

    Beispiel – K8s und Pi-hole parallel prüfen, dann GLPI-Ticket erstellen:
      groups=[
        [{"module": "kubernetes", "task": "Prüfe alle Pods auf Fehler"},
         {"module": "pihole", "task": "Lade DNS-Fehler-Log"}],
        [{"module": "glpi", "task": "Erstelle Incident-Ticket mit den K8s- und DNS-Ergebnissen"}]
      ]
    """
    # Intern: Konvertiere groups-Format zu depends_on-Format und delegiere an run_pipeline
    flat_steps: list[dict] = []
    group_start = 0
    for gi, group in enumerate(groups):
        prev_indices = (
            list(range(group_start - len(groups[gi - 1]) if gi > 0 else 0, group_start))
            if gi > 0
            else []
        )
        for step in group:
            new_step = {"module": step.get("module", ""), "task": step.get("task", "")}
            if gi == 0:
                new_step["depends_on"] = []
            else:
                new_step["depends_on"] = prev_indices
            flat_steps.append(new_step)
        group_start += len(group)

    return await run_pipeline.ainvoke({"steps": flat_steps})


@tool
async def install_skill(
    name: str,
    description: str,
    content: str,
    modules: list[str] | None = None,
) -> str:
    """
    Erstellt eine neue Skill-Datei und installiert sie dauerhaft im persistenten Skills-Verzeichnis.
    Skills sind prozedurales Domänenwissen das automatisch in passende Agenten injiziert wird.

    Args:
        name: Kurzer Skill-Name (z.B. 'glpi-ticket-templates', 'fritzbox-reboot-procedure')
        description: Wann wird dieser Skill aktiviert? (Trigger-Beschreibung, 1-2 Sätze)
        content: Der eigentliche Skill-Inhalt als Markdown (Anleitungen, Tabellen, Tipps)
        modules: Optionale Liste von Modul-Namen für die dieser Skill gilt (z.B. ['glpi']).
                 Leer lassen = für alle Agenten verfügbar.

    Beispiel für content:
        ## Ticket-Typen\\n| Typ | Wann |\\n|---|---|\\n| Incident | Ausfall/Störung |
    """
    from core.skills_manager import get_skills_manager

    sm = get_skills_manager()
    try:
        skill_path = sm.install_skill(
            name=name,
            description=description,
            content=content,
            modules=modules or [],
        )
        module_info = _t(
            f" (Modul-Filter: {', '.join(modules)})" if modules else " (alle Agenten)",
            f" (module filter: {', '.join(modules)})" if modules else " (all agents)",
        )
        logger.info("Skill '%s' installiert: %s", name, skill_path)
        return _t(
            f"✅ Skill '{name}' erfolgreich installiert{module_info}.\n"
            f"Pfad: {skill_path}\n"
            f"Er wird ab sofort automatisch injiziert wenn eine Anfrage zur Beschreibung passt:\n"
            f'→ "{description}"',
            f"✅ Skill '{name}' successfully installed{module_info}.\n"
            f"Path: {skill_path}\n"
            f"It will be automatically injected whenever a request matches the description:\n"
            f'→ "{description}"',
        )
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler beim Installieren von Skill '%s': %s", name, exc)
        return _t(
            f"Fehler beim Installieren des Skills: {exc}",
            f"Error installing skill: {exc}",
            f"Erreur lors de l'installation du skill : {exc}",
            f"Error al instalar la skill: {exc}",
            f"Errore durante l'installazione della skill: {exc}",
            f"Fout bij het installeren van de skill: {exc}",
            f"Błąd podczas instalacji skillu: {exc}",
            f"Erro ao instalar a skill: {exc}",
            f"スキルのインストール中にエラーが発生しました: {exc}",
            f"安装技能时发生错误: {exc}",
        )


@tool
async def remember_fact(fact: str) -> str:
    """
    Speichert einen wichtigen Fakt dauerhaft im Langzeitgedächtnis (ChromaDB).
    Nutze dieses Tool, wenn der User dir explizit etwas mitteilt, das du dir dauerhaft merken sollst
    (z.B. Namen, IPs, Präferenzen, Entscheidungen, Konfigurationen).
    'fact' sollte ein vollständiger, prägnanter Satz sein – formuliert in der Sprache,
    in der der User gerade kommuniziert (damit spätere Suchanfragen in derselben Sprache matchen).
    """
    try:
        from core.memory import get_memory

        memory = get_memory()
        doc_id = await memory.store(
            content=fact,
            category="agent_memory",
            metadata={"source": "explicit_tool"},
        )
        logger.info("Fakt im Langzeitgedächtnis gespeichert: id=%s", doc_id)
        return _t(f"✅ Gespeichert: '{fact}'", f"✅ Saved: '{fact}'")
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler beim Speichern im Memory: %s", exc)
        return _t(f"Fehler beim Speichern: {exc}", f"Error saving: {exc}")


@tool
async def recall_memory(query: str) -> str:
    """
    Durchsucht das Langzeitgedächtnis semantisch nach relevanten Erinnerungen.
    Nutze dieses Tool, wenn du dir nicht sicher bist ob du etwas weißt, oder wenn
    der User fragt ob du dich an etwas erinnerst.
    Gibt die relevantesten gespeicherten Fakten zurück.
    """
    try:
        from core.memory import get_memory

        memory = get_memory()
        # query() nutzt Composite Scoring (Semantic + Recency + Importance)
        docs = await memory.query(text=query, top_k=5, category="agent_memory")
        if not docs:
            return _t(
                "Keine relevanten Erinnerungen zu dieser Anfrage gefunden.",
                "No relevant memories found for this query.",
                "Aucune mémoire pertinente trouvée pour cette requête.",
                "No se encontraron memorias relevantes para esta consulta.",
                "Nessun ricordo pertinente trovato per questa query.",
                "Geen relevante herinneringen gevonden voor deze query.",
                "Nie znaleziono odpowiednich wspomnień dla tego zapytania.",
                "Nenhuma memória relevante encontrada para esta consulta.",
                "このクエリに関連するメモリが見つかりません。",
                "未找到与此查询相关的记忆。",
            )
        lines = [f"- {doc}" for doc in docs]
        return _t("Gefundene Erinnerungen:\n", "Found memories:\n") + "\n".join(lines)
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler beim Abrufen aus Memory: %s", exc)
        return _t(
            f"Fehler beim Abrufen: {exc}",
            f"Error retrieving: {exc}",
            f"Erreur lors de la récupération : {exc}",
            f"Error al recuperar: {exc}",
            f"Errore durante il recupero: {exc}",
            f"Fout bij het ophalen: {exc}",
            f"Błąd podczas pobierania: {exc}",
            f"Erro ao recuperar: {exc}",
            f"取得中にエラーが発生しました: {exc}",
            f"检索时发生错误: {exc}",
        )


@tool
async def forget_fact(fact: str) -> str:
    """
    SCHRITT 1 von 2: Zeigt Kandidaten im Langzeitgedächtnis, die zum angegebenen Fakt passen.
    Löscht NICHTS – gibt nur eine Vorschau zurück.
    Nutze dieses Tool zuerst, wenn der User etwas vergessen lassen will.
    Zeige dem User die Kandidaten und frage nach Bestätigung, bevor du confirm_forget aufrufst.
    """
    try:
        from core.memory import get_memory

        memory = get_memory()
        hits = await memory.search(query=fact, top_k=5, category="agent_memory")
        if not hits:
            return _t(
                "Keine passenden Erinnerungen zu diesem Thema gefunden.",
                "No matching memories found for this topic.",
                "Aucune mémoire correspondante trouvée pour ce sujet.",
                "No se encontraron memorias coincidentes para este tema.",
                "Nessun ricordo corrispondente trovato per questo argomento.",
                "Geen overeenkomende herinneringen gevonden voor dit onderwerp.",
                "Nie znaleziono odpowiednich wspomnień dla tego tematu.",
                "Nenhuma memória correspondente encontrada para este tópico.",
                "このトピックに関連するメモリが見つかりません。",
                "未找到与此主题相关的记忆。",
            )
        lines = []
        for h in hits:
            dist = h.get("distance", "?")
            dist_str = f"{dist:.3f}" if isinstance(dist, float) else str(dist)
            lines.append(
                _t(
                    f"- ID: `{h['id']}` | Ähnlichkeit: {dist_str} | Inhalt: {h['content']}",
                    f"- ID: `{h['id']}` | Similarity: {dist_str} | Content: {h['content']}",
                )
            )
        preview = "\n".join(lines)
        return _t(
            f"🔍 Folgende Erinnerungen wurden gefunden (noch NICHT gelöscht):\n{preview}\n\n"
            "Soll ich eine oder mehrere davon löschen? Dann nenne mir die ID(s) zur Bestätigung "
            "oder sage 'alle löschen' für alle aufgelisteten Einträge.",
            f"🔍 The following memories were found (NOT yet deleted):\n{preview}\n\n"
            "Should I delete one or more of them? Provide the ID(s) to confirm "
            "or say 'delete all' for all listed entries.",
        )
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler bei Memory-Suche für forget_fact: %s", exc)
        return _t(f"Fehler bei der Suche: {exc}", f"Error searching: {exc}")


@tool
async def confirm_forget(doc_ids: list[str]) -> str:
    """
    SCHRITT 2 von 2: Löscht Einträge aus dem Langzeitgedächtnis anhand ihrer IDs.
    Nur aufrufen, nachdem der User die Kandidaten aus forget_fact gesehen und bestätigt hat.
    'doc_ids' ist die Liste der zu löschenden IDs (aus dem forget_fact-Ergebnis).
    """
    try:
        from core.memory import get_memory

        memory = get_memory()
        for doc_id in doc_ids:
            await memory.delete(doc_id)
        return _t(
            f"🗑️ {len(doc_ids)} Erinnerung(en) dauerhaft gelöscht: {', '.join(doc_ids)}",
            f"🗑️ {len(doc_ids)} memory entry/entries permanently deleted: {', '.join(doc_ids)}",
        )
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler beim Löschen aus Memory: %s", exc)
        return _t(f"Fehler beim Löschen: {exc}", f"Error deleting: {exc}")


@tool
async def speak(text: str, lang: str = "", voice: str = "") -> str:
    """
    Erzeugt eine gesprochene Audio-Ausgabe für den angegebenen Text via Piper TTS.
    Nutze dieses Tool wenn der Benutzer explizit eine Audio-/Sprachausgabe anfordert,
    z.B. "Sag mir das laut vor" oder "Erzeuge eine Sprachansage".

    Gibt eine Audio-URL zurück, die der User im Chat abspielen kann.
    TTS muss aktiviert sein (TTS_ENABLED=true).

    Args:
        text: Zu sprechender Text (deutsch oder englisch je nach lang).
        lang: Sprach-Code (z.B. 'de', 'en'). Leer = Systemstandard (TTS_DEFAULT_LANG).
        voice: Stimmenname (z.B. 'thorsten-medium', 'kerstin-low'). Leer = Systemstandard.
    """
    import base64

    try:
        from core.tts import synthesize_reply, is_tts_available

        if not is_tts_available():
            return _t(
                "TTS ist nicht verfügbar. Bitte TTS_ENABLED=true setzen und piper installieren.",
                "TTS is not available. Please set TTS_ENABLED=true and install piper.",
            )

        wav_bytes = await synthesize_reply(
            text=text,
            lang=lang or None,
            voice=voice or None,
        )
        kb = len(wav_bytes) // 1024
        logger.info(
            "speak-Tool: %d Bytes WAV synthetisiert (%d KB)", len(wav_bytes), kb
        )

        # Audio als Data-URL zurückgeben, damit der Chat-Client es abspielen kann
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        audio_url = f"data:audio/wav;base64,{b64}"

        return _t(
            f"Audio erfolgreich synthetisiert ({kb} KB, {len(text)} Zeichen).\n"
            f"[Audio abspielen]({audio_url})",
            f"Audio successfully synthesized ({kb} KB, {len(text)} characters).\n"
            f"[Play audio]({audio_url})",
        )
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("speak-Tool Fehler: %s", exc)
        return _t(
            f"TTS-Fehler: {exc}",
            f"TTS error: {exc}",
            f"Erreur TTS : {exc}",
            f"Error de TTS: {exc}",
            f"Errore TTS: {exc}",
            f"TTS-fout: {exc}",
            f"Błąd TTS: {exc}",
            f"Erro de TTS: {exc}",
            f"TTSエラー: {exc}",
            f"TTS错误: {exc}",
        )


# ── Self-Adaptive Routing Tools ───────────────────────────────────────────────


@tool
async def configure_routing(
    preset: str = "",
    tier1_enabled: bool | None = None,
    tier2_enabled: bool | None = None,
    tier4_enabled: bool | None = None,
) -> str:
    """Passt das Routing-Verhalten des Orchestrators für die aktuelle Session an.

    Die Änderung gilt NUR für diese Session — nach Session-Ende zurück zu Defaults.

    Drei Routing-Tiers:
    - Tier 4 (Pipeline-Planner): Compound oder explizit sequentielle Multi-Modul-Anfragen
      → LLM-Planner erstellt JSON-Plan → run_pipeline führt ihn aus.
    - Tier 2 (Keyword-Fast-Path): Genau ein Modul eindeutig per Keyword → direkt delegieren.
    - Tier 1 (ReAct-Loop): Alles andere → LLM entscheidet via call_module_agent / run_pipeline.

    Nutze dieses Tool wenn:
    - Routing zurückgesetzt werden soll → preset='default'
    - Pipeline-Planner deaktivieren (schnellere Antworten) → tier4_enabled=False
    - Keyword-Fast-Path deaktivieren (alles durch ReAct-Loop) → tier2_enabled=False
    - ReAct-Loop deaktivieren → tier1_enabled=False

    Preset-Kurzformen: 'default' (reset), 'fast' (kein Tier 4), 'module-only'
    """
    from agents.orchestrator import (
        get_orchestrator,
        RoutingConfig,
        ROUTING_PRESETS,
        get_session_routing_config,
        set_session_routing_config,
        clear_session_routing_config,
    )

    get_orchestrator()  # Validierung: Orchestrator muss initialisiert sein
    session_id = status_bus.get_session_id()

    if preset == "default":
        clear_session_routing_config(session_id)
        return _t(
            "Routing zurückgesetzt auf Standard-Konfiguration (gilt für diese Session).",
            "Routing reset to default configuration (for this session).",
        )

    current = get_session_routing_config(session_id) or RoutingConfig()

    if preset:
        if preset not in ROUTING_PRESETS:
            return _t(
                f"Unbekanntes Preset '{preset}'. Verfügbar: {', '.join(ROUTING_PRESETS.keys())}",
                f"Unknown preset '{preset}'. Available: {', '.join(ROUTING_PRESETS.keys())}",
            )
        current = RoutingConfig.from_dict(
            {**RoutingConfig().to_dict(), **ROUTING_PRESETS[preset]}
        )

    updates = {
        k: v
        for k, v in {
            "tier1_enabled": tier1_enabled,
            "tier2_enabled": tier2_enabled,
            "tier4_enabled": tier4_enabled,
        }.items()
        if v is not None
    }
    if updates:
        current = RoutingConfig.from_dict({**current.to_dict(), **updates})

    set_session_routing_config(session_id, current)

    cfg_dict = current.to_dict()
    lines = [
        f"  Preset: {cfg_dict['preset']}",
        f"  Tier 4 (Pipeline-Planner): {'✓' if cfg_dict['tier4_enabled'] else '✗'}",
        f"  Tier 2 (Keyword-Fast-Path): {'✓' if cfg_dict['tier2_enabled'] else '✗'}",
        f"  Tier 1 (ReAct-Loop): {'✓' if cfg_dict['tier1_enabled'] else '✗'}",
    ]
    return _t(
        "Routing-Konfiguration aktualisiert:\n" + "\n".join(lines),
        "Routing configuration updated:\n" + "\n".join(lines),
    )


@tool
async def get_routing_info() -> str:
    """Gibt die aktuelle Routing-Konfiguration und das zuletzt genutzte Tier zurück.

    Nützlich um zu prüfen welche Routing-Einstellungen aktiv sind — z.B. bevor
    configure_routing aufgerufen wird oder um die Routing-Performance zu beurteilen.
    """
    from agents.orchestrator import (
        get_orchestrator,
        RoutingConfig,
        get_session_routing_config,
    )

    orch = get_orchestrator()
    session_id = status_bus.get_session_id()
    session_cfg = get_session_routing_config(session_id)
    cfg = session_cfg if session_cfg is not None else RoutingConfig()
    last_tier = getattr(orch, "_last_tier_used", "?") if orch else "?"
    source = "Session" if session_cfg is not None else "Default"

    return (
        f"Routing-Konfiguration (Quelle: {source}):\n"
        f"  Preset: {cfg.preset}\n"
        f"  Tier 4 (Pipeline-Planner): {'✓' if cfg.tier4_enabled else '✗'}\n"
        f"  Tier 2 (Keyword-Fast-Path): {'✓' if cfg.tier2_enabled else '✗'}\n"
        f"  Tier 1 (ReAct-Loop): {'✓' if cfg.tier1_enabled else '✗'}\n"
        f"  Zuletzt genutztes Tier: {last_tier}"
    )


@tool
async def wait(seconds: int, reason: str = "") -> str:
    """
    Wartet für eine bestimmte Anzahl von Sekunden, bevor mit der nächsten Aktion fortgefahren wird.
    Nutze dieses Tool, wenn eine Aufgabe etwas Zeit benötigt oder du bewusst eine Pause einlegen möchtest.

    WICHTIG: Dieses Tool blockiert den aktuellen Agenten-Thread für die angegebene Zeit.
    Verwende es nur für kurze Wartezeiten (< 30 Sekunden) oder wenn du sicher bist,
    dass der User auf das Ergebnis wartet.

    Args:
        seconds: Anzahl der Sekunden zum Warten (1-60)
        reason: Optionaler Grund für die Wartezeit (wird im Log protokolliert)

    Beispiele:
    - "Warte 5 Sekunden, bis die Datenbank synchronisiert ist"
    - "Warte 10 Sekunden, bevor du die nächste Abfrage startest"
    """
    if seconds < 1 or seconds > 60:
        return _t(
            f"Fehler: Ungültige Wartezeit. Erlaubt sind 1-60 Sekunden (angefordert: {seconds}).",
            f"Error: Invalid wait time. Allowed range is 1-60 seconds (requested: {seconds}).",
            f"Erreur : Temps d'attente invalide. La plage autorisée est de 1-60 secondes (demandé : {seconds}).",
            f"Error: Tiempo de espera no válido. El rango permitido es de 1-60 segundos (solicitado: {seconds}).",
            f"Errore: Tempo di attesa non valido. L'intervallo consentito è 1-60 secondi (richiesto: {seconds}).",
            f"Fout: Ongeldige wachttijd. Toegestaan bereik is 1-60 seconden (aangevraagd: {seconds}).",
            f"Błąd: Nieprawidłowy czas oczekiwania. Dozwolony zakres to 1-60 sekund (żądane: {seconds}).",
            f"Erro: Tempo de espera inválido. O intervalo permitido é 1-60 segundos (solicitado: {seconds}).",
            f"エラー: 無効な待機時間。許可範囲は1〜60秒です（要求: {seconds}秒）。",
            f"错误: 无效的等待时间。允许范围为1-60秒（请求: {seconds}秒）。",
        )

    if reason:
        logger.info("Warte %d Sekunden auf Grund: %s", seconds, reason)
    else:
        logger.info("Warte %d Sekunden (kein Grund angegeben)", seconds)

    try:
        await asyncio.sleep(seconds)
        return _t(
            f"⏳ Gewartet für {seconds} Sekunden. Fortsetzung...",
            f"⏳ Waited for {seconds} seconds. Continuing...",
        )
    except asyncio.CancelledError:
        logger.warning("Warte-Operation wurde abgebrochen")
        return _t(
            "⚠️ Warte-Operation wurde abgebrochen.",
            "⚠️ Wait operation was cancelled.",
        )
    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Fehler während der Wartezeit: %s", exc)
        return _t(
            f"Fehler während der Wartezeit: {exc}",
            f"Error during wait: {exc}",
        )


# ── Knowledge Graph Tools ────────────────────────────────────────────────────


@tool
async def kg_find_related(entity_type: str, entity_name: str) -> str:
    """
    Findet verwandte Entitäten im Knowledge Graph zu einem gegebenen Entity.

    Nutze dieses Tool um Abhängigkeiten, verwandte Systeme oder ähnliche Incidents
    zu entdecken. Das hilft bei Troubleshooting und Impact-Analyse.

    Args:
        entity_type: Typ der Entität (module, service, host, incident, configuration)
        entity_name: Name der Entität (z.B. "proxmox", "pihole", "nginx-proxy")

    Returns:
        Liste verwandter Entitäten mit Beziehungstyp und Grund

    Beispiele:
    - kg_find_related("module", "proxmox") → Systeme, die von Proxmox abhängen
    - kg_find_related("incident", "2024-01-dns-ausfall") → Ähnliche vergangene Incidents
    """
    try:
        from core.knowledge_graph import get_knowledge_graph

        kg = await get_knowledge_graph()

        # Versuche direkte ID oder suche nach Namen
        entity_id = f"{entity_type}:{entity_name}"

        # Falls nicht gefunden, suche nach Name-Property
        if entity_id not in kg._graph:
            all_entities = await kg.find_by_type(entity_type)
            for ent in all_entities:
                if ent.get("name") == entity_name or entity_name in ent.get("id", ""):
                    entity_id = ent.get("id")
                    break

        if entity_id not in kg._graph:
            return _t(
                f"Entität '{entity_name}' ({entity_type}) nicht im Knowledge Graph gefunden.",
                f"Entity '{entity_name}' ({entity_type}) not found in Knowledge Graph.",
            )

        related = await kg.suggest_related(entity_id)

        if not related:
            return _t(
                f"Keine verwandten Entitäten für '{entity_name}' gefunden.",
                f"No related entities found for '{entity_name}'.",
            )

        lines = [
            _t(
                f"Verwandte Entitäten zu '{entity_name}':\n",
                f"Related entities to '{entity_name}':\n",
            )
        ]

        for item in related[:8]:
            ent = item.get("entity", {})
            reason = item.get("reason", "")
            score = item.get("score", 0)
            ent_type = ent.get("type", "unknown")
            ent_name = ent.get("name", ent.get("id", "unknown"))
            lines.append(f"• [{ent_type}] {ent_name} (Score: {score:.2f}) – {reason}")

        return "\n".join(lines)

    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Knowledge Graph Fehler: %s", exc)
        return _t(
            f"Fehler beim Knowledge Graph Lookup: {exc}",
            f"Error during Knowledge Graph lookup: {exc}",
        )


@tool
async def kg_find_path(source: str, target: str) -> str:
    """
    Findet den Pfad (Ketten von Beziehungen) zwischen zwei Entitäten im Knowledge Graph.

    Nützlich für Impact-Analysen: "Was hängt alles an diesem System?"
    oder Root-Cause-Analysen: "Welches System könnte den Fehler verursacht haben?"

    Args:
        source: Start-Entität (z.B. "module:proxmox" oder "service:nginx")
        target: Ziel-Entität (z.B. "host:pve1" oder "module:pihole")

    Returns:
        Liste möglicher Pfade mit Beziehungen

    Beispiele:
    - kg_find_path("module:proxmox", "module:pihole") → Finde Verbindung zwischen Systemen
    - kg_find_path("host:pve1", "service:dns") → Welche DNS-Abhängigkeiten hat dieser Host?
    """
    try:
        from core.knowledge_graph import get_knowledge_graph

        kg = await get_knowledge_graph()
        paths = await kg.get_path(source, target, max_depth=5)

        if not paths:
            return _t(
                f"Kein Pfad zwischen '{source}' und '{target}' gefunden.",
                f"No path found between '{source}' and '{target}'.",
            )

        lines = [
            _t(
                f"Gefundene Pfade von '{source}' zu '{target}':\n",
                f"Found paths from '{source}' to '{target}':\n",
            )
        ]

        for i, path in enumerate(paths[:3], 1):
            lines.append(f"\nPfad {i}:")
            for j, node_id in enumerate(path):
                node = kg._graph.nodes.get(node_id, {})
                node_name = node.get("name", node_id)
                if j < len(path) - 1:
                    edge = kg._graph.edges.get((node_id, path[j + 1]), {})
                    rel = edge.get("relation", "→")
                    lines.append(f"  [{node_name}] --({rel})-->")
                else:
                    lines.append(f"  [{node_name}]")

        return "\n".join(lines)

    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Knowledge Graph Pfad-Fehler: %s", exc)
        return _t(
            f"Fehler beim Pfad-Suchen: {exc}",
            f"Error finding path: {exc}",
        )


@tool
async def kg_analyze_dependencies(module_name: str) -> str:
    """
    Analysiert alle Abhängigkeiten (inbound und outbound) eines Moduls/Systems.

    Args:
        module_name: Name des Moduls (z.B. "proxmox", "kubernetes", "pihole")

    Returns:
        Dependency-Analyse mit Impact-Bewertung
    """
    try:
        from core.knowledge_graph import get_knowledge_graph, RelationType

        kg = await get_knowledge_graph()
        module_id = f"module:{module_name}"

        if module_id not in kg._graph:
            return _t(
                f"Modul '{module_name}' nicht im Knowledge Graph gefunden.",
                f"Module '{module_name}' not found in Knowledge Graph.",
            )

        # Outgoing: Was hängt an diesem Modul?
        outgoing = await kg.get_neighbors(module_id, RelationType.DEPENDS_ON)
        outgoing_targets = [n for n in outgoing if n.get("direction") == "out"]

        # Incoming: Was hängt von diesem Modul ab?
        incoming = await kg.get_neighbors(module_id, RelationType.DEPENDS_ON)
        incoming_sources = [n for n in incoming if n.get("direction") == "in"]

        lines = [
            _t(
                f"Abhängigkeits-Analyse für '{module_name}':\n",
                f"Dependency analysis for '{module_name}':\n",
            )
        ]

        if outgoing_targets:
            lines.append(
                _t("\nDieses Modul hängt ab von:\n", "\nThis module depends on:\n")
            )
            for n in outgoing_targets[:10]:
                ent = n.get("entity", {})
                lines.append(
                    f"  • {ent.get('name', 'unknown')} ({ent.get('type', 'unknown')})"
                )
        else:
            lines.append(
                _t("\nKeine ausgehenden Abhängigkeiten.", "\nNo outgoing dependencies.")
            )

        if incoming_sources:
            lines.append(
                _t("\nVon diesem Modul hängen ab:\n", "\nSystems depending on this:\n")
            )
            for n in incoming_sources[:10]:
                ent = n.get("entity", {})
                lines.append(
                    f"  • {ent.get('name', 'unknown')} ({ent.get('type', 'unknown')})"
                )
            lines.append(
                _t(
                    f"\n⚠️ Impact: Ein Ausfall betrifft {len(incoming_sources)} Systeme!",
                    f"\n⚠️ Impact: An outage affects {len(incoming_sources)} systems!",
                )
            )
        else:
            lines.append(
                _t("\nKeine eingehenden Abhängigkeiten.", "\nNo incoming dependencies.")
            )

        return "\n".join(lines)

    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Knowledge Graph Analyse-Fehler: %s", exc)
        return _t(
            f"Fehler bei der Abhängigkeits-Analyse: {exc}",
            f"Error in dependency analysis: {exc}",
        )


@tool
async def kg_record_incident(
    module: str,
    summary: str,
    details: str,
    resolution: str = "",
) -> str:
    """
    Speichert einen Incident im Knowledge Graph für zukünftige Analysen.

    Automatisch extrahiert: Entitäten, Beziehungen und speichert im Semantic Memory.
    Der Incident ist danach über kg_find_related() auffindbar.

    Args:
        module: Betroffenes Modul (z.B. "proxmox", "kubernetes")
        summary: Kurze Zusammenfassung des Problems
        details: Detaillierte Beschreibung
        resolution: Lösung/Resolution (optional)

    Returns:
        Bestätigung mit extrahierten Entitäten
    """
    try:
        from core.knowledge_graph import get_knowledge_graph

        kg = await get_knowledge_graph()
        result = await kg.extract_from_incident(
            module=module,
            summary=summary,
            details=details,
            resolution=resolution or None,
        )

        entities = result.get("entities", [])
        relationships = result.get("relationships", [])

        return _t(
            f"✅ Incident aufgezeichnet: {len(entities)} Entitäten, {len(relationships)} Beziehungen.\n"
            f"ID: {entities[-1] if entities else 'n/a'}\n"
            f"Verfügbar für zukünftige Analysen via kg_find_related().",
            f"✅ Incident recorded: {len(entities)} entities, {len(relationships)} relationships.\n"
            f"ID: {entities[-1] if entities else 'n/a'}\n"
            f"Available for future analysis via kg_find_related().",
        )

    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("Knowledge Graph Incident-Fehler: %s", exc)
        return _t(
            f"Fehler beim Speichern des Incidents: {exc}",
            f"Error recording incident: {exc}",
        )


# ── PDF Report Generation ───────────────────────────


@tool
async def generate_pdf_report(
    title: str,
    content_markdown: str,
    output_path: str = "/tmp/ninko-reports/report.pdf",
) -> str:
    """
    Erstellt ein PDF aus Markdown-Inhalt.

    Nutzt weasyprint (Markdown → HTML → PDF). Das Output-Verzeichnis wird
    automatisch erstellt falls nicht vorhanden.

    Args:
        title: Titel des Reports (wird im PDF Header verwendet)
        content_markdown: Der Inhalt als Markdown-Text
        output_path: Zielpfad für die PDF-Datei (default: /tmp/ninko-reports/report.pdf)

    Returns:
        Absoluter Pfad zur erstellten PDF-Datei
    """
    import os
    from pathlib import Path

    try:
        import markdown
        from weasyprint import HTML, CSS
    except ImportError as exc:
        logger.error("PDF-Generierung nicht verfügbar: %s", exc)
        return _t(
            "Fehler: PDF-Generierung nicht verfügbar (weasyprint nicht installiert)",
            "Error: PDF generation not available (weasyprint not installed)",
        )

    try:
        # Verzeichnis erstellen falls nicht vorhanden
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Markdown zu HTML konvertieren
        html_content = markdown.markdown(
            content_markdown,
            extensions=["tables", "fenced_code", "toc"],
        )

        # HTML mit Styling umgeben
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                    @top-center {{
                        content: "{title}";
                        font-size: 9pt;
                        color: #666;
                    }}
                    @bottom-center {{
                        content: "Seite " counter(page) " von " counter(pages);
                        font-size: 9pt;
                        color: #666;
                    }}
                }}
                body {{
                    font-family: 'DejaVu Sans', Arial, sans-serif;
                    font-size: 11pt;
                    line-height: 1.6;
                    color: #333;
                }}
                h1 {{
                    color: #2c3e50;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 0.3em;
                    font-size: 18pt;
                }}
                h2 {{
                    color: #34495e;
                    border-bottom: 1px solid #bdc3c7;
                    padding-bottom: 0.2em;
                    font-size: 14pt;
                    margin-top: 1.5em;
                }}
                h3 {{
                    color: #7f8c8d;
                    font-size: 12pt;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 1em 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #f5f5f5;
                    font-weight: bold;
                }}
                tr:nth-child(even) {{
                    background-color: #fafafa;
                }}
                code {{
                    background-color: #f4f4f4;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'DejaVu Sans Mono', monospace;
                    font-size: 10pt;
                }}
                pre {{
                    background-color: #f4f4f4;
                    padding: 12px;
                    border-radius: 4px;
                    overflow-x: auto;
                    border-left: 4px solid #3498db;
                }}
                blockquote {{
                    border-left: 4px solid #95a5a6;
                    margin: 1em 0;
                    padding-left: 1em;
                    color: #555;
                    font-style: italic;
                }}
                ul, ol {{
                    margin: 1em 0;
                    padding-left: 2em;
                }}
                li {{
                    margin: 0.3em 0;
                }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
            {html_content}
        </body>
        </html>
        """

        # PDF generieren
        HTML(string=full_html).write_pdf(output_path)

        # Absoluten Pfad zurückgeben
        abs_path = str(Path(output_path).resolve())

        logger.info(
            "PDF-Report erstellt: %s (%d bytes)",
            abs_path,
            Path(output_path).stat().st_size,
        )

        return _t(
            f"✅ PDF-Report erstellt: {abs_path}",
            f"✅ PDF report created: {abs_path}",
        )

    except _CORE_TOOL_EXCEPTIONS as exc:
        logger.error("PDF-Generierungsfehler: %s", exc)
        return _t(
            f"Fehler bei der PDF-Generierung: {exc}",
            f"Error generating PDF: {exc}",
        )
