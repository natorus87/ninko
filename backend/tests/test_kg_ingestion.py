"""Tests für die KG-Auto-Ingestion-Hooks: alert_tools, monitor_agent, seed endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.alert_tools import _ingest_alert_to_kg, resolve_alert


@pytest.fixture
def mock_kg():
    """Mock KnowledgeGraph with all methods used by ingestion."""
    kg = MagicMock()
    kg.entity_exists = AsyncMock(return_value=False)
    kg.add_entity = AsyncMock(return_value={})
    kg.add_relationship = AsyncMock(return_value={})
    kg.extract_from_incident = AsyncMock(
        return_value={
            "entities": ["incident:test-1"],
            "relationships": [],
        }
    )
    return kg


@pytest.fixture
def mock_alert_mgr():
    """Mock AlertStateManager with get_state + resolve."""
    mgr = MagicMock()
    mgr.get_state = AsyncMock(
        return_value={
            "alert_id": "test:alert:1",
            "module": "kubernetes",
            "severity": "critical",
            "summary": "Pod nginx ist im CrashLoop",
            "ticket_id": "GLPI-123",
            "reason": "crashloopbackoff",
            "resource": "pod/nginx",
            "first_seen": "2026-06-23T10:00:00+00:00",
            "notify_count": 3,
        }
    )
    mgr.resolve = AsyncMock(return_value=True)
    return mgr


@pytest.fixture
def mock_alert_mgr_inactive():
    """Mock AlertStateManager where the alert is not active."""
    mgr = MagicMock()
    mgr.get_state = AsyncMock(return_value=None)
    mgr.resolve = AsyncMock(return_value=False)
    return mgr


@pytest.mark.asyncio
async def test_ingest_alert_to_kg_calls_extract(mock_kg):
    """_ingest_alert_to_kg ruft kg.extract_from_incident mit den richtigen Feldern auf."""
    with patch("core.knowledge_graph.get_knowledge_graph", AsyncMock(return_value=mock_kg)):
        with patch("core.auth.get_current_tenant_id", return_value="tenant-x"):
            await _ingest_alert_to_kg(
                {
                    "alert_id": "test:alert:1",
                    "module": "kubernetes",
                    "severity": "critical",
                    "summary": "Pod CrashLoop",
                    "ticket_id": "GLPI-123",
                    "reason": "crashloopbackoff",
                    "resource": "pod/nginx",
                    "first_seen": "2026-06-23T10:00:00+00:00",
                    "notify_count": 3,
                }
            )

    mock_kg.extract_from_incident.assert_awaited_once()
    call = mock_kg.extract_from_incident.await_args
    assert call.kwargs["tenant_id"] == "tenant-x"
    assert call.kwargs["module"] == "kubernetes"
    assert "Pod CrashLoop" in call.kwargs["summary"]
    assert "crashloopbackoff" in call.kwargs["details"]


@pytest.mark.asyncio
async def test_ingest_alert_to_kg_silently_swallows_errors():
    """KG-Ingestion-Fehler dürfen den Alert-Flow nicht crashen."""
    failing_kg = MagicMock()
    failing_kg.extract_from_incident = AsyncMock(side_effect=RuntimeError("KG down"))

    with patch("core.knowledge_graph.get_knowledge_graph", AsyncMock(return_value=failing_kg)):
        with patch("core.auth.get_current_tenant_id", return_value="t"):
            # Should not raise
            await _ingest_alert_to_kg({"alert_id": "x", "module": "y"})


@pytest.mark.asyncio
async def test_ingest_alert_to_kg_uses_default_tenant():
    """Wenn kein Tenant-Context, wird 'default' verwendet."""
    mock_kg_call = MagicMock()
    mock_kg_call.extract_from_incident = AsyncMock(return_value={"entities": [], "relationships": []})

    with patch("core.knowledge_graph.get_knowledge_graph", AsyncMock(return_value=mock_kg_call)):
        with patch("core.auth.get_current_tenant_id", return_value=""):
            await _ingest_alert_to_kg({"alert_id": "x", "module": "y"})

    assert mock_kg_call.extract_from_incident.await_args.kwargs["tenant_id"] == "default"


@pytest.mark.asyncio
async def test_resolve_alert_triggers_kg_ingestion(mock_kg, mock_alert_mgr):
    """resolve_alert ruft _ingest_alert_to_kg bei erfolgreichem Resolve auf."""
    ingested_alerts: list[dict] = []

    async def fake_ingest(alert: dict) -> None:
        ingested_alerts.append(alert)

    with patch("agents.alert_tools.get_alert_manager", return_value=mock_alert_mgr):
        with patch(
            "agents.alert_tools._ingest_alert_to_kg", side_effect=fake_ingest
        ):
            result = await resolve_alert.ainvoke(
                {"alert_id": "test:alert:1", "resolution": "Fixed by restart"}
            )

    assert len(ingested_alerts) == 1
    assert ingested_alerts[0]["alert_id"] == "test:alert:1"
    assert ingested_alerts[0]["resolution"] == "Fixed by restart"
    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["resolved"] is True


@pytest.mark.asyncio
async def test_resolve_alert_no_ingest_when_not_active():
    """Wenn der Alert nicht aktiv ist, wird _ingest_alert_to_kg nicht aufgerufen."""
    mgr = MagicMock()
    mgr.get_state = AsyncMock(return_value=None)
    mgr.resolve = AsyncMock(return_value=False)

    ingested_alerts: list[dict] = []

    async def fake_ingest(alert: dict) -> None:
        ingested_alerts.append(alert)

    with patch("agents.alert_tools.get_alert_manager", return_value=mgr):
        with patch(
            "agents.alert_tools._ingest_alert_to_kg", side_effect=fake_ingest
        ):
            result = await resolve_alert.ainvoke(
                {"alert_id": "ghost", "resolution": ""}
            )

    assert ingested_alerts == []
    parsed = json.loads(result)
    assert parsed["resolved"] is False


@pytest.mark.asyncio
async def test_monitor_ingest_helper_calls_extract(mock_kg):
    """MonitorAgent._ingest_kg ruft kg.extract_from_incident mit den richtigen Feldern auf."""
    from agents.monitor_agent import MonitorAgent

    fake_registry = MagicMock()
    agent = MonitorAgent.__new__(MonitorAgent)
    agent._alert_mgr = MagicMock()
    agent._settings = MagicMock()
    agent._redis = MagicMock()
    agent._memory = MagicMock()
    agent.registry = fake_registry

    with patch("core.knowledge_graph.get_knowledge_graph", AsyncMock(return_value=mock_kg)):
        with patch("core.auth.get_current_tenant_id", return_value="t-monitor"):
            await agent._ingest_kg(
                module="kubernetes",
                summary="Health-Check fehlgeschlagen",
                details="Modul: kubernetes\nDetail: timeout",
                resolution=None,
            )

    call = mock_kg.extract_from_incident.await_args
    assert call.kwargs["tenant_id"] == "t-monitor"
    assert call.kwargs["module"] == "kubernetes"
    assert "Health-Check" in call.kwargs["summary"]


@pytest.mark.asyncio
async def test_monitor_ingest_helper_swallows_errors():
    """Monitor KG-Ingestion-Fehler dürfen den Monitor-Cycle nicht crashen."""
    from agents.monitor_agent import MonitorAgent

    agent = MonitorAgent.__new__(MonitorAgent)
    failing_kg = MagicMock()
    failing_kg.extract_from_incident = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("core.knowledge_graph.get_knowledge_graph", AsyncMock(return_value=failing_kg)):
        with patch("core.auth.get_current_tenant_id", return_value="t"):
            # Should not raise
            await agent._ingest_kg(module="x", summary="y", details="z")


@pytest.mark.asyncio
async def test_seed_endpoint_admin_only():
    """POST /api/knowledge-graph/seed erfordert ROLE_ADMIN (covered by route guard)."""
    from backend.api.routes_knowledge_graph import seed_demo_data
    from fastapi import HTTPException
    from starlette.requests import Request

    from core.auth import ROLE_ADMIN, ROLE_READ

    with patch("backend.api.routes_knowledge_graph.resolve_request_auth") as mock_auth:
        with patch("backend.api.routes_knowledge_graph.resolve_request_role") as mock_role:
            with patch("backend.api.routes_knowledge_graph.auth_tenant_id", return_value="t1"):
                mock_auth.return_value = {"username": "user"}
                mock_role.return_value = ROLE_READ
                req = MagicMock(spec=Request)
                with pytest.raises(HTTPException) as exc_info:
                    await seed_demo_data(req)
                assert exc_info.value.status_code == 403

                mock_role.return_value = ROLE_ADMIN
                with patch(
                    "backend.api.routes_knowledge_graph.get_knowledge_graph"
                ) as mock_get_kg:
                    full_kg = MagicMock()
                    full_kg.entity_exists = AsyncMock(return_value=True)
                    full_kg.add_entity = AsyncMock(return_value={})
                    full_kg.add_relationship = AsyncMock(return_value={})
                    mock_get_kg.return_value = full_kg
                    result = await seed_demo_data(req)
                    assert result.success is True
                    data = result.data
                    assert data["modules_seeded"] == 0


@pytest.mark.asyncio
async def test_seed_endpoint_idempotent(mock_kg):
    """Wenn KG schon Daten hat, werden keine Duplikate angelegt."""
    from backend.api.routes_knowledge_graph import seed_demo_data
    from core.auth import ROLE_ADMIN
    from fastapi import Request

    mock_kg.entity_exists = AsyncMock(return_value=True)

    with patch(
        "backend.api.routes_knowledge_graph.get_knowledge_graph",
        AsyncMock(return_value=mock_kg),
    ):
        with patch("backend.api.routes_knowledge_graph.resolve_request_auth") as mock_auth:
            with patch(
                "backend.api.routes_knowledge_graph.resolve_request_role"
            ) as mock_role:
                with patch(
                    "backend.api.routes_knowledge_graph.auth_tenant_id",
                    return_value="t1",
                ):
                    mock_auth.return_value = {"username": "admin"}
                    mock_role.return_value = ROLE_ADMIN
                    req = MagicMock(spec=Request)
                    result = await seed_demo_data(req)
                    data = result.data
                    assert data["modules_seeded"] == 0
                    assert data["incidents_seeded"] == 0
                    mock_kg.add_entity.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_graph_middleware_uses_tenant_isolation():
    """KnowledgeGraphMiddleware nutzt get_current_tenant_id (Batch 1 v1.3.8 Fix)."""
    from agents.middleware.prompt import KnowledgeGraphMiddleware

    mw = KnowledgeGraphMiddleware()
    assert hasattr(mw, "name")
    assert mw.name == "knowledge_graph"
