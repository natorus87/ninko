"""Tasmota Modul – Package Init."""

from modules.tasmota.manifest import module_manifest
from modules.tasmota.agent import TasmotaAgent
from modules.tasmota.routes import router

agent = TasmotaAgent()

__all__ = ["module_manifest", "agent", "router"]
