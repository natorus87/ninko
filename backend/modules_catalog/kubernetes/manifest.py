"""
Kubernetes module — Manifest with metadata and health check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.kubernetes")


async def check_k8s_health() -> dict:
    """Health check for Kubernetes cluster connection."""
    try:
        from kubernetes import client
        from .tools import _get_k8s_client

        v1, _, _ = await _get_k8s_client()
        version = client.VersionApi().get_code()
        return {
            "status": "ok",
            "detail": f"Kubernetes {version.git_version} reachable",
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"Cluster not reachable: {exc}"}


module_manifest = ModuleManifest(
    name="kubernetes",
    display_name="Kubernetes",
    description=(
        "Kubernetes / k8s cluster management: cluster-wide queries across all namespaces. "
        "Workloads (Deployments, StatefulSets, DaemonSets, Jobs, CronJobs, ReplicaSets), "
        "Pods (list, describe, logs, restart/neustart), Nodes (list, describe, top), "
        "Services, Ingresses, Endpoints, NetworkPolicies, ConfigMaps, Secrets (metadata only), "
        "PVCs, PersistentVolumes, StorageClasses, HPAs, Events. "
        "Create/apply via YAML, patch deployments, scale, rollout restart. Metrics via metrics-server. "
        "Diagnose CrashLoopBackOff, evicted pods, kube-system issues."
    ),
    version="1.3.2",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="K8S_",
    required_secrets=[],
    optional_secrets=["K8S_KUBECONFIG"],
    routing_keywords=[
        "pod",
        "pods",
        "deployment",
        "deployments",
        "namespace",
        "namespaces",
        "cluster",
        "kubectl",
        "neustart",
        "neustarten",
        "neu starten",
        "skalieren",
        "replicas",
        "ingress",
        "service",
        "services",
        "kubernetes",
        "k8s",
        "pod container",
        "crashloop",
        "evicted",
        "logs",
        "log",
        "node",
        "pod neustarten",
        "pod neu starten",
        "rollout neustart",
        "rollout neustarten",
        "deployment neu starten",
        "nodes",
        "configmap",
        "configmaps",
        "secret",
        "secrets",
        "volume",
        "volumes",
        "pvc",
        "pvcs",
        "pv",
        "persistentvolume",
        "storageclass",
        "helm",
        "kube-system",
        "statefulset",
        "statefulsets",
        "daemonset",
        "daemonsets",
        "replicaset",
        "replicasets",
        "job",
        "jobs",
        "cronjob",
        "cronjobs",
        "hpa",
        "autoscaler",
        "endpoints",
        "networkpolicy",
        "events",
        "describe",
        "top",
        "metrics",
    ],
    api_prefix="/api/k8s",
    dashboard_tab={
        "id": "k8s",
        "label": "Kubernetes",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>',
    },
    health_check=check_k8s_health,
)
