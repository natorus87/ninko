"""
GLPI module — LangGraph @tool functions.
Full implementation with GLPI REST API (httpx async).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx
from langchain_core.tools import tool

from core.vault import get_vault
from core.tls import get_connection_verify_arg

logger = logging.getLogger("ninko.modules.glpi.tools")

STATUS_MAP = {
    1: "New",
    2: "In progress",
    3: "Planned",
    4: "Pending",
    5: "Solved",
    6: "Closed",
}
PRIORITY_MAP = {
    1: "Very low",
    2: "Low",
    3: "Medium",
    4: "High",
    5: "Very high",
    6: "Critical",
}


@asynccontextmanager
async def glpi_session(connection_id: str = ""):
    """
    Context manager for GLPI API sessions.
    Creates a session and terminates it after use.
    """
    from core.connections import ConnectionManager
    from core.vault import get_vault

    if connection_id:
        conn = await ConnectionManager.get_connection("glpi", connection_id)
        if not conn:
            raise ValueError(f"GLPI connection with ID '{connection_id}' not found.")
    else:
        conn = await ConnectionManager.get_default_connection("glpi")
        if not conn:
            raise ValueError("No default GLPI connection configured.")

    vault = get_vault()
    base_url = conn.config.get("base_url", "").rstrip("/")
    app_token = ""
    user_token = ""

    if "app_token" in conn.vault_keys:
        app_token = await vault.get_secret(conn.vault_keys["app_token"]) or ""
    if "user_token" in conn.vault_keys:
        user_token = await vault.get_secret(conn.vault_keys["user_token"]) or ""

    if not base_url or not app_token or not user_token:
        raise ValueError(
            "GLPI not configured: BASE_URL, APP_TOKEN, USER_TOKEN required"
        )

    verify = await get_connection_verify_arg(conn, "glpi", default_verify=True)
    async with httpx.AsyncClient(verify=verify, timeout=30.0) as client:
        # Initialize session
        resp = await client.get(
            f"{base_url}/apirest.php/initSession",
            headers={
                "App-Token": app_token,
                "Authorization": f"user_token {user_token}",
            },
        )
        resp.raise_for_status()
        session_token = resp.json()["session_token"]

        headers = {
            "App-Token": app_token,
            "Session-Token": session_token,
            "Content-Type": "application/json",
        }

        try:
            yield client, base_url, headers
        finally:
            # Kill session
            try:
                await client.get(
                    f"{base_url}/apirest.php/killSession",
                    headers=headers,
                )
            except Exception:
                pass


@tool
async def create_ticket(
    title: str,
    description: str,
    priority: int = 3,
    category_id: int = 0,
    ticket_type: int = 1,
    assigned_group_id: int = 0,
    connection_id: str = "",
) -> dict:
    """Creates a new GLPI ticket. ticket_type: 1=Incident, 2=Request. priority: 1-6."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        payload = {
            "input": {
                "name": title,
                "content": description,
                "priority": priority,
                "type": ticket_type,
            }
        }

        cat_id = category_id or int(os.environ.get("GLPI_DEFAULT_CATEGORY_ID", "0"))
        if cat_id:
            payload["input"]["itilcategories_id"] = cat_id

        group_id = assigned_group_id or int(
            os.environ.get("GLPI_DEFAULT_GROUP_ID", "0") or "0"
        )

        resp = await client.post(
            f"{base_url}/apirest.php/Ticket",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        ticket_id = data.get("id", 0)

        # Assign group if specified
        if group_id and ticket_id:
            try:
                await client.post(
                    f"{base_url}/apirest.php/Ticket/{ticket_id}/Group_Ticket",
                    json={
                        "input": {
                            "tickets_id": ticket_id,
                            "groups_id": group_id,
                            "type": 2,
                        }
                    },
                    headers=headers,
                )
            except Exception as e:
                logger.warning("Could not assign group: %s", e)

        return {
            "action": "create_ticket",
            "ticket_id": ticket_id,
            "title": title,
            "priority": PRIORITY_MAP.get(priority, str(priority)),
            "status": "success",
            "detail": f"Ticket #{ticket_id} created: {title}",
        }


@tool
async def get_ticket(ticket_id: int, connection_id: str = "") -> dict:
    """Returns the details of a GLPI ticket."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/Ticket/{ticket_id}",
            headers=headers,
        )
        resp.raise_for_status()
        t = resp.json()

        return {
            "id": t.get("id"),
            "title": t.get("name", ""),
            "content": t.get("content", ""),
            "status": t.get("status", 0),
            "status_name": STATUS_MAP.get(t.get("status", 0), "Unknown"),
            "priority": t.get("priority", 0),
            "priority_name": PRIORITY_MAP.get(t.get("priority", 0), "Unknown"),
            "type": t.get("type", 0),
            "date_creation": t.get("date_creation", ""),
            "date_mod": t.get("date_mod", ""),
            "date_solved": t.get("date_solved", ""),
            "category_id": t.get("itilcategories_id", 0),
        }


@tool
async def search_tickets(
    status: int = 0,
    priority: int = 0,
    keyword: str = "",
    limit: int = 10,
    connection_id: str = "",
) -> list[dict]:
    """Searches GLPI tickets by status, priority, or keyword."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        params: dict = {
            "range": f"0-{limit - 1}",
            "sort": "1",
            "order": "DESC",
        }

        # Build search criteria
        criteria_idx = 0
        if status:
            params[f"criteria[{criteria_idx}][field]"] = "12"  # Status
            params[f"criteria[{criteria_idx}][searchtype]"] = "equals"
            params[f"criteria[{criteria_idx}][value]"] = str(status)
            criteria_idx += 1

        if priority:
            params[f"criteria[{criteria_idx}][field]"] = "3"  # Priority
            params[f"criteria[{criteria_idx}][searchtype]"] = "equals"
            params[f"criteria[{criteria_idx}][value]"] = str(priority)
            criteria_idx += 1

        if keyword:
            params[f"criteria[{criteria_idx}][field]"] = "1"  # Name
            params[f"criteria[{criteria_idx}][searchtype]"] = "contains"
            params[f"criteria[{criteria_idx}][value]"] = keyword
            criteria_idx += 1

        # Forced display fields
        for i, field in enumerate([1, 2, 3, 12, 15, 19]):
            params[f"forcedisplay[{i}]"] = str(field)

        resp = await client.get(
            f"{base_url}/apirest.php/search/Ticket",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()

        tickets = []
        for item in result.get("data", []):
            tickets.append(
                {
                    "id": item.get("2", 0),
                    "title": item.get("1", ""),
                    "priority": item.get("3", 0),
                    "priority_name": PRIORITY_MAP.get(item.get("3", 0), ""),
                    "status": item.get("12", 0),
                    "status_name": STATUS_MAP.get(item.get("12", 0), ""),
                    "date_creation": item.get("15", ""),
                    "date_mod": item.get("19", ""),
                }
            )

        return tickets


@tool
async def update_ticket(
    ticket_id: int,
    status: int = 0,
    solution: str = "",
    priority: int = 0,
    connection_id: str = "",
) -> dict:
    """Updates a GLPI ticket (status, solution, priority)."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        update: dict = {}
        if status:
            update["status"] = status
        if priority:
            update["priority"] = priority

        if update:
            resp = await client.put(
                f"{base_url}/apirest.php/Ticket/{ticket_id}",
                json={"input": update},
                headers=headers,
            )
            resp.raise_for_status()

        if solution:
            await add_solution(ticket_id, solution)

        return {
            "action": "update_ticket",
            "ticket_id": ticket_id,
            "updates": update,
            "status": "success",
            "detail": f"Ticket #{ticket_id} updated.",
        }


@tool
async def close_ticket(ticket_id: int, solution: str, connection_id: str = "") -> dict:
    """Closes a GLPI ticket with a solution."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        # Add solution
        await client.post(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/ITILSolution",
            json={
                "input": {
                    "content": solution,
                    "itemtype": "Ticket",
                    "items_id": ticket_id,
                }
            },
            headers=headers,
        )

        # Set status to solved
        await client.put(
            f"{base_url}/apirest.php/Ticket/{ticket_id}",
            json={"input": {"status": 5}},
            headers=headers,
        )

        return {
            "action": "close_ticket",
            "ticket_id": ticket_id,
            "status": "success",
            "detail": f"Ticket #{ticket_id} closed with solution.",
        }


@tool
async def add_followup(
    ticket_id: int, content: str, is_private: bool = False, connection_id: str = ""
) -> dict:
    """Adds a follow-up (note) to a GLPI ticket."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.post(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/ITILFollowup",
            json={
                "input": {
                    "content": content,
                    "is_private": 1 if is_private else 0,
                    "itemtype": "Ticket",
                    "items_id": ticket_id,
                }
            },
            headers=headers,
        )
        resp.raise_for_status()

        return {
            "action": "add_followup",
            "ticket_id": ticket_id,
            "status": "success",
            "detail": f"Follow-up added to ticket #{ticket_id}.",
        }


@tool
async def add_solution(
    ticket_id: int, solution_content: str, connection_id: str = ""
) -> dict:
    """Adds a solution to a GLPI ticket."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.post(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/ITILSolution",
            json={
                "input": {
                    "content": solution_content,
                    "itemtype": "Ticket",
                    "items_id": ticket_id,
                }
            },
            headers=headers,
        )
        resp.raise_for_status()

        return {
            "action": "add_solution",
            "ticket_id": ticket_id,
            "status": "success",
            "detail": f"Solution added to ticket #{ticket_id}.",
        }


@tool
async def search_users(keyword: str, connection_id: str = "") -> list[dict]:
    """Searches GLPI users by name."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/search/User",
            params={
                "criteria[0][field]": "1",
                "criteria[0][searchtype]": "contains",
                "criteria[0][value]": keyword,
                "range": "0-19",
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "2",
                "forcedisplay[2]": "34",
            },
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()

        return [
            {
                "id": item.get("2", 0),
                "name": item.get("1", ""),
                "email": item.get("34", ""),
            }
            for item in result.get("data", [])
        ]


@tool
async def list_groups(connection_id: str = "") -> list[dict]:
    """Lists all GLPI groups."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/Group",
            params={"range": "0-99"},
            headers=headers,
        )
        resp.raise_for_status()
        groups = resp.json()

        return [
            {"id": g.get("id", 0), "name": g.get("name", "")}
            for g in groups
            if isinstance(g, dict)
        ]


@tool
async def list_categories(connection_id: str = "") -> list[dict]:
    """Lists all GLPI ticket categories."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/ITILCategory",
            params={"range": "0-99"},
            headers=headers,
        )
        resp.raise_for_status()
        categories = resp.json()

        return [
            {
                "id": c.get("id", 0),
                "name": c.get("name", ""),
                "completename": c.get("completename", ""),
            }
            for c in categories
            if isinstance(c, dict)
        ]


@tool
async def get_ticket_stats(connection_id: str = "") -> dict:
    """Returns ticket statistics (count per status)."""
    stats = {
        "total": 0,
        "new": 0,
        "processing": 0,
        "pending": 0,
        "solved": 0,
        "closed": 0,
    }

    status_fields = {
        1: "new",
        2: "processing",
        3: "pending",
        4: "pending",
        5: "solved",
        6: "closed",
    }

    for status_id, field in status_fields.items():
        try:
            async with glpi_session(connection_id) as (client, base_url, headers):
                resp = await client.get(
                    f"{base_url}/apirest.php/search/Ticket",
                    params={
                        "criteria[0][field]": "12",
                        "criteria[0][searchtype]": "equals",
                        "criteria[0][value]": str(status_id),
                        "range": "0-0",
                    },
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("totalcount", 0)
                    stats[field] += count
                    stats["total"] += count
        except Exception:
            pass

    return stats


@tool
async def get_ticket_attachments(ticket_id: int, connection_id: str = "") -> dict:
    """
    Get all attachments (files, images) from a GLPI ticket.
    Use this when the user asks for attachments or to view images in a ticket.
    """
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/Document",
            headers=headers,
        )
        resp.raise_for_status()
        documents = resp.json()

        attachments = []
        for doc in documents:
            if isinstance(doc, dict):
                doc_id = doc.get("id", 0)
                attachments.append(
                    {
                        "id": doc_id,
                        "filename": doc.get("filename", ""),
                        "mime": doc.get("mime", ""),
                        "url": f"{base_url}/front/document.send.php?docid={doc_id}&ticket={ticket_id}",
                    }
                )

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "attachments": attachments,
        }


@tool
async def get_ticket_followups(ticket_id: int, connection_id: str = "") -> dict:
    """
    Get all follow-ups (replies) from a GLPI ticket.
    Use this when the user asks to see the conversation or reply history.
    """
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/ITILFollowup",
            headers=headers,
        )
        resp.raise_for_status()
        followups = resp.json()

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "followups": [
                {
                    "id": f.get("id"),
                    "content": f.get("content", ""),
                    "author": f.get("users_id", 0),
                    "is_private": f.get("is_private", 0),
                    "date": f.get("date_creation", ""),
                }
                for f in followups
                if isinstance(f, dict)
            ],
        }


@tool
async def get_ticket_solutions(ticket_id: int, connection_id: str = "") -> dict:
    """
    Get all solutions from a GLPI ticket.
    Use this when the user asks for solutions or resolutions.
    """
    async with glpi_session(connection_id) as (client, base_url, headers):
        resp = await client.get(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/ITILSolution",
            headers=headers,
        )
        resp.raise_for_status()
        solutions = resp.json()

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "solutions": [
                {
                    "id": s.get("id"),
                    "content": s.get("content", ""),
                    "author": s.get("users_id", 0),
                    "date": s.get("date_creation", ""),
                }
                for s in solutions
                if isinstance(s, dict)
            ],
        }
