"""
GLPI Modul – LangGraph @tool-Funktionen.
Vollständige Implementierung mit GLPI REST API (httpx async).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx
from langchain_core.tools import tool

from core.vault import get_vault

logger = logging.getLogger("ninko.modules.glpi.tools")

STATUS_MAP = {1: "Neu", 2: "In Bearbeitung", 3: "Geplant", 4: "Wartend", 5: "Gelöst", 6: "Geschlossen"}
PRIORITY_MAP = {1: "Sehr niedrig", 2: "Niedrig", 3: "Mittel", 4: "Hoch", 5: "Sehr hoch", 6: "Kritisch"}


@asynccontextmanager
async def glpi_session(connection_id: str = ""):
    """
    Context Manager für GLPI API Sessions.
    Erstellt eine Session und beendet sie nach Gebrauch.
    """
    from core.connections import ConnectionManager
    from core.vault import get_vault
    
    if connection_id:
        conn = await ConnectionManager.get_connection("glpi", connection_id)
        if not conn:
            raise ValueError(f"GLPI Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("glpi")
        if not conn:
            raise ValueError("Keine Standard-GLPI-Verbindung konfiguriert.")

    vault = get_vault()
    base_url = conn.config.get("base_url", "").rstrip("/")
    app_token = ""
    user_token = ""
    
    if "app_token" in conn.vault_keys:
        app_token = await vault.get_secret(conn.vault_keys["app_token"]) or ""
    if "user_token" in conn.vault_keys:
        user_token = await vault.get_secret(conn.vault_keys["user_token"]) or ""

    if not base_url or not app_token or not user_token:
        raise ValueError("GLPI nicht konfiguriert: BASE_URL, APP_TOKEN, USER_TOKEN erforderlich")

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        # Session initialisieren
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
            # Session beenden
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
    """Erstellt ein neues GLPI-Ticket. ticket_type: 1=Incident, 2=Request. priority: 1-6."""
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

        group_id = assigned_group_id or int(os.environ.get("GLPI_DEFAULT_GROUP_ID", "0") or "0")

        resp = await client.post(
            f"{base_url}/apirest.php/Ticket",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        ticket_id = data.get("id", 0)

        # Gruppe zuweisen falls angegeben
        if group_id and ticket_id:
            try:
                await client.post(
                    f"{base_url}/apirest.php/Ticket/{ticket_id}/Group_Ticket",
                    json={"input": {"tickets_id": ticket_id, "groups_id": group_id, "type": 2}},
                    headers=headers,
                )
            except Exception as e:
                logger.warning("Gruppe konnte nicht zugewiesen werden: %s", e)

        return {
            "action": "create_ticket",
            "ticket_id": ticket_id,
            "title": title,
            "priority": PRIORITY_MAP.get(priority, str(priority)),
            "status": "success",
            "detail": f"Ticket #{ticket_id} erstellt: {title}",
        }


@tool
async def get_ticket(ticket_id: int, connection_id: str = "") -> dict:
    """Gibt die Details eines GLPI-Tickets zurück."""
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
            "status_name": STATUS_MAP.get(t.get("status", 0), "Unbekannt"),
            "priority": t.get("priority", 0),
            "priority_name": PRIORITY_MAP.get(t.get("priority", 0), "Unbekannt"),
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
    """Sucht GLPI-Tickets nach Status, Priorität oder Suchbegriff."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        params: dict = {
            "range": f"0-{limit - 1}",
            "sort": "1",
            "order": "DESC",
        }

        # Suchkriterien aufbauen
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

        # Forced Display Felder
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
            tickets.append({
                "id": item.get("2", 0),
                "title": item.get("1", ""),
                "priority": item.get("3", 0),
                "priority_name": PRIORITY_MAP.get(item.get("3", 0), ""),
                "status": item.get("12", 0),
                "status_name": STATUS_MAP.get(item.get("12", 0), ""),
                "date_creation": item.get("15", ""),
                "date_mod": item.get("19", ""),
            })

        return tickets


@tool
async def update_ticket(
    ticket_id: int,
    status: int = 0,
    solution: str = "",
    priority: int = 0,
    connection_id: str = "",
) -> dict:
    """Aktualisiert ein GLPI-Ticket (Status, Lösung, Priorität)."""
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
            "detail": f"Ticket #{ticket_id} aktualisiert.",
        }


@tool
async def close_ticket(ticket_id: int, solution: str, connection_id: str = "") -> dict:
    """Schließt ein GLPI-Ticket mit einer Lösung."""
    async with glpi_session(connection_id) as (client, base_url, headers):
        # Lösung hinzufügen
        await client.post(
            f"{base_url}/apirest.php/Ticket/{ticket_id}/ITILSolution",
            json={"input": {"content": solution, "itemtype": "Ticket", "items_id": ticket_id}},
            headers=headers,
        )

        # Status auf Gelöst setzen
        await client.put(
            f"{base_url}/apirest.php/Ticket/{ticket_id}",
            json={"input": {"status": 5}},
            headers=headers,
        )

        return {
            "action": "close_ticket",
            "ticket_id": ticket_id,
            "status": "success",
            "detail": f"Ticket #{ticket_id} geschlossen mit Lösung.",
        }


@tool
async def add_followup(ticket_id: int, content: str, is_private: bool = False, connection_id: str = "") -> dict:
    """Fügt ein Follow-up (Notiz) zu einem GLPI-Ticket hinzu."""
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
            "detail": f"Follow-up zu Ticket #{ticket_id} hinzugefügt.",
        }


@tool
async def add_solution(ticket_id: int, solution_content: str, connection_id: str = "") -> dict:
    """Fügt eine Lösung zu einem GLPI-Ticket hinzu."""
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
            "detail": f"Lösung zu Ticket #{ticket_id} hinzugefügt.",
        }


@tool
async def search_users(keyword: str, connection_id: str = "") -> list[dict]:
    """Sucht GLPI-Benutzer nach Name."""
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
    """Listet alle GLPI-Gruppen auf."""
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
    """Listet alle GLPI-Ticket-Kategorien auf."""
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
    """Gibt Ticket-Statistiken zurück (Anzahl pro Status)."""
    stats = {"total": 0, "new": 0, "processing": 0, "pending": 0, "solved": 0, "closed": 0}

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
