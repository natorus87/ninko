"""
Kubernetes module — FastAPI Router for dashboard API.
"""

from __future__ import annotations

import ast
import json
import logging

from fastapi import APIRouter

from .tools import (
    get_cluster_status,
    get_all_pods,
    get_failing_pods,
    get_recent_events,
    list_namespaces,
    list_services,
    restart_pod as restart_pod_tool,
    scale_deployment as scale_deployment_tool,
    rollout_restart as rollout_restart_tool,
)
from .remediation_plans import auto_remediate_failing_pods

logger = logging.getLogger("ninko.modules.kubernetes.routes")
router = APIRouter()


def _normalize_tool_output(value: object) -> object:
    if isinstance(value, str):
        text = value.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return value
    return value


@router.get("/status")
async def cluster_status(connection_id: str = "") -> object:
    """Overall cluster status."""
    result = await get_cluster_status.ainvoke({"connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/namespaces")
async def namespaces(connection_id: str = "") -> object:
    """All namespaces."""
    result = await list_namespaces.ainvoke({"connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/pods/{namespace}")
async def pods(namespace: str, connection_id: str = "") -> object:
    """All pods in a namespace."""
    result = await get_all_pods.ainvoke({"namespace": namespace, "connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/pods")
async def all_pods(connection_id: str = "") -> object:
    """All pods in the default namespace."""
    result = await get_all_pods.ainvoke({"namespace": "default", "connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/failing")
async def failing_pods(namespace: str = "", connection_id: str = "") -> object:
    """All failing pods."""
    result = await get_failing_pods.ainvoke({"namespace": namespace, "connection_id": connection_id})
    return _normalize_tool_output(result)


@router.get("/events/{namespace}")
async def events(namespace: str, minutes: int = 30, connection_id: str = "") -> object:
    """Recent events of a namespace."""
    result = await get_recent_events.ainvoke({
        "namespace": namespace,
        "last_minutes": minutes,
        "connection_id": connection_id,
    })
    return _normalize_tool_output(result)


@router.get("/services/{namespace}")
async def services(namespace: str, connection_id: str = "") -> object:
    """Services in a namespace."""
    result = await list_services.ainvoke({"namespace": namespace, "connection_id": connection_id})
    return _normalize_tool_output(result)


@router.post("/restart/{namespace}/{pod_name}")
async def restart_pod_api(namespace: str, pod_name: str, connection_id: str = "") -> object:
    """Restart a pod."""
    return await restart_pod_tool.ainvoke({
        "namespace": namespace,
        "pod_name": pod_name,
        "connection_id": connection_id,
    })


@router.post("/scale/{namespace}/{deployment_name}")
async def scale_deployment_api(namespace: str, deployment_name: str, replicas: int = 1, connection_id: str = "") -> object:
    """Scale a deployment."""
    return await scale_deployment_tool.ainvoke({
        "namespace": namespace,
        "name": deployment_name,
        "replicas": replicas,
        "connection_id": connection_id,
    })


@router.post("/rollout-restart/{namespace}/{deployment_name}")
async def rollout_restart_api(namespace: str, deployment_name: str, connection_id: str = "") -> object:
    """Rollout restart of a deployment."""
    return await rollout_restart_tool.ainvoke({
        "namespace": namespace,
        "deployment_name": deployment_name,
        "connection_id": connection_id,
    })


@router.post("/remediate")
async def remediate(namespace: str = "", connection_id: str = "") -> object:
    """Automatic remediation of all failing pods."""
    return await auto_remediate_failing_pods(namespace=namespace)
