"""Proxmox Modul – Package Init."""

from .manifest import module_manifest
from .agent import ProxmoxAgent
from .routes import router

agent = ProxmoxAgent()

__all__ = ["module_manifest", "agent", "router"]
