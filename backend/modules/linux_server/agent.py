"""
Linux Server Modul – Spezialist-Agent für SSH-basiertes Server-Management.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from modules.linux_server.tools import (
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

LINUX_SERVER_SYSTEM_PROMPT = """Du bist der Linux-Server-Spezialist von Kumio.

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
- Dokumentiere jeden Eingriff

Sicherheit:
- reboot_server erfordert explizite Bestätigung via confirm_reboot
- apt_install erfordert Bestätigung
- Prüfe Service-Status bevor Neustarts
- Keine parallelen destruktiven Aktionen"""


class LinuxServerAgent(BaseAgent):
    """Linux-Server-Spezialist mit SSH-Tools."""

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
