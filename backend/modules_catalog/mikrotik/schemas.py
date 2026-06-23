"""
MikroTik Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class MikrotikInterface(BaseModel):
    """Network interface."""

    name: str
    type: str
    status: str  # running, stopped
    rx_byte: int = 0
    tx_byte: int = 0
    rx_packet: int = 0
    tx_packet: int = 0


class MikrotikRoute(BaseModel):
    """Routing table entry."""

    dst_address: str
    gateway: str
    distance: int = 1
    scope: int = 10
    target_scope: int = 10


class MikrotikDhcpLease(BaseModel):
    """DHCP lease."""

    address: str
    mac_address: str
    client_id: str = ""
    hostname: str = ""
    status: str = "bound"
    expires_after: str = ""


class MikrotikFirewallRule(BaseModel):
    """Firewall rule."""

    chain: str
    action: str
    protocol: str = ""
    src_address: str = ""
    dst_address: str = ""
    in_interface: str = ""
    out_interface: str = str


class MikrotikQueue(BaseModel):
    """Simple queue."""

    name: str
    target: str = ""
    max_limit: str = ""
    burst_limit: str = ""
    burst_threshold: str = ""


class MikrotikWirelessClient(BaseModel):
    """Wireless client."""

    mac_address: str
    interface: str
    signal: int = 0
    tx_rate: str = ""
    rx_rate: str = ""
    uptime: str = ""


class MikrotikActionResponse(BaseModel):
    """Response to a MikroTik action."""

    action: str
    target: str
    status: str
    detail: str = ""
