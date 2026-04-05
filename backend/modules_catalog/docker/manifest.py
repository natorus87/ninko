"""
Docker Module — Manifest with metadata and health check.
Manages Docker hosts via the Docker Engine API.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.docker")


async def check_docker_health() -> dict:
    """Health check for Docker Engine API connection."""
    try:
        import httpx

        host = os.environ.get("DOCKER_HOST", "localhost")
        port = os.environ.get("DOCKER_PORT", "2375")
        use_tls = os.environ.get("DOCKER_TLS", "false").lower() == "true"

        scheme = "https" if use_tls else "http"
        base_url = f"{scheme}://{host}:{port}"

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/version")
            if resp.status_code == 200:
                version = resp.json()
                return {
                    "status": "ok",
                    "detail": f"Docker {version.get('Version', '?')} erreichbar ({host}:{port})",
                }
            return {"status": "error", "detail": f"Docker API antwortete mit HTTP {resp.status_code}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"Docker nicht erreichbar: {exc}"}


module_manifest = ModuleManifest(
    name="docker",
    display_name="Docker",
    description="Docker Host Management — Containers, Images, Volumes, System Info",
    version="1.1.1",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="DOCKER_",
    required_secrets=[],
    optional_secrets=["DOCKER_TLS_CERT", "DOCKER_TLS_KEY"],
    routing_keywords=[
        "docker", "container", "image", "volume", "compose",
        "dockerhub", "pull", "build", "registry",
    ],
    api_prefix="/api/docker",
    dashboard_tab={"id": "docker", "label": "Docker", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>'},
    health_check=check_docker_health,
)
