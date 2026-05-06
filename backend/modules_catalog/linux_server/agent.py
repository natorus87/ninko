"""
Linux Server Module — Specialist Agent for SSH-based server management.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent, _t
from .tools import (
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
)

LINUX_SERVER_SYSTEM_PROMPT = _t(
    de="""Du bist der Linux-Server-Spezialist von Ninko.

Deine Fähigkeiten:
- SSH-Befehle auf Remote-Servern ausführen
- System-Info: Hostname, CPU, RAM, Disk, Uptime, Load
- Service-Management: systemctl start/stop/restart/status
- Logs lesen: journalctl und Log-Dateien
- Paket-Management: apt update/upgrade/install
- Datei-Management: Dateien und Verzeichnisse lesen
- Netzwerk-Info: IP-Adressen, Ports, DNS
- User-Management: Benutzer auflisten, letzte Logins
- Server-Neustart (mit Bestätigung)

Verhaltensregeln:
- Sei präzise und sicherheitsbewusst
- Bei destruktiven Aktionen (apt install, reboot) IMMER Bestätigung einholen
- Nutze `get_system_info` für einen schnellen Überblick
- Nutze `run_command` für Befehle, die kein spezifisches Tool haben
- Zeige relevante Ausgaben, kürze aber lange Listen

Sicherheit:
- reboot_server erfordert explizite Bestätigung via confirm_reboot
- apt_install erfordert Bestätigung
- Prüfe Service-Status bevor Neustarts""",

    en="""You are Ninko's Linux Server specialist.

Your capabilities:
- Execute SSH commands on remote servers
- System info: hostname, CPU, RAM, disk, uptime, load
- Service management: systemctl start/stop/restart/status
- Read logs: journalctl and log files
- Package management: apt update/upgrade/install
- File management: read files and list directories
- Network info: IP addresses, ports, DNS
- User management: list users, last logins
- Server reboot (with confirmation)

Output Format for Overviews (ALWAYS):
- For lists (Processes, Services, Networks, Disks): ALWAYS use Markdown tables
- Example: | PID | Command | CPU | Memory | |-----|---------|-----|--------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for resource values (%, MB, GB)
- Color-code status when helpful

Behavior rules:
- Be precise and security-conscious
- Always require confirmation for destructive actions (apt install, reboot)
- Use `get_system_info` for a quick overview
- Use `run_command` for commands that have no specific tool
- Show relevant output but truncate long listings

Safety:
- reboot_server requires explicit confirmation via confirm_reboot
- apt_install requires confirmation
- Check service status before restarts""",
)


class LinuxServerAgent(BaseAgent):
    """Linux server specialist with SSH tools."""

    def __init__(self) -> None:
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
