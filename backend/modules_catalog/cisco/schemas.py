"""
Cisco Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class CiscoInterface(BaseModel):
    """Network interface."""

    name: str
    status: str  # up, down
    speed: str = ""
    duplex: str = ""
    description: str = ""
    vlan: Optional[int] = None
    in_bytes: int = 0
    out_bytes: int = 0


class CiscoVlan(BaseModel):
    """VLAN."""

    id: int
    name: str
    status: str = "active"


class CiscoDevice(BaseModel):
    """Device info."""

    hostname: str
    model: str
    version: str
    uptime: str
    serial: str


class CiscoMacAddress(BaseModel):
    """MAC address table entry."""

    vlan: int
    mac: str
    interface: str
    type: str  # dynamic, static
    age: int = 0


class CiscoRoute(BaseModel):
    """Routing table entry."""

    destination: str
    gateway: str
    interface: str
    metric: int = 0


class CiscoActionResponse(BaseModel):
    """Response to a Cisco action."""

    action: str
    target: str
    status: str
    detail: str = ""
