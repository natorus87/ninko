"""
Kubernetes Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from modules.kubernetes.tools import (
    get_cluster_status,
    get_all_pods,
    get_failing_pods,
    get_deployment_status,
    get_recent_events,
    list_namespaces,
    list_services,
    restart_pod as restart_pod_tool,
    scale_deployment as scale_deployment_tool,
    rollout_restart as rollout_restart_tool,
)
from modules.kubernetes.remediation_plans import auto_remediate_failing_pods

logger = logging.getLogger("ninko.modules.kubernetes.routes")
router = APIRouter()


@router.get("/status")
async def cluster_status(connection_id: str = ""):
    """Cluster-Gesamtstatus."""
    return await get_cluster_status.ainvoke({"connection_id": connection_id})


@router.get("/namespaces")
async def namespaces(connection_id: str = ""):
    """Alle Namespaces."""
    return await list_namespaces.ainvoke({"connection_id": connection_id})


@router.get("/pods/{namespace}")
async def pods(namespace: str, connection_id: str = ""):
    """Alle Pods in einem Namespace."""
    return await get_all_pods.ainvoke({"namespace": namespace, "connection_id": connection_id})


@router.get("/pods")
async def all_pods(connection_id: str = ""):
    """Alle Pods im Default-Namespace."""
    return await get_all_pods.ainvoke({"namespace": "default", "connection_id": connection_id})


@router.get("/failing")
async def failing_pods(namespace: str = "", connection_id: str = ""):
    """Alle fehlerhaften Pods."""
    return await get_failing_pods.ainvoke({"namespace": namespace, "connection_id": connection_id})


@router.get("/events/{namespace}")
async def events(namespace: str, minutes: int = 30, connection_id: str = ""):
    """Letzte Events eines Namespaces."""
    return await get_recent_events.ainvoke({
        "namespace": namespace,
        "last_minutes": minutes,
        "connection_id": connection_id,
    })


@router.get("/services/{namespace}")
async def services(namespace: str, connection_id: str = ""):
    """Services in einem Namespace."""
    return await list_services.ainvoke({"namespace": namespace, "connection_id": connection_id})


@router.post("/restart/{namespace}/{pod_name}")
async def restart_pod_api(namespace: str, pod_name: str, connection_id: str = ""):
    """Pod neu starten."""
    return await restart_pod_tool.ainvoke({
        "namespace": namespace,
        "pod_name": pod_name,
        "connection_id": connection_id,
    })


@router.post("/scale/{namespace}/{deployment_name}")
async def scale_deployment_api(namespace: str, deployment_name: str, replicas: int = 1, connection_id: str = ""):
    """Deployment skalieren."""
    return await scale_deployment_tool.ainvoke({
        "namespace": namespace,
        "name": deployment_name,
        "replicas": replicas,
        "connection_id": connection_id,
    })


@router.post("/rollout-restart/{namespace}/{deployment_name}")
async def rollout_restart_api(namespace: str, deployment_name: str, connection_id: str = ""):
    """Rollout Restart eines Deployments."""
    return await rollout_restart_tool.ainvoke({
        "namespace": namespace,
        "deployment_name": deployment_name,
        "connection_id": connection_id,
    })


@router.post("/remediate")
async def remediate(namespace: str = "", connection_id: str = ""):
    """Automatische Remediation aller failing Pods."""
    return await auto_remediate_failing_pods(namespace=namespace)
