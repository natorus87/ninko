"""GitLab module API routes."""

from fastapi import APIRouter, Query

from core.schemas import ApiResponse

router = APIRouter(prefix="/gitlab", tags=["gitlab"])


@router.get("/status")
async def get_status(connection_id: str = "") -> ApiResponse:
    """Get GitLab server status."""
    from modules_catalog.gitlab.tools import get_gitlab_status

    try:
        result = await get_gitlab_status(connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects")
async def get_projects(membership: bool = True, connection_id: str = "") -> ApiResponse:
    """List all projects."""
    from modules_catalog.gitlab.tools import list_gitlab_projects

    try:
        result = await list_gitlab_projects(membership, connection_id)
        return ApiResponse(data={"projects": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}")
async def get_project(project_id: int, connection_id: str = "") -> ApiResponse:
    """Get project details."""
    from modules_catalog.gitlab.tools import get_gitlab_project

    try:
        result = await get_gitlab_project(project_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/pipelines")
async def get_pipelines(
    project_id: int, status: str = "", connection_id: str = ""
) -> ApiResponse:
    """List project pipelines."""
    from modules_catalog.gitlab.tools import list_gitlab_pipelines

    try:
        result = await list_gitlab_pipelines(project_id, status, connection_id)
        return ApiResponse(data={"pipelines": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/pipelines/{pipeline_id}")
async def get_pipeline(
    project_id: int, pipeline_id: int, connection_id: str = ""
) -> ApiResponse:
    """Get pipeline details."""
    from modules_catalog.gitlab.tools import get_gitlab_pipeline

    try:
        result = await get_gitlab_pipeline(project_id, pipeline_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/pipelines")
async def trigger_pipeline(
    project_id: int, ref: str = "main", connection_id: str = ""
) -> ApiResponse:
    """Trigger a new pipeline."""
    from modules_catalog.gitlab.tools import trigger_gitlab_pipeline

    try:
        result = await trigger_gitlab_pipeline(project_id, ref, None, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/pipelines/{pipeline_id}/cancel")
async def cancel_pipeline(
    project_id: int, pipeline_id: int, connection_id: str = ""
) -> ApiResponse:
    """Cancel a pipeline."""
    from modules_catalog.gitlab.tools import cancel_gitlab_pipeline

    try:
        result = await cancel_gitlab_pipeline(project_id, pipeline_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/pipelines/{pipeline_id}/retry")
async def retry_pipeline(
    project_id: int, pipeline_id: int, connection_id: str = ""
) -> ApiResponse:
    """Retry a failed pipeline."""
    from modules_catalog.gitlab.tools import retry_gitlab_pipeline

    try:
        result = await retry_gitlab_pipeline(project_id, pipeline_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/jobs")
async def get_jobs(
    project_id: int, pipeline_id: int = None, connection_id: str = ""
) -> ApiResponse:
    """List project jobs."""
    from modules_catalog.gitlab.tools import list_gitlab_jobs

    try:
        result = await list_gitlab_jobs(project_id, pipeline_id, connection_id)
        return ApiResponse(data={"jobs": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/jobs/{job_id}/trace")
async def get_job_trace(
    project_id: int, job_id: int, connection_id: str = ""
) -> ApiResponse:
    """Get job log."""
    from modules_catalog.gitlab.tools import get_gitlab_job_log

    try:
        result = await get_gitlab_job_log(project_id, job_id, connection_id)
        return ApiResponse(data={"trace": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/merge-requests")
async def get_merge_requests(
    project_id: int, state: str = "opened", connection_id: str = ""
) -> ApiResponse:
    """List merge requests."""
    from modules_catalog.gitlab.tools import list_gitlab_merge_requests

    try:
        result = await list_gitlab_merge_requests(project_id, state, connection_id)
        return ApiResponse(data={"merge_requests": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/merge-requests/{mr_iid}")
async def get_merge_request(
    project_id: int, mr_iid: int, connection_id: str = ""
) -> ApiResponse:
    """Get merge request details."""
    from modules_catalog.gitlab.tools import get_gitlab_merge_request

    try:
        result = await get_gitlab_merge_request(project_id, mr_iid, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/merge-requests")
async def create_merge_request(
    project_id: int,
    title: str,
    source_branch: str,
    target_branch: str = "main",
    description: str = "",
    connection_id: str = "",
) -> ApiResponse:
    """Create a merge request."""
    from modules_catalog.gitlab.tools import create_gitlab_merge_request

    try:
        result = await create_gitlab_merge_request(
            project_id, title, source_branch, target_branch, description, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.put("/projects/{project_id}/merge-requests/{mr_iid}/merge")
async def accept_merge_request(
    project_id: int, mr_iid: int, connection_id: str = ""
) -> ApiResponse:
    """Accept/merge a merge request."""
    from modules_catalog.gitlab.tools import accept_gitlab_merge_request

    try:
        result = await accept_gitlab_merge_request(
            project_id, mr_iid, False, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/branches")
async def get_branches(project_id: int, connection_id: str = "") -> ApiResponse:
    """List branches."""
    from modules_catalog.gitlab.tools import list_gitlab_branches

    try:
        result = await list_gitlab_branches(project_id, connection_id)
        return ApiResponse(data={"branches": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/commits")
async def get_commits(
    project_id: int, ref_name: str = "main", connection_id: str = ""
) -> ApiResponse:
    """List commits."""
    from modules_catalog.gitlab.tools import list_gitlab_commits

    try:
        result = await list_gitlab_commits(project_id, ref_name, connection_id)
        return ApiResponse(data={"commits": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/tags")
async def get_tags(project_id: int, connection_id: str = "") -> ApiResponse:
    """List tags."""
    from modules_catalog.gitlab.tools import list_gitlab_tags

    try:
        result = await list_gitlab_tags(project_id, connection_id)
        return ApiResponse(data={"tags": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/releases")
async def create_release(
    project_id: int,
    tag_name: str,
    name: str = "",
    description: str = "",
    connection_id: str = "",
) -> ApiResponse:
    """Create a release."""
    from modules_catalog.gitlab.tools import create_gitlab_release

    try:
        result = await create_gitlab_release(
            project_id, tag_name, name, description, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/variables")
async def get_variables(project_id: int, connection_id: str = "") -> ApiResponse:
    """List CI/CD variables."""
    from modules_catalog.gitlab.tools import list_gitlab_variables

    try:
        result = await list_gitlab_variables(project_id, connection_id)
        return ApiResponse(data={"variables": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/variables")
async def create_variable(
    project_id: int, key: str, value: str, connection_id: str = ""
) -> ApiResponse:
    """Create a variable."""
    from modules_catalog.gitlab.tools import create_gitlab_variable

    try:
        result = await create_gitlab_variable(
            project_id, key, value, "env_var", False, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.delete("/projects/{project_id}/variables/{key}")
async def delete_variable(
    project_id: int, key: str, connection_id: str = ""
) -> ApiResponse:
    """Delete a variable."""
    from modules_catalog.gitlab.tools import delete_gitlab_variable

    try:
        result = await delete_gitlab_variable(project_id, key, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/projects/{project_id}/pipeline-schedules")
async def get_schedules(project_id: int, connection_id: str = "") -> ApiResponse:
    """List pipeline schedules."""
    from modules_catalog.gitlab.tools import get_gitlab_pipeline_schedules

    try:
        result = await get_gitlab_pipeline_schedules(project_id, connection_id)
        return ApiResponse(data={"schedules": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/projects/{project_id}/pipeline-schedules")
async def create_schedule(
    project_id: int, description: str, ref: str, cron: str, connection_id: str = ""
) -> ApiResponse:
    """Create a pipeline schedule."""
    from modules_catalog.gitlab.tools import create_gitlab_pipeline_schedule

    try:
        result = await create_gitlab_pipeline_schedule(
            project_id, description, ref, cron, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)
