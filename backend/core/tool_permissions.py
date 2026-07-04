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


# ── Subcommand-/Argument-Policy für write-fähige, aber read-only gemeinte Tools ──
# Diese Kommandos stehen auf der Allowlist für Diagnose, können aber Systemzustand
# ändern. Echte Änderungen gehören in Modul-Tools mit Safeguard, nicht in die
# generische CLI. Im Modus DANGER_FULL_ACCESS wird die Policy nicht angewandt.
_SYSTEMCTL_READ_SUBCOMMANDS: frozenset[str] = frozenset({
    "status", "show", "cat", "list-units", "list-unit-files", "list-jobs",
    "list-timers", "list-sockets", "list-dependencies", "is-active", "is-enabled",
    "is-failed", "get-default", "show-environment", "help",
})
_IP_WRITE_TOKENS: frozenset[str] = frozenset({
    "set", "add", "del", "delete", "change", "replace", "append", "flush",
})
_ROUTE_WRITE_TOKENS: frozenset[str] = frozenset({
    "add", "del", "delete", "change", "flush",
})
_JOURNALCTL_DENY_FLAG_PREFIXES: tuple[str, ...] = (
    "--vacuum", "--rotate", "--flush", "--relinquish-var", "--sync",
)
_ETHTOOL_WRITE_FLAGS: frozenset[str] = frozenset({
    "-s", "--change", "-A", "--pause", "-C", "--coalesce", "-G", "--set-ring",
    "-K", "--features", "--offload", "-L", "--set-channels", "-N", "-U",
    "--config-nfc", "--config-ntuple", "-P", "--set-eee", "-r", "--negotiate",
    "--reset",
})
_DPKG_QUERY_FLAGS: frozenset[str] = frozenset({
    "-l", "--list", "-L", "--listfiles", "-s", "--status", "-S", "--search",
    "-p", "--print-avail", "--get-selections", "-V", "--verify",
})


def _first_positional(tokens: list[str]) -> str | None:
    """Erstes Nicht-Flag-Argument (Subcommand)."""
    for tok in tokens:
        if not tok.startswith("-"):
            return tok
    return None


def _assert_readonly_cli_usage(cmd_name: str, args: list[str]) -> None:
    """Erzwingt read-only-Nutzung für write-fähige Allowlist-Kommandos.

    Raises PermissionDeniedError bei erkanntem schreibendem/zustandsänderndem Aufruf.
    """
    rest = args[1:]

    if cmd_name == "systemctl":
        sub = _first_positional(rest)
        if sub is not None and sub not in _SYSTEMCTL_READ_SUBCOMMANDS:
            raise PermissionDeniedError(
                f"systemctl-Subcommand '{sub}' ist nicht erlaubt "
                f"(nur lesende: {', '.join(sorted(_SYSTEMCTL_READ_SUBCOMMANDS))})."
            )
    elif cmd_name == "journalctl":
        for tok in rest:
            if tok.startswith(_JOURNALCTL_DENY_FLAG_PREFIXES):
                raise PermissionDeniedError(
                    f"journalctl-Option '{tok}' ist nicht erlaubt (verändert/löscht Logs)."
                )
    elif cmd_name == "ip":
        for tok in rest:
            if tok in _IP_WRITE_TOKENS:
                raise PermissionDeniedError(
                    f"ip-Aktion '{tok}' ist nicht erlaubt (nur anzeigen/lesen)."
                )
    elif cmd_name == "route":
        for tok in rest:
            if tok in _ROUTE_WRITE_TOKENS:
                raise PermissionDeniedError(
                    f"route-Aktion '{tok}' ist nicht erlaubt (nur anzeigen)."
                )
    elif cmd_name == "ethtool":
        for tok in rest:
            if tok in _ETHTOOL_WRITE_FLAGS:
                raise PermissionDeniedError(
                    f"ethtool-Option '{tok}' ist nicht erlaubt (ändert NIC-Parameter)."
                )
    elif cmd_name == "dpkg":
        first = _first_positional_or_flag(rest)
        if first is not None and first not in _DPKG_QUERY_FLAGS:
            raise PermissionDeniedError(
                f"dpkg erlaubt nur Query-Flags ({', '.join(sorted(_DPKG_QUERY_FLAGS))}), "
                f"nicht '{first}'."
            )
    elif cmd_name == "rpm":
        first = _first_positional_or_flag(rest)
        if first is not None and not (first.startswith("-q") or first == "--query"):
            raise PermissionDeniedError(
                "rpm erlaubt nur den Query-Modus (-q / --query)."
            )


def _first_positional_or_flag(tokens: list[str]) -> str | None:
    """Erstes Argument-Token (Flag oder Positional), sonst None."""
    return tokens[0] if tokens else None


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

    # Pfad-Argumente ablehnen: sonst würde die Allowlist nur den Basename prüfen
    # (z.B. "/tmp/x/cat"), aber ein beliebiges gleichnamiges Binary ausführen.
    if "/" in args[0]:
        raise PermissionDeniedError(
            f"Command must be a bare name, not a path: '{args[0]}'."
        )
    cmd_name = args[0]
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

    # Write-fähige Allowlist-Kommandos auf read-only-Nutzung beschränken.
    # Nur bei DANGER_FULL_ACCESS überspringen (Operator hat sich bewusst dafür entschieden).
    if active != PermissionMode.DANGER_FULL_ACCESS:
        _assert_readonly_cli_usage(cmd_name, args)

    return args
