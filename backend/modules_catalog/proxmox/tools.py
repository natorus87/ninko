"""
Proxmox module — LangGraph @tool functions.
Full implementation using proxmoxer.
"""

from __future__ import annotations

import json
import logging
from ipaddress import ip_address, ip_network

from langchain_core.tools import tool
from proxmoxer.core import ResourceException

logger = logging.getLogger("ninko.modules.proxmox.tools")

# Proxmox-API wirft ResourceException bei HTTP-Fehlern (404 für falsche
# VMID, 401 für ungültige Tokens, 500 für Server-Fehler). Wir fangen sie
# zusammen mit den üblichen Python-Exceptions ab, damit der LLM-Agent
# nicht durch unbehandelte Tool-Exceptions crasht.
_PROXMOX_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    ResourceException,
)


def _warn_if_insecure_verify(source: str, verify_ssl: bool) -> None:
    if not verify_ssl:
        logger.warning(
            "Proxmox SSL verification disabled for %s (verify_ssl=false). "
            "This is insecure and should only be used in development environments.",
            source,
        )


async def _get_proxmox_client(connection_id: str = "") -> object:
    """Creates an authenticated Proxmox API connection via ConnectionManager."""
    from proxmoxer import ProxmoxAPI
    from core.vault import get_vault
    from core.connections import ConnectionManager

    if connection_id:
        conn = await ConnectionManager.get_connection("proxmox", connection_id)
        if not conn:
            raise ValueError(f"Proxmox connection with ID '{connection_id}' not found.")
    else:
        conn = await ConnectionManager.get_default_connection("proxmox")
        if not conn:
            raise ValueError("No default Proxmox connection configured.")

    vault = get_vault()

    host = conn.config.get("host", "")
    user = conn.config.get("user", "root@pam")
    token_id = conn.config.get("token_id", "")
    verify_ssl = conn.config.get("verify_ssl", "false").lower() == "true"
    _warn_if_insecure_verify(f"connection '{conn.name}'", verify_ssl)

    # Extract token ID from user field if not explicitly stored
    # (user field may contain "root@pam!Ninko" → token_id = "Ninko")
    if not token_id and "!" in user:
        token_id = user.split("!", 1)[1]

    # Retrieve secret from Vault using stored keys
    token_secret = None
    if "token_secret" in conn.vault_keys:
        token_secret = await vault.get_secret(conn.vault_keys["token_secret"])

    if token_secret and token_id:
        # Clean user field: remove appended "!token" if present
        # (proxmoxer builds "user!token_name" on its own)
        base_user = user.split("!")[0]
        host_addr = host.replace("https://", "").replace("http://", "").split(":")[0]

        px = ProxmoxAPI(
            host_addr,
            port=8006,
            user=base_user,
            token_name=token_id,
            token_value=token_secret,
            verify_ssl=verify_ssl,
        )
        if verify_ssl:
            # Probe once to surface certificate issues immediately, but never
            # silently downgrade transport security.
            px.version.get()

        return px

    # Fallback: password
    password = None
    if "password" in conn.vault_keys:
        password = await vault.get_secret(conn.vault_keys["password"])

    if password:
        return ProxmoxAPI(
            host,
            user=user,
            password=password,
            verify_ssl=verify_ssl,
        )

    raise ValueError(f"No valid credentials found for Proxmox connection '{conn.name}'.")


def _format_bytes(b: int) -> str:
    """Format bytes into a human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _format_vms_as_markdown(vms: list[dict], title: str = "VMs") -> str:
    if not vms:
        return f"Keine {title} gefunden."
    lines = [
        f"**{title}** ({len(vms)}):",
        "",
        "| VMID | Name | Node | Type | Status | CPU (%) | RAM |",
        "|---:|---|---|---|---:|---:|---|",
    ]
    for vm in vms:
        mem_total = vm.get("mem_total") or 0
        ram_gb = mem_total / (1024**3)
        lines.append(
            f"| {vm.get('vmid', '-')} | {vm.get('name', '-')} | "
            f"{vm.get('node', '-')} | {vm.get('type', '-')} | "
            f"{vm.get('status', '-')} | {float(vm.get('cpu_usage') or 0):.1f} | "
            f"{ram_gb:.2f} GB |"
        )
    return "\n".join(lines)


def _format_nodes_as_markdown(nodes: list[dict]) -> str:
    if not nodes:
        return "Keine Proxmox-Nodes gefunden."
    lines = [
        f"**Proxmox-Nodes** ({len(nodes)}):",
        "",
        "| Node | Status | CPU (%) | RAM benutzt | RAM gesamt | RAM (%) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for n in nodes:
        lines.append(
            f"| {n.get('node', '-')} | {n.get('status', '-')} | "
            f"{float(n.get('cpu_usage') or 0):.1f} | "
            f"{n.get('mem_used_human', '-')} | {n.get('mem_total_human', '-')} | "
            f"{float(n.get('mem_usage') or 0):.1f} |"
        )
    return "\n".join(lines)


def _format_ips_as_markdown(ips: list[dict], title: str = "IP-Adressen") -> str:
    if not ips:
        return f"Keine {title} gefunden."
    lines = [
        f"**{title}** ({len(ips)}):",
        "",
        "| Node/VM | Interface | IP | Familie | Gateway |",
        "|---|---|---|---|---|",
    ]
    for entry in ips:
        lines.append(
            f"| {entry.get('node') or entry.get('name') or '-'} | "
            f"{entry.get('interface', '-') or '-'} | "
            f"{entry.get('ip') or entry.get('address') or '-'} | "
            f"{entry.get('family', '-')} | "
            f"{entry.get('gateway', '-') or '-'} |"
        )
    return "\n".join(lines)


def _format_vm_ip_dict_as_markdown(data: dict) -> str:
    vmid = data.get("vmid", "?")
    name = data.get("name", "?")
    node = data.get("node", "?")
    status = data.get("status", "?")
    guest_type = data.get("type", "?")
    ips = data.get("ips") or []
    source = data.get("source", "")
    note = data.get("note", "")
    header = (
        f"**{guest_type.upper()} {vmid} ({name})** auf Node `{node}` — "
        f"Status: `{status}`, Quelle: `{source or 'n/a'}`"
    )
    if not ips:
        detail = f"Keine IP-Adressen gefunden. {note}".strip()
        return f"{header}\n\n{detail}"
    lines = [header, "", "| Interface | IP | Familie |", "|---|---|---|"]
    for ip in ips:
        lines.append(
            f"| {ip.get('interface', '-') or '-'} | "
            f"{ip.get('ip') or ip.get('address') or '-'} | "
            f"{ip.get('family', '-')} |"
        )
    if note:
        lines.extend(["", f"_{note}_"])
    return "\n".join(lines)


def _normalize_ip_entry(address: str, family: str, interface: str = "") -> dict | None:
    """Normalizes an IP address entry from Proxmox into a stable shape."""
    value = str(address or "").strip()
    if not value:
        return None

    ip_value = value.split("/", 1)[0]
    try:
        parsed = ip_address(ip_value)
    except ValueError:
        return None

    if parsed.is_loopback or parsed.is_unspecified or parsed.is_link_local:
        return None

    return {
        "interface": interface,
        "address": value,
        "ip": str(parsed),
        "family": family or f"ipv{parsed.version}",
    }


def _extract_qemu_agent_ips(interfaces: list[dict]) -> list[dict]:
    """Extracts usable IPs from QEMU guest-agent network-get-interfaces output."""
    ips = []
    seen = set()
    for iface in interfaces or []:
        if not isinstance(iface, dict):
            continue
        interface_name = str(iface.get("name", ""))
        for item in iface.get("ip-addresses", []) or []:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_ip_entry(
                str(item.get("ip-address", "")),
                str(item.get("ip-address-type", "")),
                interface_name,
            )
            if not normalized:
                continue
            key = (normalized["interface"], normalized["ip"], normalized["family"])
            if key not in seen:
                ips.append(normalized)
                seen.add(key)
    return ips


def _extract_lxc_interface_ips(interfaces: list[dict]) -> list[dict]:
    """Extracts usable IPs from the LXC interfaces API response."""
    ips = []
    seen = set()
    for iface in interfaces:
        interface_name = str(iface.get("name", iface.get("iface", "")))
        for field, family in (("inet", "ipv4"), ("inet6", "ipv6")):
            normalized = _normalize_ip_entry(str(iface.get(field, "")), family, interface_name)
            if not normalized:
                continue
            key = (normalized["interface"], normalized["ip"], normalized["family"])
            if key not in seen:
                ips.append(normalized)
                seen.add(key)
    return ips


def _parse_proxmox_net_config(config: dict) -> list[dict]:
    """Extracts static IP hints from QEMU/LXC net* config values."""
    ips = []
    seen = set()
    for key, raw_value in sorted(config.items()):
        if not key.startswith("net"):
            continue
        interface = str(key)
        parts = str(raw_value).split(",")
        for part in parts:
            name, _, value = part.partition("=")
            if name not in {"ip", "ip6"} or value in {"", "dhcp", "auto", "manual"}:
                continue
            normalized = _normalize_ip_entry(value, "ipv6" if name == "ip6" else "ipv4", interface)
            if not normalized:
                continue
            key_tuple = (normalized["interface"], normalized["ip"], normalized["family"])
            if key_tuple not in seen:
                ips.append(normalized)
                seen.add(key_tuple)
    return ips


def _netmask_to_prefix(address: str, netmask: str) -> str:
    if not netmask:
        return str(address)
    try:
        network = ip_network(f"{address}/{netmask}", strict=False)
    except ValueError:
        return str(address)
    return f"{address}/{network.prefixlen}"


async def _get_nodes_raw(connection_id: str = "") -> list[dict]:
    """Internal: returns all Proxmox nodes with status information as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    nodes_basic = proxmox.nodes.get()
    result = []
    for n in nodes_basic:
        node_name = n["node"]
        try:
            status = proxmox.nodes(node_name).status.get()
            mem_info = status.get("memory", {})
            cpu_usage = round(status.get("cpu", 0) * 100, 1)
            mem_total = mem_info.get("total", 0)
            mem_used = mem_info.get("used", 0)
            mem_usage = round(mem_used / max(mem_total, 1) * 100, 1)
        except _PROXMOX_EXCEPTIONS:
            cpu_usage = 0
            mem_total = 0
            mem_used = 0
            mem_usage = 0

        result.append({
            "node": node_name,
            "status": n.get("status", "unknown"),
            "cpu_usage": cpu_usage,
            "mem_total": mem_total,
            "mem_used": mem_used,
            "mem_usage": mem_usage,
            "mem_total_human": _format_bytes(mem_total),
            "mem_used_human": _format_bytes(mem_used),
        })
    return result


@tool
async def get_nodes(connection_id: str = "") -> str:
    """Returns all Proxmox nodes with status information as a Markdown table."""
    nodes = await _get_nodes_raw(connection_id)
    return _format_nodes_as_markdown(nodes)


async def _get_node_status(node: str, connection_id: str = "") -> dict:
    """Internal: returns detailed status of a single node as a dict."""
    proxmox = await _get_proxmox_client(connection_id)
    status = proxmox.nodes(node).status.get()
    return {
        "node": node,
        "cpu_count": status.get("cpuinfo", {}).get("cpus", 0),
        "cpu_model": status.get("cpuinfo", {}).get("model", ""),
        "cpu_usage": round(status.get("cpu", 0) * 100, 1),
        "mem_total": status.get("memory", {}).get("total", 0),
        "mem_used": status.get("memory", {}).get("used", 0),
        "mem_free": status.get("memory", {}).get("free", 0),
        "uptime": status.get("uptime", 0),
        "kernel_version": status.get("kversion", ""),
        "pve_version": status.get("pveversion", ""),
    }


@tool
async def get_node_status(node: str, connection_id: str = "") -> str:
    """Returns detailed status of a single Proxmox node as a formatted Markdown block."""
    data = await _get_node_status(node, connection_id)
    if not data:
        return f"Keine Statusdaten für Node {node} gefunden."
    ram_total = (data.get("mem_total") or 0) / (1024**3)
    ram_used = (data.get("mem_used") or 0) / (1024**3)
    ram_free = (data.get("mem_free") or 0) / (1024**3)
    lines = [
        f"**Node {data.get('node', node)}** — Status: `{data.get('status', 'unknown')}`",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| CPU-Modell | {data.get('cpu_model', '-') or '-'} |",
        f"| CPU-Kerne | {data.get('cpu_count', 0)} |",
        f"| CPU-Auslastung | {float(data.get('cpu_usage') or 0):.1f} % |",
        f"| RAM gesamt | {ram_total:.2f} GB |",
        f"| RAM benutzt | {ram_used:.2f} GB |",
        f"| RAM frei | {ram_free:.2f} GB |",
        f"| Uptime (s) | {data.get('uptime', 0)} |",
        f"| Kernel | {data.get('kernel_version', '-') or '-'} |",
        f"| PVE-Version | {data.get('pve_version', '-') or '-'} |",
    ]
    return "\n".join(lines)


async def _get_node_ip_addresses_raw(node: str, connection_id: str = "") -> list[dict]:
    """Internal: returns configured IP addresses for a Proxmox node as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    interfaces = proxmox.nodes(node).network.get()
    ips = []
    for iface in interfaces:
        address = str(iface.get("address", "")).strip()
        if not address:
            continue
        cidr = _netmask_to_prefix(address, str(iface.get("netmask", "")))
        normalized = _normalize_ip_entry(cidr, "ipv4", str(iface.get("iface", "")))
        if normalized:
            normalized.update(
                {
                    "node": node,
                    "type": iface.get("type", ""),
                    "active": bool(iface.get("active", False)),
                    "gateway": iface.get("gateway", ""),
                }
            )
            ips.append(normalized)
    return ips


@tool
async def get_node_ip_addresses(node: str, connection_id: str = "") -> str:
    """Returns configured IP addresses for a Proxmox node as a Markdown table."""
    ips = await _get_node_ip_addresses_raw(node, connection_id)
    return _format_ips_as_markdown(ips, title=f"IP-Adressen Node {node}")


async def _list_node_ip_addresses_raw(connection_id: str = "") -> list[dict]:
    """Internal: returns configured IP addresses for all Proxmox nodes as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    results = []
    for node_info in proxmox.nodes.get():
        node = node_info["node"]
        try:
            results.extend(
                await _get_node_ip_addresses_raw(node, connection_id)
            )
        except _PROXMOX_EXCEPTIONS as exc:
            logger.warning("Failed to read node IP addresses on %s: %s", node, exc)
    return results


@tool
async def list_node_ip_addresses(connection_id: str = "") -> str:
    """Returns configured IP addresses for all Proxmox nodes as a Markdown table."""
    ips = await _list_node_ip_addresses_raw(connection_id)
    return _format_ips_as_markdown(ips, title="Node-IP-Adressen")


async def _list_all_vms_raw(connection_id: str = "") -> list[dict]:
    """Internal: lists all VMs across all nodes as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    all_vms = []

    for node_info in proxmox.nodes.get():
        node = node_info["node"]

        try:
            vms = proxmox.nodes(node).qemu.get()
            for vm in vms:
                all_vms.append({
                    "vmid": vm["vmid"],
                    "name": vm.get("name", f"VM-{vm['vmid']}"),
                    "node": node,
                    "status": vm.get("status", "unknown"),
                    "type": "qemu",
                    "cpu_usage": round(vm.get("cpu", 0) * 100, 1),
                    "mem_total": vm.get("maxmem", 0),
                    "mem_used": vm.get("mem", 0),
                    "uptime": vm.get("uptime", 0),
                })
        except _PROXMOX_EXCEPTIONS as e:
            logger.warning("Failed to read VMs on %s: %s", node, e)

        try:
            containers = proxmox.nodes(node).lxc.get()
            for ct in containers:
                all_vms.append({
                    "vmid": ct["vmid"],
                    "name": ct.get("name", f"CT-{ct['vmid']}"),
                    "node": node,
                    "status": ct.get("status", "unknown"),
                    "type": "lxc",
                    "cpu_usage": round(ct.get("cpu", 0) * 100, 1),
                    "mem_total": ct.get("maxmem", 0),
                    "mem_used": ct.get("mem", 0),
                    "uptime": ct.get("uptime", 0),
                })
        except _PROXMOX_EXCEPTIONS as e:
            logger.warning("Failed to read containers on %s: %s", node, e)

    return sorted(all_vms, key=lambda x: x["vmid"])


@tool
async def list_all_vms(connection_id: str = "") -> str:
    """Lists all VMs and LXC containers across all nodes as a Markdown table."""
    vms = await _list_all_vms_raw(connection_id)
    return _format_vms_as_markdown(vms, title="VMs & Container")


async def _list_vms_raw(node: str, connection_id: str = "") -> list[dict]:
    """Internal: lists all VMs on a specific node as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    vms = proxmox.nodes(node).qemu.get()
    return [
        {
            "vmid": vm["vmid"],
            "name": vm.get("name", f"VM-{vm['vmid']}"),
            "node": node,
            "status": vm.get("status", "unknown"),
            "type": "qemu",
            "cpu_usage": round(vm.get("cpu", 0) * 100, 1),
            "mem_total": vm.get("maxmem", 0),
            "mem_used": vm.get("mem", 0),
            "uptime": vm.get("uptime", 0),
        }
        for vm in vms
    ]


@tool
async def list_vms(node: str, connection_id: str = "") -> str:
    """Lists all QEMU VMs on a specific node as a Markdown table."""
    vms = await _list_vms_raw(node, connection_id)
    return _format_vms_as_markdown(vms, title=f"VMs auf Node {node}")


async def _get_vm_status_raw(node: str, vmid: int, connection_id: str = "") -> dict:
    """Internal: returns the detailed status of a VM as a dict."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        return {
            "vmid": vmid,
            "name": status.get("name", f"VM-{vmid}"),
            "node": node,
            "status": status.get("status", "unknown"),
            "cpu_usage": round(status.get("cpu", 0) * 100, 1),
            "mem_total": status.get("maxmem", 0),
            "mem_used": status.get("mem", 0),
            "disk_read": status.get("diskread", 0),
            "disk_write": status.get("diskwrite", 0),
            "net_in": status.get("netin", 0),
            "net_out": status.get("netout", 0),
            "uptime": status.get("uptime", 0),
        }
    except _PROXMOX_EXCEPTIONS:
        status = proxmox.nodes(node).lxc(vmid).status.current.get()
        return {
            "vmid": vmid,
            "name": status.get("name", f"CT-{vmid}"),
            "node": node,
            "status": status.get("status", "unknown"),
            "type": "lxc",
            "cpu_usage": round(status.get("cpu", 0) * 100, 1),
            "mem_total": status.get("maxmem", 0),
            "mem_used": status.get("mem", 0),
            "uptime": status.get("uptime", 0),
        }


@tool
async def get_vm_status(node: str, vmid: int, connection_id: str = "") -> str:
    """Returns the detailed status of a VM as a formatted Markdown block."""
    data = await _get_vm_status_raw(node, vmid, connection_id)
    guest_type = data.get("type", "qemu")
    ram_total = (data.get("mem_total") or 0) / (1024**3)
    ram_used = (data.get("mem_used") or 0) / (1024**3)
    lines = [
        f"**{guest_type.upper()} {data.get('vmid', vmid)} ({data.get('name', '-')})** "
        f"auf Node `{data.get('node', node)}` — Status: `{data.get('status', 'unknown')}`",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| CPU-Auslastung | {float(data.get('cpu_usage') or 0):.1f} % |",
        f"| RAM gesamt | {ram_total:.2f} GB |",
        f"| RAM benutzt | {ram_used:.2f} GB |",
    ]
    if "disk_read" in data:
        disk_read_gb = (data.get("disk_read") or 0) / (1024**3)
        disk_write_gb = (data.get("disk_write") or 0) / (1024**3)
        net_in_gb = (data.get("net_in") or 0) / (1024**3)
        net_out_gb = (data.get("net_out") or 0) / (1024**3)
        lines.extend(
            [
                f"| Disk Read | {disk_read_gb:.2f} GB |",
                f"| Disk Write | {disk_write_gb:.2f} GB |",
                f"| Net In | {net_in_gb:.2f} GB |",
                f"| Net Out | {net_out_gb:.2f} GB |",
            ]
        )
    lines.append(f"| Uptime (s) | {data.get('uptime', 0)} |")
    return "\n".join(lines)


async def _get_vm_ip_addresses_raw(node: str, vmid: int, connection_id: str = "") -> dict:
    """Internal: returns IP addresses for a QEMU VM or LXC container as a dict."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        config = proxmox.nodes(node).qemu(vmid).config.get()
    except _PROXMOX_EXCEPTIONS as qemu_exc:
        return await _get_lxc_ip_addresses(proxmox, node, vmid, qemu_exc)

    try:
        agent_data = (
            proxmox.nodes(node).qemu(vmid).agent("network-get-interfaces").get()
        )
        interfaces = agent_data.get("result", agent_data)
        ips = _extract_qemu_agent_ips(
            interfaces if isinstance(interfaces, list) else []
        )
        return {
            "vmid": vmid,
            "name": status.get("name", config.get("name", f"VM-{vmid}")),
            "node": node,
            "type": "qemu",
            "status": status.get("status", "unknown"),
            "ips": ips,
            "source": "qemu_guest_agent",
            "note": "" if ips else "No IPs reported by the QEMU guest agent.",
        }
    except _PROXMOX_EXCEPTIONS as agent_exc:
        ips = _parse_proxmox_net_config(config)
        return {
            "vmid": vmid,
            "name": status.get("name", config.get("name", f"VM-{vmid}")),
            "node": node,
            "type": "qemu",
            "status": status.get("status", "unknown"),
            "ips": ips,
            "source": "qemu_config",
            "note": (
                f"QEMU guest agent did not report interfaces: {agent_exc}. "
                "Enable and run the guest agent inside the VM for live IP discovery."
            ),
        }


@tool
async def get_vm_ip_addresses(node: str, vmid: int, connection_id: str = "") -> str:
    """Returns IP addresses for a QEMU VM or LXC container as a formatted Markdown block."""
    data = await _get_vm_ip_addresses_raw(node, vmid, connection_id)
    return _format_vm_ip_dict_as_markdown(data)


async def _get_lxc_ip_addresses(proxmox: object, node: str, vmid: int, qemu_exc: Exception) -> dict:
    try:
        status = proxmox.nodes(node).lxc(vmid).status.current.get()
        config = proxmox.nodes(node).lxc(vmid).config.get()
    except _PROXMOX_EXCEPTIONS as lxc_exc:
        return {
            "vmid": vmid,
            "node": node,
            "type": "unknown",
            "status": "error",
            "ips": [],
            "source": "",
            "note": f"Could not read VM/LXC IPs. QEMU: {qemu_exc}; LXC: {lxc_exc}",
        }

    try:
        interfaces = proxmox.nodes(node).lxc(vmid).interfaces.get()
        ips = _extract_lxc_interface_ips(interfaces)
        source = "lxc_interfaces"
    except _PROXMOX_EXCEPTIONS:
        ips = []
        source = "lxc_config"

    if not ips:
        ips = _parse_proxmox_net_config(config)
        source = "lxc_config"

    return {
        "vmid": vmid,
        "name": status.get("name", config.get("hostname", f"CT-{vmid}")),
        "node": node,
        "type": "lxc",
        "status": status.get("status", "unknown"),
        "ips": ips,
        "source": source,
        "note": "" if ips else "No IPs reported by the LXC interfaces or config.",
    }


async def _list_vm_ip_addresses_raw(connection_id: str = "") -> list[dict]:
    """Internal: returns IP addresses for all QEMU VMs and LXC containers as a list of dicts."""
    vms = await _list_all_vms_raw(connection_id)
    if not isinstance(vms, list):
        return []
    results = []
    for vm in vms:
        if not isinstance(vm, dict):
            continue
        try:
            result = await _get_vm_ip_addresses_raw(
                node=vm["node"],
                vmid=vm["vmid"],
                connection_id=connection_id,
            )
            if isinstance(result, dict):
                results.append(result)
        except _PROXMOX_EXCEPTIONS as exc:
            logger.warning(
                "Failed to read IP addresses for %s %s on %s: %s",
                vm.get("type", "guest"),
                vm.get("vmid"),
                vm.get("node"),
                exc,
            )
        except (AttributeError, TypeError, KeyError) as exc:
            logger.warning(
                "Unexpected error processing VM entry %r: %s", vm, exc,
            )
    return results


@tool
async def list_vm_ip_addresses(connection_id: str = "") -> str:
    """Returns IP addresses for all QEMU VMs and LXC containers as a Markdown table."""
    ip_entries = await _list_vm_ip_addresses_raw(connection_id)
    if not ip_entries:
        return "Keine VM- oder LXC-IP-Adressen gefunden."
    lines = [
        f"**VM-/LXC-IP-Adressen** ({len(ip_entries)}):",
        "",
        "| VMID | Name | Node | Type | Status | Interface | IP | Familie | Quelle |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for entry in ip_entries:
        ips = entry.get("ips") or []
        if not ips:
            lines.append(
                f"| {entry.get('vmid', '-')} | {entry.get('name', '-')} | "
                f"{entry.get('node', '-')} | {entry.get('type', '-')} | "
                f"{entry.get('status', '-')} | - | - | - | "
                f"{entry.get('source', '-') or '-'} |"
            )
            continue
        for ip in ips:
            lines.append(
                f"| {entry.get('vmid', '-')} | {entry.get('name', '-')} | "
                f"{entry.get('node', '-')} | {entry.get('type', '-')} | "
                f"{entry.get('status', '-')} | "
                f"{ip.get('interface', '-') or '-'} | "
                f"{ip.get('ip') or ip.get('address') or '-'} | "
                f"{ip.get('family', '-')} | "
                f"{entry.get('source', '-') or '-'} |"
            )
    return "\n".join(lines)


@tool
async def start_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Starts a VM. Use for German requests like 'VM starten' or 'starte VM'."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.start.post()
        return {
            "action": "start",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} on node '{node}' is being started.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "start",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def stop_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Graceful ACPI shutdown of a VM.

    Use for 'VM stoppen', 'stoppe VM', or 'VM herunterfahren'.
    """
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.stop.post()
        return {
            "action": "stop",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} is being stopped.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "stop",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def reboot_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Graceful ACPI reboot/restart of a VM.

    Use for 'VM neustarten', 'VM neu starten', or 'VM Neustart'.
    """
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.reboot.post()
        return {
            "action": "reboot",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} is being restarted.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "reboot",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def reset_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Hard power-cut/reset of a VM.

    Use only for 'hart resetten', 'zurücksetzen', 'zuruecksetzen', or forced reset.
    May cause data loss.
    """
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.reset.post()
        return {
            "action": "reset",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} is being reset.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "reset",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def suspend_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Suspends a VM (RAM preserved, execution paused)."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.suspend.post()
        return {
            "action": "suspend",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} has been suspended.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "suspend",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def resume_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Resumes a suspended VM."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.resume.post()
        return {
            "action": "resume",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} has been resumed.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "resume",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


async def _list_containers_raw(node: str, connection_id: str = "") -> list[dict]:
    """Internal: lists all LXC containers on a node as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    containers = proxmox.nodes(node).lxc.get()
    return [
        {
            "vmid": ct["vmid"],
            "name": ct.get("name", f"CT-{ct['vmid']}"),
            "node": node,
            "status": ct.get("status", "unknown"),
            "type": "lxc",
            "cpu_usage": round(ct.get("cpu", 0) * 100, 1),
            "mem_total": ct.get("maxmem", 0),
            "mem_used": ct.get("mem", 0),
        }
        for ct in containers
    ]


@tool
async def list_containers(node: str, connection_id: str = "") -> str:
    """Lists all LXC containers on a node as a Markdown table."""
    containers = await _list_containers_raw(node, connection_id)
    return _format_vms_as_markdown(containers, title=f"LXC-Container auf Node {node}")


@tool
async def start_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Starts an LXC container.

    Use for German requests like 'Container starten' or 'starte Container'.
    """
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.start.post()
        return {
            "action": "start",
            "target": f"CT {vmid}",
            "node": node,
            "status": "success",
            "detail": f"Container {vmid} is being started.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "start",
            "target": f"CT {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def stop_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Graceful shutdown of an LXC container.

    Use for 'Container stoppen', 'stoppe Container', or 'Container herunterfahren'.
    """
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.stop.post()
        return {
            "action": "stop",
            "target": f"CT {vmid}",
            "node": node,
            "status": "success",
            "detail": f"Container {vmid} is being stopped.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "stop",
            "target": f"CT {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def reboot_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Graceful reboot/restart of an LXC container.

    Use for 'Container neustarten', 'Container Neustart', or 'Container neu starten'.
    """
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.reboot.post()
        return {
            "action": "reboot",
            "target": f"CT {vmid}",
            "node": node,
            "status": "success",
            "detail": f"Container {vmid} is being restarted.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "reboot",
            "target": f"CT {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


async def _detect_target_type(proxmox: object, node: str, vmid: int) -> str | None:
    """Erkennt, ob eine VMID ein QEMU-VM ('qemu') oder LXC-Container ('lxc') ist.

    Nutzt die Proxmox cluster-resources API (single source of truth) und
    fällt auf direkten qemu/lxc-Endpoint-Check zurück, wenn die
    cluster-resources API nicht verfügbar ist.

    Returns None wenn weder VM noch LXC gefunden.
    """
    try:
        resources = proxmox.cluster.resources.get(type="vm")
        for r in resources:
            if int(r.get("vmid", -1)) == vmid and r.get("node") == node:
                return "qemu"
    except (*_PROXMOX_EXCEPTIONS, AttributeError):
        pass
    try:
        resources = proxmox.cluster.resources.get(type="lxc")
        for r in resources:
            if int(r.get("vmid", -1)) == vmid and r.get("node") == node:
                return "lxc"
    except (*_PROXMOX_EXCEPTIONS, AttributeError):
        pass

    # Fallback: direkter Endpoint-Probe. Wir versuchen zuerst qemu; wenn
    # das mit 404 endet, probieren wir lxc. Reihenfolge ist egal da
    # Proxmoxer saubere Exceptions wirft.
    try:
        proxmox.nodes(node).qemu(vmid).status.current.get()
        return "qemu"
    except (*_PROXMOX_EXCEPTIONS, AttributeError):
        pass
    try:
        proxmox.nodes(node).lxc(vmid).status.current.get()
        return "lxc"
    except (*_PROXMOX_EXCEPTIONS, AttributeError):
        return None


@tool
async def smart_reboot(node: str, vmid: int, connection_id: str = "") -> dict:
    """Reboot/restart a VM or LXC container, auto-detecting the type.

    Prefer this tool over reboot_vm / reboot_container — it picks the correct
    API endpoint based on whether the VMID belongs to a QEMU VM or an LXC
    container, so the LLM does not have to remember which one it is.
    """
    proxmox = await _get_proxmox_client(connection_id)
    target_type = await _detect_target_type(proxmox, node, vmid)
    if target_type is None:
        return {
            "action": "reboot",
            "target": f"VMID {vmid}",
            "node": node,
            "status": "error",
            "detail": (
                f"VMID {vmid} existiert weder als QEMU-VM noch als LXC-Container "
                f"auf Node '{node}'."
            ),
        }
    if target_type == "qemu":
        target_label = f"VM {vmid}"
        api_call = proxmox.nodes(node).qemu(vmid).status.reboot.post
    else:
        target_label = f"CT {vmid}"
        api_call = proxmox.nodes(node).lxc(vmid).status.reboot.post
    try:
        api_call()
        return {
            "action": "reboot",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "success",
            "detail": f"{target_label} (Node '{node}') wird neugestartet.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "reboot",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def smart_start(node: str, vmid: int, connection_id: str = "") -> dict:
    """Start a VM or LXC container, auto-detecting the type."""
    proxmox = await _get_proxmox_client(connection_id)
    target_type = await _detect_target_type(proxmox, node, vmid)
    if target_type is None:
        return {
            "action": "start",
            "target": f"VMID {vmid}",
            "node": node,
            "status": "error",
            "detail": (
                f"VMID {vmid} existiert weder als QEMU-VM noch als LXC-Container "
                f"auf Node '{node}'."
            ),
        }
    if target_type == "qemu":
        target_label = f"VM {vmid}"
        api_call = proxmox.nodes(node).qemu(vmid).status.start.post
    else:
        target_label = f"CT {vmid}"
        api_call = proxmox.nodes(node).lxc(vmid).status.start.post
    try:
        api_call()
        return {
            "action": "start",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "success",
            "detail": f"{target_label} (Node '{node}') wird gestartet.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "start",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def smart_stop(node: str, vmid: int, connection_id: str = "") -> dict:
    """Stop a VM or LXC container (graceful), auto-detecting the type."""
    proxmox = await _get_proxmox_client(connection_id)
    target_type = await _detect_target_type(proxmox, node, vmid)
    if target_type is None:
        return {
            "action": "stop",
            "target": f"VMID {vmid}",
            "node": node,
            "status": "error",
            "detail": (
                f"VMID {vmid} existiert weder als QEMU-VM noch als LXC-Container "
                f"auf Node '{node}'."
            ),
        }
    if target_type == "qemu":
        target_label = f"VM {vmid}"
        api_call = proxmox.nodes(node).qemu(vmid).status.stop.post
    else:
        target_label = f"CT {vmid}"
        api_call = proxmox.nodes(node).lxc(vmid).status.stop.post
    try:
        api_call()
        return {
            "action": "stop",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "success",
            "detail": f"{target_label} (Node '{node}') wird heruntergefahren.",
        }
    except _PROXMOX_EXCEPTIONS as e:
        return {
            "action": "stop",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "error",
            "detail": str(e),
        }


async def _get_recent_tasks_raw(node: str, connection_id: str = "") -> list[dict]:
    """Internal: returns the recent tasks of a node as a list of dicts."""
    proxmox = await _get_proxmox_client(connection_id)
    tasks = proxmox.nodes(node).tasks.get(limit=20)
    return [
        {
            "upid": t.get("upid", ""),
            "type": t.get("type", ""),
            "status": t.get("status", ""),
            "node": node,
            "user": t.get("user", ""),
            "starttime": t.get("starttime", 0),
            "endtime": t.get("endtime", 0),
        }
        for t in tasks
    ]


@tool
async def get_recent_tasks(node: str, connection_id: str = "") -> str:
    """Returns the recent tasks of a node as a Markdown table."""
    tasks = await _get_recent_tasks_raw(node, connection_id)
    if not tasks:
        return f"Keine aktuellen Tasks auf Node {node} gefunden."
    lines = [
        f"**Letzte Tasks auf Node {node}** ({len(tasks)}):",
        "",
        "| Type | Status | User | Start | End |",
        "|---|---|---|---|---|",
    ]
    from datetime import datetime, timezone

    for t in tasks:
        start = t.get("starttime", 0)
        end = t.get("endtime", 0)
        try:
            start_str = (
                datetime.fromtimestamp(start, tz=timezone.utc).isoformat()
                if start
                else "-"
            )
        except (TypeError, ValueError, OSError):
            start_str = "-"
        try:
            end_str = (
                datetime.fromtimestamp(end, tz=timezone.utc).isoformat()
                if end
                else "-"
            )
        except (TypeError, ValueError, OSError):
            end_str = "-"
        lines.append(
            f"| {t.get('type', '-')} | {t.get('status', '-')} | "
            f"{t.get('user', '-')} | {start_str} | {end_str} |"
        )
    return "\n".join(lines)


async def _get_vm_config_raw(node: str, vmid: int, connection_id: str = "") -> dict:
    """Internal: returns the configuration of a VM as a dict."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        config = proxmox.nodes(node).qemu(vmid).config.get()
        networks = {
            key: value
            for key, value in sorted(config.items())
            if str(key).startswith("net")
        }
        return {
            "vmid": vmid,
            "node": node,
            "type": "qemu",
            "name": config.get("name", ""),
            "cores": config.get("cores", 0),
            "sockets": config.get("sockets", 1),
            "memory": config.get("memory", 0),
            "balloon": config.get("balloon", 0),
            "boot": config.get("boot", ""),
            "ostype": config.get("ostype", ""),
            "scsihw": config.get("scsihw", ""),
            "net0": config.get("net0", ""),
            "networks": networks,
            "ip_hints": _parse_proxmox_net_config(config),
        }
    except _PROXMOX_EXCEPTIONS:
        config = proxmox.nodes(node).lxc(vmid).config.get()
        networks = {
            key: value
            for key, value in sorted(config.items())
            if str(key).startswith("net")
        }
        return {
            "vmid": vmid,
            "node": node,
            "type": "lxc",
            "hostname": config.get("hostname", ""),
            "cores": config.get("cores", 0),
            "memory": config.get("memory", 0),
            "swap": config.get("swap", 0),
            "rootfs": config.get("rootfs", ""),
            "net0": config.get("net0", ""),
            "networks": networks,
            "ip_hints": _parse_proxmox_net_config(config),
        }


@tool
async def get_vm_config(node: str, vmid: int, connection_id: str = "") -> str:
    """Returns the configuration of a VM as a formatted Markdown block."""
    data = await _get_vm_config_raw(node, vmid, connection_id)
    guest_type = data.get("type", "qemu")
    lines = [
        f"**Konfiguration {guest_type.upper()} {data.get('vmid', vmid)}** "
        f"auf Node `{data.get('node', node)}`",
        "",
        "| Property | Value |",
        "|---|---|",
    ]
    for key, value in data.items():
        if key in ("vmid", "node", "type", "networks", "ip_hints"):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str, ensure_ascii=False)
        lines.append(f"| {key} | {value} |")
    networks = data.get("networks") or {}
    if networks:
        lines.extend(
            [
                "",
                "**Netzwerk-Interfaces:**",
                "",
                "| Key | Config |",
                "|---|---|",
            ]
        )
        for k, v in networks.items():
            lines.append(f"| {k} | {v} |")
    ip_hints = data.get("ip_hints") or []
    if ip_hints:
        lines.extend(
            [
                "",
                "**Statische IP-Hints:**",
                "",
                "| Interface | IP | Familie |",
                "|---|---|---|",
            ]
        )
        for ip in ip_hints:
            lines.append(
                f"| {ip.get('interface', '-') or '-'} | "
                f"{ip.get('ip') or ip.get('address') or '-'} | "
                f"{ip.get('family', '-')} |"
            )
    return "\n".join(lines)
