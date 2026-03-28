"""
Core Tools for Ninko Agents.
These tools provide fundamental system capabilities rather than domain-specific modular functions.
"""

import asyncio
import logging
import shlex
from pathlib import Path
from langchain_core.tools import tool

# Strong references to background tasks to prevent premature GC
_background_tasks: set[asyncio.Task] = set()


def _t(de: str, en: str) -> str:
    """Gibt DE oder EN zurück abhängig von der LANGUAGE-Einstellung."""
    try:
        from core.config import get_settings
        return de if get_settings().LANGUAGE == "de" else en
    except Exception:
        return de

# Whitelist of allowed executables for execute_cli_command
_ALLOWED_COMMANDS = {
    "uptime", "ping", "df", "free", "ps", "uname", "hostname",
    "netstat", "ss", "ip", "dig", "nslookup", "traceroute",
    "cat", "ls", "echo", "date", "who", "w",
    "systemctl", "journalctl", "dmesg", "curl", "wget", "nmap",
}

logger = logging.getLogger("ninko.agents.core_tools")

# opencode-Prinzip: Tool-Outputs auf sinnvolle Größe begrenzen
_MAX_OUTPUT_CHARS = 4000
_MAX_OUTPUT_LINES = 200


def _truncate_output(text: str, max_chars: int = _MAX_OUTPUT_CHARS, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    """
    Kürzt Tool-Output auf max_lines Zeilen ODER max_chars Zeichen (was zuerst greift).
    Fügt am Ende einen Hinweis ein dass mehr Daten vorhanden sind.
    Analog zu opencode's Truncate.output() Prinzip.
    """
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

    return (
        f"{preview}\n\n"
        + _t(
            f"[…{hint} gekürzt – frage nach einem spezifischen Teil wenn du mehr benötigst]",
            f"[…{hint} truncated – ask for a specific part if you need more]",
        )
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
            args = shlex.split(command)
        except ValueError as e:
            return _t(f"Fehler: Ungültige Befehlssyntax: {e}", f"Error: Invalid command syntax: {e}")

        if not args:
            return _t("Fehler: Leerer Befehl.", "Error: Empty command.")

        cmd_name = Path(args[0]).name
        if cmd_name not in _ALLOWED_COMMANDS:
            return _t(
                f"Fehler: Befehl '{cmd_name}' ist nicht erlaubt. "
                f"Erlaubte Befehle: {', '.join(sorted(_ALLOWED_COMMANDS))}",
                f"Error: Command '{cmd_name}' is not allowed. "
                f"Allowed commands: {', '.join(sorted(_ALLOWED_COMMANDS))}",
            )

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
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
            )

        out_str = stdout.decode('utf-8', errors='replace').strip() if stdout else ""
        err_str = stderr.decode('utf-8', errors='replace').strip() if stderr else ""

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

    except Exception as exc:
        logger.error("Fehler bei CLI-Kommando '%s': %s", command, exc)
        return _t(
            f"Fehler bei der Ausführung von '{command}': {exc}",
            f"Error executing '{command}': {exc}",
        )

@tool
async def create_custom_agent(name: str, system_prompt: str, description: str = "") -> str:
    """
    Erstellt einen neuen benutzerspezifischen Agenten in Ninko.
    Dies ist nützlich, um spezialisierte KI-Personas für bestimmte Aufgaben dauerhaft anzulegen.
    Der Agent wird sofort im Agenten-Pool registriert und ist für zukünftige Aufgaben wiederverwendbar.
    Gibt die ID des neu erstellten Agenten zurück.
    """
    from core.agent_pool import get_agent_pool

    pool = get_agent_pool()
    agent_id, _ = await pool.register(name=name, system_prompt=system_prompt, description=description)
    logger.info("Custom Agent via Tool erstellt und im Pool registriert: %s (%s)", name, agent_id)

    return _t(
        f"Agent '{name}' (ID: {agent_id}) wurde erfolgreich erstellt und ist sofort im Agenten-Pool verfügbar.",
        f"Agent '{name}' (ID: {agent_id}) was successfully created and is immediately available in the agent pool.",
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
    nodes = [{
        "id": trigger_id,
        "type": "trigger",
        "label": "Start",
        "config": {"mode": "manual"},
        "position": {"x": 100, "y": 100}
    }]
    edges = []
    
    # 2. Agent Nodes & Edges
    prev_id = trigger_id
    y_pos = 250
    for i, step_prompt in enumerate(steps):
        node_id = str(uuid.uuid4())[:8]
        nodes.append({
            "id": node_id,
            "type": "agent",
            "label": f"Step {i+1}",
            "config": {"agent_id": "orchestrator", "prompt": step_prompt},
            "position": {"x": 100, "y": y_pos}
        })
        edges.append({
            "id": str(uuid.uuid4())[:8],
            "source_id": prev_id,
            "target_id": node_id,
            "label": ""
        })
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
        "updated_at": now
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
    
    wf = next((w for w in workflows if w["id"] == workflow_name_or_id or w["name"].lower() == workflow_name_or_id.lower()), None)
    if not wf:
        return _t(
            f"Fehler: Workflow '{workflow_name_or_id}' nicht gefunden.",
            f"Error: Workflow '{workflow_name_or_id}' not found.",
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
        triggered_by="AI_Agent"
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
            return "Fehler: Orchestrator noch nicht initialisiert."
        engine = WorkflowEngine(redis, orchestrator)
        _task = asyncio.create_task(engine.execute(wf, run_id))
        _background_tasks.add(_task)
        _task.add_done_callback(_background_tasks.discard)
    except Exception as exc:
        return f"Kritischer Fehler beim Starten des Workflows: {exc}"
        
    # Poll variables
    max_retries = 120 # 2 Minutes timeout
    
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
            if current_run.get('error'):
                trace += _t(
                    f"- **Fehler:** {current_run.get('error')}\n",
                    f"- **Error:** {current_run.get('error')}\n",
                )
            trace += _t("### Details pro Schritt:\n", "### Step details:\n")

            for step in current_run.get("steps", []):
                sym = "✅" if step.get("status") == "succeeded" else "❌" if step.get("status") == "failed" else "⏳" if step.get("status") == "pending" else "⏭️"
                trace += _t(
                    f"\n- {sym} **{step.get('node_label')}** ({step.get('node_type')}) [Dauer: {step.get('duration_ms', 0)} ms]\n",
                    f"\n- {sym} **{step.get('node_label')}** ({step.get('node_type')}) [Duration: {step.get('duration_ms', 0)} ms]\n",
                )

                output = step.get('output')
                if output:
                    # Prevent breaking details tag formatting
                    safe_out = output.replace('\n', '\n> ')
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
        return _t("Fehler: Orchestrator noch nicht initialisiert.", "Error: Orchestrator not yet initialized.")

    agent = orchestrator.registry.get_agent(module_name)
    if agent is None:
        available = [m.name for m in orchestrator.registry.list_modules()]
        return _t(
            f"Fehler: Modul '{module_name}' nicht gefunden oder nicht aktiv. "
            f"Verfügbare Module: {', '.join(available)}",
            f"Error: Module '{module_name}' not found or not active. "
            f"Available modules: {', '.join(available)}",
        )

    session_id = status_bus.get_session_id()
    logger.info("call_module_agent: delegiere an '%s': %s…", module_name, task[:80])
    try:
        result, _ = await agent.invoke(message=task, chat_history=None, session_id=session_id)
        return result
    except Exception as exc:
        logger.error("call_module_agent Fehler bei '%s': %s", module_name, exc)
        return _t(
            f"Fehler im Modul '{module_name}': {exc}",
            f"Error in module '{module_name}': {exc}",
        )


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

    Beispiele:
    - "Recherchiere X und sende Email": steps=[
        {"module": "web_search", "task": "Recherchiere aktuelle Infos über X"},
        {"module": "email", "task": "Sende die Recherche-Ergebnisse an user@example.com als HTML-Email"}
      ]
    - "Prüfe K8s und erstelle GLPI-Ticket": steps=[
        {"module": "kubernetes", "task": "Prüfe alle Pods auf Fehler"},
        {"module": "glpi", "task": "Erstelle ein Incident-Ticket für die gefundenen Pod-Fehler"}
      ]
    """
    from agents.orchestrator import get_orchestrator
    from core import status_bus

    orchestrator = get_orchestrator()
    if orchestrator is None:
        return _t("Fehler: Orchestrator noch nicht initialisiert.", "Error: Orchestrator not yet initialized.")

    if not steps:
        return _t("Fehler: Keine Schritte angegeben.", "Error: No steps provided.")

    session_id = status_bus.get_session_id()
    results: list[str] = []
    context = ""

    # Display-Namen der Module für Status-Updates voraufladen
    manifests = {m.name: m for m in orchestrator.registry.list_modules()}

    for i, step in enumerate(steps):
        module = step.get("module", "").strip()
        task = step.get("task", "").strip()

        if not module or not task:
            results.append(_t(
                f"⚠️ Schritt {i + 1}: Übersprungen (module oder task fehlt).",
                f"⚠️ Step {i + 1}: Skipped (module or task missing).",
            ))
            continue

        # Kontext aus vorherigem Schritt einfügen
        full_task = task
        if context:
            prev_module = steps[i - 1].get("module", _t("vorheriger Schritt", "previous step"))
            full_task = task + "\n\n" + _t(
                f"Verwende folgende Ergebnisse aus '{prev_module}' als Inhalt:\n{context}",
                f"Use the following results from '{prev_module}' as content:\n{context}",
            )

        agent = orchestrator.registry.get_agent(module)
        if agent is None:
            available = [m.name for m in orchestrator.registry.list_modules()]
            result = _t(
                f"Fehler: Modul '{module}' nicht gefunden. "
                f"Verfügbar: {', '.join(available)}",
                f"Error: Module '{module}' not found. "
                f"Available: {', '.join(available)}",
            )
        else:
            # Status-Update für diesen Schritt emittieren
            display = manifests[module].display_name if module in manifests else module
            await status_bus.emit(
                session_id,
                _t(f"Rufe {display} auf… ({i + 1}/{len(steps)})", f"Calling {display}… ({i + 1}/{len(steps)})"),
            )

            logger.info(
                "Pipeline Schritt %d/%d – delegiere an '%s': %s…",
                i + 1, len(steps), module, task[:80],
            )
            try:
                result, _ = await agent.invoke(message=full_task, chat_history=None, session_id=session_id)
            except Exception as exc:
                logger.error("Pipeline Schritt %d ('%s') Fehler: %s", i + 1, module, exc)
                result = _t(
                    f"Fehler in Modul '{module}': {exc}",
                    f"Error in module '{module}': {exc}",
                )

        context = result
        results.append(_t(
            f"**Schritt {i + 1} – {module}:**\n{result}",
            f"**Step {i + 1} – {module}:**\n{result}",
        ))

        # Abbruch bei Fehler oder Timeout – Folgeschritte überspringen (DE + EN)
        _err_prefixes = (
            "Fehler",
            "Die Anfrage hat zu lange gedauert",
            "Entschuldigung, es ist ein Fehler",
            "Error",
            "The request took too long",
            "Sorry, an error occurred",
        )
        if any(result.startswith(p) for p in _err_prefixes):
            skipped = len(steps) - i - 1
            if skipped > 0:
                results.append(_t(
                    f"⚠️ Pipeline abgebrochen nach Schritt {i + 1} – "
                    f"{skipped} weiterer Schritt(e) übersprungen.",
                    f"⚠️ Pipeline aborted after step {i + 1} – "
                    f"{skipped} remaining step(s) skipped.",
                ))
            break

    return "\n\n".join(results)


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
            f"→ \"{description}\"",
            f"✅ Skill '{name}' successfully installed{module_info}.\n"
            f"Path: {skill_path}\n"
            f"It will be automatically injected whenever a request matches the description:\n"
            f"→ \"{description}\"",
        )
    except Exception as exc:
        logger.error("Fehler beim Installieren von Skill '%s': %s", name, exc)
        return _t(
            f"Fehler beim Installieren des Skills: {exc}",
            f"Error installing skill: {exc}",
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
    except Exception as exc:
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
        hits = await memory.search(query=query, top_k=5, category="agent_memory")
        if not hits:
            return _t(
                "Keine relevanten Erinnerungen zu dieser Anfrage gefunden.",
                "No relevant memories found for this query.",
            )
        lines = [f"- {h['content']}" for h in hits]
        return _t("Gefundene Erinnerungen:\n", "Found memories:\n") + "\n".join(lines)
    except Exception as exc:
        logger.error("Fehler beim Abrufen aus Memory: %s", exc)
        return _t(f"Fehler beim Abrufen: {exc}", f"Error retrieving: {exc}")


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
            )
        lines = []
        for h in hits:
            dist = h.get('distance', '?')
            dist_str = f"{dist:.3f}" if isinstance(dist, float) else str(dist)
            lines.append(_t(
                f"- ID: `{h['id']}` | Ähnlichkeit: {dist_str} | Inhalt: {h['content']}",
                f"- ID: `{h['id']}` | Similarity: {dist_str} | Content: {h['content']}",
            ))
        preview = "\n".join(lines)
        return _t(
            f"🔍 Folgende Erinnerungen wurden gefunden (noch NICHT gelöscht):\n{preview}\n\n"
            "Soll ich eine oder mehrere davon löschen? Dann nenne mir die ID(s) zur Bestätigung "
            "oder sage 'alle löschen' für alle aufgelisteten Einträge.",
            f"🔍 The following memories were found (NOT yet deleted):\n{preview}\n\n"
            "Should I delete one or more of them? Provide the ID(s) to confirm "
            "or say 'delete all' for all listed entries.",
        )
    except Exception as exc:
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
    except Exception as exc:
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
        logger.info("speak-Tool: %d Bytes WAV synthetisiert (%d KB)", len(wav_bytes), kb)

        # Audio als Data-URL zurückgeben, damit der Chat-Client es abspielen kann
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        audio_url = f"data:audio/wav;base64,{b64}"

        return _t(
            f"Audio erfolgreich synthetisiert ({kb} KB, {len(text)} Zeichen).\n"
            f"[Audio abspielen]({audio_url})",
            f"Audio successfully synthesized ({kb} KB, {len(text)} characters).\n"
            f"[Play audio]({audio_url})",
        )
    except Exception as exc:
        logger.error("speak-Tool Fehler: %s", exc)
        return _t(f"TTS-Fehler: {exc}", f"TTS error: {exc}")


# ── Self-Adaptive Routing Tools ───────────────────────────────────────────────

@tool
async def configure_routing(
    preset: str = "",
    tier1_enabled: bool | None = None,
    tier2_enabled: bool | None = None,
) -> str:
    """Passt das Routing-Verhalten des Orchestrators für die aktuelle Session an.

    Die Änderung gilt NUR für diese Session — nach Session-Ende zurück zu Defaults.

    Zwei Routing-Tiers:
    - Tier 2 (Keyword-Fast-Path): Genau ein Modul eindeutig per Keyword erkannt → direkt delegieren.
    - Tier 1 (ReAct-Loop): Alles andere → LLM entscheidet selbst via call_module_agent / run_pipeline.

    Nutze dieses Tool wenn:
    - Routing zurückgesetzt werden soll → preset='default'
    - Keyword-Fast-Path deaktivieren (alles durch ReAct-Loop) → tier2_enabled=False
    - ReAct-Loop für nicht-gematchte Anfragen deaktivieren → tier1_enabled=False

    Preset-Kurzformen: 'default' (reset), 'fast', 'module-only'
    """
    from agents.orchestrator import (
        get_orchestrator, RoutingConfig, ROUTING_PRESETS,
        get_session_routing_config, set_session_routing_config, clear_session_routing_config,
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
        current = RoutingConfig.from_dict({**RoutingConfig().to_dict(), **ROUTING_PRESETS[preset]})

    updates = {k: v for k, v in {"tier1_enabled": tier1_enabled, "tier2_enabled": tier2_enabled}.items() if v is not None}
    if updates:
        current = RoutingConfig.from_dict({**current.to_dict(), **updates})

    set_session_routing_config(session_id, current)

    cfg_dict = current.to_dict()
    lines = [
        f"  Preset: {cfg_dict['preset']}",
        f"  Tier 1 (ReAct-Loop): {'✓' if cfg_dict['tier1_enabled'] else '✗'}",
        f"  Tier 2 (Keyword-Fast-Path): {'✓' if cfg_dict['tier2_enabled'] else '✗'}",
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
    from agents.orchestrator import get_orchestrator, RoutingConfig, get_session_routing_config

    orch = get_orchestrator()
    session_id = status_bus.get_session_id()
    session_cfg = get_session_routing_config(session_id)
    cfg = session_cfg if session_cfg is not None else RoutingConfig()
    last_tier = getattr(orch, "_last_tier_used", "?") if orch else "?"
    source = "Session" if session_cfg is not None else "Default"

    return (
        f"Routing-Konfiguration (Quelle: {source}):\n"
        f"  Preset: {cfg.preset}\n"
        f"  Tier 1 (direkt): {'✓' if cfg.tier1_enabled else '✗'} | max {cfg.simple_query_max_chars} Zeichen\n"
        f"  Tier 2 (Modul): {'✓' if cfg.tier2_enabled else '✗'} | LLM-Fallback: {'✓' if cfg.llm_routing_enabled else '✗'} ({cfg.llm_routing_timeout}s timeout)\n"
        f"  Tier 3 (dynamisch): {'✓' if cfg.tier3_enabled else '✗'}\n"
        f"  Tier 4 (Pipeline): {'✓' if cfg.tier4_enabled else '✗'} | Mehrstufige Erkennung: {'✓' if cfg.multistep_detection_enabled else '✗'}\n"
        f"  Zuletzt genutztes Tier: {last_tier}"
    )
