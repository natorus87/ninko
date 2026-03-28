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
import hashlib
import json as _json
import logging
import re
import time
from dataclasses import dataclass, fields as _dc_fields
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent, _t
from agents.core_tools import execute_cli_command, create_custom_agent, install_skill, create_linear_workflow, execute_workflow, remember_fact, recall_memory, forget_fact, confirm_forget, call_module_agent, run_pipeline, configure_routing, get_routing_info
from modules.image_gen.tools import generate_image
from core import status_bus

if TYPE_CHECKING:
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.orchestrator")

# ── Tier-Klassifikation ────────────────────────────────────────────────────

# Indikatoren für mehrstufige Aufgaben (→ Stufe 4) — DE + EN, pre-compiled
_MULTISTEP_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    # Deutsch
    r"\b(erst|zuerst|zunächst)\b.{5,80}\b(dann|danach|anschließend)\b",
    r"\b(und\s+dann|und\s+anschließend|und\s+danach|und\s+schicke|und\s+sende|und\s+erstelle)\b",
    r"\bschritt\s*\d+\b",
    r"\b(analysiere|prüfe)\b.{5,80}\b(und|dann)\b.{5,80}\b(erstelle|schicke|sende|melde)\b",
    # English
    r"\b(first|initially)\b.{5,80}\b(then|next|afterwards|after\s+that)\b",
    r"\b(and\s+then|and\s+next|and\s+afterwards|and\s+send|and\s+create)\b",
    r"\bstep\s*\d+\b",
    r"\b(analyze|check|inspect)\b.{5,80}\b(and|then)\b.{5,80}\b(create|send|report|notify)\b",
]]

# Action-Verben die auf eine operative Aufgabe hinweisen (kein Tier-1) — DE + EN
_ACTION_VERBS = {
    # Deutsch
    "erstelle", "erstell", "lösche", "starte", "stoppe", "führe aus",
    "konfiguriere", "deploye", "analysiere", "prüfe", "überprüfe",
    "scanne", "hole", "lade", "liste", "suche", "setze", "update",
    "neustarte", "skaliere", "öffne", "schließe", "aktiviere", "deaktiviere",
    "sende", "schicke", "erzeuge", "generiere", "berechne", "optimiere",
    # English
    "create", "delete", "remove", "start", "stop", "execute", "run",
    "configure", "deploy", "analyze", "check", "inspect", "verify",
    "scan", "fetch", "load", "list", "search", "find", "set", "update",
    "restart", "scale", "open", "close", "enable", "disable",
    "send", "generate", "calculate", "optimize",
}

# ── LLM-Routing-Cache ─────────────────────────────────────────────────────────
# Verhindert doppelte LLM-Calls bei schnellen Folgenachrichten (TTL 60s)
_llm_routing_cache: dict[str, tuple[str | None, float]] = {}  # hash → (module|None, timestamp)
_LLM_ROUTING_CACHE_TTL = 60.0  # seconds
_LLM_ROUTING_TIMEOUT = 8.0     # seconds – kurzer Timeout für Routing-Call

# ── Routing-Konfiguration ─────────────────────────────────────────────────────

@dataclass
class RoutingConfig:
    """Laufzeit-Konfiguration für die 4-Tier-Routing-Logik des Orchestrators.

    Alle Felder haben Defaults, die das bisherige Verhalten 1:1 reproduzieren.
    Session-scoped: Änderungen gelten nur für die aktuelle Session, danach Defaults.
    """
    tier1_enabled: bool = True
    tier2_enabled: bool = True
    tier3_enabled: bool = True
    tier4_enabled: bool = True
    simple_query_max_chars: int = 120
    llm_routing_enabled: bool = True
    llm_routing_timeout: float = 8.0
    llm_routing_cache_ttl: float = 60.0
    multistep_detection_enabled: bool = True
    preset: str = "default"

    @classmethod
    def from_dict(cls, d: dict) -> "RoutingConfig":
        known = {f.name for f in _dc_fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in _dc_fields(self)}


ROUTING_PRESETS: dict[str, dict] = {
    "default": {},
    "fast": {
        "preset": "fast",
        "llm_routing_enabled": False,
        "tier3_enabled": False,
        "tier4_enabled": False,
    },
    "module-only": {
        "preset": "module-only",
        "tier1_enabled": False,
        "tier3_enabled": False,
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


SYSTEM_PROMPT = """Du bist Ninko – ein intelligenter IT-Operations-Assistent mit 4 Verarbeitungsstufen.

Deine Aufgabe:
- Du bist der zentrale Ansprechpartner für IT-Operations-Fragen.
- Du routest Anfragen an spezialisierte Module (siehe VERFÜGBARE MODULE weiter unten).
- Wenn keine spezialisierten Module zuständig sind, antwortest du direkt.
- Du hast Zugriff auf lokale CLI-Commands (execute_cli_command), um Systeminformationen (z. B. uptime, ping, ls) abzufragen. Nutze dies proaktiv, wenn der User nach Host/Container-Zuständen fragt.
- Du kannst eigene "Custom Agents" erstellen (`create_custom_agent`), um definierte KI-Personas für den Nutzer anzulegen.
- Du kannst Skills installieren (`install_skill`): prozedurales Domänenwissen das automatisch in passende Agenten injiziert wird. Nutze dies, wenn der User dir eine spezifische Vorgehensweise, ein Verfahren oder Best Practices beibringt, die dauerhaft gespeichert werden sollen.
- WICHTIG: Wenn der User einen Workflow fordert, erkläre ihm NICHT wie er das machen kann. DU MUSST ZWINGEND das Tool `create_linear_workflow` aufrufen, um ihn sofort für ihn zu erstellen! Formuliere dafür einfach die gefragte Schritt-für-Schritt-Logik.
- Du kannst Bilder generieren (`generate_image`). Nutze dieses Tool wenn der User ein Bild, eine Illustration, ein Logo oder eine Grafik erstellen möchte. Beschreibe das Bild detailliert im Prompt (auf Englisch für bessere Ergebnisse). Die generierte Bild-URL wird dem User angezeigt.
- Du kannst Workflows ausführen (`execute_workflow`). Führe explizite Workflows aus, wenn der User danach verlangt, und präsentiere ihm das Ergebnis detailliert im Chat.
- Du hast ein Langzeitgedächtnis (`remember_fact`, `recall_memory`, `forget_fact`, `confirm_forget`). Nutze `remember_fact`, wenn der User dich bittet, sich etwas dauerhaft zu merken. Nutze `recall_memory`, wenn du prüfen möchtest, ob du etwas weißt. Wenn der User etwas vergessen lassen will: Rufe ZUERST `forget_fact` auf (Vorschau ohne Löschen), zeige dem User die Kandidaten, und rufe danach erst `confirm_forget` mit den bestätigten IDs auf.
- Du antwortest präzise, professionell und hilfreich.

MODULÜBERGREIFENDE AUFGABEN:
- Für ALLE mehrstufigen Aufgaben die MEHRERE Module erfordern: IMMER `run_pipeline` verwenden!
  `run_pipeline` ist DETERMINISTISCH und ZUVERLÄSSIG – es übergibt Ergebnisse automatisch weiter.
  Verwende es statt mehrerer `call_module_agent`-Aufrufe!
- Beispiele:
  - "Recherchiere X und schicke mir das per Telegram" → run_pipeline([{"module":"web_search","task":"..."},{"module":"telegram","task":"Sende die Ergebnisse an den User"}])
  - "Prüfe K8s auf Fehler und erstelle GLPI-Ticket" → run_pipeline([{"module":"kubernetes","task":"..."},{"module":"glpi","task":"..."}])
- `call_module_agent` nur für EINZELNE isolierte Modul-Aufrufe ohne Folgeschritte verwenden.

Verhalte dich professionell, proaktiv und sicherheitsbewusst.

**Routing-Selbstoptimierung**: Du kannst dein eigenes Routing-Verhalten dynamisch anpassen.
- Nutze `get_routing_info` um die aktuelle Konfiguration und das zuletzt genutzte Tier zu prüfen.
- Nutze `configure_routing` wenn:
  - LLM-Klassifikation wiederholt langsam oder falsch ist → llm_routing_enabled=False
  - Der User explizit schnellere Antworten möchte → preset='fast'
  - Tier-3-Agenten immer irrelevant sind → tier3_enabled=False
  - Alle Anfragen immer zu Modulen sollen (keine Direktantworten) → tier1_enabled=False
  - Der User preset='default' möchte, um das Routing zurückzusetzen → preset='default'
- Ändere das Routing nur wenn du einen klaren Grund hast. Kommuniziere kurz, was du geändert hast."""


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
            new_cfg = RoutingConfig.from_dict({
                **RoutingConfig().to_dict(),
                "preset": "fast",
                "llm_routing_enabled": False,
                "tier3_enabled": False,
            })
            set_session_routing_config(session_id, new_cfg)
            logger.info(
                "Proaktives Routing: Speed-Signal erkannt → Fast-Preset für Session '%s'", session_id
            )
            return new_cfg

        # ── Heuristik 2: Reset-Signale → zurück zu Defaults ─────────────────
        _RESET_SIGNALS = {"default", "normal", "reset", "zurück", "standard", "alles", "wieder"}
        if words & _RESET_SIGNALS and cfg.preset != "default":
            clear_session_routing_config(session_id)
            logger.info(
                "Proaktives Routing: Reset-Signal erkannt → Defaults für Session '%s'", session_id
            )
            return RoutingConfig()

        # ── Heuristik 3: Modul-Fokus → LLM-Routing deaktivieren wenn unnötig ─
        recent_tiers = stats.get("tiers", [])[-6:]
        recent_modules = [m for m in stats.get("modules", [])[-6:] if m]
        if (
            len(recent_tiers) >= 5
            and all(t == 2 for t in recent_tiers)        # alle letzten Anfragen Tier 2
            and len(set(recent_modules)) == 1             # immer dasselbe Modul
            and cfg.llm_routing_enabled                   # LLM-Routing noch aktiv
        ):
            dominant = recent_modules[0]
            new_cfg = RoutingConfig.from_dict({
                **cfg.to_dict(),
                "llm_routing_enabled": False,
                "preset": f"focus:{dominant}",
            })
            set_session_routing_config(session_id, new_cfg)
            logger.info(
                "Proaktives Routing: Modul-Fokus '%s' erkannt → LLM-Routing deaktiviert für Session '%s'",
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

    def _build_module_descriptions(self) -> str:
        """
        Baut eine Beschreibungs-Liste aller aktiven Module für den LLM-Routing-Prompt.
        Format: "- <name>: <description> (z.B.: kw1, kw2, kw3)"
        Wird dynamisch aus der Registry gebaut – kein Hardcoding.
        """
        lines: list[str] = []
        for manifest in self.registry.list_modules():
            desc = manifest.description or manifest.display_name
            kw_examples = ", ".join(manifest.routing_keywords[:5])
            kw_part = f" (z.B.: {kw_examples})" if kw_examples else ""
            lines.append(f"- {manifest.name}: {desc}{kw_part}")
        return "\n".join(lines)

    async def _llm_classify_module(
        self,
        message: str,
        timeout: float | None = None,
        cache_ttl: float | None = None,
    ) -> str | None:
        """
        LLM-basierte Modul-Klassifikation — Fallback wenn Keyword-Matching
        keinen eindeutigen Treffer liefert (Score=0 oder Ambiguität).

        Args:
            timeout: LLM-Timeout in Sekunden (Default: _LLM_ROUTING_TIMEOUT)
            cache_ttl: Cache-TTL in Sekunden (Default: _LLM_ROUTING_CACHE_TTL)

        Returns:
            Modulname (exakt aus Registry) oder None (kein passendes Modul / Fehler).
        """
        _timeout = timeout if timeout is not None else _LLM_ROUTING_TIMEOUT
        _cache_ttl = cache_ttl if cache_ttl is not None else _LLM_ROUTING_CACHE_TTL

        global _llm_routing_cache

        # Cache-Check (verhindert Doppel-Calls bei schnellen Folgenachrichten)
        msg_hash = hashlib.md5(message.encode(), usedforsecurity=False).hexdigest()
        now = time.monotonic()
        if msg_hash in _llm_routing_cache:
            cached_module, cached_ts = _llm_routing_cache[msg_hash]
            if now - cached_ts < _cache_ttl:
                logger.info(
                    "LLM-Routing Cache-Treffer: '%s…' → '%s'",
                    message[:50], cached_module,
                )
                return cached_module

        # Alte Cache-Einträge bereinigen
        if len(_llm_routing_cache) > 500:
            cutoff = now - _cache_ttl
            _llm_routing_cache = {
                k: v for k, v in _llm_routing_cache.items() if v[1] > cutoff
            }

        available_names = {m.name for m in self.registry.list_modules()}
        module_descriptions = self._build_module_descriptions()

        system_prompt = _t(
            "Du bist ein Nachrichten-Router für ein IT-Operations-System. "
            "Antworte NUR mit dem exakten Modulnamen aus der Liste oder dem Wort 'none'. "
            "Kein anderer Text, keine Erklärung, keine Formatierung.",
            "You are a message router for an IT operations system. "
            "Respond ONLY with the exact module name from the list or the word 'none'. "
            "No other text, no explanation, no formatting.",
        )
        user_prompt = _t(
            f"Nachricht: \"{message}\"\n\n"
            f"Verfügbare Module:\n{module_descriptions}\n\n"
            "Welches Modul soll diese Nachricht bearbeiten? "
            "Antworte NUR mit dem Modulnamen (z.B. 'kubernetes') oder 'none'.",
            f"Message: \"{message}\"\n\n"
            f"Available modules:\n{module_descriptions}\n\n"
            "Which module should handle this message? "
            "Respond ONLY with the module name (e.g. 'kubernetes') or 'none'.",
        )

        try:
            result = await asyncio.wait_for(
                self._llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]),
                timeout=_timeout,
            )
            raw = result.content.strip() if hasattr(result, "content") else str(result).strip()
            # Thinking-Tags entfernen (Qwen3.5 etc.)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            # Nur erste Zeile / erstes Wort nehmen; Sonderzeichen entfernen
            candidate = raw.split("\n")[0].split()[0].lower().strip('"`\'.,!?:') if raw else "none"

            module: str | None = candidate if candidate in available_names else None
            _llm_routing_cache[msg_hash] = (module, now)
            logger.info(
                "LLM-Routing: '%s…' → '%s' (Methode: llm)",
                message[:60], module,
            )
            return module

        except asyncio.TimeoutError:
            logger.warning(
                "LLM-Routing: Timeout nach %.0fs für '%s…' – Fallback auf Keyword-Matching",
                _timeout, message[:60],
            )
        except Exception as exc:
            logger.warning(
                "LLM-Routing: Fehler '%s' für '%s…' – Fallback auf Keyword-Matching",
                exc, message[:60],
            )
        return None

    # ──────────────────────────────────────────────────────────────────────
    # Tier-Klassifikation
    # ──────────────────────────────────────────────────────────────────────

    def _is_simple_query(self, message: str, cfg: RoutingConfig | None = None) -> bool:
        """
        Stufe 1: Erkennt einfache Fragen / Konversation, die direkt
        beantwortet werden können (ohne Agent-Overhead).
        Kurze Nachrichten ohne operative Action-Verben.
        """
        max_chars = cfg.simple_query_max_chars if cfg else 120
        if len(message) > max_chars:
            return False
        msg_lower = message.lower()
        if any(re.search(rf'\b{re.escape(v)}\b', msg_lower) for v in _ACTION_VERBS):
            return False
        return True

    @staticmethod
    def _has_workflow_intent(message: str) -> bool:
        """
        Erkennt ob der User einen Workflow erstellen/bearbeiten möchte (DE + EN).
        Solche Requests müssen zum Orchestrator (Tier 1), der das
        create_linear_workflow-Tool hat – nicht zum dynamischen Agenten.
        """
        msg_lower = message.lower()
        return bool(re.search(
            r"(?:erstell|erzeug|generier|mach|bau|anleg|create|build|make|set\s*up|generate).{0,15}workflow|"
            r"workflow.{0,15}(?:erstell|erzeug|generier|mach|bau|anleg|create|build|make|set\s*up|generate)",
            msg_lower
        ))

    def _has_multistep_indicators(self, message: str) -> bool:
        """
        Stufe 4: Erkennt explizit mehrstufige Aufgaben anhand von
        Sprach-Mustern (erst … dann, Schritt 1 … Schritt 2, etc.).
        """
        msg_lower = message.lower()
        return any(p.search(msg_lower) for p in _MULTISTEP_PATTERNS)

    @staticmethod
    def _strip_bot_context(message: str) -> str:
        """Entfernt Bot-Kontext-Präfixe vor dem Keyword-Routing (z. B. '[Telegram Chat-ID: 123]').
        Das LLM erhält weiterhin den vollen Text — nur die Routing-Erkennung nutzt den bereinigten Text."""
        return re.sub(r'^\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?', '', message).strip()

    async def _classify_tier(
        self,
        message: str,
        chat_history: list[dict] | None,
        cfg: RoutingConfig | None = None,
    ) -> tuple[int, str | None, bool]:
        """
        Klassifiziert eine Anfrage in Tier 1–4.

        Returns:
            (tier, target_module_or_None, is_compound)
            - tier 1: Direkt beantworten
            - tier 2: An Modul-Agent delegieren  (target_module gesetzt)
            - tier 3: Dynamischer Agent
            - tier 4: Workflow-Orchestrierung    (is_compound oder multistep)
        """
        if cfg is None:
            cfg = RoutingConfig()

        # Kontext-Präfixe (Telegram/Teams) vor dem Routing entfernen,
        # damit z. B. "[Telegram Chat-ID: 123]" nicht das telegram-Modul triggert.
        routing_message = self._strip_bot_context(message)
        target_module, is_compound = await self._detect_module(routing_message, chat_history, cfg)

        # Tier 4: Compound (multi-modul) oder explizit mehrstufig
        if cfg.tier4_enabled and (is_compound or (cfg.multistep_detection_enabled and self._has_multistep_indicators(routing_message))):
            return 4, None, True

        # Tier 2: Modul erkannt
        if cfg.tier2_enabled and target_module:
            return 2, target_module, False

        # Tier 1: Einfache Direktfrage
        if cfg.tier1_enabled and self._is_simple_query(routing_message, cfg):
            return 1, None, False

        # Workflow-Erstellung → Orchestrator mit Core-Tools (Tier 1),
        # NICHT zum dynamischen Agenten (Tier 3) der kein create_linear_workflow hat
        if self._has_workflow_intent(routing_message):
            return 1, None, False

        # Tier 3: Komplex, aber kein passendes Modul → dynamischer Agent
        if cfg.tier3_enabled:
            return 3, None, False

        # Tier 3 deaktiviert → Fallback auf direkte LLM-Antwort
        return 1, None, False

    async def _detect_module(self, message: str, chat_history: list[dict] | None = None, cfg: RoutingConfig | None = None) -> tuple[str | None, bool]:
        """
        Erkennt welches Modul zuständig ist — zweistufig:
        1. Keyword-Matching (Schnellpfad, kein LLM-Call)
        2. LLM-Klassifikation (nur bei Score=0 oder Ambiguität)

        Logging zeigt welche Methode geroutet hat: keyword / llm / fallback.
        """
        # --- CORE OVERRIDES ---
        # Wenn der User explizit nach Core-Features fragt, leiten wir NICHT an Submodule weiter!
        core_patterns = [
            # DE + EN: Workflow, Agent, CLI, System
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

        # --- STUFE 1: KEYWORD-MATCHING (Schnellpfad) ---
        def get_scores(text: str) -> dict[str, int]:
            text_lower = text.lower()
            text_compact = re.sub(r'[\W_]+', '', text_lower)
            scores: dict[str, int] = {}

            for keyword, module_name in self._routing_map.items():
                kw_lower = keyword.lower()
                kw_compact = re.sub(r'[\W_]+', '', kw_lower)
                matches = 0

                kw_pattern = r'\b' + re.escape(kw_lower) + r'\b'
                matches += len(re.findall(kw_pattern, text_lower))

                if len(kw_compact) >= 7 and matches == 0:
                    if kw_compact in text_compact:
                        matches += 1

                weight = 1
                # Keyword entspricht direkt dem Modulnamen → drastisch höher gewichten
                if kw_lower in [module_name.lower(), module_name.lower().replace("-", "")]:
                    weight = 5

                if matches > 0:
                    scores[module_name] = scores.get(module_name, 0) + (matches * weight)
            return scores

        module_scores = get_scores(message)

        # Wenn keine Treffer in aktueller Nachricht (z. B. "ja", "weiter"), prüfe Historie
        if not module_scores and chat_history:
            history_text = " ".join([m.get("content", "") for m in chat_history[-3:]])
            module_scores = get_scores(history_text)

        # Schnellpfad: genau ein Modul eindeutig erkannt → direkt zurück, kein LLM nötig
        if len(module_scores) == 1:
            best = next(iter(module_scores))
            logger.info(
                "Routing per Keyword (eindeutig): '%s' (Score: %d, Methode: keyword)",
                best, module_scores[best],
            )
            return best, False

        # --- STUFE 2: LLM-KLASSIFIKATION (bei Score=0 oder Ambiguität) ---
        if not module_scores:
            # Kein Keyword-Treffer → LLM könnte semantisch matchen
            if cfg and not cfg.llm_routing_enabled:
                logger.info("LLM-Routing deaktiviert → kein Modul erkannt für: '%s…'", message[:60])
                return None, False
            logger.info("Kein Keyword-Treffer → LLM-Klassifikation für: '%s…'", message[:60])
            llm_module = await self._llm_classify_module(
                message,
                timeout=cfg.llm_routing_timeout if cfg else None,
                cache_ttl=cfg.llm_routing_cache_ttl if cfg else None,
            )
            if llm_module:
                return llm_module, False
            return None, False

        # Mehrere Module erkannt → Ambiguität → LLM entscheidet: einzelnes Modul oder Compound?
        if cfg and not cfg.llm_routing_enabled:
            # Keyword-Ambiguität ohne LLM → bestes Keyword-Ergebnis nehmen
            logger.info("LLM-Routing deaktiviert bei Ambiguität → nehme Keyword-Spitzenreiter für: '%s…'", message[:60])
            sorted_m = sorted(module_scores.items(), key=lambda x: x[1], reverse=True)
            return sorted_m[0][0], False
        logger.info(
            "Keyword-Ambiguität (%s) → LLM-Klassifikation für: '%s…'",
            module_scores, message[:60],
        )
        llm_module = await self._llm_classify_module(
            message,
            timeout=cfg.llm_routing_timeout if cfg else None,
            cache_ttl=cfg.llm_routing_cache_ttl if cfg else None,
        )
        if llm_module:
            # LLM hat eindeutig ein Modul identifiziert → kein Compound
            return llm_module, False

        # LLM-Fallback: altes Keyword-Verhalten — Compound-Signal prüfen
        # Compound nur wenn zweites Modul mindestens 40% des ersten Scores hat UND Score >= 2.
        # Verhindert Fehlklassifikation wenn ein Modul klar dominiert (z.B. kubernetes:10, linux_server:1).
        sorted_modules = sorted(module_scores.items(), key=lambda x: x[1], reverse=True)
        if (
            len(sorted_modules) > 1
            and sorted_modules[1][1] >= 2
            and sorted_modules[1][1] >= sorted_modules[0][1] * 0.4
        ):
            logger.info(
                "Compound-Anfrage erkannt (LLM+Keyword Fallback): %s", module_scores,
            )
            return None, True  # Orchestrator-LLM übernimmt

        best_module = sorted_modules[0][0]
        logger.info(
            "Routing per Keyword (Fallback): '%s' (Score: %d, Scores: %s, Methode: fallback)",
            best_module, module_scores[best_module], module_scores,
        )
        return best_module, False

    async def _plan_and_execute_pipeline(
        self,
        message: str,
        chat_history: list[dict] | None,
        session_id: str = "",
    ) -> tuple[str, bool]:
        """
        Deterministisches Compound-Routing ohne ReAct-Loop:
        1. Einmaliger strukturierter LLM-Call → Pipeline-Steps als JSON
        2. Deterministische Ausführung via run_pipeline (kein weiteres LLM-Sequencing)

        Verhindert, dass der Orchestrator Rückfragen stellt statt zu handeln.
        """
        available = [m.name for m in self.registry.list_modules()]
        modules_str = ", ".join(available)

        # Chatverlauf als Kontext einbetten (letzten 3 Nachrichten)
        history_context = ""
        if chat_history:
            recent = chat_history[-3:]
            history_context = "\n".join(
                f"{'User' if m.get('role') == 'user' else 'Assistent'}: {m.get('content', '')[:200]}"
                for m in recent
            )
            history_context = f"\n\nBisheriger Gesprächskontext:\n{history_context}"

        planning_prompt = _t(
            f"Aufgabe des Benutzers:\n\"{message}\"{history_context}\n\n"
            f"Verfügbare Module: {modules_str}\n\n"
            "Erstelle eine minimale Pipeline-Schrittliste. Wichtige Regeln:\n"
            "- Nur Module einbeziehen, die für diese Aufgabe DIREKT notwendig sind\n"
            "- Wenn EIN Modul ausreicht, genau 1 Schritt zurückgeben\n"
            "- Maximal 3 Schritte außer bei sehr komplexen Aufgaben\n"
            "- Kein web_search, kein image_gen, kein telegram, kein teams sofern nicht explizit gefordert\n"
            "Antwort AUSSCHLIESSLICH als JSON-Array ohne weiteren Text:\n"
            "[{\"module\": \"<modul_name>\", \"task\": \"<präzise, vollständige Aufgabe für dieses Modul>\"}, ...]",
            f"User task:\n\"{message}\"{history_context}\n\n"
            f"Available modules: {modules_str}\n\n"
            "Create a minimal pipeline step list. Important rules:\n"
            "- Only include modules that are DIRECTLY needed for this task\n"
            "- If ONE module is sufficient, return exactly 1 step\n"
            "- Maximum 3 steps except for very complex tasks\n"
            "- Do not include web_search, image_gen, telegram, or teams unless explicitly requested\n"
            "Respond EXCLUSIVELY as a JSON array without any other text:\n"
            "[{\"module\": \"<module_name>\", \"task\": \"<precise, complete task for this module>\"}, ...]",
        )

        try:
            result = await self._llm.ainvoke([HumanMessage(content=planning_prompt)])
            raw = (
                result.content.strip()
                if hasattr(result, "content")
                else str(result).strip()
            )

            # JSON aus Markdown-Codeblöcken oder reinem Text extrahieren
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                steps = _json.loads(match.group(0))
                valid = (
                    isinstance(steps, list)
                    and len(steps) >= 1
                    and all(
                        isinstance(s, dict) and "module" in s and "task" in s
                        for s in steps
                    )
                )
                if valid:
                    logger.info(
                        "Compound-Routing: Pipeline-Steps geplant (%d Schritte): %s",
                        len(steps),
                        [(s["module"], s["task"][:50]) for s in steps],
                    )
                    return await run_pipeline.ainvoke({"steps": steps}), False

            logger.warning(
                "Pipeline-Planung lieferte kein valides JSON: %s…", raw[:200]
            )
        except Exception as exc:
            logger.warning(
                "Pipeline-Planung fehlgeschlagen: %s – Fallback auf invoke()", exc
            )

        # Fallback: voller ReAct-Loop (kann Rückfragen stellen)
        response, did_compact = await self.invoke(message=message, chat_history=chat_history, session_id=session_id)
        return response, did_compact

    async def _route_tier3(
        self,
        message: str,
        chat_history: list[dict] | None,
        session_id: str,
        confirmed: bool = False,
    ) -> tuple[str, str | None, bool]:
        """
        Stufe 3 – Dynamischer Agent:
        Sucht einen passenden dynamischen Agenten oder erstellt einen neuen,
        der exakt auf diese Aufgabe zugeschnitten ist. Persistiert den Agenten
        im DynamicAgentPool für spätere Wiederverwendung.
        """
        from core.agent_pool import get_agent_pool

        pool = get_agent_pool()
        await status_bus.emit(session_id, _t("Suche passenden Spezial-Agenten…", "Searching for matching specialist agent…"))

        # 1. Vorhandenen dynamischen Agenten suchen
        agent, agent_name = pool.find_best_match(message)
        if agent:
            logger.info("Stufe 3: Vorhandener dynamischer Agent '%s' gefunden.", agent_name)
            await status_bus.emit(session_id, f"Delegiere an {agent_name}…")
            response, did_compact = await agent.invoke(
                message=message, chat_history=chat_history, session_id=session_id,
                confirmed=confirmed,
            )
            return response, f"dynamic:{agent_name}", did_compact

        # 2. Neuen spezialisierten Agenten via LLM generieren
        await status_bus.emit(session_id, _t("Erstelle spezialisierten Agenten…", "Creating specialized agent…"))
        logger.info("Stufe 3: Erstelle neuen dynamischen Agenten für: %s…", message[:80])

        spec_prompt = _t(
            f"Analysiere diese Aufgabe: \"{message}\"\n\n"
            "Erstelle einen spezialisierten Agenten-Profil dafür. Antworte NUR als JSON ohne weiteren Text:\n"
            "{\n"
            "  \"name\": \"<kurzer prägnanter Agent-Name, 2-4 Wörter>\",\n"
            "  \"description\": \"<1 Satz: was dieser Agent kann>\",\n"
            "  \"system_prompt\": \"<Spezialisierter System-Prompt, 3-5 Sätze auf Deutsch>\"\n"
            "}",
            f"Analyze this task: \"{message}\"\n\n"
            "Create a specialized agent profile for it. Respond ONLY as JSON without any other text:\n"
            "{\n"
            "  \"name\": \"<short concise agent name, 2-4 words>\",\n"
            "  \"description\": \"<1 sentence: what this agent can do>\",\n"
            "  \"system_prompt\": \"<Specialized system prompt, 3-5 sentences in English>\"\n"
            "}",
        )

        try:
            result = await self._llm.ainvoke([HumanMessage(content=spec_prompt)])
            raw = result.content.strip() if hasattr(result, "content") else str(result).strip()

            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                spec = _json.loads(match.group(0))
                agent_id, agent = await pool.register(
                    name=spec.get("name", "Dynamischer Agent"),
                    system_prompt=spec.get("system_prompt", "Du bist ein spezialisierter Assistent."),
                    description=spec.get("description", ""),
                )
                agent_label = spec.get("name", "Dynamischer Agent")
                logger.info(
                    "Stufe 3: Neuer Agent '%s' erstellt (id=%s) – wird sofort für Aufgabe eingesetzt.",
                    agent_label, agent_id,
                )
                await status_bus.emit(session_id, f"Delegiere an {agent_label}…")
                response, did_compact = await agent.invoke(
                    message=message, chat_history=chat_history, session_id=session_id,
                    confirmed=confirmed,
                )
                return response, f"dynamic:{agent_label}", did_compact

        except Exception as exc:
            logger.warning(
                "Stufe 3: Agenten-Erstellung fehlgeschlagen (%s) – Fallback auf direkte Antwort.", exc
            )

        # Fallback: direkte LLM-Antwort
        logger.info("Stufe 3 Fallback → direkte LLM-Antwort.")
        response, did_compact = await self.invoke(
            message=message, chat_history=chat_history, session_id=session_id,
            confirmed=confirmed,
        )
        return response, None, did_compact

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
        4-stufiges Hauptrouting:

        Stufe 1 – Direkte Ausführung:     Einfache Fragen direkt beantworten.
        Stufe 2 – Modul-Delegation:       Spezialisierte Modul-Agenten einsetzen.
        Stufe 3 – Dynamischer Agent:      Neuen Agenten erstellen / wiederverwenden.
        Stufe 4 – Workflow-Orchestrierung: Mehrstufige Aufgaben deterministisch planen.

        Returns:
            tuple[str, str | None, bool]: (Antwort, Modul/Agent oder None, did_compact)
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

        tier, target_module, is_compound = await self._classify_tier(message, chat_history, cfg)
        self._last_tier_used = tier
        self._update_session_stats(session_id, tier, target_module)
        logger.info("Routing-Stufe %d gewählt für: %s…", tier, message[:80])

        # ── Stufe 4: Workflow-Orchestrierung ─────────────────────────────
        if tier == 4:
            await status_bus.emit(session_id, _t("Plane mehrstufige Aufgabe…", "Planning multi-step task…"))
            response, did_compact = await self._plan_and_execute_pipeline(message, chat_history, session_id)
            return response, None, did_compact

        # ── Stufe 2: Modul-Agent ─────────────────────────────────────────
        if tier == 2 and target_module:
            agent = self.registry.get_agent(target_module)
            if agent is not None:
                manifests = {m.name: m for m in self.registry.list_modules()}
                display = manifests.get(
                    target_module, type("", (), {"display_name": target_module})()
                ).display_name
                await status_bus.emit(session_id, f"Rufe {display} auf…")
                logger.info("Stufe 2: Routing an Modul '%s': %s…", target_module, message[:80])
                try:
                    response, did_compact = await agent.invoke(
                        message=message,
                        chat_history=chat_history,
                        session_id=session_id,
                        confirmed=confirmed,
                    )
                    return response, target_module, did_compact
                except Exception as exc:
                    logger.error("Stufe 2: Modul '%s' Fehler: %s", target_module, exc, exc_info=True)
                    return (
                        _t(
                            f"Fehler: Modul '{target_module}' hat einen Fehler gemeldet: {exc}.",
                            f"Error: Module '{target_module}' reported an error: {exc}.",
                        ),
                        target_module,
                        False,
                    )
            else:
                logger.warning("Modul '%s' hat keinen registrierten Agent.", target_module)

        # ── Stufe 1: Direkte LLM-Antwort ────────────────────────────────
        if tier == 1:
            logger.info("Stufe 1: Direkte LLM-Antwort: %s…", message[:80])
            response, did_compact = await self.invoke(
                message=message, chat_history=chat_history, session_id=session_id,
                confirmed=confirmed,
            )
            return response, None, did_compact

        # ── Stufe 3: Dynamischer Agent ───────────────────────────────────
        logger.info("Stufe 3: Dynamischer Agent für: %s…", message[:80])
        return await self._route_tier3(message, chat_history, session_id, confirmed=confirmed)


# ── Globaler Singleton (gesetzt von main.py) ─────────────────────────────────
_global_orchestrator: "OrchestratorAgent | None" = None


def get_orchestrator() -> "OrchestratorAgent | None":
    """Gibt die globale Orchestrator-Instanz zurück (nach App-Start verfügbar)."""
    return _global_orchestrator


def set_orchestrator(orchestrator: "OrchestratorAgent") -> None:
    """Wird von main.py nach Erstellung des Orchestrators aufgerufen."""
    global _global_orchestrator
    _global_orchestrator = orchestrator
