from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core import knowledge_graph as kg_module
from core.knowledge_graph import (
    DEFAULT_TENANT_ID,
    EntityType,
    KnowledgeGraph,
    RelationType,
    _normalize_tenant_id,
)


@pytest.fixture
def tmp_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "core.config.get_settings",
        lambda: type("S", (), {"DATA_DIR": str(data_dir)})(),
    )
    monkeypatch.setattr(kg_module, "get_settings", lambda: type(
        "S", (), {"DATA_DIR": str(data_dir)}
    )())
    return data_dir


@pytest.fixture
def fresh_kg(tmp_data_dir: Path) -> KnowledgeGraph:
    kg_module.KnowledgeGraph._instance = None
    kg_module.KnowledgeGraph._default_tenant_warned = False
    return KnowledgeGraph()


@pytest.fixture(autouse=True)
def _reset_memory_mock() -> None:
    with patch.object(kg_module, "get_memory") as mock_mem:
        mem = mock_mem.return_value

        async def _noop_search(*args: object, **kwargs: object) -> list[dict]:
            return []

        async def _noop_store(*args: object, **kwargs: object) -> dict:
            return {}

        mem.search = _noop_search
        mem.store = _noop_store
        yield


def test_normalize_tenant_id_returns_default_for_empty() -> None:
    assert _normalize_tenant_id(None) == DEFAULT_TENANT_ID
    assert _normalize_tenant_id("") == DEFAULT_TENANT_ID
    assert _normalize_tenant_id("   ") == DEFAULT_TENANT_ID


def test_normalize_tenant_id_preserves_value() -> None:
    assert _normalize_tenant_id("customer-a") == "customer-a"
    assert _normalize_tenant_id("  trimmed  ") == "trimmed"


@pytest.mark.asyncio
async def test_add_and_get_entity_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    entity = await kg.add_entity(
        tenant_id="tenant-a",
        entity_id="host:pve1",
        entity_type=EntityType.HOST,
        name="PVE1",
        properties={"ip": "10.0.0.1"},
    )

    assert entity["id"] == "host:pve1"
    assert entity["tenant_id"] == "tenant-a"

    fetched = await kg.get_entity(tenant_id="tenant-a", entity_id="host:pve1")
    assert fetched is not None
    assert fetched["id"] == "host:pve1"
    assert fetched["tenant_id"] == "tenant-a"
    assert fetched["properties"]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_get_entity_returns_none_for_other_tenant(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a",
        entity_id="host:pve1",
        entity_type=EntityType.HOST,
        name="PVE1",
    )

    fetched = await kg.get_entity(tenant_id="tenant-b", entity_id="host:pve1")
    assert fetched is None


@pytest.mark.asyncio
async def test_update_entity_only_affects_owning_tenant(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a",
        entity_id="host:pve1",
        entity_type=EntityType.HOST,
        name="PVE1",
    )

    result_b = await kg.update_entity(
        tenant_id="tenant-b", entity_id="host:pve1", properties={"ip": "1.2.3.4"}
    )
    assert result_b is None

    result_a = await kg.update_entity(
        tenant_id="tenant-a",
        entity_id="host:pve1",
        properties={"ip": "10.0.0.1"},
    )
    assert result_a is not None
    assert result_a["properties"]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_delete_entity_only_affects_owning_tenant(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a",
        entity_id="host:pve1",
        entity_type=EntityType.HOST,
        name="PVE1",
    )

    deleted_b = await kg.delete_entity(tenant_id="tenant-b", entity_id="host:pve1")
    assert deleted_b is False

    deleted_a = await kg.delete_entity(tenant_id="tenant-a", entity_id="host:pve1")
    assert deleted_a is True

    fetched = await kg.get_entity(tenant_id="tenant-a", entity_id="host:pve1")
    assert fetched is None


@pytest.mark.asyncio
async def test_add_relationship_requires_both_tenants(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a",
        entity_id="host:pve1",
        entity_type=EntityType.HOST,
        name="PVE1",
    )
    await kg.add_entity(
        tenant_id="tenant-b",
        entity_id="host:pve2",
        entity_type=EntityType.HOST,
        name="PVE2",
    )

    with pytest.raises(ValueError):
        await kg.add_relationship(
            tenant_id="tenant-a",
            source="host:pve1",
            target="host:pve2",
            relation_type=RelationType.DEPENDS_ON,
        )

    rel = await kg.add_relationship(
        tenant_id="tenant-a",
        source="host:pve1",
        target="host:pve1",
        relation_type=RelationType.DEPENDS_ON,
    )
    assert rel["source"] == "host:pve1"


@pytest.mark.asyncio
async def test_find_by_type_is_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a2", entity_type=EntityType.HOST, name="A2"
    )
    await kg.add_entity(
        tenant_id="tenant-b", entity_id="host:b1", entity_type=EntityType.HOST, name="B1"
    )

    a_hosts = await kg.find_by_type(tenant_id="tenant-a", entity_type=EntityType.HOST)
    assert {e["id"] for e in a_hosts} == {"host:a1", "host:a2"}

    b_hosts = await kg.find_by_type(tenant_id="tenant-b", entity_type=EntityType.HOST)
    assert {e["id"] for e in b_hosts} == {"host:b1"}


@pytest.mark.asyncio
async def test_list_all_entities_tenant_scoped(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-b", entity_id="host:b1", entity_type=EntityType.HOST, name="B1"
    )

    a_entities = await kg.list_all_entities(tenant_id="tenant-a")
    assert {e["id"] for e in a_entities} == {"host:a1"}

    b_entities = await kg.list_all_entities(tenant_id="tenant-b")
    assert {e["id"] for e in b_entities} == {"host:b1"}


@pytest.mark.asyncio
async def test_get_neighbors_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a2", entity_type=EntityType.HOST, name="A2"
    )
    await kg.add_entity(
        tenant_id="tenant-b", entity_id="host:b1", entity_type=EntityType.HOST, name="B1"
    )

    await kg.add_relationship(
        tenant_id="tenant-a",
        source="host:a1",
        target="host:a2",
        relation_type=RelationType.DEPENDS_ON,
    )

    neighbors_a = await kg.get_neighbors(
        tenant_id="tenant-a", entity_id="host:a1"
    )
    assert any(n["entity"]["id"] == "host:a2" for n in neighbors_a)

    neighbors_b = await kg.get_neighbors(
        tenant_id="tenant-b", entity_id="host:a1"
    )
    assert neighbors_b == []


@pytest.mark.asyncio
async def test_get_path_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    for tid in ("tenant-a", "tenant-b"):
        await kg.add_entity(
            tenant_id=tid, entity_id="host:start", entity_type=EntityType.HOST, name="S"
        )
        await kg.add_entity(
            tenant_id=tid, entity_id="host:end", entity_type=EntityType.HOST, name="E"
        )
        await kg.add_relationship(
            tenant_id=tid,
            source="host:start",
            target="host:end",
            relation_type=RelationType.DEPENDS_ON,
        )

    paths_a = await kg.get_path(
        tenant_id="tenant-a", source="host:start", target="host:end"
    )
    assert paths_a is not None and len(paths_a) >= 1

    paths_cross = await kg.get_path(
        tenant_id="tenant-a", source="host:start", target="host:start"
    )
    assert paths_cross == [["host:start"]]

    paths_b_to_a = await kg.get_path(
        tenant_id="tenant-b", source="host:start", target="host:end"
    )
    assert paths_b_to_a is not None and len(paths_b_to_a) >= 1


@pytest.mark.asyncio
async def test_get_centrality_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-b", entity_id="host:b1", entity_type=EntityType.HOST, name="B1"
    )

    try:
        rank_a = await kg.get_centrality(tenant_id="tenant-a", top_k=10)
    except ModuleNotFoundError as exc:
        if "scipy" in str(exc):
            pytest.skip("scipy not installed (required by networkx.pagerank)")
        raise
    assert {r["entity_id"] for r in rank_a} == {"host:a1"}

    rank_b = await kg.get_centrality(tenant_id="tenant-b", top_k=10)
    assert {r["entity_id"] for r in rank_b} == {"host:b1"}


@pytest.mark.asyncio
async def test_find_communities_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a2", entity_type=EntityType.HOST, name="A2"
    )
    await kg.add_relationship(
        tenant_id="tenant-a",
        source="host:a1",
        target="host:a2",
        relation_type=RelationType.DEPENDS_ON,
    )

    comm_a = await kg.find_communities(tenant_id="tenant-a")
    assert len(comm_a) == 1
    assert {m["id"] for m in comm_a[0]["members"]} == {"host:a1", "host:a2"}

    comm_b = await kg.find_communities(tenant_id="tenant-b")
    assert comm_b == []


@pytest.mark.asyncio
async def test_export_graph_only_exports_tenant(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-b", entity_id="host:b1", entity_type=EntityType.HOST, name="B1"
    )

    data_a = await kg.export_graph(tenant_id="tenant-a")
    node_ids = {n["id"] for n in data_a["nodes"]}
    assert node_ids == {"host:a1"}
    for node in data_a["nodes"]:
        assert node["tenant_id"] == "tenant-a"

    data_b = await kg.export_graph(tenant_id="tenant-b")
    node_ids = {n["id"] for n in data_b["nodes"]}
    assert node_ids == {"host:b1"}


@pytest.mark.asyncio
async def test_import_graph_scoped_to_tenant(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    payload = {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "host:imported",
                "type": EntityType.HOST,
                "name": "Imported",
                "tenant_id": "tenant-other",
            }
        ],
        "edges": [],
    }

    stats = await kg.import_graph(tenant_id="tenant-b", data=payload)
    assert stats["nodes"] == 1

    imported = await kg.get_entity(tenant_id="tenant-b", entity_id="host:imported")
    assert imported is not None
    assert imported["tenant_id"] == "tenant-b"

    other_view = await kg.get_entity(tenant_id="tenant-a", entity_id="host:imported")
    assert other_view is None


@pytest.mark.asyncio
async def test_get_stats_tenant_scoped(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:a1", entity_type=EntityType.HOST, name="A1"
    )
    await kg.add_entity(
        tenant_id="tenant-b", entity_id="host:b1", entity_type=EntityType.HOST, name="B1"
    )

    stats_a = await kg.get_stats(tenant_id="tenant-a")
    assert stats_a["nodes"] == 1

    stats_b = await kg.get_stats(tenant_id="tenant-b")
    assert stats_b["nodes"] == 1

    stats_all = await kg.get_stats()
    assert stats_all["nodes"] == 2
    assert stats_all["tenants"] == 2


@pytest.mark.asyncio
async def test_per_tenant_persistence(
    tmp_data_dir: Path,
) -> None:
    kg_module.KnowledgeGraph._instance = None
    kg_module.KnowledgeGraph._default_tenant_warned = False
    kg1 = KnowledgeGraph()

    await kg1.add_entity(
        tenant_id="tenant-a", entity_id="host:1", entity_type=EntityType.HOST, name="H1"
    )
    await kg1.add_entity(
        tenant_id="tenant-b", entity_id="host:2", entity_type=EntityType.HOST, name="H2"
    )

    a_path = tmp_data_dir / "knowledge_graph" / "graph_tenant-a.json"
    b_path = tmp_data_dir / "knowledge_graph" / "graph_tenant-b.json"
    assert a_path.exists()
    assert b_path.exists()

    a_data = json.loads(a_path.read_text(encoding="utf-8"))
    b_data = json.loads(b_path.read_text(encoding="utf-8"))
    assert {n["id"] for n in a_data["nodes"]} == {"host:1"}
    assert {n["id"] for n in b_data["nodes"]} == {"host:2"}

    kg_module.KnowledgeGraph._instance = None
    kg_module.KnowledgeGraph._default_tenant_warned = False
    kg2 = KnowledgeGraph()

    a_entity = await kg2.get_entity(tenant_id="tenant-a", entity_id="host:1")
    b_entity = await kg2.get_entity(tenant_id="tenant-b", entity_id="host:2")
    assert a_entity is not None
    assert b_entity is not None
    assert a_entity["name"] == "H1"
    assert b_entity["name"] == "H2"
    assert a_entity["tenant_id"] == "tenant-a"
    assert b_entity["tenant_id"] == "tenant-b"

    assert (
        await kg2.get_entity(tenant_id="tenant-b", entity_id="host:1") is None
    )
    assert (
        await kg2.get_entity(tenant_id="tenant-a", entity_id="host:2") is None
    )


@pytest.mark.asyncio
async def test_node_has_tenant_id_attribute_for_defense_in_depth(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="tenant-a", entity_id="host:x", entity_type=EntityType.HOST, name="X"
    )

    raw_node = kg.get_node_data(tenant_id="tenant-a", entity_id="host:x")
    assert raw_node is not None
    assert raw_node["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_empty_tenant_id_uses_default(fresh_kg: KnowledgeGraph) -> None:
    kg = fresh_kg

    await kg.add_entity(
        tenant_id="", entity_id="host:default", entity_type=EntityType.HOST, name="D"
    )

    fetched = await kg.get_entity(tenant_id="default", entity_id="host:default")
    assert fetched is not None
    assert fetched["tenant_id"] == "default"


@pytest.mark.asyncio
async def test_extract_from_incident_tenant_scoped(
    fresh_kg: KnowledgeGraph,
) -> None:
    kg = fresh_kg

    result_a = await kg.extract_from_incident(
        tenant_id="tenant-a",
        module="proxmox",
        summary="Outage on PVE1",
        details="VM was down",
        resolution="Used a runbook",
    )
    assert result_a["entities"]
    incident_id_a = next(
        (e for e in result_a["entities"] if e.startswith("incident:")), None
    )
    assert incident_id_a is not None

    a_incidents = await kg.find_by_type(tenant_id="tenant-a", entity_type="incident")
    assert any(i["id"] == incident_id_a for i in a_incidents)
    for inc in a_incidents:
        assert inc.get("tenant_id") == "tenant-a"

    b_incidents = await kg.find_by_type(tenant_id="tenant-b", entity_type="incident")
    assert b_incidents == []
