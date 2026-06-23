"""
Proxmox module — FastAPI Router for dashboard API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import (
    _get_node_ip_addresses_raw,
    _get_nodes_raw,
    _get_node_status,
    _get_recent_tasks_raw,
    _get_vm_config_raw,
    _get_vm_ip_addresses_raw,
    _get_vm_status_raw,
    _list_all_vms_raw,
    _list_containers_raw,
    _list_node_ip_addresses_raw,
    _list_vms_raw,
    _list_vm_ip_addresses_raw,
    start_vm as start_vm_tool,
    stop_vm as stop_vm_tool,
    reboot_vm as reboot_vm_tool,
)

logger = logging.getLogger("ninko.modules.proxmox.routes")
router = APIRouter()


@router.get("/nodes")
async def nodes(connection_id: str = "") -> object:
    """All Proxmox nodes."""
    return await _get_nodes_raw(connection_id)


@router.get("/nodes/{node}")
async def node_status(node: str, connection_id: str = "") -> object:
    """Status of a single node."""
    return await _get_node_status(node, connection_id)


@router.get("/nodes/{node}/ips")
async def node_ip_addresses(node: str, connection_id: str = "") -> object:
    """IP addresses of a single Proxmox node."""
    return await _get_node_ip_addresses_raw(node, connection_id)


@router.get("/node-ips")
async def all_node_ip_addresses(connection_id: str = "") -> object:
    """IP addresses of all Proxmox nodes."""
    return await _list_node_ip_addresses_raw(connection_id)


@router.get("/vms")
async def all_vms(connection_id: str = "") -> object:
    """All VMs across all nodes."""
    return await _list_all_vms_raw(connection_id)


@router.get("/vms/{node}")
async def vms_on_node(node: str, connection_id: str = "") -> object:
    """VMs on a specific node."""
    return await _list_vms_raw(node, connection_id)


@router.get("/vm/{node}/{vmid}")
async def vm_status(node: str, vmid: int, connection_id: str = "") -> object:
    """Status of a single VM."""
    return await _get_vm_status_raw(node, vmid, connection_id)


@router.get("/vm/{node}/{vmid}/ips")
async def vm_ip_addresses(node: str, vmid: int, connection_id: str = "") -> object:
    """IP addresses of a single VM or LXC container."""
    return await _get_vm_ip_addresses_raw(node, vmid, connection_id)


@router.get("/vm-ips")
async def all_vm_ip_addresses(connection_id: str = "") -> object:
    """IP addresses of all Proxmox VMs and LXC containers."""
    return await _list_vm_ip_addresses_raw(connection_id)


@router.post("/vm/{node}/{vmid}/start")
async def start_vm_api(node: str, vmid: int, connection_id: str = "") -> object:
    """Start a VM."""
    return await start_vm_tool.ainvoke(
        {"node": node, "vmid": vmid, "connection_id": connection_id}
    )


@router.post("/vm/{node}/{vmid}/stop")
async def stop_vm_api(node: str, vmid: int, connection_id: str = "") -> object:
    """Stop a VM."""
    return await stop_vm_tool.ainvoke(
        {"node": node, "vmid": vmid, "connection_id": connection_id}
    )


@router.post("/vm/{node}/{vmid}/reboot")
async def reboot_vm_api(node: str, vmid: int, connection_id: str = "") -> object:
    """Restart a VM."""
    return await reboot_vm_tool.ainvoke(
        {"node": node, "vmid": vmid, "connection_id": connection_id}
    )


@router.get("/containers/{node}")
async def containers_on_node(node: str, connection_id: str = "") -> object:
    """LXC containers on a node."""
    return await _list_containers_raw(node, connection_id)


@router.get("/nodes/{node}/tasks")
async def node_tasks(node: str, connection_id: str = "") -> object:
    """Recent tasks on a Proxmox node."""
    return await _get_recent_tasks_raw(node, connection_id)


@router.get("/vm/{node}/{vmid}/config")
async def vm_config(node: str, vmid: int, connection_id: str = "") -> object:
    """Configuration of a VM or LXC container."""
    return await _get_vm_config_raw(node, vmid, connection_id)
