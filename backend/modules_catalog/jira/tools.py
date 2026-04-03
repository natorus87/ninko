"""
Jira Module — LangGraph @tool functions.
"""

from __future__ import annotations

import logging
import os
import base64
from typing import Any

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.jira.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Load config and secrets from ConnectionManager or env vars."""
    if connection_id:
        conn = await ConnectionManager.get_connection("jira", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Jira-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Jira connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("jira")

    if conn:
        base_url = conn.config.get("url", "")
        vault = get_vault()
        email = conn.config.get("email", "")
        api_key = None
        api_key_path = conn.vault_keys.get("JIRA_API_KEY")
        if api_key_path:
            api_key = await vault.get_secret(api_key_path)
        return {"base_url": base_url.rstrip("/"), "email": email, "api_key": api_key}

    base_url = os.environ.get("JIRA_URL", "")
    email = os.environ.get("JIRA_EMAIL", "")
    api_key = os.environ.get("JIRA_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de=(
                    "Keine Jira-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen JIRA_URL / JIRA_EMAIL / JIRA_API_KEY setzen."
                ),
                en=(
                    "No Jira connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars JIRA_URL / JIRA_EMAIL / JIRA_API_KEY."
                ),
            )
        )

    return {"base_url": base_url.rstrip("/"), "email": email, "api_key": api_key}


def _build_auth_header(email: str, api_key: str) -> str:
    """Build Basic Auth header for Jira."""
    credentials = f"{email}:{api_key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def _jira_request(
    base_url: str,
    auth_header: str,
    method: str,
    endpoint: str,
    params: dict | None = None,
    data: dict | None = None,
) -> dict:
    """Make a request to the Jira API."""
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{base_url}/rest/api/3{endpoint}"
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
async def get_jira_projects(connection_id: str = "") -> dict:
    """
    Retrieve all projects from Jira.
    Use this when the user asks for projects or to see available projects.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            "/project",
            {"maxResults": 100},
        )
        return {
            "status": "success",
            "projects": result.get("values", result),
        }
    except Exception as e:
        logger.error("get_jira_projects failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_project(project_key: str, connection_id: str = "") -> dict:
    """
    Get details of a specific project.
    Use this when the user asks for details about a specific project.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            f"/project/{project_key}",
        )
        return {
            "status": "success",
            "project": result,
        }
    except Exception as e:
        logger.error("get_jira_project failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_issues(
    project_key: str = "",
    status: str = "open",
    jql: str = "",
    max_results: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Retrieve issues from Jira.
    Use this when the user asks for tickets, issues, or bugs.
    Can filter by project, status, or custom JQL.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        if jql:
            query = jql
        elif project_key:
            if status == "open":
                query = f"project = {project_key} AND status NOT IN (Done, Closed)"
            else:
                query = f"project = {project_key}"
        else:
            query = " ORDER BY updated DESC"
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            "/search",
            {"jql": query, "maxResults": min(max_results, 100)},
        )
        return {
            "status": "success",
            "issues": result.get("issues", []),
            "total": result.get("total", 0),
        }
    except Exception as e:
        logger.error("get_jira_issues failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_issue(issue_key: str, connection_id: str = "") -> dict:
    """
    Get details of a specific issue.
    Use this when the user asks for details about a specific ticket.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            f"/issue/{issue_key}",
            {"fields": "summary,description,status,priority,assignee,reporter,created,updated,labels,components"},
        )
        return {
            "status": "success",
            "issue": result,
        }
    except Exception as e:
        logger.error("get_jira_issue failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def create_jira_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
    priority: str = "",
    assignee: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new issue in Jira.
    Use this when the user asks to create a ticket, issue, or bug.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
            }
        }
        if description:
            issue_data["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            }
        if priority:
            issue_data["fields"]["priority"] = {"name": priority}
        if assignee:
            issue_data["fields"]["assignee"] = {"name": assignee}

        result = await _jira_request(
            client["base_url"],
            auth,
            "POST",
            "/issue",
            data=issue_data,
        )
        return {
            "status": "success",
            "message": f"Issue created: {result.get('key')}",
            "issue": result,
        }
    except Exception as e:
        logger.error("create_jira_issue failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def update_jira_issue(
    issue_key: str,
    summary: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    connection_id: str = "",
) -> dict:
    """
    Update an existing issue.
    Use this when the user asks to update an issue status, priority, or description.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        fields = {}
        update = {}
        
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            }
        if priority:
            fields["priority"] = {"name": priority}
        
        issue_data = {}
        if fields:
            issue_data["fields"] = fields
        if status:
            issue_data["transition"] = {"id": status}
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "PUT",
            f"/issue/{issue_key}",
            data=issue_data,
        )
        return {
            "status": "success",
            "message": f"Issue {issue_key} updated.",
        }
    except Exception as e:
        logger.error("update_jira_issue failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_boards(project_key: str = "", connection_id: str = "") -> dict:
    """
    Retrieve boards from Jira.
    Use this when the user asks for boards or Kanban/Scrum boards.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        params = {"maxResults": 50}
        if project_key:
            params["projectKeyOrId"] = project_key
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            "/board",
            params,
        )
        return {
            "status": "success",
            "boards": result.get("values", result),
        }
    except Exception as e:
        logger.error("get_jira_boards failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_sprints(board_id: str, connection_id: str = "") -> dict:
    """
    Retrieve sprints from a Jira board.
    Use this when the user asks for sprints or sprint planning.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            f"/board/{board_id}/sprint",
            {"maxResults": 50},
        )
        return {
            "status": "success",
            "sprints": result.get("values", result),
        }
    except Exception as e:
        logger.error("get_jira_sprints failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_sprint(sprint_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific sprint.
    Use this when the user asks for sprint details or backlog.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            f"/sprint/{sprint_id}",
        )
        return {
            "status": "success",
            "sprint": result,
        }
    except Exception as e:
        logger.error("get_jira_sprint failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def search_jira(jql: str, max_results: int = 25, connection_id: str = "") -> dict:
    """
    Search Jira issues using JQL (Jira Query Language).
    Use this when the user asks to search for issues or complex queries.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            "/search",
            {"jql": jql, "maxResults": min(max_results, 100)},
        )
        return {
            "status": "success",
            "issues": result.get("issues", []),
            "total": result.get("total", 0),
        }
    except Exception as e:
        logger.error("search_jira failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_issue_transitions(issue_key: str, connection_id: str = "") -> dict:
    """
    Get available transitions for an issue.
    Use this when the user asks what status changes are possible for a ticket.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            f"/issue/{issue_key}/transitions",
        )
        return {
            "status": "success",
            "transitions": result.get("transitions", []),
        }
    except Exception as e:
        logger.error("get_jira_issue_transitions failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def transition_jira_issue(
    issue_key: str,
    transition_id: str,
    connection_id: str = "",
) -> dict:
    """
    Transition an issue to a new status.
    Use this when the user asks to move a ticket to a different status.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "POST",
            f"/issue/{issue_key}/transitions",
            data={"transition": {"id": transition_id}},
        )
        return {
            "status": "success",
            "message": f"Issue {issue_key} transitioned.",
        }
    except Exception as e:
        logger.error("transition_jira_issue failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_priorities(connection_id: str = "") -> dict:
    """
    Retrieve all issue priorities.
    Use this when the user asks for available priorities.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            "/priority",
        )
        return {
            "status": "success",
            "priorities": result,
        }
    except Exception as e:
        logger.error("get_jira_priorities failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_jira_issue_counts(
    project_key: str = "",
    connection_id: str = "",
) -> dict:
    """
    Get counts of issues by status for a project.
    Use this when the user asks for a summary or how many open/closed tickets.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])
        
        if project_key:
            jql = f"project = {project_key}"
        else:
            jql = "ORDER BY created DESC"
        
        result = await _jira_request(
            client["base_url"],
            auth,
            "GET",
            "/search",
            {"jql": jql, "maxResults": 0},
        )
        
        total = result.get("total", 0)
        
        return {
            "status": "success",
            "total": total,
        }
    except Exception as e:
        logger.error("get_jira_issue_counts failed: %s", e)
        return {"error": "Request failed. Check server logs."}
