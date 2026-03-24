"""
Ninko BaseAgent – Abstrakte Basis für alle Agenten.
Nutzt LangGraph für Tool-Calling und Conversation-Management.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from core.llm_factory import get_llm, get_model_context_window, get_llm_generation
from core.memory import get_memory
from core.context_manager import get_context_manager
from core import status_bus

logger = logging.getLogger("ninko.agents.base")


def _get_language() -> str:
    """Gibt den konfigurierten Sprach-Code zurück (gecacht, Fallback: 'de')."""
    try:
        from core.config import get_settings
        return get_settings().LANGUAGE
    except Exception:
        return "de"


def _t(de: str, en: str) -> str:
    """Gibt den deutschen oder englischen Text zurück, je nach LANGUAGE-Setting."""
    return de if _get_language() == "de" else en


# ── Tool-Name → Status-Label (DE / EN) ──────────────────────────────────────
_TOOL_LABELS: dict[str, tuple[str, str]] = {
    "execute_code":             ("Führe Code aus",                "Executing code"),
    "get_available_languages":  ("Prüfe verfügbare Sprachen",     "Checking available languages"),
    "get_cluster_status":       ("Lade Cluster-Status",           "Loading cluster status"),
    "get_all_pods":             ("Lade Pods",                     "Loading pods"),
    "get_failing_pods":         ("Prüfe fehlerhafte Pods",        "Checking failing pods"),
    "list_namespaces":          ("Lade Namespaces",               "Loading namespaces"),
    "list_services":            ("Lade Services",                 "Loading services"),
    "restart_pod":              ("Starte Pod neu",                "Restarting pod"),
    "rollout_restart":          ("Führe Rollout-Restart durch",   "Performing rollout restart"),
    "scale_deployment":         ("Skaliere Deployment",           "Scaling deployment"),
    "get_recent_events":        ("Lade Cluster-Events",           "Loading cluster events"),
    "get_pihole_summary":       ("Lade Pi-hole Statistiken",      "Loading Pi-hole statistics"),
    "get_query_log":            ("Lade DNS-Query-Log",            "Loading DNS query log"),
    "toggle_blocking":          ("Konfiguriere Blocking",         "Configuring blocking"),
    "add_domain_to_list":       ("Aktualisiere Domain-Liste",     "Updating domain list"),
    "remove_domain_from_list":  ("Aktualisiere Domain-Liste",     "Updating domain list"),
    "update_gravity":           ("Aktualisiere Gravity",          "Updating gravity"),
    "flush_dns_cache":          ("Leere DNS-Cache",               "Flushing DNS cache"),
    "perform_web_search":       ("Durchsuche das Web",            "Searching the web"),
    "web_search":               ("Durchsuche das Web",            "Searching the web"),
    "execute_cli_command":      ("Führe CLI-Befehl aus",          "Executing CLI command"),
    "call_module_agent":        ("Rufe Modul-Agent auf",          "Calling module agent"),
    "run_pipeline":             ("Führe Pipeline aus",            "Running pipeline"),
    "create_linear_workflow":   ("Erstelle Workflow",             "Creating workflow"),
    "execute_workflow":         ("Führe Workflow aus",             "Executing workflow"),
    "remember_fact":            ("Speichere im Gedächtnis",       "Saving to memory"),
    "recall_memory":            ("Durchsuche Gedächtnis",         "Searching memory"),
    "forget_fact":              ("Suche zu löschende Fakten",     "Searching facts to forget"),
    "confirm_forget":           ("Lösche Fakten",                 "Deleting facts"),
    "create_custom_agent":      ("Erstelle Agenten",              "Creating agent"),
    "install_skill":            ("Installiere Skill",             "Installing skill"),
    "get_fritzbox_status":      ("Lade FritzBox-Status",          "Loading FritzBox status"),
    "get_connected_devices":    ("Lade verbundene Geräte",        "Loading connected devices"),
    "get_call_list":            ("Lade Anrufliste",               "Loading call list"),
    "get_ha_entities":          ("Lade Home Assistant Entitäten",  "Loading Home Assistant entities"),
    "call_ha_service":          ("Steuere Gerät",                 "Controlling device"),
    "get_dns_zones":            ("Lade DNS-Zonen",                "Loading DNS zones"),
    "get_zone_records":         ("Lade DNS-Einträge",             "Loading DNS records"),
    "create_dns_record":        ("Erstelle DNS-Eintrag",          "Creating DNS record"),
    "send_email":               ("Sende E-Mail",                  "Sending email"),
    "fetch_emails":             ("Lade E-Mails",                  "Fetching emails"),
    "send_telegram_message":    ("Sende Telegram-Nachricht",      "Sending Telegram message"),
    "generate_image":           ("Generiere Bild",                "Generating image"),
}


class _StatusEmitter(AsyncCallbackHandler):
    """Emittiert Tool-Start-Events als Status-Updates an den Status-Bus."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:  # type: ignore[override]
        tool_name = serialized.get("name", "")
        pair = _TOOL_LABELS.get(tool_name)
        if pair:
            label = pair[0] if _get_language() == "de" else pair[1]
        else:
            label = tool_name.replace("_", " ").title()
        await status_bus.emit(self.session_id, f"{label}…")

    async def on_llm_start(self, serialized: dict, messages: list, **kwargs) -> None:  # type: ignore[override]
        await status_bus.emit(self.session_id, _t("Denke nach…", "Thinking…"))

# Ab dieser Tool-Anzahl wird JIT Tool Injection aktiviert
_JIT_THRESHOLD = 6
# Max. Tools nach JIT-Filterung (Kontext-Sparsamkeit)
_JIT_MAX_TOOLS = 8

# Strong references to background tasks to prevent premature GC
_background_tasks: set[asyncio.Task] = set()

# Auto-Memorize Cooldown: agent_name → letzter Zeitstempel (monotonic)
_memorize_cooldowns: dict[str, float] = {}
_MEMORIZE_COOLDOWN_SECS = 60.0  # Max 1 Auto-Memorize pro Minute pro Agent
# Agenten die kein Auto-Memorize brauchen (Background-Loops)
_MEMORIZE_EXCLUDED_AGENTS = {"monitor", "scheduler"}

# Sprachanweisungen für Language-Injection am Ende jedes System-Prompts
_LANG_INSTRUCTIONS: dict[str, str] = {
    "de": "Antworte immer auf Deutsch. Verwende passende Emojis in deinen Antworten, um sie lebendiger und übersichtlicher zu gestalten – z. B. am Anfang von Abschnitten, bei Status-Angaben oder zur Hervorhebung wichtiger Punkte.",
    "en": "Always respond in English. Use fitting emojis in your responses to make them more lively and clear – e.g. at the start of sections, for status indicators, or to highlight key points.",
    "fr": "Réponds toujours en français.",
    "es": "Responde siempre en español.",
    "it": "Rispondi sempre in italiano.",
    "nl": "Antwoord altijd in het Nederlands.",
    "pl": "Zawsze odpowiadaj po polsku.",
    "pt": "Responda sempre em português.",
    "ja": "常に日本語で回答してください。",
    "zh": "请始终用中文回答。",
}


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


def _strip_thinking(text: str) -> str:
    """Entfernt <think>...</think> Blöcke aus Thinking-Model-Antworten.

    Qwen3.5, DeepSeek-R1 und ähnliche Modelle generieren interne
    Überlegungen in <think>-Tags, die nicht an den User weitergegeben werden sollen.
    """
    import re
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return stripped.strip()


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

    def _select_tools_for_request(self, message: str) -> list[BaseTool]:
        """
        JIT Tool Injection (OpenClaw-Prinzip):
        Gibt nur die für diese Anfrage relevanten Tools zurück.
        Reduziert Kontext-Overhead bei Agenten mit vielen Tools.
        """
        if len(self.tools) <= _JIT_THRESHOLD:
            return self.tools

        msg_lower = message.lower()
        # Wörter mit mind. 2 Zeichen extrahieren (IT-Fachbegriffe wie IP, VM, K8s, HA, DNS)
        words = [
            w.strip(".,!?:;")
            for w in msg_lower.replace("-", " ").split()
            if len(w.strip(".,!?:;")) >= 2
        ]

        scored: list[tuple[int, BaseTool]] = []
        for t in self.tools:
            searchable = f"{t.name} {t.description or ''}".lower()
            score = sum(1 for w in words if w in searchable)
            scored.append((score, t))

        # Tools mit mindestens 1 Treffer
        relevant = [t for s, t in scored if s > 0]

        # Fallback: zu wenige gefunden → alle Tools zurückgeben
        if len(relevant) < 3:
            return self.tools

        # Sortiert nach Score, max. _JIT_MAX_TOOLS
        top = sorted(scored, key=lambda x: x[0], reverse=True)
        selected = [t for _, t in top[:_JIT_MAX_TOOLS]]
        logger.debug(
            "JIT Tool Injection: Agent '%s' %d → %d Tools.",
            self.name, len(self.tools), len(selected),
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

            info = _t(
                "VERFÜGBARE VERBINDUNGEN FÜR DIESES MODUL:\n",
                "AVAILABLE CONNECTIONS FOR THIS MODULE:\n",
            )
            for c in conns:
                d = " [DEFAULT]" if c.is_default else ""
                info += f"- connection_id: '{c.id}' | Name: '{c.name}' | Env: '{c.environment}'{d}\n"

            info += _t(
                "\nWICHTIG: Nutze IMMER die passende 'connection_id' für Tools! "
                "Wenn der User keine Umgebung nennt, nutze die Default-Verbindung.",
                "\nIMPORTANT: ALWAYS use the appropriate 'connection_id' for tools! "
                "If the user does not specify an environment, use the default connection.",
            )
            return info
        except Exception as e:
            logger.warning("Fehler beim Laden der Connections für Prompt: %s", e)
            return ""

    async def invoke(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
    ) -> tuple[str, bool]:
        """
        Führt den Agenten mit einer Nachricht aus.

        Gibt (antwort, wurde_komprimiert) zurück.
        `wurde_komprimiert` ist True wenn der Kontext in diesem Aufruf
        per LLM-Summary komprimiert wurde — der Aufrufer kann dann eine
        System-Nachricht in die sichtbare Chat-History einfügen.

        1. Context-Window kalibrieren (einmalig, gecacht)
        2. Chat-History auf Token-Budget trimmen / komprimieren
        3. System-Prompt + History + aktuelle Nachricht zusammenbauen
        4. LangGraph Agent ausführen
        5. Antwort + Compaction-Flag zurückgeben
        """
        # Chat-History aufbereiten
        history = chat_history or []

        # LLM neu initialisieren wenn Provider gewechselt wurde
        current_gen = get_llm_generation()
        if current_gen != self._llm_generation:
            self._llm = get_llm()
            self._agent = create_react_agent(model=self._llm, tools=self.tools)
            self._llm_generation = current_gen
            logger.info("Agent '%s': LLM nach Provider-Wechsel neu initialisiert.", self.name)

        # Context-Window einmalig kalibrieren (gecacht nach erstem Aufruf)
        model_window = await get_model_context_window()
        self._context_mgr.update_from_model_window(model_window)

        # Context-Budget prüfen: Komprimierung oder Trimming
        did_compact = False
        if self._context_mgr.should_reset(history):
            await status_bus.emit(session_id, _t("Kontext wird komprimiert…", "Compacting context…"))
            trimmed_history, did_compact = await self._context_mgr.compact_messages_async(
                history, self._llm
            )
        else:
            # Einzelne sehr lange Nachrichten vorher stutzen (opencode Pruning)
            history = self._context_mgr.trim_large_messages(history)
            trimmed_history = self._context_mgr.trim_messages(
                messages=history,
                system_prompt=self.system_prompt,
            )

        # Dynamischen Zusatz für den System Prompt holen
        appendix = await self._dynamic_prompt_appendix()
        final_system_prompt = self.system_prompt
        if appendix:
            final_system_prompt += f"\n\n{appendix}"

        # Soul-Injection: Identität an den Anfang des System-Prompts setzen
        try:
            from core.soul_manager import get_soul_manager
            soul = get_soul_manager().get_soul(self.name)
            if soul:
                final_system_prompt = soul + "\n\n---\n\n" + final_system_prompt
                logger.debug("Soul MD für Agent '%s' injiziert.", self.name)
        except Exception as exc:
            logger.debug("Soul-Injection fehlgeschlagen (ignoriert): %s", exc)

        # Sprachanweisung injizieren
        try:
            from core.config import get_settings as _gs
            lang = _gs().LANGUAGE
            lang_instruction = _LANG_INSTRUCTIONS.get(lang)
            if lang_instruction:
                final_system_prompt += f"\n\n{lang_instruction}"
        except Exception:
            pass  # Fallback: keine Sprachanweisung

        # Komprimierungs-Zusammenfassungen aus der History einsammeln (role="system")
        # und in den System-Prompt integrieren (nicht als separate SystemMessage —
        # Thinking-Modelle wie Qwen3.5 akzeptieren nur EINEN System-Block am Anfang)
        for msg in trimmed_history:
            if msg.get("role") == "system":
                final_system_prompt += "\n\n" + msg.get("content", "")

        # RAG-Kontext in den System-Prompt integrieren
        try:
            memory_hits = await self._memory.search(query=message, top_k=3)
            relevant_hits = [
                hit for hit in memory_hits
                if hit.get("distance") is None or hit["distance"] < 0.5
            ]
            if relevant_hits:
                rag_context = "\n\n".join(
                    f"[Memory] {hit['content']}" for hit in relevant_hits
                )
                final_system_prompt += "\n\n" + _t(
                    "Relevanter Kontext aus dem Memory:\n",
                    "Relevant context from memory:\n",
                ) + rag_context
        except Exception as exc:
            logger.debug("Memory-Suche fehlgeschlagen: %s", exc)

        # Skills-Injection in den System-Prompt integrieren
        try:
            from core.skills_manager import get_skills_manager
            sm = get_skills_manager()
            matching_skills = sm.find_matching_skills(message, self.name)
            if matching_skills:
                skill_text = sm.build_injection(matching_skills)
                final_system_prompt += f"\n\n{skill_text}"
                logger.debug(
                    "Agent '%s': %d Skill(s) injiziert: %s",
                    self.name, len(matching_skills), [s.name for s in matching_skills],
                )
        except Exception as exc:
            logger.debug("Skills-Injection fehlgeschlagen (ignoriert): %s", exc)

        # Nachrichten aufbauen — genau EIN SystemMessage-Block am Anfang
        # (Thinking-Modelle wie Qwen3.5 erlauben nur einen System-Block)
        messages: list[BaseMessage] = [
            SystemMessage(content=final_system_prompt),
        ]

        for msg in trimmed_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            # role="system" → bereits in final_system_prompt integriert
            # role="system_compaction" → UI-Notification, nicht für LLM bestimmt

        messages.append(HumanMessage(content=message))

        # JIT Tool Injection: nur relevante Tools für diese Anfrage laden
        active_tools = self._select_tools_for_request(message)
        if len(active_tools) != len(self.tools):
            # Temporären Agent mit gefiltertem Tool-Set erstellen
            jit_agent = create_react_agent(model=self._llm, tools=active_tools)
        else:
            jit_agent = self._agent

        # Agent ausführen – kein Schrittzähler (wie Roo Code), stattdessen Timeout
        AGENT_TIMEOUT = 1800  # 30 Minuten max pro Anfrage
        run_config: dict = {"recursion_limit": 10000}
        if session_id:
            run_config["callbacks"] = [_StatusEmitter(session_id)]
        try:
            result = await asyncio.wait_for(
                jit_agent.ainvoke(
                    {"messages": messages},
                    config=run_config,
                ),
                timeout=AGENT_TIMEOUT,
            )

            # Letzte AI-Nachricht extrahieren
            all_messages = result.get("messages", [])
            ai_messages = [
                m for m in all_messages
                if isinstance(m, AIMessage) and m.content
            ]

            if ai_messages:
                raw = _extract_text(ai_messages[-1].content)
                response = _strip_thinking(raw)
                # Thinking-Only-Antwort: Modell hat nur <think>-Blöcke generiert, kein Text
                if not response:
                    logger.debug(
                        "Agent '%s': AI-Antwort enthielt nur <think>-Blöcke, suche Tool-Ergebnis.",
                        self.name,
                    )
                    ai_messages = []  # Fallback auf Tool-Messages auslösen
            if not ai_messages:
                # Fallback: letztes Tool-Ergebnis verwenden wenn kein AI-Text vorhanden
                # (passiert wenn LLM nach Tool-Aufruf keinen Text generiert oder nur <think>)
                tool_messages = [
                    m for m in all_messages
                    if isinstance(m, ToolMessage) and m.content
                ]
                if tool_messages:
                    response = _extract_text(tool_messages[-1].content)
                    logger.debug(
                        "Agent '%s': kein AI-Text, nutze letztes Tool-Ergebnis als Antwort.",
                        self.name,
                    )
                else:
                    response = _t("Keine Antwort generiert.", "No response generated.")

            logger.debug(
                "Agent '%s' Antwort: %s…",
                self.name,
                response[:100],
            )

            # Langzeitgedächtnis: relevante Fakten im Hintergrund speichern
            # Triviale Antworten (< 80 Zeichen) überspringen – kein Mehrwert
            # Background-Agenten (monitor, scheduler) ausschließen + Cooldown pro Agent
            _now = asyncio.get_event_loop().time()
            _last = _memorize_cooldowns.get(self.name, 0.0)
            if (
                len(response) >= 80
                and self.name not in _MEMORIZE_EXCLUDED_AGENTS
                and (_now - _last) >= _MEMORIZE_COOLDOWN_SECS
            ):
                _memorize_cooldowns[self.name] = _now
                _task = asyncio.create_task(self._auto_memorize(message, response))
                _background_tasks.add(_task)
                _task.add_done_callback(_background_tasks.discard)

            return response, did_compact

        except asyncio.TimeoutError:
            logger.warning("Agent '%s' Timeout nach %ds.", self.name, AGENT_TIMEOUT)
            return _t(
                "Die Anfrage hat zu lange gedauert und wurde abgebrochen. "
                "Bitte versuche es mit einer spezifischeren Frage erneut.",
                "The request took too long and was aborted. "
                "Please try again with a more specific question.",
            ), False
        except Exception as exc:
            exc_str = str(exc)
            # Spezifische LM Studio / LLM Fehler benutzerfreundlich machen
            if "Model unloaded" in exc_str:
                user_msg = _t(
                    "Fehler: Das KI-Modell ist gerade nicht verfügbar (nicht geladen). "
                    "Bitte prüfe LM Studio und lade das Modell neu.",
                    "Error: The AI model is currently unavailable (not loaded). "
                    "Please check LM Studio and reload the model.",
                )
            else:
                user_msg = _t(
                    f"Fehler: {exc_str}",
                    f"Error: {exc_str}",
                )
            logger.error(
                "Agent '%s' Fehler: %s", self.name, exc, exc_info=True
            )
            return user_msg, False

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
        """
        try:
            prompt = _t(
                "Extrahiere aus diesem Gespräch NUR dauerhaft relevante Fakten "
                "(z.B. Namen des Users, IPs, Präferenzen, Entscheidungen, gelöste Probleme, gelernte Konfigurationen). "
                "Schreibe NUR 1-2 prägnante Sätze – in der Sprache des Users. "
                "Wenn NICHTS dauerhaft Merkenswertes vorhanden ist, schreibe exakt (ohne Sonderzeichen): NICHTS\n\n"
                f"User: {user_msg}\nAssistent: {ai_response[:800]}",
                "Extract ONLY permanently relevant facts from this conversation "
                "(e.g. user names, IPs, preferences, decisions, solved problems, learned configurations). "
                "Write ONLY 1-2 concise sentences — in the user's language. "
                "If NOTHING permanently noteworthy is present, write exactly (no special characters) "
                "one of: NOTHING / NICHTS / RIEN / NADA / NULLA / NIETS / NIC\n\n"
                f"User: {user_msg}\nAssistant: {ai_response[:800]}",
            )
            result = await self._llm.ainvoke([HumanMessage(content=prompt)])
            fact = result.content.strip() if hasattr(result, "content") else str(result).strip()
            _MEMORIZE_STOP_WORDS = {
                "NICHTS", "NOTHING", "RIEN", "NADA", "NULLA", "NIETS", "NIC", "何もない", "没有"
            }
            if fact and fact.strip("*_ \n").upper() not in _MEMORIZE_STOP_WORDS:
                await self._memory.store(
                    content=fact,
                    category="agent_memory",
                    metadata={"agent": self.name, "source": "auto"},
                )
                logger.debug("Auto-Memory gespeichert für Agent '%s': %s…", self.name, fact[:80])
        except Exception as exc:
            logger.debug("Auto-Memorize fehlgeschlagen (ignoriert): %s", exc)
