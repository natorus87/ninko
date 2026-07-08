from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
TOOLS_PATH = BACKEND_DIR / "modules_catalog" / "linux_server" / "tools.py"
spec = importlib.util.spec_from_file_location("linux_server_tools_under_test", TOOLS_PATH)
assert spec is not None
assert spec.loader is not None
linux_tools = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = linux_tools
spec.loader.exec_module(linux_tools)


class CommandCapture:
    def __init__(self, output: str = "OPEN") -> None:
        self.commands: list[tuple[str, str, int]] = []
        self.output = output

    async def __call__(
        self,
        cmd: str,
        connection_id: str = "",
        timeout: int = 30,
    ) -> dict[str, Any]:
        self.commands.append((cmd, connection_id, timeout))
        return {"exit_code": 0, "output": self.output, "error": "", "host": "test-host"}


@pytest.mark.parametrize(
    ("tool", "payload"),
    [
        (linux_tools.service_action, {"service": "nginx.service; reboot", "action": "restart"}),
        (linux_tools.get_journal, {"service": "nginx.service; reboot", "lines": 20}),
        (linux_tools.apt_install, {"packages": "nginx; reboot"}),
        (linux_tools.apt_upgrade, {"packages": "openssl $(reboot)"}),
        (linux_tools.check_port, {"host": "example.com; reboot", "port": 443}),
        (linux_tools.check_port, {"host": "example.com", "port": 70000}),
    ],
)
async def test_linux_server_tools_reject_shell_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
    tool: Any,
    payload: dict[str, Any],
) -> None:
    capture = CommandCapture()
    monkeypatch.setattr(linux_tools, "_run_ssh_command", capture)

    result = await tool.ainvoke(payload)

    assert capture.commands == []
    assert "Invalid value" in str(result) or "Ungültiger Wert" in str(result)


async def test_file_tools_quote_paths_and_use_option_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = CommandCapture(output="log line")
    monkeypatch.setattr(linux_tools, "_run_ssh_command", capture)

    result = await linux_tools.get_logfile.ainvoke(
        {"path": "/var/log/app error's.log", "lines": 25}
    )

    assert result == "log line"
    assert capture.commands == [
        ("tail -n 25 -- '/var/log/app error'\"'\"'s.log' 2>/dev/null", "", 30)
    ]


async def test_check_port_passes_host_and_port_as_bash_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = CommandCapture(output="OPEN")
    monkeypatch.setattr(linux_tools, "_run_ssh_command", capture)

    result = await linux_tools.check_port.ainvoke({"host": "example.com", "port": 443})

    assert result == {"host": "example.com", "port": 443, "status": "open"}
    assert capture.commands == [
        (
            "timeout 3 bash -c 'echo > /dev/tcp/$1/$2' -- example.com 443 "
            "2>&1 && echo 'OPEN' || echo 'CLOSED'",
            "",
            30,
        )
    ]
