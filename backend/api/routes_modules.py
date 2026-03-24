"""
Kumio Module API – Modul-Verwaltung und Tab-Informationen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from schemas.module import (
    ModuleInfo,
    ModuleHealthStatus,
    ModuleTabInfo,
    AllModulesHealthResponse,
)

logger = logging.getLogger("kumio.api.modules")
router = APIRouter(prefix="/api/modules", tags=["Module"])


@router.get("", response_model=list[ModuleInfo])
@router.get("/", response_model=list[ModuleInfo])
async def list_modules(request: Request) -> list[ModuleInfo]:
    """Listet alle registrierten Module auf."""
    registry = request.app.state.registry
    modules = registry.list_modules()

    return [
        ModuleInfo(
            name=m.name,
            display_name=m.display_name,
            description=m.description,
            version=m.version,
            author=m.author,
            enabled=True,
            api_prefix=m.api_prefix,
            dashboard_tab=m.dashboard_tab,
        )
        for m in modules
    ]


@router.get("/tabs", response_model=list[ModuleTabInfo])
async def get_module_tabs(request: Request) -> list[ModuleTabInfo]:
    """Gibt Dashboard-Tab-Metadaten aller aktiven Module zurück."""
    registry = request.app.state.registry
    tabs = registry.get_module_tabs()

    return [
        ModuleTabInfo(**tab) for tab in tabs
    ]


@router.get("/health", response_model=AllModulesHealthResponse)
async def get_modules_health(request: Request) -> AllModulesHealthResponse:
    """Health-Status aller Module."""
    registry = request.app.state.registry
    health = await registry.get_health()

    statuses = [
        ModuleHealthStatus(
            module=name,
            status=h.get("status", "unknown"),
            detail=h.get("detail", ""),
        )
        for name, h in health.items()
    ]

    has_error = any(s.status == "error" for s in statuses)
    overall = "error" if has_error else "ok"
    if has_error and any(s.status == "ok" for s in statuses):
        overall = "degraded"

    return AllModulesHealthResponse(modules=statuses, overall=overall)


@router.get("/{module_name}/frontend/{filename}")
async def get_module_frontend(
    request: Request, module_name: str, filename: str
) -> HTMLResponse:
    """
    Liefert Frontend-Dateien eines Moduls aus (tab.html, tab.js).
    Pfad: modules/<module_name>/frontend/<filename>
    """
    # Sicherheit: nur erlaubte Dateinamen
    allowed_files = {"tab.html", "tab.js"}
    if filename not in allowed_files:
        return HTMLResponse(
            content="Datei nicht erlaubt.",
            status_code=403,
        )

    # Dateipfad konstruieren
    base_dir = Path(__file__).resolve().parent.parent / "modules"
    file_path = (base_dir / module_name / "frontend" / filename).resolve()

    # Pfad-Traversal verhindern
    if not file_path.is_relative_to(base_dir):
        return HTMLResponse(content="Zugriff verweigert.", status_code=403)

    if not file_path.is_file():
        # Fallback auf plugins/ Verzeichnis
        plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
        file_path = (plugins_dir / module_name / "frontend" / filename).resolve()
        if not file_path.is_relative_to(plugins_dir):
            return HTMLResponse(content="Zugriff verweigert.", status_code=403)
        if not file_path.is_file():
            return HTMLResponse(
                content="Datei nicht gefunden.",
                status_code=404,
            )

    content = file_path.read_text(encoding="utf-8")

    content_type = "text/html" if filename.endswith(".html") else "application/javascript"
    return HTMLResponse(content=content, media_type=content_type)
