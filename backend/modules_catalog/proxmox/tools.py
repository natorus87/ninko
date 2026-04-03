"""
Proxmox module — LangGraph @tool functions.
Full implementation using proxmoxer.
"""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.proxmox.tools")


async def _get_proxmox_client(connection_id: str = ""):
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

        # Test call: detect SSL errors early and retry without verification
        if verify_ssl:
            try:
                px.version.get()
            except Exception as e:
                err_str = str(e).lower()
                if "ssl" in err_str or "certificate" in err_str:
                    logger.warning("SSL verification failed, retrying without verify_ssl")
                    px = ProxmoxAPI(
                        host_addr,
                        port=8006,
                        user=base_user,
                        token_name=token_id,
                        token_value=token_secret,
                        verify_ssl=False,
                    )

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
            cpu_info = status.get("cpuinfo", {})
            mem_info = status.get("memory", {})
            cpu_usage = round(status.get("cpu", 0) * 100, 1)
            mem_total = mem_info.get("total", 0)
            mem_used = mem_info.get("used", 0)
            mem_usage = round(mem_used / max(mem_total, 1) * 100, 1)
        except Exception:
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
        except Exception as e:
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
        except Exception as e:
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
    except Exception:
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
async def start_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Starts a VM."""
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
    except Exception as e:
        return {"action": "start", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def stop_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Stops a VM (DESTRUCTIVE — requires confirmation)."""
    confirm = os.environ.get("PROXMOX_CONFIRM_DESTRUCTIVE", "true").lower()
    if confirm == "true":
        return {
            "action": "stop",
            "target": f"VM {vmid}",
            "node": node,
            "status": "confirmation_required",
            "detail": f"Should VM {vmid} on node '{node}' really be stopped? Please confirm with 'Yes'.",
        }

    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.stop.post()
        return {"action": "stop", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} is being stopped."}
    except Exception as e:
        return {"action": "stop", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def reboot_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Restarts a VM (reboot)."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.reboot.post()
        return {"action": "reboot", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} is being restarted."}
    except Exception as e:
        return {"action": "reboot", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def reset_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Hard-reset of a VM (DESTRUCTIVE — requires confirmation)."""
    confirm = os.environ.get("PROXMOX_CONFIRM_DESTRUCTIVE", "true").lower()
    if confirm == "true":
        return {
            "action": "reset",
            "target": f"VM {vmid}",
            "node": node,
            "status": "confirmation_required",
            "detail": f"Hard-reset VM {vmid} on node '{node}'? This may cause data loss! Confirm with 'Yes'.",
        }

    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.reset.post()
        return {"action": "reset", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} is being reset."}
    except Exception as e:
        return {"action": "reset", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def suspend_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Suspends a VM."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.suspend.post()
        return {"action": "suspend", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} has been suspended."}
    except Exception as e:
        return {"action": "suspend", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def resume_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Resumes a suspended VM."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.resume.post()
        return {"action": "resume", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} has been resumed."}
    except Exception as e:
        return {"action": "resume", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


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
    """Starts an LXC container."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.start.post()
        return {"action": "start", "target": f"CT {vmid}", "node": node, "status": "success", "detail": f"Container {vmid} is being started."}
    except Exception as e:
        return {"action": "start", "target": f"CT {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def stop_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Stops an LXC container (DESTRUCTIVE)."""
    confirm = os.environ.get("PROXMOX_CONFIRM_DESTRUCTIVE", "true").lower()
    if confirm == "true":
        return {
            "action": "stop",
            "target": f"CT {vmid}",
            "node": node,
            "status": "confirmation_required",
            "detail": f"Stop container {vmid} on node '{node}'? Confirm with 'Yes'.",
        }

    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.stop.post()
        return {"action": "stop", "target": f"CT {vmid}", "node": node, "status": "success", "detail": f"Container {vmid} is being stopped."}
    except Exception as e:
        return {"action": "stop", "target": f"CT {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def reboot_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Restarts an LXC container."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.reboot.post()
        return {"action": "reboot", "target": f"CT {vmid}", "node": node, "status": "success", "detail": f"Container {vmid} is being restarted."}
    except Exception as e:
        return {"action": "reboot", "target": f"CT {vmid}", "node": node, "status": "error", "detail": str(e)}


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
        return {
            "vmid": vmid,
            "node": node,
            "name": config.get("name", ""),
            "cores": config.get("cores", 0),
            "sockets": config.get("sockets", 1),
            "memory": config.get("memory", 0),
            "balloon": config.get("balloon", 0),
            "boot": config.get("boot", ""),
            "ostype": config.get("ostype", ""),
            "scsihw": config.get("scsihw", ""),
            "net0": config.get("net0", ""),
        }
    except Exception:
        config = proxmox.nodes(node).lxc(vmid).config.get()
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
        }
