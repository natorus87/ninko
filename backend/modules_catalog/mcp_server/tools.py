"""MCP Server module tools."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.mcp_registry import (
    DEFAULT_PROTOCOL_VERSION,
    McpClientError,
    McpConnectionConfig,
    get_mcp_registry,
)
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.mcp_server.tools")


def _parse_json_config(raw: str, fallback: Any) -> Any:
    text = (raw or "").strip()
    if not text:
        return fallback
    parsed = json.loads(text)
    if isinstance(fallback, list) and not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    if isinstance(fallback, dict) and not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


async def _load_config(connection_id: str = "") -> McpConnectionConfig:
    if connection_id:
        conn = await ConnectionManager.get_connection("mcp_server", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"MCP-Server-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"MCP Server connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("mcp_server")

    if conn:
        vault = get_vault()
        token_path = conn.vault_keys.get("MCP_AUTH_TOKEN")
        auth_token = await vault.get_secret(token_path) if token_path else ""
        return McpConnectionConfig(
            transport=conn.config.get("transport", "stdio"),
            command=conn.config.get("command", ""),
            args=_parse_json_config(conn.config.get("args_json", "[]"), []),
            cwd=conn.config.get("cwd", ""),
            env=_parse_json_config(conn.config.get("env_json", "{}"), {}),
            url=conn.config.get("url", ""),
            message_url=conn.config.get("message_url", ""),
            headers=_parse_json_config(conn.config.get("headers_json", "{}"), {}),
            protocol_version=conn.config.get(
                "protocol_version", DEFAULT_PROTOCOL_VERSION
            ),
            timeout_seconds=float(conn.config.get("timeout_seconds", "20") or 20),
            auth_token=auth_token or conn.config.get("auth_token", ""),
        )

    return McpConnectionConfig(
        transport=os.environ.get("MCP_SERVER_TRANSPORT", "stdio"),
        command=os.environ.get("MCP_SERVER_COMMAND", ""),
        args=_parse_json_config(os.environ.get("MCP_SERVER_ARGS_JSON", "[]"), []),
        cwd=os.environ.get("MCP_SERVER_CWD", ""),
        env=_parse_json_config(os.environ.get("MCP_SERVER_ENV_JSON", "{}"), {}),
        url=os.environ.get("MCP_SERVER_URL", ""),
        message_url=os.environ.get("MCP_SERVER_MESSAGE_URL", ""),
        headers=_parse_json_config(os.environ.get("MCP_SERVER_HEADERS_JSON", "{}"), {}),
        protocol_version=os.environ.get(
            "MCP_SERVER_PROTOCOL_VERSION", DEFAULT_PROTOCOL_VERSION
        ),
        timeout_seconds=float(os.environ.get("MCP_SERVER_TIMEOUT_SECONDS", "20") or 20),
        auth_token=os.environ.get("MCP_AUTH_TOKEN", ""),
    )


def _format_mcp_error(exc: Exception) -> dict:
    return {
        "status": "error",
        "detail": str(exc),
    }


def _validate_config_shape(config: McpConnectionConfig) -> list[str]:
    issues: list[str] = []
    if config.transport == "stdio":
        if not config.command.strip():
            issues.append(
                _t(
                    de="stdio-Transport erfordert 'command'.",
                    en="stdio transport requires 'command'.",
                )
            )
    elif config.transport in {"http", "sse"}:
        if not config.url.strip():
            issues.append(
                _t(
                    de=f"{config.transport}-Transport erfordert 'url'.",
                    en=f"{config.transport} transport requires 'url'.",
                )
            )
    else:
        issues.append(
            _t(
                de=f"Transport '{config.transport}' wird nicht unterstützt.",
                en=f"Unsupported transport '{config.transport}'.",
            )
        )

    if config.timeout_seconds <= 0:
        issues.append(
            _t(
                de="timeout_seconds muss größer als 0 sein.",
                en="timeout_seconds must be greater than 0.",
            )
        )

    if (
        config.transport == "sse"
        and config.message_url
        and not config.message_url.startswith(("http://", "https://"))
    ):
        issues.append(
            _t(
                de="sse 'message_url' muss eine absolute http(s) URL sein.",
                en="sse 'message_url' must be an absolute http(s) URL when set.",
            )
        )

    return issues


@tool("validate_mcp_server_connection")
async def validate_mcp_server_connection(connection_id: str = "") -> dict:
    """
    Validate the configured MCP connection shape and then attempt a real
    initialize handshake against the server.
    """
    try:
        config = await _load_config(connection_id)
        issues = _validate_config_shape(config)
        if issues:
            return {
                "status": "error",
                "detail": _t(
                    de="Ungültige MCP-Verbindungskonfiguration.",
                    en="Invalid MCP connection configuration.",
                ),
                "issues": issues,
            }
        registry = get_mcp_registry()
        status = await registry.get_server_status(config)
        return {
            "status": "ok",
            "validation": "passed",
            "transport": config.transport,
            "server": status,
        }
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        McpClientError,
        httpx.HTTPError,
    ) as exc:
        logger.error("validate_mcp_server_connection failed: %s", exc)
        return _format_mcp_error(exc)


@tool("get_mcp_server_status")
async def get_mcp_server_status(connection_id: str = "") -> dict:
    """
    Connect to the configured MCP server and return initialization data,
    capabilities and server metadata.
    """
    try:
        config = await _load_config(connection_id)
        issues = _validate_config_shape(config)
        if issues:
            return {
                "status": "error",
                "detail": _t(
                    de="Ungültige MCP-Verbindungskonfiguration.",
                    en="Invalid MCP connection configuration.",
                ),
                "issues": issues,
            }
        registry = get_mcp_registry()
        result = await registry.get_server_status(config)
        result["note"] = _t(
            de=f"Verbunden über {config.transport} MCP-Transport.",
            en=f"Connected via {config.transport} MCP transport.",
        )
        return result
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        McpClientError,
        httpx.HTTPError,
    ) as exc:
        logger.error("get_mcp_server_status failed: %s", exc)
        return _format_mcp_error(exc)


@tool("list_mcp_server_tools")
async def list_mcp_server_tools(connection_id: str = "") -> list[dict] | dict:
    """
    List all tools exposed by the configured MCP server.
    """
    try:
        config = await _load_config(connection_id)
        issues = _validate_config_shape(config)
        if issues:
            return {
                "status": "error",
                "detail": _t(
                    de="Ungültige MCP-Verbindungskonfiguration.",
                    en="Invalid MCP connection configuration.",
                ),
                "issues": issues,
            }
        registry = get_mcp_registry()
        return await registry.list_tools(config)
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        McpClientError,
        httpx.HTTPError,
    ) as exc:
        logger.error("list_mcp_server_tools failed: %s", exc)
        return _format_mcp_error(exc)


@tool("list_mcp_server_resources")
async def list_mcp_server_resources(connection_id: str = "") -> list[dict] | dict:
    """
    List all resources exposed by the configured MCP server.
    """
    try:
        config = await _load_config(connection_id)
        issues = _validate_config_shape(config)
        if issues:
            return {
                "status": "error",
                "detail": "Invalid MCP connection configuration.",
                "issues": issues,
            }
        registry = get_mcp_registry()
        return await registry.list_resources(config)
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        McpClientError,
        httpx.HTTPError,
    ) as exc:
        logger.error("list_mcp_server_resources failed: %s", exc)
        return _format_mcp_error(exc)


@tool("read_mcp_server_resource")
async def read_mcp_server_resource(uri: str, connection_id: str = "") -> dict:
    """
    Read a resource from the configured MCP server by URI.
    """
    try:
        config = await _load_config(connection_id)
        issues = _validate_config_shape(config)
        if issues:
            return {
                "status": "error",
                "detail": _t(
                    de="Ungültige MCP-Verbindungskonfiguration.",
                    en="Invalid MCP connection configuration.",
                ),
                "issues": issues,
            }
        registry = get_mcp_registry()
        return await registry.read_resource(config, uri)
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        McpClientError,
        httpx.HTTPError,
    ) as exc:
        logger.error("read_mcp_server_resource failed: %s", exc)
        return _format_mcp_error(exc)


@tool("call_mcp_server_tool")
async def call_mcp_server_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    connection_id: str = "",
) -> dict:
    """
    Call any tool exposed by the configured MCP server.

    Use this tool when the user already knows the MCP tool name or after
    discovering it via list_mcp_server_tools.
    """
    try:
        config = await _load_config(connection_id)
        issues = _validate_config_shape(config)
        if issues:
            return {
                "status": "error",
                "detail": _t(
                    de="Ungültige MCP-Verbindungskonfiguration.",
                    en="Invalid MCP connection configuration.",
                ),
                "issues": issues,
            }
        registry = get_mcp_registry()
        return await registry.call_tool(config, tool_name, arguments or {})
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        McpClientError,
        httpx.HTTPError,
    ) as exc:
        logger.error("call_mcp_server_tool failed: %s", exc)
        return _format_mcp_error(exc)
