"""
Ubiquiti Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class UbiquitiDevice(BaseModel):
    """UniFi device."""

    mac: str
    name: str
    type: str
    model: str
    version: str
    uptime: int = 0
    state: int = 0  # 1 = connected
    ip: str = ""


class UbiquitiClient(BaseModel):
    """WiFi client."""

    mac: str
    hostname: str = ""
    ip: str = ""
    name: str = ""
    wired: bool = False
    signal: int = 0
    uptime: int = 0


class UbiquitiNetwork(BaseModel):
    """Network/WLAN."""

    name: str
    enabled: bool = True
    ssid: str = ""
    security: str = ""


class UbiquitiPort(BaseModel):
    """Switch port."""

    port_idx: int
    name: str
    enable: bool = True
    poe_enable: bool = False
    speed: int = 0


class UbiquitiActionResponse(BaseModel):
    """Response to a Ubiquiti action."""

    action: str
    target: str
    status: str
    detail: str = ""
