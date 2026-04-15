"""
API Smoke Tests - Quick health checks for critical endpoints.

Run with: pytest backend/tests/test_api_smoke.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_api_root_health():
    """Test that API root responds."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/health")
        assert response.status_code in (200, 503)  # 503 is ok if redis not ready


@pytest.mark.unit
async def test_api_agents_list():
    """Test agents list endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/agents/")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data


@pytest.mark.unit
async def test_api_workflows_list():
    """Test workflows list endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/workflows/")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data


@pytest.mark.unit
async def test_api_modules_list():
    """Test modules list endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/modules/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.unit
async def test_api_settings_llm_providers():
    """Test LLM providers endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/settings/llm/providers")
        assert response.status_code == 200


@pytest.mark.unit
async def test_api_skills_list():
    """Test skills list endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/skills/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.unit
async def test_api_scripting_list():
    """Test scripting list endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/scripting/scripts")
        assert response.status_code == 200
        data = response.json()
        assert "scripts" in data


@pytest.mark.unit
async def test_api_codelab_languages():
    """Test codelab languages endpoint."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/codelab/languages")
        assert response.status_code == 200
