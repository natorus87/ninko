"""
Kumio Module Schemas – Pydantic-Modelle für Modul-Verwaltung.
"""

from __future__ import annotations

from pydantic import BaseModel


class ModuleInfo(BaseModel):
    """Öffentliche Modul-Informationen."""

    name: str
    display_name: str
    description: str
    version: str
    author: str
    enabled: bool = True
    api_prefix: str = ""
    dashboard_tab: dict = {}


class ModuleHealthStatus(BaseModel):
    """Health-Status eines Moduls."""

    module: str
    status: str  # "ok" | "error"
    detail: str = ""


class ModuleTabInfo(BaseModel):
    """Dashboard-Tab-Informationen eines Moduls."""

    id: str
    label: str
    icon: str = ""
    module: str = ""
    api_prefix: str = ""


class AllModulesHealthResponse(BaseModel):
    """Health-Status aller Module."""

    modules: list[ModuleHealthStatus]
    overall: str  # "ok" | "degraded" | "error"
