from __future__ import annotations

from agents.orchestrator import OrchestratorAgent
from core.module_registry import ModuleManifest, ModuleRegistry, RegisteredModule


def _registry_with_manifests(*manifests: ModuleManifest) -> ModuleRegistry:
    registry = ModuleRegistry()
    for manifest in manifests:
        registry._modules[manifest.name] = RegisteredModule(manifest=manifest)
    return registry


def _build_schema_from_registry(registry: ModuleRegistry) -> list[dict]:
    agent = object.__new__(OrchestratorAgent)
    agent.registry = registry
    return agent._build_module_tools_schema()


def test_build_module_tools_schema_structure() -> None:
    registry = _registry_with_manifests(
        ModuleManifest(name="kubernetes", display_name="Kubernetes", description="Cluster management"),
        ModuleManifest(name="pihole", display_name="Pi-hole", description="DNS blocking"),
    )
    manifests = registry.list_modules()

    schema = _build_schema_from_registry(registry)

    assert isinstance(schema, list)
    assert len(schema) == len(manifests)

    for tool in schema:
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]
        assert tool["function"]["parameters"]["type"] == "object"
        assert "query" in tool["function"]["parameters"]["properties"]
        assert tool["function"]["parameters"]["properties"]["query"]["type"] == "string"
        assert "query" in tool["function"]["parameters"]["required"]


def test_build_module_tools_schema_names_match_manifests() -> None:
    registry = _registry_with_manifests(
        ModuleManifest(name="kubernetes", display_name="Kubernetes", description="Cluster management"),
        ModuleManifest(name="pihole", display_name="Pi-hole", description="DNS blocking"),
    )

    schema = _build_schema_from_registry(registry)
    manifest_names = {m.name for m in registry.list_modules()}
    tool_names = {t["function"]["name"] for t in schema}

    assert tool_names == manifest_names


def test_build_module_tools_schema_description_from_manifest() -> None:
    registry = _registry_with_manifests(
        ModuleManifest(name="kubernetes", display_name="Kubernetes", description="Cluster management"),
        ModuleManifest(name="pihole", display_name="Pi-hole", description="DNS blocking"),
    )

    schema = _build_schema_from_registry(registry)
    name_to_manifest = {m.name: m for m in registry.list_modules()}
    for tool in schema:
        manifest = name_to_manifest[tool["function"]["name"]]
        assert tool["function"]["description"] == (manifest.description or "")


def test_build_module_tools_schema_empty_for_no_modules() -> None:
    registry = ModuleRegistry()
    schema = _build_schema_from_registry(registry)
    assert schema == []
