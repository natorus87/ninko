"""
Ninko Skills API – CRUD für das prozeduale Domänenwissen der Agenten
+ Skill-Marketplace (Remote Skill-Repositories).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import ROLE_ADMIN, resolve_request_auth_async
from core.skills_manager import get_skills_manager
from core.skill_marketplace import get_skill_marketplace
from schemas.skills import (
    MarketplaceEntry,
    MarketplaceInstallResponse,
    SkillCreateResponse,
    SkillDeleteResponse,
    SkillDetail,
    SkillRepo,
    SkillRepoAddResponse,
    SkillRepoRemoveResponse,
    SkillSummary,
    SkillUpdateResponse,
)

logger = logging.getLogger("ninko.api.skills")

router = APIRouter(prefix="/api/skills", tags=["skills"])


async def _assert_admin(request: Request) -> None:
    """Erzwingt Admin-Authentifizierung für state-changing Skill-Operationen."""
    auth_ctx = await resolve_request_auth_async(request)
    if not auth_ctx or str(auth_ctx.get("role")) != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required.")


# ── Schemas ───────────────────────────────────────────────────────────────────


class SkillCreate(BaseModel):
    name: str
    description: str
    content: str
    modules: Optional[list[str]] = None


class SkillUpdate(BaseModel):
    description: str
    content: str
    modules: Optional[list[str]] = None


class MarketplaceInstall(BaseModel):
    name: str
    skill_url: str
    modules: Optional[list[str]] = None


class RepoCreate(BaseModel):
    id: str
    name: str = ""
    catalog_url: str


# ── Endpunkte ─────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[SkillSummary])
async def list_skills() -> list[SkillSummary]:
    """Gibt alle geladenen Skills zurück (Katalog ohne Content)."""
    raw = get_skills_manager().get_catalog()
    return [SkillSummary(**s) for s in raw]


# ═══════════════════════════════════════════════════════════════════════════════
# Marketplace & Repos (MÜSSEN vor /{name} definiert werden!)
# FastAPI wertet Routes in Reihenfolge aus - /{name} würde "marketplace" fangen
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/marketplace", response_model=list[MarketplaceEntry])
async def get_marketplace() -> list[MarketplaceEntry]:
    """Aggregierter Katalog aller konfigurierten Skill-Repos."""
    mp = get_skill_marketplace()
    installed = {s["name"] for s in get_skills_manager().get_catalog()}
    skills = await mp.fetch_all_catalogs()
    for s in skills:
        s["installed"] = s.get("name", "") in installed
    return [MarketplaceEntry(**s) for s in skills]


@router.post("/marketplace/install", status_code=201, response_model=MarketplaceInstallResponse)
async def install_from_marketplace(
    body: MarketplaceInstall, request: Request
) -> MarketplaceInstallResponse:
    """Installiert einen Skill aus dem Marketplace."""
    await _assert_admin(request)
    mp = get_skill_marketplace()
    try:
        path = await mp.install_from_remote(
            skill_url=body.skill_url,
            name=body.name,
            modules=body.modules,
        )
        return MarketplaceInstallResponse(name=body.name, path=str(path))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Marketplace-Install fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/repos", response_model=list[SkillRepo])
async def list_repos() -> list[SkillRepo]:
    """Konfigurierte Skill-Repositories auflisten."""
    mp = get_skill_marketplace()
    raw = await mp.get_repos()
    return [SkillRepo(**r) for r in raw]


@router.post("/repos", status_code=201, response_model=SkillRepoAddResponse)
async def add_repo(
    body: RepoCreate, request: Request
) -> SkillRepoAddResponse:
    """Neues Skill-Repository hinzufügen."""
    await _assert_admin(request)
    mp = get_skill_marketplace()
    try:
        await mp.add_repo(
            {
                "id": body.id,
                "name": body.name or body.id,
                "catalog_url": body.catalog_url,
                "builtin": False,
            }
        )
        return SkillRepoAddResponse(id=body.id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/repos/{repo_id}", response_model=SkillRepoRemoveResponse)
async def remove_repo(
    repo_id: str, request: Request
) -> SkillRepoRemoveResponse:
    """Skill-Repository entfernen (builtin-Repos geschützt)."""
    await _assert_admin(request)
    mp = get_skill_marketplace()
    try:
        await mp.remove_repo(repo_id)
        return SkillRepoRemoveResponse(id=repo_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD für einzelne Skills (NACH Marketplace, damit /{name} nicht "marketplace" fängt)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(name: str) -> SkillDetail:
    """Gibt einen einzelnen Skill inkl. vollem Content zurück."""
    skill = get_skills_manager().get_skill_full(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' nicht gefunden.")
    return SkillDetail(**skill)


@router.post("/", status_code=201, response_model=SkillCreateResponse)
async def create_skill(
    body: SkillCreate, request: Request
) -> SkillCreateResponse:
    """Erstellt einen neuen Skill und persistiert ihn in data/skills/."""
    await _assert_admin(request)
    mgr = get_skills_manager()
    if mgr.get_skill(body.name):
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{body.name}' existiert bereits. Nutze PUT zum Aktualisieren.",
        )
    try:
        path = mgr.install_skill(
            body.name, body.description, body.content, body.modules
        )
        return SkillCreateResponse(name=body.name, path=str(path))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Skill-Erstellung fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{name}", response_model=SkillUpdateResponse)
async def update_skill(
    name: str, body: SkillUpdate, request: Request
) -> SkillUpdateResponse:
    """Aktualisiert einen bestehenden Skill (Runtime-Override für Built-ins möglich)."""
    await _assert_admin(request)
    mgr = get_skills_manager()
    try:
        path = mgr.update_skill(name, body.description, body.content, body.modules)
        return SkillUpdateResponse(name=name, path=str(path))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Skill-Update fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{name}", status_code=200, response_model=SkillDeleteResponse)
async def delete_skill(
    name: str, request: Request
) -> SkillDeleteResponse:
    """Löscht einen Runtime-Skill. Built-in Skills können nicht gelöscht werden."""
    await _assert_admin(request)
    mgr = get_skills_manager()
    try:
        success = mgr.delete_skill(name)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Skill '{name}' nicht gefunden."
            )
        return SkillDeleteResponse(deleted=name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))
