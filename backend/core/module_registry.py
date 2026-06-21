"""
Ninko Module Registry – Herzstück der modularen Architektur.

Scannt modules/, importiert Manifeste, validiert, registriert Agenten,
Router und Keywords. Alle anderen Komponenten fragen hier nach –
niemals direkt Module importieren.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import pkgutil
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from fastapi import FastAPI

logger = logging.getLogger("ninko.registry")

_REGISTRY_EXCEPTIONS = (
    ImportError,
    AttributeError,
    NameError,
    TypeError,
    ValueError,
    KeyError,
    RuntimeError,
    OSError,
)


def _version_key(version: str) -> tuple[int, ...]:
    """Parse simple semantic versions for catalog/plugin precedence checks."""
    parts = re.findall(r"\d+", str(version or "0"))
    return tuple(int(part) for part in parts[:4]) or (0,)


# ── Modul-Manifest-Datenklasse ──────────────────────────────
@dataclass
class ModuleManifest:
    """Pflichtfelder jedes Ninko-Moduls."""

    name: str
    display_name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = "Ninko Team"
    enabled_by_default: bool = True
    env_prefix: str = ""
    required_secrets: list[str] = field(default_factory=list)
    optional_secrets: list[str] = field(default_factory=list)
    routing_keywords: list[str] = field(default_factory=list)
    api_prefix: str = ""
    dashboard_tab: dict[str, str] = field(default_factory=dict)
    health_check: Callable[..., Awaitable[dict]] | None = None
    agent_capabilities: list[str] = field(default_factory=list)


# ── Registrierter Modul-Container ───────────────────────────
@dataclass
class RegisteredModule:
    """Internes Daten-Objekt für ein geladenes Modul."""

    manifest: ModuleManifest
    agent: Any = None
    router: Any = None
    package: Any = None


# ── Registry ────────────────────────────────────────────────
class PluginRouteRegistry:
    """Trackt FastAPI-Routen, die von Plugins zur Laufzeit gemountet wurden.

    Kapselt die fragile Starlette-`app.router.routes`-Manipulation, damit
    ModuleRegistry ein sauberes mount()/unmount()-API bekommt. So bleibt
    die Starlette-Internals-Abhängigkeit auf eine Klasse beschränkt
    (austauschbar bei FastAPI/Starlette-Versionswechseln).
    """

    def __init__(self) -> None:
        self._plugin_routes: dict[str, list[Any]] = {}
        self._app: FastAPI | None = None

    def set_app(self, app: FastAPI) -> None:
        """Setzt die FastAPI-App-Referenz (für späteres unmount ohne app-Argument)."""
        self._app = app

    def get_app(self) -> FastAPI | None:
        """Gibt die gespeicherte App-Referenz zurück (oder None)."""
        return self._app

    def mount(
        self,
        app: FastAPI,
        modname: str,
        router: Any,
        *,
        prefix: str,
        tags: list[str] | None = None,
    ) -> list[Any]:
        """Mounted Router in app und trackt die hinzugefügten Routen pro Plugin.

        Liefert die Liste der hinzugefügten Starlette-Routen zurück.
        """
        if self._app is None:
            self._app = app

        routes_before = len(app.router.routes)
        app.include_router(
            router,
            prefix=prefix,
            tags=tags or [],
        )
        added = list(app.router.routes[routes_before:])
        self._move_before_static_catchall(app, added, routes_before)
        self._plugin_routes[modname] = added
        app.middleware_stack = app.build_middleware_stack()
        return added

    def unmount(self, app: FastAPI, modname: str) -> int:
        """Entfernt alle getrackten Routen eines Plugins aus app. Liefert Anzahl entfernter Routen."""
        tracked = self._plugin_routes.pop(modname, [])
        if not tracked:
            return 0
        tracked_ids = {id(r) for r in tracked}
        original_len = len(app.router.routes)
        app.router.routes = [r for r in app.router.routes if id(r) not in tracked_ids]
        removed = original_len - len(app.router.routes)
        if removed:
            app.middleware_stack = app.build_middleware_stack()
        return removed

    def get_tracked(self, modname: str) -> list[Any]:
        """Liefert eine Kopie der getrackten Routen (read-only)."""
        return list(self._plugin_routes.get(modname, []))

    def tracked_count(self) -> int:
        """Anzahl getrackter Plugins (für Diagnostics/Tests)."""
        return len(self._plugin_routes)

    @staticmethod
    def _move_before_static_catchall(
        app: FastAPI, new_routes: list[Any], routes_before: int
    ) -> None:
        """Verschiebt neu gemountete Routen vor den StaticFiles-Catch-all-Mount,
        damit sie nicht vom Mount("/") abgefangen werden."""
        if not new_routes:
            return
        from starlette.routing import Mount
        from fastapi.staticfiles import StaticFiles

        static_idx = next(
            (
                i
                for i, r in enumerate(app.router.routes)
                if isinstance(r, Mount)
                and isinstance(getattr(r, "app", None), StaticFiles)
            ),
            None,
        )
        if static_idx is None:
            return
        del app.router.routes[routes_before:]
        for route in reversed(new_routes):
            app.router.routes.insert(static_idx, route)


class ModuleRegistry:
    """
    Zentrale Registry. Wird beim App-Start einmalig befüllt.
    Alle anderen Komponenten fragen hier nach – niemals direkt
    Module importieren.
    """

    def __init__(self) -> None:
        self._modules: dict[str, RegisteredModule] = {}
        self._disabled_manifests: dict[str, ModuleManifest] = {}
        self._hot_load_lock = asyncio.Lock()
        self._route_registry = PluginRouteRegistry()

    def _resolve_module_key(self, name: str) -> str | None:
        """Mappt modname (Verzeichnisname) auf den Registry-Key (manifest.name).

        Behebt die Asymmetrie zwischen Hot-Load (modname als Key) und
        discover_and_load (manifest.name als Key). Gibt None zurück, wenn
        kein Modul unter irgendeinem der beiden Namen gefunden wurde.
        """
        if name in self._modules:
            return name
        for key, mod in self._modules.items():
            if mod.manifest.name == name:
                return key
            if mod.package == name or mod.package.endswith(f".{name}"):
                return key
        return None

    # ── Discovery ───────────────────────────────────────
    def discover_and_load(self) -> None:
        """
        1. Scannt backend/modules/ nach Unterordnern
        2. Importiert modules/<name>/__init__.py → module_manifest
        3. Prüft Env: NINKO_MODULE_<NAME_UPPER>=true|false
        4. Registriert Modul: Agent, Router, Keywords
        5. Loggt welche Module geladen / übersprungen wurden
        """
        modules_dir = Path(__file__).resolve().parent.parent / "modules"
        if not modules_dir.is_dir():
            logger.warning("Module-Verzeichnis nicht gefunden: %s", modules_dir)
            return

        # Finde alle Unter-Packages
        for importer, modname, ispkg in pkgutil.iter_modules([str(modules_dir)]):
            if not ispkg:
                continue

            try:
                self._load_module(modname, modules_dir)
            except _REGISTRY_EXCEPTIONS as exc:
                logger.error(
                    "Fehler beim Laden von Modul '%s': %s", modname, exc, exc_info=True
                )

        # 2. Plugins Scannen (aus ./plugins) -> Dynamisch gemountetes Verzeichnis
        plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
        if plugins_dir.is_dir():
            # Füge den Parent-Ordner (backend) in sys.path ein, falls nicht vorhanden,
            # um 'plugins.xyz' importieren zu können.
            backend_dir = str(plugins_dir.parent)
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)

            for importer, modname, ispkg in pkgutil.iter_modules([str(plugins_dir)]):
                if not ispkg:
                    continue
                try:
                    self._load_module(modname, plugins_dir, is_plugin=True)
                except _REGISTRY_EXCEPTIONS as exc:
                    logger.error(
                        "Fehler beim Laden von Plugin '%s': %s",
                        modname,
                        exc,
                        exc_info=True,
                    )

        loaded = [m.manifest.display_name for m in self._modules.values()]
        logger.info(
            "Module/Plugins geladen (%d): %s", len(loaded), ", ".join(loaded) or "–"
        )

    def _load_module(
        self, modname: str, base_dir: Path, is_plugin: bool = False
    ) -> None:
        """Einzelnes Modul oder Plugin laden und registrieren."""
        package_prefix = "plugins" if is_plugin else "modules"
        package_path = f"{package_prefix}.{modname}"

        # Vor dem Import sicherstellen, dass wir es neu laden, falls es schon existiert (Hot-Reload)
        if package_path in sys.modules:
            importlib.reload(sys.modules[package_path])

        package = importlib.import_module(package_path)

        # Manifest holen
        manifest: ModuleManifest | None = getattr(package, "module_manifest", None)
        if manifest is None:
            logger.warning(
                "Modul '%s' hat kein 'module_manifest' – übersprungen.", modname
            )
            return
        if not isinstance(manifest, ModuleManifest):
            logger.warning(
                "Modul '%s' hat ungültiges 'module_manifest' (Typ: %s) – übersprungen.",
                modname,
                type(manifest).__name__,
            )
            return
        if is_plugin:
            package, manifest = self._prefer_catalog_module_when_current(
                modname, package, manifest
            )

        # Prüfe ob per Env aktiviert/deaktiviert
        # Plugins (vom Marketplace installiert) sind immer aktiv, außer eine Env-Var sagt explizit false
        env_key = f"NINKO_MODULE_{manifest.name.upper()}"
        env_val = os.environ.get(env_key)

        if env_val is not None:
            enabled = env_val.lower() in ("true", "1", "yes")
        elif is_plugin:
            enabled = True  # Installierte Plugins sind standardmäßig aktiv
        else:
            enabled = manifest.enabled_by_default

        if not enabled:
            logger.info(
                "Modul '%s' ist deaktiviert (%s=false).", manifest.display_name, env_key
            )
            self._disabled_manifests[manifest.name] = manifest
            return

        # Agent und Router aus dem Package holen
        agent = getattr(package, "agent", None)
        router = getattr(package, "router", None)

        registered = RegisteredModule(
            manifest=manifest,
            agent=agent,
            router=router,
            package=package,
        )
        self._modules[manifest.name] = registered

        logger.info(
            "Modul registriert: %s v%s (Keywords: %d, API: %s)",
            manifest.display_name,
            manifest.version,
            len(manifest.routing_keywords),
            manifest.api_prefix or "–",
        )

    def _prefer_catalog_module_when_current(
        self,
        modname: str,
        plugin_package: Any,
        plugin_manifest: ModuleManifest,
    ) -> tuple[Any, ModuleManifest]:
        """
        Prefer the bundled catalog module over a stale marketplace plugin copy.

        Marketplace installs persist under backend/plugins. After an image update
        those files can lag behind the catalog version and still override the
        fixed module because plugins are loaded later. If both module names match
        and the bundled catalog version is at least as new, use the catalog
        package for runtime registration.
        """
        catalog_package_path = f"modules_catalog.{modname}"
        try:
            catalog_package = importlib.import_module(catalog_package_path)
        except _REGISTRY_EXCEPTIONS:
            return plugin_package, plugin_manifest

        catalog_manifest = getattr(catalog_package, "module_manifest", None)
        if catalog_manifest is None or catalog_manifest.name != plugin_manifest.name:
            return plugin_package, plugin_manifest

        if _version_key(catalog_manifest.version) < _version_key(plugin_manifest.version):
            return plugin_package, plugin_manifest

        logger.info(
            "Plugin '%s' v%s wird durch aktuelleres Katalogmodul v%s ersetzt.",
            plugin_manifest.name,
            plugin_manifest.version,
            catalog_manifest.version,
        )
        return catalog_package, catalog_manifest

    # ── Route-Registration ──────────────────────────────
    def register_routes(self, app: FastAPI) -> None:
        """Registriert alle Modul-Router an der FastAPI-App."""
        for name, mod in self._modules.items():
            if mod.router is not None and mod.manifest.api_prefix:
                app.include_router(
                    mod.router,
                    prefix=mod.manifest.api_prefix,
                    tags=[mod.manifest.display_name],
                )
                logger.info(
                    "Router registriert: %s → %s",
                    mod.manifest.display_name,
                    mod.manifest.api_prefix,
                )

    async def hot_load_plugin(self, modname: str, app: FastAPI) -> bool:
        """
        Lädt ein Plugin dynamisch zur Laufzeit nach und hängt seinen Router an die laufende FastAPI-Instanz.
        Entfernt zuerst das alte Plugin falls vorhanden, um sauberes Update zu gewährleisten.
        """
        async with self._hot_load_lock:
            return await self._hot_load_plugin_unlocked(modname, app)

    async def _hot_load_plugin_unlocked(self, modname: str, app: FastAPI) -> bool:
        """Internal hot-load without lock. Caller must hold _hot_load_lock."""
        plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
        backend_dir = str(plugins_dir.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        # venv-Site-Packages des Plugins in sys.path einsetzen (CWE-829 Mitigation).
        # Dadurch findet der Python-Importer die Plugin-Dependencies (die in
        # einer dedizierten venv pro Plugin installiert wurden) ohne den
        # System-Namespace zu kontaminieren.
        venvs_root = plugins_dir.parent / ".plugin_venvs" / modname
        venv_site_packages = venvs_root / "lib"
        if venv_site_packages.is_dir():
            # Python 3.12+: lib/python3.X/site-packages (X variiert pro Build)
            for sub in venv_site_packages.iterdir():
                sp = sub / "site-packages"
                if sp.is_dir():
                    sp_str = str(sp)
                    if sp_str not in sys.path:
                        sys.path.insert(0, sp_str)
                    break

        # Erst altes Plugin entfernen falls vorhanden (für sauberes Update)
        if modname in self._modules:
            logger.info("Entferne altes Plugin '%s' vor Hot-Reload...", modname)
            # Direkt _remove_plugin_locked statt remove_plugin-Wrapper, weil
            # wir den Lock bereits halten (Lock ist nicht-reentrant).
            self._remove_plugin_locked(modname)
            # Auch aus sys.modules alle Submodule entfernen
            package_path = f"plugins.{modname}"
            modules_to_remove = [
                name
                for name in sys.modules.keys()
                if name == package_path or name.startswith(f"{package_path}.")
            ]
            for name in modules_to_remove:
                del sys.modules[name]
                logger.debug("Entfernt aus sys.modules: %s", name)

        try:
            self._load_module(modname, plugins_dir, is_plugin=True)
        except _REGISTRY_EXCEPTIONS as exc:
            import traceback

            logger.error(
                "Hot-Load gescheitert für '%s': %s\n%s",
                modname,
                exc,
                traceback.format_exc(),
            )
            return False

        # Wenn erfolgreich geladen, Route direkt an app hängen
        mod = self._modules.get(self._resolve_module_key(modname) or modname)
        if mod and mod.router and mod.manifest.api_prefix:
            self._route_registry.mount(
                app,
                modname,
                mod.router,
                prefix=mod.manifest.api_prefix,
                tags=[mod.manifest.display_name],
            )
            logger.info("Hot-Load Router registriert: %s", mod.manifest.api_prefix)

        # Soul für das neue Plugin generieren (falls noch keine existiert)
        if mod:
            try:
                from core.soul_manager import get_soul_manager

                soul_manager = get_soul_manager()
                if not soul_manager.has_soul(mod.manifest.name):
                    tool_names = [t.name for t in mod.agent.tools] if mod.agent else []
                    soul_md = soul_manager.generate_module_soul(
                        name=mod.manifest.name,
                        display_name=mod.manifest.display_name,
                        description=mod.manifest.description,
                        tool_names=tool_names,
                    )
                    await soul_manager.save_soul(mod.manifest.name, soul_md)
                    logger.info("Soul für Plugin '%s' generiert.", modname)
            except _REGISTRY_EXCEPTIONS as exc:
                logger.warning(
                    "Soul-Generierung für Plugin '%s' fehlgeschlagen: %s", modname, exc
                )

        return True

    def remove_plugin(self, modname: str, app: FastAPI | None = None) -> None:
        """
        Synchroner Wrapper — hält den _hot_load_lock für die Dauer der Mutation.
        Damit sind parallele Aufrufe von remove_plugin + hot_load_plugin
        serialisiert (sonst Race auf _modules, _plugin_routes, sys.modules).
        Lock kann in single-threaded asyncio nicht awaiten, daher sync-Implementierung.
        """
        if self._hot_load_lock.locked():
            # Hot-Load läuft gerade — _hot_load_lock ist nicht-reentrant.
            # In dem Fall übernimmt der Hot-Load den Cleanup, nichts tun.
            logger.debug(
                "remove_plugin('%s') übersprungen — Hot-Load hält bereits den Lock.",
                modname,
            )
            return
        self._remove_plugin_locked(modname, app)

    def _remove_plugin_locked(self, modname: str, app: FastAPI | None = None) -> None:
        """Interner Remove-Pfad. Muss unter _hot_load_lock aufgerufen werden."""
        if app is None:
            app = self._route_registry.get_app()
        if app is not None:
            removed = self._route_registry.unmount(app, modname)
            if removed:
                logger.info(
                    "Plugin '%s': %d FastAPI-Routen aus app entfernt.", modname, removed,
                )
        elif modname in self._route_registry.get_tracked(modname) or self._route_registry.tracked_count() > 0:
            logger.warning(
                "Plugin '%s' hat getrackte Routen, aber keine App-Referenz verfügbar. "
                "Routen-Leak möglich – restart erforderlich.",
                modname,
            )

        resolved_key = self._resolve_module_key(modname)
        if resolved_key and resolved_key in self._modules:
            del self._modules[resolved_key]
        if modname in self._disabled_manifests:
            del self._disabled_manifests[modname]

        package_path = f"plugins.{modname}"
        if package_path in sys.modules:
            del sys.modules[package_path]

        logger.info("Plugin '%s' aus Registry unmounted.", modname)

    # ── Abfragen ────────────────────────────────────────
    def get_agent(self, module_name: str) -> Any | None:
        """Agent eines Moduls zurückgeben."""
        mod = self._modules.get(module_name)
        return mod.agent if mod else None

    def get_router(self, module_name: str) -> Any | None:
        """Router eines Moduls zurückgeben."""
        mod = self._modules.get(module_name)
        return mod.router if mod else None

    def get_routing_map(self) -> dict[str, str]:
        """Aggregiert alle routing_keywords → {keyword: module_name}.

        Der technische Modulname wird automatisch als Alias ergänzt, damit
        Modul-Autoren ihn nicht zusätzlich in routing_keywords pflegen müssen.
        """
        routing: dict[str, str] = {}
        duplicates: dict[str, list[str]] = {}

        for name, mod in self._modules.items():
            module_aliases = {
                name,
                name.replace("_", " "),
                name.replace("_", ""),
                name.replace("-", " "),
                name.replace("-", ""),
            }
            keywords = [*mod.manifest.routing_keywords, *module_aliases]
            seen_for_module: set[str] = set()

            for kw in keywords:
                key = kw.lower()
                if key in seen_for_module:
                    continue
                seen_for_module.add(key)
                if key in routing:
                    if routing[key] == name:
                        continue
                    # Duplikat gefunden
                    if key not in duplicates:
                        duplicates[key] = [routing[key]]
                    duplicates[key].append(name)
                else:
                    routing[key] = name

        # Bei Duplikaten: Warning loggen (Orchestrator-Ambiguität)
        if duplicates:
            for keyword, modules in duplicates.items():
                logger.warning(
                    "Duplicate routing_keyword '%s' found in modules: %s. "
                    "Orchestrator will use '%s'.",
                    keyword,
                    modules,
                    routing[keyword],
                )

        return routing

    def get_routing_keywords(self) -> dict[str, str]:
        """Alias für get_routing_map()."""
        return self.get_routing_map()

    def list_modules(self) -> list[ModuleManifest]:
        """Alle registrierten (aktiven) Modul-Manifeste zurückgeben."""
        return [mod.manifest for mod in self._modules.values()]

    def list_all_modules(self) -> list[ModuleManifest]:
        """Alle entdeckten Module (aktiv + deaktiviert) zurückgeben."""
        all_manifests = [mod.manifest for mod in self._modules.values()]
        all_manifests.extend(self._disabled_manifests.values())
        return all_manifests

    def is_enabled(self, module_name: str) -> bool:
        """Prüft ob ein Modul aktiv ist."""
        return module_name in self._modules

    def get_module_tabs(self) -> list[dict]:
        """Dashboard-Tab-Metadaten aller aktiven Module."""
        tabs: list[dict] = []
        for mod in self._modules.values():
            if mod.manifest.dashboard_tab:
                tab = {
                    **mod.manifest.dashboard_tab,
                    "module": mod.manifest.name,
                    "api_prefix": mod.manifest.api_prefix,
                }
                tabs.append(tab)
        return tabs

    async def get_health(self) -> dict[str, dict]:
        """Health-Status aller Module abfragen."""
        results: dict[str, dict] = {}
        # list()-Kopie: ein health_check könnte (böswillig oder fehlerhaft)
        # ein Modul deregistrieren → "dictionary changed size during iteration"
        for name, mod in list(self._modules.items()):
            if mod.manifest.health_check is not None:
                try:
                    results[name] = await mod.manifest.health_check()
                except _REGISTRY_EXCEPTIONS as exc:
                    results[name] = {"status": "error", "detail": str(exc)}
                except Exception as exc:
                    logger.exception(
                        "Uncaught health check exception in module '%s': %s", name, exc
                    )
                    results[name] = {
                        "status": "error",
                        "detail": f"Uncaught health check error: {exc}",
                    }
            else:
                results[name] = {
                    "status": "ok",
                    "detail": "Kein Health-Check definiert",
                }
        return results

    def get_registered_modules(self) -> dict[str, RegisteredModule]:
        """Gibt das interne Registry-Dict zurück (für Monitor-Agent)."""
        return self._modules


# ── Globaler Singleton (gesetzt von main.py nach discover_and_load) ──────────
_global_registry: "ModuleRegistry | None" = None


def get_registry() -> "ModuleRegistry | None":
    """Gibt die globale Registry-Instanz zurück (nach App-Start verfügbar)."""
    return _global_registry


def set_registry(registry: "ModuleRegistry") -> None:
    """Wird von main.py nach discover_and_load() aufgerufen."""
    global _global_registry
    _global_registry = registry
