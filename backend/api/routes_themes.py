"""
Theme management API:
- list/apply themes
- create/update/delete custom themes
- manage theme repos and install themes from GitHub
"""

from __future__ import annotations

import io
import json
import logging
import re
import tarfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from core.redis_client import get_redis
from core.theme_manager import (
    CUSTOM_THEMES_DIR,
    delete_custom_theme,
    get_active_theme_id,
    get_all_themes,
    list_builtin_themes,
    save_custom_theme,
    set_active_theme_id,
    summarize,
    validate_theme_id,
)
from schemas.theme import (
    ThemeActiveUpdate,
    ThemeDefinition,
    ThemeListResponse,
    ThemeRepo,
    ThemeRepoCreate,
)

logger = logging.getLogger("ninko.api.themes")
router = APIRouter(prefix="/api/themes", tags=["Themes"])

REDIS_KEY_THEME_REPOS = "ninko:settings:theme_repos"
_OFFICIAL_REPO_ID = "official"
_MAX_TARBALL_SIZE = 20 * 1024 * 1024
_DEFAULT_REPOS: list[dict[str, str]] = [
    {
        "id": _OFFICIAL_REPO_ID,
        "name": "Ninko Official Themes",
        "repo_url": "https://github.com/natorus87/ninko",
        "branch": "main",
        "themes_path": "backend/themes",
        "github_token": "",
    }
]


def _parse_github_url(url: str) -> tuple[str, str] | None:
    m = re.search(r"github\.com[:/]([^/]+)/([^/.\s]+?)(?:\.git)?\s*$", url.strip())
    return (m.group(1), m.group(2)) if m else None


def _github_headers(token: str) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _mask_repo(repo: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in repo.items() if k != "github_token"} | {
        "github_token_set": bool(repo.get("github_token"))
    }


async def _load_repos() -> list[dict[str, Any]]:
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_THEME_REPOS)
    if raw:
        repos = json.loads(raw)
        if repos:
            return repos
    return list(_DEFAULT_REPOS)


async def _save_repos(repos: list[dict[str, Any]]) -> None:
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_THEME_REPOS, json.dumps(repos))


@router.get("/", response_model=ThemeListResponse)
async def list_themes() -> ThemeListResponse:
    all_themes = get_all_themes()
    active = await get_active_theme_id()
    builtins = set(list_builtin_themes().keys())
    summaries = [
        summarize(
            t,
            is_builtin=(tid in builtins),
            is_active=(tid == active),
            source="builtin" if tid in builtins else "custom",
        )
        for tid, t in sorted(all_themes.items(), key=lambda x: x[0])
    ]
    return ThemeListResponse(themes=summaries, active_theme_id=active)


@router.get("/item/{theme_id}")
async def get_theme_item(theme_id: str) -> dict:
    theme = get_all_themes().get(theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme nicht gefunden.")
    return {"theme": theme.model_dump()}


@router.get("/active")
async def get_active_theme() -> dict:
    theme_id = await get_active_theme_id()
    all_themes = get_all_themes()
    theme = all_themes.get(theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Aktives Theme nicht gefunden.")
    return {"theme_id": theme_id, "theme": theme.model_dump()}


@router.put("/active")
async def set_active_theme(body: ThemeActiveUpdate) -> dict:
    all_themes = get_all_themes()
    if body.theme_id not in all_themes:
        raise HTTPException(status_code=404, detail=f"Theme '{body.theme_id}' nicht gefunden.")
    await set_active_theme_id(body.theme_id)
    return {"theme_id": body.theme_id, "status": "active"}


@router.post("/custom", response_model=ThemeDefinition)
async def create_custom_theme(body: ThemeDefinition) -> ThemeDefinition:
    if body.id in list_builtin_themes():
        raise HTTPException(status_code=409, detail="Theme-ID kollidiert mit Built-in Theme.")
    try:
        return save_custom_theme(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/custom/{theme_id}", response_model=ThemeDefinition)
async def update_custom_theme(theme_id: str, body: ThemeDefinition) -> ThemeDefinition:
    if theme_id != body.id:
        raise HTTPException(status_code=400, detail="Path-ID und Body-ID müssen übereinstimmen.")
    if theme_id in list_builtin_themes():
        raise HTTPException(status_code=403, detail="Built-in Themes können nicht überschrieben werden.")
    try:
        return save_custom_theme(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/custom/{theme_id}")
async def remove_custom_theme(theme_id: str) -> dict:
    if theme_id in list_builtin_themes():
        raise HTTPException(status_code=403, detail="Built-in Themes können nicht gelöscht werden.")
    deleted = delete_custom_theme(theme_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Theme nicht gefunden.")
    active = await get_active_theme_id()
    if active == theme_id:
        await set_active_theme_id("default")
    return {"deleted": True, "theme_id": theme_id}


@router.post("/custom/{theme_id}/duplicate")
async def duplicate_theme(theme_id: str) -> dict:
    all_themes = get_all_themes()
    source = all_themes.get(theme_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Theme nicht gefunden.")
    new_id = f"{theme_id}-{uuid.uuid4().hex[:6]}"
    clone = ThemeDefinition(**source.model_dump())
    clone.id = new_id
    clone.name = f"{source.name} Copy"
    save_custom_theme(clone)
    return {"theme_id": new_id, "status": "created"}


@router.get("/repos")
async def list_theme_repos() -> dict:
    repos = await _load_repos()
    return {"repos": [_mask_repo(r) for r in repos]}


@router.post("/repos")
async def add_theme_repo(body: ThemeRepoCreate) -> dict:
    if not _parse_github_url(body.repo_url):
        raise HTTPException(status_code=400, detail="Ungültige GitHub-URL.")
    repos = await _load_repos()
    repo = ThemeRepo(
        id=uuid.uuid4().hex[:10],
        name=body.name,
        repo_url=body.repo_url,
        branch=body.branch,
        themes_path=body.themes_path,
        github_token=body.github_token,
    ).model_dump()
    repos.append(repo)
    await _save_repos(repos)
    return {"repo": _mask_repo(repo)}


@router.put("/repos/{repo_id}")
async def update_theme_repo(repo_id: str, body: ThemeRepoCreate) -> dict:
    repos = await _load_repos()
    repo = next((r for r in repos if r["id"] == repo_id), None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo nicht gefunden.")
    if not _parse_github_url(body.repo_url):
        raise HTTPException(status_code=400, detail="Ungültige GitHub-URL.")
    repo.update(body.model_dump())
    await _save_repos(repos)
    return {"repo": _mask_repo(repo)}


@router.delete("/repos/{repo_id}")
async def delete_theme_repo(repo_id: str) -> dict:
    if repo_id == _OFFICIAL_REPO_ID:
        raise HTTPException(status_code=403, detail="Official Repo kann nicht gelöscht werden.")
    repos = await _load_repos()
    filtered = [r for r in repos if r["id"] != repo_id]
    if len(filtered) == len(repos):
        raise HTTPException(status_code=404, detail="Repo nicht gefunden.")
    await _save_repos(filtered)
    return {"deleted": True}


@router.get("/repos/{repo_id}/themes")
async def list_repo_themes(repo_id: str) -> dict:
    repos = await _load_repos()
    repo_cfg = next((r for r in repos if r["id"] == repo_id), None)
    if repo_cfg is None:
        raise HTTPException(status_code=404, detail="Repo nicht gefunden.")
    parsed = _parse_github_url(repo_cfg["repo_url"])
    if parsed is None:
        raise HTTPException(status_code=400, detail="Ungültige Repo-URL.")
    owner, repo_name = parsed
    branch = repo_cfg.get("branch", "main")
    themes_path = repo_cfg.get("themes_path", "backend/themes").rstrip("/")
    token = repo_cfg.get("github_token", "")
    headers = _github_headers(token)

    async with httpx.AsyncClient(timeout=20.0) as client:
        tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
        resp = await client.get(tree_url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Repo-Abfrage fehlgeschlagen ({resp.status_code})")
        tree = resp.json().get("tree", [])
        prefix = f"{themes_path}/"
        theme_ids = sorted({
            item["path"][len(prefix):].split("/")[0]
            for item in tree
            if item.get("path", "").startswith(prefix)
            and item.get("type") == "tree"
            and item["path"][len(prefix):].count("/") == 0
        })

        themes: list[dict[str, Any]] = []
        for tid in theme_ids:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{themes_path}/{tid}/theme.json"
            r = await client.get(raw_url, headers=headers)
            if r.status_code != 200:
                continue
            try:
                data = r.json()
                theme = ThemeDefinition(**data)
                themes.append(
                    {
                        "id": theme.id,
                        "name": theme.name,
                        "description": theme.description,
                        "author": theme.author,
                        "version": theme.version,
                    }
                )
            except Exception:
                continue
    return {"themes": themes, "repo_id": repo_id}


@router.post("/install-from-repo/{theme_id}")
async def install_theme_from_repo(theme_id: str, repo_id: str = Query(default=_OFFICIAL_REPO_ID)) -> dict:
    if not validate_theme_id(theme_id):
        raise HTTPException(status_code=400, detail="Ungültige Theme-ID.")
    repos = await _load_repos()
    repo_cfg = next((r for r in repos if r["id"] == repo_id), None)
    if repo_cfg is None:
        raise HTTPException(status_code=404, detail="Repo nicht gefunden.")
    parsed = _parse_github_url(repo_cfg["repo_url"])
    if parsed is None:
        raise HTTPException(status_code=400, detail="Ungültige Repo-URL.")

    owner, repo_name = parsed
    branch = repo_cfg.get("branch", "main")
    themes_path = repo_cfg.get("themes_path", "backend/themes").rstrip("/")
    token = repo_cfg.get("github_token", "")
    headers = _github_headers(token)
    tarball_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.tar.gz"

    async with httpx.AsyncClient(timeout=40.0) as client:
        resp = await client.get(tarball_url, headers=headers, follow_redirects=True)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Download fehlgeschlagen ({resp.status_code})")
        if len(resp.content) > _MAX_TARBALL_SIZE:
            raise HTTPException(status_code=413, detail="Tarball zu groß.")

    tar = tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz")
    root = f"{repo_name}-{branch}/"
    target_prefix = f"{root}{themes_path}/{theme_id}/"
    data: dict[str, bytes] = {}
    for member in tar.getmembers():
        if not member.isfile():
            continue
        if not member.name.startswith(target_prefix):
            continue
        rel = member.name[len(target_prefix):]
        if not rel or ".." in rel or rel.startswith("/"):
            continue
        extracted = tar.extractfile(member)
        if extracted is None:
            continue
        data[rel] = extracted.read()

    if "theme.json" not in data:
        raise HTTPException(status_code=404, detail="theme.json nicht gefunden.")

    try:
        theme = ThemeDefinition(**json.loads(data["theme.json"].decode("utf-8")))
    except Exception:
        raise HTTPException(status_code=400, detail="theme.json ungültig.")
    if theme.id != theme_id:
        raise HTTPException(status_code=400, detail="Theme-ID passt nicht zum angeforderten Pfad.")

    target_dir = CUSTOM_THEMES_DIR / theme_id
    target_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in data.items():
        p = target_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    return {"installed": True, "theme_id": theme_id}
