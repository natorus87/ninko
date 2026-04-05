"""Pydantic schemas for the MCP Server module."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TransportType = Literal["stdio", "http", "sse"]


class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict)
    connection_id: str = Field("", description="Optional connection ID")


class MCPResourceReadRequest(BaseModel):
    uri: str
    connection_id: str = ""


class MCPServerConnectionConfig(BaseModel):
    transport: TransportType = "stdio"
    command: str = ""
    args_json: str = "[]"
    cwd: str = ""
    env_json: str = "{}"
    url: str = ""
    message_url: str = ""
    headers_json: str = "{}"
    protocol_version: str = "2025-03-26"
    timeout_seconds: float = 20.0


class MCPValidateRequest(BaseModel):
    connection_id: str = ""
