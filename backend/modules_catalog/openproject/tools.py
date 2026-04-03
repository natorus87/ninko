"""
OpenProject Module — LangGraph @tool functions.
OpenProject API for project management.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.openproject.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get OpenProject API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("openproject", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"OpenProject-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"OpenProject connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("openproject")

    if conn:
        base_url = conn.config.get("url", "")
        api_key = conn.config.get("api_key", "")
        if not api_key:
            vault = get_vault()
            vault_key = conn.vault_keys.get("OPENPROJECT_API_KEY")
            if vault_key:
                api_key = await vault.get_secret(vault_key)
        return {"base_url": base_url, "api_key": api_key}

    base_url = os.environ.get("OPENPROJECT_HOST", "")
    vault = get_vault()
    api_key = await vault.get_secret("OPENPROJECT_API_KEY")
    if not api_key:
        api_key = os.environ.get("OPENPROJECT_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de="Keine OpenProject-Verbindung konfiguriert.",
                en="No OpenProject connection configured.",
            )
        )

    return {"base_url": base_url, "api_key": api_key}


async def _op_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to OpenProject API."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/api/v3{path}"
    headers = {"Authorization": f"Bearer {client['api_key']}"}

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        async with session.request(method, url, json=json) as resp:
            if resp.status == 204:
                return {"status": "OK"}
            if resp.status == 201:
                return await resp.json()
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_openproject_projects(connection_id: str = "") -> str:
    """
    List all projects in OpenProject.
    Use this to see all available projects.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _op_request("GET", "/projects", client)
        projects = data.get("_embedded", {}).get("elements", [])
        if not projects:
            return _t(de="Keine Projekte gefunden", en="No projects found")

        lines = ["📁 " + _t(de="Projekte", en="Projects")]
        for p in projects[:15]:
            status_icon = "✅" if p.get("status") == "active" else "📦"
            lines.append(f"  {status_icon} {p.get('name', '-')}")
            if p.get("identifier"):
                lines.append(f"      [{p.get('identifier')}]")

        total = len(projects)
        lines.append(f"\n✓ {total} Projekte")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_openproject_projects failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_openproject_project(project_name: str, connection_id: str = "") -> str:
    """
    Get details of a specific project.
    Use this to see project details and members.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _op_request("GET", "/projects", client)
        projects = data.get("_embedded", {}).get("elements", [])
        project = next(
            (
                p
                for p in projects
                if p.get("name") == project_name or p.get("identifier") == project_name
            ),
            None,
        )
        if not project:
            return _t(
                de=f"Projekt nicht gefunden: {project_name}",
                en=f"Project not found: {project_name}",
            )

        project_id = project.get("id")
        details = await _op_request("GET", f"/projects/{project_id}", client)

        lines = ["📁 " + _t(de="Projektdetails", en="Project details")]
        lines.append(f"  {details.get('name', '-')}")
        if details.get("description"):
            desc = details.get("description", "")[:150]
            lines.append(f"  📝 {desc}")
        lines.append(f"  Status: {details.get('status', '-')}")
        if details.get("createdAt"):
            lines.append(f"  Erstellt: {details.get('createdAt', '')[:10]}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_openproject_project failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_openproject_work_packages(
    project_name: str = "", connection_id: str = ""
) -> str:
    """
    List work packages (tasks, bugs) in OpenProject.
    Use this to see all tasks, optionally filtered by project.
    """
    try:
        client = await _get_api_client(connection_id)
        if project_name:
            projects = await _op_request("GET", "/projects", client)
            proj_list = projects.get("_embedded", {}).get("elements", [])
            project = next(
                (
                    p
                    for p in proj_list
                    if p.get("name") == project_name
                    or p.get("identifier") == project_name
                ),
                None,
            )
            if project:
                data = await _op_request(
                    "GET",
                    f"/projects/{project.get('id')}/work_packages",
                    client,
                )
            else:
                return _t(
                    de=f"Projekt nicht gefunden: {project_name}",
                    en=f"Project not found: {project_name}",
                )
        else:
            data = await _op_request("GET", "/work_packages", client)

        wps = data.get("_embedded", {}).get("elements", [])
        if not wps:
            return _t(de="Keine Work Packages gefunden", en="No work packages found")

        lines = ["📋 " + _t(de="Work Packages", en="Work packages")]
        for wp in wps[:15]:
            type_icon = (
                "🐛"
                if wp.get("type") == "Bug"
                else "✅"
                if wp.get("type") == "Task"
                else "📝"
            )
            status = (
                wp.get("status", {}).get("name", "-")
                if isinstance(wp.get("status"), dict)
                else wp.get("status", "-")
            )
            lines.append(f"  {type_icon} #{wp.get('id')} {wp.get('subject', '-')}")
            lines.append(f"      Status: {status}")

        total = len(wps)
        lines.append(f"\n✓ {total} Work Packages")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_openproject_work_packages failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_openproject_work_package(
    work_package_id: int, connection_id: str = ""
) -> str:
    """
    Get details of a specific work package.
    Use this to see full task details.
    """
    try:
        client = await _get_api_client(connection_id)
        wp = await _op_request("GET", f"/work_packages/{work_package_id}", client)

        lines = ["📋 " + _t(de="Work Package Details", en="Work package details")]
        lines.append(f"  #{wp.get('id')}: {wp.get('subject', '-')}")
        lines.append(f"  Type: {wp.get('type', '-')}")

        status = wp.get("status")
        if isinstance(status, dict):
            lines.append(f"  Status: {status.get('name', '-')}")
        else:
            lines.append(f"  Status: {status}")

        priority = wp.get("priority")
        if isinstance(priority, dict):
            lines.append(f"  Priority: {priority.get('name', '-')}")

        if wp.get("description"):
            desc = wp.get("description", "")[:200]
            lines.append(f"  📝 {desc}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_openproject_work_package failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_openproject_users(connection_id: str = "") -> str:
    """
    List users in OpenProject.
    Use this to see all team members.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _op_request("GET", "/users", client)
        users = data.get("_embedded", {}).get("elements", [])
        if not users:
            return _t(de="Keine Benutzer gefunden", en="No users found")

        lines = ["👥 " + _t(de="Benutzer", en="Users")]
        for u in users[:15]:
            name = f"{u.get('firstname', '')} {u.get('lastname', '')}".strip() or u.get(
                "login", "-"
            )
            status = u.get("status", "active")
            status_icon = "✅" if status == "active" else "❌"
            lines.append(f"  {status_icon} {name} ({u.get('email', '-')})")

        total = len(users)
        lines.append(f"\n✓ {total} Benutzer")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_openproject_users failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_openproject_time_entries(
    project_name: str = "", connection_id: str = ""
) -> str:
    """
    List time entries in OpenProject.
    Use this to see logged time.
    """
    try:
        client = await _get_api_client(connection_id)
        if project_name:
            projects = await _op_request("GET", "/projects", client)
            proj_list = projects.get("_embedded", {}).get("elements", [])
            project = next(
                (
                    p
                    for p in proj_list
                    if p.get("name") == project_name
                    or p.get("identifier") == project_name
                ),
                None,
            )
            if project:
                data = await _op_request(
                    "GET",
                    f"/projects/{project.get('id')}/time_entries",
                    client,
                )
            else:
                return _t(
                    de=f"Projekt nicht gefunden: {project_name}",
                    en=f"Project not found: {project_name}",
                )
        else:
            data = await _op_request("GET", "/time_entries", client)

        entries = data.get("_embedded", {}).get("elements", [])
        if not entries:
            return _t(de="Keine Time Entries", en="No time entries")

        lines = ["⏱️ " + _t(de="Time Entries", en="Time entries")]
        for e in entries[:15]:
            hours = e.get("hours", 0)
            date = e.get("spentOn", "-")
            activity = e.get("_embedded", {}).get("activity", {}).get("name", "-")
            lines.append(f"  {date}: {hours}h ({activity})")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_openproject_time_entries failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def create_openproject_work_package(
    project_name: str,
    subject: str,
    type: str = "Task",
    description: str = "",
    connection_id: str = "",
) -> str:
    """
    Create a new work package (task) in OpenProject.
    Use this to create a new task.
    """
    try:
        client = await _get_api_client(connection_id)
        projects = await _op_request("GET", "/projects", client)
        proj_list = projects.get("_embedded", {}).get("elements", [])
        project = next(
            (
                p
                for p in proj_list
                if p.get("name") == project_name or p.get("identifier") == project_name
            ),
            None,
        )
        if not project:
            return _t(
                de=f"Projekt nicht gefunden: {project_name}",
                en=f"Project not found: {project_name}",
            )

        project_id = project.get("id")
        wp_data = {
            "subject": subject,
            "description": {"raw": description},
            "type": type,
            "project": {"href": f"/api/v3/projects/{project_id}"},
        }
        result = await _op_request("POST", "/work_packages", client, json=wp_data)

        return _t(
            de=f"✅ Work Package erstellt: #{result.get('id')} - {subject}",
            en=f"✅ Work package created: #{result.get('id')} - {subject}",
        )
    except Exception as e:
        logger.error("create_openproject_work_package failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def update_openproject_work_package(
    work_package_id: int,
    status: str = "",
    subject: str = "",
    connection_id: str = "",
) -> str:
    """
    Update a work package (task) in OpenProject.
    Use this to change status or subject.
    """
    try:
        client = await _get_api_client(connection_id)
        update_data = {}
        if subject:
            update_data["subject"] = subject
        if status:
            status_data = {"name": status}
            update_data["status"] = status_data

        await _op_request(
            "PATCH",
            f"/work_packages/{work_package_id}",
            client,
            json=update_data,
        )
        return _t(
            de=f"✅ Work Package aktualisiert: #{work_package_id}",
            en=f"✅ Work package updated: #{work_package_id}",
        )
    except Exception as e:
        logger.error("update_openproject_work_package failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def log_openproject_time(
    project_name: str,
    hours: float,
    activity: str = "Development",
    work_package_id: int = None,
    comment: str = "",
    connection_id: str = "",
) -> str:
    """
    Log time entry in OpenProject.
    Use this to log hours worked.
    """
    try:
        client = await _get_api_client(connection_id)
        projects = await _op_request("GET", "/projects", client)
        proj_list = projects.get("_embedded", {}).get("elements", [])
        project = next(
            (
                p
                for p in proj_list
                if p.get("name") == project_name or p.get("identifier") == project_name
            ),
            None,
        )
        if not project:
            return _t(
                de=f"Projekt nicht gefunden: {project_name}",
                en=f"Project not found: {project_name}",
            )

        project_id = project.get("id")
        entry_data = {
            "hours": hours,
            "spentOn": datetime.now().strftime("%Y-%m-%d"),
            "project": {"href": f"/api/v3/projects/{project_id}"},
        }

        if work_package_id:
            entry_data["workPackage"] = {
                "href": f"/api/v3/work_packages/{work_package_id}"
            }

        if comment:
            entry_data["comment"] = {"raw": comment}

        result = await _op_request("POST", "/time_entries", client, json=entry_data)

        return _t(
            de=f"✅ {hours}h gebucht für {project_name}",
            en=f"✅ {hours}h logged for {project_name}",
        )
    except Exception as e:
        logger.error("log_openproject_time failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
