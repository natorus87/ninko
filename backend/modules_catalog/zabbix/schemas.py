"""Zabbix module schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class ZabbixConnection(BaseModel):
    name: str
    url: str
    user: str
    password: str


class ZabbixHost(BaseModel):
    hostid: str
    name: str
    status: str
    lastsync: Optional[str] = None


class ZabbixItem(BaseModel):
    itemid: str
    name: str
    key_: str = Field(alias="key")
    lastvalue: Optional[str] = None
    lastclock: Optional[str] = None
    state: Optional[str] = None


class ZabbixTrigger(BaseModel):
    triggerid: str
    description: str
    status: str
    priority: int
    lastchange: Optional[str] = None


class ZabbixProblem(BaseModel):
    eventid: str
    name: str
    severity: int
    host: str
    clock: str


class ZabbixGraph(BaseModel):
    graphid: str
    name: str
    width: int
    height: int


class ZabbixAction(BaseModel):
    actionid: str
    name: str
    status: str
    esc_period: str


class ZabbixHistory(BaseModel):
    clock: str
    value: str
    itemid: str
