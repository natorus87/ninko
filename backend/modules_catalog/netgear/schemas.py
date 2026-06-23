"""
Netgear Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class NetgearPort(BaseModel):
    """Switch port."""

    port: str
    status: str  # Up, Down
    speed: str = ""
    duplex: str = ""
    flow_control: str = ""


class NetgearVlan(BaseModel):
    """VLAN."""

    vid: int
    name: str
    tagged_ports: str = ""
    untagged_ports: str = ""


class NetgearDevice(BaseModel):
    """Device info."""

    name: str
    model: str
    description: str
    firmware_version: str
    mac_address: str


class NetgearArpEntry(BaseModel):
    """ARP table entry."""

    ip_address: str
    mac_address: str
    age: int = 0
    interface: str = ""


class NetgearActionResponse(BaseModel):
    """Response to a Netgear action."""

    action: str
    target: str
    status: str
    detail: str = ""
