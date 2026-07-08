"""
Tests für core/workflow_validation.py — den gemeinsamen Workflow-Validator.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow_validation import (
    VALID_NODE_TYPES,
    is_valid_condition_expression,
    validate_workflow_definition,
)


def _node(node_id: str, node_type: str = "agent", config: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "label": node_id, "config": config or {}}


def _edge(src: str, tgt: str, label: str = "") -> dict:
    return {"source_id": src, "target_id": tgt, "label": label}


def _valid_workflow() -> tuple[list[dict], list[dict]]:
    nodes = [
        _node("start", "trigger", {"mode": "manual"}),
        _node("work", "agent", {"agent_id": "orchestrator", "prompt": "Tu was"}),
        _node("done", "end", {"status": "succeeded"}),
    ]
    edges = [_edge("start", "work"), _edge("work", "done")]
    return nodes, edges


class TestNodeTypes:
    def test_valid_node_types_derived_from_schema(self):
        assert "agent" in VALID_NODE_TYPES
        assert "subflow" in VALID_NODE_TYPES
        assert "debate" in VALID_NODE_TYPES

    def test_valid_workflow_passes(self):
        nodes, edges = _valid_workflow()
        assert validate_workflow_definition(nodes, edges) == []

    def test_unknown_node_type_rejected(self):
        nodes, edges = _valid_workflow()
        nodes.append(_node("weird", "teleport"))
        errors = validate_workflow_definition(nodes, edges)
        assert any("unbekannter Typ 'teleport'" in e for e in errors)

    def test_empty_nodes_rejected(self):
        errors = validate_workflow_definition([], [])
        assert errors

    def test_duplicate_node_id_rejected(self):
        nodes, edges = _valid_workflow()
        nodes.append(_node("start", "end"))
        errors = validate_workflow_definition(nodes, edges)
        assert any("Doppelte Node-ID" in e for e in errors)


class TestEdges:
    def test_edge_with_unknown_source_rejected(self):
        nodes, edges = _valid_workflow()
        edges.append(_edge("ghost", "done"))
        errors = validate_workflow_definition(nodes, edges)
        assert any("unbekannte Quell-Node-ID 'ghost'" in e for e in errors)

    def test_edge_with_unknown_target_rejected(self):
        nodes, edges = _valid_workflow()
        edges.append(_edge("start", "ghost"))
        errors = validate_workflow_definition(nodes, edges)
        assert any("unbekannte Ziel-Node-ID 'ghost'" in e for e in errors)

    def test_self_loop_edge_rejected(self):
        nodes, edges = _valid_workflow()
        edges.append(_edge("work", "work"))
        errors = validate_workflow_definition(nodes, edges)
        assert any("auf sich selbst" in e for e in errors)

    def test_cycle_rejected(self):
        nodes = [_node("a"), _node("b"), _node("c")]
        edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "a")]
        errors = validate_workflow_definition(nodes, edges)
        assert any("Zyklus" in e for e in errors)


class TestConditionExpressions:
    def test_known_expressions_valid(self):
        assert is_valid_condition_expression("output.contains('error')")
        assert is_valid_condition_expression('output.startswith("OK")')
        assert is_valid_condition_expression("len(output) > 10")
        assert is_valid_condition_expression("variable.count >= 3")
        assert is_valid_condition_expression("true")
        assert is_valid_condition_expression("False")

    def test_unknown_expression_invalid(self):
        assert not is_valid_condition_expression("output.contians('typo')")
        assert not is_valid_condition_expression("")
        assert not is_valid_condition_expression("if error then panic")

    def test_condition_node_with_bad_expression_rejected(self):
        nodes, edges = _valid_workflow()
        nodes.append(_node("cond", "condition", {"expression": "kaputt"}))
        errors = validate_workflow_definition(nodes, edges)
        assert any("ungültige Condition-Expression" in e for e in errors)

    def test_loop_while_with_bad_condition_rejected(self):
        nodes, edges = _valid_workflow()
        nodes.append(_node("loop", "loop", {"mode": "while", "condition": "kaputt"}))
        errors = validate_workflow_definition(nodes, edges)
        assert any("ungültige While-Condition" in e for e in errors)


class TestTypeSpecificConfig:
    def test_cron_trigger_with_invalid_cron_rejected(self):
        nodes, edges = _valid_workflow()
        nodes[0] = _node("start", "trigger", {"mode": "cron", "cron": "not-a-cron"})
        errors = validate_workflow_definition(nodes, edges)
        assert any("ungültiger Cron-Ausdruck" in e for e in errors)

    def test_cron_trigger_with_valid_cron_passes(self):
        nodes, edges = _valid_workflow()
        nodes[0] = _node("start", "trigger", {"mode": "cron", "cron": "0 8 * * *"})
        assert validate_workflow_definition(nodes, edges) == []

    def test_subflow_with_empty_workflow_id_allowed_as_draft(self):
        # Templates liefern leere Platzhalter — als Entwurf speicherbar,
        # Laufzeitfehler bleibt sichtbar (Engine wirft ValueError).
        nodes, edges = _valid_workflow()
        nodes.append(_node("sub", "subflow", {"workflow_id": ""}))
        assert validate_workflow_definition(nodes, edges) == []

    def test_subflow_self_reference_rejected(self):
        nodes, edges = _valid_workflow()
        nodes.append(_node("sub", "subflow", {"workflow_id": "wf-self"}))
        errors = validate_workflow_definition(nodes, edges, public_workflow_id="wf-self")
        assert any("eigenen Workflow" in e for e in errors)

    def test_script_with_empty_script_id_allowed_as_draft(self):
        nodes, edges = _valid_workflow()
        nodes.append(_node("scr", "script", {}))
        assert validate_workflow_definition(nodes, edges) == []
