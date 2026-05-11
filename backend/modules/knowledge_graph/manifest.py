"""
Knowledge Graph Module – Manifest.

Structured entity and relationship graph for IT operations.
Works alongside Semantic Memory (ChromaDB) for hybrid RAG.
"""

from __future__ import annotations

from core.module_registry import ModuleManifest
from agents.base_agent import _t


async def check_knowledge_graph_health() -> dict:
    """Health check for Knowledge Graph."""
    try:
        from core.knowledge_graph import get_knowledge_graph

        kg = await get_knowledge_graph()
        stats = await kg.get_stats()
        return {
            "status": "ok",
            "detail": _t(
                f"Knowledge Graph bereit: {stats['nodes']} Nodes, {stats['edges']} Edges",
                f"Knowledge Graph ready: {stats['nodes']} nodes, {stats['edges']} edges",
            ),
            "stats": stats,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="knowledge_graph",
    display_name="Knowledge Graph",
    description=(
        "Knowledge graph / KG: structured entity and relationship graph for IT operations. "
        "Dependencies, impact analysis, system topology, infrastructure relations, "
        "related systems, network topology, graph queries, RAG enrichment."
    ),
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="KG_",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "knowledge graph",
        "dependencies",
        "abhängigkeiten",
        "impact analysis",
        "entity relationships",
        "system topology",
        "infrastructure graph",
        "related systems",
        "graph query",
        "network topology",
    ],
    api_prefix="/api/knowledge-graph",
    dashboard_tab={
        "id": "knowledge_graph",
        "label": "Knowledge Graph",
        "icon": "🕸️",
    },
    health_check=check_knowledge_graph_health,
)
