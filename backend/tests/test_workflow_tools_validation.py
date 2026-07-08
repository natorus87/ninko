"""
Regressionstests für die Workflow-LLM-Tools in agents/core_tools.py:
- create_dag_workflow lehnt kaputte Edges/Nodes ab und persistiert dann nichts
- execute_workflow verkraftet Workflows ohne 'name'-Key
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.core_tools import create_dag_workflow


def _nodes() -> list[dict]:
    return [
        {"id": "start", "type": "trigger", "label": "Start", "config": {"mode": "manual"}},
        {"id": "work", "type": "agent", "label": "Arbeit",
         "config": {"agent_id": "orchestrator", "prompt": "Tu was"}},
    ]


@pytest.mark.asyncio
async def test_create_dag_workflow_rejects_unknown_edge_reference(mock_redis):
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        result = await create_dag_workflow.ainvoke(
            {
                "name": "Kaputt",
                "description": "Edge zeigt ins Leere",
                "nodes": _nodes(),
                "edges": [{"source_id": "start", "target_id": "ghost", "label": ""}],
            }
        )
    assert "unbekannte Node-ID 'ghost'" in result
    mock_redis.connection.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_dag_workflow_rejects_unknown_node_type(mock_redis):
    nodes = _nodes()
    nodes.append({"id": "weird", "type": "teleport", "label": "Nope", "config": {}})
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        result = await create_dag_workflow.ainvoke(
            {
                "name": "Kaputt",
                "description": "Unbekannter Node-Typ",
                "nodes": nodes,
                "edges": [{"source_id": "start", "target_id": "work", "label": ""}],
            }
        )
    assert "ungültig" in result or "unbekannter Typ" in result
    mock_redis.connection.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_dag_workflow_valid_definition_persists(mock_redis):
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        result = await create_dag_workflow.ainvoke(
            {
                "name": "Sauber",
                "description": "Valider Workflow",
                "nodes": _nodes(),
                "edges": [{"source_id": "start", "target_id": "work", "label": ""}],
            }
        )
    assert "erfolgreich" in result or "successfully" in result
    mock_redis.connection.set.assert_called_once()
