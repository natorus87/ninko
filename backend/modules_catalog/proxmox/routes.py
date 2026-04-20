"""
Proxmox module — FastAPI Router for dashboard API.
"""

from __future__ import annotations

import ast
import json
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


def _normalize_tool_output(value: object) -> object:
    if isinstance(value, str):
        text = value.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return value
    return value


@router.get("/nodes")
async def nodes(connection_id: str = "") -> object:
    """All Proxmox nodes."""
    result = await get_nodes.ainvoke({"connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/nodes/{node}")
async def node_status(node: str, connection_id: str = "") -> object:
    """Status of a single node."""
    result = await get_node_status.ainvoke(
        {"node": node, "connection_id": connection_id}
    )
    return _normalize_tool_output(result)


@router.get("/vms")
async def all_vms(connection_id: str = "") -> object:
    """All VMs across all nodes."""
    result = await list_all_vms.ainvoke({"connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/vms/{node}")
async def vms_on_node(node: str, connection_id: str = "") -> object:
    """VMs on a specific node."""
    result = await list_vms.ainvoke({"node": node, "connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/vm/{node}/{vmid}")
async def vm_status(node: str, vmid: int, connection_id: str = "") -> object:
    """Status of a single VM."""
    result = await get_vm_status.ainvoke(
        {"node": node, "vmid": vmid, "connection_id": connection_id}
    )
    return _normalize_tool_output(result)


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
    return await list_containers.ainvoke(
        {"node": node, "connection_id": connection_id}
    )
