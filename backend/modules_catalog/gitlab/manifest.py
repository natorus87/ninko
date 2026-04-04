"""GitLab module manifest."""

from pydantic import Literal

ModuleCategory = Literal[
    "monitoring", "network", "storage", "security", "communication", "devops"
]


class ModuleManifest:
    name = "gitlab"
    category: ModuleCategory = "devops"
    version = "1.0.0"
    description = {
        "de": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests und Releases",
        "en": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests and Releases",
    }
    routing_keywords = [
        "gitlab",
        "ci",
        "cd",
        "pipeline",
        "merge request",
        "repository",
        "commit",
    ]
    api_prefix = "gitlab"
    dashboard_tab = "gitlab"
    health_check = "check_gitlab_health"


module_manifest = ModuleManifest()


async def check_gitlab_health(connection_id: str = "") -> dict:
    """Health check for GitLab API."""
    from modules_catalog.gitlab.tools import get_gitlab_status

    try:
        result = await get_gitlab_status(connection_id)
        return {"status": "healthy", "info": result}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
