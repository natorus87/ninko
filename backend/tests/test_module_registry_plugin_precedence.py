"""
Tests für PluginRouteRegistry und Plugin-Hot-Unload (PLAN.md 2.1).

Abgedeckte Szenarien:
  1. Stale Plugin wird durch neueres Catalog-Modul ersetzt (Pre-Existing)
  2. PluginRouteRegistry.mount() trackt hinzugefügte Routen
  3. PluginRouteRegistry.unmount() entfernt genau die getrackten Routen
  4. PluginRouteRegistry.unmount() für unbekanntes Plugin → 0
  5. PluginRouteRegistry.move-before-static: neue Routen vor Static-Mount
  6. ModuleRegistry.remove_plugin(modname, app) unmountet getrackte Routen
  7. ModuleRegistry.remove_plugin(modname) ohne app nutzt gespeicherten app-Ref
  8. Hot-Reload: hot_load → remove_plugin → re-hot_load → exakt N Routen (kein Duplicate)
  9. _route_registry Instanz wird bei __init__ erstellt
 10. remove_plugin auf Plugin ohne tracked Routes → no-op
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, FastAPI

from core.module_registry import (
    ModuleManifest,
    ModuleRegistry,
    PluginRouteRegistry,
)


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


# ── PluginRouteRegistry: mount/unmount Lifecycle (PLAN.md 2.1) ─────────────────


def test_module_registry_has_route_registry_on_init() -> None:
    """ModuleRegistry instanziiert _route_registry im __init__."""
    registry = ModuleRegistry()
    assert isinstance(registry._route_registry, PluginRouteRegistry)
    assert registry._route_registry.tracked_count() == 0
    assert registry._route_registry.get_app() is None


def test_plugin_route_registry_mount_tracks_added_routes() -> None:
    """mount() fügt Routen hinzu und trackt sie pro Plugin."""
    app = FastAPI()
    prr = PluginRouteRegistry()
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    routes_before = len(app.router.routes)
    added = prr.mount(app, "test_plugin", router, prefix="/api/test", tags=["Test"])

    assert len(added) == 2
    assert prr.tracked_count() == 1
    assert len(prr.get_tracked("test_plugin")) == 2
    assert len(app.router.routes) == routes_before + 2
    assert prr.get_app() is app


def test_plugin_route_registry_unmount_removes_tracked_routes() -> None:
    """unmount() entfernt genau die getrackten Routen und gibt die Anzahl zurück."""
    app = FastAPI()
    prr = PluginRouteRegistry()
    router = APIRouter()

    @router.get("/a")
    async def a() -> dict[str, str]:
        return {"a": "1"}

    @router.get("/b")
    async def b() -> dict[str, str]:
        return {"b": "2"}

    prr.mount(app, "plugin_x", router, prefix="/api/x", tags=["X"])
    routes_after_mount = len(app.router.routes)

    removed = prr.unmount(app, "plugin_x")

    assert removed == 2
    assert len(app.router.routes) == routes_after_mount - 2
    assert prr.tracked_count() == 0
    assert prr.get_tracked("plugin_x") == []


def test_plugin_route_registry_unmount_unknown_plugin_returns_zero() -> None:
    """unmount() für nicht-getracktes Plugin gibt 0 zurück, no-op."""
    app = FastAPI()
    prr = PluginRouteRegistry()
    routes_before = len(app.router.routes)
    assert prr.unmount(app, "never_mounted") == 0
    assert len(app.router.routes) == routes_before, "unmount darf keine Routen entfernen"


def test_plugin_route_registry_move_routes_before_static_mount() -> None:
    """Neu gemountete Routen werden vor StaticFiles-Catch-all-Mount einsortiert."""
    from fastapi.staticfiles import StaticFiles

    app = FastAPI()
    app.mount("/", StaticFiles(directory="/tmp"), name="static")

    prr = PluginRouteRegistry()
    router = APIRouter()

    @router.get("/api/foo")
    async def foo() -> dict[str, str]:
        return {"foo": "1"}

    prr.mount(app, "foo_plugin", router, prefix="", tags=["Foo"])

    static_idx = next(
        i for i, r in enumerate(app.router.routes) if getattr(r, "name", "") == "static"
    )
    foo_idx = next(
        i
        for i, r in enumerate(app.router.routes)
        if getattr(r, "path", "") == "/api/foo"
    )
    assert foo_idx < static_idx, f"foo at {foo_idx} should be before static at {static_idx}"


def test_module_registry_remove_plugin_unmounts_routes() -> None:
    """remove_plugin(name, app) unmountet getrackte Routen aus app."""
    registry = ModuleRegistry()
    app = FastAPI()
    registry._modules["testplug"] = SimpleNamespace(
        manifest=SimpleNamespace(name="testplug"),
    )
    router = APIRouter()

    @router.get("/x")
    async def x() -> dict[str, str]:
        return {"x": "1"}

    registry._route_registry.mount(app, "testplug", router, prefix="/api/testplug", tags=[])
    assert len(registry._route_registry.get_tracked("testplug")) == 1

    registry.remove_plugin("testplug", app)

    assert "testplug" not in registry._modules
    assert registry._route_registry.tracked_count() == 0


def test_module_registry_remove_plugin_uses_stored_app_on_no_arg() -> None:
    """remove_plugin(name) ohne app-Argument nutzt die gespeicherte app-Ref."""
    registry = ModuleRegistry()
    app = FastAPI()
    registry._modules["plug_a"] = SimpleNamespace(manifest=SimpleNamespace(name="plug_a"))
    router = APIRouter()

    @router.get("/a")
    async def a() -> dict[str, str]:
        return {"a": "1"}

    registry._route_registry.mount(app, "plug_a", router, prefix="/api/plug_a", tags=[])
    routes_after_mount = len(app.router.routes)

    registry.remove_plugin("plug_a")

    assert "plug_a" not in registry._modules
    assert len(app.router.routes) == routes_after_mount - 1
    assert registry._route_registry.tracked_count() == 0


def test_module_registry_remove_plugin_no_app_no_tracked_routes_is_noop() -> None:
    """remove_plugin(name) ohne app und ohne tracked routes ist no-op (nur Registry-Cleanup)."""
    registry = ModuleRegistry()
    registry._modules["plug_orphan"] = SimpleNamespace(
        manifest=SimpleNamespace(name="plug_orphan"),
    )

    registry.remove_plugin("plug_orphan")

    assert "plug_orphan" not in registry._modules
    assert registry._route_registry.tracked_count() == 0


def test_plugin_hot_reload_no_route_duplicates() -> None:
    """hot_load → remove_plugin → re-hot_load: keine Route-Duplikate."""
    app = FastAPI()
    prr = PluginRouteRegistry()
    router_v1 = APIRouter()

    @router_v1.get("/v1")
    async def v1() -> dict[str, str]:
        return {"v": "1"}

    prr.mount(app, "reloadable", router_v1, prefix="/api/reloadable", tags=["V1"])
    after_first = len(app.router.routes)

    prr.unmount(app, "reloadable")
    assert len(app.router.routes) == after_first - 1

    router_v2 = APIRouter()

    @router_v2.get("/v2")
    async def v2() -> dict[str, str]:
        return {"v": "2"}

    prr.mount(app, "reloadable", router_v2, prefix="/api/reloadable", tags=["V2"])
    after_second = len(app.router.routes)
    assert after_second == after_first, "Nach Reload darf es keine zusätzlichen Routen geben"

    paths = [getattr(r, "path", "") for r in app.router.routes]
    assert "/api/reloadable/v1" not in paths
    assert "/api/reloadable/v2" in paths
