"""
Tests für core/workflow_templates.py — alle Templates müssen vollständige,
valide Definitionen liefern (Regression zu leeren nodes_preview-Configs).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow_templates import (
    WORKFLOW_TEMPLATES,
    instantiate_template,
    load_template_definition,
)
from core.workflow_validation import validate_workflow_definition


@pytest.mark.parametrize("template", WORKFLOW_TEMPLATES, ids=lambda t: t["id"])
def test_template_definition_loads_with_nodes(template):
    definition = load_template_definition(template["id"])
    assert definition is not None, f"Template '{template['id']}' lädt nicht"
    assert definition.get("nodes"), f"Template '{template['id']}' hat keine Nodes"


@pytest.mark.parametrize("template", WORKFLOW_TEMPLATES, ids=lambda t: t["id"])
def test_template_nodes_have_nonempty_configs(template):
    definition = load_template_definition(template["id"])
    for node in definition.get("nodes", []):
        if node.get("type") in ("trigger", "end"):
            continue
        assert node.get("config"), (
            f"Template '{template['id']}': Node '{node.get('id')}' "
            f"({node.get('type')}) hat leere config"
        )


@pytest.mark.parametrize("template", WORKFLOW_TEMPLATES, ids=lambda t: t["id"])
def test_template_passes_validator(template):
    definition = load_template_definition(template["id"])
    errors = validate_workflow_definition(
        definition.get("nodes", []), definition.get("edges", [])
    )
    assert errors == [], f"Template '{template['id']}' invalide: {errors}"


@pytest.mark.parametrize("template", WORKFLOW_TEMPLATES, ids=lambda t: t["id"])
def test_template_instantiates_with_remapped_ids(template):
    instance = instantiate_template(template["id"], name="Testkopie")
    assert instance is not None
    node_ids = {n["id"] for n in instance["nodes"]}
    for edge in instance["edges"]:
        assert edge["source_id"] in node_ids
        assert edge["target_id"] in node_ids
