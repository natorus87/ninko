"""
Core tool permission policy for Ninko.

Provides a small, centralized permission layer for high-impact core tools.
The first rollout focuses on CLI command execution so future tools can reuse
the same mode and decision model.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from enum import StrEnum


class PermissionMode(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class PermissionDeniedError(ValueError):
    """Raised when a core tool call violates the active permission policy."""


@dataclass(slots=True, frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str = ""


_MODE_RANK: dict[PermissionMode, int] = {
    PermissionMode.READ_ONLY: 0,
    PermissionMode.WORKSPACE_WRITE: 1,
    PermissionMode.DANGER_FULL_ACCESS: 2,
}

_TOOL_REQUIREMENTS: dict[str, PermissionMode] = {
    "execute_cli_command": PermissionMode.WORKSPACE_WRITE,
    "create_task": PermissionMode.WORKSPACE_WRITE,
    "stop_task": PermissionMode.WORKSPACE_WRITE,
}

_READ_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "cat",
        "date",
        "df",
        "dig",
        "dmesg",
        "echo",
        "free",
        "hostname",
        "ip",
        "journalctl",
        "ls",
        "netstat",
        "nslookup",
        "ping",
        "ps",
        "ss",
        "uname",
        "uptime",
        "w",
        "who",
    }
)


def get_permission_mode() -> PermissionMode:
    """Return the active core permission mode from environment."""
    raw = os.environ.get("NINKO_CORE_PERMISSION_MODE", PermissionMode.WORKSPACE_WRITE)
    try:
        return PermissionMode(raw)
    except ValueError:
        return PermissionMode.WORKSPACE_WRITE


def validate_tool_permission(tool_name: str) -> PermissionDecision:
    """Validate the active permission mode for a core tool."""
    required = _TOOL_REQUIREMENTS.get(tool_name, PermissionMode.WORKSPACE_WRITE)
    active = get_permission_mode()
    if _MODE_RANK[active] < _MODE_RANK[required]:
        return PermissionDecision(
            allowed=False,
            reason=(
                f"Tool '{tool_name}' requires permission mode '{required}', "
                f"active mode is '{active}'."
            ),
        )
    return PermissionDecision(allowed=True)


def validate_cli_command(command: str, allowed_commands: set[str]) -> list[str]:
    """
    Parse and validate a CLI command according to the active permission mode.

    Returns the tokenized argv list if the command is allowed.
    """
    decision = validate_tool_permission("execute_cli_command")
    if not decision.allowed:
        raise PermissionDeniedError(decision.reason)

    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise PermissionDeniedError(f"Invalid command syntax: {exc}") from exc

    if not args:
        raise PermissionDeniedError("Empty command.")

    cmd_name = args[0].rsplit("/", 1)[-1]
    if cmd_name not in allowed_commands:
        raise PermissionDeniedError(
            f"Command '{cmd_name}' is not allowed. Allowed commands: "
            f"{', '.join(sorted(allowed_commands))}"
        )

    active = get_permission_mode()
    if active == PermissionMode.READ_ONLY and cmd_name not in _READ_ONLY_COMMANDS:
        raise PermissionDeniedError(
            f"Command '{cmd_name}' is blocked in permission mode '{active}'."
        )

    return args
