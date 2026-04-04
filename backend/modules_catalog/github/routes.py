"""GitHub module API routes."""

from fastapi import APIRouter, Query

from core.schemas import ApiResponse

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/status")
async def get_status(connection_id: str = "") -> ApiResponse:
    """Get GitHub user and rate limit status."""
    from modules_catalog.github.tools import get_github_status

    try:
        result = await get_github_status(connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos")
async def get_repos(connection_id: str = "") -> ApiResponse:
    """List repositories."""
    from modules_catalog.github.tools import list_github_repos

    try:
        result = await list_github_repos(connection_id)
        return ApiResponse(data={"repos": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}")
async def get_repo(owner: str, repo: str, connection_id: str = "") -> ApiResponse:
    """Get repository details."""
    from modules_catalog.github.tools import get_github_repo

    try:
        result = await get_github_repo(owner, repo, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/workflows")
async def get_workflows(owner: str, repo: str, connection_id: str = "") -> ApiResponse:
    """List workflows."""
    from modules_catalog.github.tools import list_github_workflows

    try:
        result = await list_github_workflows(owner, repo, connection_id)
        return ApiResponse(data={"workflows": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/workflow-runs")
async def get_workflow_runs(
    owner: str, repo: str, branch: str = "", status: str = "", connection_id: str = ""
) -> ApiResponse:
    """List workflow runs."""
    from modules_catalog.github.tools import list_github_workflow_runs

    try:
        result = await list_github_workflow_runs(
            owner, repo, branch, status, connection_id
        )
        return ApiResponse(data={"runs": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/workflow-runs/{run_id}")
async def get_workflow_run(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> ApiResponse:
    """Get workflow run details."""
    from modules_catalog.github.tools import get_github_workflow_run

    try:
        result = await get_github_workflow_run(owner, repo, run_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/repos/{owner}/{repo}/workflows/{workflow_id}/dispatch")
async def trigger_workflow(
    owner: str, repo: str, workflow_id: int, ref: str = "main", connection_id: str = ""
) -> ApiResponse:
    """Trigger a workflow."""
    from modules_catalog.github.tools import trigger_github_workflow

    try:
        result = await trigger_github_workflow(
            owner, repo, workflow_id, ref, None, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/repos/{owner}/{repo}/workflow-runs/{run_id}/cancel")
async def cancel_workflow_run(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> ApiResponse:
    """Cancel a workflow run."""
    from modules_catalog.github.tools import cancel_github_workflow_run

    try:
        result = await cancel_github_workflow_run(owner, repo, run_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/repos/{owner}/{repo}/workflow-runs/{run_id}/rerun")
async def rerun_workflow(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> ApiResponse:
    """Re-run a workflow."""
    from modules_catalog.github.tools import rerun_github_workflow

    try:
        result = await rerun_github_workflow(owner, repo, run_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/workflow-runs/{run_id}/jobs")
async def get_jobs(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> ApiResponse:
    """List workflow jobs."""
    from modules_catalog.github.tools import list_github_jobs

    try:
        result = await list_github_jobs(owner, repo, run_id, connection_id)
        return ApiResponse(data={"jobs": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/pulls")
async def get_pull_requests(
    owner: str, repo: str, state: str = "open", connection_id: str = ""
) -> ApiResponse:
    """List pull requests."""
    from modules_catalog.github.tools import list_github_pull_requests

    try:
        result = await list_github_pull_requests(owner, repo, state, connection_id)
        return ApiResponse(data={"pull_requests": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/pulls/{pr_number}")
async def get_pull_request(
    owner: str, repo: str, pr_number: int, connection_id: str = ""
) -> ApiResponse:
    """Get pull request details."""
    from modules_catalog.github.tools import get_github_pull_request

    try:
        result = await get_github_pull_request(owner, repo, pr_number, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/repos/{owner}/{repo}/pulls")
async def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
    connection_id: str = "",
) -> ApiResponse:
    """Create a pull request."""
    from modules_catalog.github.tools import create_github_pull_request

    try:
        result = await create_github_pull_request(
            owner, repo, title, head, base, body, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.put("/repos/{owner}/{repo}/pulls/{pr_number}/merge")
async def merge_pull_request(
    owner: str, repo: str, pr_number: int, connection_id: str = ""
) -> ApiResponse:
    """Merge a pull request."""
    from modules_catalog.github.tools import merge_github_pull_request

    try:
        result = await merge_github_pull_request(
            owner, repo, pr_number, "", connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/issues")
async def get_issues(
    owner: str, repo: str, state: str = "open", connection_id: str = ""
) -> ApiResponse:
    """List issues."""
    from modules_catalog.github.tools import list_github_issues

    try:
        result = await list_github_issues(owner, repo, state, connection_id)
        return ApiResponse(data={"issues": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/repos/{owner}/{repo}/issues")
async def create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    labels: list = None,
    connection_id: str = "",
) -> ApiResponse:
    """Create an issue."""
    from modules_catalog.github.tools import create_github_issue

    try:
        result = await create_github_issue(
            owner, repo, title, body, labels, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/branches")
async def get_branches(owner: str, repo: str, connection_id: str = "") -> ApiResponse:
    """List branches."""
    from modules_catalog.github.tools import list_github_branches

    try:
        result = await list_github_branches(owner, repo, connection_id)
        return ApiResponse(data={"branches": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/commits")
async def get_commits(
    owner: str, repo: str, sha: str = "", connection_id: str = ""
) -> ApiResponse:
    """List commits."""
    from modules_catalog.github.tools import list_github_commits

    try:
        result = await list_github_commits(owner, repo, sha, "", connection_id)
        return ApiResponse(data={"commits": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/tags")
async def get_tags(owner: str, repo: str, connection_id: str = "") -> ApiResponse:
    """List tags."""
    from modules_catalog.github.tools import list_github_tags

    try:
        result = await list_github_tags(owner, repo, connection_id)
        return ApiResponse(data={"tags": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/releases")
async def get_releases(owner: str, repo: str, connection_id: str = "") -> ApiResponse:
    """List releases."""
    from modules_catalog.github.tools import list_github_releases

    try:
        result = await list_github_releases(owner, repo, connection_id)
        return ApiResponse(data={"releases": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/repos/{owner}/{repo}/releases")
async def create_release(
    owner: str,
    repo: str,
    tag_name: str,
    name: str = "",
    body: str = "",
    connection_id: str = "",
) -> ApiResponse:
    """Create a release."""
    from modules_catalog.github.tools import create_github_release

    try:
        result = await create_github_release(
            owner, repo, tag_name, name, body, False, connection_id
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/repos/{owner}/{repo}/variables")
async def get_variables(owner: str, repo: str, connection_id: str = "") -> ApiResponse:
    """List repository variables."""
    from modules_catalog.github.tools import list_github_variables

    try:
        result = await list_github_variables(owner, repo, connection_id)
        return ApiResponse(data={"variables": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.put("/repos/{owner}/{repo}/variables/{name}")
async def create_variable(
    owner: str, repo: str, name: str, value: str, connection_id: str = ""
) -> ApiResponse:
    """Create or update a variable."""
    from modules_catalog.github.tools import create_github_variable

    try:
        result = await create_github_variable(owner, repo, name, value, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.delete("/repos/{owner}/{repo}/variables/{name}")
async def delete_variable(
    owner: str, repo: str, name: str, connection_id: str = ""
) -> ApiResponse:
    """Delete a variable."""
    from modules_catalog.github.tools import delete_github_variable

    try:
        result = await delete_github_variable(owner, repo, name, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/search/code")
async def search_code(q: str, connection_id: str = "") -> ApiResponse:
    """Search code."""
    from modules_catalog.github.tools import search_github_code

    try:
        result = await search_github_code(q, connection_id)
        return ApiResponse(data={"results": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/search/issues")
async def search_issues(q: str, connection_id: str = "") -> ApiResponse:
    """Search issues."""
    from modules_catalog.github.tools import search_github_issues

    try:
        result = await search_github_issues(q, connection_id)
        return ApiResponse(data={"results": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)
