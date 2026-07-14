"""
Integration tests for Agents API critical paths.

Tests:
- CRUD operations (Create, Read, Update, Delete)
- Agent generation with fallback behavior
- Template listing

Run with pytest:
    cd backend && python -m pytest tests/test_agents_integration.py -v

Or run directly:
    cd backend && python tests/test_agents_integration.py
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


pytestmark = pytest.mark.integration


client = TestClient(app)


class TestAgentsCRUD:
    """Test suite for Agent CRUD operations."""

    def test_list_agents_empty(self) -> None:
        response = client.get("/api/agents/")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "total" in data
        assert isinstance(data["agents"], list)

    # Hinweis Kontrakt: AgentCreate hat kein `id`-Feld — die Agent-ID wird
    # serverseitig generiert und im Create-Response zurückgegeben.

    def _create_agent(self, name: str, description: str = "", system_prompt: str = "Test.") -> str:
        payload = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
        }
        create_resp = client.post("/api/agents/", json=payload)
        assert create_resp.status_code == 201
        create_data = create_resp.json()
        assert create_data["status"] == "created"
        assert create_data["id"]
        return create_data["id"]

    def test_create_and_get_agent(self) -> None:
        suffix = uuid.uuid4().hex[:8]
        name = f"Test Agent {suffix}"
        agent_id = self._create_agent(
            name=name,
            description="Integration test agent",
            system_prompt="You are a test agent.",
        )

        get_resp = client.get(f"/api/agents/{agent_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == agent_id
        assert get_data["name"] == name
        assert get_data["description"] == "Integration test agent"

    def test_update_agent(self) -> None:
        agent_id = self._create_agent(
            name="Original Name",
            description="Original description",
            system_prompt="Original prompt.",
        )

        update_payload = {
            "name": "Updated Name",
            "description": "Updated description",
            "system_prompt": "Updated prompt.",
        }
        update_resp = client.put(f"/api/agents/{agent_id}", json=update_payload)
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "updated"

        get_resp = client.get(f"/api/agents/{agent_id}")
        get_data = get_resp.json()
        assert get_data["name"] == "Updated Name"
        assert get_data["description"] == "Updated description"

    def test_delete_agent(self) -> None:
        agent_id = self._create_agent(name="Agent to Delete", description="Will be deleted")

        delete_resp = client.delete(f"/api/agents/{agent_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

        get_resp = client.get(f"/api/agents/{agent_id}")
        assert get_resp.status_code == 404

    def test_duplicate_agent(self) -> None:
        agent_id = self._create_agent(name="Original Agent", description="Will be duplicated")

        dup_resp = client.post(f"/api/agents/{agent_id}/duplicate")
        assert dup_resp.status_code == 201
        dup_data = dup_resp.json()
        assert dup_data["status"] == "created"
        assert "id" in dup_data
        assert dup_data["id"] != agent_id


@pytest.mark.skipif(
    os.getenv("NINKO_FULL_APP_TESTS") != "1",
    reason="Braucht App-Lifespan (Modul-Registry für generate) — mit NINKO_FULL_APP_TESTS=1 aktivieren",
)
class TestAgentGeneration:
    """Test suite for Agent generation endpoint.

    Der generate-Endpoint greift auf die Modul-Registry zu, die erst der
    App-Lifespan initialisiert — der module-level TestClient startet keinen
    Lifespan, daher nur in Voll-Stack-Umgebungen lauffähig.
    """

    def test_generate_agent_with_use_case(self) -> None:
        payload = {
            "use_case": "Kubernetes cluster monitoring and pod diagnostics",
            "allowed_modules": ["kubernetes"],
        }

        response = client.post("/api/agents/generate", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "name" in data
        assert "description" in data
        assert "system_prompt" in data
        assert "suggested_modules" in data
        assert isinstance(data["suggested_modules"], list)

        assert len(data["name"]) > 0
        assert len(data["system_prompt"]) > 0

    def test_generate_agent_infers_modules(self) -> None:
        payload = {"use_case": "DNS blocking and firewall management"}

        response = client.post("/api/agents/generate", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "suggested_modules" in data
        modules = data["suggested_modules"]

        assert isinstance(modules, list)
        assert len(modules) > 0

        expected_modules = {"pihole", "opnsense", "linux_server"}
        assert any(m in expected_modules for m in modules)

    def test_generate_agent_empty_use_case_fails(self) -> None:
        payload = {"use_case": "   "}

        response = client.post("/api/agents/generate", json=payload)
        assert response.status_code == 422

    def test_generate_agent_fallback_on_error(self) -> None:
        payload = {
            "use_case": "Very specific custom task that might confuse the LLM " * 50,
        }

        response = client.post("/api/agents/generate", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "name" in data
        assert "_generation_info" in data

        gen_info = data["_generation_info"]
        assert "fallback_used" in gen_info

        if gen_info["fallback_used"]:
            assert "original_error" in gen_info

    def test_generate_agent_web_research_use_case(self) -> None:
        payload = {"use_case": "Internet research and web search automation"}

        response = client.post("/api/agents/generate", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "web_search" in data.get("suggested_modules", [])

    def test_generate_agent_provides_generation_info(self) -> None:
        """Verify that agent generation includes metadata about the process."""
        payload = {"use_case": "Kubernetes monitoring"}

        response = client.post("/api/agents/generate", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "_generation_info" in data
        gen_info = data["_generation_info"]

        assert "used_inferred_modules" in gen_info
        assert "fallback_used" in gen_info
        assert isinstance(gen_info["used_inferred_modules"], bool)
        assert isinstance(gen_info["fallback_used"], bool)

        if gen_info["fallback_used"]:
            assert "original_error" in gen_info
            assert len(gen_info["original_error"]) > 0


class TestAgentTemplates:
    """Test suite for Agent templates endpoint."""

    def test_list_templates(self) -> None:
        response = client.get("/api/agents/templates")
        assert response.status_code == 200
        data = response.json()

        assert "templates" in data
        assert isinstance(data["templates"], list)
        assert len(data["templates"]) > 0

        template = data["templates"][0]
        assert "id" in template
        assert "name" in template
        assert "system_prompt" in template


class TestAgentCards:
    """Test suite for AgentCards endpoint."""

    def test_get_agent_cards(self) -> None:
        response = client.get("/api/agents/cards")
        assert response.status_code == 200
        data = response.json()

        assert "cards" in data
        assert "total" in data
        assert isinstance(data["cards"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
