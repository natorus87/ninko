"""GitLab module — LangGraph @tool functions."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.gitlab.tools")


async def _get_gitlab_config(connection_id: str = "") -> dict:
    """Load GitLab config and secrets from ConnectionManager."""
    if connection_id:
        conn = await ConnectionManager.get_connection("gitlab", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"GitLab-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"GitLab connection with ID '{connection_id}' not found.",
                    fr=f"Connexion GitLab avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión GitLab con ID '{connection_id}' no encontrada.",
                    it=f"Connessione GitLab con ID '{connection_id}' non trovata.",
                    nl=f"GitLab-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie GitLab z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão GitLab com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のGitLab接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的GitLab连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("gitlab")

    if conn:
        vault = get_vault()
        token = conn.vault_keys.get("GITLAB_TOKEN")
        token_value = (
            await vault.get_secret(token) if token else conn.config.get("token", "")
        )
        return {
            "url": conn.config.get("url", ""),
            "token": token_value,
        }

    url = os.environ.get("GITLAB_URL", "https://gitlab.com")
    token = os.environ.get("GITLAB_TOKEN", "")

    if not token:
        raise ValueError(
            _t(
                de="Keine GitLab-Verbindung konfiguriert. Bitte GitLab-Token in den Einstellungen setzen.",
                en="No GitLab connection configured. Please set GitLab token in settings.",
                fr="Aucune connexion GitLab configurée. Veuillez définir le token GitLab dans les paramètres.",
                es="No hay conexión GitLab configurada. Por favor configure el token de GitLab en la configuración.",
                it="Nessuna connessione GitLab configurata. Per favore imposta il token GitLab nelle impostazioni.",
                nl="Geen GitLab-verbinding geconfigureerd. Stel alstublieft het GitLab-token in in de instellingen.",
                pl="Nie skonfigurowano połączenia GitLab. Ustaw token GitLab w ustawieniach.",
                pt="Nenhuma conexão GitLab configurada. Por favor, defina o token do GitLab nas configurações.",
                ja="GitLab接続が設定されていません。設定でGitLabトークンを設定してください。",
                zh="未配置GitLab连接。请在设置中设置GitLab令牌。",
            )
        )

    return {"url": url, "token": token}


async def _gitlab_request(
    method: str,
    endpoint: str,
    url: str,
    token: str,
    json_data: dict = None,
    params: dict = None,
) -> Any:
    """Make a request to GitLab API."""
    headers = {"Private-Token": token}

    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            resp = await client.get(
                f"{url}/api/v4{endpoint}", headers=headers, params=params
            )
        elif method == "POST":
            resp = await client.post(
                f"{url}/api/v4{endpoint}",
                headers=headers,
                json=json_data,
                params=params,
            )
        elif method == "PUT":
            resp = await client.put(
                f"{url}/api/v4{endpoint}", headers=headers, json=json_data
            )
        elif method == "DELETE":
            resp = await client.delete(
                f"{url}/api/v4{endpoint}", headers=headers, params=params
            )
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise ValueError(f"GitLab API error: {resp.status_code} - {resp.text}")

        return resp.json()


@tool("get_gitlab_status")
async def get_gitlab_status(connection_id: str = "") -> Dict:
    """
    Get GitLab server status and version.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        Dict with version, status, and info
    """
    config = await _get_gitlab_config(connection_id)

    version = await _gitlab_request("GET", "/version", config["url"], config["token"])
    user = await _gitlab_request("GET", "/user", config["url"], config["token"])

    return {
        "version": version.get("version"),
        "revision": version.get("revision"),
        "user": user.get("username"),
        "status": "online",
    }


@tool("list_gitlab_projects")
async def list_gitlab_projects(
    membership: bool = True, connection_id: str = ""
) -> List[Dict]:
    """
    List GitLab projects.

    Args:
        membership: Only show projects where user is a member
        connection_id: Optional connection ID for named connection

    Returns:
        List of project objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        "/projects",
        config["url"],
        config["token"],
        params={"membership": membership, "per_page": 50},
    )

    projects = []
    for proj in result:
        projects.append(
            {
                "id": proj.get("id"),
                "name": proj.get("name"),
                "path": proj.get("path_with_namespace"),
                "web_url": proj.get("web_url"),
                "description": proj.get("description"),
                "default_branch": proj.get("default_branch"),
                "visibility": proj.get("visibility"),
                "last_activity_at": proj.get("last_activity_at"),
            }
        )

    return projects


@tool("get_gitlab_project")
async def get_gitlab_project(project_id: int, connection_id: str = "") -> Dict:
    """
    Get detailed project information.

    Args:
        project_id: GitLab project ID (can be numeric ID or path-encoded)
        connection_id: Optional connection ID for named connection

    Returns:
        Project details
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET", f"/projects/{project_id}", config["url"], config["token"]
    )

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "path": result.get("path_with_namespace"),
        "web_url": result.get("web_url"),
        "description": result.get("description"),
        "default_branch": result.get("default_branch"),
        "visibility": result.get("visibility"),
        "archived": result.get("archived"),
        "created_at": result.get("created_at"),
        "last_activity_at": result.get("last_activity_at"),
        "open_issues_count": result.get("open_issues_count"),
        "star_count": result.get("star_count"),
        "forks_count": result.get("forks_count"),
    }


@tool("list_gitlab_pipelines")
async def list_gitlab_pipelines(
    project_id: int, status: str = "", connection_id: str = ""
) -> List[Dict]:
    """
    List pipelines for a project.

    Args:
        project_id: GitLab project ID
        status: Filter by status (running, success, failed, canceled)
        connection_id: Optional connection ID for named connection

    Returns:
        List of pipeline objects
    """
    config = await _get_gitlab_config(connection_id)
    params = {"per_page": 20}
    if status:
        params["status"] = status

    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/pipelines",
        config["url"],
        config["token"],
        params=params,
    )

    pipelines = []
    for pipe in result:
        pipelines.append(
            {
                "id": pipe.get("id"),
                "status": pipe.get("status"),
                "ref": pipe.get("ref"),
                "sha": pipe.get("sha"),
                "web_url": pipe.get("web_url"),
                "created_at": pipe.get("created_at"),
                "updated_at": pipe.get("updated_at"),
            }
        )

    return pipelines


@tool("get_gitlab_pipeline")
async def get_gitlab_pipeline(
    project_id: int, pipeline_id: int, connection_id: str = ""
) -> Dict:
    """
    Get detailed pipeline information.

    Args:
        project_id: GitLab project ID
        pipeline_id: GitLab pipeline ID
        connection_id: Optional connection ID for named connection

    Returns:
        Pipeline details
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/pipelines/{pipeline_id}",
        config["url"],
        config["token"],
    )

    return {
        "id": result.get("id"),
        "status": result.get("status"),
        "ref": result.get("ref"),
        "sha": result.get("sha"),
        "web_url": result.get("web_url"),
        "created_at": result.get("created_at"),
        "updated_at": result.get("updated_at"),
        "duration": result.get("duration"),
        "queued_duration": result.get("queued_duration"),
    }


@tool("trigger_gitlab_pipeline")
async def trigger_gitlab_pipeline(
    project_id: int, ref: str = "main", variables: dict = None, connection_id: str = ""
) -> Dict:
    """
    Trigger a new pipeline.

    Args:
        project_id: GitLab project ID
        ref: Branch or tag name to trigger
        variables: Optional variables dict
        connection_id: Optional connection ID for named connection

    Returns:
        Created pipeline object
    """
    config = await _get_gitlab_config(connection_id)
    params = {"ref": ref}
    if variables:
        params["variables"] = [{"key": k, "value": v} for k, v in variables.items()]

    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/pipeline",
        config["url"],
        config["token"],
        params=params,
    )

    return {
        "id": result.get("id"),
        "status": result.get("status"),
        "ref": result.get("ref"),
        "web_url": result.get("web_url"),
    }


@tool("cancel_gitlab_pipeline")
async def cancel_gitlab_pipeline(
    project_id: int, pipeline_id: int, connection_id: str = ""
) -> Dict:
    """
    Cancel a running pipeline.

    Args:
        project_id: GitLab project ID
        pipeline_id: GitLab pipeline ID
        connection_id: Optional connection ID for named connection

    Returns:
        Canceled pipeline object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/pipelines/{pipeline_id}/cancel",
        config["url"],
        config["token"],
    )

    return {"status": result.get("status"), "id": result.get("id")}


@tool("retry_gitlab_pipeline")
async def retry_gitlab_pipeline(
    project_id: int, pipeline_id: int, connection_id: str = ""
) -> Dict:
    """
    Retry a failed pipeline.

    Args:
        project_id: GitLab project ID
        pipeline_id: GitLab pipeline ID
        connection_id: Optional connection ID for named connection

    Returns:
        Retried pipeline object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/pipelines/{pipeline_id}/retry",
        config["url"],
        config["token"],
    )

    return {"status": result.get("status"), "id": result.get("id")}


@tool("list_gitlab_jobs")
async def list_gitlab_jobs(
    project_id: int, pipeline_id: int = None, connection_id: str = ""
) -> List[Dict]:
    """
    List jobs for a pipeline or project.

    Args:
        project_id: GitLab project ID
        pipeline_id: Optional pipeline ID to filter jobs
        connection_id: Optional connection ID for named connection

    Returns:
        List of job objects
    """
    config = await _get_gitlab_config(connection_id)

    if pipeline_id:
        endpoint = f"/projects/{project_id}/pipelines/{pipeline_id}/jobs"
    else:
        endpoint = f"/projects/{project_id}/jobs"

    result = await _gitlab_request(
        "GET", endpoint, config["url"], config["token"], params={"per_page": 50}
    )

    jobs = []
    for job in result:
        jobs.append(
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "status": job.get("status"),
                "stage": job.get("stage"),
                "started_at": job.get("started_at"),
                "finished_at": job.get("finished_at"),
                "duration": job.get("duration"),
            }
        )

    return jobs


@tool("get_gitlab_job_log")
async def get_gitlab_job_log(
    project_id: int, job_id: int, connection_id: str = ""
) -> str:
    """
    Get job log (trace).

    Args:
        project_id: GitLab project ID
        job_id: GitLab job ID
        connection_id: Optional connection ID for named connection

    Returns:
        Job log as string
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/jobs/{job_id}/trace",
        config["url"],
        config["token"],
    )

    return result


@tool("list_gitlab_merge_requests")
async def list_gitlab_merge_requests(
    project_id: int, state: str = "opened", connection_id: str = ""
) -> List[Dict]:
    """
    List merge requests.

    Args:
        project_id: GitLab project ID
        state: Filter by state (opened, closed, merged, all)
        connection_id: Optional connection ID for named connection

    Returns:
        List of merge request objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/merge_requests",
        config["url"],
        config["token"],
        params={"state": state, "per_page": 20},
    )

    mrs = []
    for mr in result:
        mrs.append(
            {
                "id": mr.get("id"),
                "iid": mr.get("iid"),
                "title": mr.get("title"),
                "state": mr.get("state"),
                "source_branch": mr.get("source_branch"),
                "target_branch": mr.get("target_branch"),
                "web_url": mr.get("web_url"),
                "author": mr.get("author", {}).get("username"),
                "created_at": mr.get("created_at"),
                "updated_at": mr.get("updated_at"),
            }
        )

    return mrs


@tool("get_gitlab_merge_request")
async def get_gitlab_merge_request(
    project_id: int, mr_iid: int, connection_id: str = ""
) -> Dict:
    """
    Get detailed merge request information.

    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID (internal ID)
        connection_id: Optional connection ID for named connection

    Returns:
        Merge request details
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/merge_requests/{mr_iid}",
        config["url"],
        config["token"],
    )

    return {
        "id": result.get("id"),
        "iid": result.get("iid"),
        "title": result.get("title"),
        "description": result.get("description"),
        "state": result.get("state"),
        "source_branch": result.get("source_branch"),
        "target_branch": result.get("target_branch"),
        "web_url": result.get("web_url"),
        "author": result.get("author", {}).get("username"),
        "merge_status": result.get("detailed_merge_status"),
        "has_conflicts": result.get("has_conflicts"),
        "changes_count": result.get("changes_count"),
    }


@tool("create_gitlab_merge_request")
async def create_gitlab_merge_request(
    project_id: int,
    title: str,
    source_branch: str,
    target_branch: str = "main",
    description: str = "",
    connection_id: str = "",
) -> Dict:
    """
    Create a new merge request.

    Args:
        project_id: GitLab project ID
        title: MR title
        source_branch: Source branch name
        target_branch: Target branch name
        description: Optional MR description
        connection_id: Optional connection ID for named connection

    Returns:
        Created MR object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/merge_requests",
        config["url"],
        config["token"],
        json_data={
            "title": title,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "description": description,
        },
    )

    return {
        "id": result.get("id"),
        "iid": result.get("iid"),
        "web_url": result.get("web_url"),
    }


@tool("accept_gitlab_merge_request")
async def accept_gitlab_merge_request(
    project_id: int,
    mr_iid: int,
    should_remove_source_branch: bool = False,
    connection_id: str = "",
) -> Dict:
    """
    Accept/merge a merge request.

    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        should_remove_source_branch: Delete source branch after merge
        connection_id: Optional connection ID for named connection

    Returns:
        Merged MR object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "PUT",
        f"/projects/{project_id}/merge_requests/{mr_iid}/merge",
        config["url"],
        config["token"],
        json_data={"should_remove_source_branch": should_remove_source_branch},
    )

    return {
        "state": result.get("state"),
        "merged_by": result.get("merged_by", {}).get("username"),
        "web_url": result.get("web_url"),
    }


@tool("list_gitlab_branches")
async def list_gitlab_branches(project_id: int, connection_id: str = "") -> List[Dict]:
    """
    List branches for a project.

    Args:
        project_id: GitLab project ID
        connection_id: Optional connection ID for named connection

    Returns:
        List of branch objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/repository/branches",
        config["url"],
        config["token"],
        params={"per_page": 50},
    )

    branches = []
    for branch in result:
        branches.append(
            {
                "name": branch.get("name"),
                "protected": branch.get("protected"),
                "commit": branch.get("commit", {}).get("id")[:8]
                if branch.get("commit")
                else None,
            }
        )

    return branches


@tool("list_gitlab_commits")
async def list_gitlab_commits(
    project_id: int, ref_name: str = "main", connection_id: str = ""
) -> List[Dict]:
    """
    List commits for a project.

    Args:
        project_id: GitLab project ID
        ref_name: Branch or tag name
        connection_id: Optional connection ID for named connection

    Returns:
        List of commit objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/repository/commits",
        config["url"],
        config["token"],
        params={"ref_name": ref_name, "per_page": 20},
    )

    commits = []
    for commit in result:
        commits.append(
            {
                "id": commit.get("id"),
                "short_id": commit.get("short_id"),
                "title": commit.get("title"),
                "author_name": commit.get("author_name"),
                "authored_date": commit.get("authored_date"),
                "created_at": commit.get("created_at"),
            }
        )

    return commits


@tool("list_gitlab_tags")
async def list_gitlab_tags(project_id: int, connection_id: str = "") -> List[Dict]:
    """
    List tags for a project.

    Args:
        project_id: GitLab project ID
        connection_id: Optional connection ID for named connection

    Returns:
        List of tag objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/repository/tags",
        config["url"],
        config["token"],
        params={"per_page": 30},
    )

    tags = []
    for tag in result:
        tags.append(
            {
                "name": tag.get("name"),
                "message": tag.get("message"),
                "release": tag.get("release") if tag.get("release") else None,
                "commit": tag.get("commit", {}).get("id")[:8]
                if tag.get("commit")
                else None,
            }
        )

    return tags


@tool("create_gitlab_release")
async def create_gitlab_release(
    project_id: int,
    tag_name: str,
    name: str = "",
    description: str = "",
    connection_id: str = "",
) -> Dict:
    """
    Create a new release.

    Args:
        project_id: GitLab project ID
        tag_name: Tag name for the release
        name: Release name
        description: Release notes
        connection_id: Optional connection ID for named connection

    Returns:
        Created release object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/releases",
        config["url"],
        config["token"],
        json_data={
            "tag_name": tag_name,
            "name": name or tag_name,
            "description": description,
        },
    )

    return {
        "tag_name": result.get("tag_name"),
        "name": result.get("name"),
        "web_url": result.get("_links", {}).get("self"),
    }


@tool("list_gitlab_variables")
async def list_gitlab_variables(project_id: int, connection_id: str = "") -> List[Dict]:
    """
    List CI/CD variables for a project.

    Args:
        project_id: GitLab project ID
        connection_id: Optional connection ID for named connection

    Returns:
        List of variable objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET", f"/projects/{project_id}/variables", config["url"], config["token"]
    )

    variables = []
    for var in result:
        variables.append(
            {
                "key": var.get("key"),
                "value": var.get("value"),
                "variable_type": var.get("variable_type"),
                "protected": var.get("protected"),
            }
        )

    return variables


@tool("create_gitlab_variable")
async def create_gitlab_variable(
    project_id: int,
    key: str,
    value: str,
    variable_type: str = "env_var",
    masked: bool = False,
    connection_id: str = "",
) -> Dict:
    """
    Create or update a CI/CD variable.

    Args:
        project_id: GitLab project ID
        key: Variable key
        value: Variable value
        variable_type: env_var or file
        masked: Hide variable in job logs
        connection_id: Optional connection ID for named connection

    Returns:
        Created variable object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/variables",
        config["url"],
        config["token"],
        json_data={
            "key": key,
            "value": value,
            "variable_type": variable_type,
            "masked": masked,
        },
    )

    return {"key": result.get("key"), "variable_type": result.get("variable_type")}


@tool("delete_gitlab_variable")
async def delete_gitlab_variable(
    project_id: int, key: str, connection_id: str = ""
) -> Dict:
    """
    Delete a CI/CD variable.

    Args:
        project_id: GitLab project ID
        key: Variable key to delete
        connection_id: Optional connection ID for named connection

    Returns:
        Deletion result
    """
    config = await _get_gitlab_config(connection_id)
    await _gitlab_request(
        "DELETE",
        f"/projects/{project_id}/variables/{key}",
        config["url"],
        config["token"],
    )

    return {"deleted": key, "result": "success"}


@tool("get_gitlab_pipeline_schedules")
async def get_gitlab_pipeline_schedules(
    project_id: int, connection_id: str = ""
) -> List[Dict]:
    """
    List pipeline schedules.

    Args:
        project_id: GitLab project ID
        connection_id: Optional connection ID for named connection

    Returns:
        List of schedule objects
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "GET",
        f"/projects/{project_id}/pipeline_schedules",
        config["url"],
        config["token"],
    )

    schedules = []
    for sched in result:
        schedules.append(
            {
                "id": sched.get("id"),
                "description": sched.get("description"),
                "ref": sched.get("ref"),
                "cron": sched.get("cron"),
                "active": sched.get("active"),
                "next_run_at": sched.get("next_run_at"),
            }
        )

    return schedules


@tool("create_gitlab_pipeline_schedule")
async def create_gitlab_pipeline_schedule(
    project_id: int, description: str, ref: str, cron: str, connection_id: str = ""
) -> Dict:
    """
    Create a new pipeline schedule.

    Args:
        project_id: GitLab project ID
        description: Schedule description
        ref: Branch to run pipeline on
        cron: Cron expression (e.g., "0 2 * * *")
        connection_id: Optional connection ID for named connection

    Returns:
        Created schedule object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/pipeline_schedules",
        config["url"],
        config["token"],
        json_data={"description": description, "ref": ref, "cron": cron},
    )

    return {
        "id": result.get("id"),
        "description": result.get("description"),
        "cron": result.get("cron"),
    }


@tool("trigger_gitlab_pipeline_schedule")
async def trigger_gitlab_pipeline_schedule(
    project_id: int, schedule_id: int, connection_id: str = ""
) -> Dict:
    """
    Trigger a pipeline schedule manually.

    Args:
        project_id: GitLab project ID
        schedule_id: Schedule ID
        connection_id: Optional connection ID for named connection

    Returns:
        Triggered pipeline object
    """
    config = await _get_gitlab_config(connection_id)
    result = await _gitlab_request(
        "POST",
        f"/projects/{project_id}/pipeline_schedules/{schedule_id}/play",
        config["url"],
        config["token"],
    )

    return {"pipeline_id": result.get("id"), "status": result.get("status")}
