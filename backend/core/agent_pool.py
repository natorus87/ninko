"""
Ninko – Dynamischer Agenten-Pool (Stufe 3).
Verwaltet zur Laufzeit erstellte Agenten: persistiert Metadaten in Redis,
hält instanziierte Objekte im Speicher und ermöglicht Wiederverwendung.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.core.agent_pool")

REDIS_KEY = "ninko:agents"
# Minimale Keyword-Übereinstimmung (0–1) damit ein Agent als passend gilt
_MATCH_THRESHOLD = 0.18


class DynamicAgentPool:
    """
    Pool für dynamisch erstellte Agenten.

    Workflow:
    1. Beim App-Start: alle gespeicherten Custom-Agenten aus Redis laden
       und als BaseAgent-Instanzen im Speicher halten.
    2. Bei Stufe-3-Routing: `find_best_match(task)` prüft, ob ein
       bereits vorhandener Agent zur Aufgabe passt.
    3. Bei Neuanforderung: `register(...)` persistiert den Agenten in Redis
       UND erstellt sofort eine Live-Instanz.
    """

    def __init__(self) -> None:
        # In-Memory: agent_id → BaseAgent instance
        self._live_agents: dict[str, "BaseAgent"] = {}
        # Metadaten-Cache: agent_id → dict  (name, description, ...)
        self._meta: dict[str, dict] = {}
        # Verhindert Race Condition bei gleichzeitigen register()-Aufrufen
        self._register_lock = asyncio.Lock()

    # ──────────────────────────────────────────────────────────────────────
    # Startup / Persistenz
    # ──────────────────────────────────────────────────────────────────────

    async def load_from_redis(self) -> None:
        """
        Lädt alle gespeicherten Agenten aus Redis und instanziiert sie.
        Wird einmalig beim App-Start in main.py aufgerufen.
        """
        try:
            from core.redis_client import get_redis
            redis = get_redis()
            raw = await redis.connection.get(REDIS_KEY)
            if not raw:
                return

            agents = json.loads(raw)
            loaded = 0
            for agent_def in agents:
                if agent_def.get("enabled", True) and agent_def.get("system_prompt"):
                    try:
                        self._instantiate(agent_def)
                        loaded += 1
                    except Exception as exc:
                        logger.warning(
                            "Agent '%s' konnte nicht instanziiert werden: %s",
                            agent_def.get("name"), exc,
                        )
            logger.info("DynamicAgentPool: %d Agenten geladen.", loaded)
        except Exception as exc:
            logger.warning("DynamicAgentPool.load_from_redis fehlgeschlagen: %s", exc)

    @staticmethod
    def _get_dynamic_tools() -> list:
        """Gibt die Basis-Tools zurück, die allen dynamischen Agenten zur Verfügung stehen."""
        from agents.core_tools import execute_cli_command, call_module_agent, recall_memory, remember_fact
        return [execute_cli_command, call_module_agent, recall_memory, remember_fact]

    def _instantiate(self, agent_def: dict) -> "BaseAgent":
        """
        Erstellt eine BaseAgent-Instanz aus einem Agent-Definition-Dict
        und speichert sie im internen Pool.
        """
        from agents.base_agent import BaseAgent

        agent_id = agent_def["id"]
        agent = BaseAgent(
            name=agent_def["name"],
            system_prompt=agent_def["system_prompt"],
            tools=self._get_dynamic_tools(),
        )
        self._live_agents[agent_id] = agent
        self._meta[agent_id] = agent_def
        logger.debug(
            "Dynamischer Agent instanziiert: '%s' (id=%s)",
            agent_def["name"], agent_id,
        )
        return agent

    # ──────────────────────────────────────────────────────────────────────
    # Suche / Matching
    # ──────────────────────────────────────────────────────────────────────

    def find_best_match(self, task: str) -> tuple["BaseAgent | None", str]:
        """
        Sucht den besten passenden Agenten für eine Aufgabe anhand von
        Keyword-Überschneidung (Name, Description, System-Prompt-Anfang).

        Gibt (agent_instance, agent_name) zurück, oder (None, "") wenn
        kein Agent den Mindest-Schwellwert überschreitet.
        """
        if not self._live_agents:
            return None, ""

        task_words = set(_tokenize(task))
        if not task_words:
            return None, ""

        best_id: str | None = None
        best_score = 0.0

        for agent_id, meta in self._meta.items():
            if not meta.get("enabled", True):
                continue

            # Suchraum: Name + Description + erste 300 Zeichen System-Prompt
            search_text = " ".join([
                meta.get("name", ""),
                meta.get("description", ""),
                meta.get("system_prompt", "")[:300],
            ])
            search_words = set(_tokenize(search_text))

            if not search_words:
                continue

            common = task_words & search_words
            score = len(common) / max(len(task_words), 1)

            if score > best_score:
                best_score = score
                best_id = agent_id

        if best_id and best_score >= _MATCH_THRESHOLD:
            agent_name = self._meta[best_id].get("name", best_id)
            logger.debug(
                "DynamicAgentPool: Bester Match '%s' mit Score %.2f",
                agent_name, best_score,
            )
            return self._live_agents[best_id], agent_name

        return None, ""

    def get_agent_by_id(self, agent_id: str) -> tuple["BaseAgent | None", str]:
        """Gibt einen Agenten anhand seiner ID zurück, oder (None, '') wenn nicht gefunden."""
        agent = self._live_agents.get(agent_id)
        name = self._meta.get(agent_id, {}).get("name", agent_id) if agent else ""
        return agent, name

    # ──────────────────────────────────────────────────────────────────────
    # Registrierung
    # ──────────────────────────────────────────────────────────────────────

    async def register(
        self,
        name: str,
        system_prompt: str,
        description: str = "",
    ) -> tuple[str, "BaseAgent"]:
        """
        Registriert einen neuen Agenten:
        - Persistiert Metadaten in Redis (ninko:agents).
        - Erstellt sofort eine Live-Instanz.
        - Gibt (agent_id, agent_instance) zurück.
        """
        import uuid
        from core.redis_client import get_redis

        agent_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        agent_def = {
            "id": agent_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "llm_provider_id": None,
            "module_names": [],
            "steps": [],
            "enabled": True,
            "created_at": now,
            "updated_at": now,
            "dynamic": True,
        }

        async with self._register_lock:
            redis = get_redis()
            raw = await redis.connection.get(REDIS_KEY)
            agents = json.loads(raw) if raw else []
            agents.append(agent_def)
            await redis.connection.set(REDIS_KEY, json.dumps(agents))

        # Soul MD automatisch generieren und persistent speichern
        try:
            from core.soul_manager import get_soul_manager
            sm = get_soul_manager()
            capabilities = _extract_capabilities(system_prompt)
            soul_md = sm.generate_soul(
                name=name,
                purpose=description or f"Spezialisierter Agent für: {name}",
                capabilities=capabilities or None,
            )
            await sm.save_soul(name, soul_md)
            logger.debug("Soul MD für dynamischen Agent '%s' generiert und gespeichert.", name)
        except Exception as exc:
            logger.warning("Soul-Generierung für Agent '%s' fehlgeschlagen: %s", name, exc)

        agent = self._instantiate(agent_def)
        logger.info(
            "DynamicAgentPool: Neuer Agent registriert: '%s' (id=%s)",
            name, agent_id,
        )
        return agent_id, agent

    def get_by_id(self, agent_id: str) -> "BaseAgent | None":
        """Gibt einen Live-Agenten anhand seiner ID zurück."""
        return self._live_agents.get(agent_id)


# ── Hilfsfunktion ────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Zerlegt Text in bereinige Tokens (mind. 3 Zeichen)."""
    words = re.sub(r"[\W_]+", " ", text.lower()).split()
    return [w for w in words if len(w) >= 3]


def _extract_capabilities(system_prompt: str) -> list[str]:
    """
    Extrahiert Fähigkeiten aus einem System-Prompt.
    Sucht nach Aufzählungszeichen (-, *, •) in den ersten 600 Zeichen.
    Gibt maximal 8 Capabilities zurück.
    """
    capabilities: list[str] = []
    for line in system_prompt[:600].splitlines():
        stripped = line.strip()
        if stripped and stripped[0] in "-*•" and len(stripped) > 3:
            cap = stripped.lstrip("-*• ").strip()
            if cap and len(cap) > 5:
                capabilities.append(cap)
    return capabilities[:8]


# ── Globaler Singleton ────────────────────────────────────────────────────

_global_pool: DynamicAgentPool | None = None


def get_agent_pool() -> DynamicAgentPool:
    """Gibt den globalen DynamicAgentPool zurück (ggf. neu erstellen)."""
    global _global_pool
    if _global_pool is None:
        _global_pool = DynamicAgentPool()
    return _global_pool
