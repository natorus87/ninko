"""FastAPI routes for the MCP Server module."""

from __future__ import annotations

from fastapi import APIRouter

from .schemas import MCPResourceReadRequest, MCPToolCallRequest, MCPValidateRequest
from .tools import (
    call_mcp_server_tool,
    get_mcp_server_status,
    list_mcp_server_resources,
    list_mcp_server_tools,
    read_mcp_server_resource,
    validate_mcp_server_connection,
)

router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    result = await get_mcp_server_status.ainvoke({"connection_id": connection_id})
    return {"status": "ok" if result.get("status") != "error" else "error", "data": result}


@router.post("/validate")
async def post_validate(body: MCPValidateRequest) -> dict:
    result = await validate_mcp_server_connection.ainvoke(
        {"connection_id": body.connection_id}
    )
    return {"status": "ok" if result.get("status") != "error" else "error", "data": result}


@router.get("/tools")
async def get_tools(connection_id: str = "") -> dict:
    result = await list_mcp_server_tools.ainvoke({"connection_id": connection_id})
    ok = not isinstance(result, dict) or result.get("status") != "error"
    return {"status": "ok" if ok else "error", "data": result}


@router.get("/resources")
async def get_resources(connection_id: str = "") -> dict:
    result = await list_mcp_server_resources.ainvoke({"connection_id": connection_id})
    ok = not isinstance(result, dict) or result.get("status") != "error"
    return {"status": "ok" if ok else "error", "data": result}


@router.post("/resource")
async def post_resource(body: MCPResourceReadRequest) -> dict:
    result = await read_mcp_server_resource.ainvoke(
        {"uri": body.uri, "connection_id": body.connection_id}
    )
    return {"status": "ok" if result.get("status") != "error" else "error", "data": result}


@router.post("/tool-call")
async def post_tool_call(body: MCPToolCallRequest) -> dict:
    result = await call_mcp_server_tool.ainvoke(
        {
            "tool_name": body.tool_name,
            "arguments": body.arguments,
            "connection_id": body.connection_id,
        }
    )
    return {"status": "ok" if result.get("status") != "error" else "error", "data": result}
