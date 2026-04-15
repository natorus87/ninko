"""
Integration tests for Scripting API.

Tests:
- Script CRUD
- Script execution via codelab integration
- Execution history

Run with pytest:
    cd backend && python -m pytest tests/test_scripting_integration.py -v
"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


client = TestClient(app)


class TestScriptingCRUD:
    def test_list_scripts_empty(self) -> None:
        response = client.get("/api/scripting/scripts")
        assert response.status_code == 200
        data = response.json()
        assert "scripts" in data
        assert "total" in data
        assert isinstance(data["scripts"], list)

    def test_create_and_get_script(self) -> None:
        script_id = f"test-script-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": f"Test Script {script_id}",
            "description": "Integration test script",
            "code": "#!/usr/bin/env python3\nprint('Hello, World!')",
            "language": "python",
            "timeout": 30,
            "tags": ["test", "integration"],
        }

        create_resp = client.post("/api/scripting/scripts", json=payload)
        assert create_resp.status_code == 201
        create_data = create_resp.json()
        assert "id" in create_data
        assert create_data["status"] == "created"

        script_id = create_data["id"]

        get_resp = client.get(f"/api/scripting/scripts/{script_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["name"] == payload["name"]
        assert get_data["description"] == payload["description"]

        code_resp = client.get(f"/api/scripting/scripts/{script_id}/code")
        assert code_resp.status_code == 200
        code_data = code_resp.json()
        assert "code" in code_data
        assert "print" in code_data["code"]

    def test_update_script(self) -> None:
        payload = {
            "name": "Original Script Name",
            "description": "Original description",
            "code": "print('original')",
            "timeout": 30,
        }
        create_resp = client.post("/api/scripting/scripts", json=payload)
        script_id = create_resp.json()["id"]

        update_payload = {
            "name": "Updated Script Name",
            "description": "Updated description",
            "code": "print('updated')",
            "timeout": 60,
        }
        update_resp = client.put(f"/api/scripting/scripts/{script_id}", json=update_payload)
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "updated"

        get_resp = client.get(f"/api/scripting/scripts/{script_id}")
        get_data = get_resp.json()
        assert get_data["name"] == "Updated Script Name"
        assert get_data["timeout"] == 60

    def test_delete_script(self) -> None:
        payload = {
            "name": "Script to Delete",
            "description": "Will be deleted",
            "code": "print('delete me')",
        }
        create_resp = client.post("/api/scripting/scripts", json=payload)
        script_id = create_resp.json()["id"]

        delete_resp = client.delete(f"/api/scripting/scripts/{script_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

        get_resp = client.get(f"/api/scripting/scripts/{script_id}")
        assert get_resp.status_code == 404

    def test_create_duplicate_name_fails(self) -> None:
        name = f"Duplicate Test {uuid.uuid4().hex[:8]}"
        payload = {
            "name": name,
            "description": "First script",
            "code": "print('first')",
        }
        client.post("/api/scripting/scripts", json=payload)

        duplicate_payload = {
            "name": name,
            "description": "Second script with same name",
            "code": "print('second')",
        }
        dup_resp = client.post("/api/scripting/scripts", json=duplicate_payload)
        assert dup_resp.status_code == 409


class TestScriptingExecution:
    def test_execute_simple_script(self) -> None:
        payload = {
            "name": "Simple Execution Test",
            "description": "Test basic execution",
            "code": "#!/usr/bin/env python3\nprint('Hello from script')\nprint('Line 2')",
            "timeout": 30,
        }
        create_resp = client.post("/api/scripting/scripts", json=payload)
        script_id = create_resp.json()["id"]

        exec_resp = client.post(f"/api/scripting/scripts/{script_id}/execute")
        assert exec_resp.status_code == 200
        result = exec_resp.json()

        assert result["script_id"] == script_id
        assert result["status"] in ["succeeded", "failed"]
        assert "stdout" in result
        assert "duration_ms" in result

        if result["status"] == "succeeded":
            assert "Hello from script" in result["stdout"]

    def test_execute_with_error(self) -> None:
        payload = {
            "name": "Error Script Test",
            "description": "Test error handling",
            "code": "#!/usr/bin/env python3\nraise ValueError('Intentional error')",
            "timeout": 30,
        }
        create_resp = client.post("/api/scripting/scripts", json=payload)
        script_id = create_resp.json()["id"]

        exec_resp = client.post(f"/api/scripting/scripts/{script_id}/execute")
        assert exec_resp.status_code == 200
        result = exec_resp.json()

        assert result["status"] == "failed"
        assert result["exit_code"] != 0

    def test_execution_history(self) -> None:
        payload = {
            "name": "History Test Script",
            "description": "Test history tracking",
            "code": "print('history test')",
        }
        create_resp = client.post("/api/scripting/scripts", json=payload)
        script_id = create_resp.json()["id"]

        client.post(f"/api/scripting/scripts/{script_id}/execute")

        history_resp = client.get(f"/api/scripting/scripts/{script_id}/executions")
        assert history_resp.status_code == 200
        history_data = history_resp.json()

        assert "executions" in history_data
        assert len(history_data["executions"]) >= 1

        first_exec = history_data["executions"][0]
        assert first_exec["script_id"] == script_id
        assert "status" in first_exec
        assert "started_at" in first_exec

    def test_list_all_executions(self) -> None:
        all_execs_resp = client.get("/api/scripting/executions")
        assert all_execs_resp.status_code == 200
        data = all_execs_resp.json()
        assert "executions" in data
        assert "total" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
