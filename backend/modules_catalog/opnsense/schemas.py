"""
OPNsense Modul – Pydantic Schemas für API-Antworten.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class OPNsenseSystemStatus(BaseModel):
    """System-Status der OPNsense."""
    firmware: Optional[str] = None
    version: Optional[str] = None
    uptime: Optional[int] = None
    cpu: Optional[float] = None
    memory: Optional[float] = None
    disk: Optional[float] = None


class OPNsenseInterface(BaseModel):
    """Netzwerk-Interface."""
    name: str
    descr: Optional[str] = None
    ipaddr: Optional[str] = None
    subnet: Optional[int] = None
    macaddr: Optional[str] = None
    status: Optional[str] = None
    media: Optional[str] = None
    speed: Optional[int] = None


class OPNsenseGateway(BaseModel):
    """Gateway-Status."""
    name: str
    ip: str
    status: str
    rtt: Optional[float] = None
    rttdev: Optional[float] = None


class OPNsenseFirewallRule(BaseModel):
    """Firewall-Regel."""
    uuid: str
    sequence: int
    enabled: str
    action: str
    interface: str
    protocol: str
    source: Optional[str] = None
    destination: Optional[str] = None
    target: Optional[str] = None
    log: Optional[str] = None
    descr: Optional[str] = None


class OPNsenseNATRule(BaseModel):
    """NAT-Regel."""
    uuid: str
    sequence: int
    enabled: str
    interface: str
    protocol: str
    source: Optional[str] = None
    destination: Optional[str] = None
    target: Optional[str] = None
    target_port: Optional[str] = None
    descr: Optional[str] = None


class OPNsenseService(BaseModel):
    """Service-Status."""
    name: str
    description: str
    enabled: bool
    status: str


class OPNsenseDHCPLease(BaseModel):
    """DHCP-Lease."""
    ip: str
    mac: str
    hostname: Optional[str] = None
    starts: Optional[str] = None
    ends: Optional[str] = None
    state: Optional[str] = None
