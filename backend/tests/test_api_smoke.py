"""
API Smoke Tests - Quick health checks for critical endpoints.

Run with: pytest backend/tests/test_api_smoke.py -v

Optional environment variables:
- NINKO_BASE_URL (default: http://localhost:8000)
- NINKO_TEST_USERNAME
- NINKO_TEST_PASSWORD
- NINKO_API_KEY (used as X-API-Key when set)
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

BASE_URL = os.getenv("NINKO_BASE_URL", "http://localhost:8000")
TEST_USERNAME = os.getenv("NINKO_TEST_USERNAME", "").strip()
TEST_PASSWORD = os.getenv("NINKO_TEST_PASSWORD", "")
API_KEY = os.getenv("NINKO_API_KEY", "").strip()


async def _create_client() -> AsyncClient:
    headers: dict[str, str] = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    client = AsyncClient(base_url=BASE_URL, headers=headers)

    # If auth is cookie/session based and credentials are available, login once.
    if TEST_USERNAME and TEST_PASSWORD and not API_KEY:
        login_response = await client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        if login_response.status_code != 200:
            await client.aclose()
            raise AssertionError(
                "Login failed for smoke tests "
                f"({login_response.status_code}): {login_response.text}"
            )

    return client


@pytest.mark.integration
async def test_api_root_health():
    """Test that API health endpoint responds."""
    async with AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/health")
        assert response.status_code in (200, 503)  # 503 is ok if redis not ready


@pytest.mark.integration
async def test_api_agents_list():
    """Test agents list endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/agents/")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
    finally:
        await client.aclose()


@pytest.mark.integration
async def test_api_workflows_list():
    """Test workflows list endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/workflows/")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
    finally:
        await client.aclose()


@pytest.mark.integration
async def test_api_modules_list():
    """Test modules list endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/modules/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    finally:
        await client.aclose()


@pytest.mark.integration
async def test_api_settings_llm_providers():
    """Test LLM providers endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/settings/llm/providers")
        assert response.status_code == 200
    finally:
        await client.aclose()


@pytest.mark.integration
async def test_api_skills_list():
    """Test skills list endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/skills/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    finally:
        await client.aclose()


@pytest.mark.integration
async def test_api_scripting_list():
    """Test scripting list endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/scripting/scripts")
        assert response.status_code == 200
        data = response.json()
        assert "scripts" in data
    finally:
        await client.aclose()


@pytest.mark.integration
async def test_api_codelab_languages():
    """Test codelab languages endpoint."""
    client = await _create_client()
    try:
        response = await client.get("/api/codelab/languages")
        # In some deployments codelab can be present but runtime-incomplete.
        # Then this endpoint returns a controlled 500 JSON error.
        assert response.status_code in (200, 500)
        if response.status_code == 500:
            payload = response.json()
            assert isinstance(payload, dict)
            assert "error" in payload
    finally:
        await client.aclose()
