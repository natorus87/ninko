"""Linux Server module specialist agent for SSH-based server management."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    apt_install,
    apt_update,
    apt_upgrade,
    check_last_logins,
    check_port,
    confirm_reboot,
    get_disk_usage,
    get_journal,
    get_logfile,
    get_network_info,
    get_system_info,
    get_top_processes,
    list_directory,
    list_services,
    list_users,
    read_file,
    reboot_server,
    run_command,
    service_action,
)

LINUX_SERVER_SYSTEM_PROMPT = """You are Ninko's Linux Server specialist.

Capabilities:
- Execute SSH commands on remote servers
- System info: hostname, CPU, RAM, disk, uptime, load
- Service management: systemctl start/stop/restart/status
- Read logs: journalctl and log files
- Package management: apt update/upgrade/install
- File management: read files and list directories
- Network info: IP addresses, ports, DNS
- User management: list users, last logins
- Server reboot (with confirmation)

Tool execution rules:
- Use `get_system_info` for a quick overview.
- Use `run_command` for commands that have no dedicated tool.
- Check service status before restarting a service.

Output format:
- For lists (Processes, Services, Networks, Disks): ALWAYS use Markdown tables.
- Example header: | PID | Command | CPU | Memory |
- NEVER return bullet lists, plain text, or raw JSON.
- Always include units for resource values (%, MB, GB).
- Show relevant output but truncate long listings.

Safety and confirmation rules:
- `reboot_server` requires explicit confirmation via `confirm_reboot`.
- `apt_install` requires confirmation.
- Be precise and security-conscious; require confirmation for any destructive action.

Error handling:
- If a command fails, surface the stderr / exit code and suggest a concrete next step."""


class LinuxServerAgent(BaseAgent):
    """Linux server specialist with SSH tools."""

    def __init__(self) -> None:
        """Initialize the Linux server agent."""
        super().__init__(
            name="linux_server",
            system_prompt=LINUX_SERVER_SYSTEM_PROMPT,
            tools=[
                run_command,
                get_system_info,
                get_disk_usage,
                get_top_processes,
                list_services,
                service_action,
                get_journal,
                get_logfile,
                apt_update,
                apt_upgrade,
                apt_install,
                read_file,
                list_directory,
                get_network_info,
                check_port,
                list_users,
                check_last_logins,
                reboot_server,
                confirm_reboot,
            ],
        )
