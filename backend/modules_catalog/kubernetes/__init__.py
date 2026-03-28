"""Kubernetes Modul – Package Init."""

from modules.kubernetes.manifest import module_manifest
from modules.kubernetes.agent import KubernetesAgent
from modules.kubernetes.routes import router

agent = KubernetesAgent()

__all__ = ["module_manifest", "agent", "router"]
