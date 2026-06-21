"""
Proxmox module — LangGraph @tool functions.
Full implementation using proxmoxer.
"""

from __future__ import annotations

import logging
from ipaddress import ip_address, ip_network

from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.proxmox.tools")


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


@tool
async def get_nodes(connection_id: str = "") -> list[dict]:
    """Returns all Proxmox nodes with status information."""
    proxmox = await _get_proxmox_client(connection_id)
    nodes_basic = proxmox.nodes.get()
    result = []
    for n in nodes_basic:
        node_name = n["node"]
        # Load detailed status (CPU, RAM, etc.)
        try:
            status = proxmox.nodes(node_name).status.get()
            mem_info = status.get("memory", {})
            cpu_usage = round(status.get("cpu", 0) * 100, 1)
            mem_total = mem_info.get("total", 0)
            mem_used = mem_info.get("used", 0)
            mem_usage = round(mem_used / max(mem_total, 1) * 100, 1)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError):
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
async def get_node_status(node: str, connection_id: str = "") -> dict:
    """Returns detailed status of a single node."""
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
async def get_node_ip_addresses(node: str, connection_id: str = "") -> list[dict]:
    """Returns configured IP addresses for a Proxmox node."""
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
async def list_node_ip_addresses(connection_id: str = "") -> list[dict]:
    """Returns configured IP addresses for all Proxmox nodes."""
    proxmox = await _get_proxmox_client(connection_id)
    results = []
    for node_info in proxmox.nodes.get():
        node = node_info["node"]
        try:
            results.extend(
                await get_node_ip_addresses.ainvoke(
                    {"node": node, "connection_id": connection_id}
                )
            )
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.warning("Failed to read node IP addresses on %s: %s", node, exc)
    return results


@tool
async def list_all_vms(connection_id: str = "") -> list[dict]:
    """Lists all VMs across all nodes."""
    proxmox = await _get_proxmox_client(connection_id)
    all_vms = []

    for node_info in proxmox.nodes.get():
        node = node_info["node"]

        # QEMU VMs
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
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
            logger.warning("Failed to read VMs on %s: %s", node, e)

        # LXC Container
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
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
            logger.warning("Failed to read containers on %s: %s", node, e)

    return sorted(all_vms, key=lambda x: x["vmid"])


@tool
async def list_vms(node: str, connection_id: str = "") -> list[dict]:
    """Lists all VMs on a specific node."""
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
async def get_vm_status(node: str, vmid: int, connection_id: str = "") -> dict:
    """Returns the detailed status of a VM."""
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
        # Maybe it's an LXC container
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
async def get_vm_ip_addresses(node: str, vmid: int, connection_id: str = "") -> dict:
    """Returns IP addresses for a QEMU VM or LXC container."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        status = proxmox.nodes(node).qemu(vmid).status.current.get()
        config = proxmox.nodes(node).qemu(vmid).config.get()
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as qemu_exc:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as agent_exc:
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


async def _get_lxc_ip_addresses(proxmox: object, node: str, vmid: int, qemu_exc: Exception) -> dict:
    try:
        status = proxmox.nodes(node).lxc(vmid).status.current.get()
        config = proxmox.nodes(node).lxc(vmid).config.get()
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as lxc_exc:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
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


@tool
async def list_vm_ip_addresses(connection_id: str = "") -> list[dict]:
    """Returns IP addresses for all QEMU VMs and LXC containers across all nodes."""
    vms = await list_all_vms.ainvoke({"connection_id": connection_id})
    results = []
    for vm in vms:
        try:
            results.append(
                await get_vm_ip_addresses.ainvoke(
                    {
                        "node": vm["node"],
                        "vmid": vm["vmid"],
                        "connection_id": connection_id,
                    }
                )
            )
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.warning(
                "Failed to read IP addresses for %s %s on %s: %s",
                vm.get("type", "guest"),
                vm.get("vmid"),
                vm.get("node"),
                exc,
            )
    return results


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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        return {
            "action": "resume",
            "target": f"VM {vmid}",
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def list_containers(node: str, connection_id: str = "") -> list[dict]:
    """Lists all LXC containers on a node."""
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, AttributeError):
        pass
    try:
        resources = proxmox.cluster.resources.get(type="lxc")
        for r in resources:
            if int(r.get("vmid", -1)) == vmid and r.get("node") == node:
                return "lxc"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, AttributeError):
        pass

    # Fallback: direkter Endpoint-Probe. Wir versuchen zuerst qemu; wenn
    # das mit 404 endet, probieren wir lxc. Reihenfolge ist egal da
    # Proxmoxer saubere Exceptions wirft.
    try:
        proxmox.nodes(node).qemu(vmid).status.current.get()
        return "qemu"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, AttributeError):
        pass
    try:
        proxmox.nodes(node).lxc(vmid).status.current.get()
        return "lxc"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, AttributeError):
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        return {
            "action": "stop",
            "target": target_label,
            "target_type": target_type,
            "node": node,
            "status": "error",
            "detail": str(e),
        }


@tool
async def get_recent_tasks(node: str, connection_id: str = "") -> list[dict]:
    """Returns the recent tasks of a node."""
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
async def get_vm_config(node: str, vmid: int, connection_id: str = "") -> dict:
    """Returns the configuration of a VM."""
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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
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
