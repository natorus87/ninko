"""
Conftest for Ninko tests.

Provides shared fixtures for testing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Test-Isolation: sichere Settings BEVOR irgendein core-Modul geladen wird ─
#
# WICHTIG: Diese Env-Vars MÜSSEN auf Modul-Ebene gesetzt werden, nicht erst
# in einer Fixture! Viele Tests importieren `core.tool_registry` (oder
# transitiv `core.config`), was lazy `CoreSettings()` instantiiert. Ohne diese
# Vars wirft der Security-Validator ein ValueError. Da Test-Module oben im
# File stehen und beim pytest-Collect geladen werden, MUSS das vor dem ersten
# `import core.*` passieren — und conftest.py wird genau dort zuerst geladen.
os.environ.setdefault("SESSION_SECRET", "x" * 32)
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password-for-unit-tests")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password-for-unit-tests")
os.environ.setdefault("DEPLOYMENT_ENV", "development")
os.environ.setdefault("API_AUTH_ENABLED", "false")
os.environ.setdefault("CHROMADB_HOST", "localhost")
os.environ.setdefault("CHROMADB_PORT", "8000")


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


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
    redis_mock.connection.setex = AsyncMock(return_value=True)
    redis_mock.connection.delete = AsyncMock(return_value=True)
    redis_mock.connection.ttl = AsyncMock(return_value=-1)
    redis_mock.connection.lrange = AsyncMock(return_value=[])
    redis_mock.get_session_owner = AsyncMock(return_value=None)
    redis_mock.set_session_owner = AsyncMock(return_value=True)
    redis_mock.clear_session_owner = AsyncMock(return_value=True)
    redis_mock.get_chat_history = AsyncMock(return_value=[])
    redis_mock.store_chat_message = AsyncMock(return_value=True)
    redis_mock.clear_chat_history = AsyncMock(return_value=True)
    redis_mock.ui_history_get_all = AsyncMock(return_value=[])
    redis_mock.ui_history_save = AsyncMock(return_value=True)
    redis_mock.ui_history_delete = AsyncMock(return_value=True)
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
