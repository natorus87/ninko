"""
Ninko – Workflow Templates.
Vordefinierte Workflow-Vorlagen für häufige IT-Operations-Use-Cases.
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_template(filename: str) -> dict | None:
    template_dir = Path(__file__).parent.parent / "data" / "workflows"
    template_path = template_dir / filename

    if not template_path.exists():
        return None

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


WORKFLOW_TEMPLATES: list[dict] = [
    {
        "id": "simple-sequential",
        "name": "Einfache Sequenz",
        "description": "Ein einfacher linearer Workflow: Trigger → Agent → Ende. Ideal für erste Schritte.",
        "category": "basic",
        "icon": "➡️",
        "tags": ["simple", "linear", "beginner"],
        "template_file": "template-simple-sequential.json",
    },
    {
        "id": "conditional-branching",
        "name": "Bedingte Verzweigung",
        "description": "Workflow mit Bedingung: Der Pfad wird basierend auf dem Agent-Ergebnis gewählt.",
        "category": "logic",
        "icon": "🔀",
        "tags": ["condition", "branching", "logic"],
        "template_file": "template-conditional-branching.json",
    },
    {
        "id": "parallel-processing",
        "name": "Parallele Verarbeitung",
        "description": "Führt mehrere Aufgaben gleichzeitig aus und sammelt die Ergebnisse.",
        "category": "advanced",
        "icon": "⚡",
        "tags": ["parallel", "concurrent", "performance"],
        "template_file": "template-parallel-processing.json",
    },
    {
        "id": "subflow-orchestration",
        "name": "Subflow Orchestration",
        "description": "Ruft einen anderen Workflow als Subflow auf und verarbeitet dessen Ergebnis.",
        "category": "advanced",
        "icon": "🔀",
        "tags": ["subflow", "orchestration", "modular"],
        "template_file": "template-subflow-orchestration.json",
    },
    {
        "id": "script-automation",
        "name": "Script Automation",
        "description": "Führt ein Python-Script aus und verarbeitet dessen Output. Ideal für deterministische Datenverarbeitung.",
        "category": "advanced",
        "icon": "📜",
        "tags": ["script", "automation", "code"],
        "template_file": "template-script-automation.json",
    },
    {
        "id": "daily-health-check",
        "name": "Daily Health Check",
        "description": "Automatischer System-Health-Check mit Benachrichtigung bei Problemen.",
        "category": "operations",
        "icon": "🏥",
        "tags": ["monitoring", "health", "daily", "automation"],
        "nodes_preview": [
            {"type": "trigger", "label": "Täglich 08:00"},
            {"type": "agent", "label": "System-Check"},
            {"type": "condition", "label": "Probleme gefunden?"},
            {"type": "agent", "label": "Benachrichtigung senden"},
            {"type": "end", "label": "Ende"},
        ],
    },
    {
        "id": "incident-response",
        "name": "Incident Response",
        "description": "Strukturierte Eskalation bei Incidents: Diagnose → Ticket → Benachrichtigung.",
        "category": "operations",
        "icon": "🚨",
        "tags": ["incident", "escalation", "ticketing", "alert"],
        "nodes_preview": [
            {"type": "trigger", "label": "Alert empfangen"},
            {"type": "agent", "label": "Erstdiagnose"},
            {"type": "condition", "label": "Kritisch?"},
            {"type": "agent", "label": "Ticket erstellen"},
            {"type": "agent", "label": "Team benachrichtigen"},
            {"type": "end", "label": "Ende"},
        ],
    },
    {
        "id": "backup-verification",
        "name": "Backup Verification",
        "description": "Backup durchführen, Verifizieren und bei Fehler alarmieren.",
        "category": "operations",
        "icon": "💾",
        "tags": ["backup", "verification", "maintenance"],
        "nodes_preview": [
            {"type": "trigger", "label": "Nächtlicher Cron"},
            {"type": "agent", "label": "Backup starten"},
            {"type": "agent", "label": "Backup verifizieren"},
            {"type": "condition", "label": "Erfolgreich?"},
            {"type": "agent", "label": "Erfolg loggen"},
            {"type": "agent", "label": "Alarm senden"},
            {"type": "end", "label": "Ende"},
        ],
    },
]


def get_workflow_templates() -> list[dict]:
    """Returns all workflow template definitions."""
    return WORKFLOW_TEMPLATES


def get_template_by_id(template_id: str) -> dict | None:
    """Returns a template by ID."""
    return next((t for t in WORKFLOW_TEMPLATES if t["id"] == template_id), None)


def load_template_definition(template_id: str) -> dict | None:
    """Loads the full template definition including nodes and edges."""
    template = get_template_by_id(template_id)
    if not template:
        return None

    template_file = template.get("template_file")
    if template_file:
        return _load_template(template_file)

    if "nodes_preview" in template:
        return {
            "id": template["id"],
            "name": template["name"],
            "description": template["description"],
            "nodes": [
                {
                    "id": f"node-{i}",
                    "type": n["type"],
                    "label": n["label"],
                    "config": {},
                    "position": {"x": 100 + i * 300, "y": 100},
                }
                for i, n in enumerate(template["nodes_preview"])
            ],
            "edges": [
                {
                    "id": f"edge-{i}",
                    "source_id": f"node-{i}",
                    "target_id": f"node-{i + 1}",
                }
                for i in range(len(template["nodes_preview"]) - 1)
            ],
            "variables": [],
        }

    return None


def instantiate_template(template_id: str, name: str | None = None) -> dict | None:
    """Creates a workflow instance from a template with a new ID."""
    import uuid

    definition = load_template_definition(template_id)
    if not definition:
        return None

    new_id = f"wf-{uuid.uuid4().hex[:8]}"
    new_name = name or f"{definition['name']} (Kopie)"

    instance = {
        "id": new_id,
        "name": new_name,
        "description": definition.get("description", ""),
        "nodes": definition.get("nodes", []),
        "edges": definition.get("edges", []),
        "variables": definition.get("variables", []),
        "enabled": True,
    }

    for node in instance["nodes"]:
        old_id = node["id"]
        new_node_id = f"node-{uuid.uuid4().hex[:4]}"
        node["id"] = new_node_id

        for edge in instance["edges"]:
            if edge.get("source_id") == old_id:
                edge["source_id"] = new_node_id
            if edge.get("target_id") == old_id:
                edge["target_id"] = new_node_id

    for edge in instance["edges"]:
        edge["id"] = f"edge-{uuid.uuid4().hex[:4]}"

    return instance
