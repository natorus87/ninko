"""
GLPI Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from .tools import (
    get_ticket,
    search_tickets,
    create_ticket as create_ticket_tool,
    get_ticket_stats,
    close_ticket as close_ticket_tool,
    add_followup as add_followup_tool,
)

logger = logging.getLogger("ninko.modules.glpi.routes")
router = APIRouter()


@router.get("/stats")
async def ticket_stats():
    """Ticket-Statistiken."""
    return await get_ticket_stats.ainvoke({})


@router.get("/tickets")
async def tickets(status: int = 0, priority: int = 0, keyword: str = "", limit: int = 10):
    """Tickets suchen."""
    return await search_tickets.ainvoke({
        "status": status,
        "priority": priority,
        "keyword": keyword,
        "limit": limit,
    })


@router.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: int):
    """Ticket-Details."""
    return await get_ticket.ainvoke({"ticket_id": ticket_id})


@router.post("/tickets")
async def create_ticket_api(
    title: str,
    description: str,
    priority: int = 3,
    category_id: int = 0,
    ticket_type: int = 1,
):
    """Neues Ticket erstellen."""
    return await create_ticket_tool.ainvoke({
        "title": title,
        "description": description,
        "priority": priority,
        "category_id": category_id,
        "ticket_type": ticket_type,
    })


@router.post("/tickets/{ticket_id}/close")
async def close_ticket_api(ticket_id: int, solution: str):
    """Ticket schließen."""
    return await close_ticket_tool.ainvoke({
        "ticket_id": ticket_id,
        "solution": solution,
    })


@router.post("/tickets/{ticket_id}/followup")
async def add_followup_api(ticket_id: int, content: str, is_private: bool = False):
    """Follow-up hinzufügen."""
    return await add_followup_tool.ainvoke({
        "ticket_id": ticket_id,
        "content": content,
        "is_private": is_private,
    })


@router.get("/base-url")
async def get_base_url():
    """GLPI Base-URL für Direktlinks."""
    return {"base_url": os.environ.get("GLPI_BASE_URL", "")}
