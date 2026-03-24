"""
Docker Modul – LangGraph @tool-Funktionen.
Verwaltet Docker-Hosts über die Docker Engine REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("kumio.modules.docker.tools")


def _format_bytes(b: int | float) -> str:
    """Formatiert Bytes in lesbare Größe."""
    b = float(b)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


async def _get_docker_client(connection_id: str = "") -> dict:
    """
    Erstellt Docker API Connection-Config aus dem ConnectionManager.
    Gibt dict mit base_url und optionalen TLS/Auth-Parametern zurück.
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("docker", connection_id)
        if not conn:
            raise ValueError(f"Docker-Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("docker")
        if not conn:
            # Fallback auf Env-Variablen
            host = os.environ.get("DOCKER_HOST", "localhost")
            port = os.environ.get("DOCKER_PORT", "2375")
            use_tls = os.environ.get("DOCKER_TLS", "false").lower() == "true"
            api_version = os.environ.get("DOCKER_API_VERSION", "")
            scheme = "https" if use_tls else "http"
            base_url = f"{scheme}://{host}:{port}"
            if api_version:
                base_url = f"{base_url}/v{api_version}"
            return {"base_url": base_url, "headers": {}}

    host = conn.config.get("host", os.environ.get("DOCKER_HOST", "localhost"))
    port = conn.config.get("port", os.environ.get("DOCKER_PORT", "2375"))
    use_tls = conn.config.get("tls", os.environ.get("DOCKER_TLS", "false")).lower() == "true"
    api_version = conn.config.get("api_version", os.environ.get("DOCKER_API_VERSION", ""))

    scheme = "https" if use_tls else "http"
    base_url = f"{scheme}://{host}:{port}"
    if api_version:
        base_url = f"{base_url}/v{api_version}"

    # Optional: TLS-Zertifikate aus Vault
    headers = {}
    vault = get_vault()

    cert_path = conn.vault_keys.get("DOCKER_TLS_CERT")
    key_path = conn.vault_keys.get("DOCKER_TLS_KEY")

    tls_config = None
    if cert_path and key_path:
        cert = await vault.get_secret(cert_path)
        key = await vault.get_secret(key_path)
        if cert and key:
            tls_config = (cert, key)

    return {"base_url": base_url, "headers": headers, "tls": tls_config}


async def _docker_api(method: str, path: str, connection_id: str = "", json_body: dict | None = None, params: dict | None = None) -> Any:
    """Führt einen Docker Engine API-Aufruf durch."""
    client_cfg = await _get_docker_client(connection_id)
    base_url = client_cfg["base_url"]
    headers = client_cfg.get("headers", {})
    tls = client_cfg.get("tls")

    verify = True
    cert = None
    if tls:
        verify = False
        cert = tls

    url = f"{base_url}{path}"

    async with httpx.AsyncClient(verify=verify, cert=cert, timeout=30) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers, params=params)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=json_body, params=params)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if resp.status_code >= 400:
            raise RuntimeError(f"Docker API Error {resp.status_code}: {resp.text[:500]}")

        if resp.status_code == 204:
            return {"status": "success"}

        return resp.json()


# ═══════════════════════════════════════════════════════
# Container Tools
# ═══════════════════════════════════════════════════════

@tool
async def list_containers(all: bool = True, connection_id: str = "") -> list[dict]:
    """
    Listet alle Docker-Container auf dem Host auf.
    Setze all=true für alle Container (auch gestoppte), all=false nur laufende.
    """
    params = {"all": 1 if all else 0, "size": 1}
    containers = await _docker_api("GET", "/containers/json", connection_id, params=params)
    return [
        {
            "id": c["Id"][:12],
            "name": c.get("Names", [""])[0].lstrip("/"),
            "image": c.get("Image", ""),
            "status": c.get("Status", ""),
            "state": c.get("State", ""),
            "ports": c.get("Ports", []),
            "created": c.get("Created", 0),
            "size_rw": c.get("SizeRw", 0),
            "size_root_fs": c.get("SizeRootFs", 0),
        }
        for c in containers
    ]


@tool
async def inspect_container(container_id: str, connection_id: str = "") -> dict:
    """
    Gibt detaillierte Informationen über einen Container zurück.
    container_id kann der Name oder die ID des Containers sein.
    """
    data = await _docker_api("GET", f"/containers/{container_id}/json", connection_id)
    return {
        "id": data["Id"][:12],
        "name": data["Name"].lstrip("/"),
        "image": data.get("Config", {}).get("Image", ""),
        "state": data.get("State", {}),
        "network_settings": data.get("NetworkSettings", {}).get("Networks", {}),
        "mounts": [
            {"source": m.get("Source", ""), "destination": m.get("Destination", ""), "type": m.get("Type", "")}
            for m in data.get("Mounts", [])
        ],
        "env": data.get("Config", {}).get("Env", []),
        "cmd": data.get("Config", {}).get("Cmd", []),
        "created": data.get("Created", ""),
        "platform": data.get("Platform", ""),
    }


@tool
async def start_container(container_id: str, connection_id: str = "") -> dict:
    """Startet einen Docker-Container."""
    result = await _docker_api("POST", f"/containers/{container_id}/start", connection_id)
    return {"action": "start", "target": container_id, "status": "success", "detail": f"Container {container_id} wird gestartet."}


@tool
async def stop_container(container_id: str, timeout: int = 10, connection_id: str = "") -> dict:
    """Stoppt einen Docker-Container. timeout gibt die Wartezeit in Sekunden vor dem SIGKILL an."""
    result = await _docker_api("POST", f"/containers/{container_id}/stop", connection_id, params={"t": timeout})
    return {"action": "stop", "target": container_id, "status": "success", "detail": f"Container {container_id} wird gestoppt."}


@tool
async def restart_container(container_id: str, timeout: int = 10, connection_id: str = "") -> dict:
    """Startet einen Docker-Container neu."""
    result = await _docker_api("POST", f"/containers/{container_id}/restart", connection_id, params={"t": timeout})
    return {"action": "restart", "target": container_id, "status": "success", "detail": f"Container {container_id} wird neu gestartet."}


@tool
async def remove_container(container_id: str, force: bool = False, connection_id: str = "") -> dict:
    """Entfernt einen Docker-Container. Bei force=true wird ein laufender Container erzwungen gestoppt."""
    params = {"force": 1 if force else 0, "v": 1}
    result = await _docker_api("DELETE", f"/containers/{container_id}", connection_id, params=params)
    return {"action": "remove", "target": container_id, "status": "success", "detail": f"Container {container_id} wurde entfernt."}


@tool
async def get_container_logs(container_id: str, tail: int = 100, connection_id: str = "") -> str:
    """
    Gibt die Logs eines Containers zurück.
    tail gibt an, wie viele Zeilen von Ende angezeigt werden sollen.
    """
    params = {"stdout": 1, "stderr": 1, "tail": tail, "timestamps": 1}
    client_cfg = await _get_docker_client(connection_id)
    base_url = client_cfg["base_url"]
    headers = client_cfg.get("headers", {})
    tls = client_cfg.get("tls")

    verify = True
    cert = None
    if tls:
        verify = False
        cert = tls

    url = f"{base_url}/containers/{container_id}/logs"
    async with httpx.AsyncClient(verify=verify, cert=cert, timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"Docker API Error {resp.status_code}: {resp.text[:500]}")
        return resp.text


@tool
async def get_container_stats(container_id: str, connection_id: str = "") -> dict:
    """Gibt aktuelle Ressourcen-Statistiken (CPU, RAM, Netzwerk, Disk) eines laufenden Containers zurück."""
    params = {"stream": 0}
    stats = await _docker_api("GET", f"/containers/{container_id}/stats", connection_id, params=params)

    cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
    system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
    cpu_percent = 0.0
    if system_delta > 0:
        cpu_percent = (cpu_delta / system_delta) * len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])) * 100.0

    mem_usage = stats["memory_stats"].get("usage", 0)
    mem_limit = stats["memory_stats"].get("limit", 1)
    mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0

    net_rx = 0
    net_tx = 0
    for net_name, net_stats in stats.get("networks", {}).items():
        net_rx += net_stats.get("rx_bytes", 0)
        net_tx += net_stats.get("tx_bytes", 0)

    return {
        "container": container_id,
        "cpu_percent": round(cpu_percent, 2),
        "memory_usage": _format_bytes(mem_usage),
        "memory_limit": _format_bytes(mem_limit),
        "memory_percent": round(mem_percent, 2),
        "network_rx": _format_bytes(net_rx),
        "network_tx": _format_bytes(net_tx),
    }


# ═══════════════════════════════════════════════════════
# Image Tools
# ═══════════════════════════════════════════════════════

@tool
async def list_images(all: bool = False, connection_id: str = "") -> list[dict]:
    """Listet alle Docker-Images auf dem Host auf."""
    params = {"all": 1 if all else 0}
    images = await _docker_api("GET", "/images/json", connection_id, params=params)
    return [
        {
            "id": img["Id"].replace("sha256:", "")[:12],
            "tags": img.get("RepoTags", []),
            "size": _format_bytes(img.get("Size", 0)),
            "created": img.get("Created", 0),
        }
        for img in images
    ]


@tool
async def pull_image(image_name: str, tag: str = "latest", connection_id: str = "") -> dict:
    """
    Lädt ein Image von Docker Hub oder einer Registry herunter.
    Beispiel: image_name='nginx', tag='latest'
    """
    params = {"fromImage": image_name, "tag": tag}
    result = await _docker_api("POST", "/images/create", connection_id, params=params)
    return {"action": "pull", "image": f"{image_name}:{tag}", "status": "success", "detail": f"Image {image_name}:{tag} wurde heruntergeladen."}


@tool
async def remove_image(image_id: str, force: bool = False, connection_id: str = "") -> dict:
    """Entfernt ein Docker-Image. Bei force=true werden auch verwendete Images entfernt."""
    params = {"force": 1 if force else 0}
    result = await _docker_api("DELETE", f"/images/{image_id}", connection_id, params=params)
    return {"action": "remove", "target": image_id, "status": "success", "detail": f"Image {image_id} wurde entfernt."}


# ═══════════════════════════════════════════════════════
# Volume Tools
# ═══════════════════════════════════════════════════════

@tool
async def list_volumes(connection_id: str = "") -> list[dict]:
    """Listet alle Docker-Volumes auf dem Host auf."""
    data = await _docker_api("GET", "/volumes", connection_id)
    return [
        {
            "name": v.get("Name", ""),
            "driver": v.get("Driver", ""),
            "mountpoint": v.get("Mountpoint", ""),
            "created": v.get("CreatedAt", ""),
            "size": v.get("Size", ""),
            "labels": v.get("Labels", {}),
        }
        for v in data.get("Volumes", [])
    ]


@tool
async def remove_volume(volume_name: str, force: bool = False, connection_id: str = "") -> dict:
    """Entfernt ein Docker-Volume."""
    params = {"force": 1 if force else 0}
    result = await _docker_api("DELETE", f"/volumes/{volume_name}", connection_id, params=params)
    return {"action": "remove", "target": volume_name, "status": "success", "detail": f"Volume {volume_name} wurde entfernt."}


# ═══════════════════════════════════════════════════════
# System Tools
# ═══════════════════════════════════════════════════════

@tool
async def get_docker_info(connection_id: str = "") -> dict:
    """Gibt System-Informationen über den Docker-Host zurück (Anzahl Container, Images, Ressourcen)."""
    info = await _docker_api("GET", "/info", connection_id)
    return {
        "containers_running": info.get("ContainersRunning", 0),
        "containers_paused": info.get("ContainersPaused", 0),
        "containers_stopped": info.get("ContainersStopped", 0),
        "images_count": info.get("Images", 0),
        "docker_version": info.get("ServerVersion", ""),
        "os": info.get("OperatingSystem", ""),
        "kernel": info.get("KernelVersion", ""),
        "total_memory": _format_bytes(info.get("MemTotal", 0)),
        "cpus": info.get("NCPU", 0),
        "storage_driver": info.get("Driver", ""),
    }


@tool
async def get_docker_version(connection_id: str = "") -> dict:
    """Gibt die Docker Engine Version und API-Version zurück."""
    version = await _docker_api("GET", "/version", connection_id)
    return {
        "version": version.get("Version", ""),
        "api_version": version.get("ApiVersion", ""),
        "min_api_version": version.get("MinAPIVersion", ""),
        "os": version.get("Os", ""),
        "arch": version.get("Arch", ""),
        "kernel": version.get("KernelVersion", ""),
        "build_time": version.get("BuildTime", ""),
    }


@tool
async def get_docker_disk_usage(connection_id: str = "") -> dict:
    """Gibt die Speicherauslastung des Docker-Systems zurück (Images, Container, Volumes, Build Cache)."""
    data = await _docker_api("GET", "/system/df", connection_id)
    return {
        "images": {
            "count": len(data.get("Images", [])),
            "size": _format_bytes(sum(img.get("Size", 0) for img in data.get("Images", []))),
        },
        "containers": {
            "count": len(data.get("Containers", [])),
            "size": _format_bytes(sum(c.get("SizeRw", 0) for c in data.get("Containers", []))),
        },
        "volumes": {
            "count": len(data.get("Volumes", [])),
            "size": _format_bytes(sum(v.get("UsageData", {}).get("Size", 0) for v in data.get("Volumes", []))),
        },
        "build_cache": {
            "count": len(data.get("BuildCache", [])),
        },
    }
