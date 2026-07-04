"""
Script Tools Bridge für den Ninko Orchestrator.

Ermöglicht es dem Orchestrator, als Tool markierte Scripts zu entdecken und auszuführen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool

from core.redis_client import get_redis

logger = logging.getLogger("ninko.agents.script_tools")

REDIS_SCRIPTS_KEY = "ninko:scripting:scripts"
REDIS_TOOL_INVOCATIONS_KEY = "ninko:scripting:tool_invocations"

# Serialisiert Read-Modify-Write auf dem Invocation-Log, damit parallele
# Script-Läufe sich keine Log-Einträge gegenseitig überschreiben (prozessweit).
_invocations_write_lock = asyncio.Lock()


def _normalize_tenant_id(tenant_id: str) -> str:
    return (tenant_id or "default").strip().lower().replace(" ", "_") or "default"


def _tenant_scripts_key(tenant_id: str) -> str:
    return f"{REDIS_SCRIPTS_KEY}:{_normalize_tenant_id(tenant_id)}"


def _tenant_invocations_key(tenant_id: str) -> str:
    return f"{REDIS_TOOL_INVOCATIONS_KEY}:{_normalize_tenant_id(tenant_id)}"


async def _load_scripts(tenant_id: str) -> list[dict]:
    redis = get_redis()
    scoped_key = _tenant_scripts_key(tenant_id)
    raw = await redis.connection.get(scoped_key)
    if raw:
        return json.loads(raw)

    # Backward compatibility: ältere Daten lagen im globalen Key ohne Tenant-Suffix.
    if _normalize_tenant_id(tenant_id) == "default":
        legacy_raw = await redis.connection.get(REDIS_SCRIPTS_KEY)
        if legacy_raw:
            scripts = json.loads(legacy_raw)
            await redis.connection.set(scoped_key, json.dumps(scripts))
            logger.info(
                "Legacy scripts nach tenant-scoped key migriert (script_tools): tenant=%s count=%d",
                tenant_id or "default",
                len(scripts),
            )
            return scripts
    return []


async def _save_invocations(tenant_id: str, invocations: list[dict]) -> None:
    redis = get_redis()
    scoped_key = _tenant_invocations_key(tenant_id)
    await redis.connection.set(scoped_key, json.dumps(invocations))


async def get_available_script_tools(tenant_id: str) -> list[dict]:
    """Gibt alle als Tool verfügbaren Scripts für einen Tenant zurück."""
    scripts = await _load_scripts(tenant_id)
    tools = [
        {
            "name": s["tool_name"],
            "description": s.get("tool_description") or s["name"],
            "script_id": s["id"],
            "script_name": s["name"],
            "input_schema": s.get("tool_input_schema"),
        }
        for s in scripts
        if s.get("tool_enabled") and s.get("tool_name")
    ]
    return tools


async def get_script_tool_by_name(tenant_id: str, tool_name: str) -> dict | None:
    """Findet ein Script-Tool anhand seines Namens."""
    scripts = await _load_scripts(tenant_id)
    script = next(
        (s for s in scripts if s.get("tool_enabled") and s.get("tool_name") == tool_name),
        None,
    )
    if not script:
        return None
    return {
        "name": script["tool_name"],
        "description": script.get("tool_description") or script["name"],
        "script_id": script["id"],
        "script_name": script["name"],
        "code": script["code"],
        "language": script.get("language", "python"),
        "timeout": script.get("timeout", 30),
        "input_schema": script.get("tool_input_schema"),
    }


async def execute_script_tool(
    tenant_id: str,
    tool_name: str,
    input_data: dict | None = None,
    invoked_by: str = "orchestrator",
) -> dict:
    """Führt ein Script-Tool aus und loggt den Aufruf."""
    tool_def = await get_script_tool_by_name(tenant_id, tool_name)
    if not tool_def:
        return {
            "status": "error",
            "error": f"Tool '{tool_name}' nicht gefunden",
            "stdout": "",
            "stderr": f"Tool '{tool_name}' ist nicht aktiviert oder existiert nicht",
        }

    script_id = tool_def["script_id"]
    now = datetime.now(timezone.utc)
    exec_id = str(uuid.uuid4())

    invocation = {
        "id": exec_id,
        "script_id": script_id,
        "script_name": tool_def["script_name"],
        "tool_name": tool_name,
        "tenant_id": tenant_id,
        "input_data": input_data or {},
        "started_at": now.isoformat(),
        "finished_at": None,
        "status": "running",
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "duration_ms": 0.0,
        "invoked_by": invoked_by,
        "invocation_source": "orchestrator",
    }

    try:
        code_with_input = tool_def["code"]
        if input_data:
            input_json = json.dumps(input_data, ensure_ascii=False)
            code_with_input = (
                f"import json\n"
                f"_ninko_tool_input = json.loads({repr(input_json)})\n"
                f"\n{code_with_input}"
            )

        from modules.codelab.tools import execute_code

        result = await execute_code.coroutine(
            code=code_with_input,
            language=tool_def["language"],
            timeout=min(tool_def["timeout"], 300),
        )

        finished_at = datetime.now(timezone.utc)
        duration_ms = result.get("duration_ms", 0.0)
        exit_code = result.get("exit_code", 0)
        status = "succeeded" if exit_code == 0 else "failed"

        invocation["finished_at"] = finished_at.isoformat()
        invocation["status"] = status
        invocation["stdout"] = result.get("stdout", "")[:10000]
        invocation["stderr"] = result.get("stderr", "")[:5000]
        invocation["exit_code"] = exit_code
        invocation["duration_ms"] = duration_ms

        return {
            "status": status,
            "stdout": invocation["stdout"],
            "stderr": invocation["stderr"],
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "tool_name": tool_name,
        }

    except asyncio.TimeoutError:
        finished_at = datetime.now(timezone.utc)
        invocation["finished_at"] = finished_at.isoformat()
        invocation["status"] = "timeout"
        invocation["stderr"] = "Execution timeout"
        invocation["exit_code"] = -1

        return {
            "status": "timeout",
            "error": "Execution timeout",
            "stdout": "",
            "stderr": "Script execution timed out",
            "exit_code": -1,
            "tool_name": tool_name,
        }

    except Exception as e:
        logger.exception("Script tool execution failed")
        finished_at = datetime.now(timezone.utc)
        invocation["finished_at"] = finished_at.isoformat()
        invocation["status"] = "failed"
        invocation["stderr"] = str(e)[:5000]
        invocation["exit_code"] = -1

        return {
            "status": "error",
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "tool_name": tool_name,
        }

    finally:
        async with _invocations_write_lock:
            invocations = await _load_invocations(tenant_id)
            invocations.insert(0, invocation)
            invocations = invocations[:100]
            await _save_invocations(tenant_id, invocations)


async def _load_invocations(tenant_id: str) -> list[dict]:
    redis = get_redis()
    scoped_key = _tenant_invocations_key(tenant_id)
    raw = await redis.connection.get(scoped_key)
    if raw:
        return json.loads(raw)
    return []


@tool
async def run_script_tool(tool_name: str, input_data: dict | None = None) -> str:
    """Führt ein als Tool registriertes Script aus.

    Args:
        tool_name: Der eindeutige Name des Tools (z.B. "backup-database", "check-disk-space")
        input_data: Optionale Eingabedaten als Dictionary, passend zum Tool-Schema

    Returns:
        Die Ausgabe des Scripts (stdout) oder eine Fehlermeldung
    """
    from core.auth import get_current_tenant_id

    tenant_id = get_current_tenant_id() or "default"

    result = await execute_script_tool(tenant_id, tool_name, input_data)

    if result["status"] == "succeeded":
        return result["stdout"] or "Script executed successfully (no output)"
    else:
        error_msg = result.get("stderr") or result.get("error") or "Unknown error"
        return f"Error executing tool '{tool_name}': {error_msg}"


@tool
async def list_script_tools() -> str:
    """Listet alle verfügbaren Script-Tools auf.

    Returns:
        Eine Liste der verfügbaren Tools mit Name und Beschreibung
    """
    from core.auth import get_current_tenant_id

    tenant_id = get_current_tenant_id() or "default"

    tools = await get_available_script_tools(tenant_id)

    if not tools:
        return "Keine Script-Tools verfügbar."

    lines = ["Verfügbare Script-Tools:"]
    for script_tool in tools:
        desc = script_tool.get("description", "")
        lines.append(f"- {script_tool['name']}: {desc}")

    return "\n".join(lines)


class ScriptToolRegistry:
    """Registry für Script-Tools mit Caching."""

    def __init__(self):
        self._cache: dict[str, list[dict]] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_ttl = 30.0

    async def get_tools(self, tenant_id: str) -> list[dict]:
        now = asyncio.get_event_loop().time()

        if tenant_id in self._cache:
            timestamp = self._cache_timestamps.get(tenant_id, 0)
            if now - timestamp < self._cache_ttl:
                return self._cache[tenant_id]

        tools = await get_available_script_tools(tenant_id)
        self._cache[tenant_id] = tools
        self._cache_timestamps[tenant_id] = now
        return tools

    def invalidate(self, tenant_id: str | None = None):
        if tenant_id is None:
            self._cache.clear()
            self._cache_timestamps.clear()
        else:
            self._cache.pop(tenant_id, None)
            self._cache_timestamps.pop(tenant_id, None)


script_tool_registry = ScriptToolRegistry()


async def get_cached_script_tools(tenant_id: str) -> list[dict]:
    """Gibt gecachte Script-Tools zurück."""
    return await script_tool_registry.get_tools(tenant_id)


def invalidate_script_tool_cache(tenant_id: str | None = None):
    """Invalidiert den Script-Tool-Cache."""
    script_tool_registry.invalidate(tenant_id)
