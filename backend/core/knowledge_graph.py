"""
Ninko Knowledge Graph – NetworkX-basierte Graph-Datenbank für IT-Beziehungen.

Ergänzt das Semantic Memory (ChromaDB) mit strukturierten Entitäten und Beziehungen.
Ermöglicht Graph-Traversal, Pattern-Matching und erweiterte RAG-Queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from core.config import get_settings
from core.memory import get_memory

logger = logging.getLogger("ninko.knowledge_graph")

DEFAULT_TENANT_ID = "default"


class EntityType:
    """Entity-Typen für den Knowledge Graph."""

    MODULE = "module"
    SERVICE = "service"
    HOST = "host"
    CONFIGURATION = "configuration"
    INCIDENT = "incident"
    USER = "user"
    TAG = "tag"
    RUNBOOK = "runbook"
    WORKFLOW = "workflow"
    AGENT = "agent"


class RelationType:
    """Beziehungstypen zwischen Entitäten."""

    DEPENDS_ON = "depends_on"
    TRIGGERS = "triggers"
    RESOLVED_BY = "resolved_by"
    SIMILAR_TO = "similar_to"
    CONFIGURED_WITH = "configured_with"
    MANAGES = "manages"
    PART_OF = "part_of"
    CAUSED_BY = "caused_by"
    HAS_TAG = "has_tag"
    EXECUTED_BY = "executed_by"


def _normalize_tenant_id(tenant_id: str | None) -> str:
    if not tenant_id:
        return DEFAULT_TENANT_ID
    normalized = str(tenant_id).strip()
    return normalized or DEFAULT_TENANT_ID


class KnowledgeGraph:
    """
    NetworkX-basierter Knowledge Graph für Ninko.

    Pro Tenant wird ein eigener ``DiGraph`` vorgehalten, der in
    ``data/knowledge_graph/graph_<tenant>.json`` persistiert wird.
    Arbeitet ergänzend zum Semantic Memory (ChromaDB).
    """

    _instance: KnowledgeGraph | None = None
    _init_lock: threading.Lock = threading.Lock()
    _default_tenant_warned: bool = False

    def __init__(self) -> None:
        self._graphs: dict[str, nx.DiGraph] = {}
        self._settings = get_settings()
        self._data_dir = Path(self._settings.DATA_DIR) / "knowledge_graph"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._pickle_path = self._data_dir / "graph.pkl"
        self._json_path = self._data_dir / "graph_export.json"
        self._lock = asyncio.Lock()
        self._load()
        total_nodes = sum(g.number_of_nodes() for g in self._graphs.values())
        total_edges = sum(g.number_of_edges() for g in self._graphs.values())
        logger.info(
            "Knowledge Graph initialisiert: %d tenants, %d nodes, %d edges",
            len(self._graphs),
            total_nodes,
            total_edges,
        )

    @classmethod
    def get_instance(cls) -> KnowledgeGraph:
        """Singleton-Accessor mit thread-safe Initialisierung."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = KnowledgeGraph()
        return cls._instance

    def _get_graph(self, tenant_id: str) -> nx.DiGraph:
        key = _normalize_tenant_id(tenant_id)
        graph = self._graphs.get(key)
        if graph is None:
            graph = self._load_tenant_graph(key)
            self._graphs[key] = graph
            if key == DEFAULT_TENANT_ID and not KnowledgeGraph._default_tenant_warned:
                logger.warning(
                    "Knowledge Graph: Default-Tenant '%s' verwendet – "
                    "es wurde kein expliziter tenant_id übergeben.",
                    DEFAULT_TENANT_ID,
                )
                KnowledgeGraph._default_tenant_warned = True
        return graph

    def _tenant_path(self, tenant_id: str) -> Path:
        key = _normalize_tenant_id(tenant_id)
        return self._data_dir / f"graph_{key}.json"

    def _load_tenant_graph(self, tenant_id: str) -> nx.DiGraph:
        path = self._tenant_path(tenant_id)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                edges_key = "links" if "links" in data else "edges"
                return nx.node_link_graph(
                    data, directed=True, edges=edges_key
                )
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                json.JSONDecodeError,
            ) as e:
                logger.error(
                    "Fehler beim Laden von Tenant-Graph %s: %s – starte leer",
                    tenant_id,
                    e,
                )
        return nx.DiGraph()

    def _load(self) -> None:
        """Lädt alle Tenant-Graphen. Migriert Legacy-Dateien."""
        for path in self._data_dir.glob("graph_*.json"):
            tenant_id = path.stem[len("graph_") :]
            if not tenant_id:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                edges_key = "links" if "links" in data else "edges"
                self._graphs[tenant_id] = nx.node_link_graph(
                    data, directed=True, edges=edges_key
                )
                logger.info("Knowledge Graph geladen: tenant=%s file=%s", tenant_id, path)
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                json.JSONDecodeError,
            ) as e:
                logger.error("Fehler beim Laden von %s: %s – wird übersprungen", path, e)

        if self._json_path.exists():
            try:
                with open(self._json_path, encoding="utf-8") as f:
                    data = json.load(f)
                if not self._graphs:
                    edges_key = "links" if "links" in data else "edges"
                    self._graphs[DEFAULT_TENANT_ID] = nx.node_link_graph(
                        data, directed=True, edges=edges_key
                    )
                    logger.info(
                        "Legacy graph_export.json in Default-Tenant geladen: %s",
                        self._json_path,
                    )
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                json.JSONDecodeError,
            ) as e:
                logger.error(
                    "Fehler beim Laden des Legacy-Graph: %s – starte leer", e
                )
        elif self._pickle_path.exists():
            logger.warning(
                "Ignoriere unsichere Legacy-Pickle-Datei %s; bitte per JSON neu exportieren/importieren.",
                self._pickle_path,
            )

    async def _save(self, tenant_id: str) -> None:
        """Persistiert den Graph eines Tenants als JSON."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._save_sync, key)

    def _save_sync(self, tenant_id: str) -> None:
        """Synchrone JSON-Speicherung (für Executor)."""
        graph = self._graphs.get(tenant_id)
        if graph is None:
            return
        try:
            data = nx.node_link_data(graph, edges="links")
            path = self._tenant_path(tenant_id)
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            tmp.replace(path)
            logger.debug("Knowledge Graph gespeichert: tenant=%s path=%s", tenant_id, path)
        except OSError as e:
            logger.error("Fehler beim Speichern von Tenant %s: %s", tenant_id, e)

    def _check_tenant_match(self, tenant_id: str, graph: nx.DiGraph, node_id: str) -> bool:
        if node_id not in graph:
            return False
        node_tenant = graph.nodes[node_id].get("tenant_id")
        if node_tenant and node_tenant != _normalize_tenant_id(tenant_id):
            return False
        return True

    # ────────────────────────────────────────────────────────────────────────────
    # CRUD Operations
    # ────────────────────────────────────────────────────────────────────────────

    async def add_entity(
        self,
        tenant_id: str,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """
        Fügt eine Entität zum Tenant-Graph hinzu.

        Args:
            tenant_id: Tenant-ID (Isolation-Key)
            entity_id: Eindeutige ID (z.B. "proxmox:node:pve1")
            entity_type: EntityType-Konstante
            name: Menschenlesbarer Name
            properties: Zusätzliche Attribute

        Returns:
            Die erstellte Entity-Dict
        """
        key = _normalize_tenant_id(tenant_id)
        now = datetime.now(timezone.utc).isoformat()
        node_data = {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "tenant_id": key,
            "created_at": now,
            "updated_at": now,
            "properties": properties or {},
        }

        async with self._lock:
            graph = self._get_graph(key)
            graph.add_node(entity_id, **node_data)

        await self._save(key)
        logger.debug("Entity hinzugefügt: tenant=%s id=%s (%s)", key, entity_id, entity_type)
        return node_data

    async def add_relationship(
        self,
        tenant_id: str,
        source: str,
        target: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """
        Erstellt eine gerichtete Beziehung zwischen zwei Entitäten im Tenant-Graph.

        Args:
            tenant_id: Tenant-ID (Isolation-Key)
            source: Source-Entity-ID
            target: Target-Entity-ID
            relation_type: RelationType-Konstante
            properties: Zusätzliche Edge-Attribute

        Returns:
            Die erstellte Relationship-Dict
        """
        key = _normalize_tenant_id(tenant_id)
        now = datetime.now(timezone.utc).isoformat()
        edge_data = {
            "relation": relation_type,
            "created_at": now,
            "properties": properties or {},
        }

        async with self._lock:
            graph = self._get_graph(key)
            if not self._check_tenant_match(key, graph, source):
                raise ValueError(f"Source-Entity nicht gefunden: {source}")
            if not self._check_tenant_match(key, graph, target):
                raise ValueError(f"Target-Entity nicht gefunden: {target}")
            graph.add_edge(source, target, **edge_data)

        await self._save(key)
        logger.debug(
            "Beziehung erstellt: tenant=%s %s -[%s]-> %s", key, source, relation_type, target
        )
        return {"source": source, "target": target, **edge_data}

    async def get_entity(self, tenant_id: str, entity_id: str) -> dict | None:
        """Gibt eine Entität mit ihren Beziehungen zurück (Tenant-scoped)."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if not self._check_tenant_match(key, graph, entity_id):
                return None

            node = dict(graph.nodes[entity_id])
            predecessors = [
                {"from": p, "relation": graph[p][entity_id].get("relation")}
                for p in graph.predecessors(entity_id)
            ]
            successors = [
                {"to": s, "relation": graph[entity_id][s].get("relation")}
                for s in graph.successors(entity_id)
            ]

            return {
                **node,
                "incoming_relations": predecessors,
                "outgoing_relations": successors,
            }

    async def update_entity(
        self, tenant_id: str, entity_id: str, properties: dict[str, Any]
    ) -> dict | None:
        """Aktualisiert Properties einer Entität (Tenant-scoped, merged)."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if not self._check_tenant_match(key, graph, entity_id):
                return None

            node = graph.nodes[entity_id]
            node["properties"] = {**node.get("properties", {}), **properties}
            node["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self._save(key)
        return dict(node)

    async def delete_entity(self, tenant_id: str, entity_id: str) -> bool:
        """Löscht eine Entität und alle ihre Beziehungen (Tenant-scoped)."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if not self._check_tenant_match(key, graph, entity_id):
                return False
            graph.remove_node(entity_id)

        await self._save(key)
        logger.debug("Entity gelöscht: tenant=%s id=%s", key, entity_id)
        return True

    async def list_all_entities(self, tenant_id: str) -> list[dict]:
        """Gibt alle Entitäten des Tenants zurück."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            return [dict(data) for _, data in graph.nodes(data=True)]

    def get_node_data(
        self, tenant_id: str, entity_id: str
    ) -> dict[str, Any] | None:
        """Gibt die Node-Attribute einer Entität zurück (Tenant-scoped, synchron)."""
        key = _normalize_tenant_id(tenant_id)
        graph = self._graphs.get(key)
        if graph is None:
            return None
        if not self._check_tenant_match(key, graph, entity_id):
            return None
        return dict(graph.nodes[entity_id])

    def get_edge_data(
        self, tenant_id: str, source: str, target: str
    ) -> dict[str, Any] | None:
        """Gibt die Edge-Attribute einer Beziehung zurück (Tenant-scoped, synchron)."""
        key = _normalize_tenant_id(tenant_id)
        graph = self._graphs.get(key)
        if graph is None or not graph.has_edge(source, target):
            return None
        return dict(graph[source][target])

    async def entity_exists(self, tenant_id: str, entity_id: str) -> bool:
        """Prüft ob eine Entität im Tenant-Graph existiert."""
        return await self._entity_exists(tenant_id, entity_id)

    # ────────────────────────────────────────────────────────────────────────────
    # Graph Queries
    # ────────────────────────────────────────────────────────────────────────────

    async def find_by_type(self, tenant_id: str, entity_type: str) -> list[dict]:
        """Gibt alle Entitäten eines Typs im Tenant-Graph zurück."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            return [
                dict(data)
                for _, data in graph.nodes(data=True)
                if data.get("type") == entity_type
            ]

    async def find_by_property(
        self, tenant_id: str, key: str, value: Any
    ) -> list[dict]:
        """Suche nach Property-Wert (exakt match) im Tenant-Graph."""
        tid = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(tid)
            results = []
            for _, data in graph.nodes(data=True):
                props = data.get("properties", {})
                if props.get(key) == value:
                    results.append(dict(data))
            return results

    async def get_neighbors(
        self, tenant_id: str, entity_id: str, relation_type: str | None = None
    ) -> list[dict]:
        """
        Gibt Nachbarn einer Entität zurück (in + out).
        Optional gefiltert nach Beziehungstyp. Tenant-scoped.
        """
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if not self._check_tenant_match(key, graph, entity_id):
                return []

            neighbors = []

            for succ in graph.successors(entity_id):
                edge_data = graph[entity_id][succ]
                if relation_type is None or edge_data.get("relation") == relation_type:
                    neighbors.append(
                        {
                            "direction": "out",
                            "entity": dict(graph.nodes[succ]),
                            "relation": edge_data.get("relation"),
                        }
                    )

            for pred in graph.predecessors(entity_id):
                edge_data = graph[pred][entity_id]
                if relation_type is None or edge_data.get("relation") == relation_type:
                    neighbors.append(
                        {
                            "direction": "in",
                            "entity": dict(graph.nodes[pred]),
                            "relation": edge_data.get("relation"),
                        }
                    )

            return neighbors

    async def get_path(
        self, tenant_id: str, source: str, target: str, max_depth: int = 5
    ) -> list[list[str]] | None:
        """
        Findet Pfade zwischen zwei Entitäten (bis max_depth). Tenant-scoped.
        Gibt eine Liste von Pfaden (jeder Pfad ist eine Liste von IDs) zurück.
        """
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if not self._check_tenant_match(key, graph, source):
                return None
            if not self._check_tenant_match(key, graph, target):
                return None
            try:
                paths = list(
                    nx.all_simple_paths(graph, source, target, cutoff=max_depth)
                )
                return paths
            except nx.NetworkXNoPath:
                return None

    async def get_centrality(self, tenant_id: str, top_k: int = 10) -> list[dict]:
        """
        Berechnet PageRank-Zentralität aller Nodes im Tenant-Graph.
        """
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if graph.number_of_nodes() == 0:
                return []

            pr = nx.pagerank(graph)
            ranked = sorted(pr.items(), key=lambda x: x[1], reverse=True)

            return [
                {
                    "entity_id": eid,
                    "score": score,
                    "entity": dict(graph.nodes[eid]),
                }
                for eid, score in ranked[:top_k]
            ]

    async def find_communities(self, tenant_id: str) -> list[dict]:
        """
        Erkennt Communities (Cluster) im Tenant-Graph mittels Louvain-Algorithmus.
        """
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if graph.number_of_edges() == 0:
                return []

            undirected = graph.to_undirected()
            communities = nx.community.louvain_communities(undirected)

            return [
                {
                    "community_id": i,
                    "members": [dict(graph.nodes[n]) for n in community],
                    "size": len(community),
                }
                for i, community in enumerate(communities)
            ]

    async def search_similar_entities(
        self, tenant_id: str, query_embedding: list[float], top_k: int = 5
    ) -> list[dict]:
        """
        Semantische Suche über Entitäten via ChromaDB (bridget Semantic Memory).
        Tenant-scoped.
        """
        key = _normalize_tenant_id(tenant_id)
        memory = get_memory()

        hits = await memory.search(
            query=" ",
            top_k=100,
            category="entity",
        )

        async with self._lock:
            graph = self._get_graph(key)
            results = []
            for hit in hits:
                meta = hit.get("metadata", {})
                entity_id = meta.get("entity_id")
                if entity_id and self._check_tenant_match(key, graph, entity_id):
                    results.append(
                        {
                            "entity": dict(graph.nodes[entity_id]),
                            "memory_distance": hit.get("distance"),
                        }
                    )
                if len(results) >= top_k:
                    break

        return results

    # ────────────────────────────────────────────────────────────────────────────
    # Smart Extraction & Learning
    # ────────────────────────────────────────────────────────────────────────────

    async def extract_from_incident(
        self,
        tenant_id: str,
        module: str,
        summary: str,
        details: str,
        resolution: str | None = None,
    ) -> dict:
        """
        Extrahiert automatisch Entitäten und Beziehungen aus einem Incident.
        Speichert auch im Semantic Memory. Tenant-scoped.

        Returns:
            Dict mit extracted_entities und created_relationships
        """
        key = _normalize_tenant_id(tenant_id)
        extracted = {"entities": [], "relationships": []}

        module_id = f"module:{module}"
        if not await self._entity_exists(key, module_id):
            await self.add_entity(
                tenant_id=key,
                entity_id=module_id,
                entity_type=EntityType.MODULE,
                name=module.upper(),
                properties={"category": "infrastructure"},
            )
            extracted["entities"].append(module_id)

        incident_id = (
            f"incident:{module}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        )
        await self.add_entity(
            tenant_id=key,
            entity_id=incident_id,
            entity_type=EntityType.INCIDENT,
            name=summary[:50],
            properties={
                "module": module,
                "summary": summary,
                "details": details,
                "status": "resolved" if resolution else "open",
                "resolution": resolution,
            },
        )
        extracted["entities"].append(incident_id)

        rel = await self.add_relationship(
            tenant_id=key,
            source=incident_id,
            target=module_id,
            relation_type=RelationType.CAUSED_BY,
            properties={"confidence": 0.8},
        )
        extracted["relationships"].append(rel)

        if resolution:
            agent_keywords = ["agent", "workflow", "runbook", "playbook"]
            if any(kw in resolution.lower() for kw in agent_keywords):
                agent_id = "agent:orchestrator"
                if not await self._entity_exists(key, agent_id):
                    await self.add_entity(
                        tenant_id=key,
                        entity_id=agent_id,
                        entity_type=EntityType.AGENT,
                        name="Ninko Orchestrator",
                        properties={"role": "resolver"},
                    )
                    extracted["entities"].append(agent_id)

                rel = await self.add_relationship(
                    tenant_id=key,
                    source=incident_id,
                    target=agent_id,
                    relation_type=RelationType.RESOLVED_BY,
                    properties={"resolution": resolution[:200]},
                )
                extracted["relationships"].append(rel)

        memory = get_memory()
        content = f"[{module.upper()}] {summary}\n\n{details}"
        await memory.store(
            content=content,
            metadata={
                "type": "incident",
                "module": module,
                "entity_id": incident_id,
                "resolution": resolution,
                "tenant_id": key,
            },
            category="incident",
        )

        return extracted

    async def _entity_exists(self, tenant_id: str, entity_id: str) -> bool:
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            return self._check_tenant_match(key, graph, entity_id)

    async def suggest_related(self, tenant_id: str, entity_id: str) -> list[dict]:
        """
        Schlägt verwandte Entitäten vor basierend auf:
        1. Graph-Nachbarschaft
        2. Gemeinsame Tags
        3. Ähnliche Incidents (via Semantic Memory)
        Tenant-scoped.
        """
        key = _normalize_tenant_id(tenant_id)
        entity = await self.get_entity(key, entity_id)
        if not entity:
            return []

        suggestions = []

        neighbors = await self.get_neighbors(key, entity_id)
        for n in neighbors:
            suggestions.append(
                {
                    "entity": n["entity"],
                    "reason": f"Graph-{n['direction']}going ({n['relation']})",
                    "score": 1.0,
                }
            )

        entity_tags = set(entity.get("properties", {}).get("tags", []))
        if entity_tags:
            all_entities = await self.find_by_type(key, entity.get("type"))
            for other in all_entities:
                if other["id"] == entity_id:
                    continue
                other_tags = set(other.get("properties", {}).get("tags", []))
                if other_tags:
                    intersection = len(entity_tags & other_tags)
                    union = len(entity_tags | other_tags)
                    if union > 0:
                        similarity = intersection / union
                        if similarity > 0.5:
                            suggestions.append(
                                {
                                    "entity": other,
                                    "reason": f"Tag-Overlap ({similarity:.0%})",
                                    "score": similarity,
                                }
                            )

        memory_hits = await self.search_similar_entities(
            tenant_id=key,
            query_embedding=[],
            top_k=3,
        )
        for hit in memory_hits:
            e = hit.get("entity")
            if e and e.get("id") != entity_id:
                suggestions.append(
                    {
                        "entity": e,
                        "reason": f"Semantic-Similarity ({hit.get('memory_distance', 0):.2f})",
                        "score": 1.0 - (hit.get("memory_distance", 1) or 1),
                    }
                )

        seen = {entity_id}
        unique = []
        for s in sorted(suggestions, key=lambda x: x["score"], reverse=True):
            eid = s["entity"].get("id")
            if eid not in seen:
                seen.add(eid)
                unique.append(s)

        return unique[:10]

    # ────────────────────────────────────────────────────────────────────────────
    # Stats & Export
    # ────────────────────────────────────────────────────────────────────────────

    async def get_stats(self, tenant_id: str | None = None) -> dict:
        """Statistiken zum Graph. Aggregiert über alle Tenants, wenn tenant_id fehlt."""
        async with self._lock:
            if tenant_id is None:
                nodes = sum(g.number_of_nodes() for g in self._graphs.values())
                edges = sum(g.number_of_edges() for g in self._graphs.values())
                tenants = len(self._graphs)
                is_connected = False
                components = tenants
                if tenants == 0:
                    return {
                        "nodes": 0,
                        "edges": 0,
                        "density": 0.0,
                        "is_connected": False,
                        "components": 0,
                        "node_types": {},
                        "tenants": 0,
                    }
                if tenants == 1 and nodes > 0:
                    only_graph = next(iter(self._graphs.values()))
                    try:
                        components = nx.number_weakly_connected_components(only_graph)
                        is_connected = components == 1
                    except nx.NetworkXPointlessConcept:
                        is_connected = False
                node_types: dict[str, int] = {}
                for graph in self._graphs.values():
                    for _, data in graph.nodes(data=True):
                        t = data.get("type")
                        if t:
                            node_types[t] = node_types.get(t, 0) + 1
                return {
                    "nodes": nodes,
                    "edges": edges,
                    "density": 0.0,
                    "is_connected": is_connected,
                    "components": components,
                    "node_types": node_types,
                    "tenants": tenants,
                }

            key = _normalize_tenant_id(tenant_id)
            graph = self._get_graph(key)
            nodes = graph.number_of_nodes()
            edges = graph.number_of_edges()
            is_connected = False
            components = 0
            if nodes > 0:
                try:
                    components = nx.number_weakly_connected_components(graph)
                    is_connected = components == 1
                except nx.NetworkXPointlessConcept:
                    is_connected = False
            node_types = {}
            for _, data in graph.nodes(data=True):
                t = data.get("type")
                if t:
                    node_types[t] = node_types.get(t, 0) + 1
            return {
                "nodes": nodes,
                "edges": edges,
                "density": nx.density(graph) if nodes > 1 else 0.0,
                "is_connected": is_connected,
                "components": components,
                "node_types": node_types,
            }

    async def export_graph(self, tenant_id: str) -> dict:
        """Exportiert den Tenant-Graph als node-link JSON."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            return nx.node_link_data(graph, edges="links")

    async def import_graph(
        self, tenant_id: str, data: dict, merge: bool = False
    ) -> dict:
        """Importiert einen Graph aus node-link JSON in den Tenant-Graph."""
        key = _normalize_tenant_id(tenant_id)
        async with self._lock:
            graph = self._get_graph(key)
            if not merge:
                graph.clear()

            edges_key = "links" if "links" in data else "edges"
            new_graph = nx.node_link_graph(
                data, directed=True, edges=edges_key
            )
            for node_id, node_data in new_graph.nodes(data=True):
                enriched = dict(node_data)
                enriched["tenant_id"] = key
                graph.add_node(node_id, **enriched)
            for u, v, edge_data in new_graph.edges(data=True):
                graph.add_edge(u, v, **edge_data)

        await self._save(key)
        return await self.get_stats(key)


async def get_knowledge_graph() -> KnowledgeGraph:
    """Gibt die globale Knowledge Graph Instanz zurück."""
    return KnowledgeGraph.get_instance()
