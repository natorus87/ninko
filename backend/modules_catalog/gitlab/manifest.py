"""GitLab module manifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_gitlab_health(connection_id: str = "") -> dict:
    """Health check for GitLab API."""
    from .tools import get_gitlab_status

    try:
        result = await get_gitlab_status(connection_id)
        return {"status": "ok", "detail": "GitLab reachable", "info": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="gitlab",
    display_name="GitLab",
    description="GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests und Releases.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="GITLAB_",
    required_secrets=["GITLAB_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "gitlab",
        "gitlab ci",
        "gitlab pipeline",
        "merge request",
        "repository",
        "commit",
    ],
    api_prefix="/api/gitlab",
    dashboard_tab={
        "id": "gitlab",
        "label": "GitLab",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 0 1-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 0 1 4.82 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0 1 18.6 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.51 1.22 3.78a.84.84 0 0 1-.3.92z"/></svg>',
    },
    health_check=check_gitlab_health,
)
