"""
Conftest for Ninko tests.

Provides shared fixtures for testing.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=True)
    redis_mock.connection = MagicMock()
    redis_mock.connection.get = AsyncMock(return_value=None)
    redis_mock.connection.set = AsyncMock(return_value=True)
    return redis_mock


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return {
        "content": '{"name": "Test Agent", "description": "Test", "system_prompt": "You are a test.", "suggested_modules": []}'
    }


@pytest.fixture
def sample_agent_data():
    """Sample agent data for testing."""
    return {
        "id": "test-agent-123",
        "name": "Test Agent",
        "description": "A test agent",
        "system_prompt": "You are a test agent.",
        "enabled": True,
        "module_names": ["web_search"],
        "steps": [],
        "llm_provider_id": "test-provider",
    }


@pytest.fixture
def sample_workflow_data():
    """Sample workflow data for testing."""
    return {
        "id": "test-workflow-123",
        "name": "Test Workflow",
        "description": "A test workflow",
        "enabled": True,
        "nodes": [
            {
                "id": "node-1",
                "type": "trigger",
                "label": "Start",
                "config": {"mode": "manual"},
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "node-2",
                "type": "end",
                "label": "End",
                "config": {"status": "succeeded"},
                "position": {"x": 400, "y": 100},
            },
        ],
        "edges": [{"id": "edge-1", "source_id": "node-1", "target_id": "node-2"}],
        "variables": [],
    }


@pytest.fixture
def sample_script_data():
    """Sample script data for testing."""
    return {
        "id": "test-script-123",
        "name": "test-script",
        "description": "A test script",
        "code": "print('Hello, World!')",
        "language": "python",
        "timeout": 30,
        "tags": ["test", "example"],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "run_count": 0,
        "last_run_status": "idle",
    }
