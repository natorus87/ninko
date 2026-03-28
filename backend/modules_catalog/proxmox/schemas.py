"""
Proxmox Modul – Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class NodeInfo(BaseModel):
    """Proxmox Node-Status."""

    node: str
    status: str  # "online", "offline"
    cpu_usage: float = 0.0  # Prozent
    mem_total: int = 0  # Bytes
    mem_used: int = 0  # Bytes
    mem_usage: float = 0.0  # Prozent
    uptime: int = 0  # Sekunden


class VmInfo(BaseModel):
    """VM-Informationen."""

    vmid: int
    name: str
    node: str
    status: str  # "running", "stopped", "paused"
    type: str = "qemu"  # "qemu" | "lxc"
    cpu_usage: float = 0.0
    mem_total: int = 0
    mem_used: int = 0
    disk_total: int = 0
    disk_used: int = 0
    uptime: int = 0


class TaskInfo(BaseModel):
    """Proxmox Task-Information."""

    upid: str
    type: str
    status: str
    node: str
    user: str = ""
    starttime: int = 0
    endtime: int = 0


class ProxmoxActionResponse(BaseModel):
    """Antwort auf eine Proxmox-Aktion."""

    action: str
    target: str  # z.B. "VM 100"
    node: str
    status: str  # "success" | "error" | "confirmation_required"
    detail: str = ""
