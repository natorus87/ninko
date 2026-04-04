"""GitHub module manifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_github_health(connection_id: str = "") -> dict:
    """Health check for GitHub API."""
    from .tools import get_github_status

    try:
        result = await get_github_status(connection_id)
        return {"status": "ok", "detail": "GitHub reachable", "info": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="github",
    display_name="GitHub",
    description="GitHub – Repositories, Actions, Pull Requests, Issues und Releases.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="GITHUB_",
    required_secrets=["GITHUB_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "github",
        "github actions",
        "repository",
        "repo",
        "workflow run",
        "pull request",
        "issue",
    ],
    api_prefix="/api/github",
    dashboard_tab={
        "id": "github",
        "label": "GitHub",
        "icon": "🐙",
    },
    health_check=check_github_health,
)
