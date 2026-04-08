"""
Ninko Skill Marketplace – Remote Skill-Repositories für Community-Sharing.

Analog zum Modul-Marketplace: catalog.json + HTTP-Download von raw.githubusercontent.com.

Redis Key: ninko:settings:skill_repos — Liste von Repo-Dicts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger("ninko.core.skill_marketplace")

_MARKETPLACE_EXCEPTIONS = (
    OSError,
    TypeError,
    ValueError,
    RuntimeError,
    KeyError,
    httpx.HTTPError,
    json.JSONDecodeError,
)

REDIS_KEY = "ninko:settings:skill_repos"

# Default official repo — seeded on first access if no repos exist
_DEFAULT_REPO = {
    "id": "official",
    "name": "Ninko Official Skills",
    "catalog_url": "https://raw.githubusercontent.com/natorus87/ninko/main/backend/skills/catalog.json",
    "builtin": True,
}


class SkillMarketplace:
    """Fetch, list, and install skills from remote repositories."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._cache_ttl = 300.0  # 5 min

    # ── Repo management ──────────────────────────────────────────────────────

    async def get_repos(self) -> list[dict]:
        """Return all configured skill repos from Redis."""
        from core.redis_client import get_redis

        redis = get_redis()
        raw = await redis.connection.get(REDIS_KEY)
        if raw:
            try:
                repos = json.loads(raw)
                if isinstance(repos, list):
                    return repos
            except _MARKETPLACE_EXCEPTIONS:
                pass
        # Seed default repo
        repos = [_DEFAULT_REPO]
        await self._save_repos(repos)
        return repos

    async def add_repo(self, repo: dict) -> None:
        """Add a new skill repository."""
        repos = await self.get_repos()

        # Validate required fields
        if not repo.get("id") or not repo.get("catalog_url"):
            raise ValueError("Repo muss 'id' und 'catalog_url' enthalten.")

        # Check for duplicate ID
        if any(r["id"] == repo["id"] for r in repos):
            raise ValueError(f"Repo mit ID '{repo['id']}' existiert bereits.")

        repo.setdefault("name", repo["id"])
        repo.setdefault("builtin", False)
        repos.append(repo)
        await self._save_repos(repos)
        logger.info("Skill-Repo hinzugefügt: %s (%s)", repo["id"], repo["catalog_url"])

    async def remove_repo(self, repo_id: str) -> None:
        """Remove a skill repository (builtin repos cannot be removed)."""
        repos = await self.get_repos()

        target = next((r for r in repos if r["id"] == repo_id), None)
        if target is None:
            raise ValueError(f"Repo '{repo_id}' nicht gefunden.")
        if target.get("builtin"):
            raise PermissionError(f"Builtin-Repo '{repo_id}' kann nicht entfernt werden.")

        repos = [r for r in repos if r["id"] != repo_id]
        await self._save_repos(repos)
        self._cache.pop(repo_id, None)
        logger.info("Skill-Repo entfernt: %s", repo_id)

    async def _save_repos(self, repos: list[dict]) -> None:
        from core.redis_client import get_redis

        redis = get_redis()
        await redis.connection.set(REDIS_KEY, json.dumps(repos))

    # ── Catalog fetching ─────────────────────────────────────────────────────

    async def fetch_catalog(self, catalog_url: str, repo_id: str = "") -> list[dict]:
        """Fetch skills catalog from a remote URL."""
        import time

        # Check cache
        cache_key = repo_id or catalog_url
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < self._cache_ttl:
            return cached[1]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(catalog_url)
                resp.raise_for_status()
                data = resp.json()
                skills = data.get("skills", [])
                # Tag each skill with its repo source
                for s in skills:
                    s["repo_id"] = repo_id
                self._cache[cache_key] = (time.time(), skills)
                logger.info(
                    "Skill-Katalog geladen: %s (%d Skills)", catalog_url, len(skills)
                )
                return skills
        except _MARKETPLACE_EXCEPTIONS as exc:
            logger.warning("Skill-Katalog konnte nicht geladen werden (%s): %s", catalog_url, exc)
            return []

    async def fetch_all_catalogs(self) -> list[dict]:
        """Aggregate skills from all configured repos."""
        repos = await self.get_repos()
        all_skills: list[dict] = []

        for repo in repos:
            catalog_url = repo.get("catalog_url", "")
            if not catalog_url:
                continue
            skills = await self.fetch_catalog(catalog_url, repo_id=repo["id"])
            # Add repo metadata to each skill
            for s in skills:
                s["repo_name"] = repo.get("name", repo["id"])
            all_skills.extend(skills)

        return all_skills

    # ── Install from remote ──────────────────────────────────────────────────

    async def install_from_remote(
        self,
        skill_url: str,
        name: str,
        modules: list[str] | None = None,
    ) -> Path:
        """
        Download a SKILL.md from a remote URL and install it via SkillsManager.
        Returns the local path of the installed skill.
        """
        from core.skills_manager import get_skills_manager

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(skill_url)
                resp.raise_for_status()
                content = resp.text
        except _MARKETPLACE_EXCEPTIONS as exc:
            raise RuntimeError(f"Skill-Download fehlgeschlagen ({skill_url}): {exc}") from exc

        if not content.strip():
            raise ValueError(f"Leere SKILL.md von {skill_url}")

        # Parse the remote SKILL.md to extract description from frontmatter
        import re

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        description = ""
        body = content
        if fm_match:
            fm_text = fm_match.group(1)
            body = fm_match.group(2).strip()
            for line in fm_text.splitlines():
                if line.strip().startswith("description:"):
                    description = line.partition(":")[2].strip().strip("'\"")
                    break

        if not description:
            description = f"Remote skill: {name}"

        sm = get_skills_manager()
        path = sm.install_skill(
            name=name,
            description=description,
            content=body,
            modules=modules,
        )
        logger.info("Remote-Skill installiert: '%s' von %s", name, skill_url)
        return path


# ── Global singleton ─────────────────────────────────────────────────────────

_global_marketplace: SkillMarketplace | None = None


def get_skill_marketplace() -> SkillMarketplace:
    """Return the global SkillMarketplace singleton."""
    global _global_marketplace
    if _global_marketplace is None:
        _global_marketplace = SkillMarketplace()
    return _global_marketplace
