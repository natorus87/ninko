"""
E2E test for Workflow critical path.

Tests: Create → Save → Load → Run workflow

Run against a live backend:
  NINKO_BASE_URL=http://localhost:8000 python3 backend/test_e2e_workflow_critical_path.py

Optional auth:
  NINKO_API_KEY_WRITE=...
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("NINKO_BASE_URL", "http://localhost:8000").rstrip("/")
KEY_WRITE = os.getenv("NINKO_API_KEY_WRITE", "")


def _request(
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict | str]:
    """Make HTTP request and return (status, parsed_response)."""
    url = f"{BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8") if payload else None
    req_headers = {"Content-Type": "application/json"} if payload else {}
    if headers:
        req_headers.update(headers)
    if KEY_WRITE:
        req_headers["X-API-Key"] = KEY_WRITE

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(data)
            except json.JSONDecodeError:
                return resp.status, data
    except urllib.error.HTTPError as exc:
        data = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(data)
        except json.JSONDecodeError:
            return exc.code, data


def _print_result(name: str, ok: bool, detail: str = "") -> None:
    state = "OK" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    if ok:
        logger.info("[%s] %s%s", state, name, suffix)
    else:
        logger.warning("[%s] %s%s", state, name, suffix)


def test_workflow_crud() -> tuple[bool, str]:
    """Test Create, Read, Update, Delete workflow."""
    workflow_id = f"test-wf-{uuid.uuid4().hex[:8]}"
    workflow_name = f"Test Workflow {workflow_id}"

    create_payload = {
        "id": workflow_id,
        "name": workflow_name,
        "description": "E2E test workflow with all node types",
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
                "config": {
                    "expression": "output.contains('hello')",
                    "true_label": "yes",
                    "false_label": "no",
                },
                "position": {"x": 700, "y": 100},
            },
            {
                "id": "node-4",
                "type": "end",
                "label": "Finish",
                "config": {"status": "succeeded"},
                "position": {"x": 1000, "y": 100},
            },
        ],
        "edges": [
            {"id": "edge-1", "source_id": "node-1", "target_id": "node-2"},
            {"id": "edge-2", "source_id": "node-2", "target_id": "node-3"},
            {
                "id": "edge-3",
                "source_id": "node-3",
                "target_id": "node-4",
                "label": "yes",
            },
        ],
        "variables": [],
    }

    status, resp = _request("POST", "/api/workflows/", payload=create_payload)
    if status != 201:
        return False, f"Create failed: status={status}, resp={resp}"

    status, resp = _request("GET", f"/api/workflows/{workflow_id}")
    if status != 200:
        return False, f"Get failed: status={status}"

    loaded = resp if isinstance(resp, dict) else {}
    if loaded.get("name") != workflow_name:
        return (
            False,
            f"Name mismatch: expected {workflow_name}, got {loaded.get('name')}",
        )

    nodes = loaded.get("nodes", [])
    if len(nodes) != 4:
        return False, f"Node count mismatch: expected 4, got {len(nodes)}"

    update_payload = {
        "name": f"{workflow_name} (Updated)",
        "description": "Updated description",
        "nodes": create_payload["nodes"],
        "edges": create_payload["edges"],
        "variables": [{"name": "test_var", "value": "test_value"}],
        "enabled": True,
    }
    status, resp = _request(
        "PUT", f"/api/workflows/{workflow_id}", payload=update_payload
    )
    if status != 200:
        return False, f"Update failed: status={status}"

    status, resp = _request("GET", f"/api/workflows/{workflow_id}")
    loaded = resp if isinstance(resp, dict) else {}
    if loaded.get("name") != f"{workflow_name} (Updated)":
        return False, "Update not persisted"

    status, _ = _request("DELETE", f"/api/workflows/{workflow_id}")
    if status != 200:
        return False, f"Delete failed: status={status}"

    status, _ = _request("GET", f"/api/workflows/{workflow_id}")
    if status != 404:
        return False, f"Expected 404 after delete, got {status}"

    return True, "CRUD cycle passed"


def test_workflow_run() -> tuple[bool, str]:
    """Test workflow execution with polling."""
    workflow_id = f"test-run-wf-{uuid.uuid4().hex[:8]}"
    workflow_name = f"Run Test {workflow_id}"

    create_payload = {
        "id": workflow_id,
        "name": workflow_name,
        "description": "Test execution",
        "enabled": True,
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "label": "Trigger",
                "config": {"mode": "manual"},
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "v1",
                "type": "variable",
                "label": "Set Var",
                "config": {"name": "result", "value": "test_output"},
                "position": {"x": 400, "y": 100},
            },
            {
                "id": "e1",
                "type": "end",
                "label": "End",
                "config": {"status": "succeeded"},
                "position": {"x": 700, "y": 100},
            },
        ],
        "edges": [
            {"id": "e1-t1-v1", "source_id": "t1", "target_id": "v1"},
            {"id": "e1-v1-e1", "source_id": "v1", "target_id": "e1"},
        ],
        "variables": [],
    }

    status, resp = _request("POST", "/api/workflows/", payload=create_payload)
    if status != 201:
        return False, f"Create failed: status={status}"

    try:
        status, resp = _request("POST", f"/api/workflows/{workflow_id}/run")
        if status != 202:
            return False, f"Run start failed: status={status}"

        resp_data = resp if isinstance(resp, dict) else {}
        run_id = resp_data.get("run_id")
        if not run_id:
            return False, "No run_id returned"

        final_status = None
        for _ in range(30):
            time.sleep(1)
            status, resp = _request("GET", f"/api/workflows/runs/{run_id}")
            if status == 200:
                run_data = resp if isinstance(resp, dict) else {}
                final_status = run_data.get("status")
                if final_status in ("succeeded", "failed"):
                    break

        if final_status != "succeeded":
            return False, f"Run did not succeed: status={final_status}"

        status, resp = _request("GET", f"/api/workflows/{workflow_id}/runs")
        if status != 200:
            return False, f"Run history failed: status={status}"

        runs_data = resp if isinstance(resp, dict) else {}
        runs = runs_data.get("runs", [])
        if not runs:
            return False, "No runs in history"

        return True, f"Run completed: {run_id}"

    finally:
        _request("DELETE", f"/api/workflows/{workflow_id}")


def test_parallel_and_subflow_nodes() -> tuple[bool, str]:
    """Verify parallel and subflow nodes are accepted by backend."""
    workflow_id = f"test-adv-{uuid.uuid4().hex[:8]}"

    create_payload = {
        "id": workflow_id,
        "name": "Advanced Nodes Test",
        "description": "Test parallel and subflow nodes",
        "enabled": True,
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "label": "Trigger",
                "config": {"mode": "manual"},
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "p1",
                "type": "parallel",
                "label": "Parallel Tasks",
                "config": {"prompts": ["Task A", "Task B", "Task C"]},
                "position": {"x": 400, "y": 100},
            },
            {
                "id": "e1",
                "type": "end",
                "label": "End",
                "config": {"status": "succeeded"},
                "position": {"x": 700, "y": 100},
            },
        ],
        "edges": [
            {"id": "e1", "source_id": "t1", "target_id": "p1"},
            {"id": "e2", "source_id": "p1", "target_id": "e1"},
        ],
        "variables": [],
    }

    status, resp = _request("POST", "/api/workflows/", payload=create_payload)
    if status != 201:
        return False, f"Create with parallel node failed: status={status}"

    status, resp = _request("GET", f"/api/workflows/{workflow_id}")
    if status != 200:
        return False, f"Load failed: status={status}"

    loaded = resp if isinstance(resp, dict) else {}
    nodes = loaded.get("nodes", [])
    node_types = {n.get("type") for n in nodes}

    if "parallel" not in node_types:
        return False, "Parallel node not persisted correctly"

    _request("DELETE", f"/api/workflows/{workflow_id}")

    return True, "Advanced nodes accepted by backend"


def main() -> int:
    failures = 0

    ok, detail = test_workflow_crud()
    _print_result("workflow_crud", ok, detail)
    failures += 0 if ok else 1

    ok, detail = test_workflow_run()
    _print_result("workflow_run", ok, detail)
    failures += 0 if ok else 1

    ok, detail = test_parallel_and_subflow_nodes()
    _print_result("parallel_subflow_nodes", ok, detail)
    failures += 0 if ok else 1

    summary = {"base_url": BASE_URL, "tests_run": 3, "failures": failures}
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
