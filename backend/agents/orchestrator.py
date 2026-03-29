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
from agents.core_tools import execute_cli_command, create_custom_agent, install_skill, create_linear_workflow, execute_workflow, remember_fact, recall_memory, forget_fact, confirm_forget, call_module_agent, run_pipeline, configure_routing, get_routing_info
from modules.image_gen.tools import generate_image
from core import status_bus

if TYPE_CHECKING:
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.orchestrator")

# ── Tier-4 Konstanten ─────────────────────────────────────────────────────────

# Utility-Module zählen für Compound-Scoring nur wenn explizit erwähnt
_UTILITY_MODULES: frozenset[str] = frozenset({
    "web_search", "image_gen", "telegram", "email", "teams",
})

# Sequentielle Verknüpfungs-Muster (word-boundary-gesichert)
_MULTISTEP_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r'\bund\s+dann\b',
    r'\bund\s+danach\b',
    r'\bdanach\b',
    r'\banschlie[ßs]end\b',
    r'\bals\s+n[äa]chstes\b',
    r'\bzuerst\b.{1,80}\bdann\b',
    r'\berst\b.{1,80}\bdann\b',
    r'\bnachdem\b',
    r'\bwenn\s+fertig\b',
    r'\bim\s+anschluss\b',
    r'\bthen\b',
    r'\bafter\s+that\b',
    r'\bfollowed\s+by\b',
    r'\bwhen\s+done\b',
]]

# Timeout für den Pipeline-Planner-LLM-Call
_LLM_ROUTING_TIMEOUT: float = 10.0

# ── Routing-Konfiguration ─────────────────────────────────────────────────────

@dataclass
class RoutingConfig:
    """Routing-Konfiguration des Orchestrators (session-scoped).

    Zwei Pfade:
    - Tier 2 (keyword fast-path): Einzelnes Modul eindeutig erkannt → direkt delegieren.
    - Tier 1 (invoke): Alles andere → Orchestrator-ReAct-Loop entscheidet selbst
      via call_module_agent / run_pipeline / create_custom_agent / direkte Antwort.
    """
    tier1_enabled: bool = True   # ReAct-Loop für alles ohne eindeutigen Keyword-Match
    tier2_enabled: bool = True   # Keyword-Fast-Path direkt zum Modul-Agent
    tier4_enabled: bool = True   # Multi-Modul-Pipeline-Planner
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
    "module-only": {"preset": "module-only", "tier1_enabled": False, "tier4_enabled": False},
}

# ── Session-scoped Routing State ──────────────────────────────────────────────
# Routing-Configs gelten nur für die aktuelle Session — nach Session-Ende zurück zu Defaults.
# session_id → (RoutingConfig, last_updated_monotonic)
_session_routing_configs: dict[str, tuple[RoutingConfig, float]] = {}
# session_id → {"tiers": [2,2,1,2], "modules": ["k8s","k8s",None,"k8s"]}
_session_stats: dict[str, dict] = {}
_SESSION_ROUTING_TTL = 86400.0  # 24h, matching Redis chat-history TTL

# Speed signals that trigger auto-fast preset for a session (DE + EN)
_SPEED_SIGNALS = frozenset({
    "schnell", "schnelle", "schneller", "schnelles", "quick", "fast",
    "kurz", "kurze", "kurzer", "kurzes", "brief", "knapp", "simplified",
    "einfach", "kürzer", "kürze",
})


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
3. Braucht der User ein spezialisiertes KI-Profil das kein Modul abdeckt?
   → `create_custom_agent` aufrufen.
4. Braucht der User einen Workflow?
   → `create_linear_workflow` SOFORT aufrufen — NIEMALS nur erklären wie es geht.
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

WICHTIG: `call_module_agent` für EINZELNE Modul-Aufrufe. `run_pipeline` wenn Ergebnisse zwischen Modulen fließen müssen. Multi-Modul-Anfragen mit explizit sequentiellem Intent (z.B. "restart X und schick dann Telegram-Nachricht") werden automatisch als Tier-4-Pipeline erkannt und benötigen KEIN manuelles `run_pipeline` im ReAct-Loop — vermeide Doppel-Routing.

BILD-TAGS: Wenn ein Tool-Ergebnis `[KUMIO_IMAGE:url]` enthält, übernimm diesen Tag EXAKT und UNVERÄNDERT in deine Antwort. Ersetze ihn NIEMALS durch einen Markdown-Link, eine URL oder ein Emoji. Der Tag muss wörtlich `[KUMIO_IMAGE:https://...]` im Antworttext erscheinen.

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
            tools=[execute_cli_command, create_custom_agent, install_skill, create_linear_workflow, execute_workflow, remember_fact, recall_memory, forget_fact, confirm_forget, call_module_agent, run_pipeline, generate_image, configure_routing, get_routing_info],
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
        except Exception as e:
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
        except Exception as e:
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
            new_cfg = RoutingConfig.from_dict({**RoutingConfig().to_dict(), "preset": "fast"})
            set_session_routing_config(session_id, new_cfg)
            logger.info("Proaktives Routing: Speed-Signal erkannt → Fast-Preset für Session '%s'", session_id)
            return new_cfg

        # ── Heuristik 2: Reset-Signale → zurück zu Defaults ─────────────────
        _RESET_SIGNALS = {"default", "normal", "reset", "zurück", "standard", "alles", "wieder"}
        if words & _RESET_SIGNALS and cfg.preset != "default":
            clear_session_routing_config(session_id)
            logger.info("Proaktives Routing: Reset-Signal erkannt → Defaults für Session '%s'", session_id)
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
            new_cfg = RoutingConfig.from_dict({**cfg.to_dict(), "preset": f"focus:{dominant}"})
            set_session_routing_config(session_id, new_cfg)
            logger.info(
                "Proaktives Routing: Modul-Fokus '%s' erkannt (Session '%s')",
                dominant, session_id,
            )
            return new_cfg

        return cfg

    def _update_session_stats(self, session_id: str, tier: int, module: str | None) -> None:
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
        return re.sub(r'^\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?', '', message).strip()

    def _get_module_scores(self, text: str) -> dict[str, int]:
        """Keyword-Scoring für einen Text. Gibt Module → Score zurück (ohne History-Fallback)."""
        text_lower = text.lower()
        text_compact = re.sub(r'[\W_]+', '', text_lower)
        scores: dict[str, int] = {}
        for keyword, module_name in self._routing_map.items():
            kw_lower = keyword.lower()
            kw_compact = re.sub(r'[\W_]+', '', kw_lower)
            matches = len(re.findall(r'\b' + re.escape(kw_lower) + r'\b', text_lower))
            if len(kw_compact) >= 7 and matches == 0 and kw_compact in text_compact:
                matches = 1
            weight = 5 if kw_lower in [module_name.lower(), module_name.lower().replace("-", "")] else 1
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
            r"\bwork?flows?\b", r"\bworflows?\b",
            r"\bagenten?\b", r"\bagent\s*erstellen\b", r"\bneuen?\s*agent\b",
            r"\bcreate\s*agent\b", r"\bnew\s*agent\b",
            r"\bcli\s*befehl\b", r"\blokales?\s*kommando\b", r"\bskript\s*ausführen\b",
            r"\bcli\s*command\b", r"\brun\s*script\b", r"\bshell\s*command\b",
            r"\bterminal\b", r"\bsystembefehl\b", r"\bping\b", r"\buptime\b",
        ]
        msg_lower = message.lower()
        for pattern in core_patterns:
            if re.search(pattern, msg_lower):
                logger.info("Core-Override erkannt ('%s'), überspringe Modul-Routing.", pattern)
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
                sorted_h = sorted(history_scores.items(), key=lambda x: x[1], reverse=True)
                logger.info("History-Ambiguität %s → ReAct-Loop", sorted_h)
                return None, False
            return None, False

        if not current_scores:
            logger.info("Kein Keyword-Treffer → ReAct-Loop entscheidet für: '%s…'", message[:60])
            return None, False

        if len(current_scores) == 1:
            best = next(iter(current_scores))
            logger.info("Keyword-Fast-Path: '%s…' → '%s' (Score: %d)", message[:60], best, current_scores[best])
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
            sorted_f[:3], sorted_f[0][0],
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
        target_module, is_compound = self._detect_module_fast(routing_message, chat_history)

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

        await status_bus.emit(session_id, _t(
            "Plane mehrstufige Aufgabe…", "Planning multi-step task…",
        ))

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
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
            # Erstes JSON-Array extrahieren
            json_match = re.search(r'\[[\s\S]*?\]', raw)
            if not json_match:
                raise ValueError("Kein JSON-Array im Planner-Output gefunden")
            steps: list[dict] = _json.loads(json_match.group(0))
        except Exception as exc:
            logger.warning(
                "Tier-4-Planner fehlgeschlagen (%s) → Fallback Tier 1", exc,
            )
            await status_bus.emit(session_id, _t(
                "Pipeline-Planung fehlgeschlagen, direkte Verarbeitung…",
                "Pipeline planning failed, direct processing…",
            ))
            return await self.invoke(
                message=message, chat_history=chat_history,
                session_id=session_id, confirmed=confirmed,
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
                    "Tier-4: Utility-Modul '%s' nicht explizit erwähnt → verworfen", mod,
                )
                continue
            valid_steps.append({"module": mod, "task": task})
            if len(valid_steps) >= 4:
                break

        if not valid_steps:
            logger.warning("Tier-4: Keine validen Schritte nach Validierung → Fallback Tier 1")
            return await self.invoke(
                message=message, chat_history=chat_history,
                session_id=session_id, confirmed=confirmed,
            )

        logger.info(
            "Tier-4-Pipeline: %d Schritte: %s",
            len(valid_steps), [s["module"] for s in valid_steps],
        )
        await status_bus.emit(session_id, _t(
            f"Führe {len(valid_steps)}-Schritt-Pipeline aus…",
            f"Executing {len(valid_steps)}-step pipeline…",
        ))

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
                "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                "Error: No pending tool call for this session.",
            ), False

        try:
            pending = _json.loads(pending_raw)
        except Exception:
            pending = {}

        agent_name = pending.get("agent", "orchestrator")

        # Redis-Key löschen (agent re-erstellt ihn falls weiterer Call Bestätigung braucht)
        await redis.connection.delete(f"ninko:safeguard_tool_pending:{session_id}")

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
                except Exception:
                    agent = None

        if agent is None:
            return _t(
                f"Fehler: Agent '{agent_name}' nicht gefunden.",
                f"Error: Agent '{agent_name}' not found.",
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
        await status_bus.emit(session_id, _t("Analysiere deine Anfrage…", "Analyzing your request…"))

        self._refresh_routing_map()
        cfg = await self._load_routing_config(session_id)
        cfg = self._proactive_routing_adjust(session_id, message, chat_history, cfg)

        # ── Direktes Modul-Routing (force_module) ────────────────────────────
        if force_module:
            agent = self.registry.get_agent(force_module)
            if agent is None:
                return (
                    _t(
                        f"Fehler: Modul '{force_module}' ist nicht verfügbar oder nicht aktiviert.",
                        f"Error: Module '{force_module}' is not available or not enabled.",
                    ),
                    force_module,
                    False,
                )
            manifests = {m.name: m for m in self.registry.list_modules()}
            display = manifests.get(
                force_module, type("", (), {"display_name": force_module})()
            ).display_name
            await status_bus.emit(session_id, _t(f"Rufe {display} direkt auf…", f"Calling {display} directly…"))
            logger.info("Direktes Routing an Modul '%s': %s…", force_module, message[:80])
            try:
                response, did_compact = await agent.invoke(
                    message=message,
                    chat_history=chat_history,
                    session_id=session_id,
                    confirmed=confirmed,
                )
                return response, force_module, did_compact
            except Exception as exc:
                logger.error("Direktes Routing: Modul '%s' Fehler: %s", force_module, exc, exc_info=True)
                return (
                    _t(
                        f"Fehler: Modul '{force_module}' hat einen Fehler gemeldet: {exc}.",
                        f"Error: Module '{force_module}' reported an error: {exc}.",
                    ),
                    force_module,
                    False,
                )

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
                manifests = {m.name: m for m in self.registry.list_modules()}
                display = manifests.get(
                    target_module, type("", (), {"display_name": target_module})()
                ).display_name
                await status_bus.emit(session_id, f"Rufe {display} auf…")
                logger.info("Tier 2: Routing an Modul '%s': %s…", target_module, message[:80])
                try:
                    response, did_compact = await agent.invoke(
                        message=message,
                        chat_history=chat_history,
                        session_id=session_id,
                        confirmed=confirmed,
                    )
                    return response, target_module, did_compact
                except Exception as exc:
                    logger.error("Tier 2: Modul '%s' Fehler: %s", target_module, exc, exc_info=True)
                    return (
                        _t(
                            f"Fehler: Modul '{target_module}' hat einen Fehler gemeldet: {exc}.",
                            f"Error: Module '{target_module}' reported an error: {exc}.",
                        ),
                        target_module,
                        False,
                    )
            else:
                logger.warning("Modul '%s' hat keinen registrierten Agent — Fallback auf ReAct-Loop.", target_module)

        # ── Tier 1: Orchestrator-ReAct-Loop ─────────────────────────────
        # LLM entscheidet: call_module_agent, run_pipeline, create_custom_agent oder direkte Antwort.
        logger.info("Tier 1: Orchestrator-ReAct-Loop für: %s…", message[:80])
        response, did_compact = await self.invoke(
            message=message, chat_history=chat_history, session_id=session_id,
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
