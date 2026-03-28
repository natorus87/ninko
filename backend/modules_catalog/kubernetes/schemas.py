"""
Kubernetes Modul – Pydantic Schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PodInfo(BaseModel):
    """Pod-Status-Informationen."""

    name: str
    namespace: str
    status: str
    ready: str  # "1/1", "0/1", etc.
    restarts: int = 0
    age: str = ""
    node: str = ""
    ip: str = ""


class DeploymentInfo(BaseModel):
    """Deployment-Status."""

    name: str
    namespace: str
    ready: str  # "3/3"
    available: int = 0
    desired: int = 0
    updated: int = 0
    age: str = ""


class NamespaceInfo(BaseModel):
    """Namespace-Informationen."""

    name: str
    status: str
    labels: dict = {}


class ServiceInfo(BaseModel):
    """Service-Informationen."""

    name: str
    namespace: str
    type: str  # ClusterIP, NodePort, LoadBalancer
    cluster_ip: str = ""
    ports: list[str] = []


class IngressInfo(BaseModel):
    """Ingress-Informationen."""

    name: str
    namespace: str
    hosts: list[str] = []
    class_name: str = ""


class PvcInfo(BaseModel):
    """PersistentVolumeClaim-Informationen."""

    name: str
    namespace: str
    status: str
    capacity: str = ""
    storage_class: str = ""


class EventInfo(BaseModel):
    """Kubernetes-Event."""

    type: str  # Normal, Warning
    reason: str
    message: str
    source: str = ""
    object: str = ""
    timestamp: str = ""


class ClusterStatusResponse(BaseModel):
    """Gesamt-Cluster-Status."""

    nodes: int = 0
    namespaces: int = 0
    total_pods: int = 0
    running_pods: int = 0
    failing_pods: int = 0
    deployments: int = 0


class K8sActionResponse(BaseModel):
    """Antwort auf eine K8s-Aktion (Restart, Scale, etc.)."""

    action: str
    target: str
    namespace: str
    status: str  # "success" | "error"
    detail: str = ""
