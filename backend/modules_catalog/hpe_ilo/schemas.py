"""
HPE iLO Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class IloManagerInfo(BaseModel):
    """iLO Manager information."""

    manager_type: str
    firmware_version: str
    license: str
    serial_number: str
    uuid: str


class IloSystemInfo(BaseModel):
    """Server system information from iLO."""

    name: str
    model: str
    manufacturer: str
    serial_number: str
    uuid: str
    power_state: str  # "On", "Off"
    health: str  # "OK", "Warning", "Critical"


class IloThermal(BaseModel):
    """Thermal readings from iLO."""

    temperatures: list[dict]  # [{"name": "01-Inlet", "readingC": 28, "status": "OK"}]
    fans: list[dict]  # [{"name": "Fan 1", "reading rpm": 5300, "percent": 42}]


class IloPower(BaseModel):
    """Power supplies from iLO."""

    power_supplies: list[dict]  # [{"name": "PSU 1", "status": "OK", "watts": 500}]


class IloNicInfo(BaseModel):
    """Network Interface Card info from iLO."""

    name: str
    mac_address: str
    ip_address: str
    status: str


class IloEventLog(BaseModel):
    """iLO event log entry."""

    timestamp: str
    event_source: str
    event_level: str  # "Critical", "Warning", "OK"
    message: str


class IloActionResponse(BaseModel):
    """Response to an iLO action."""

    action: str
    target: str
    status: str  # "success" | "error"
    detail: str = ""
