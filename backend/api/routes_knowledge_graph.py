"""
API Routes für Knowledge Graph Management und Queries.

Bietet CRUD für Entitäten/Beziehungen, Graph-Traversal, und Analytics.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.auth import (
    ROLE_ADMIN,
    auth_tenant_id,
    resolve_request_auth,
    resolve_request_role,
)
from core.knowledge_graph import (
    get_knowledge_graph,
    EntityType,
    RelationType,
)
from core.schemas import ApiResponse

logger = logging.getLogger("ninko.api.knowledge_graph")

router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge-graph"])


class EntityCreateRequest(BaseModel):
    entity_id: str = Field(min_length=1, max_length=256)
    entity_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    properties: dict[str, Any] = Field(default_factory=dict)


class EntityUpdateRequest(BaseModel):
    properties: dict[str, Any] = Field(default_factory=dict)


class RelationshipCreateRequest(BaseModel):
    source: str = Field(min_length=1, max_length=256)
    target: str = Field(min_length=1, max_length=256)
    relation_type: str = Field(min_length=1, max_length=64)
    properties: dict[str, Any] = Field(default_factory=dict)


class IncidentExtractRequest(BaseModel):
    module: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)
    details: str = Field(min_length=1, max_length=20000)
    resolution: str | None = Field(default=None, max_length=20000)


class GraphImportRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    merge: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Entity CRUD
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/entities", response_model=ApiResponse)
async def create_entity(
    request: Request,
    body: EntityCreateRequest,
) -> ApiResponse:
    """Erstellt eine neue Entität im Knowledge Graph."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    try:
        kg = await get_knowledge_graph()
        entity = await kg.add_entity(
            tenant_id=tenant_id,
            entity_id=body.entity_id,
            entity_type=body.entity_type,
            name=body.name,
            properties=body.properties,
        )
        return ApiResponse(success=True, data=entity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fehler beim Erstellen der Entität")
        raise HTTPException(status_code=500, detail="Entity creation failed.") from exc


@router.get("/entities/{entity_id}", response_model=ApiResponse)
async def get_entity(
    request: Request,
    entity_id: str,
) -> ApiResponse:
    """Gibt eine Entität mit ihren Beziehungen zurück."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    entity = await kg.get_entity(tenant_id=tenant_id, entity_id=entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return ApiResponse(success=True, data=entity)


@router.put("/entities/{entity_id}", response_model=ApiResponse)
async def update_entity(
    request: Request,
    entity_id: str,
    body: EntityUpdateRequest,
) -> ApiResponse:
    """Aktualisiert Properties einer Entität."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    result = await kg.update_entity(
        tenant_id=tenant_id, entity_id=entity_id, properties=body.properties
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return ApiResponse(success=True, data=result)


@router.delete("/entities/{entity_id}", response_model=ApiResponse)
async def delete_entity(
    request: Request,
    entity_id: str,
) -> ApiResponse:
    """Löscht eine Entität und alle ihre Beziehungen."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    success = await kg.delete_entity(tenant_id=tenant_id, entity_id=entity_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return ApiResponse(success=True, data={"deleted": True})


@router.get("/entities", response_model=ApiResponse)
async def list_entities(
    request: Request,
    entity_type: str | None = None,
    limit: int = 100,
) -> ApiResponse:
    """Listet alle Entitäten (optional gefiltert nach Typ)."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()

    if entity_type:
        entities = await kg.find_by_type(tenant_id=tenant_id, entity_type=entity_type)
    else:
        # Alle Entitäten
        entities = await kg.list_all_entities(tenant_id=tenant_id)

    return ApiResponse(
        success=True, data={"entities": entities[:limit], "total": len(entities)}
    )


# ──────────────────────────────────────────────────────────────────────────────
# Relationships
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/relationships", response_model=ApiResponse)
async def create_relationship(
    request: Request,
    body: RelationshipCreateRequest,
) -> ApiResponse:
    """Erstellt eine Beziehung zwischen zwei Entitäten."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    try:
        kg = await get_knowledge_graph()
        rel = await kg.add_relationship(
            tenant_id=tenant_id,
            source=body.source,
            target=body.target,
            relation_type=body.relation_type,
            properties=body.properties,
        )
        return ApiResponse(success=True, data=rel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fehler beim Erstellen der Beziehung")
        raise HTTPException(status_code=500, detail="Relationship creation failed.") from exc


@router.get("/relationships/types", response_model=ApiResponse)
async def get_relation_types(
    request: Request,
) -> ApiResponse:
    """Gibt alle verfügbaren Beziehungstypen zurück."""
    auth_tenant_id(resolve_request_auth(request))
    return ApiResponse(
        success=True,
        data={
            "types": [
                RelationType.DEPENDS_ON,
                RelationType.TRIGGERS,
                RelationType.RESOLVED_BY,
                RelationType.SIMILAR_TO,
                RelationType.CONFIGURED_WITH,
                RelationType.MANAGES,
                RelationType.PART_OF,
                RelationType.CAUSED_BY,
                RelationType.HAS_TAG,
                RelationType.EXECUTED_BY,
            ]
        },
    )


@router.get("/entity-types", response_model=ApiResponse)
async def get_entity_types(
    request: Request,
) -> ApiResponse:
    """Gibt alle verfügbaren Entity-Typen zurück."""
    auth_tenant_id(resolve_request_auth(request))
    return ApiResponse(
        success=True,
        data={
            "types": [
                EntityType.MODULE,
                EntityType.SERVICE,
                EntityType.HOST,
                EntityType.CONFIGURATION,
                EntityType.INCIDENT,
                EntityType.USER,
                EntityType.TAG,
                EntityType.RUNBOOK,
                EntityType.WORKFLOW,
                EntityType.AGENT,
            ]
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Graph Queries & Traversal
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/entities/{entity_id}/neighbors", response_model=ApiResponse)
async def get_neighbors(
    request: Request,
    entity_id: str,
    relation_type: str | None = None,
) -> ApiResponse:
    """Gibt Nachbarn einer Entität zurück."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    neighbors = await kg.get_neighbors(
        tenant_id=tenant_id, entity_id=entity_id, relation_type=relation_type
    )
    return ApiResponse(success=True, data={"neighbors": neighbors})


@router.get("/path", response_model=ApiResponse)
async def find_path(
    request: Request,
    source: str,
    target: str,
    max_depth: int = 5,
) -> ApiResponse:
    """Findet Pfade zwischen zwei Entitäten."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    paths = await kg.get_path(
        tenant_id=tenant_id, source=source, target=target, max_depth=max_depth
    )
    if paths is None:
        return ApiResponse(success=True, data={"paths": [], "found": False})
    return ApiResponse(success=True, data={"paths": paths, "found": True})


@router.get("/centrality", response_model=ApiResponse)
async def get_centrality(
    request: Request,
    top_k: int = 10,
) -> ApiResponse:
    """Berechnet PageRank-Zentralität (Top-K)."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    ranked = await kg.get_centrality(tenant_id=tenant_id, top_k=top_k)
    return ApiResponse(success=True, data={"rankings": ranked})


@router.get("/communities", response_model=ApiResponse)
async def get_communities(
    request: Request,
) -> ApiResponse:
    """Erkennt Communities (Cluster) im Knowledge Graph."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    communities = await kg.find_communities(tenant_id=tenant_id)
    return ApiResponse(success=True, data={"communities": communities})


@router.get("/entities/{entity_id}/suggestions", response_model=ApiResponse)
async def get_suggestions(
    request: Request,
    entity_id: str,
) -> ApiResponse:
    """Schlägt verwandte Entitäten basierend auf Graph und Semantic Memory vor."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    suggestions = await kg.suggest_related(tenant_id=tenant_id, entity_id=entity_id)
    return ApiResponse(success=True, data={"suggestions": suggestions})


# ──────────────────────────────────────────────────────────────────────────────
# Smart Extraction & Learning
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/extract/incident", response_model=ApiResponse)
async def extract_from_incident(
    request: Request,
    body: IncidentExtractRequest,
) -> ApiResponse:
    """
    Extrahiert automatisch Entitäten und Beziehungen aus einem Incident.
    Speichert auch im Semantic Memory.
    """
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    try:
        kg = await get_knowledge_graph()
        extracted = await kg.extract_from_incident(
            tenant_id=tenant_id,
            module=body.module,
            summary=body.summary,
            details=body.details,
            resolution=body.resolution or None,
        )
        return ApiResponse(success=True, data=extracted)
    except Exception as exc:
        logger.exception("Fehler bei Incident-Extraktion")
        raise HTTPException(status_code=500, detail="Incident extraction failed.") from exc


# ──────────────────────────────────────────────────────────────────────────────
# Stats & Export
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=ApiResponse)
async def get_stats(
    request: Request,
) -> ApiResponse:
    """Gibt Statistiken zum Knowledge Graph zurück."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    stats = await kg.get_stats(tenant_id=tenant_id)
    return ApiResponse(success=True, data=stats)


@router.get("/export", response_model=ApiResponse)
async def export_graph(
    request: Request,
) -> ApiResponse:
    """Exportiert den Tenant-Graph als JSON (node-link Format)."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    data = await kg.export_graph(tenant_id=tenant_id)
    return ApiResponse(success=True, data=data)


@router.post("/import", response_model=ApiResponse)
async def import_graph(
    request: Request,
    body: GraphImportRequest,
) -> ApiResponse:
    """Importiert einen Graph aus JSON (node-link Format)."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    try:
        kg = await get_knowledge_graph()
        stats = await kg.import_graph(
            tenant_id=tenant_id, data=body.data, merge=body.merge
        )
        return ApiResponse(success=True, data=stats)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fehler beim Import")
        raise HTTPException(status_code=500, detail="Graph import failed.") from exc


@router.get("/visualization", response_model=ApiResponse)
async def get_visualization_data(
    request: Request,
    entity_type: str | None = None,
    limit: int = 200,
) -> ApiResponse:
    """
    Gibt Graph-Daten im Cytoscape.js-Format zurück für Frontend-Visualisierung.
    """
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    kg = await get_knowledge_graph()
    graph_data = await kg.export_graph(tenant_id=tenant_id)

    # Konvertiere zu Cytoscape-Format
    nodes = []
    edges = []

    type_colors = {
        EntityType.MODULE: "#3498db",  # Blue
        EntityType.SERVICE: "#2ecc71",  # Green
        EntityType.HOST: "#e74c3c",  # Red
        EntityType.CONFIGURATION: "#f39c12",  # Orange
        EntityType.INCIDENT: "#9b59b6",  # Purple
        EntityType.USER: "#1abc9c",  # Teal
        EntityType.TAG: "#95a5a6",  # Gray
        EntityType.RUNBOOK: "#e67e22",  # Dark Orange
        EntityType.WORKFLOW: "#34495e",  # Dark Gray
        EntityType.AGENT: "#16a085",  # Dark Teal
    }

    for node in graph_data.get("nodes", []):
        if entity_type and node.get("type") != entity_type:
            continue

        nodes.append(
            {
                "data": {
                    "id": node.get("id"),
                    "label": node.get("name", node.get("id")),
                    "type": node.get("type"),
                    "color": type_colors.get(node.get("type"), "#7f8c8d"),
                    **{
                        k: v for k, v in node.items() if k not in ["id", "name", "type"]
                    },
                }
            }
        )

        if len(nodes) >= limit:
            break

    node_ids = {n["data"]["id"] for n in nodes}

    for edge in graph_data.get("links", []):
        source = edge.get("source")
        target = edge.get("target")

        # Nur Edges wo beide Nodes im gefilterten Set sind
        if source in node_ids and target in node_ids:
            edges.append(
                {
                    "data": {
                        "id": f"{source}->{target}",
                        "source": source,
                        "target": target,
                        "label": edge.get("relation", "rel"),
                        **{
                            k: v
                            for k, v in edge.items()
                            if k not in ["source", "target", "relation"]
                        },
                    }
                }
            )

    return ApiResponse(
        success=True,
        data={
            "elements": nodes + edges,
            "stats": {
                "nodes": len(nodes),
                "edges": len(edges),
            },
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Demo Seed
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/seed", response_model=ApiResponse)
async def seed_demo_data(request: Request) -> ApiResponse:
    """Seedet Demo-Daten in den Knowledge Graph: Modul-Inventar + Beispiel-Incidents.
    Idempotent: bereits vorhandene Entities werden nicht überschrieben.
    Nur für Admins — verhindert versehentliches Seeden durch User.
    """
    role = resolve_request_role(request)
    if role != ROLE_ADMIN:
        raise HTTPException(
            status_code=403, detail="Nur Admins dürfen Demo-Daten seeden."
        )

    auth_ctx = resolve_request_auth(request)
    tenant_id = auth_tenant_id(auth_ctx)
    kg = await get_knowledge_graph()

    modules = [
        ("module:proxmox", "module", "Proxmox VE", "hypervisor"),
        ("module:kubernetes", "module", "Kubernetes Cluster", "orchestrator"),
        ("module:pihole", "module", "Pi-hole DNS", "dns"),
        ("module:homeassistant", "module", "Home Assistant", "automation"),
        ("module:docker", "module", "Docker Host", "container"),
        ("module:fritzbox", "module", "FRITZ!Box Router", "network"),
        ("module:web_search", "module", "Web Search", "tool"),
        ("module:knowledge_graph", "module", "Knowledge Graph", "tool"),
    ]
    entities_created = 0
    for entity_id, etype, name, category in modules:
        if not await kg.entity_exists(tenant_id, entity_id):
            await kg.add_entity(
                tenant_id=tenant_id,
                entity_id=entity_id,
                entity_type=etype,
                name=name,
                properties={"category": category, "seeded": True},
            )
            entities_created += 1

    relationships = [
        ("module:proxmox", "module:kubernetes", "runs"),
        ("module:proxmox", "module:pihole", "runs"),
        ("module:kubernetes", "module:homeassistant", "manages"),
        ("module:docker", "module:kubernetes", "supports"),
        ("module:fritzbox", "module:proxmox", "connects_to"),
    ]
    rels_created = 0
    for source, target, rel_type in relationships:
        if await kg.entity_exists(tenant_id, source) and await kg.entity_exists(
            tenant_id, target
        ):
            try:
                await kg.add_relationship(
                    tenant_id=tenant_id,
                    source=source,
                    target=target,
                    relation_type=rel_type,
                )
                rels_created += 1
            except ValueError:
                pass

    incidents = [
        {
            "summary": "Pi-hole DNS-Lookup fehlgeschlagen",
            "details": "DNS-Resolver antwortet nicht. Container im CrashLoopBackOff.",
            "module": "pihole",
        },
        {
            "summary": "Proxmox API Timeout",
            "details": "Cluster-Health-Check schlägt fehl. Mehrere VMs nicht erreichbar.",
            "module": "proxmox",
        },
    ]
    incidents_created = 0
    tenant_key = (tenant_id or "default")[:8]
    for idx, inc in enumerate(incidents, start=1):
        incident_id = f"incident:seed-{tenant_key}-{idx}"
        if not await kg.entity_exists(tenant_id, incident_id):
            await kg.add_entity(
                tenant_id=tenant_id,
                entity_id=incident_id,
                entity_type="incident",
                name=inc["summary"][:50],
                properties={
                    "module": inc["module"],
                    "summary": inc["summary"],
                    "details": inc["details"],
                    "status": "open",
                    "source": "seed",
                },
            )
            await kg.add_relationship(
                tenant_id=tenant_id,
                source=incident_id,
                target=f"module:{inc['module']}",
                relation_type="caused_by",
            )
            incidents_created += 1

    return ApiResponse(
        success=True,
        data={
            "tenant_id": tenant_id,
            "modules_seeded": entities_created,
            "relationships_seeded": rels_created,
            "incidents_seeded": incidents_created,
            "message": (
                f"Seed complete: +{entities_created} modules, "
                f"+{rels_created} relationships, +{incidents_created} incidents"
            ),
        },
    )
