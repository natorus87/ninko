"""Proxmox module specialist agent."""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent

from .tools import (
    get_node_status,
    get_node_ip_addresses,
    get_nodes,
    get_recent_tasks,
    get_vm_ip_addresses,
    get_vm_config,
    get_vm_status,
    list_node_ip_addresses,
    list_all_vms,
    list_containers,
    list_vm_ip_addresses,
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
- IP address discovery for nodes, VMs, and LXC containers
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
  - "Which IP address does node X have?" → call `get_node_ip_addresses`.
  - "Which IP address does VM/CT Y have?" → call `get_vm_ip_addresses`.
  - "Show all Proxmox IP addresses" → call `list_node_ip_addresses` and `list_vm_ip_addresses`.

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


def _is_simple_proxmox_status_request(message: str) -> bool:
    """Detect Proxmox overview questions that do not need LLM planning."""
    text = message.casefold()
    has_proxmox_target = any(token in text for token in ("proxmox", "pve"))
    has_status_intent = any(
        token in text
        for token in (
            "status",
            "health",
            "gesund",
            "zustand",
            "overview",
            "übersicht",
            "uebersicht",
        )
    )
    has_specific_scope = any(
        token in text
        for token in (
            "vm ",
            "vmid",
            "node ",
            "knoten",
            "lxc",
            "container",
            "task",
            "tasks",
            "config",
        )
    )
    return has_proxmox_target and has_status_intent and not has_specific_scope


def _format_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f} %"
    except (TypeError, ValueError):
        return "n/a"


def _format_proxmox_status(nodes: Any, vms: Any) -> str:
    node_items = nodes if isinstance(nodes, list) else []
    node_rows = []
    for node in node_items:
        node_rows.append(
            "| {node} | {status} | {cpu} | {mem_used} / {mem_total} | {mem_pct} |".format(
                node=node.get("node", "-"),
                status=node.get("status", "unknown"),
                cpu=_format_pct(node.get("cpu_usage")),
                mem_used=node.get("mem_used_human", "n/a"),
                mem_total=node.get("mem_total_human", "n/a"),
                mem_pct=_format_pct(node.get("mem_usage")),
            )
        )

    vm_items = vms if isinstance(vms, list) else []
    running = sum(1 for vm in vm_items if str(vm.get("status", "")).lower() == "running")
    stopped = sum(1 for vm in vm_items if str(vm.get("status", "")).lower() == "stopped")
    other = max(0, len(vm_items) - running - stopped)

    warning_nodes = [
        str(node.get("node", "unknown"))
        for node in node_items
        if str(node.get("status", "")).lower() != "online"
    ]
    assessment = (
        "Der Proxmox-Cluster wirkt gesund."
        if not warning_nodes
        else "Der Proxmox-Cluster braucht Aufmerksamkeit."
    )

    sections = [
        assessment,
        "",
        "| Node | Status | CPU | RAM | RAM-Auslastung |",
        "|---|---:|---:|---:|---:|",
        *(node_rows or ["| - | Keine Node-Daten | - | - | - |"]),
        "",
        "| VMs gesamt | Laufend | Gestoppt | Sonstige |",
        "|---:|---:|---:|---:|",
        f"| {len(vm_items)} | {running} | {stopped} | {other} |",
    ]
    return "\n".join(sections)


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
                get_node_ip_addresses,
                list_node_ip_addresses,
                list_all_vms,
                list_vms,
                get_vm_status,
                get_vm_ip_addresses,
                list_vm_ip_addresses,
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

    async def invoke(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
        confirmed: bool = False,
        wants_stream: bool = False,
        token_callback: Any = None,
        cancellation_check: Any = None,
    ) -> tuple[str, bool]:
        if _is_simple_proxmox_status_request(message):
            from core import status_bus

            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Proxmox-Status-Fast-Path",
                detail="get_nodes und list_all_vms werden direkt ausgeführt.",
                data={"agent": self.name, "tools": ["get_nodes", "list_all_vms"]},
                status="running",
            )
            nodes = await get_nodes.ainvoke({"connection_id": ""})
            vms = await list_all_vms.ainvoke({"connection_id": ""})
            await status_bus.emit_trace(
                session_id,
                phase="agent",
                label="Proxmox-Status geladen",
                data={"agent": self.name, "tools": ["get_nodes", "list_all_vms"]},
            )
            return _format_proxmox_status(nodes, vms), False

        return await super().invoke(
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )
