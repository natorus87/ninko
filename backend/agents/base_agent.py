"""
Ninko BaseAgent – Abstrakte Basis für alle Agenten.
Nutzt LangGraph für Tool-Calling und Conversation-Management.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import re
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from core.safeguard import SafeguardMiddleware

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
    "execute_code": ("Führe Code aus", "Executing code"),
    "get_available_languages": (
        "Prüfe verfügbare Sprachen",
        "Checking available languages",
    ),
    "get_cluster_status": ("Lade Cluster-Status", "Loading cluster status"),
    "get_all_pods": ("Lade Pods", "Loading pods"),
    "get_failing_pods": ("Prüfe fehlerhafte Pods", "Checking failing pods"),
    "list_namespaces": ("Lade Namespaces", "Loading namespaces"),
    "list_services": ("Lade Services", "Loading services"),
    "restart_pod": ("Starte Pod neu", "Restarting pod"),
    "rollout_restart": ("Führe Rollout-Restart durch", "Performing rollout restart"),
    "scale_deployment": ("Skaliere Deployment", "Scaling deployment"),
    "get_recent_events": ("Lade Cluster-Events", "Loading cluster events"),
    "get_pihole_summary": ("Lade Pi-hole Statistiken", "Loading Pi-hole statistics"),
    "get_query_log": ("Lade DNS-Query-Log", "Loading DNS query log"),
    "toggle_blocking": ("Konfiguriere Blocking", "Configuring blocking"),
    "add_domain_to_list": ("Aktualisiere Domain-Liste", "Updating domain list"),
    "remove_domain_from_list": ("Aktualisiere Domain-Liste", "Updating domain list"),
    "update_gravity": ("Aktualisiere Gravity", "Updating gravity"),
    "flush_dns_cache": ("Leere DNS-Cache", "Flushing DNS cache"),
    "perform_web_search": ("Durchsuche das Web", "Searching the web"),
    "web_search": ("Durchsuche das Web", "Searching the web"),
    "execute_cli_command": ("Führe CLI-Befehl aus", "Executing CLI command"),
    "call_module_agent": ("Rufe Modul-Agent auf", "Calling module agent"),
    "run_pipeline": ("Führe Pipeline aus", "Running pipeline"),
    "create_linear_workflow": ("Erstelle Workflow", "Creating workflow"),
    "execute_workflow": ("Führe Workflow aus", "Executing workflow"),
    "remember_fact": ("Speichere im Gedächtnis", "Saving to memory"),
    "recall_memory": ("Durchsuche Gedächtnis", "Searching memory"),
    "forget_fact": ("Suche zu löschende Fakten", "Searching facts to forget"),
    "confirm_forget": ("Lösche Fakten", "Deleting facts"),
    "create_custom_agent": ("Erstelle Agenten", "Creating agent"),
    "install_skill": ("Installiere Skill", "Installing skill"),
    "get_fritzbox_status": ("Lade FritzBox-Status", "Loading FritzBox status"),
    "get_connected_devices": ("Lade verbundene Geräte", "Loading connected devices"),
    "get_call_list": ("Lade Anrufliste", "Loading call list"),
    "get_ha_entities": (
        "Lade Home Assistant Entitäten",
        "Loading Home Assistant entities",
    ),
    "call_ha_service": ("Steuere Gerät", "Controlling device"),
    "get_dns_zones": ("Lade DNS-Zonen", "Loading DNS zones"),
    "get_zone_records": ("Lade DNS-Einträge", "Loading DNS records"),
    "create_dns_record": ("Erstelle DNS-Eintrag", "Creating DNS record"),
    "send_email": ("Sende E-Mail", "Sending email"),
    "fetch_emails": ("Lade E-Mails", "Fetching emails"),
    "send_telegram_message": ("Sende Telegram-Nachricht", "Sending Telegram message"),
    "generate_image": ("Generiere Bild", "Generating image"),
    "checkmk_get_hosts": ("Lade Hosts", "Loading hosts"),
    "checkmk_get_services": ("Lade Services", "Loading services"),
    "checkmk_get_host_status": ("Prüfe Host-Status", "Checking host status"),
    "checkmk_get_service_status": ("Prüfe Service-Status", "Checking service status"),
    "checkmk_get_alerts": ("Lade Alarme", "Loading alerts"),
    "checkmk_get_host_details": ("Lade Host-Details", "Loading host details"),
    "checkmk_get_service_details": ("Lade Service-Details", "Loading service details"),
    "checkmk_search_hosts": ("Suche Hosts", "Searching hosts"),
    "checkmk_search_services": ("Suche Services", "Searching services"),
    # Synology
    "get_synology_system_info": ("Lade System-Info", "Loading system info"),
    "get_synology_storage": ("Lade Storage", "Loading storage"),
    "get_synology_packages": ("Lade Pakete", "Loading packages"),
    "get_synology_services": ("Lade Services", "Loading services"),
    "get_synology_tasks": ("Lade Tasks", "Loading tasks"),
    "restart_synology_service": ("Starte Service neu", "Restarting service"),
    "check_synology_updates": ("Prüfe Updates", "Checking updates"),
    "install_synology_update": ("Installiere Update", "Installing update"),
    "install_synology_package": ("Installiere Paket", "Installing package"),
    "uninstall_synology_package": ("Deinstalliere Paket", "Uninstalling package"),
    "get_synology_network_info": ("Lade Netzwerk-Info", "Loading network info"),
    "get_synology_users": ("Lade Benutzer", "Loading users"),
    "get_synology_groups": ("Lade Gruppen", "Loading groups"),
    "create_synology_user": ("Erstelle Benutzer", "Creating user"),
    "delete_synology_user": ("Lösche Benutzer", "Deleting user"),
    "change_synology_user_password": ("Ändere Passwort", "Changing password"),
    "create_synology_group": ("Erstelle Gruppe", "Creating group"),
    "add_user_to_group": ("Füge User zu Gruppe hinzu", "Adding user to group"),
    "remove_user_from_group": ("Entferne User von Gruppe", "Removing user from group"),
    "shutdown_synologyNAS": ("Fahre NAS herunter", "Shutting down NAS"),
    "reboot_synologyNAS": ("Boote NAS neu", "Rebooting NAS"),
    # HPE iLO
    "get_ilo_info": ("Lade iLO-Info", "Loading iLO info"),
    "get_server_info": ("Lade Server-Info", "Loading server info"),
    "get_server_thermal": ("Lade Thermal", "Loading thermal"),
    "get_server_power": ("Lade Power", "Loading power"),
    "get_ilo_nics": ("Lade Netzwerk", "Loading network"),
    "get_ilo_eventlog": ("Lade Events", "Loading events"),
    "server_power_on": ("Schalte Server ein", "Powering on server"),
    "server_power_off": ("Schalte Server aus", "Powering off server"),
    "server_reset_ilo": ("Reset iLO", "Resetting iLO"),
    "server_press_boot_button": ("Boot-Button", "Pressing boot button"),
    # Microsoft Entra
    "list_entra_users": ("Lade Benutzer", "Loading users"),
    "search_entra_user": ("Suche Benutzer", "Searching user"),
    "get_user_details": ("Lade Benutzerdetails", "Loading user details"),
    "list_entra_groups": ("Lade Gruppen", "Loading groups"),
    "get_group_members": ("Lade Gruppenmitglieder", "Loading group members"),
    "list_entra_applications": ("Lade Anwendungen", "Loading applications"),
    "list_entra_devices": ("Lade Geräte", "Loading devices"),
    "create_entra_user": ("Erstelle Benutzer", "Creating user"),
    "disable_entra_user": ("Deaktiviere Benutzer", "Disabling user"),
    "reset_entra_user_password": ("Setze Passwort zurück", "Resetting password"),
    "create_entra_group": ("Erstelle Gruppe", "Creating group"),
    "add_user_to_group": ("Füge User zu Gruppe", "Adding user to group"),
    # Microsoft Intune
    "list_intune_devices": ("Lade Geräte", "Loading devices"),
    "get_intune_device": ("Lade Gerätedetails", "Loading device details"),
    "list_intune_policies": ("Lade Richtlinien", "Loading policies"),
    "list_intune_compliance_policies": ("Lade Compliance", "Loading compliance"),
    "list_intune_apps": ("Lade Apps", "Loading apps"),
    "get_intune_device_compliance": ("Prüfe Compliance", "Checking compliance"),
    "wipe_intune_device": ("Wipe Gerät", "Wiping device"),
    "retire_intune_device": (" Retire Gerät", "Retiring device"),
    "sync_intune_device": ("Sync Gerät", "Syncing device"),
    "locate_intune_device": (" Lokalisiere Gerät", "Locating device"),
    # Redmine
    "get_redmine_projects": ("Lade Projekte", "Loading projects"),
    "get_redmine_project": ("Lade Projekt", "Loading project"),
    "get_redmine_issues": ("Lade Tickets", "Loading issues"),
    "get_redmine_issue": ("Lade Ticket", "Loading issue"),
    "create_redmine_issue": ("Erstelle Ticket", "Creating issue"),
    "update_redmine_issue": ("Aktualisiere Ticket", "Updating issue"),
    "get_redmine_users": ("Lade Benutzer", "Loading users"),
    "get_redmine_time_entries": ("Lade Zeiten", "Loading time entries"),
    "log_redmine_time": ("Logge Zeit", "Logging time"),
    "get_redmine_issue_statuses": ("Lade Status", "Loading statuses"),
    "get_redmine_priorities": ("Lade Prioritäten", "Loading priorities"),
    "search_redmine_issues": ("Suche Tickets", "Searching issues"),
    "get_redmine_issue_counts": ("Zähle Tickets", "Counting issues"),
    # GLPI
    "create_ticket": ("Erstelle Ticket", "Creating ticket"),
    "get_ticket": ("Lade Ticket", "Loading ticket"),
    "search_tickets": ("Suche Tickets", "Searching tickets"),
    "update_ticket": ("Aktualisiere Ticket", "Updating ticket"),
    "close_ticket": ("Schließe Ticket", "Closing ticket"),
    "add_followup": ("Füge Follow-up hinzu", "Adding follow-up"),
    "add_solution": ("Füge Lösung hinzu", "Adding solution"),
    "search_users": ("Suche Benutzer", "Searching users"),
    "list_groups": ("Lade Gruppen", "Loading groups"),
    "list_categories": ("Lade Kategorien", "Loading categories"),
    "get_ticket_stats": ("Lade Statistik", "Loading stats"),
    "get_ticket_attachments": ("Lade Anhänge", "Loading attachments"),
    "get_ticket_followups": ("Lade Antworten", "Loading replies"),
    "get_ticket_solutions": ("Lade Lösungen", "Loading solutions"),
    # Confluence
    "get_confluence_spaces": ("Lade Spaces", "Loading spaces"),
    "get_confluence_space": ("Lade Space", "Loading space"),
    "get_confluence_pages": ("Lade Seiten", "Loading pages"),
    "get_confluence_page": ("Lade Seite", "Loading page"),
    "create_confluence_page": ("Erstelle Seite", "Creating page"),
    "update_confluence_page": ("Aktualisiere Seite", "Updating page"),
    "get_confluence_blog_posts": ("Lade Blog-Posts", "Loading blog posts"),
    "create_confluence_blog_post": ("Erstelle Blog-Post", "Creating blog post"),
    "search_confluence": ("Suche Confluence", "Searching Confluence"),
    "get_confluence_labels": ("Lade Labels", "Loading labels"),
    "get_confluence_page_history": ("Lade Historie", "Loading history"),
    # Jira
    "get_jira_projects": ("Lade Projekte", "Loading projects"),
    "get_jira_project": ("Lade Projekt", "Loading project"),
    "get_jira_issues": ("Lade Issues", "Loading issues"),
    "get_jira_issue": ("Lade Issue", "Loading issue"),
    "create_jira_issue": ("Erstelle Issue", "Creating issue"),
    "update_jira_issue": ("Aktualisiere Issue", "Updating issue"),
    "get_jira_boards": ("Lade Boards", "Loading boards"),
    "get_jira_sprints": ("Lade Sprints", "Loading sprints"),
    "get_jira_sprint": ("Lade Sprint", "Loading sprint"),
    "search_jira": ("Suche Jira", "Searching Jira"),
    "get_jira_issue_transitions": ("Lade Transitions", "Loading transitions"),
    "transition_jira_issue": ("Transitioniere Issue", "Transitioning issue"),
    "get_jira_priorities": ("Lade Prioritäten", "Loading priorities"),
    "get_jira_issue_counts": ("Zähle Issues", "Counting issues"),
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

# Auto-Memorize Cooldown: (agent_name, session_id) → letzter Zeitstempel (monotonic)
_memorize_cooldowns: dict[tuple[str, str], float] = {}
_MEMORIZE_COOLDOWN_SECS = 60.0  # Max 1 Auto-Memorize pro Minute pro Agent
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
_TOOL_SAFEGUARD_SENTINEL = "__TOOL_SAFEGUARD__"

# Paused safeguard agents: session_id → (sg_agent, thread_config)
# Hält den unterbrochenen LangGraph-Agenten für den Resume-Aufruf am Leben.
_paused_sg_agents: dict[str, tuple] = {}
# Session-spezifische Locks verhindern parallele Safeguard-Runs/Resumes
_safeguard_session_locks: dict[str, asyncio.Lock] = {}

_global_safeguard: "SafeguardMiddleware | None" = None


def set_global_safeguard(sg: "SafeguardMiddleware") -> None:
    """Setzt die globale Safeguard-Instanz (wird von main.py aufgerufen)."""
    global _global_safeguard
    _global_safeguard = sg
    logger.info("Globale Safeguard-Instanz registriert.")


def _get_safeguard_session_lock(session_id: str) -> asyncio.Lock:
    """Gibt den Lock für eine Session zurück (lazy init)."""
    if session_id not in _safeguard_session_locks:
        _safeguard_session_locks[session_id] = asyncio.Lock()
    return _safeguard_session_locks[session_id]


def _get_agent_timeout_seconds() -> int:
    """Lädt den Agent-Timeout aus der Config mit robustem Fallback."""
    try:
        from core.config import get_settings

        timeout = int(get_settings().AGENT_TIMEOUT_SECONDS)
        return timeout if timeout > 0 else 1800
    except Exception:
        return 1800


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
        confirmed: bool = False,
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
            logger.info(
                "Agent '%s': LLM nach Provider-Wechsel neu initialisiert.", self.name
            )

        # Context-Window einmalig kalibrieren (gecacht nach erstem Aufruf)
        model_window = await get_model_context_window()
        self._context_mgr.update_from_model_window(model_window)

        # Context-Budget prüfen: Komprimierung oder Trimming
        did_compact = False
        if self._context_mgr.should_reset(history):
            await status_bus.emit(
                session_id, _t("Kontext wird komprimiert…", "Compacting context…")
            )
            (
                trimmed_history,
                did_compact,
            ) = await self._context_mgr.compact_messages_async(history, self._llm)
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

        # Aktuelles Datum + Uhrzeit injizieren (Timezone aus Config)
        try:
            from datetime import datetime
            import zoneinfo
            from core.config import get_settings as _gs2

            tz_name = _gs2().TIMEZONE
            tz = zoneinfo.ZoneInfo(tz_name)
            now = datetime.now(tz)
            weekdays_de = [
                "Montag",
                "Dienstag",
                "Mittwoch",
                "Donnerstag",
                "Freitag",
                "Samstag",
                "Sonntag",
            ]
            weekdays_en = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            lang = _gs().LANGUAGE if "lang" in dir() else "de"
            if lang == "de":
                dt_str = (
                    f"Aktuelles Datum: {weekdays_de[now.weekday()]}, "
                    f"{now.day:02d}.{now.month:02d}.{now.year} | "
                    f"Uhrzeit: {now.strftime('%H:%M')} ({tz_name})"
                )
            else:
                dt_str = (
                    f"Current date: {weekdays_en[now.weekday()]}, "
                    f"{now.strftime('%B %d, %Y')} | "
                    f"Time: {now.strftime('%H:%M')} ({tz_name})"
                )
            final_system_prompt += f"\n\n{dt_str}"
        except Exception as exc:
            logger.debug("Datetime-Injection fehlgeschlagen (ignoriert): %s", exc)

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
                hit
                for hit in memory_hits
                if hit.get("distance") is None or hit["distance"] < 0.5
            ]
            if relevant_hits:
                rag_context = "\n\n".join(
                    f"[Memory] {hit['content']}" for hit in relevant_hits
                )
                final_system_prompt += (
                    "\n\n"
                    + _t(
                        "Relevanter Kontext aus dem Memory:\n",
                        "Relevant context from memory:\n",
                    )
                    + rag_context
                )
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
                    self.name,
                    len(matching_skills),
                    [s.name for s in matching_skills],
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
        AGENT_TIMEOUT = _get_agent_timeout_seconds()
        run_config: dict = {"recursion_limit": 10000}
        if session_id:
            run_config["callbacks"] = [_StatusEmitter(session_id)]
        try:
            # Safeguard-Pfad: interrupt_before=["tools"] + MemorySaver wenn aktiv
            # .enabled wird durch das aktive Profil gesteuert (disabled-Profil → False)
            use_safeguard = (
                _global_safeguard is not None
                and _global_safeguard.enabled
                and not confirmed
                and bool(session_id)
                and bool(active_tools)
            )

            if use_safeguard:
                # Wenn bereits ein pausierter Tool-Call in dieser Session wartet, nicht überschreiben.
                if session_id in _paused_sg_agents:
                    return _t(
                        "Für diese Session gibt es bereits eine ausstehende Tool-Bestätigung. "
                        "Bestätige zuerst den offenen Schritt (confirmed=true).",
                        "There is already a pending tool confirmation for this session. "
                        "Confirm the open step first (confirmed=true).",
                    ), did_compact

                async with _get_safeguard_session_lock(session_id):
                    raw_result = await self._run_with_safeguard(
                        messages, active_tools, run_config, session_id
                    )
                # Sentinel-String → Tool-Call braucht Bestätigung
                if isinstance(raw_result, str):
                    return raw_result, did_compact
                result = raw_result
            else:
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
                m for m in all_messages if isinstance(m, AIMessage) and m.content
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
                    m for m in all_messages if isinstance(m, ToolMessage) and m.content
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
            _now = asyncio.get_running_loop().time()
            _cooldown_key = (self.name, session_id or "__no_session__")
            _last = _memorize_cooldowns.get(_cooldown_key, 0.0)
            if (
                len(response) >= 80
                and self.name not in _MEMORIZE_EXCLUDED_AGENTS
                and (_now - _last) >= _MEMORIZE_COOLDOWN_SECS
            ):
                _memorize_cooldowns[_cooldown_key] = _now
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
                logger.warning(
                    "Agent '%s' Fehler wird gegenüber User sanitisiert. raw_error=%s",
                    self.name,
                    exc_str[:300],
                )
                user_msg = _t(
                    "Fehler: Bei der Verarbeitung ist ein interner Fehler aufgetreten. "
                    "Bitte versuche es erneut oder präzisiere die Anfrage.",
                    "Error: An internal processing error occurred. "
                    "Please retry or make the request more specific.",
                )
            logger.error("Agent '%s' Fehler: %s", self.name, exc, exc_info=True)
            return user_msg, False

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
    ) -> "dict | str":
        """
        Kern-Schleife für den Safeguard-Interrupt-Mechanismus.

        Führt den Agenten aus und pausiert vor jedem Tool-Call. Gibt das
        LangGraph-Ergebnis-Dict zurück wenn die Ausführung abgeschlossen ist,
        oder einen Sentinel-String wenn ein Tool-Call Bestätigung benötigt.
        """
        AGENT_TIMEOUT = _get_agent_timeout_seconds()

        while True:
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
                if _global_safeguard is None or not _global_safeguard.enabled:
                    logger.warning(
                        "[Safeguard] Instanz während Lauf verloren/deaktiviert "
                        "(Agent: %s, Session: %s) – setze Ausführung ohne erneuten Check fort.",
                        self.name,
                        session_id,
                    )
                    dangerous_call = None
                    break

                sg_result = await _global_safeguard.check_tool_call(
                    tool_name,
                    tool_args,
                    agent_id=self.name,
                    session_id=session_id,
                )
                if sg_result.requires_confirmation:
                    dangerous_call = (tool_name, tool_args, sg_result)
                    break  # Ersten gefährlichen Call als Confirmation-Request nehmen

            if dangerous_call is None:
                # Alle Tools sind SAFE → sofort resumieren (transparent)
                continue

            tool_name, tool_args, sg_result = dangerous_call

            # Pausiert: Zustand im Modul-Dict speichern + in Redis vermerken
            _paused_sg_agents[session_id] = (sg_agent, thread_config)
            from core.redis_client import get_redis

            redis = get_redis()
            await redis.connection.setex(
                f"ninko:safeguard_tool_pending:{session_id}",
                300,
                _json.dumps(
                    {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "agent": self.name,
                        "category": sg_result.category.value,
                        "rationale": sg_result.rationale,
                    }
                ),
            )

            logger.info(
                "[Safeguard] Tool-Call '%s' pausiert (Agent: '%s', Session: '%s').",
                tool_name,
                self.name,
                session_id,
            )
            return f"{_TOOL_SAFEGUARD_SENTINEL}" + _json.dumps(
                {
                    "tool_name": tool_name,
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
            sg_agent, thread_config, {"messages": messages}, session_id
        )

    async def resume_safeguard_tool(self, session_id: str) -> tuple[str, bool]:
        """
        Setzt die Ausführung nach Safeguard-Bestätigung durch den User fort.
        Holt den pausierten Agenten aus _paused_sg_agents und resumiert den Graph.
        """
        if session_id not in _paused_sg_agents:
            logger.warning(
                "[Safeguard] Resume angefragt, aber kein pausierter Agent für Session '%s'.",
                session_id,
            )
            return _t(
                "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                "Error: No pending tool call for this session.",
            ), False

        async with _get_safeguard_session_lock(session_id):
            # Nicht poppen bevor Resume erfolgreich ist — sonst State-Verlust bei Fehlern.
            paused = _paused_sg_agents.get(session_id)
            if paused is None:
                return _t(
                    "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                    "Error: No pending tool call for this session.",
                ), False
            sg_agent, thread_config = paused
            try:
                result = await self._sg_loop(sg_agent, thread_config, None, session_id)
            except asyncio.TimeoutError:
                logger.warning(
                    "Agent '%s' Timeout beim Resume (Session: %s).",
                    self.name,
                    session_id,
                )
                return _t(
                    "Die Ausführung hat zu lange gedauert und wurde abgebrochen.",
                    "Execution timed out and was aborted.",
                ), False
            except Exception as exc:
                logger.error(
                    "Agent '%s' Fehler beim Resume: %s", self.name, exc, exc_info=True
                )
                return _t(
                    "Fehler: Resume fehlgeschlagen. Bitte erneut bestätigen oder Anfrage wiederholen.",
                    "Error: Resume failed. Please confirm again or retry the request.",
                ), False

            # Weiterer Sentinel? (nächster gefährlicher Tool-Call)
            if isinstance(result, str):
                return result, False

            # Erfolg: pausierten Zustand + Pending-Key aufräumen
            _paused_sg_agents.pop(session_id, None)
            try:
                from core.redis_client import get_redis

                redis = get_redis()
                await redis.connection.delete(
                    f"ninko:safeguard_tool_pending:{session_id}"
                )
            except Exception as exc:
                logger.debug(
                    "[Safeguard] Pending-Key Cleanup fehlgeschlagen (Session: %s): %s",
                    session_id,
                    exc,
                )
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
            fact = (
                result.content.strip()
                if hasattr(result, "content")
                else str(result).strip()
            )
            if fact and fact.strip("*_ \n").upper() not in _MEMORIZE_STOP_WORDS:
                await self._memory.store(
                    content=fact,
                    category="agent_memory",
                    metadata={"agent": self.name, "source": "auto"},
                )
                logger.debug(
                    "Auto-Memory gespeichert für Agent '%s': %s…", self.name, fact[:80]
                )
        except Exception as exc:
            logger.debug("Auto-Memorize fehlgeschlagen (ignoriert): %s", exc)
