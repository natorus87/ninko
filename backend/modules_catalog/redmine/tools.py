"""
Redmine Module — LangGraph @tool functions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.redmine.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Load config and secrets from ConnectionManager or env vars."""
    if connection_id:
        conn = await ConnectionManager.get_connection("redmine", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Redmine-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Redmine connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("redmine")

    if conn:
        base_url = conn.config.get("url", "")
        vault = get_vault()
        api_key = None
        api_key_path = conn.vault_keys.get("REDMINE_API_KEY")
        if api_key_path:
            api_key = await vault.get_secret(api_key_path)
        return {"base_url": base_url.rstrip("/"), "api_key": api_key}

    base_url = os.environ.get("REDMINE_URL", "")
    api_key = os.environ.get("REDMINE_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de=(
                    "Keine Redmine-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen REDMINE_URL / REDMINE_API_KEY setzen."
                ),
                en=(
                    "No Redmine connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars REDMINE_URL / REDMINE_API_KEY."
                ),
            )
        )

    return {"base_url": base_url.rstrip("/"), "api_key": api_key}


async def _redmine_request(
    base_url: str,
    api_key: str,
    method: str,
    endpoint: str,
    params: dict | None = None,
    data: dict | None = None,
) -> dict:
    """Make a request to the Redmine API."""
    headers = {
        "X-Redmine-API-Key": api_key,
        "Content-Type": "application/json",
    }

    url = f"{base_url}/{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method.upper() == "GET":
            resp = await client.get(url, params=params, headers=headers)
        elif method.upper() == "POST":
            resp = await client.post(url, json=data, headers=headers)
        elif method.upper() == "PUT":
            resp = await client.put(url, json=data, headers=headers)
        elif method.upper() == "DELETE":
            resp = await client.delete(url, params=params, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        resp.raise_for_status()
        return resp.json()


@tool
async def get_redmine_projects(connection_id: str = "") -> dict:
    """
    Retrieve all projects from Redmine.
    Use this when the user asks for projects or to see available project list.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "projects.json",
            {"limit": 100},
        )
        return {
            "status": "success",
            "projects": result.get("projects", []),
            "total": result.get("total_count", 0),
        }
    except Exception as e:
        logger.error("get_redmine_projects failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_project(project_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific project.
    Use this when the user asks for details about a specific project.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            f"projects/{project_id}.json",
        )
        return {
            "status": "success",
            "project": result.get("project", {}),
        }
    except Exception as e:
        logger.error("get_redmine_project failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_issues(
    project_id: str = "",
    status: str = "open",
    limit: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Retrieve issues (tickets) from Redmine.
    Use this when the user asks for tickets, issues, or bugs.
    Can filter by project and status (open/closed/all).
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"limit": min(limit, 100), "sort": "updated_on:desc"}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status_id"] = status

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            params,
        )
        return {
            "status": "success",
            "issues": result.get("issues", []),
            "total": result.get("total_count", 0),
        }
    except Exception as e:
        logger.error("get_redmine_issues failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_issue(issue_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific issue.
    Use this when the user asks for details about a specific ticket.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            f"issues/{issue_id}.json",
            {"include": "journals,attachments,changesets"},
        )
        return {
            "status": "success",
            "issue": result.get("issue", {}),
        }
    except Exception as e:
        logger.error("get_redmine_issue failed: %s", e)
        return {"error": str(e)}


@tool
async def create_redmine_issue(
    project_id: str,
    subject: str,
    description: str = "",
    priority_id: str = "",
    assigned_to_id: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new issue in Redmine.
    Use this when the user asks to create a ticket, issue, or bug.
    """
    try:
        client = await _get_api_client(connection_id)
        issue = {
            "project_id": project_id,
            "subject": subject,
        }
        if description:
            issue["description"] = description
        if priority_id:
            issue["priority_id"] = priority_id
        if assigned_to_id:
            issue["assigned_to_id"] = assigned_to_id

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            "issues.json",
            data={"issue": issue},
        )
        return {
            "status": "success",
            "message": f"Issue created: #{result.get('issue', {}).get('id')}",
            "issue": result.get("issue", {}),
        }
    except Exception as e:
        logger.error("create_redmine_issue failed: %s", e)
        return {"error": str(e)}


@tool
async def update_redmine_issue(
    issue_id: str,
    status_id: str = "",
    priority_id: str = "",
    assigned_to_id: str = "",
    notes: str = "",
    connection_id: str = "",
) -> dict:
    """
    Update an existing issue.
    Use this when the user asks to update a ticket status, priority, or assignee.
    """
    try:
        client = await _get_api_client(connection_id)
        issue = {}
        if status_id:
            issue["status_id"] = status_id
        if priority_id:
            issue["priority_id"] = priority_id
        if assigned_to_id:
            issue["assigned_to_id"] = assigned_to_id

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "PUT",
            f"issues/{issue_id}.json",
            data={"issue": issue, "notes": notes} if notes else {"issue": issue},
        )
        return {
            "status": "success",
            "message": f"Issue #{issue_id} updated.",
            "issue": result.get("issue", {}),
        }
    except Exception as e:
        logger.error("update_redmine_issue failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_users(connection_id: str = "") -> dict:
    """
    Retrieve all users from Redmine.
    Use this when the user asks for user list or to see who has access.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "users.json",
            {"limit": 100},
        )
        return {
            "status": "success",
            "users": result.get("users", []),
            "total": result.get("total_count", 0),
        }
    except Exception as e:
        logger.error("get_redmine_users failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_time_entries(
    project_id: str = "",
    from_date: str = "",
    to_date: str = "",
    connection_id: str = "",
) -> dict:
    """
    Retrieve time entries from Redmine.
    Use this when the user asks for time entries, logged hours, or time tracking.
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"limit": 100}
        if project_id:
            params["project_id"] = project_id
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "time_entries.json",
            params,
        )
        return {
            "status": "success",
            "time_entries": result.get("time_entries", []),
            "total": result.get("total_count", 0),
        }
    except Exception as e:
        logger.error("get_redamine_time_entries failed: %s", e)
        return {"error": str(e)}


@tool
async def log_redmine_time(
    issue_id: str,
    hours: float,
    activity_id: str = "",
    comments: str = "",
    connection_id: str = "",
) -> dict:
    """
    Log time spent on an issue.
    Use this when the user asks to log time or add time entry.
    """
    try:
        client = await _get_api_client(connection_id)
        entry = {
            "issue_id": issue_id,
            "hours": hours,
        }
        if activity_id:
            entry["activity_id"] = activity_id
        if comments:
            entry["comments"] = comments

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            "time_entries.json",
            data={"time_entry": entry},
        )
        return {
            "status": "success",
            "message": f"Time logged: {hours}h on issue #{issue_id}",
            "time_entry": result.get("time_entry", {}),
        }
    except Exception as e:
        logger.error("log_redmine_time failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_issue_statuses(connection_id: str = "") -> dict:
    """
    Retrieve all possible issue statuses.
    Use this when the user asks for available statuses or workflow states.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issue_statuses.json",
        )
        return {
            "status": "success",
            "statuses": result.get("issue_statuses", []),
        }
    except Exception as e:
        logger.error("get_redmine_issue_statuses failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_priorities(connection_id: str = "") -> dict:
    """
    Retrieve all possible issue priorities.
    Use this when the user asks for available priorities.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "enumerations/issue_priorities.json",
        )
        return {
            "status": "success",
            "priorities": result.get("issue_priorities", []),
        }
    except Exception as e:
        logger.error("get_redmine_priorities failed: %s", e)
        return {"error": str(e)}


@tool
async def search_redmine_issues(
    query: str,
    connection_id: str = "",
) -> dict:
    """
    Search for issues by text query.
    Use this when the user asks to search for tickets or find issues.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            {"search": query, "limit": 50},
        )
        return {
            "status": "success",
            "issues": result.get("issues", []),
            "total": result.get("total_count", 0),
        }
    except Exception as e:
        logger.error("search_redmine_issues failed: %s", e)
        return {"error": str(e)}


@tool
async def get_redmine_issue_counts(
    project_id: str = "",
    connection_id: str = "",
) -> dict:
    """
    Get counts of issues by status for a project.
    Use this when the user asks for a summary or how many open/closed tickets.
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"status_id": "*"}
        if project_id:
            params["project_id"] = project_id

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            params,
        )

        issues = result.get("issues", [])
        open_count = sum(
            1 for i in issues if i.get("status", {}).get("is_closed") == False
        )
        closed_count = sum(
            1 for i in issues if i.get("status", {}).get("is_closed") == True
        )

        return {
            "status": "success",
            "open": open_count,
            "closed": closed_count,
            "total": len(issues),
        }
    except Exception as e:
        logger.error("get_redmine_issue_counts failed: %s", e)
        return {"error": str(e)}
