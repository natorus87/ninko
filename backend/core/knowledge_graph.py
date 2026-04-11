"""
Ninko Knowledge Graph – NetworkX-basierte Graph-Datenbank für IT-Beziehungen.

Ergänzt das Semantic Memory (ChromaDB) mit strukturierten Entitäten und Beziehungen.
Ermöglicht Graph-Traversal, Pattern-Matching und erweiterte RAG-Queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pickle
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from core.config import get_settings
from core.memory import get_memory

logger = logging.getLogger("ninko.knowledge_graph")


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


class KnowledgeGraph:
    """
    NetworkX-basierter Knowledge Graph für Ninko.

    Persistiert als Pickle-Datei (JSON-Backup für Human-Readable Export).
    Arbeitet ergänzend zum Semantic Memory (ChromaDB).
    """

    _instance: KnowledgeGraph | None = None
    _init_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._graph = nx.DiGraph()
        self._settings = get_settings()
        self._data_dir = Path(self._settings.DATA_DIR) / "knowledge_graph"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._pickle_path = self._data_dir / "graph.pkl"
        self._json_path = self._data_dir / "graph_export.json"
        self._lock = asyncio.Lock()
        self._load()
        logger.info(
            "Knowledge Graph initialisiert: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )

    @classmethod
    def get_instance(cls) -> KnowledgeGraph:
        """Singleton-Accessor mit thread-safe Initialisierung."""
        if cls._instance is None:
            with cls._init_lock:
                # Double-check pattern
                if cls._instance is None:
                    cls._instance = KnowledgeGraph()
        return cls._instance

    def _load(self) -> None:
        """Lädt den Graph aus Pickle (oder startet leer)."""
        if self._pickle_path.exists():
            try:
                with open(self._pickle_path, "rb") as f:
                    self._graph = pickle.load(f)
                logger.info("Knowledge Graph geladen aus %s", self._pickle_path)
            except (pickle.PickleError, OSError, EOFError) as e:
                logger.error("Fehler beim Laden: %s – starte leer", e)
                self._graph = nx.DiGraph()
        else:
            self._graph = nx.DiGraph()

    async def _save(self) -> None:
        """Persistiert den Graph (Pickle + JSON-Export)."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._save_sync)

    def _save_sync(self) -> None:
        """Synchrone Speicherung (für Executor)."""
        try:
            # Pickle (schnell, vollständig)
            with open(self._pickle_path, "wb") as f:
                pickle.dump(self._graph, f, protocol=pickle.HIGHEST_PROTOCOL)

            # JSON-Export (human-readable, für Analyse/Backup)
            data = nx.node_link_data(self._graph)
            with open(self._json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

            logger.debug("Knowledge Graph gespeichert")
        except OSError as e:
            logger.error("Fehler beim Speichern: %s", e)

    # ────────────────────────────────────────────────────────────────────────────
    # CRUD Operations
    # ────────────────────────────────────────────────────────────────────────────

    async def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """
        Fügt eine Entität zum Graph hinzu.

        Args:
            entity_id: Eindeutige ID (z.B. "proxmox:node:pve1")
            entity_type: EntityType-Konstante
            name: Menschenlesbarer Name
            properties: Zusätzliche Attribute

        Returns:
            Die erstellte Entity-Dict
        """
        now = datetime.now(timezone.utc).isoformat()
        node_data = {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "created_at": now,
            "updated_at": now,
            "properties": properties or {},
        }

        async with self._lock:
            self._graph.add_node(entity_id, **node_data)

        await self._save()
        logger.debug("Entity hinzugefügt: %s (%s)", entity_id, entity_type)
        return node_data

    async def add_relationship(
        self,
        source: str,
        target: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """
        Erstellt eine gerichtete Beziehung zwischen zwei Entitäten.

        Args:
            source: Source-Entity-ID
            target: Target-Entity-ID
            relation_type: RelationType-Konstante
            properties: Zusätzliche Edge-Attribute

        Returns:
            Die erstellte Relationship-Dict
        """
        now = datetime.now(timezone.utc).isoformat()
        edge_data = {
            "relation": relation_type,
            "created_at": now,
            "properties": properties or {},
        }

        async with self._lock:
            if source not in self._graph:
                raise ValueError(f"Source-Entity nicht gefunden: {source}")
            if target not in self._graph:
                raise ValueError(f"Target-Entity nicht gefunden: {target}")
            self._graph.add_edge(source, target, **edge_data)

        await self._save()
        logger.debug("Beziehung erstellt: %s -[%s]-> %s", source, relation_type, target)
        return {"source": source, "target": target, **edge_data}

    async def get_entity(self, entity_id: str) -> dict | None:
        """Gibt eine Entität mit ihren Beziehungen zurück."""
        async with self._lock:
            if entity_id not in self._graph:
                return None

            node = dict(self._graph.nodes[entity_id])
            predecessors = [
                {"from": p, "relation": self._graph[p][entity_id].get("relation")}
                for p in self._graph.predecessors(entity_id)
            ]
            successors = [
                {"to": s, "relation": self._graph[entity_id][s].get("relation")}
                for s in self._graph.successors(entity_id)
            ]

            return {
                **node,
                "incoming_relations": predecessors,
                "outgoing_relations": successors,
            }

    async def update_entity(
        self, entity_id: str, properties: dict[str, Any]
    ) -> dict | None:
        """Aktualisiert Properties einer Entität (merged)."""
        async with self._lock:
            if entity_id not in self._graph:
                return None

            node = self._graph.nodes[entity_id]
            node["properties"] = {**node.get("properties", {}), **properties}
            node["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self._save()
        return dict(node)

    async def delete_entity(self, entity_id: str) -> bool:
        """Löscht eine Entität und alle ihre Beziehungen."""
        async with self._lock:
            if entity_id not in self._graph:
                return False
            self._graph.remove_node(entity_id)

        await self._save()
        logger.debug("Entity gelöscht: %s", entity_id)
        return True

    # ────────────────────────────────────────────────────────────────────────────
    # Graph Queries
    # ────────────────────────────────────────────────────────────────────────────

    async def find_by_type(self, entity_type: str) -> list[dict]:
        """Gibt alle Entitäten eines Typs zurück."""
        async with self._lock:
            return [
                dict(data)
                for n, data in self._graph.nodes(data=True)
                if data.get("type") == entity_type
            ]

    async def find_by_property(self, key: str, value: Any) -> list[dict]:
        """Suche nach Property-Wert (exakt match)."""
        async with self._lock:
            results = []
            for n, data in self._graph.nodes(data=True):
                props = data.get("properties", {})
                if props.get(key) == value:
                    results.append(dict(data))
            return results

    async def get_neighbors(
        self, entity_id: str, relation_type: str | None = None
    ) -> list[dict]:
        """
        Gibt Nachbarn einer Entität zurück (in + out).
        Optional gefiltert nach Beziehungstyp.
        """
        async with self._lock:
            if entity_id not in self._graph:
                return []

            neighbors = []

            # Outgoing
            for succ in self._graph.successors(entity_id):
                edge_data = self._graph[entity_id][succ]
                if relation_type is None or edge_data.get("relation") == relation_type:
                    neighbors.append(
                        {
                            "direction": "out",
                            "entity": dict(self._graph.nodes[succ]),
                            "relation": edge_data.get("relation"),
                        }
                    )

            # Incoming
            for pred in self._graph.predecessors(entity_id):
                edge_data = self._graph[pred][entity_id]
                if relation_type is None or edge_data.get("relation") == relation_type:
                    neighbors.append(
                        {
                            "direction": "in",
                            "entity": dict(self._graph.nodes[pred]),
                            "relation": edge_data.get("relation"),
                        }
                    )

            return neighbors

    async def get_path(
        self, source: str, target: str, max_depth: int = 5
    ) -> list[list[str]] | None:
        """
        Findet Pfade zwischen zwei Entitäten (bis max_depth).
        Gibt eine Liste von Pfaden (jeder Pfad ist eine Liste von IDs) zurück.
        """
        async with self._lock:
            try:
                paths = list(
                    nx.all_simple_paths(self._graph, source, target, cutoff=max_depth)
                )
                return paths
            except nx.NetworkXNoPath:
                return None

    async def get_centrality(self, top_k: int = 10) -> list[dict]:
        """
        Berechnet PageRank-Zentralität aller Nodes.
        Nützlich für "wichtigste" Entitäten.
        """
        async with self._lock:
            if self._graph.number_of_nodes() == 0:
                return []

            pr = nx.pagerank(self._graph)
            ranked = sorted(pr.items(), key=lambda x: x[1], reverse=True)

            return [
                {
                    "entity_id": eid,
                    "score": score,
                    "entity": dict(self._graph.nodes[eid]),
                }
                for eid, score in ranked[:top_k]
            ]

    async def find_communities(self) -> list[dict]:
        """
        Erkennt Communities (Cluster) im Graph mittels Louvain-Algorithmus.
        """
        async with self._lock:
            if self._graph.number_of_edges() == 0:
                return []

            # Louvain benötigt ungerichteten Graph
            undirected = self._graph.to_undirected()
            communities = nx.community.louvain_communities(undirected)

            return [
                {
                    "community_id": i,
                    "members": [dict(self._graph.nodes[n]) for n in community],
                    "size": len(community),
                }
                for i, community in enumerate(communities)
            ]

    async def search_similar_entities(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[dict]:
        """
        Semantische Suche über Entitäten via ChromaDB (bridget Semantic Memory).
        """
        # Semantic Memory für ähnliche Inhalte fragen
        memory = get_memory()

        # Wir suchen nach Entitäten, die im Semantic Memory gespeichert wurden
        hits = await memory.search(
            query=" ",  # Dummy - wir brauchen die Embeddings
            top_k=100,
            category="entity",
        )

        # Filtern auf Entitäten, die im Graph existieren
        results = []
        for hit in hits:
            meta = hit.get("metadata", {})
            entity_id = meta.get("entity_id")
            if entity_id and entity_id in self._graph:
                results.append(
                    {
                        "entity": dict(self._graph.nodes[entity_id]),
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
        self, module: str, summary: str, details: str, resolution: str | None = None
    ) -> dict:
        """
        Extrahiert automatisch Entitäten und Beziehungen aus einem Incident.
        Speichert auch im Semantic Memory.

        Returns:
            Dict mit extracted_entities und created_relationships
        """
        extracted = {"entities": [], "relationships": []}

        # Module-Entity erstellen/aktualisieren
        module_id = f"module:{module}"
        if module_id not in self._graph:
            await self.add_entity(
                entity_id=module_id,
                entity_type=EntityType.MODULE,
                name=module.upper(),
                properties={"category": "infrastructure"},
            )
            extracted["entities"].append(module_id)

        # Incident-Entity
        incident_id = (
            f"incident:{module}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        )
        await self.add_entity(
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

        # Beziehung: Incident wurde durch Module ausgelöst
        rel = await self.add_relationship(
            source=incident_id,
            target=module_id,
            relation_type=RelationType.CAUSED_BY,
            properties={"confidence": 0.8},
        )
        extracted["relationships"].append(rel)

        # Falls Resolution bekannt: Runbook/Agent als Resolver
        if resolution:
            # Simplistische Heuristik: Prüfe ob ein Agent-Name vorkommt
            agent_keywords = ["agent", "workflow", "runbook", "playbook"]
            if any(kw in resolution.lower() for kw in agent_keywords):
                agent_id = "agent:orchestrator"  # Default
                if agent_id not in self._graph:
                    await self.add_entity(
                        entity_id=agent_id,
                        entity_type=EntityType.AGENT,
                        name="Ninko Orchestrator",
                        properties={"role": "resolver"},
                    )
                    extracted["entities"].append(agent_id)

                rel = await self.add_relationship(
                    source=incident_id,
                    target=agent_id,
                    relation_type=RelationType.RESOLVED_BY,
                    properties={"resolution": resolution[:200]},
                )
                extracted["relationships"].append(rel)

        # In Semantic Memory speichern für Vektor-Suche
        memory = get_memory()
        content = f"[{module.upper()}] {summary}\n\n{details}"
        await memory.store(
            content=content,
            metadata={
                "type": "incident",
                "module": module,
                "entity_id": incident_id,
                "resolution": resolution,
            },
            category="incident",
        )

        return extracted

    async def suggest_related(self, entity_id: str) -> list[dict]:
        """
        Schlägt verwandte Entitäten vor basierend auf:
        1. Graph-Nachbarschaft
        2. Gemeinsame Tags
        3. Ähnliche Incidents (via Semantic Memory)
        """
        entity = await self.get_entity(entity_id)
        if not entity:
            return []

        suggestions = []

        # 1. Direkte Nachbarn
        neighbors = await self.get_neighbors(entity_id)
        for n in neighbors:
            suggestions.append(
                {
                    "entity": n["entity"],
                    "reason": f"Graph-{n['direction']}going ({n['relation']})",
                    "score": 1.0,
                }
            )

        # 2. Gemeinsame Tags (Jaccard-Ähnlichkeit)
        entity_tags = set(entity.get("properties", {}).get("tags", []))
        if entity_tags:
            all_entities = await self.find_by_type(entity.get("type"))
            for other in all_entities:
                if other["id"] == entity_id:
                    continue
                other_tags = set(other.get("properties", {}).get("tags", []))
                if other_tags:
                    intersection = len(entity_tags & other_tags)
                    union = len(entity_tags | other_tags)
                    if union > 0:
                        similarity = intersection / union
                        if similarity > 0.5:  # Mindestens 50% Overlap
                            suggestions.append(
                                {
                                    "entity": other,
                                    "reason": f"Tag-Overlap ({similarity:.0%})",
                                    "score": similarity,
                                }
                            )

        # 3. Semantic Memory für ähnliche Inhalte
        memory_hits = await self.search_similar_entities(
            query_embedding=[],  # Wird intern gefüllt
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

        # Nach Score sortieren, Duplikate entfernen
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

    async def get_stats(self) -> dict:
        """Statistiken zum Graph."""
        async with self._lock:
            nodes = self._graph.number_of_nodes()
            edges = self._graph.number_of_edges()
            is_connected = False
            if nodes > 0 and edges > 0:
                try:
                    is_connected = nx.is_weakly_connected(self._graph)
                except nx.NetworkXPointlessConcept:
                    is_connected = False
            return {
                "nodes": nodes,
                "edges": edges,
                "density": nx.density(self._graph) if nodes > 1 else 0.0,
                "is_connected": is_connected,
                "node_types": {
                    t: len(await self.find_by_type(t))
                    for t in set(
                        data.get("type") for _, data in self._graph.nodes(data=True)
                    )
                },
            }

    async def export_graph(self) -> dict:
        """Exportiert den gesamten Graph als node-link JSON."""
        async with self._lock:
            return nx.node_link_data(self._graph)

    async def import_graph(self, data: dict, merge: bool = False) -> dict:
        """Importiert einen Graph aus node-link JSON."""
        async with self._lock:
            if not merge:
                self._graph.clear()

            new_graph = nx.node_link_graph(data, directed=True)
            self._graph = nx.compose(self._graph, new_graph)

        await self._save()
        return await self.get_stats()


# Singleton-Accessor
async def get_knowledge_graph() -> KnowledgeGraph:
    """Gibt die globale Knowledge Graph Instanz zurück."""
    return KnowledgeGraph.get_instance()
