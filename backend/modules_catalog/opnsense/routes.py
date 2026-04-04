"""OPNsense module — FastAPI router for dashboard API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .tools import (
    get_opnsense_system_status,
    get_opnsense_interfaces,
    get_opnsense_services,
    create_opnsense_firewall_rule,
    delete_opnsense_firewall_rule,
    create_opnsense_nat_rule,
    delete_opnsense_nat_rule,
)

logger = logging.getLogger("ninko.modules.opnsense.routes")
router = APIRouter()


class ApiResponse(BaseModel):
    status: str
    data: Any = None
    detail: str = ""


@router.get("/status", response_model=ApiResponse)
async def get_status(connection_id: str = "") -> ApiResponse:
    """REST endpoint for the UI frontend — system status."""
    try:
        result = await get_opnsense_system_status.ainvoke({"connection_id": connection_id})
        return ApiResponse(status="ok", data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))


@router.get("/interfaces", response_model=ApiResponse)
async def get_interfaces(connection_id: str = "") -> ApiResponse:
    """REST endpoint for interfaces."""
    try:
        result = await get_opnsense_interfaces.ainvoke({"connection_id": connection_id})
        return ApiResponse(status="ok", data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))


@router.get("/services", response_model=ApiResponse)
async def get_services(connection_id: str = "") -> ApiResponse:
    """REST endpoint for services."""
    try:
        result = await get_opnsense_services.ainvoke({"connection_id": connection_id})
        return ApiResponse(status="ok", data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))


@router.post("/firewall/rules", response_model=ApiResponse)
async def create_firewall_rule(
    interface: str,
    action: str,
    protocol: str,
    source: str,
    destination: str,
    description: str = "",
    connection_id: str = ""
) -> ApiResponse:
    """REST endpoint to create a firewall rule."""
    try:
        result = await create_opnsense_firewall_rule.ainvoke({
            "interface": interface,
            "action": action,
            "protocol": protocol,
            "source": source,
            "destination": destination,
            "description": description,
            "connection_id": connection_id
        })
        return ApiResponse(status="ok", data={"message": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))


@router.delete("/firewall/rules/{rule_uuid}", response_model=ApiResponse)
async def delete_firewall_rule(rule_uuid: str, connection_id: str = "") -> ApiResponse:
    """REST endpoint to delete a firewall rule."""
    try:
        result = await delete_opnsense_firewall_rule.ainvoke({
            "rule_uuid": rule_uuid,
            "connection_id": connection_id
        })
        return ApiResponse(status="ok", data={"message": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))


@router.post("/nat/rules", response_model=ApiResponse)
async def create_nat_rule(
    interface: str,
    protocol: str,
    source: str,
    destination: str,
    target: str,
    target_port: str,
    description: str = "",
    connection_id: str = ""
) -> ApiResponse:
    """REST endpoint to create a NAT rule."""
    try:
        result = await create_opnsense_nat_rule.ainvoke({
            "interface": interface,
            "protocol": protocol,
            "source": source,
            "destination": destination,
            "target": target,
            "target_port": target_port,
            "description": description,
            "connection_id": connection_id
        })
        return ApiResponse(status="ok", data={"message": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))


@router.delete("/nat/rules/{rule_uuid}", response_model=ApiResponse)
async def delete_nat_rule(rule_uuid: str, connection_id: str = "") -> ApiResponse:
    """REST endpoint to delete a NAT rule."""
    try:
        result = await delete_opnsense_nat_rule.ainvoke({
            "rule_uuid": rule_uuid,
            "connection_id": connection_id
        })
        return ApiResponse(status="ok", data={"message": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", detail=str(e))
