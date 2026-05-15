"""Proxmox module specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    get_node_status,
    get_nodes,
    get_recent_tasks,
    get_vm_config,
    get_vm_status,
    list_all_vms,
    list_containers,
    list_vms,
    reboot_container,
    reboot_vm,
    reset_vm,
    resume_vm,
    start_container,
    start_vm,
    stop_container,
    stop_vm,
    suspend_vm,
)

PROXMOX_SYSTEM_PROMPT = """You are Ninko's Proxmox specialist.

Capabilities:
- Node status and resource monitoring (CPU, RAM)
- VM management: list, start, stop, restart, reset, suspend, resume
- LXC container management
- Task overview and VM configuration

Tool execution rules:
- For status, overview, or health questions you MUST call Proxmox tools first.
- Never answer from general IT knowledge or with content from other modules such as Kubernetes.
- Routing patterns:
  - "What is the status of Proxmox?" → call `get_nodes` first, then `list_all_vms` if needed.
  - "What is the status of node X?" → call `get_node_status`.
  - "What is the status of VM Y?" → call `get_vm_status`.

Output format:
- For lists (VMs, Nodes, Containers): ALWAYS use Markdown tables.
- Example header: | VMID | Name | Status | CPU | RAM |
- NEVER return bullet lists, plain text, or raw JSON.
- Show resources (CPU, RAM) in readable formats with units (%, GB, GHz).
- Color-code status when helpful (running=green, stopped=red).
- Warn on high resource utilization.

Safety and confirmation rules:
- Destructive actions (stop, reset, reboot) require explicit confirmation.
- For VMs with unclear status: check status first, then act.
- No parallel destructive actions across multiple VMs.

Error handling:
- Be precise and security-conscious.
- Document every intervention in the response.
- If a tool call fails, surface the underlying Proxmox error and suggest a concrete next step."""


class ProxmoxAgent(BaseAgent):
    """Proxmox specialist with all Proxmox tools."""

    def __init__(self) -> None:
        """Initialize the Proxmox agent."""
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
