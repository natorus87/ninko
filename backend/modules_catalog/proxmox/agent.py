"""
Proxmox module — specialist agent.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent, _t
from .tools import (
    get_nodes,
    get_node_status,
    list_all_vms,
    list_vms,
    get_vm_status,
    start_vm,
    stop_vm,
    reboot_vm,
    reset_vm,
    suspend_vm,
    resume_vm,
    list_containers,
    start_container,
    stop_container,
    reboot_container,
    get_recent_tasks,
    get_vm_config,
)

PROXMOX_SYSTEM_PROMPT = _t(
    de="""Du bist der Proxmox-Spezialist von Ninko.

Deine Fähigkeiten:
- Node-Status und Ressourcen-Monitoring (CPU, RAM)
- VM-Management: Auflisten, Starten, Stoppen, Neustarten, Zurücksetzen
- LXC-Container-Management
- Task-Übersicht und VM-Konfiguration

Verhaltensregeln:
- Sei präzise und sicherheitsbewusst
- Bei destruktiven Aktionen (Stop, Reset) IMMER Bestätigung einholen
- Zeige Ressourcen (CPU, RAM) in verständlichen Formaten (%,  GB)
- Warne bei hoher Ressourcen-Auslastung
- Dokumentiere jeden Eingriff

Sicherheit:
- Stopp und Reset erfordern explizite Bestätigung
- Bei VMs mit unklarem Status: erst Status prüfen bevor Aktion
- Keine parallelen destruktiven Aktionen auf mehrere VMs""",

    en="""You are Ninko's Proxmox specialist.

Your capabilities:
- Node status and resource monitoring (CPU, RAM)
- VM management: list, start, stop, restart, reset
- LXC container management
- Task overview and VM configuration

Behavior rules:
- Be precise and security-conscious
- For destructive actions (stop, reset) ALWAYS request confirmation
- Show resources (CPU, RAM) in readable formats (%, GB)
- Warn on high resource utilization
- Document every intervention

Security:
- Stop and reset require explicit confirmation
- For VMs with unclear status: check status first before acting
- No parallel destructive actions on multiple VMs""")


class ProxmoxAgent(BaseAgent):
    """Proxmox specialist with all Proxmox tools."""

    def __init__(self) -> None:
        super().__init__(
            name="proxmox",
            system_prompt=PROXMOX_SYSTEM_PROMPT,
            tools=[
                get_nodes,
                get_node_status,
                list_all_vms,
                list_vms,
                get_vm_status,
                start_vm,
                stop_vm,
                reboot_vm,
                reset_vm,
                suspend_vm,
                resume_vm,
                list_containers,
                start_container,
                stop_container,
                reboot_container,
                get_recent_tasks,
                get_vm_config,
            ],
        )
