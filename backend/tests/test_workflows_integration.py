"""
Integration tests for Workflows API critical paths.

Tests:
- Workflow CRUD (Create, Read, Update, Delete)
- Workflow execution and run status
- Version management
- All node types support

Run with pytest:
    cd backend && python -m pytest tests/test_workflows_integration.py -v
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


def _create_test_workflow_payload(workflow_id: str) -> dict:
    return {
        "id": workflow_id,
        "name": f"Test Workflow {workflow_id}",
        "description": "Integration test workflow with all node types",
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
                "type": "agent",
                "label": "Agent Action",
                "config": {"agent_id": "", "prompt": "Say hello"},
                "position": {"x": 400, "y": 100},
            },
            {
                "id": "node-3",
                "type": "condition",
                "label": "Check Result",
                "config": {"expression": "true"},
                "position": {"x": 700, "y": 100},
            },
            {
                "id": "node-4",
                "type": "end",
                "label": "Finish",
                "config": {},
                "position": {"x": 1000, "y": 100},
            },
        ],
        "edges": [
            {"id": "e1", "source_id": "node-1", "target_id": "node-2"},
            {"id": "e2", "source_id": "node-2", "target_id": "node-3"},
            {"id": "e3", "source_id": "node-3", "target_id": "node-4"},
        ],
        "variables": [],
    }


class TestWorkflowsCRUD:
    def test_list_workflows(self) -> None:
        response = client.get("/api/workflows/")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert isinstance(data["workflows"], list)

    def test_create_and_get_workflow(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = _create_test_workflow_payload(workflow_id)

        create_resp = client.post("/api/workflows/", json=payload)
        assert create_resp.status_code == 201
        create_data = create_resp.json()
        assert create_data["id"] == workflow_id
        assert create_data["status"] == "created"

        get_resp = client.get(f"/api/workflows/{workflow_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == workflow_id
        assert get_data["name"] == payload["name"]
        assert len(get_data["nodes"]) == 4

    def test_update_workflow_creates_version(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        create_payload = _create_test_workflow_payload(workflow_id)
        client.post("/api/workflows/", json=create_payload)

        update_payload = {
            "name": "Updated Workflow Name",
            "description": "Updated description",
            "enabled": False,
            "nodes": create_payload["nodes"],
            "edges": create_payload["edges"],
        }

        update_resp = client.put(f"/api/workflows/{workflow_id}", json=update_payload)
        assert update_resp.status_code == 200
        update_data = update_resp.json()
        assert update_data["status"] == "updated"
        assert update_data["version"] == 2

    def test_delete_workflow(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        create_payload = _create_test_workflow_payload(workflow_id)
        client.post("/api/workflows/", json=create_payload)

        delete_resp = client.delete(f"/api/workflows/{workflow_id}")
        assert delete_resp.status_code == 200

        get_resp = client.get(f"/api/workflows/{workflow_id}")
        assert get_resp.status_code == 404


class TestWorkflowNodeTypes:
    def test_workflow_with_parallel_nodes(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": workflow_id,
            "name": "Parallel Test Workflow",
            "description": "Test parallel execution",
            "enabled": True,
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "label": "Start",
                    "config": {},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": "parallel-1",
                    "type": "parallel",
                    "label": "Run Parallel",
                    "config": {"branches": 2},
                    "position": {"x": 300, "y": 100},
                },
                {
                    "id": "end-1",
                    "type": "end",
                    "label": "End",
                    "config": {},
                    "position": {"x": 500, "y": 100},
                },
            ],
            "edges": [
                {"id": "e1", "source_id": "trigger-1", "target_id": "parallel-1"},
                {"id": "e2", "source_id": "parallel-1", "target_id": "end-1"},
            ],
            "variables": [],
        }

        response = client.post("/api/workflows/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["id"] == workflow_id

    def test_workflow_with_loop_node(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": workflow_id,
            "name": "Loop Test Workflow",
            "description": "Test loop execution",
            "enabled": True,
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "label": "Start",
                    "config": {},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": "loop-1",
                    "type": "loop",
                    "label": "Iterate",
                    "config": {"iterations": 3},
                    "position": {"x": 300, "y": 100},
                },
                {
                    "id": "end-1",
                    "type": "end",
                    "label": "End",
                    "config": {},
                    "position": {"x": 500, "y": 100},
                },
            ],
            "edges": [
                {"id": "e1", "source_id": "trigger-1", "target_id": "loop-1"},
                {"id": "e2", "source_id": "loop-1", "target_id": "end-1"},
            ],
            "variables": [],
        }

        response = client.post("/api/workflows/", json=payload)
        assert response.status_code == 201

    def test_workflow_with_subflow_node(self) -> None:
        """Test that workflows with subflow nodes are accepted and persisted correctly."""
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": workflow_id,
            "name": "Subflow Test Workflow",
            "description": "Test subflow node type",
            "enabled": True,
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"mode": "manual"},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": "subflow-1",
                    "type": "subflow",
                    "label": "Call Subflow",
                    "config": {"workflow_id": "some-other-workflow"},
                    "position": {"x": 400, "y": 100},
                },
                {
                    "id": "end-1",
                    "type": "end",
                    "label": "End",
                    "config": {"status": "succeeded"},
                    "position": {"x": 700, "y": 100},
                },
            ],
            "edges": [
                {"id": "e1", "source_id": "trigger-1", "target_id": "subflow-1"},
                {"id": "e2", "source_id": "subflow-1", "target_id": "end-1"},
            ],
            "variables": [],
        }

        response = client.post("/api/workflows/", json=payload)
        assert response.status_code == 201

        # Verify the workflow can be retrieved with correct node types
        get_resp = client.get(f"/api/workflows/{workflow_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        nodes = data.get("nodes", [])
        node_types = {n.get("type") for n in nodes}
        assert "subflow" in node_types, "Subflow node type should be persisted"

    def test_workflow_with_script_node(self) -> None:
        """Test that workflows with script nodes are accepted and persisted correctly."""
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": workflow_id,
            "name": "Script Test Workflow",
            "description": "Test script node type",
            "enabled": True,
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"mode": "manual"},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": "script-1",
                    "type": "script",
                    "label": "Execute Script",
                    "config": {"script_id": "test-script-123", "input_var": "", "timeout": "30"},
                    "position": {"x": 400, "y": 100},
                },
                {
                    "id": "end-1",
                    "type": "end",
                    "label": "End",
                    "config": {"status": "succeeded"},
                    "position": {"x": 700, "y": 100},
                },
            ],
            "edges": [
                {"id": "e1", "source_id": "trigger-1", "target_id": "script-1"},
                {"id": "e2", "source_id": "script-1", "target_id": "end-1"},
            ],
            "variables": [],
        }

        response = client.post("/api/workflows/", json=payload)
        assert response.status_code == 201

        # Verify the workflow can be retrieved with correct node types
        get_resp = client.get(f"/api/workflows/{workflow_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        nodes = data.get("nodes", [])
        node_types = {n.get("type") for n in nodes}
        assert "script" in node_types, "Script node type should be persisted"

        # Find the script node and verify its config
        script_node = next((n for n in nodes if n.get("type") == "script"), None)
        assert script_node is not None
        assert script_node.get("config", {}).get("script_id") == "test-script-123"
        assert script_node.get("config", {}).get("timeout") == "30"


class TestWorkflowTemplates:
    def test_templates_endpoint_returns_template_list(self) -> None:
        response = client.get("/api/workflows/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)
        assert any(item.get("id") == "script-automation" for item in data["templates"])

    def test_instantiate_template_creates_fetchable_workflow(self) -> None:
        response = client.post("/api/workflows/templates/script-automation/instantiate")
        assert response.status_code == 200
        data = response.json()
        workflow_id = data["id"]

        get_resp = client.get(f"/api/workflows/{workflow_id}")
        assert get_resp.status_code == 200
        workflow = get_resp.json()
        assert workflow["id"] == workflow_id
        assert workflow["name"]


class TestWorkflowVersions:
    def test_list_workflow_versions(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = _create_test_workflow_payload(workflow_id)
        client.post("/api/workflows/", json=payload)

        for i in range(2):
            update_payload = {
                **payload,
                "name": f"Version {i + 2}",
            }
            client.put(f"/api/workflows/{workflow_id}", json=update_payload)

        versions_resp = client.get(f"/api/workflows/{workflow_id}/versions")
        assert versions_resp.status_code == 200
        versions_data = versions_resp.json()

        assert "versions" in versions_data
        assert len(versions_data["versions"]) >= 3


@pytest.mark.skipif(
    os.getenv("NINKO_FULL_APP_TESTS") != "1",
    reason="Braucht App-Lifespan (app.state.orchestrator für /run) — mit NINKO_FULL_APP_TESTS=1 aktivieren",
)
class TestWorkflowRuns:
    def test_run_workflow_and_get_status(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = _create_test_workflow_payload(workflow_id)
        client.post("/api/workflows/", json=payload)

        run_resp = client.post(f"/api/workflows/{workflow_id}/run")
        assert run_resp.status_code == 202
        run_data = run_resp.json()

        assert "run_id" in run_data
        assert "status" in run_data

        run_id = run_data["run_id"]

        status_resp = client.get(f"/api/workflows/runs/{run_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()

        assert "id" in status_data
        assert "status" in status_data
        assert status_data["id"] == run_id

    def test_list_workflow_runs(self) -> None:
        workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
        payload = _create_test_workflow_payload(workflow_id)
        client.post("/api/workflows/", json=payload)

        client.post(f"/api/workflows/{workflow_id}/run")

        runs_resp = client.get(f"/api/workflows/{workflow_id}/runs")
        assert runs_resp.status_code == 200
        runs_data = runs_resp.json()

        assert "runs" in runs_data
        assert len(runs_data["runs"]) >= 1


class TestWorkflowStepRetry:
    """Test suite for Workflow Step Retry functionality."""

    def test_retry_endpoint_exists(self) -> None:
        """Test that retry endpoint returns appropriate error for non-existent run."""
        fake_run_id = "non-existent-run-12345"
        response = client.post(f"/api/workflows/runs/{fake_run_id}/steps/0/retry")
        assert response.status_code == 404

    @pytest.mark.skipif(
        os.getenv("NINKO_FULL_APP_TESTS") != "1",
        reason="Braucht App-Lifespan (app.state.orchestrator für /run) — mit NINKO_FULL_APP_TESTS=1 aktivieren",
    )
    def test_retry_requires_failed_step(self) -> None:
        """Test that retry only works on failed steps."""
        # Create and run a workflow to get a real run_id
        workflow_id = f"test-retry-wf-{uuid.uuid4().hex[:8]}"
        payload = _create_test_workflow_payload(workflow_id)
        client.post("/api/workflows/", json=payload)

        # Start run
        run_resp = client.post(f"/api/workflows/{workflow_id}/run")
        assert run_resp.status_code == 202
        run_data = run_resp.json()
        run_id = run_data["run_id"]

        # Try to retry step 0 (which is trigger - not failed)
        # This should fail because step is not in failed state
        retry_resp = client.post(f"/api/workflows/runs/{run_id}/steps/0/retry")
        # Returns 400 because step is not failed, or 404 if run not yet persisted
        assert retry_resp.status_code in [400, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
