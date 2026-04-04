"""Shared lightweight API schemas for module routes."""

from __future__ import annotations

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool = True
    data: dict | list | str | None = None
    error: str | None = None
