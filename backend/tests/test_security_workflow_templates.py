"""Tests fuer die 5 Security-Workflow-Templates als echte Ninko-WorkflowEngine-
Workflows (Task 8) — kein neuer Node-Typ, Wiederverwendung des bestehenden
`agent`-Node-Typs (siehe modules/security/workflows.py Docstring fuer die
Architekturabwaegung)."""

from __future__ import annotations

import pytest

from core.workflow_templates import (
    WORKFLOW_TEMPLATES,
    get_template_by_id,
    instantiate_template,
    load_template_definition,
)
from core.workflow_validation import validate_workflow_definition

pytestmark = pytest.mark.unit

SECURITY_TEMPLATE_IDS = [
    "security-kubernetes-audit",
    "security-container-image-audit",
    "security-external-service-audit",
    "security-git-repository-audit",
    "security-ai-platform-audit",
]


def test_all_five_security_templates_registered():
    ids = {t["id"] for t in WORKFLOW_TEMPLATES}
    for template_id in SECURITY_TEMPLATE_IDS:
        assert template_id in ids


@pytest.mark.parametrize("template_id", SECURITY_TEMPLATE_IDS)
def test_template_file_loads_valid_json(template_id):
    template = get_template_by_id(template_id)
    assert template is not None
    definition = load_template_definition(template_id)
    assert definition is not None
    assert definition["nodes"]
    assert definition["edges"]


@pytest.mark.parametrize("template_id", SECURITY_TEMPLATE_IDS)
def test_template_passes_workflow_validation(template_id):
    definition = load_template_definition(template_id)
    # Wirft bei ungueltigen Node-Typen/Kanten — darf hier nicht werfen.
    validate_workflow_definition(definition["nodes"], definition["edges"])


@pytest.mark.parametrize("template_id", SECURITY_TEMPLATE_IDS)
def test_template_agent_node_targets_security_module(template_id):
    definition = load_template_definition(template_id)
    agent_nodes = [n for n in definition["nodes"] if n["type"] == "agent"]
    assert len(agent_nodes) == 1
    assert agent_nodes[0]["config"]["agent_id"] == "security"
    assert "security_workflow_run" in agent_nodes[0]["config"]["prompt"]


@pytest.mark.parametrize("template_id", SECURITY_TEMPLATE_IDS)
def test_template_has_target_id_variable(template_id):
    definition = load_template_definition(template_id)
    variable_names = {v["name"] for v in definition["variables"]}
    assert "target_id" in variable_names


@pytest.mark.parametrize("template_id", SECURITY_TEMPLATE_IDS)
def test_template_instantiates_into_valid_workflow(template_id):
    instance = instantiate_template(template_id)
    assert instance is not None
    assert instance["id"].startswith("wf-")
    # Instanziierung darf Node-IDs neu vergeben, aber Kanten muessen konsistent bleiben.
    node_ids = {n["id"] for n in instance["nodes"]}
    for edge in instance["edges"]:
        assert edge["source_id"] in node_ids
        assert edge["target_id"] in node_ids
    validate_workflow_definition(instance["nodes"], instance["edges"])


def test_ai_platform_audit_prompt_mentions_approval():
    definition = load_template_definition("security-ai-platform-audit")
    agent_node = next(n for n in definition["nodes"] if n["type"] == "agent")
    assert "approval" in agent_node["config"]["prompt"].lower() or "waiting_for_approval" in agent_node["config"]["prompt"]
