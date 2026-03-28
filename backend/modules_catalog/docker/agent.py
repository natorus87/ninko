"""
Docker Modul – Spezialist-Agent für Docker Host Management.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from .tools import (
    list_containers,
    inspect_container,
    start_container,
    stop_container,
    restart_container,
    remove_container,
    get_container_logs,
    get_container_stats,
    list_images,
    pull_image,
    remove_image,
    list_volumes,
    remove_volume,
    get_docker_info,
    get_docker_version,
    get_docker_disk_usage,
)

DOCKER_SYSTEM_PROMPT = """Du bist der Docker-Spezialist von Ninko.

Deine Fähigkeiten:
- Container-Management: Auflisten, Starten, Stoppen, Neustarten, Entfernen
- Container-Logs und Ressourcen-Statistiken (CPU, RAM, Netzwerk)
- Image-Management: Auflisten, Herunterladen (pull), Entfernen
- Volume-Management: Auflisten, Entfernen
- System-Info: Docker Version, Speicherauslastung, Host-Ressourcen

Verhaltensregeln:
- Sei präzise und sicherheitsbewusst
- Bei destruktiven Aktionen (remove, force remove) IMMER Bestätigung einholen
- Zeige Ressourcen in verständlichen Formaten (%, GB, MB)
- Bei der Container-Auflistung zeige Status (running, stopped, exited) klar an
- Dokumentiere jeden Eingriff

Sicherheit:
- Container entfernen erfordert explizite Bestätigung
- Images mit force=true erfordern Bestätigung
- Prüfe Container-Status bevor Aktionen ausgeführt werden
- Keine parallelen destruktiven Aktionen"""


class DockerAgent(BaseAgent):
    """Docker-Spezialist mit allen Docker-Management-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="docker",
            system_prompt=DOCKER_SYSTEM_PROMPT,
            tools=[
                list_containers,
                inspect_container,
                start_container,
                stop_container,
                restart_container,
                remove_container,
                get_container_logs,
                get_container_stats,
                list_images,
                pull_image,
                remove_image,
                list_volumes,
                remove_volume,
                get_docker_info,
                get_docker_version,
                get_docker_disk_usage,
            ],
        )
