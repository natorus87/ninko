"""
Lenovo XClarity Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class XClarityServer(BaseModel):
    """XClarity managed server."""

    uuid: str
    name: str
    model: str
    type: str
    status: str  # OK, Warning, Critical
    ip: str
    machine_type: Optional[str] = None
    serial_number: Optional[str] = None


class XClarityChassis(BaseModel):
    """XClarity chassis."""

    uuid: str
    name: str
    model: str
    type: str
    status: str
    ip: str


class XClarityStorage(BaseModel):
    """XClarity storage."""

    uuid: str
    name: str
    model: str
    status: str


class XClarityFirmware(BaseModel):
    """Firmware info."""

    component: str
    version: str
    status: str  # OK, UpdateAvailable


class XClarityEvent(BaseModel):
    """XClarity event."""

    id: str
    severity: str
    timestamp: str
    message: str
    source: str


class XClarityActionResponse(BaseModel):
    """Response to an XClarity action."""

    action: str
    target: str
    status: str
    detail: str = ""
