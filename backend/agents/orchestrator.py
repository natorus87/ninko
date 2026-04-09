"""
Ninko Orchestrator Agent – 4-stufige Routing-Logik via ModuleRegistry.

Stufe 1 – Direkte Ausführung:  Einfache Fragen direkt beantworten.
Stufe 2 – Modul-Delegation:    Spezialisierte Modul-Agenten einsetzen.
Stufe 3 – Dynamischer Agent:   Neuen spezialisierten Agenten erstellen und wiederverwenden.
Stufe 4 – Workflow-Orchestrierung: Mehrstufige Aufgaben als deterministischen Plan ausführen.

Kennt KEINE Modul-Namen hardcodiert, arbeitet ausschließlich mit der Registry.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import re
import time
from dataclasses import dataclass, fields as _dc_fields
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from agents.base_agent import BaseAgent, _t
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
    configure_routing,
    get_routing_info,
    wait,
)
from agents.alert_tools import (
    check_alert_state,
    record_alert,
    resolve_alert,
)
from agents.data_analysis_subagent import (
    DataAnalysisSubagent,
    _get_or_create_subagent,
    _cleanup_subagent,
)
from modules.image_gen.tools import generate_image
from core import status_bus

if TYPE_CHECKING:
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.orchestrator")

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

# ── Tier-4 Konstanten ─────────────────────────────────────────────────────────

# Utility-Module zählen für Compound-Scoring nur wenn explizit erwähnt
_UTILITY_MODULES: frozenset[str] = frozenset(
    {
        "web_search",
        "image_gen",
        "telegram",
        "email",
        "teams",
    }
)

# Sequentielle Verknüpfungs-Muster (word-boundary-gesichert)
_MULTISTEP_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bund\s+dann\b",
        r"\bund\s+danach\b",
        r"\bdanach\b",
        r"\banschlie[ßs]end\b",
        r"\bals\s+n[äa]chstes\b",
        r"\bzuerst\b.{1,80}\bdann\b",
        r"\berst\b.{1,80}\bdann\b",
        r"\bnachdem\b",
        r"\bwenn\s+fertig\b",
        r"\bim\s+anschluss\b",
        r"\bthen\b",
        r"\bafter\s+that\b",
        r"\bfollowed\s+by\b",
        r"\bwhen\s+done\b",
    ]
]

# Timeout für den Pipeline-Planner-LLM-Call
_LLM_ROUTING_TIMEOUT: float = 10.0
_COMPLEXITY_CHECK_TIMEOUT: float = 2.0

# ── Routing-Konfiguration ─────────────────────────────────────────────────────


@dataclass
class RoutingConfig:
    """Routing-Konfiguration des Orchestrators (session-scoped).

    Zwei Pfade:
    - Tier 2 (keyword fast-path): Einzelnes Modul eindeutig erkannt → direkt delegieren.
    - Tier 1 (invoke): Alles andere → Orchestrator-ReAct-Loop entscheidet selbst
      via call_module_agent / run_pipeline / create_custom_agent / direkte Antwort.
    """

    tier1_enabled: bool = True  # ReAct-Loop für alles ohne eindeutigen Keyword-Match
    tier2_enabled: bool = True  # Keyword-Fast-Path direkt zum Modul-Agent
    tier4_enabled: bool = True  # Multi-Modul-Pipeline-Planner
    preset: str = "default"

    @classmethod
    def from_dict(cls, d: dict) -> "RoutingConfig":
        known = {f.name for f in _dc_fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in _dc_fields(self)}


ROUTING_PRESETS: dict[str, dict] = {
    "default": {},
    # fast: kein Pipeline-Overhead, direkte Antworten priorisiert
    "fast": {"preset": "fast", "tier4_enabled": False},
    # module-only: Tier 1 (direkte Antwort) und Tier 4 (Pipeline) deaktiviert
    "module-only": {
        "preset": "module-only",
        "tier1_enabled": False,
        "tier4_enabled": False,
    },
}

# ── Session-scoped Routing State ──────────────────────────────────────────────
# Routing-Configs gelten nur für die aktuelle Session — nach Session-Ende zurück zu Defaults.
# session_id → (RoutingConfig, last_updated_monotonic)
_session_routing_configs: dict[str, tuple[RoutingConfig, float]] = {}
# session_id → {"tiers": [2,2,1,2], "modules": ["k8s","k8s",None,"k8s"]}
_session_stats: dict[str, dict] = {}
_SESSION_ROUTING_TTL = 86400.0  # 24h, matching Redis chat-history TTL

# Speed signals that trigger auto-fast preset for a session (DE + EN)
_SPEED_SIGNALS = frozenset(
    {
        "schnell",
        "schnelle",
        "schneller",
        "schnelles",
        "quick",
        "fast",
        "kurz",
        "kurze",
        "kurzer",
        "kurzes",
        "brief",
        "knapp",
        "simplified",
        "einfach",
        "kürzer",
        "kürze",
    }
)

# Explizite Agent-Erstellungs-Intention (DE + EN)
_AGENT_CREATE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\berstell(?:e|en|t)?\b.{0,40}\bagent(?:en)?\b", re.IGNORECASE),
    re.compile(
        r"\bleg(?:e|en|t)?\b.{0,40}\bagent(?:en)?\b.{0,20}\ban\b", re.IGNORECASE
    ),
    re.compile(r"\bbau(?:e|en|t)?\b.{0,40}\bagent(?:en)?\b", re.IGNORECASE),
    re.compile(r"\bcreate\b.{0,40}\bagent\b", re.IGNORECASE),
    re.compile(r"\bbuild\b.{0,40}\bagent\b", re.IGNORECASE),
    re.compile(r"\bmake\b.{0,40}\bagent\b", re.IGNORECASE),
)

# How-to / Anleitung statt Ausführung
_AGENT_HOWTO_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(
        r"\bwie\b.{0,30}\b(agent|agenten)\b.{0,20}\b(erstell|anleg|bau)\w*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\b.{0,20}\b(to\b.{0,10})?(create|build|make)\b.{0,30}\bagent\b",
        re.IGNORECASE,
    ),
    re.compile(r"\banleitung\b.{0,40}\bagent\b", re.IGNORECASE),
)

# Explizite Workflow-Erstellungs-Intention (DE + EN)
_WORKFLOW_CREATE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\berstell(?:e|en|t)?\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bleg(?:e|en|t)?\b.{0,40}\bworkflow\b.{0,20}\ban\b", re.IGNORECASE),
    re.compile(r"\bbau(?:e|en|t)?\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bcreate\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bbuild\b.{0,40}\bworkflow\b", re.IGNORECASE),
    re.compile(
        r"\bautomatisier\w*\b.{0,40}\b(ablauf|prozess|workflow)\b", re.IGNORECASE
    ),
)

# How-to / Anleitung statt Ausführung
_WORKFLOW_HOWTO_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(
        r"\bwie\b.{0,30}\bworkflow\b.{0,20}\b(erstell|anleg|bau)\w*", re.IGNORECASE
    ),
    re.compile(
        r"\bhow\b.{0,20}\b(to\b.{0,10})?(create|build|make)\b.{0,30}\bworkflow\b",
        re.IGNORECASE,
    ),
    re.compile(r"\banleitung\b.{0,40}\bworkflow\b", re.IGNORECASE),
)


def get_session_routing_config(session_id: str) -> RoutingConfig | None:
    """Gibt die session-scoped Routing-Config zurück, falls vorhanden und nicht abgelaufen."""
    if not session_id or session_id not in _session_routing_configs:
        return None
    cfg, ts = _session_routing_configs[session_id]
    if time.monotonic() - ts > _SESSION_ROUTING_TTL:
        _session_routing_configs.pop(session_id, None)
        return None
    return cfg


def set_session_routing_config(session_id: str, cfg: RoutingConfig) -> None:
    """Setzt die session-scoped Routing-Config (überschreibt Defaults für diese Session)."""
    if session_id:
        _session_routing_configs[session_id] = (cfg, time.monotonic())


def clear_session_routing_config(session_id: str) -> None:
    """Löscht die session-scoped Routing-Config → nächste Anfrage nutzt wieder Defaults."""
    _session_routing_configs.pop(session_id, None)


SYSTEM_PROMPT = """Du bist Ninko – ein intelligenter IT-Operations-Assistent.

Du bist der zentrale Ansprechpartner. Du entscheidest selbst, wie du eine Anfrage bearbeitest:

ENTSCHEIDUNGS-LOGIK:
1. Ist die Anfrage eindeutig einem Modul zugeordnet (Kubernetes, Pi-hole, HomeAssistant etc.)?
   → `call_module_agent("<modul>", "<vollständige Aufgabe>")` aufrufen.
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
        super().__init__(
            name="orchestrator",
            system_prompt=SYSTEM_PROMPT,
            tools=[
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
                configure_routing,
                get_routing_info,
                wait,
            ],
        )
        self.registry = registry
        self._routing_map: dict[str, str] = {}
        self._routing_dirty = True
        self._refresh_routing_map()
        # ── Self-adaptive routing config ──
        self._routing_config: RoutingConfig = RoutingConfig()
        self._routing_config_loaded_at: float = 0.0
        self._last_tier_used: int = 0

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
            logger.warning(
                "Konnte globale Connections für Orchestrator nicht laden: %s", e
            )

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

        return "\n\n".join(parts)

    async def _load_routing_config(self, session_id: str = "") -> RoutingConfig:
        """Gibt die Routing-Config für die Session zurück.

        Priorität: session-scoped config > RoutingConfig() Defaults.
        Session-Config wird durch configure_routing-Tool oder proaktive Heuristiken gesetzt.
        """
        session_cfg = get_session_routing_config(session_id)
        if session_cfg is not None:
            return session_cfg
        return RoutingConfig()

    def _invalidate_routing_cache(self) -> None:
        """Kein-Op – bleibt für Kompatibilität mit configure_routing-Tool."""
        pass

    def _proactive_routing_adjust(
        self,
        session_id: str,
        message: str,
        chat_history: list[dict] | None,
        cfg: RoutingConfig,
    ) -> RoutingConfig:
        """Proaktive Heuristiken: passt die Session-Routing-Config ohne expliziten User-Befehl an.

        Läuft synchron und ohne LLM-Call — nur Pattern-Matching und Session-Stats.
        """
        msg_lower = message.lower()
        stats = _session_stats.get(session_id, {"tiers": [], "modules": []})
        words = set(re.sub(r"[^\w\s]", " ", msg_lower).split())

        # ── Heuristik 1: Speed-Signale → Fast-Preset für diese Session ──────
        if cfg.preset != "fast" and words & _SPEED_SIGNALS:
            new_cfg = RoutingConfig.from_dict(
                {**RoutingConfig().to_dict(), "preset": "fast"}
            )
            set_session_routing_config(session_id, new_cfg)
            logger.info(
                "Proaktives Routing: Speed-Signal erkannt → Fast-Preset für Session '%s'",
                session_id,
            )
            return new_cfg

        # ── Heuristik 2: Reset-Signale → zurück zu Defaults ─────────────────
        _RESET_SIGNALS = {
            "default",
            "normal",
            "reset",
            "zurück",
            "standard",
            "alles",
            "wieder",
        }
        if words & _RESET_SIGNALS and cfg.preset != "default":
            clear_session_routing_config(session_id)
            logger.info(
                "Proaktives Routing: Reset-Signal erkannt → Defaults für Session '%s'",
                session_id,
            )
            return RoutingConfig()

        # ── Heuristik 3: Modul-Fokus → Tier 2 dominiert, kein Bedarf für ReAct-Loop ─
        # Informativer Log — im neuen Modell gibt es kein llm_routing_enabled mehr,
        # aber wir tracken den Fokus weiterhin für zukünftige Optimierungen.
        recent_tiers = stats.get("tiers", [])[-6:]
        recent_modules = [m for m in stats.get("modules", [])[-6:] if m]
        if (
            len(recent_tiers) >= 5
            and all(t == 2 for t in recent_tiers)
            and len(set(recent_modules)) == 1
            and not cfg.preset.startswith("focus:")
        ):
            dominant = recent_modules[0]
            new_cfg = RoutingConfig.from_dict(
                {**cfg.to_dict(), "preset": f"focus:{dominant}"}
            )
            set_session_routing_config(session_id, new_cfg)
            logger.info(
                "Proaktives Routing: Modul-Fokus '%s' erkannt (Session '%s')",
                dominant,
                session_id,
            )
            return new_cfg

        return cfg

    def _update_session_stats(
        self, session_id: str, tier: int, module: str | None
    ) -> None:
        """Trackt Tier-Nutzung und Modul-Verteilung pro Session für proaktive Heuristiken."""
        if not session_id:
            return
        stats = _session_stats.setdefault(session_id, {"tiers": [], "modules": []})
        stats["tiers"].append(tier)
        stats["modules"].append(module)
        # Nur die letzten 20 Einträge behalten
        if len(stats["tiers"]) > 20:
            stats["tiers"] = stats["tiers"][-20:]
            stats["modules"] = stats["modules"][-20:]

    def _refresh_routing_map(self) -> None:
        """Routing-Map aus der Registry aktualisieren (nur wenn dirty)."""
        if not self._routing_dirty:
            return
        self._routing_map = self.registry.get_routing_map()
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

    async def _check_task_complexity(self, message: str, module: str) -> dict | None:
        from core.llm_factory import get_llm
        from langchain_core.messages import HumanMessage

        prompt = f"""Analysiere diese Aufgabe für Modul "{module}":

User-Query: {message}

Wird diese Aufgabe wahrscheinlich viele Datensätze zurückliefern
(> 20 Ergebnisse, komplexe Filterung, Aggregation)?

Indikatoren für JA (is_complex: true):
- "alle/list all/show all" → viele Ergebnisse erwartet
- "gruppiert nach/group by" → Aggregation über große Menge
- "vergleiche/compare" → muss viele Daten durchgehen
- Keine explizite Limitierung ("die letzten 5")
- "Überblick/overview" über viele Ressourcen
- "Statistik/statistics" über große Mengen
- "älter als/older than" kombiniert mit "alle/all"

Indikatoren für NEIN (is_complex: false):
- "Ticket #123" → einzelne Ressource
- "erstelle/create" → Schreiboperation, keine Datenabfrage
- Explizites Limit ("zeige 3", "letzte 5")
- "Status von/status of" einzelner Ressource
- "Details" zu spezifischer Ressource

Antworte NUR mit JSON:
{{
  "is_complex": true/false,
  "sub_tasks": ["task1", "task2"],
  "suggested_subagent_count": 1-2,
  "reasoning": "kurze Begründung"
}}"""

        try:
            llm = get_llm()
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=_COMPLEXITY_CHECK_TIMEOUT,
            )
            raw = response.content if hasattr(response, "content") else str(response)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                logger.debug("Complexity-Check: Kein JSON gefunden, Fallback zu Tier 2")
                return None

            result = _json.loads(m.group(0))

            is_complex = bool(result.get("is_complex", False))
            sub_tasks = (
                result.get("sub_tasks", [])
                if isinstance(result.get("sub_tasks"), list)
                else []
            )
            suggested_count = max(
                1, min(2, int(result.get("suggested_subagent_count", 1)))
            )
            reasoning = str(result.get("reasoning", ""))[:200]

            logger.info(
                "Complexity-Check für '%s': is_complex=%s, reasoning='%s'",
                module,
                is_complex,
                reasoning,
            )

            return {
                "is_complex": is_complex,
                "sub_tasks": sub_tasks,
                "suggested_subagent_count": suggested_count,
                "reasoning": reasoning,
            }

        except asyncio.TimeoutError:
            logger.debug("Complexity-Check Timeout → Fallback zu Tier 2")
            return None
        except Exception as e:
            logger.warning("Complexity-Check Fehler: %s → Fallback zu Tier 2", e)
            return None

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

    async def _auto_create_custom_agent(
        self, message: str, session_id: str
    ) -> tuple[str, bool]:
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
            ", ".join(module_names)
            if module_names
            else "kubernetes, linux_server, docker"
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
            logger.warning(
                "Auto-Create-Agent: Spec-Generierung fehlgeschlagen: %s", exc
            )
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
        existing = pool._meta.get(name.lower().replace(" ", "-"))
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

    async def _auto_create_workflow(
        self, message: str, session_id: str
    ) -> tuple[str, bool]:
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
                timeout=12.0,
            )
            raw = response.content if hasattr(response, "content") else str(response)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                raise ValueError("Kein JSON-Objekt in der LLM-Antwort gefunden.")
            spec = _json.loads(m.group(0))
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning(
                "Auto-Create-Workflow: Spec-Generierung fehlgeschlagen: %s", exc
            )
            return _t(
                de="Fehler: Die Workflow-Spezifikation konnte nicht erzeugt werden. "
                "Bitte beschreibe Ablauf und Ziel klarer.",
                en="Error: Failed to generate the workflow specification. "
                "Please describe flow and goal more clearly.",
                fr="Erreur : La spécification du workflow n'a pas pu être générée. "
                "Veuillez décrire plus clairement le flux et l'objectif.",
                es="Error: No se pudo generar la especificación del workflow. "
                "Por favor, describe el flujo y el objetivo con más claridad.",
                it="Errore: impossibile generare la specifica del workflow. "
                "Descrivi più chiaramente il flusso e l'obiettivo.",
                nl="Fout: De workflow-specificatie kon niet worden gegenereerd. "
                "Beschrijf de stroom en het doel duidelijker.",
                pl="Błąd: Nie można wygenerować specyfikacji workflow. "
                "Opisz jasniej przepływ i cel.",
                pt="Erro: Falha ao gerar a especificação do workflow. "
                "Por favor, descreva o fluxo e o objetivo com mais clareza.",
                ja="エラー：ワークフロー仕様を生成できませんでした。"
                "フローと目標を明確に説明してください。",
                zh="错误：无法生成工作流规范。请更清楚地描述流程和目标。",
            ), False

        name = str(spec.get("name", "")).strip()[:120]
        description = str(spec.get("description", "")).strip()[:500]
        steps_raw = spec.get("steps", [])
        steps = [
            str(s).strip()
            for s in (steps_raw if isinstance(steps_raw, list) else [])
            if str(s).strip()
        ]

        if not name:
            return _t(
                de="Fehler: Die Workflow-Spezifikation enthält keinen gültigen Namen.",
                en="Error: The workflow specification has no valid name.",
                fr="Erreur : La spécification du workflow ne contient pas de nom valide.",
                es="Error: La especificación del workflow no contiene un nombre válido.",
                it="Errore: La specifica del workflow non contiene un nome valido.",
                nl="Fout: De workflow-specificatie bevat geen geldige naam.",
                pl="Błąd: Specyfikacja workflow nie zawiera prawidłowej nazwy.",
                pt="Erro: A especificação do workflow não contém um nome válido.",
                ja="エラー：ワークフロー仕様に有効な名前が含まれていません。",
                zh="错误：工作流规范没有有效的名称。",
            ), False
        if len(steps) < 2:
            return _t(
                de="Fehler: Für einen Workflow werden mindestens 2 Schritte benötigt.",
                en="Error: A workflow needs at least 2 steps.",
                fr="Erreur : Un workflow nécessite au moins 2 étapes.",
                es="Error: Un workflow necesita al menos 2 pasos.",
                it="Errore: Un workflow richiede almeno 2 passaggi.",
                nl="Fout: Een workflow heeft minimaal 2 stappen nodig.",
                pl="Błąd: Workflow wymaga co najmniej 2 kroków.",
                pt="Erro: Um workflow precisa de pelo menos 2 etapas.",
                ja="エラー：ワークフローには少なくとも2つのステップが必要です。",
                zh="错误：工作流至少需要2个步骤。",
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
    # Routing (2-Tier)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_bot_context(message: str) -> str:
        """Entfernt Bot-Kontext-Präfixe vor dem Keyword-Routing (z. B. '[Telegram Chat-ID: 123]').
        Das LLM erhält weiterhin den vollen Text — nur die Routing-Erkennung nutzt den bereinigten Text."""
        return re.sub(
            r"^\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?",
            "",
            message,
        ).strip()

    def _get_module_scores(self, text: str) -> dict[str, int]:
        """Keyword-Scoring für einen Text. Gibt Module → Score zurück (ohne History-Fallback)."""
        text_lower = text.lower()
        text_compact = re.sub(r"[\W_]+", "", text_lower)
        scores: dict[str, int] = {}
        for keyword, module_name in self._routing_map.items():
            kw_lower = keyword.lower()
            kw_compact = re.sub(r"[\W_]+", "", kw_lower)
            matches = len(re.findall(r"\b" + re.escape(kw_lower) + r"\b", text_lower))
            if len(kw_compact) >= 7 and matches == 0 and kw_compact in text_compact:
                matches = 1
            weight = (
                5
                if kw_lower
                in [module_name.lower(), module_name.lower().replace("-", "")]
                else 1
            )
            if matches > 0:
                scores[module_name] = scores.get(module_name, 0) + (matches * weight)
        return scores

    def _has_multistep_indicators(
        self,
        message: str,
        current_scores: dict[str, int],
    ) -> bool:
        """Erkennt explizite sequentielle Multi-Modul-Anfragen.

        Single-Module-Guard: Gibt False zurück wenn weniger als 2 Module mit Score >= 2
        in der aktuellen Nachricht erkannt wurden. "Logs anzeigen und dann neustart"
        (1 Modul) bleibt Tier 2.
        """
        # Mindestens 2 Module mit ausreichendem Score in aktueller Nachricht
        qualified = [mod for mod, score in current_scores.items() if score >= 2]
        if len(qualified) < 2:
            return False
        msg_lower = message.lower()
        return any(p.search(msg_lower) for p in _MULTISTEP_PATTERNS)

    def _detect_module_fast(
        self,
        message: str,
        chat_history: list[dict] | None = None,
    ) -> tuple[str | None, bool]:
        """Keyword-Fast-Path. Gibt (modul, is_compound) zurück.

        - (modul, False): genau ein eindeutiges Modul → Tier 2
        - (None, True):   mehrere Module → Compound → Tier 4
        - (None, False):  kein Treffer oder Tier-4-Guard → Tier 1
        """
        # Core-Overrides: explizite Core-Feature-Anfragen nicht an Module delegieren
        core_patterns = [
            r"\bwork?flows?\b",
            r"\bworflows?\b",
            r"\bagenten?\b",
            r"\bagent\s*erstellen\b",
            r"\bneuen?\s*agent\b",
            r"\bcreate\s*agent\b",
            r"\bnew\s*agent\b",
            r"\bcli\s*befehl\b",
            r"\blokales?\s*kommando\b",
            r"\bskript\s*ausführen\b",
            r"\bcli\s*command\b",
            r"\brun\s*script\b",
            r"\bshell\s*command\b",
            r"\bterminal\b",
            r"\bsystembefehl\b",
            r"\bping\b",
            r"\buptime\b",
        ]
        msg_lower = message.lower()
        for pattern in core_patterns:
            if re.search(pattern, msg_lower):
                logger.info(
                    "Core-Override erkannt ('%s'), überspringe Modul-Routing.", pattern
                )
                return None, False

        # Scoring der aktuellen Nachricht
        current_scores = self._get_module_scores(message)

        # History-Fallback NUR für Single-Module-Detection (nie für Compound)
        from_history = False
        if not current_scores and chat_history:
            history_text = " ".join([m.get("content", "") for m in chat_history[-3:]])
            history_scores = self._get_module_scores(history_text)
            if len(history_scores) == 1:
                best = next(iter(history_scores))
                logger.info("History-Fast-Path: '%s…' → '%s'", message[:60], best)
                return best, False
            elif history_scores:
                # Mehrere Treffer aus History → ReAct entscheiden lassen (nie Compound)
                sorted_h = sorted(
                    history_scores.items(), key=lambda x: x[1], reverse=True
                )
                logger.info("History-Ambiguität %s → ReAct-Loop", sorted_h)
                return None, False
            return None, False

        if not current_scores:
            logger.info(
                "Kein Keyword-Treffer → ReAct-Loop entscheidet für: '%s…'", message[:60]
            )
            return None, False

        if len(current_scores) == 1:
            best = next(iter(current_scores))
            logger.info(
                "Keyword-Fast-Path: '%s…' → '%s' (Score: %d)",
                message[:60],
                best,
                current_scores[best],
            )
            return best, False

        # Mehrere Module — Utility-Module filtern: nur wenn explizit erwähnt
        filtered: dict[str, int] = {}
        for mod, score in current_scores.items():
            if mod in _UTILITY_MODULES:
                if (
                    mod in msg_lower
                    or mod.replace("_", " ") in msg_lower
                    or mod.replace("_", "") in msg_lower
                ):
                    filtered[mod] = score
            else:
                filtered[mod] = score

        if len(filtered) <= 1:
            if filtered:
                best = next(iter(filtered))
                return best, False
            # Alle Matches waren nicht-explizite Utility-Module → ReAct
            return None, False

        # Compound-Schwellen: beide Top-Module müssen ≥ 3 Score und ausbalanciert sein
        sorted_f = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
        top_score = sorted_f[0][1]
        second_score = sorted_f[1][1]

        if top_score >= 3 and second_score >= 3 and second_score >= (0.4 * top_score):
            logger.info("Compound erkannt %s → Tier 4", sorted_f[:3])
            return None, True

        # Scores zu niedrig oder unausgewogen → stärkstes Modul gewinnt
        logger.info(
            "Schwache Ambiguität %s → Tier 2 mit stärkstem Modul '%s'",
            sorted_f[:3],
            sorted_f[0][0],
        )
        return sorted_f[0][0], False

    def _classify_tier(
        self,
        message: str,
        chat_history: list[dict] | None,
        cfg: RoutingConfig | None = None,
    ) -> tuple[int, str | None]:
        """
        3-Tier-Routing (Reihenfolge: 4 → 2 → 1):
        - Tier 4: Compound (mehrere Module mit hohem Score) ODER explizite sequentielle
                  Multi-Modul-Anfrage (_has_multistep_indicators) → Pipeline-Planner.
        - Tier 2: Keyword-Fast-Path → genau ein Modul eindeutig erkannt → direkt delegieren.
        - Tier 1: Alles andere → Orchestrator-ReAct-Loop: LLM entscheidet selbst.

        Returns:
            (tier, target_module_or_None)
        """
        if cfg is None:
            cfg = RoutingConfig()

        routing_message = self._strip_bot_context(message)
        target_module, is_compound = self._detect_module_fast(
            routing_message, chat_history
        )

        # ── Tier 4: Multi-Modul-Pipeline ─────────────────────────────────────
        if cfg.tier4_enabled:
            if is_compound:
                return 4, None
            # Multistep-Check nur bei keinem eindeutigen Single-Match
            if target_module is None:
                current_scores = self._get_module_scores(routing_message)
                if self._has_multistep_indicators(routing_message, current_scores):
                    return 4, None

        # ── Tier 2: Keyword-Fast-Path ─────────────────────────────────────────
        if cfg.tier2_enabled and target_module:
            return 2, target_module

        # ── Tier 1: Orchestrator-ReAct-Loop ──────────────────────────────────
        return 1, None

    async def _plan_and_execute_pipeline(
        self,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool,
    ) -> tuple[str, bool]:
        """Tier-4-Pipeline: LLM-Planner → Validierung → run_pipeline-Ausführung.

        Erstellt einen strukturierten Ausführungsplan (max 4 Schritte), validiert jeden
        Schritt gegen die Registry, filtert halluzinierte Utility-Module heraus und führt
        den Plan via run_pipeline aus.

        Fallback: Tier 1 (ReAct-Loop) bei Timeout, Parse-Fehler oder leerem Validierungsresultat.
        """
        from core.llm_factory import get_llm

        await status_bus.emit(
            session_id,
            _t(
                de="Plane mehrstufige Aufgabe…",
                en="Planning multi-step task…",
                fr="Planification de la tâche multi-étapes…",
                es="Planificando tarea de múltiples pasos…",
                it="Pianificazione attività multi-passo…",
                nl="Meerstaps-taak plannen…",
                pl="Planowanie zadania wieloetapowego…",
                pt="Planejando tarefa de múltiplas etapas…",
                ja="複数ステップのタスクを計画中…",
                zh="正在规划多步骤任务…",
            ),
        )

        modules = self.registry.list_modules()
        valid_module_names: set[str] = {m.name for m in modules}
        msg_lower = message.lower()

        # Utility-Module nur wenn explizit im Text erwähnt
        utility_explicitly_mentioned: set[str] = set()
        for mod in _UTILITY_MODULES:
            if (
                mod in msg_lower
                or mod.replace("_", " ") in msg_lower
                or mod.replace("_", "") in msg_lower
            ):
                utility_explicitly_mentioned.add(mod)

        # Module-Beschreibungen dynamisch aus Registry (keine hardcodierten Namen)
        module_lines = [f'- "{m.name}": {m.description}' for m in modules]
        module_descriptions = "\n".join(module_lines)

        planner_prompt = (
            f"Du bist ein Aufgaben-Planer. Erstelle einen Ausführungsplan.\n\n"
            f"ANFRAGE: {message}\n\n"
            f"VERFÜGBARE MODULE:\n{module_descriptions}\n\n"
            f"REGELN:\n"
            f"1. Maximal 4 Schritte\n"
            f"2. Nur Module nutzen die der User EXPLIZIT benötigt oder die als "
            f"Datenzulieferer für den nächsten Schritt zwingend nötig sind\n"
            f"3. Utility-Module (web_search, image_gen, telegram, email, teams) "
            f"NUR wenn der User sie explizit erwähnt\n"
            f"4. Jeder task-String muss die vollständige Aufgabe für das Modul enthalten\n"
            f"5. NUR das JSON-Array zurückgeben — kein erklärender Text\n\n"
            f'AUSGABE: [{{"module": "<name>", "task": "<vollständige aufgabe>"}}, ...]'
        )

        try:
            llm = get_llm()
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=planner_prompt)]),
                timeout=_LLM_ROUTING_TIMEOUT,
            )
            raw = response.content if hasattr(response, "content") else str(response)
            # Thinking-Blöcke entfernen
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            # Erstes JSON-Array extrahieren
            json_match = re.search(r"\[[\s\S]*?\]", raw)
            if not json_match:
                raise ValueError("Kein JSON-Array im Planner-Output gefunden")
            steps: list[dict] = _json.loads(json_match.group(0))
        except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning(
                "Tier-4-Planner fehlgeschlagen (%s) → Fallback Tier 1",
                exc,
            )
            await status_bus.emit(
                session_id,
                _t(
                    de="Pipeline-Planung fehlgeschlagen, direkte Verarbeitung…",
                    en="Pipeline planning failed, direct processing…",
                    fr="Échec de la planification du pipeline, traitement direct…",
                    es="Error en la planificación del pipeline, procesamiento directo…",
                    it="Pianificazione pipeline non riuscita, elaborazione diretta…",
                    nl="Pipeline-planning mislukt, directe verwerking…",
                    pl="Planowanie pipeline nie powiodło się, bezpośrednie przetwarzanie…",
                    pt="Falha no planejamento do pipeline, processamento direto…",
                    ja="パイプライン計画に失敗しました、直接処理中…",
                    zh="管道规划失败，直接处理中…",
                ),
            )
            return await self.invoke(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
            )

        # ── Validierung ────────────────────────────────────────────────────
        valid_steps: list[dict] = []
        for step in steps:
            mod = step.get("module", "").strip()
            task = step.get("task", "").strip()
            if not mod or not task:
                continue
            if mod not in valid_module_names:
                logger.warning("Tier-4: Modul '%s' nicht in Registry → verworfen", mod)
                continue
            if mod in _UTILITY_MODULES and mod not in utility_explicitly_mentioned:
                logger.warning(
                    "Tier-4: Utility-Modul '%s' nicht explizit erwähnt → verworfen",
                    mod,
                )
                continue
            valid_steps.append({"module": mod, "task": task})
            if len(valid_steps) >= 4:
                break

        if not valid_steps:
            logger.warning(
                "Tier-4: Keine validen Schritte nach Validierung → Fallback Tier 1"
            )
            return await self.invoke(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
            )

        logger.info(
            "Tier-4-Pipeline: %d Schritte: %s",
            len(valid_steps),
            [s["module"] for s in valid_steps],
        )
        await status_bus.emit(
            session_id,
            _t(
                de=f"Führe {len(valid_steps)}-Schritt-Pipeline aus…",
                en=f"Executing {len(valid_steps)}-step pipeline…",
                fr=f"Exécution du pipeline à {len(valid_steps)} étapes…",
                es=f"Ejecutando pipeline de {len(valid_steps)} pasos…",
                it=f"Esecuzione pipeline a {len(valid_steps)} passaggi…",
                nl=f"{len(valid_steps)}-staps pipeline uitvoeren…",
                pl=f"Wykonuję pipeline {len(valid_steps)}-etapowy…",
                pt=f"Executando pipeline de {len(valid_steps)} etapas…",
                ja=f"{len(valid_steps)}ステップのパイプラインを実行中…",
                zh=f"正在执行{len(valid_steps)}步管道…",
            ),
        )

        result = await run_pipeline.ainvoke({"steps": valid_steps})
        return str(result), False

    async def resume_tool_execution(self, session_id: str) -> tuple[str, bool]:
        """
        Setzt einen pausierten Tool-Call nach Safeguard-Bestätigung fort.

        Liest den wartenden Agent-Namen aus dem Redis-Key, sucht die Instanz
        und delegiert an agent.resume_safeguard_tool(session_id).
        """
        from core.redis_client import get_redis

        redis = get_redis()
        pending_raw = await redis.connection.get(
            f"ninko:safeguard_tool_pending:{session_id}"
        )
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
        except _ORCH_RECOVERABLE_EXCEPTIONS:
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
                    agent = pool.get_agent_by_id(agent_name)
                except _ORCH_RECOVERABLE_EXCEPTIONS:
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

    async def route(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
        confirmed: bool = False,
        force_module: str | None = None,
    ) -> tuple[str, str | None, bool]:
        """
        3-Tier-Routing (Reihenfolge: 4 → 2 → 1):
        - Tier 4: Compound-Erkennung oder explizit sequentielle Multi-Modul-Anfrage
                  → LLM-Planner → validierter JSON-Plan → run_pipeline.
        - Tier 2: Keyword-Fast-Path → genau ein Modul eindeutig erkannt → direkt delegieren.
        - Tier 1: Orchestrator-ReAct-Loop → LLM entscheidet: call_module_agent,
          run_pipeline, create_custom_agent, generate_image oder direkte Antwort.

        Returns:
            tuple[str, str | None, bool]: (Antwort, Modul oder None, did_compact)
        """
        status_bus.set_session_id(session_id)
        await status_bus.emit(
            session_id,
            _t(
                de="Analysiere deine Anfrage…",
                en="Analyzing your request…",
                fr="Analyse de votre demande…",
                es="Analizando tu solicitud…",
                it="Analizzando la tua richiesta…",
                nl="Je verzoek analyseren…",
                pl="Analizowanie Twojego żądania…",
                pt="Analisando sua solicitação…",
                ja="リクエストを分析中…",
                zh="正在分析您的请求…",
            ),
        )

        self._refresh_routing_map()
        cfg = await self._load_routing_config(session_id)
        cfg = self._proactive_routing_adjust(session_id, message, chat_history, cfg)

        # ── Direktes Modul-Routing (force_module) ────────────────────────────
        if force_module:
            agent = self.registry.get_agent(force_module)
            # Fallback: Custom Agent aus DynamicAgentPool (agent_id übergeben)
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
                            )
                            return response, force_module, did_compact
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
                            )
                except _ORCH_RECOVERABLE_EXCEPTIONS as pool_exc:
                    logger.warning(
                        "Custom-Agent '%s' aus Pool konnte nicht geladen werden: %s",
                        force_module,
                        pool_exc,
                    )
                    # Nicht ignorieren - wir wissen jetzt, dass es ein Pool-Problem gab
            if agent is None:
                return (
                    _t(
                        de=f"Fehler: Modul '{force_module}' ist nicht verfügbar oder nicht aktiviert.",
                        en=f"Error: Module '{force_module}' is not available or not enabled.",
                        fr=f"Erreur : Le module '{force_module}' n'est pas disponible ou n'est pas activé.",
                        es=f"Error: El módulo '{force_module}' no está disponible o no está activado.",
                        it=f"Errore: Il modulo '{force_module}' non è disponibile o non è attivato.",
                        nl=f"Fout: Module '{force_module}' is niet beschikbaar of niet geactiveerd.",
                        pl=f"Błąd: Moduł '{force_module}' nie jest dostępny lub nie jest włączony.",
                        pt=f"Erro: Módulo '{force_module}' não disponível ou não ativado.",
                        ja=f"エラー：モジュール '{force_module}' が利用できないか、有効になっていません。",
                        zh=f"错误：模块 '{force_module}' 不可用或未启用。",
                    ),
                    force_module,
                    False,
                )
            manifests = {m.name: m for m in self.registry.list_modules()}
            display = manifests.get(
                force_module, type("", (), {"display_name": force_module})()
            ).display_name
            await status_bus.emit(
                session_id,
                _t(
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
            )
            logger.info(
                "Direktes Routing an Modul '%s': %s…", force_module, message[:80]
            )
            try:
                response, did_compact = await agent.invoke(
                    message=message,
                    chat_history=chat_history,
                    session_id=session_id,
                    confirmed=confirmed,
                )
                return response, force_module, did_compact
            except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
                logger.error(
                    "Direktes Routing: Modul '%s' Fehler: %s",
                    force_module,
                    exc,
                    exc_info=True,
                )
                return (
                    _t(
                        de=f"Fehler: Modul '{force_module}' hat einen Fehler gemeldet: {exc}.",
                        en=f"Error: Module '{force_module}' reported an error: {exc}.",
                        fr=f"Erreur : Le module '{force_module}' a signalé une erreur : {exc}.",
                        es=f"Error: El módulo '{force_module}' reportó un error: {exc}.",
                        it=f"Errore: Il modulo '{force_module}' ha segnalato un errore: {exc}.",
                        nl=f"Fout: Module '{force_module}' heeft een fout gerapporteerd: {exc}.",
                        pl=f"Błąd: Moduł '{force_module}' zgłosił błąd: {exc}.",
                        pt=f"Erro: Módulo '{force_module}' relatou um erro: {exc}.",
                        ja=f"エラー：モジュール '{force_module}' がエラーを報告しました: {exc}。",
                        zh=f"错误：模块 '{force_module}' 报告了错误: {exc}。",
                    ),
                    force_module,
                    False,
                )

        # ── Explizite Agent-Erstellung: deterministischer Create-Fast-Path ──
        # Verhindert "nur Anleitung", wenn der User klar "Agent erstellen" verlangt.
        if self._wants_agent_creation(message):
            logger.info(
                "Explizite Agent-Erstellungs-Intention erkannt → Auto-Create-Fast-Path."
            )
            response, did_compact = await self._auto_create_custom_agent(
                message, session_id
            )
            return response, "orchestrator", did_compact

        # ── Explizite Workflow-Erstellung: deterministischer Create-Fast-Path ─
        # Verhindert "nur Anleitung", wenn der User klar "Workflow erstellen" verlangt.
        if self._wants_workflow_creation(message):
            logger.info(
                "Explizite Workflow-Erstellungs-Intention erkannt → Auto-Create-Fast-Path."
            )
            response, did_compact = await self._auto_create_workflow(
                message, session_id
            )
            return response, "orchestrator", did_compact

        tier, target_module = self._classify_tier(message, chat_history, cfg)
        self._last_tier_used = tier
        self._update_session_stats(session_id, tier, target_module)
        logger.info("Routing-Tier %d gewählt für: %s…", tier, message[:80])

        # ── Tier 4: Multi-Modul-Pipeline-Planner ─────────────────────────
        if tier == 4:
            response, did_compact = await self._plan_and_execute_pipeline(
                message=message,
                chat_history=chat_history,
                session_id=session_id,
                confirmed=confirmed,
            )
            return response, None, did_compact

        # ── Tier 2: Keyword-Fast-Path direkt zum Modul-Agent ─────────────
        if tier == 2 and target_module:
            agent = self.registry.get_agent(target_module)
            if agent is not None:
                readonly_tools = self._get_readonly_tools_for_module(target_module)
                if readonly_tools:
                    complexity = await self._check_task_complexity(message, target_module)
                    if complexity and complexity.get("is_complex"):
                        logger.info(
                            "Tier 2.5: DataAnalysisSubagent für '%s' (Reason: %s)",
                            target_module,
                            complexity.get("reasoning", "unknown"),
                        )
                        await status_bus.emit(
                            session_id,
                            _t(
                                de=f"Analysiere komplexe Daten in {target_module}…",
                                en=f"Analyzing complex data in {target_module}…",
                            ),
                        )

                        subagent = _get_or_create_subagent(
                            session_id=session_id,
                            module=target_module,
                            tools=readonly_tools,
                        )
                        try:
                            response, did_compact = await subagent.invoke(
                                task=message,
                                chat_history=chat_history,
                                sub_tasks=complexity.get("sub_tasks"),
                            )
                        finally:
                            _cleanup_subagent(session_id, target_module)
                        return response, target_module, did_compact

                manifests = {m.name: m for m in self.registry.list_modules()}
                display = manifests.get(
                    target_module, type("", (), {"display_name": target_module})()
                ).display_name
                await status_bus.emit(
                    session_id,
                    _t(
                        de=f"Rufe {display} auf…",
                        en=f"Calling {display}…",
                        fr=f"Appel de {display}…",
                        es=f"Llamando a {display}…",
                        it=f"Chiamando {display}…",
                        nl=f"{display} aanroepen…",
                        pl=f"Wywołuję {display}…",
                        pt=f"Chamando {display}…",
                        ja=f"{display} を呼び出し中…",
                        zh=f"正在调用 {display}…",
                    ),
                )
                logger.info(
                    "Tier 2: Routing an Modul '%s': %s…", target_module, message[:80]
                )
                try:
                    response, did_compact = await agent.invoke(
                        message=message,
                        chat_history=chat_history,
                        session_id=session_id,
                        confirmed=confirmed,
                    )
                    return response, target_module, did_compact
                except _ORCH_RECOVERABLE_EXCEPTIONS as exc:
                    logger.error(
                        "Tier 2: Modul '%s' Fehler: %s",
                        target_module,
                        exc,
                        exc_info=True,
                    )
                    return (
                        _t(
                            de=f"Fehler: Modul '{target_module}' hat einen Fehler gemeldet: {exc}.",
                            en=f"Error: Module '{target_module}' reported an error: {exc}.",
                            fr=f"Erreur : Le module '{target_module}' a signalé une erreur : {exc}.",
                            es=f"Error: El módulo '{target_module}' reportó un error: {exc}.",
                            it=f"Errore: Il modulo '{target_module}' ha segnalato un errore: {exc}.",
                            nl=f"Fout: Module '{target_module}' heeft een fout gerapporteerd: {exc}.",
                            pl=f"Błąd: Moduł '{target_module}' zgłosił błąd: {exc}.",
                            pt=f"Erro: Módulo '{target_module}' relatou um erro: {exc}.",
                            ja=f"エラー：モジュール '{target_module}' がエラーを報告しました: {exc}。",
                            zh=f"错误：模块 '{target_module}' 报告了错误: {exc}。",
                        ),
                        target_module,
                        False,
                    )
            else:
                logger.warning(
                    "Modul '%s' hat keinen registrierten Agent — Fallback auf ReAct-Loop.",
                    target_module,
                )
        # ── Tier 1: Orchestrator-ReAct-Loop ─────────────────────────────
        # LLM entscheidet: call_module_agent, run_pipeline, create_custom_agent oder direkte Antwort.
        logger.info("Tier 1: Orchestrator-ReAct-Loop für: %s…", message[:80])
        response, did_compact = await self.invoke(
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
        )
        return response, None, did_compact


# ── Globaler Singleton (gesetzt von main.py) ─────────────────────────────────
_global_orchestrator: "OrchestratorAgent | None" = None


def get_orchestrator() -> "OrchestratorAgent | None":
    """Gibt die globale Orchestrator-Instanz zurück (nach App-Start verfügbar)."""
    return _global_orchestrator


def set_orchestrator(orchestrator: "OrchestratorAgent") -> None:
    """Wird von main.py nach Erstellung des Orchestrators aufgerufen."""
    global _global_orchestrator
    _global_orchestrator = orchestrator
