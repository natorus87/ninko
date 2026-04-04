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
        "icon": "🦊",
    },
    health_check=check_gitlab_health,
)
