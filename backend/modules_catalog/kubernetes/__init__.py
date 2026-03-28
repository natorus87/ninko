"""Kubernetes Modul – Package Init."""

from .manifest import module_manifest
from .agent import KubernetesAgent
from .routes import router

agent = KubernetesAgent()

__all__ = ["module_manifest", "agent", "router"]
