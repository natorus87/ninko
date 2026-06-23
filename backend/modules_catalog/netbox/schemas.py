"""Netbox module schemas."""

from typing import Optional
from pydantic import BaseModel


class NetboxConnection(BaseModel):
    name: str
    url: str
    token: str


class NetboxDevice(BaseModel):
    id: int
    name: str
    display: str
    status: str
    site: Optional[str] = None
    role: Optional[str] = None
    platform: Optional[str] = None


class NetboxSite(BaseModel):
    id: int
    name: str
    slug: str
    status: str


class NetboxRack(BaseModel):
    id: int
    name: str
    site: str
    status: str
    u_height: int


class NetboxVlan(BaseModel):
    id: int
    vid: int
    name: str
    site: Optional[str] = None
    group: Optional[str] = None
    status: str


class NetboxIPAddress(BaseModel):
    id: int
    address: str
    family: int
    status: str
    device: Optional[str] = None
    interface: Optional[str] = None


class NetboxPrefix(BaseModel):
    id: int
    prefix: str
    family: int
    site: Optional[str] = None
    vlan: Optional[str] = None
    status: str


class NetboxCircuit(BaseModel):
    id: int
    cid: str
    provider: str
    type: str
    status: str


class NetboxCable(BaseModel):
    id: int
    status: str
    a_side: Optional[str] = None
    b_side: Optional[str] = None


class NetboxCluster(BaseModel):
    id: int
    name: str
    type: str
    site: Optional[str] = None
