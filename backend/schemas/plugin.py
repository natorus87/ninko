"""
Ninko Plugin Schemas – Pydantic-Modelle für Plugin- und Marketplace-Endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── Marketplace – Repo-CRUD ──────────────────────────────────────────────────


class MarketplaceRepo(BaseModel):
    """Maskierte Repo-Konfiguration (Token nicht enthalten, token_set-Flag)."""

    id: str
    name: str
    repo_url: str
    branch: str = "main"
    modules_path: str = "backend/modules_catalog"
    github_token_set: bool = False


class MarketplaceRepoListResponse(BaseModel):
    """Antwort: Liste der konfigurierten Marketplace-Repos."""

    repos: list[MarketplaceRepo]


class MarketplaceRepoResponse(BaseModel):
    """Antwort: einzelnes Repo nach Create/Update."""

    repo: MarketplaceRepo


class MarketplaceRepoDeleteResponse(BaseModel):
    """Antwort: erfolgreiche Repo-Löschung."""

    message: str


class MessageResponse(BaseModel):
    """Generische Antwort mit einer `message`."""

    message: str


# ─── Marketplace – Module-Listing ────────────────────────────────────────────


class MarketplaceModuleInfo(BaseModel):
    """Informationen zu einem Modul im Marketplace-Listing."""

    name: str
    display_name: str = ""
    description: str = ""
    version: str = ""
    author: str = ""


class MarketplaceModuleUpdateInfo(MarketplaceModuleInfo):
    """Modul-Info inkl. installierter Version und Update-Flag."""

    installed_version: str = ""
    update_available: bool = False
    installed_source: str = ""
    installed_updated_at: float = 0.0


class MarketplaceModuleListResponse(BaseModel):
    """Antwort: Modul-Listing eines Repos (neu + Updates)."""

    modules: list[MarketplaceModuleInfo] = Field(default_factory=list)
    updates: list[MarketplaceModuleUpdateInfo] = Field(default_factory=list)
    error: str | None = None


# ─── Installierte Plugins ─────────────────────────────────────────────────────


class InstalledPluginInfo(BaseModel):
    """Metadaten zu einem installierten Plugin."""

    name: str
    version: str = ""
    installed_at: float = 0.0
    updated_at: float = 0.0
    source: str = "unknown"
    repo_id: str = ""
    repo_url: str = ""
    repo_version: str = ""


class InstalledPluginListResponse(BaseModel):
    """Antwort: Liste installierter Plugins."""

    plugins: list[InstalledPluginInfo]


class PluginUpdateCheckEntry(BaseModel):
    """Update-Check-Ergebnis für ein einzelnes Plugin."""

    name: str
    installed_version: str = ""
    repo_version: str = ""
    update_available: bool = False
    repo_url: str = ""


class PluginUpdateCheckResponse(BaseModel):
    """Antwort: Update-Checks für alle installierten Plugins."""

    plugins: list[PluginUpdateCheckEntry]


# ─── Plugin-Upload / Install / Uninstall ─────────────────────────────────────


class PluginUploadResponse(BaseModel):
    """Antwort: Plugin-Upload (201 Created)."""

    message: str
    plugin_name: str


class PluginInstallResponse(BaseModel):
    """Antwort: Installation aus Marketplace-Repo (201 Created)."""

    message: str
    module_name: str
    repo_version: str = ""


class PluginUninstallResponse(BaseModel):
    """Antwort: Deinstallation eines Plugins."""

    message: str


class PluginUpdateResponse(BaseModel):
    """Antwort: Re-Install/Update eines Plugins."""

    message: str
