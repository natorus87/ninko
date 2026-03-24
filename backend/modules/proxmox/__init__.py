"""Proxmox Modul – Package Init."""

from modules.proxmox.manifest import module_manifest
from modules.proxmox.agent import ProxmoxAgent
from modules.proxmox.routes import router

agent = ProxmoxAgent()

__all__ = ["module_manifest", "agent", "router"]
