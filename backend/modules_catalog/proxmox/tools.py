"""
Proxmox Modul – LangGraph @tool-Funktionen.
Vollständige Implementierung mit proxmoxer.
"""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.proxmox.tools")


async def _get_proxmox_client(connection_id: str = ""):
    """Erstellt eine authentifizierte Proxmox-API-Verbindung basierend auf ConnectionManager."""
    from proxmoxer import ProxmoxAPI
    from core.vault import get_vault
    from core.connections import ConnectionManager

    if connection_id:
        conn = await ConnectionManager.get_connection("proxmox", connection_id)
        if not conn:
            raise ValueError(f"Proxmox Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("proxmox")
        if not conn:
            raise ValueError("Keine Standard-Proxmox-Verbindung konfiguriert.")

    vault = get_vault()

    host = conn.config.get("host", "")
    user = conn.config.get("user", "root@pam")
    token_id = conn.config.get("token_id", "")
    verify_ssl = conn.config.get("verify_ssl", "false").lower() == "true"

    # Token-ID aus User-Feld extrahieren falls nicht explizit gespeichert
    # (User-Feld könnte "root@pam!Ninko" enthalten → token_id = "Ninko")
    if not token_id and "!" in user:
        token_id = user.split("!", 1)[1]

    # Hole Secret aus Vault anhand der gespeicherten Keys
    token_secret = None
    if "token_secret" in conn.vault_keys:
        token_secret = await vault.get_secret(conn.vault_keys["token_secret"])

    if token_secret and token_id:
        # User-Feld bereinigen: falls "!token" angehängt ist, entfernen
        # (proxmoxer baut selbst "user!token_name" zusammen)
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

        # Test-Call: SSL-Fehler früh erkennen und ohne Verifikation neu starten
        if verify_ssl:
            try:
                px.version.get()
            except Exception as e:
                err_str = str(e).lower()
                if "ssl" in err_str or "certificate" in err_str:
                    logger.warning("SSL-Verifikation fehlgeschlagen, retry ohne verify_ssl")
                    px = ProxmoxAPI(
                        host_addr,
                        port=8006,
                        user=base_user,
                        token_name=token_id,
                        token_value=token_secret,
                        verify_ssl=False,
                    )

        return px

    # Fallback: Passwort
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

    raise ValueError(f"Keine validen Anmeldedaten für Proxmox-Verbindung '{conn.name}' gefunden.")


def _format_bytes(b: int) -> str:
    """Formatiert Bytes in lesbare Größe."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


@tool
async def get_nodes(connection_id: str = "") -> list[dict]:
    """Gibt alle Proxmox-Nodes mit Status-Informationen zurück."""
    proxmox = await _get_proxmox_client(connection_id)
    nodes_basic = proxmox.nodes.get()
    result = []
    for n in nodes_basic:
        node_name = n["node"]
        # Detail-Status laden (CPU, RAM, etc.)
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
    """Gibt detaillierten Status eines einzelnen Nodes zurück."""
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
    """Listet alle VMs auf allen Nodes auf."""
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
            logger.warning("Fehler beim Lesen der VMs auf %s: %s", node, e)

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
            logger.warning("Fehler beim Lesen der Container auf %s: %s", node, e)

    return sorted(all_vms, key=lambda x: x["vmid"])


@tool
async def list_vms(node: str, connection_id: str = "") -> list[dict]:
    """Listet alle VMs auf einem bestimmten Node auf."""
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
    """Gibt den detaillierten Status einer VM zurück."""
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
        # Vielleicht LXC
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
    """Startet eine VM."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.start.post()
        return {
            "action": "start",
            "target": f"VM {vmid}",
            "node": node,
            "status": "success",
            "detail": f"VM {vmid} auf Node '{node}' wird gestartet.",
        }
    except Exception as e:
        return {"action": "start", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def stop_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Stoppt eine VM (DESTRUKTIV – erfordert Bestätigung)."""
    confirm = os.environ.get("PROXMOX_CONFIRM_DESTRUCTIVE", "true").lower()
    if confirm == "true":
        return {
            "action": "stop",
            "target": f"VM {vmid}",
            "node": node,
            "status": "confirmation_required",
            "detail": f"Soll VM {vmid} auf Node '{node}' wirklich gestoppt werden? Bitte bestätige mit 'Ja'.",
        }

    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.stop.post()
        return {"action": "stop", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} wird gestoppt."}
    except Exception as e:
        return {"action": "stop", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def reboot_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Startet eine VM neu (Reboot)."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.reboot.post()
        return {"action": "reboot", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} wird neu gestartet."}
    except Exception as e:
        return {"action": "reboot", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def reset_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Hard-Reset einer VM (DESTRUKTIV – erfordert Bestätigung)."""
    confirm = os.environ.get("PROXMOX_CONFIRM_DESTRUCTIVE", "true").lower()
    if confirm == "true":
        return {
            "action": "reset",
            "target": f"VM {vmid}",
            "node": node,
            "status": "confirmation_required",
            "detail": f"Hard-Reset für VM {vmid} auf Node '{node}'? Dies kann zu Datenverlust führen! Bestätige mit 'Ja'.",
        }

    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.reset.post()
        return {"action": "reset", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} wird zurückgesetzt."}
    except Exception as e:
        return {"action": "reset", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def suspend_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Suspendiert eine VM."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.suspend.post()
        return {"action": "suspend", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} wurde suspendiert."}
    except Exception as e:
        return {"action": "suspend", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def resume_vm(node: str, vmid: int, connection_id: str = "") -> dict:
    """Setzt eine suspendierte VM fort."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).qemu(vmid).status.resume.post()
        return {"action": "resume", "target": f"VM {vmid}", "node": node, "status": "success", "detail": f"VM {vmid} wurde fortgesetzt."}
    except Exception as e:
        return {"action": "resume", "target": f"VM {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def list_containers(node: str, connection_id: str = "") -> list[dict]:
    """Listet alle LXC-Container auf einem Node auf."""
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
    """Startet einen LXC-Container."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.start.post()
        return {"action": "start", "target": f"CT {vmid}", "node": node, "status": "success", "detail": f"Container {vmid} wird gestartet."}
    except Exception as e:
        return {"action": "start", "target": f"CT {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def stop_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Stoppt einen LXC-Container (DESTRUKTIV)."""
    confirm = os.environ.get("PROXMOX_CONFIRM_DESTRUCTIVE", "true").lower()
    if confirm == "true":
        return {
            "action": "stop",
            "target": f"CT {vmid}",
            "node": node,
            "status": "confirmation_required",
            "detail": f"Container {vmid} auf Node '{node}' stoppen? Bestätige mit 'Ja'.",
        }

    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.stop.post()
        return {"action": "stop", "target": f"CT {vmid}", "node": node, "status": "success", "detail": f"Container {vmid} wird gestoppt."}
    except Exception as e:
        return {"action": "stop", "target": f"CT {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def reboot_container(node: str, vmid: int, connection_id: str = "") -> dict:
    """Startet einen LXC-Container neu."""
    proxmox = await _get_proxmox_client(connection_id)
    try:
        proxmox.nodes(node).lxc(vmid).status.reboot.post()
        return {"action": "reboot", "target": f"CT {vmid}", "node": node, "status": "success", "detail": f"Container {vmid} wird neu gestartet."}
    except Exception as e:
        return {"action": "reboot", "target": f"CT {vmid}", "node": node, "status": "error", "detail": str(e)}


@tool
async def get_recent_tasks(node: str, connection_id: str = "") -> list[dict]:
    """Gibt die letzten Tasks eines Nodes zurück."""
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
    """Gibt die Konfiguration einer VM zurück."""
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
