"""
Ninko Skills API – CRUD für das prozeduale Domänenwissen der Agenten
+ Skill-Marketplace (Remote Skill-Repositories).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.skills_manager import get_skills_manager
from core.skill_marketplace import get_skill_marketplace

logger = logging.getLogger("ninko.api.skills")

router = APIRouter(prefix="/api/skills", tags=["skills"])


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


@router.get("/")
async def list_skills() -> list[dict]:
    """Gibt alle geladenen Skills zurück (Katalog ohne Content)."""
    return get_skills_manager().get_catalog()


@router.get("/{name}")
async def get_skill(name: str) -> dict:
    """Gibt einen einzelnen Skill inkl. vollem Content zurück."""
    skill = get_skills_manager().get_skill_full(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' nicht gefunden.")
    return skill


@router.post("/", status_code=201)
async def create_skill(body: SkillCreate) -> dict:
    """Erstellt einen neuen Skill und persistiert ihn in data/skills/."""
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
        return {"status": "created", "name": body.name, "path": str(path)}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Skill-Erstellung fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{name}")
async def update_skill(name: str, body: SkillUpdate) -> dict:
    """Aktualisiert einen bestehenden Skill (Runtime-Override für Built-ins möglich)."""
    mgr = get_skills_manager()
    try:
        path = mgr.update_skill(name, body.description, body.content, body.modules)
        return {"status": "updated", "name": name, "path": str(path)}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Skill-Update fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{name}", status_code=200)
async def delete_skill(name: str) -> dict:
    """Löscht einen Runtime-Skill. Built-in Skills können nicht gelöscht werden."""
    mgr = get_skills_manager()
    try:
        success = mgr.delete_skill(name)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Skill '{name}' nicht gefunden."
            )
        return {"deleted": name}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Marketplace (MUSS vor /{name} kommen, sonst wird "marketplace" als Skill-Name interpretiert) ──


@router.get("/marketplace")
async def get_marketplace() -> list[dict]:
    """Aggregierter Katalog aller konfigurierten Skill-Repos."""
    mp = get_skill_marketplace()
    installed = {s["name"] for s in get_skills_manager().get_catalog()}
    skills = await mp.fetch_all_catalogs()
    # Mark installed skills
    for s in skills:
        s["installed"] = s.get("name", "") in installed
    return skills


@router.post("/marketplace/install", status_code=201)
async def install_from_marketplace(body: MarketplaceInstall) -> dict:
    """Installiert einen Skill aus dem Marketplace."""
    mp = get_skill_marketplace()
    try:
        path = await mp.install_from_remote(
            skill_url=body.skill_url,
            name=body.name,
            modules=body.modules,
        )
        return {"status": "installed", "name": body.name, "path": str(path)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Marketplace-Install fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Repos ────────────────────────────────────────────────────────────────────


@router.get("/repos")
async def list_repos() -> list[dict]:
    """Konfigurierte Skill-Repositories auflisten."""
    mp = get_skill_marketplace()
    return await mp.get_repos()


@router.post("/repos", status_code=201)
async def add_repo(body: RepoCreate) -> dict:
    """Neues Skill-Repository hinzufügen."""
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
        return {"status": "added", "id": body.id}
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/repos/{repo_id}")
async def remove_repo(repo_id: str) -> dict:
    """Skill-Repository entfernen (builtin-Repos geschützt)."""
    mp = get_skill_marketplace()
    try:
        await mp.remove_repo(repo_id)
        return {"status": "removed", "id": repo_id}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── CRUD für Skills (nach Marketplace, damit /{name} nicht "marketplace" fängt) ──


@router.get("/{name}")
async def get_skill(name: str) -> dict:
    """Gibt einen einzelnen Skill inkl. vollem Content zurück."""
    skill = get_skills_manager().get_skill_full(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' nicht gefunden.")
    return skill


@router.post("/", status_code=201)
async def create_skill(body: SkillCreate) -> dict:
    """Erstellt einen neuen Skill und persistiert ihn in data/skills/."""
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
        return {"status": "created", "name": body.name, "path": str(path)}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Skill-Erstellung fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{name}")
async def update_skill(name: str, body: SkillUpdate) -> dict:
    """Aktualisiert einen bestehenden Skill (Runtime-Override für Built-ins möglich)."""
    mgr = get_skills_manager()
    try:
        path = mgr.update_skill(name, body.description, body.content, body.modules)
        return {"status": "updated", "name": name, "path": str(path)}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Skill-Update fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{name}", status_code=200)
async def delete_skill(name: str) -> dict:
    """Löscht einen Runtime-Skill. Built-in Skills können nicht gelöscht werden."""
    mgr = get_skills_manager()
    try:
        success = mgr.delete_skill(name)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Skill '{name}' nicht gefunden."
            )
        return {"deleted": name}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))
