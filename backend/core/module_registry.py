"""
Ninko Module Registry – Herzstück der modularen Architektur.

Scannt modules/, importiert Manifeste, validiert, registriert Agenten,
Router und Keywords. Alle anderen Komponenten fragen hier nach –
niemals direkt Module importieren.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from fastapi import FastAPI

logger = logging.getLogger("ninko.registry")


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


# ── Registrierter Modul-Container ───────────────────────────
@dataclass
class RegisteredModule:
    """Internes Daten-Objekt für ein geladenes Modul."""

    manifest: ModuleManifest
    agent: Any = None
    router: Any = None
    package: Any = None


# ── Registry ────────────────────────────────────────────────
class ModuleRegistry:
    """
    Zentrale Registry. Wird beim App-Start einmalig befüllt.
    Alle anderen Komponenten fragen hier nach – niemals direkt
    Module importieren.
    """

    def __init__(self) -> None:
        self._modules: dict[str, RegisteredModule] = {}
        self._disabled_manifests: dict[str, ModuleManifest] = {}

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
            except Exception as exc:
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
                except Exception as exc:
                    logger.error("Fehler beim Laden von Plugin '%s': %s", modname, exc, exc_info=True)

        loaded = [m.manifest.display_name for m in self._modules.values()]
        logger.info("Module/Plugins geladen (%d): %s", len(loaded), ", ".join(loaded) or "–")

    def _load_module(self, modname: str, base_dir: Path, is_plugin: bool = False) -> None:
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
        """
        plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
        backend_dir = str(plugins_dir.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        try:
            self._load_module(modname, plugins_dir, is_plugin=True)
        except Exception as exc:
            logger.error("Hot-Load gescheitert für '%s': %s", modname, exc)
            return False

        # Wenn erfolgreich geladen, Route direkt an app hängen
        mod = self._modules.get(modname)
        if mod and mod.router and mod.manifest.api_prefix:
            # Merke aktuelle Route-Anzahl, um neu hinzugefügte Routen zu identifizieren
            routes_before = len(app.router.routes)
            app.include_router(
                mod.router,
                prefix=mod.manifest.api_prefix,
                tags=[mod.manifest.display_name],
            )
            # Neu hinzugefügte Routen vor den StaticFiles-Catch-all-Mount verschieben,
            # damit sie nicht vom Mount("/") abgefangen werden.
            new_routes = app.router.routes[routes_before:]
            if new_routes:
                from starlette.routing import Mount
                from fastapi.staticfiles import StaticFiles
                static_idx = next(
                    (i for i, r in enumerate(app.router.routes)
                     if isinstance(r, Mount) and isinstance(getattr(r, "app", None), StaticFiles)),
                    None,
                )
                if static_idx is not None:
                    del app.router.routes[routes_before:]
                    for route in reversed(new_routes):
                        app.router.routes.insert(static_idx, route)
            # Rebuild Middleware Stack to force FastAPI to notice runtime changes
            app.middleware_stack = app.build_middleware_stack()
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
            except Exception as exc:
                logger.warning("Soul-Generierung für Plugin '%s' fehlgeschlagen: %s", modname, exc)

        return True

    def remove_plugin(self, modname: str) -> None:
        """
        Entfernt das Plugin intern aus der Registry.
        Achtung: Die FastAPI Routen bleiben im Memory der laufenden App aktiv, 
        geben aber idealerweise Fehler oder werden ignoriert. 
        Ein echter Neustart ist für sauberen Garbage Collect nötig.
        """
        if modname in self._modules:
            del self._modules[modname]
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
        """Aggregiert alle routing_keywords → {keyword: module_name}."""
        routing: dict[str, str] = {}
        for name, mod in self._modules.items():
            for kw in mod.manifest.routing_keywords:
                routing[kw.lower()] = name
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
        for name, mod in self._modules.items():
            if mod.manifest.health_check is not None:
                try:
                    results[name] = await mod.manifest.health_check()
                except Exception as exc:
                    results[name] = {"status": "error", "detail": str(exc)}
            else:
                results[name] = {"status": "ok", "detail": "Kein Health-Check definiert"}
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
