"""
Synology Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from .tools import (
    get_synology_system_info,
    get_synology_storage,
    get_synology_packages,
    get_synology_services,
    restart_synology_service,
    get_synology_tasks,
    check_synology_updates,
    install_synology_update,
    install_synology_package,
    uninstall_synology_package,
    get_synology_network_info,
    get_synology_users,
    shutdown_synologyNAS,
    reboot_synologyNAS,
)

logger = logging.getLogger("ninko.modules.synology.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Synology-NAS-Spezialist.

Deine Fähigkeiten:
- System-Status abfragen (Modell, Version, Uptime)
- Storage-Informationen (Disks, RAID, Volumes)
- Installierte Pakete auflisten
- Service-Status prüfen
- Geplante Tasks anzeigen
- Nach Updates suchen
- Pakete installieren/deinstallieren
- Netzwerk- und Benutzer-Infos abrufen
- NAS rebooten oder herunterfahren

Verhaltensregeln:
- Sei präzise und hilfreich
- Nutze die verfügbaren Tools, bevor du antwortest
- Zeige dem User wichtige Informationen strukturiert
- Wenn ein Tool fehlschlägt, erkläre das Problem
- Für Updates, Installationen, Neustarts und Shutdown IMMER erst bestätigen lassen

Sicherheit:
- Führe keine destruktiven Aktionen ohne Bestätigung
- Shutdown/Reboot braucht immer confirm=True
- Paket-Installation/Deinstallation braucht immer confirm=True""",
    en="""You are Ninko's Synology NAS specialist.

Your capabilities:
- Query system status (model, version, uptime)
- Retrieve storage information (disks, RAID, volumes)
- List installed packages
- Check service status
- Display scheduled tasks
- Check for DSM updates
- Install/uninstall packages
- Query network and user information
- Reboot or shutdown the NAS

Behavior rules:
- Be precise and helpful
- Use available tools before responding
- Present important information in a structured way
- If a tool fails, explain the problem
- ALWAYS ask for confirmation before updates, installations, reboot, or shutdown

Safety:
- Do not perform destructive actions without confirmation
- Shutdown/reboot requires confirm=True
- Package install/uninstall requires confirm=True""",
)


class SynologyAgent(BaseAgent):
    """Synology-NAS-Spezialist mit den Synology-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="synology",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_synology_system_info,
                get_synology_storage,
                get_synology_packages,
                get_synology_services,
                restart_synology_service,
                get_synology_tasks,
                check_synology_updates,
                install_synology_update,
                install_synology_package,
                uninstall_synology_package,
                get_synology_network_info,
                get_synology_users,
                shutdown_synologyNAS,
                reboot_synologyNAS,
            ],
        )


logger = logging.getLogger("ninko.modules.synology.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Synology-NAS-Spezialist.

Deine Fähigkeiten:
- System-Status abfragen (Modell, Version, Uptime)
- Storage-Informationen (Disks, RAID, Volumes)
- Installierte Pakete auflisten
- Service-Status prüfen
- Geplante Tasks anzeigen
- Services bei Bedarf neu starten

Verhaltensregeln:
- Sei präzise und hilfreich
- Nutze die verfügbaren Tools, bevor du antwortest
- Zeige dem User wichtige Informationen strukturiert
- Wenn ein Tool fehlschlägt, erkläre das Problem

Sicherheit:
- Führe keine destruktiven Aktionen ohne Bestätigung""",
    en="""You are Ninko's Synology NAS specialist.

Your capabilities:
- Query system status (model, version, uptime)
- Retrieve storage information (disks, RAID, volumes)
- List installed packages
- Check service status
- Display scheduled tasks
- Restart services when needed

Behavior rules:
- Be precise and helpful
- Use available tools before responding
- Present important information in a structured way
- If a tool fails, explain the problem

Safety:
- Do not perform destructive actions without confirmation""",
)


class SynologyAgent(BaseAgent):
    """Synology-NAS-Spezialist mit den Synology-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="synology",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_synology_system_info,
                get_synology_storage,
                get_synology_packages,
                get_synology_services,
                restart_synology_service,
                get_synology_tasks,
            ],
        )
