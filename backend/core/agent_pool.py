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
from collections import OrderedDict
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
# Namen von Built-in-Agenten. Ein Custom-Agent mit einem dieser Namen würde beim
# name-gekeyten `save_soul(name, ...)` die Built-in-Soul zur Laufzeit überschreiben
# (Prompt-Injection in Core-Agenten) — daher bei der Registrierung blockieren.
_RESERVED_AGENT_NAMES = frozenset({"orchestrator", "monitor", "scheduler"})
# Infra-Module, für die ein dynamischer Agent rohen CLI-Zugriff bekommen darf.
_CLI_CAPABLE_MODULES = frozenset({"linux_server", "docker", "kubernetes", "proxmox"})
# Obergrenze für user-definierte System-Prompts (verhindert Kontext-/Speicher-Missbrauch).
_MAX_SYSTEM_PROMPT_CHARS = 20000

# Prozessweiter Lock für Read-Modify-Write auf den Agenten-Redis-Keys
# (ninko:agents:<tenant>). Wird von Pool UND Agents-API genutzt, damit parallele
# Writes (register vs. API create/update/delete) sich nicht gegenseitig überschreiben.
_AGENTS_REDIS_LOCK = asyncio.Lock()


def get_agents_redis_lock() -> asyncio.Lock:
    """Gemeinsamer Lock für alle Writer der Agenten-Liste (Pool + API)."""
    return _AGENTS_REDIS_LOCK


class DynamicAgentPool:
    """
    Pool für dynamisch erstellte Agenten.

    Workflow:
    1. Beim App-Start: alle gespeicherten Custom-Agenten aus Redis laden
       und als BaseAgent-Instanzen im Speicher halten.
    2. `register(...)` persistiert einen neuen Agenten in Redis UND erstellt
       sofort eine Live-Instanz. Zugriff zur Laufzeit über `get_agent_by_id`.

    Hinweis: `find_best_match` + der Token-Index sind derzeit NICHT im route()-Pfad
    verdrahtet (Routing ist Function-Calling-only). Sie bleiben als Keyword-Matching-
    Baustein erhalten, falls Keyword-Routing wieder aktiviert wird.
    """

    def __init__(self) -> None:
        # In-Memory: agent_id → BaseAgent instance
        self._live_agents: OrderedDict[str, "BaseAgent"] = OrderedDict()
        # Metadaten-Cache: agent_id → dict  (name, description, ...)
        self._meta: OrderedDict[str, dict] = OrderedDict()
        # Vorgehashter Suchraum pro Agent für schnelles Matching
        self._search_terms: dict[str, set[str]] = {}
        # Inverted-Index: token -> scoped agent ids
        self._token_index: dict[str, set[str]] = {}
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

            # Legacy-Key (ohne Tenant) einmalig in den Tenant-Key "default"
            # migrieren und danach löschen. Sonst bleiben Legacy-Agenten live und
            # routbar, sind aber über die API (die nur ninko:agents:default nutzt)
            # weder aktualisier- noch löschbar (Ghost-Agenten).
            await self._migrate_legacy_key(redis)

            # Tenant-scoped Keys laden. scan_iter statt KEYS, damit Redis bei
            # großen Keyspaces nicht blockiert wird.
            async for key in redis.connection.scan_iter(match=f"{REDIS_KEY}:*", count=100):
                tenant = _tenant_from_key(key)
                if not tenant:
                    continue
                loaded += await _load_for_tenant(tenant, key)
            logger.info("DynamicAgentPool: %d Agenten geladen.", loaded)
        except _AGENT_POOL_EXCEPTIONS as exc:
            logger.warning("DynamicAgentPool.load_from_redis fehlgeschlagen: %s", exc)

    @staticmethod
    async def _migrate_legacy_key(redis) -> None:
        """Migriert den Legacy-Key `ninko:agents` einmalig nach `ninko:agents:default`.

        Legacy-Agenten (ohne Tenant-Suffix) werden nur beim id-Match NICHT überschrieben
        — der bereits vorhandene default-Eintrag hat Vorrang. Danach wird der Legacy-Key
        gelöscht, damit er nicht bei jedem Neustart erneut auftaucht.
        """
        raw_legacy = await redis.connection.get(REDIS_KEY)
        if not raw_legacy:
            return
        try:
            legacy_agents = json.loads(raw_legacy) or []
        except json.JSONDecodeError:
            legacy_agents = []
        if not legacy_agents:
            await redis.connection.delete(REDIS_KEY)
            return

        default_key = _tenant_key("default")
        raw_default = await redis.connection.get(default_key)
        try:
            default_agents = json.loads(raw_default) if raw_default else []
        except json.JSONDecodeError:
            default_agents = []

        existing_ids = {a.get("id") for a in default_agents}
        migrated = 0
        for agent_def in legacy_agents:
            if agent_def.get("id") not in existing_ids:
                default_agents.append(agent_def)
                migrated += 1

        await redis.connection.set(default_key, json.dumps(default_agents))
        await redis.connection.delete(REDIS_KEY)
        logger.info(
            "DynamicAgentPool: Legacy-Key '%s' migriert (%d neue Agenten → '%s') und gelöscht.",
            REDIS_KEY,
            migrated,
            default_key,
        )

    @staticmethod
    def _get_dynamic_tools(agent_def: dict | None = None) -> list:
        """Basis-Tools für dynamische Agenten.

        `execute_cli_command` wird NICHT mehr pauschal vergeben (user-definierter,
        unvalidierter System-Prompt + rohe Shell = zu mächtig). Es gibt es nur für
        Agenten, die explizit auf ein Infra-Modul gescoped sind; alle anderen
        delegieren über `call_module_agent` an Module (die eigene Tools + Safeguard haben).
        """
        from agents.core_tools import (
            execute_cli_command,
            call_module_agent,
            recall_memory,
            remember_fact,
        )

        tools = [call_module_agent, recall_memory, remember_fact]
        module_names = set((agent_def or {}).get("module_names", []) or [])
        if module_names & _CLI_CAPABLE_MODULES:
            tools.insert(0, execute_cli_command)

        script_tool_names = set((agent_def or {}).get("script_tool_names", []) or [])
        if script_tool_names:
            from agents.script_tools import make_scoped_script_tools

            tools.extend(make_scoped_script_tools(frozenset(script_tool_names)))

        return tools

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

        # LRU-Eviction: Wenn die Zahl der LIVE-Instanzen das Limit erreicht, die am
        # längsten ungenutzte Live-Instanz entladen. Metadaten (_meta) und Such-Index
        # bleiben erhalten — sonst wäre der Agent danach weder routbar noch per
        # get_agent_by_id auffindbar (Scheduler-Tasks würden dauerhaft scheitern).
        # Bei erneutem Zugriff wird die Instanz aus _meta rehydriert.
        if (
            scoped_id not in self._live_agents
            and len(self._live_agents) >= _AGENT_POOL_MAX
        ):
            evicted_id, _ = self._live_agents.popitem(last=False)
            logger.info(
                "DynamicAgentPool: LRU-Eviction: Live-Instanz '%s' entladen "
                "(Meta bleibt, Live-Limit %d)",
                evicted_id,
                _AGENT_POOL_MAX,
            )

        agent = BaseAgent(
            name=normalized_def["name"],
            system_prompt=normalized_def["system_prompt"],
            tools=self._get_dynamic_tools(normalized_def),
        )
        self._remove_index(scoped_id)
        self._live_agents[scoped_id] = agent
        self._meta[scoped_id] = normalized_def
        self._index_agent(scoped_id, normalized_def)
        self._mark_used(scoped_id)
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

    async def _close_live_agent(self, scoped_id: str) -> None:
        """Close and remove a live agent instance plus its search metadata."""
        old_agent = self._live_agents.pop(scoped_id, None)
        self._meta.pop(scoped_id, None)
        self._remove_index(scoped_id)
        if old_agent and hasattr(old_agent, "aclose"):
            try:
                await old_agent.aclose()
            except _AGENT_POOL_EXCEPTIONS as exc:
                logger.debug(
                    "Agent '%s' konnte nicht sauber geschlossen werden: %s",
                    scoped_id,
                    exc,
                )

    def _rehydrate(self, scoped_id: str) -> "BaseAgent | None":
        """Gibt die Live-Instanz zurück; re-instanziiert sie aus _meta falls evicted.

        Ermöglicht, dass ein per LRU entladener Agent bei Zugriff transparent
        wiederhergestellt wird (statt dauerhaft zu verschwinden).
        """
        agent = self._live_agents.get(scoped_id)
        if agent is not None:
            self._mark_used(scoped_id)
            return agent
        meta = self._meta.get(scoped_id)
        if meta is None:
            return None
        try:
            return self._instantiate(meta)
        except _AGENT_POOL_EXCEPTIONS as exc:
            logger.warning(
                "Rehydrierung von Agent '%s' fehlgeschlagen: %s", scoped_id, exc
            )
            return None

    def _mark_used(self, scoped_id: str) -> None:
        """Markiert einen Agenten als zuletzt verwendet, damit die Eviction echtes LRU bleibt."""
        if scoped_id in self._live_agents:
            self._live_agents.move_to_end(scoped_id)
        if scoped_id in self._meta:
            self._meta.move_to_end(scoped_id)

    def _index_agent(self, scoped_id: str, meta: dict) -> None:
        """Baut den invertierten Token-Index für einen Agenten auf."""
        search_text = " ".join(
            [
                meta.get("name", ""),
                meta.get("description", ""),
                meta.get("system_prompt", "")[:300],
            ]
        )
        search_words = set(_tokenize(search_text))
        self._search_terms[scoped_id] = search_words
        for token in search_words:
            self._token_index.setdefault(token, set()).add(scoped_id)

    def _remove_index(self, scoped_id: str) -> None:
        """Entfernt einen Agenten aus dem invertierten Token-Index."""
        old_terms = self._search_terms.pop(scoped_id, None)
        if not old_terms:
            return
        for token in old_terms:
            scoped_ids = self._token_index.get(token)
            if not scoped_ids:
                continue
            scoped_ids.discard(scoped_id)
            if not scoped_ids:
                self._token_index.pop(token, None)

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
        if not self._meta:
            return None, ""

        task_words = set(_tokenize(task))
        if not task_words:
            return None, ""

        best_id: str | None = None
        best_score = 0.0
        tenant = _effective_tenant_id()
        candidate_ids: set[str] = set()

        for task_word in task_words:
            candidate_ids.update(self._token_index.get(task_word, ()))

        if not candidate_ids:
            return None, ""

        for agent_id in candidate_ids:
            meta = self._meta.get(agent_id)
            if not meta:
                continue
            if not meta.get("enabled", True):
                continue
            if _normalize_tenant(meta.get("tenant_id", "default")) != tenant:
                continue

            search_words = self._search_terms.get(agent_id, set())
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
            agent = self._rehydrate(best_id)
            if agent is not None:
                return agent, agent_name

        return None, ""

    def get_agent_by_id(
        self, agent_id: str, *, allow_cross_tenant: bool = False
    ) -> tuple["BaseAgent | None", str]:
        """Gibt einen Agenten anhand seiner ID zurück, oder (None, '') wenn nicht gefunden.

        allow_cross_tenant: Nur für vertrauenswürdige System-Kontexte ohne Session
            (z.B. Scheduler). Erlaubt den tenant-übergreifenden endswith-Fallback.
            Für user-facing Pfade (Chat/force_module) IMMER False → Tenant-Isolation.
        """
        tenant = _effective_tenant_id()
        scoped = _scoped_id(tenant, agent_id)

        if scoped in self._meta:
            name = self._meta.get(scoped, {}).get("name", agent_id)
            agent = self._rehydrate(scoped)
            if agent is not None:
                logger.debug("get_agent_by_id: Gefunden mit scoped_id, name='%s'", name)
                return agent, name

        # Tenant-übergreifender Fallback nur für System-Kontexte. Sonst könnte ein
        # User per bekannter fremder UUID einen Agenten eines anderen Tenants aufrufen.
        if allow_cross_tenant:
            for sid in list(self._meta.keys()):
                if sid.endswith(f":{agent_id}"):
                    name = self._meta.get(sid, {}).get("name", agent_id)
                    agent = self._rehydrate(sid)
                    if agent is not None:
                        logger.debug(
                            "get_agent_by_id: Gefunden mit System-Fallback, name='%s'", name
                        )
                        return agent, name

        logger.warning(
            "get_agent_by_id: NICHT GEFUNDEN agent_id='%s', tenant='%s'",
            agent_id,
            tenant,
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

        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Agent-Name darf nicht leer sein.")
        if clean_name.casefold() in _RESERVED_AGENT_NAMES:
            raise ValueError(
                f"Agent-Name '{clean_name}' ist reserviert (Built-in-Agent) "
                "und kann nicht für einen Custom-Agenten verwendet werden."
            )
        name = clean_name

        if len(system_prompt or "") > _MAX_SYSTEM_PROMPT_CHARS:
            raise ValueError(
                f"System-Prompt zu lang ({len(system_prompt)} Zeichen, "
                f"max. {_MAX_SYSTEM_PROMPT_CHARS})."
            )

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

        async with self._register_lock, _AGENTS_REDIS_LOCK:
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

    async def sync_agent(self, agent_def: dict) -> None:
        """
        Synchronisiert einen bereits persistierten Agenten in den Live-Pool.

        Wird von der Agents-API genutzt, damit UI/REST-erstellte oder aktualisierte
        Agenten ohne Backend-Neustart direkt routbar sind.
        """
        tenant = _normalize_tenant(agent_def.get("tenant_id", "default"))
        agent_id = str(agent_def.get("id", "")).strip()
        if not agent_id:
            raise ValueError("Agent-ID fehlt")

        scoped_id = _scoped_id(tenant, agent_id)
        if not agent_def.get("enabled", True) or not agent_def.get("system_prompt"):
            # Auch der Disable-Pfad muss unter dem Lock laufen, sonst kann ein
            # paralleles sync_agent/update_agent den Agenten neu instanziieren
            # → Endzustand "live trotz disabled".
            async with self._register_lock:
                await self._close_live_agent(scoped_id)
            return

        normalized_def = {**agent_def, "id": agent_id, "tenant_id": tenant}
        async with self._register_lock:
            await self._close_live_agent(scoped_id)
            self._instantiate(normalized_def)

    async def remove_agent(self, agent_id: str, tenant_id: str = "") -> bool:
        """Entfernt einen Agenten aus dem Live-Pool."""
        tenant = _effective_tenant_id(tenant_id)
        scoped_id = _scoped_id(tenant, agent_id)
        if scoped_id not in self._live_agents and scoped_id not in self._meta:
            return False
        async with self._register_lock:
            await self._close_live_agent(scoped_id)
        return True

    def get_by_id(self, agent_id: str, *, allow_cross_tenant: bool = False) -> "BaseAgent | None":
        """Gibt einen Live-Agenten anhand seiner ID zurück.

        Der Cross-Tenant-Scan läuft nur mit explizitem allow_cross_tenant=True
        (System-Kontexte wie der Scheduler) — analog zu get_agent_by_id.
        """
        tenant = _effective_tenant_id()
        scoped = _scoped_id(tenant, agent_id)
        if scoped in self._meta:
            agent = self._rehydrate(scoped)
            if agent is not None:
                return agent
        if not allow_cross_tenant:
            return None
        for sid in list(self._meta.keys()):
            if sid.endswith(f":{agent_id}"):
                agent = self._rehydrate(sid)
                if agent is not None:
                    return agent
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
            if agents[idx].get("enabled", True) and agents[idx].get("system_prompt"):
                await self._close_live_agent(scoped_id)
                self._instantiate(agents[idx])
            else:
                await self._close_live_agent(scoped_id)

            # Soul MD neu generieren wenn name oder description geändert wurde.
            # Muss unter _register_lock laufen, weil self._meta[scoped_id] sonst
            # von einem parallelen remove_agent entfernt werden kann.
            if name is not None or description is not None:
                try:
                    from core.soul_manager import get_soul_manager

                    sm = get_soul_manager()
                    meta = self._meta.get(scoped_id)
                    if meta is None:
                        logger.debug(
                            "Soul-Update für '%s' übersprungen (Agent nicht im Pool).",
                            agent_id,
                        )
                    else:
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
