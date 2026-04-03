"""
OpenProject Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class OpenProjectProject(BaseModel):
    """OpenProject project."""

    id: int
    name: str
    identifier: str
    description: Optional[str] = None
    status: str = "active"
    created_at: Optional[str] = None


class OpenProjectWorkPackage(BaseModel):
    """Work package (task/bug)."""

    id: int
    subject: str
    description: Optional[str] = None
    type: str = "Task"
    status: str
    priority: str = "normal"
    assignee: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    estimated_hours: Optional[float] = None


class OpenProjectUser(BaseModel):
    """OpenProject user."""

    id: int
    name: str
    email: str
    login: str
    status: str = "active"


class OpenProjectTimeEntry(BaseModel):
    """Time entry."""

    id: int
    hours: float
    activity: str
    spent_on: str
    work_package: Optional[int] = None
    user: Optional[int] = None


class OpenProjectActionResponse(BaseModel):
    """Response to an OpenProject action."""

    action: str
    target: str
    status: str
    detail: str = ""
