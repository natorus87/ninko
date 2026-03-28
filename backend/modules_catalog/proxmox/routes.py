"""
Proxmox Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import (
    get_nodes,
    get_node_status,
    list_all_vms,
    list_vms,
    get_vm_status,
    start_vm as start_vm_tool,
    stop_vm as stop_vm_tool,
    reboot_vm as reboot_vm_tool,
    list_containers,
)

logger = logging.getLogger("ninko.modules.proxmox.routes")
router = APIRouter()


@router.get("/nodes")
async def nodes():
    """Alle Proxmox-Nodes."""
    return await get_nodes.ainvoke({})


@router.get("/nodes/{node}")
async def node_status(node: str):
    """Status eines einzelnen Nodes."""
    return await get_node_status.ainvoke({"node": node})


@router.get("/vms")
async def all_vms():
    """Alle VMs auf allen Nodes."""
    return await list_all_vms.ainvoke({})


@router.get("/vms/{node}")
async def vms_on_node(node: str):
    """VMs auf einem bestimmten Node."""
    return await list_vms.ainvoke({"node": node})


@router.get("/vm/{node}/{vmid}")
async def vm_status(node: str, vmid: int):
    """Status einer einzelnen VM."""
    return await get_vm_status.ainvoke({"node": node, "vmid": vmid})


@router.post("/vm/{node}/{vmid}/start")
async def start_vm_api(node: str, vmid: int):
    """VM starten."""
    return await start_vm_tool.ainvoke({"node": node, "vmid": vmid})


@router.post("/vm/{node}/{vmid}/stop")
async def stop_vm_api(node: str, vmid: int):
    """VM stoppen."""
    return await stop_vm_tool.ainvoke({"node": node, "vmid": vmid})


@router.post("/vm/{node}/{vmid}/reboot")
async def reboot_vm_api(node: str, vmid: int):
    """VM neu starten."""
    return await reboot_vm_tool.ainvoke({"node": node, "vmid": vmid})


@router.get("/containers/{node}")
async def containers_on_node(node: str):
    """LXC-Container auf einem Node."""
    return await list_containers.ainvoke({"node": node})
