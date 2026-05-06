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
    version="1.0.1",
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
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></svg>',
    },
    health_check=check_github_health,
)
