"""GitHub module — LangGraph @tool functions."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.github.tools")


async def _get_github_config(connection_id: str = "") -> dict:
    """Load GitHub config and secrets from ConnectionManager."""
    if connection_id:
        conn = await ConnectionManager.get_connection("github", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"GitHub-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"GitHub connection with ID '{connection_id}' not found.",
                    fr=f"Connexion GitHub avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión GitHub con ID '{connection_id}' no encontrada.",
                    it=f"Connessione GitHub con ID '{connection_id}' non trovata.",
                    nl=f"GitHub-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie GitHub z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão GitHub com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のGitHub接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的GitHub连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("github")

    if conn:
        vault = get_vault()
        token = conn.vault_keys.get("GITHUB_TOKEN")
        token_value = (
            await vault.get_secret(token) if token else conn.config.get("token", "")
        )
        return {"token": token_value}

    token = os.environ.get("GITHUB_TOKEN", "")

    if not token:
        raise ValueError(
            _t(
                de="Keine GitHub-Verbindung konfiguriert. Bitte GitHub-Token in den Einstellungen setzen.",
                en="No GitHub connection configured. Please set GitHub token in settings.",
                fr="Aucune connexion GitHub configurée. Veuillez définir le token GitHub dans les paramètres.",
                es="No hay conexión GitHub configurada. Por favor configure el token de GitHub en la configuración.",
                it="Nessuna connessione GitHub configurata. Per favore imposta il token GitHub nelle impostazioni.",
                nl="Geen GitHub-verbinding geconfigureerd. Stel alstublieft het GitHub-token in in de instellingen.",
                pl="Nie skonfigurowano połączenia GitHub. Ustaw token GitHub w ustawieniach.",
                pt="Nenhuma conexão GitHub configurada. Por favor, defina o token do GitHub nas configurações.",
                ja="GitHub接続が設定されていません。設定でGitHubトークンを設定してください。",
                zh="未配置GitHub连接。请在设置中设置GitHub令牌。",
            )
        )

    return {"token": token}


async def _github_request(
    method: str, endpoint: str, token: str, json_data: dict = None, params: dict = None
) -> Any:
    """Make a request to GitHub API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            resp = await client.get(
                f"https://api.github.com{endpoint}", headers=headers, params=params
            )
        elif method == "POST":
            resp = await client.post(
                f"https://api.github.com{endpoint}",
                headers=headers,
                json=json_data,
                params=params,
            )
        elif method == "PUT":
            resp = await client.put(
                f"https://api.github.com{endpoint}", headers=headers, json=json_data
            )
        elif method == "PATCH":
            resp = await client.patch(
                f"https://api.github.com{endpoint}", headers=headers, json=json_data
            )
        elif method == "DELETE":
            resp = await client.delete(
                f"https://api.github.com{endpoint}", headers=headers, params=params
            )
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise ValueError(f"GitHub API error: {resp.status_code} - {resp.text}")

        return resp.json()


@tool("get_github_status")
async def get_github_status(connection_id: str = "") -> Dict:
    """
    Get GitHub user and rate limit status.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        Dict with user info and rate limit
    """
    config = await _get_github_config(connection_id)

    user = await _github_request("GET", "/user", config["token"])
    rate = await _github_request("GET", "/rate_limit", config["token"])

    return {
        "user": user.get("login"),
        "name": user.get("name"),
        "public_repos": user.get("public_repos"),
        "rate_limit": rate.get("rate", {}).get("limit"),
        "rate_remaining": rate.get("rate", {}).get("remaining"),
        "rate_reset": rate.get("rate", {}).get("reset"),
    }


@tool("list_github_repos")
async def list_github_repos(connection_id: str = "") -> List[Dict]:
    """
    List repositories for the authenticated user.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of repository objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET",
        "/user/repos",
        config["token"],
        params={"sort": "updated", "per_page": 50},
    )

    repos = []
    for repo in result:
        repos.append(
            {
                "id": repo.get("id"),
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "private": repo.get("private"),
                "html_url": repo.get("html_url"),
                "description": repo.get("description"),
                "default_branch": repo.get("default_branch"),
                "language": repo.get("language"),
                "updated_at": repo.get("updated_at"),
            }
        )

    return repos


@tool("get_github_repo")
async def get_github_repo(owner: str, repo: str, connection_id: str = "") -> Dict:
    """
    Get repository details.

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        Repository details
    """
    config = await _get_github_config(connection_id)
    result = await _github_request("GET", f"/repos/{owner}/{repo}", config["token"])

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "full_name": result.get("full_name"),
        "private": result.get("private"),
        "html_url": result.get("html_url"),
        "description": result.get("description"),
        "default_branch": result.get("default_branch"),
        "language": result.get("language"),
        "stargazers_count": result.get("stargazers_count"),
        "forks_count": result.get("forks_count"),
        "open_issues_count": result.get("open_issues_count"),
        "created_at": result.get("created_at"),
        "updated_at": result.get("updated_at"),
    }


@tool("list_github_workflows")
async def list_github_workflows(
    owner: str, repo: str, connection_id: str = ""
) -> List[Dict]:
    """
    List workflows in a repository.

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        List of workflow objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/workflows", config["token"]
    )

    workflows = []
    for wf in result.get("workflows", []):
        workflows.append(
            {
                "id": wf.get("id"),
                "name": wf.get("name"),
                "state": wf.get("state"),
                "path": wf.get("path"),
            }
        )

    return workflows


@tool("list_github_workflow_runs")
async def list_github_workflow_runs(
    owner: str, repo: str, branch: str = "", status: str = "", connection_id: str = ""
) -> List[Dict]:
    """
    List workflow runs.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Filter by branch
        status: Filter by status (completed, in_progress, queued)
        connection_id: Optional connection ID for named connection

    Returns:
        List of workflow run objects
    """
    config = await _get_github_config(connection_id)
    params = {"per_page": 20}
    if branch:
        params["branch"] = branch
    if status:
        params["status"] = status

    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/runs", config["token"], params=params
    )

    runs = []
    for run in result.get("workflow_runs", []):
        runs.append(
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "head_branch": run.get("head_branch"),
                "head_sha": run.get("head_sha"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "html_url": run.get("html_url"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
            }
        )

    return runs


@tool("get_github_workflow_run")
async def get_github_workflow_run(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> Dict:
    """
    Get workflow run details.

    Args:
        owner: Repository owner
        repo: Repository name
        run_id: Workflow run ID
        connection_id: Optional connection ID for named connection

    Returns:
        Workflow run details
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}", config["token"]
    )

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "head_branch": result.get("head_branch"),
        "head_sha": result.get("head_sha"),
        "status": result.get("status"),
        "conclusion": result.get("conclusion"),
        "html_url": result.get("html_url"),
        "created_at": result.get("created_at"),
        "updated_at": result.get("updated_at"),
        "run_started_at": result.get("run_started_at"),
        "run_attempt": result.get("run_attempt"),
    }


@tool("trigger_github_workflow")
async def trigger_github_workflow(
    owner: str,
    repo: str,
    workflow_id: int,
    ref: str = "main",
    inputs: dict = None,
    connection_id: str = "",
) -> Dict:
    """
    Trigger a workflow dispatch.

    Args:
        owner: Repository owner
        repo: Repository name
        workflow_id: Workflow ID
        ref: Branch or tag ref
        inputs: Workflow inputs
        connection_id: Optional connection ID for named connection

    Returns:
        Dispatch result
    """
    config = await _get_github_config(connection_id)
    json_data = {"ref": ref}
    if inputs:
        json_data["inputs"] = inputs

    await _github_request(
        "POST",
        f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
        config["token"],
        json_data=json_data,
    )

    return {"workflow_id": workflow_id, "ref": ref, "status": "triggered"}


@tool("cancel_github_workflow_run")
async def cancel_github_workflow_run(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> Dict:
    """
    Cancel a workflow run.

    Args:
        owner: Repository owner
        repo: Repository name
        run_id: Workflow run ID
        connection_id: Optional connection ID for named connection

    Returns:
        Cancellation result
    """
    config = await _get_github_config(connection_id)
    await _github_request(
        "POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel", config["token"]
    )

    return {"run_id": run_id, "status": "cancelled"}


@tool("rerun_github_workflow")
async def rerun_github_workflow(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> Dict:
    """
    Re-run a failed workflow.

    Args:
        owner: Repository owner
        repo: Repository name
        run_id: Workflow run ID
        connection_id: Optional connection ID for named connection

    Returns:
        Re-run result
    """
    config = await _get_github_config(connection_id)
    await _github_request(
        "POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun", config["token"]
    )

    return {"run_id": run_id, "status": "rerun_triggered"}


@tool("list_github_jobs")
async def list_github_jobs(
    owner: str, repo: str, run_id: int, connection_id: str = ""
) -> List[Dict]:
    """
    List jobs for a workflow run.

    Args:
        owner: Repository owner
        repo: Repository name
        run_id: Workflow run ID
        connection_id: Optional connection ID for named connection

    Returns:
        List of job objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs", config["token"]
    )

    jobs = []
    for job in result.get("jobs", []):
        jobs.append(
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "status": job.get("status"),
                "conclusion": job.get("conclusion"),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
            }
        )

    return jobs


@tool("get_github_job_logs")
async def get_github_job_logs(
    owner: str, repo: str, job_id: int, connection_id: str = ""
) -> str:
    """
    Get job logs.

    Args:
        owner: Repository owner
        repo: Repository name
        job_id: Job ID
        connection_id: Optional connection ID for named connection

    Returns:
        Job logs as text
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", config["token"]
    )

    return result


@tool("list_github_pull_requests")
async def list_github_pull_requests(
    owner: str, repo: str, state: str = "open", connection_id: str = ""
) -> List[Dict]:
    """
    List pull requests.

    Args:
        owner: Repository owner
        repo: Repository name
        state: Filter by state (open, closed, all)
        connection_id: Optional connection ID for named connection

    Returns:
        List of pull request objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/pulls",
        config["token"],
        params={"state": state, "per_page": 20},
    )

    prs = []
    for pr in result:
        prs.append(
            {
                "id": pr.get("id"),
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "html_url": pr.get("html_url"),
                "user": pr.get("user", {}).get("login"),
                "base": pr.get("base", {}).get("ref"),
                "head": pr.get("head", {}).get("ref"),
                "draft": pr.get("draft"),
                "created_at": pr.get("created_at"),
            }
        )

    return prs


@tool("get_github_pull_request")
async def get_github_pull_request(
    owner: str, repo: str, pr_number: int, connection_id: str = ""
) -> Dict:
    """
    Get pull request details.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number
        connection_id: Optional connection ID for named connection

    Returns:
        PR details
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/pulls/{pr_number}", config["token"]
    )

    return {
        "id": result.get("id"),
        "number": result.get("number"),
        "title": result.get("title"),
        "body": result.get("body"),
        "state": result.get("state"),
        "html_url": result.get("html_url"),
        "user": result.get("user", {}).get("login"),
        "base": result.get("base", {}).get("ref"),
        "head": result.get("head", {}).get("ref"),
        "draft": result.get("draft"),
        "mergeable": result.get("mergeable"),
        "merged": result.get("merged"),
        "mergeable_state": result.get("mergeable_state"),
    }


@tool("create_github_pull_request")
async def create_github_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
    connection_id: str = "",
) -> Dict:
    """
    Create a pull request.

    Args:
        owner: Repository owner
        repo: Repository name
        title: PR title
        head: Head branch
        base: Base branch
        body: PR description
        connection_id: Optional connection ID for named connection

    Returns:
        Created PR
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        config["token"],
        json_data={"title": title, "head": head, "base": base, "body": body},
    )

    return {
        "number": result.get("number"),
        "html_url": result.get("html_url"),
    }


@tool("merge_github_pull_request")
async def merge_github_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    commit_message: str = "",
    connection_id: str = "",
) -> Dict:
    """
    Merge a pull request.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number
        commit_message: Merge commit message
        connection_id: Optional connection ID for named connection

    Returns:
        Merge result
    """
    config = await _get_github_config(connection_id)
    json_data = {}
    if commit_message:
        json_data["commit_message"] = commit_message

    result = await _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        config["token"],
        json_data=json_data,
    )

    return {
        "sha": result.get("sha"),
        "merged": result.get("merged"),
        "message": result.get("message"),
    }


@tool("list_github_issues")
async def list_github_issues(
    owner: str, repo: str, state: str = "open", connection_id: str = ""
) -> List[Dict]:
    """
    List issues.

    Args:
        owner: Repository owner
        repo: Repository name
        state: Filter by state (open, closed, all)
        connection_id: Optional connection ID for named connection

    Returns:
        List of issue objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/issues",
        config["token"],
        params={"state": state, "per_page": 20},
    )

    issues = []
    for issue in result:
        if "pull_request" in issue:
            continue
        issues.append(
            {
                "id": issue.get("id"),
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "html_url": issue.get("html_url"),
                "user": issue.get("user", {}).get("login"),
                "labels": [l.get("name") for l in issue.get("labels", [])],
                "created_at": issue.get("created_at"),
            }
        )

    return issues


@tool("create_github_issue")
async def create_github_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    labels: list = None,
    connection_id: str = "",
) -> Dict:
    """
    Create an issue.

    Args:
        owner: Repository owner
        repo: Repository name
        title: Issue title
        body: Issue body
        labels: List of labels
        connection_id: Optional connection ID for named connection

    Returns:
        Created issue
    """
    config = await _get_github_config(connection_id)
    json_data = {"title": title, "body": body}
    if labels:
        json_data["labels"] = labels

    result = await _github_request(
        "POST", f"/repos/{owner}/{repo}/issues", config["token"], json_data=json_data
    )

    return {
        "number": result.get("number"),
        "html_url": result.get("html_url"),
    }


@tool("list_github_branches")
async def list_github_branches(
    owner: str, repo: str, connection_id: str = ""
) -> List[Dict]:
    """
    List branches.

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        List of branch objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/branches",
        config["token"],
        params={"per_page": 50},
    )

    branches = []
    for branch in result:
        branches.append(
            {
                "name": branch.get("name"),
                "protected": branch.get("protected"),
                "commit": branch.get("commit", {}).get("sha")[:8]
                if branch.get("commit")
                else None,
            }
        )

    return branches


@tool("list_github_commits")
async def list_github_commits(
    owner: str, repo: str, sha: str = "", path: str = "", connection_id: str = ""
) -> List[Dict]:
    """
    List commits.

    Args:
        owner: Repository owner
        repo: Repository name
        sha: Branch or ref
        path: Filter by file path
        connection_id: Optional connection ID for named connection

    Returns:
        List of commit objects
    """
    config = await _get_github_config(connection_id)
    params = {"per_page": 20}
    if sha:
        params["sha"] = sha
    if path:
        params["path"] = path

    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/commits", config["token"], params=params
    )

    commits = []
    for commit in result:
        commits.append(
            {
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message", "").split("\n")[0],
                "author": commit.get("commit", {}).get("author", {}).get("name"),
                "date": commit.get("commit", {}).get("author", {}).get("date"),
            }
        )

    return commits


@tool("list_github_tags")
async def list_github_tags(
    owner: str, repo: str, connection_id: str = ""
) -> List[Dict]:
    """
    List tags.

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        List of tag objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/tags", config["token"], params={"per_page": 30}
    )

    tags = []
    for tag in result:
        tags.append(
            {
                "name": tag.get("name"),
                "commit": tag.get("commit", {}).get("sha")[:8]
                if tag.get("commit")
                else None,
            }
        )

    return tags


@tool("list_github_releases")
async def list_github_releases(
    owner: str, repo: str, connection_id: str = ""
) -> List[Dict]:
    """
    List releases.

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        List of release objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/releases",
        config["token"],
        params={"per_page": 20},
    )

    releases = []
    for rel in result:
        releases.append(
            {
                "id": rel.get("id"),
                "tag_name": rel.get("tag_name"),
                "name": rel.get("name"),
                "body": rel.get("body", "")[:200],
                "html_url": rel.get("html_url"),
                "published_at": rel.get("published_at"),
            }
        )

    return releases


@tool("create_github_release")
async def create_github_release(
    owner: str,
    repo: str,
    tag_name: str,
    name: str = "",
    body: str = "",
    draft: bool = False,
    connection_id: str = "",
) -> Dict:
    """
    Create a release.

    Args:
        owner: Repository owner
        repo: Repository name
        tag_name: Tag name
        name: Release name
        body: Release notes
        draft: Is draft
        connection_id: Optional connection ID for named connection

    Returns:
        Created release
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "POST",
        f"/repos/{owner}/{repo}/releases",
        config["token"],
        json_data={
            "tag_name": tag_name,
            "name": name or tag_name,
            "body": body,
            "draft": draft,
        },
    )

    return {
        "id": result.get("id"),
        "html_url": result.get("html_url"),
    }


@tool("list_github_variables")
async def list_github_variables(
    owner: str, repo: str, connection_id: str = ""
) -> List[Dict]:
    """
    List repository variables.

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        List of variable objects
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/variables", config["token"]
    )

    variables = []
    for var in result.get("variables", []):
        variables.append(
            {
                "name": var.get("name"),
                "value": "***"
                if var.get("visibility") == "private"
                else var.get("value"),
            }
        )

    return variables


@tool("create_github_variable")
async def create_github_variable(
    owner: str, repo: str, name: str, value: str, connection_id: str = ""
) -> Dict:
    """
    Create or update a repository variable.

    Args:
        owner: Repository owner
        repo: Repository name
        name: Variable name
        value: Variable value
        connection_id: Optional connection ID for named connection

    Returns:
        Created variable
    """
    config = await _get_github_config(connection_id)
    await _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/actions/variables/{name}",
        config["token"],
        json_data={"name": name, "value": value},
    )

    return {"name": name}


@tool("delete_github_variable")
async def delete_github_variable(
    owner: str, repo: str, name: str, connection_id: str = ""
) -> Dict:
    """
    Delete a repository variable.

    Args:
        owner: Repository owner
        repo: Repository name
        name: Variable name
        connection_id: Optional connection ID for named connection

    Returns:
        Deletion result
    """
    config = await _get_github_config(connection_id)
    await _github_request(
        "DELETE", f"/repos/{owner}/{repo}/actions/variables/{name}", config["token"]
    )

    return {"deleted": name, "result": "success"}


@tool("list_github_secrets")
async def list_github_secrets(
    owner: str, repo: str, connection_id: str = ""
) -> List[Dict]:
    """
    List repository secrets (names only, not values).

    Args:
        owner: Repository owner
        repo: Repository name
        connection_id: Optional connection ID for named connection

    Returns:
        List of secret names
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", f"/repos/{owner}/{repo}/actions/secrets", config["token"]
    )

    secrets = []
    for sec in result.get("secrets", []):
        secrets.append(
            {
                "name": sec.get("name"),
                "visibility": sec.get("visibility"),
            }
        )

    return secrets


@tool("get_github_repo_content")
async def get_github_repo_content(
    owner: str, repo: str, path: str = "", ref: str = "main", connection_id: str = ""
) -> Dict:
    """
    Get repository content.

    Args:
        owner: Repository owner
        repo: Repository name
        path: File path
        ref: Branch or tag
        connection_id: Optional connection ID for named connection

    Returns:
        Content info
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{path}",
        config["token"],
        params={"ref": ref},
    )

    return {
        "name": result.get("name"),
        "path": result.get("path"),
        "type": result.get("type"),
        "size": result.get("size"),
        "content": result.get("content", "")[:500]
        if result.get("type") == "file"
        else None,
    }


@tool("search_github_code")
async def search_github_code(query: str, connection_id: str = "") -> List[Dict]:
    """
    Search code across repositories.

    Args:
        query: Search query
        connection_id: Optional connection ID for named connection

    Returns:
        List of search results
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", "/search/code", config["token"], params={"q": query, "per_page": 20}
    )

    results = []
    for item in result.get("items", []):
        results.append(
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "repository": item.get("repository", {}).get("full_name"),
                "html_url": item.get("html_url"),
            }
        )

    return results


@tool("search_github_issues")
async def search_github_issues(query: str, connection_id: str = "") -> List[Dict]:
    """
    Search issues and PRs.

    Args:
        query: Search query
        connection_id: Optional connection ID for named connection

    Returns:
        List of search results
    """
    config = await _get_github_config(connection_id)
    result = await _github_request(
        "GET", "/search/issues", config["token"], params={"q": query, "per_page": 20}
    )

    results = []
    for item in result.get("items", []):
        results.append(
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "html_url": item.get("html_url"),
                "repository": item.get("repository_url", "").replace(
                    "https://api.github.com/repos/", ""
                ),
            }
        )

    return results
