"""
API-Tests für die Agent-Job-Endpoints in api/routes_agents.py.
Der AgentJobManager wird gemockt — getestet wird das HTTP-Verhalten.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.routes_agents import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _job(status: str = "pending") -> dict:
    return {
        "id": "job-123",
        "tenant_id": "default",
        "agent_id": "agent-1",
        "agent_name": "Test-Agent",
        "prompt": "Mach was",
        "status": status,
        "result": "Fertig." if status == "succeeded" else None,
        "error": None,
        "triggered_by": "api",
        "created_at": "2026-07-08T10:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
    }


def _mock_manager() -> MagicMock:
    manager = MagicMock()
    manager.start_job = AsyncMock(return_value=_job())
    manager.get_job = AsyncMock(return_value=_job("succeeded"))
    manager.list_jobs = AsyncMock(return_value=[_job("succeeded")])
    manager.cancel_job = AsyncMock(return_value=_job("cancelled"))
    return manager


class TestRunAgent:
    def test_run_returns_202_with_job_id(self, client):
        manager = _mock_manager()
        with patch("core.agent_jobs.get_agent_job_manager", return_value=manager):
            res = client.post("/api/agents/agent-1/run", json={"prompt": "Mach was"})
        assert res.status_code == 202
        body = res.json()
        assert body["job_id"] == "job-123"
        assert body["status"] == "pending"

    def test_run_unknown_agent_returns_404(self, client):
        manager = _mock_manager()
        manager.start_job = AsyncMock(side_effect=ValueError("Agent 'x' nicht im Pool gefunden."))
        with patch("core.agent_jobs.get_agent_job_manager", return_value=manager):
            res = client.post("/api/agents/ghost/run", json={"prompt": "Mach was"})
        assert res.status_code == 404

    def test_run_empty_prompt_rejected(self, client):
        res = client.post("/api/agents/agent-1/run", json={"prompt": ""})
        assert res.status_code == 422


class TestJobQueries:
    def test_get_job(self, client):
        with patch("core.agent_jobs.get_agent_job_manager", return_value=_mock_manager()):
            res = client.get("/api/agents/jobs/job-123")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "succeeded"
        assert "tenant_id" not in body

    def test_get_unknown_job_returns_404(self, client):
        manager = _mock_manager()
        manager.get_job = AsyncMock(return_value=None)
        with patch("core.agent_jobs.get_agent_job_manager", return_value=manager):
            res = client.get("/api/agents/jobs/ghost")
        assert res.status_code == 404

    def test_list_jobs_for_agent(self, client):
        with patch("core.agent_jobs.get_agent_job_manager", return_value=_mock_manager()):
            res = client.get("/api/agents/agent-1/jobs")
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["jobs"][0]["id"] == "job-123"


class TestCancel:
    def test_cancel_running_job(self, client):
        with patch("core.agent_jobs.get_agent_job_manager", return_value=_mock_manager()):
            res = client.post("/api/agents/jobs/job-123/cancel")
        assert res.status_code == 200
        assert res.json()["status"] == "cancelled"

    def test_cancel_terminal_job_returns_409(self, client):
        manager = _mock_manager()
        manager.cancel_job = AsyncMock(
            side_effect=ValueError("Job 'job-123' ist bereits beendet (succeeded).")
        )
        with patch("core.agent_jobs.get_agent_job_manager", return_value=manager):
            res = client.post("/api/agents/jobs/job-123/cancel")
        assert res.status_code == 409

    def test_cancel_unknown_job_returns_404(self, client):
        manager = _mock_manager()
        manager.cancel_job = AsyncMock(side_effect=ValueError("Job 'x' nicht gefunden."))
        with patch("core.agent_jobs.get_agent_job_manager", return_value=manager):
            res = client.post("/api/agents/jobs/x/cancel")
        assert res.status_code == 404
