from __future__ import annotations

from types import SimpleNamespace

from core.module_registry import ModuleManifest, ModuleRegistry


def test_stale_plugin_uses_newer_catalog_module(monkeypatch) -> None:
    registry = ModuleRegistry()
    plugin_package = SimpleNamespace()
    catalog_package = SimpleNamespace(
        module_manifest=ModuleManifest(
            name="tasmota", display_name="Tasmota", version="1.1.4"
        )
    )
    plugin_manifest = ModuleManifest(
        name="tasmota", display_name="Tasmota", version="1.1.3"
    )

    def fake_import_module(path: str) -> object:
        assert path == "modules_catalog.tasmota"
        return catalog_package

    monkeypatch.setattr("core.module_registry.importlib.import_module", fake_import_module)

    package, manifest = registry._prefer_catalog_module_when_current(
        "tasmota",
        plugin_package,
        plugin_manifest,
    )

    assert package is catalog_package
    assert manifest.version == "1.1.4"


def test_newer_plugin_keeps_plugin_module(monkeypatch) -> None:
    registry = ModuleRegistry()
    plugin_package = SimpleNamespace()
    catalog_package = SimpleNamespace(
        module_manifest=ModuleManifest(
            name="tasmota", display_name="Tasmota", version="1.1.4"
        )
    )
    plugin_manifest = ModuleManifest(
        name="tasmota", display_name="Tasmota", version="1.1.5"
    )

    def fake_import_module(path: str) -> object:
        assert path == "modules_catalog.tasmota"
        return catalog_package

    monkeypatch.setattr("core.module_registry.importlib.import_module", fake_import_module)

    package, manifest = registry._prefer_catalog_module_when_current(
        "tasmota",
        plugin_package,
        plugin_manifest,
    )

    assert package is plugin_package
    assert manifest.version == "1.1.5"
