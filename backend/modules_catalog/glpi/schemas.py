"""
GLPI Modul – Pydantic Schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GlpiTicket(BaseModel):
    """GLPI Ticket-Informationen."""

    id: int
    title: str = ""
    content: str = ""
    status: int = 1  # 1=New, 2=Processing, 3=Pending, 4=Solved, 5=Closed
    status_name: str = ""
    priority: int = 3  # 1-6
    priority_name: str = ""
    type: int = 1  # 1=Incident, 2=Request
    date_creation: str = ""
    date_mod: str = ""
    date_solved: str = ""
    category_id: int = 0
    assigned_group: str = ""
    assigned_user: str = ""


class CreateTicketRequest(BaseModel):
    """Anfrage zum Erstellen eines Tickets."""

    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    priority: int = Field(default=3, ge=1, le=6)
    category_id: int = Field(default=0)
    ticket_type: int = Field(default=1)  # 1=Incident, 2=Request
    assigned_group_id: int = Field(default=0)


class TicketSearchRequest(BaseModel):
    """Suchkriterien für Tickets."""

    status: int | None = None
    priority: int | None = None
    keyword: str = ""
    limit: int = Field(default=10, ge=1, le=100)


class TicketStats(BaseModel):
    """Ticket-Statistiken."""

    total: int = 0
    new: int = 0
    processing: int = 0
    pending: int = 0
    solved: int = 0
    closed: int = 0
