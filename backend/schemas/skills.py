"""
Ninko – Pydantic-Response-Modelle für Skills-Endpoints (routes_skills.py).

Schemas für:
  - Skill-CRUD (list, get, create, update, delete)
  - Marketplace (catalog, install)
  - Skill-Repositories (list, add, remove)

Request-Modelle (SkillCreate, SkillUpdate, MarketplaceInstall, RepoCreate)
bleiben in routes_skills.py, da sie nur als Eingabe-Validierung dienen.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── Skill-Payload ────────────────────────────────────────────────────────────

class SkillSummary(BaseModel):
    """Skill-Katalog-Eintrag (kein content, nur Metadaten)."""
    name: str
    description: str = ""
    modules: list[str] = Field(default_factory=list)
    location: str = ""
    builtin: bool = True


class SkillDetail(BaseModel):
    """Skill inkl. vollstaendigem Content-Text."""
    name: str
    description: str = ""
    modules: list[str] = Field(default_factory=list)
    content: str
    location: str = ""
    builtin: bool = True


# ─── CRUD-Responses ──────────────────────────────────────────────────────────

# list_skills() -> list[dict] (matches SkillSummary)
SkillListResponse = list[SkillSummary]


class SkillCreateResponse(BaseModel):
    """Antwort nach Erstellen (POST /api/skills/)."""
    status: str = "created"
    name: str
    path: str


class SkillUpdateResponse(BaseModel):
    """Antwort nach Update (PUT /api/skills/{name})."""
    status: str = "updated"
    name: str
    path: str


class SkillDeleteResponse(BaseModel):
    """Antwort nach Loeschen (DELETE /api/skills/{name})."""
    deleted: str


# ─── Marketplace ─────────────────────────────────────────────────────────────

class MarketplaceEntry(BaseModel):
    """Ein Marketplace-Katalogeintrag (aggregiert aus Repos)."""
    name: str
    description: str = ""
    modules: list[str] = Field(default_factory=list)
    installed: bool = False


# list_marketplace() -> list[dict] (matches MarketplaceEntry)
MarketplaceListResponse = list[MarketplaceEntry]


class MarketplaceInstallResponse(BaseModel):
    """Antwort nach Install (POST /api/skills/marketplace/install)."""
    status: str = "installed"
    name: str
    path: str


# ─── Repositories ────────────────────────────────────────────────────────────

class SkillRepo(BaseModel):
    """Ein konfiguriertes Skill-Repository."""
    id: str
    name: str = ""
    catalog_url: str = ""
    builtin: bool = False


# list_repos() -> list[dict] (matches SkillRepo)
SkillRepoListResponse = list[SkillRepo]


class SkillRepoAddResponse(BaseModel):
    """Antwort nach Hinzufuegen (POST /api/skills/repos)."""
    status: str = "added"
    id: str


class SkillRepoRemoveResponse(BaseModel):
    """Antwort nach Entfernen (DELETE /api/skills/repos/{repo_id})."""
    status: str = "removed"
    id: str
