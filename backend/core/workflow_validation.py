"""
Ninko – Workflow-Validierung.
Gemeinsamer Validator für Workflow-Definitionen (API-Routen, LLM-Tools) und
Condition-Expressions (Engine-Laufzeit).

Hinweis Multi-Replica: Die Validierung selbst ist zustandslos. Die Workflow-
Persistenz (JSON-Blobs + In-Process-Locks) ist nur für Single-Replica-Betrieb
ausgelegt — siehe core/workflow_engine.py.
"""

from __future__ import annotations

import re
from typing import get_args

from croniter import croniter

from schemas.workflows import WorkflowNode

# Aus dem Pydantic-Schema abgeleitet — keine zweite Wahrheitsquelle.
VALID_NODE_TYPES: frozenset[str] = frozenset(
    get_args(WorkflowNode.model_fields["type"].annotation)
)

# Muster für Condition-Expressions. Wird auch von der Engine
# (workflow_engine._evaluate_condition) zur Laufzeit-Auswertung genutzt.
CONDITION_PATTERNS: dict[str, re.Pattern] = {
    "contains": re.compile(r"output\.contains\(['\"](.+?)['\"]\)"),
    "startswith": re.compile(r"output\.startswith\(['\"](.+?)['\"]\)"),
    "endswith": re.compile(r"output\.endswith\(['\"](.+?)['\"]\)"),
    "matches": re.compile(r"output\.matches\(['\"](.+?)['\"]\)"),
    "output_len": re.compile(r"len\(output\)\s*([><=!]+)\s*(\d+)"),
    "variable": re.compile(r"variable\.(\w+)\s*([><=!]+)\s*['\"]?([^'\"]+?)['\"]?$"),
}


def is_valid_condition_expression(expr: str) -> bool:
    """Prüft, ob eine Condition-Expression einem bekannten Muster entspricht."""
    expr = (expr or "").strip()
    if not expr:
        return False
    if expr.lower() in ("true", "false"):
        return True
    return any(pattern.match(expr) for pattern in CONDITION_PATTERNS.values())


def _has_cycle(node_ids: list[str], edges: list[dict]) -> bool:
    """Zyklus-Erkennung via Kahn-Toposort auf den Edge-Paaren."""
    indegree = {nid: 0 for nid in node_ids}
    outgoing: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src = edge.get("source_id", "")
        tgt = edge.get("target_id", "")
        if src in indegree and tgt in indegree:
            outgoing[src].append(tgt)
            indegree[tgt] += 1

    queue = [nid for nid, deg in indegree.items() if deg == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for nxt in outgoing[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return visited < len(node_ids)


def validate_workflow_definition(
    nodes: list[dict],
    edges: list[dict],
    *,
    public_workflow_id: str = "",
) -> list[str]:
    """Validiert eine Workflow-Definition strukturell.

    Gibt eine Liste menschenlesbarer Fehler zurück (leer = valide).
    Wird von den API-Routen (422) UND den LLM-Tools (Fehlertext) genutzt.
    """
    errors: list[str] = []

    if not nodes:
        errors.append("Workflow enthält keine Nodes.")
        return errors

    node_ids: list[str] = []
    seen_ids: set[str] = set()
    for node in nodes:
        node_id = str(node.get("id", "")).strip()
        node_type = str(node.get("type", "")).strip()
        label = node.get("label") or node_id or node_type

        if not node_id:
            errors.append(f"Node '{label}' hat keine ID.")
            continue
        if node_id in seen_ids:
            errors.append(f"Doppelte Node-ID '{node_id}'.")
            continue
        seen_ids.add(node_id)
        node_ids.append(node_id)

        if node_type not in VALID_NODE_TYPES:
            errors.append(
                f"Node '{node_id}': unbekannter Typ '{node_type}'. "
                f"Erlaubt: {', '.join(sorted(VALID_NODE_TYPES))}."
            )
            continue

        config = node.get("config") or {}

        if node_type == "condition":
            expr = str(config.get("expression", "")).strip()
            if not is_valid_condition_expression(expr):
                errors.append(
                    f"Node '{node_id}': ungültige Condition-Expression '{expr}'. "
                    "Erlaubt: output.contains/startswith/endswith/matches('...'), "
                    "len(output) <op> N, variable.<name> <op> <wert>."
                )

        if node_type == "loop" and str(config.get("mode", "foreach")) == "while":
            expr = str(config.get("condition", "")).strip()
            if expr and not is_valid_condition_expression(expr):
                errors.append(f"Node '{node_id}': ungültige While-Condition '{expr}'.")

        if node_type == "trigger" and str(config.get("mode", "manual")) == "cron":
            cron_expr = str(config.get("cron", "")).strip()
            if not cron_expr or not croniter.is_valid(cron_expr):
                errors.append(
                    f"Node '{node_id}': ungültiger Cron-Ausdruck '{cron_expr}'. "
                    "Beispiel: '0 8 * * *'."
                )

        # Leere subflow.workflow_id / script.script_id sind als Entwurf erlaubt
        # (Templates liefern Platzhalter) — die Engine schlägt zur Laufzeit
        # sichtbar fehl. Nur Selbstreferenzen werden hier abgefangen.
        if node_type == "subflow":
            sub_id = str(config.get("workflow_id", "")).strip()
            if sub_id and public_workflow_id and sub_id == public_workflow_id:
                errors.append(f"Node '{node_id}': Subflow referenziert den eigenen Workflow.")

    valid_ids = set(node_ids)
    for edge in edges:
        src = str(edge.get("source_id", "")).strip()
        tgt = str(edge.get("target_id", "")).strip()
        if src not in valid_ids:
            errors.append(f"Edge referenziert unbekannte Quell-Node-ID '{src}'.")
        if tgt not in valid_ids:
            errors.append(f"Edge referenziert unbekannte Ziel-Node-ID '{tgt}'.")
        if src and src == tgt:
            errors.append(f"Edge von '{src}' auf sich selbst ist nicht erlaubt.")

    if not errors and _has_cycle(node_ids, edges):
        errors.append("Workflow enthält einen Zyklus — nur azyklische Graphen (DAG) sind erlaubt.")

    return errors
