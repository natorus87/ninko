"""
Kubernetes Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.kubernetes")


async def check_k8s_health() -> dict:
    """Health-Check für Kubernetes-Cluster-Verbindung."""
    try:
        from kubernetes import client, config
        from modules.kubernetes.tools import _get_k8s_client

        v1, _, _ = await _get_k8s_client()
        version = client.VersionApi().get_code()
        return {
            "status": "ok",
            "detail": f"Kubernetes {version.git_version} erreichbar",
        }
    except Exception as e:
        return {"status": "error", "detail": f"Cluster nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="kubernetes",
    display_name="Kubernetes",
    description="Kubernetes Cluster Management – Pods, Deployments, Services, Health-Monitoring",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="K8S_",
    required_secrets=[],
    optional_secrets=["K8S_KUBECONFIG"],
    routing_keywords=[
        "pod", "deployment", "namespace", "cluster", "kubectl",
        "neustart", "skalieren", "replicas", "ingress", "service",
        "kubernetes", "k8s", "container", "crashloop", "evicted",
    ],
    api_prefix="/api/k8s",
    dashboard_tab={"id": "k8s", "label": "Kubernetes", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'},
    health_check=check_k8s_health,
)
