"""
Ninko Skills API – CRUD für das prozeduale Domänenwissen der Agenten.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.skills_manager import get_skills_manager

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
        raise HTTPException(status_code=409, detail=f"Skill '{body.name}' existiert bereits. Nutze PUT zum Aktualisieren.")
    try:
        path = mgr.install_skill(body.name, body.description, body.content, body.modules)
        return {"status": "created", "name": body.name, "path": str(path)}
    except Exception as exc:
        logger.error("Skill-Erstellung fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{name}")
async def update_skill(name: str, body: SkillUpdate) -> dict:
    """Aktualisiert einen bestehenden Skill (Runtime-Override für Built-ins möglich)."""
    mgr = get_skills_manager()
    try:
        path = mgr.update_skill(name, body.description, body.content, body.modules)
        return {"status": "updated", "name": name, "path": str(path)}
    except Exception as exc:
        logger.error("Skill-Update fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{name}", status_code=200)
async def delete_skill(name: str) -> dict:
    """Löscht einen Runtime-Skill. Built-in Skills können nicht gelöscht werden."""
    mgr = get_skills_manager()
    try:
        success = mgr.delete_skill(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' nicht gefunden.")
        return {"deleted": name}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
