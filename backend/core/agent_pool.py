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

_AGENT_POOL_EXCEPTIONS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    RuntimeError,
    json.JSONDecodeError,
)

REDIS_KEY = "ninko:agents"
# Minimale Keyword-Übereinstimmung (0–1) damit ein Agent als passend gilt
_MATCH_THRESHOLD = 0.18
# Maximale Anzahl live-instanziierter Agenten im Pool vor LRU-Eviction
_AGENT_POOL_MAX = 200


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
            loaded = 0

            async def _load_for_tenant(tenant_id: str, key: str) -> int:
                raw = await redis.connection.get(key)
                if not raw:
                    return 0
                tenant_loaded = 0
                agents = json.loads(raw)
                for agent_def in agents:
                    if not agent_def.get("enabled", True) or not agent_def.get(
                        "system_prompt"
                    ):
                        continue
                    try:
                        self._instantiate({**agent_def, "tenant_id": tenant_id})
                        tenant_loaded += 1
                    except _AGENT_POOL_EXCEPTIONS as exc:
                        logger.warning(
                            "Agent '%s' konnte nicht instanziiert werden: %s",
                            agent_def.get("name"),
                            exc,
                        )
                return tenant_loaded

            # Legacy-Key (ohne Tenant) weiterhin unterstützen
            loaded += await _load_for_tenant("default", REDIS_KEY)

            # Tenant-scoped Keys laden
            keys = await redis.connection.keys(f"{REDIS_KEY}:*")
            for key in keys:
                tenant = _tenant_from_key(key)
                if not tenant:
                    continue
                loaded += await _load_for_tenant(tenant, key)
            logger.info("DynamicAgentPool: %d Agenten geladen.", loaded)
        except _AGENT_POOL_EXCEPTIONS as exc:
            logger.warning("DynamicAgentPool.load_from_redis fehlgeschlagen: %s", exc)

    @staticmethod
    def _get_dynamic_tools() -> list:
        """Gibt die Basis-Tools zurück, die allen dynamischen Agenten zur Verfügung stehen."""
        from agents.core_tools import (
            execute_cli_command,
            call_module_agent,
            recall_memory,
            remember_fact,
        )

        return [execute_cli_command, call_module_agent, recall_memory, remember_fact]

    def _instantiate(self, agent_def: dict) -> "BaseAgent":
        """
        Erstellt eine BaseAgent-Instanz aus einem Agent-Definition-Dict
        und speichert sie im internen Pool.
        Implementiert LRU-Eviction wenn der Pool die Größe _AGENT_POOL_MAX überschreitet.
        """
        from agents.base_agent import BaseAgent

        tenant_id = _normalize_tenant(agent_def.get("tenant_id", "default"))
        agent_id = agent_def["id"]
        scoped_id = _scoped_id(tenant_id, agent_id)
        normalized_def = {**agent_def, "tenant_id": tenant_id}

        # LRU-Eviction: Wenn Pool-Größe >= Limit, ältesten Eintrag entfernen
        if (
            scoped_id not in self._live_agents
            and len(self._live_agents) >= _AGENT_POOL_MAX
        ):
            evicted_id = next(iter(self._live_agents))
            evicted_agent = self._live_agents.pop(evicted_id)
            self._meta.pop(evicted_id, None)
            logger.info(
                "DynamicAgentPool: LRU-Eviction: Agent '%s' entfernt (Pool-Limit %d)",
                evicted_id,
                _AGENT_POOL_MAX,
            )

        agent = BaseAgent(
            name=normalized_def["name"],
            system_prompt=normalized_def["system_prompt"],
            tools=self._get_dynamic_tools(),
        )
        self._live_agents[scoped_id] = agent
        self._meta[scoped_id] = normalized_def
        logger.info(
            "Dynamischer Agent instanziiert: '%s' (id=%s, scoped_id=%s, tenant=%s), "
            "Pool-Größe jetzt: %d",
            normalized_def["name"],
            agent_id,
            scoped_id,
            tenant_id,
            len(self._live_agents),
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
        tenant = _effective_tenant_id()

        for agent_id, meta in self._meta.items():
            if not meta.get("enabled", True):
                continue
            if _normalize_tenant(meta.get("tenant_id", "default")) != tenant:
                continue

            # Suchraum: Name + Description + erste 300 Zeichen System-Prompt
            search_text = " ".join(
                [
                    meta.get("name", ""),
                    meta.get("description", ""),
                    meta.get("system_prompt", "")[:300],
                ]
            )
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
                agent_name,
                best_score,
            )
            return self._live_agents[best_id], agent_name

        return None, ""

    def get_agent_by_id(self, agent_id: str) -> tuple["BaseAgent | None", str]:
        """Gibt einen Agenten anhand seiner ID zurück, oder (None, '') wenn nicht gefunden."""
        tenant = _effective_tenant_id()
        scoped = _scoped_id(tenant, agent_id)

        logger.debug(
            "get_agent_by_id: Suche agent_id='%s', tenant='%s', scoped='%s', "
            "verfügbare_live=%d, keys=%s",
            agent_id,
            tenant,
            scoped,
            len(self._live_agents),
            list(self._live_agents.keys()),
        )

        agent = self._live_agents.get(scoped)
        if agent:
            name = self._meta.get(scoped, {}).get("name", agent_id)
            logger.debug("get_agent_by_id: Gefunden mit scoped_id, name='%s'", name)
            return agent, name

        # Fallback: für Legacy-/System-Kontexte nicht tenant-scoped suchen
        for sid, a in self._live_agents.items():
            if sid.endswith(f":{agent_id}"):
                name = self._meta.get(sid, {}).get("name", agent_id)
                logger.debug(
                    "get_agent_by_id: Gefunden mit Fallback endsWith, name='%s'", name
                )
                return a, name

        logger.warning(
            "get_agent_by_id: NICHT GEFUNDEN agent_id='%s', tenant='%s', verfügbare=%s",
            agent_id,
            tenant,
            list(self._live_agents.keys()),
        )
        return None, ""

    # ──────────────────────────────────────────────────────────────────────
    # Registrierung
    # ──────────────────────────────────────────────────────────────────────

    async def register(
        self,
        name: str,
        system_prompt: str,
        description: str = "",
        tenant_id: str = "",
    ) -> tuple[str, "BaseAgent"]:
        """
        Registriert einen neuen Agenten:
        - Persistiert Metadaten in Redis (ninko:agents).
        - Erstellt sofort eine Live-Instanz.
        - Gibt (agent_id, agent_instance) zurück.
        """
        import uuid
        from core.redis_client import get_redis

        tenant = _effective_tenant_id(tenant_id)
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
            "tenant_id": tenant,
        }

        async with self._register_lock:
            redis = get_redis()
            redis_key = _tenant_key(tenant)
            raw = await redis.connection.get(redis_key)
            agents = json.loads(raw) if raw else []
            agents.append(agent_def)
            await redis.connection.set(redis_key, json.dumps(agents))

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
            logger.debug(
                "Soul MD für dynamischen Agent '%s' generiert und gespeichert.", name
            )
        except _AGENT_POOL_EXCEPTIONS as exc:
            logger.warning(
                "Soul-Generierung für Agent '%s' fehlgeschlagen: %s", name, exc
            )

        agent = self._instantiate(agent_def)
        logger.info(
            "DynamicAgentPool: Neuer Agent registriert: '%s' (id=%s)",
            name,
            agent_id,
        )
        return agent_id, agent

    def get_by_id(self, agent_id: str) -> "BaseAgent | None":
        """Gibt einen Live-Agenten anhand seiner ID zurück."""
        tenant = _effective_tenant_id()
        scoped = _scoped_id(tenant, agent_id)
        agent = self._live_agents.get(scoped)
        if agent:
            return agent
        for sid, a in self._live_agents.items():
            if sid.endswith(f":{agent_id}"):
                return a
        return None

    # ──────────────────────────────────────────────────────────────────────
    # Update
    # ──────────────────────────────────────────────────────────────────────

    async def update_agent(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        description: str | None = None,
        tenant_id: str = "",
    ) -> bool:
        """
        Aktualisiert einen bestehenden Agenten in Redis und im Live-Pool.
        Gibt True zurück wenn der Agent gefunden und aktualisiert wurde.
        """
        from core.redis_client import get_redis
        from datetime import datetime, timezone

        tenant = _effective_tenant_id(tenant_id)
        scoped_id = _scoped_id(tenant, agent_id)
        async with self._register_lock:
            redis = get_redis()
            redis_key = _tenant_key(tenant)
            raw = await redis.connection.get(redis_key)
            agents = json.loads(raw) if raw else []

            idx = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)
            if idx is None:
                return False

            if name is not None:
                agents[idx]["name"] = name
            if system_prompt is not None:
                agents[idx]["system_prompt"] = system_prompt
            if description is not None:
                agents[idx]["description"] = description
            agents[idx]["updated_at"] = datetime.now(timezone.utc).isoformat()

            await redis.connection.set(redis_key, json.dumps(agents))

            # Live-Instanz neu erstellen damit der neue Prompt sofort wirkt
            self._meta[scoped_id] = agents[idx]
            if scoped_id in self._live_agents:
                old_agent = self._live_agents[scoped_id]
                try:
                    if hasattr(old_agent, "aclose"):
                        await old_agent.aclose()
                except Exception:
                    pass
                self._instantiate(agents[idx])

        # Soul MD neu generieren wenn name oder description geändert wurde
        if name is not None or description is not None:
            try:
                from core.soul_manager import get_soul_manager

                sm = get_soul_manager()
                meta = self._meta[scoped_id]
                caps = _extract_capabilities(meta.get("system_prompt", ""))
                soul_md = sm.generate_soul(
                    name=meta["name"],
                    purpose=meta.get("description")
                    or f"Spezialisierter Agent für: {meta['name']}",
                    capabilities=caps or None,
                )
                await sm.save_soul(meta["name"], soul_md)
            except _AGENT_POOL_EXCEPTIONS as exc:
                logger.warning(
                    "Soul-Update für Agent '%s' fehlgeschlagen: %s", agent_id, exc
                )

        logger.info("DynamicAgentPool: Agent '%s' aktualisiert.", agent_id)
        return True

    def list_agents(self) -> list[dict]:
        """Gibt alle Agent-Metadaten als Liste zurück."""
        tenant = _effective_tenant_id()
        return [
            m
            for m in self._meta.values()
            if _normalize_tenant(m.get("tenant_id", "default")) == tenant
        ]


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


def _normalize_tenant(tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return t or "default"


def _effective_tenant_id(tenant_id: str = "") -> str:
    if tenant_id:
        return _normalize_tenant(tenant_id)
    try:
        from core import status_bus

        sid = status_bus.get_session_id().strip()
    except _AGENT_POOL_EXCEPTIONS:
        sid = ""
    if ":" in sid:
        return _normalize_tenant(sid.split(":", 1)[0])
    return "default"


def _tenant_key(tenant_id: str) -> str:
    return f"{REDIS_KEY}:{_normalize_tenant(tenant_id)}"


def _tenant_from_key(key: str) -> str:
    raw = (key or "").strip()
    prefix = f"{REDIS_KEY}:"
    if not raw.startswith(prefix):
        return ""
    return _normalize_tenant(raw[len(prefix) :])


def _scoped_id(tenant_id: str, agent_id: str) -> str:
    return f"{_normalize_tenant(tenant_id)}:{agent_id}"
