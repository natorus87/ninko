"""
Minimal MCP client registry for generic MCP servers.

The initial implementation supports stdio transport and the MCP calls needed
for the first marketplace module slice: initialize, tools/list, tools/call,
resources/list and resources/read.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("ninko.core.mcp_registry")

DEFAULT_PROTOCOL_VERSION = "2025-03-26"

# CWE-78 Mitigation: Whitelist for MCP command validation
_MCP_ALLOWED_COMMAND_RE = re.compile(r"^/?[a-zA-Z0-9_][a-zA-Z0-9_./-]*$")
_MCP_ALLOWED_ARG_RE = re.compile(r"^[a-zA-Z0-9_./:=@+\- ]*$")


def _validate_mcp_command(command: str) -> str:
  """Validates MCP executable against whitelist pattern (CWE-78)."""
  cmd = command.strip()
  if not cmd or not _MCP_ALLOWED_COMMAND_RE.match(cmd):
    raise ValueError(
        f"Invalid MCP command: '{cmd}'. "
        "Only alphanumeric characters, '_', '.', '/', '-' allowed."
    )
  return cmd


def _validate_mcp_args(args: list[str]) -> None:
  """Validates MCP arguments against whitelist pattern (CWE-78)."""
  for arg in args:
    if not _MCP_ALLOWED_ARG_RE.match(str(arg)):
      raise ValueError(f"Invalid MCP argument: '{arg}'")


@dataclass(slots=True)
class McpConnectionConfig:
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    message_url: str = ""
    protocol_version: str = DEFAULT_PROTOCOL_VERSION
    timeout_seconds: float = 20.0
    auth_token: str = ""


class McpClientError(RuntimeError):
    """Raised when MCP communication fails."""


class McpRegistry:
    """Factory-style registry for MCP server operations."""

    async def get_server_status(self, config: McpConnectionConfig) -> dict:
        init = await self.initialize(config)
        return {
            "transport": config.transport,
            "protocol_version": init.get("protocolVersion", config.protocol_version),
            "server_info": init.get("serverInfo", {}),
            "capabilities": init.get("capabilities", {}),
            "status": "connected",
        }

    async def list_tools(self, config: McpConnectionConfig) -> list[dict]:
        result = await self._call(config, "tools/list", {})
        return result.get("tools", [])

    async def list_resources(self, config: McpConnectionConfig) -> list[dict]:
        result = await self._call(config, "resources/list", {})
        return result.get("resources", [])

    async def read_resource(self, config: McpConnectionConfig, uri: str) -> dict:
        return await self._call(config, "resources/read", {"uri": uri})

    async def call_tool(
        self, config: McpConnectionConfig, tool_name: str, arguments: dict[str, Any]
    ) -> dict:
        return await self._call(
            config,
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )

    async def initialize(self, config: McpConnectionConfig) -> dict:
        return await self._call(config, "initialize", None, initialize_only=True)

    async def _call(
        self,
        config: McpConnectionConfig,
        method: str,
        params: dict[str, Any] | None,
        *,
        initialize_only: bool = False,
    ) -> dict:
        if config.transport != "stdio":
            if config.transport == "http":
                return await self._call_http(
                    config, method, params or {}, initialize_only
                )
            if config.transport == "sse":
                return await self._call_sse(
                    config, method, params or {}, initialize_only
                )
            raise McpClientError(f"Unsupported MCP transport '{config.transport}'.")

        return await self._call_stdio(config, method, params or {}, initialize_only)

    async def _call_http(
        self,
        config: McpConnectionConfig,
        method: str,
        params: dict[str, Any],
        initialize_only: bool,
    ) -> dict:
        if not config.url.strip():
            raise McpClientError("No MCP server URL configured for HTTP transport.")

        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            headers = self._build_http_headers(config)
            initialize_result = await self._post_jsonrpc(
                client,
                config.url,
                headers,
                "initialize",
                {
                    "protocolVersion": config.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "ninko-mcp-server", "version": "0.2.0"},
                },
                request_id=1,
            )
            await self._post_notification(
                client, config.url, headers, "notifications/initialized", {}
            )
            if initialize_only:
                return initialize_result
            return await self._post_jsonrpc(
                client,
                config.url,
                headers,
                method,
                params,
                request_id=2,
            )

    async def _call_sse(
        self,
        config: McpConnectionConfig,
        method: str,
        params: dict[str, Any],
        initialize_only: bool,
    ) -> dict:
        if not config.url.strip():
            raise McpClientError("No MCP SSE URL configured.")

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        endpoint_queue: asyncio.Queue[str] = asyncio.Queue()

        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            headers = self._build_http_headers(config)
            headers["Accept"] = "text/event-stream"
            async with client.stream("GET", config.url, headers=headers) as response:
                response.raise_for_status()
                session_id = response.headers.get("mcp-session-id", "")
                reader = asyncio.create_task(
                    self._read_sse_stream(response, queue, endpoint_queue)
                )
                try:
                    post_url = config.message_url.strip()
                    if not post_url:
                        with contextlib.suppress(asyncio.TimeoutError):
                            post_url = await asyncio.wait_for(
                                endpoint_queue.get(),
                                timeout=min(3.0, config.timeout_seconds),
                            )
                    if not post_url:
                        post_url = config.url

                    post_headers = self._build_http_headers(config)
                    if session_id:
                        post_headers["mcp-session-id"] = session_id

                    await self._post_jsonrpc(
                        client,
                        post_url,
                        post_headers,
                        "initialize",
                        {
                            "protocolVersion": config.protocol_version,
                            "capabilities": {},
                            "clientInfo": {
                                "name": "ninko-mcp-server",
                                "version": "0.2.0",
                            },
                        },
                        request_id=1,
                    )
                    initialize_result = await self._await_queue_result(
                        queue,
                        request_id=1,
                        timeout=config.timeout_seconds,
                        method="initialize",
                    )
                    await self._post_notification(
                        client,
                        post_url,
                        post_headers,
                        "notifications/initialized",
                        {},
                    )
                    if initialize_only:
                        return initialize_result

                    await self._post_jsonrpc(
                        client,
                        post_url,
                        post_headers,
                        method,
                        params,
                        request_id=2,
                    )
                    return await self._await_queue_result(
                        queue,
                        request_id=2,
                        timeout=config.timeout_seconds,
                        method=method,
                    )
                finally:
                    reader.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await reader

    async def _call_stdio(
        self,
        config: McpConnectionConfig,
        method: str,
        params: dict[str, Any],
        initialize_only: bool,
    ) -> dict:
        if not config.command.strip():
            raise McpClientError(
                "No MCP server command configured for stdio transport."
            )

        # CWE-78: Validate command and arguments against whitelist
        try:
            validated_command = _validate_mcp_command(config.command)
            _validate_mcp_args(config.args)
        except ValueError as exc:
            raise McpClientError(str(exc)) from exc

        env = {**os.environ, **config.env}
        if config.auth_token:
            env.setdefault("MCP_AUTH_TOKEN", config.auth_token)

        process = await asyncio.create_subprocess_exec(
            validated_command,
            *config.args,
            cwd=config.cwd or None,
            env=env or None,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            initialize_result = await asyncio.wait_for(
                self._initialize_stdio(process, config),
                timeout=config.timeout_seconds,
            )
            if initialize_only:
                return initialize_result
            result = await asyncio.wait_for(
                self._send_request(process, method, params, request_id=2),
                timeout=config.timeout_seconds,
            )
            return result
        except asyncio.TimeoutError as exc:
            raise McpClientError(
                f"MCP request '{method}' timed out after {config.timeout_seconds} seconds."
            ) from exc
        finally:
            try:
                # Gracefully terminate process and close all pipes
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                # Ensure all pipes are properly closed using communicate()
                # This prevents stdout/stderr pipe leaks (stdout/stderr are StreamReader)
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=1.0
                    )
                    if stderr:
                        logger.debug(
                            "MCP stderr: %s", stderr.decode("utf-8", errors="replace")
                        )
                except asyncio.TimeoutError:
                    # communicate() timed out - stdin is the only pipe we can close
                    if process.stdin:
                        process.stdin.close()
            except (ProcessLookupError, OSError):
                # Process already gone, ignore
                pass

    async def _initialize_stdio(
        self,
        process: asyncio.subprocess.Process,
        config: McpConnectionConfig,
    ) -> dict:
        params = {
            "protocolVersion": config.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "ninko-mcp-server", "version": "0.1.0"},
        }
        result = await self._send_request(process, "initialize", params, request_id=1)
        await self._send_notification(process, "notifications/initialized", {})
        return result

    async def _send_request(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: dict[str, Any],
        *,
        request_id: int,
    ) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        await self._write_message(process, payload)
        while True:
            message = await self._read_message(process)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise McpClientError(
                    f"MCP error for '{method}': {error.get('message', 'unknown error')}"
                )
            return message.get("result", {})

    async def _post_jsonrpc(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        method: str,
        params: dict[str, Any],
        *,
        request_id: int,
    ) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        if "text/event-stream" in response.headers.get("content-type", ""):
            return {}
        if not response.content:
            return {}
        data = response.json()
        if "error" in data:
            error = data["error"]
            raise McpClientError(
                f"MCP error for '{method}': {error.get('message', 'unknown error')}"
            )
        return data.get("result", {})

    async def _post_notification(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        method: str,
        params: dict[str, Any],
    ) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    def _build_http_headers(self, config: McpConnectionConfig) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(config.headers)
        if config.auth_token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {config.auth_token}"
        return headers

    async def _read_sse_stream(
        self,
        response: httpx.Response,
        queue: asyncio.Queue[dict[str, Any]],
        endpoint_queue: asyncio.Queue[str],
    ) -> None:
        event_name = "message"
        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if line == "":
                await self._flush_sse_event(
                    event_name, data_lines, queue, endpoint_queue
                )
                event_name = "message"
                data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip() or "message"
                continue
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        await self._flush_sse_event(event_name, data_lines, queue, endpoint_queue)

    async def _flush_sse_event(
        self,
        event_name: str,
        data_lines: list[str],
        queue: asyncio.Queue[dict[str, Any]],
        endpoint_queue: asyncio.Queue[str],
    ) -> None:
        if not data_lines:
            return
        raw = "\n".join(data_lines).strip()
        if event_name == "endpoint":
            await endpoint_queue.put(raw)
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        await queue.put(payload)

    async def _await_queue_result(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        *,
        request_id: int,
        timeout: float,
        method: str,
    ) -> dict:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise McpClientError(
                    f"MCP SSE response for '{method}' timed out after {timeout} seconds."
                ) from exc
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                error = payload["error"]
                raise McpClientError(
                    f"MCP error for '{method}': {error.get('message', 'unknown error')}"
                )
            return payload.get("result", {})

    async def _send_notification(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: dict[str, Any],
    ) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._write_message(process, payload)

    async def _write_message(
        self,
        process: asyncio.subprocess.Process,
        payload: dict[str, Any],
    ) -> None:
        if not process.stdin:
            raise McpClientError("MCP stdin is not available.")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        process.stdin.write(header + body)
        await process.stdin.drain()

    async def _read_message(self, process: asyncio.subprocess.Process) -> dict:
        if not process.stdout:
            raise McpClientError("MCP stdout is not available.")

        content_length = 0
        while True:
            line = await process.stdout.readline()
            if not line:
                raise McpClientError("MCP server closed stdout unexpectedly.")
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("utf-8", errors="replace").partition(":")
            if key.lower().strip() == "content-length":
                content_length = int(value.strip())

        if content_length <= 0:
            raise McpClientError("Missing or invalid Content-Length in MCP response.")

        body = await process.stdout.readexactly(content_length)
        return json.loads(body.decode("utf-8", errors="replace"))


_global_mcp_registry: McpRegistry | None = None


def get_mcp_registry() -> McpRegistry:
    global _global_mcp_registry
    if _global_mcp_registry is None:
        _global_mcp_registry = McpRegistry()
    return _global_mcp_registry
